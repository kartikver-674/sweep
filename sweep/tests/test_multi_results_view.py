"""Multi-Track Phase 4 (P4-R2): the Results of a Multi-Track run.

All Jobs is every row the engine kept, in its order; a résumé's view is the
rows its track has an evaluation for (track_evals), each with that track's own
score and matched skills, ranked by that score. The views are the RUN's tracks,
never the setup as it stands later; labels are presentation only and follow a
rename, even after the run started. Each row says which résumé to use in the
engine's own terms — relative, the caution first — and nothing here scores,
compares or recommends. A one-track run's Results are today's, untouched.

The Render public app runs through its own routes against the real worker app
on loopback; the setup is P4-U1's (persona fixtures, real engine dry runs with
sockets refused, no run child). The rows each run serves are engine-shaped and
synthetic, written as the engine writes them; every one passes P4-R1's strict
reader. No model, provider or external network.
"""
import copy
import csv
import html
import json
import os
import re
import unittest
from unittest import mock

import markupsafe
import scraper
from sweep import app as app_module
from sweep import logic, public, worker_link
from sweep.tests import test_multi_render as r1
from sweep.tests import test_multi_setup as u1

setUpModule, tearDownModule = r1.setUpModule, r1.tearDownModule

A, B, C = "a" * 16, "b" * 16, "c" * 16
# A run calls each résumé by its editable name (design decision 4: the label the
# visitor can change is primary, the file it came from is secondary). The harness
# reads each persona's first search title as its default name and uploads
# <who>-cv.pdf.
LA, LB, LC = u1.LABEL["ada"], u1.LABEL["bhaskar"], u1.LABEL["chen"]
FA, FB, FC = "ada-cv.pdf", "bhaskar-cv.pdf", "chen-cv.pdf"
SKILLS = {A: "python, django", B: "react, node.js", C: "go, kubernetes"}
CODES = ("clear", "close", "tied", "split")
NEVER = ("clear match", "strong match", "weak match", "best chance", "best fit", "winner",
         "best résumé", "targeted", "specialis", "direct", "poor match", "unsuitable",
         "don't apply", "low chance", "not recommended", "%")


def job(n, best, scores, rec=None, kind=None, caution=None, found_by=None):
    """One engine row: `scores` {track: score}, each track with its own skills."""
    evals = {t: {"s": s, "m": SKILLS[t]} for t, s in scores.items()}
    row = {"title": f"Job {n}", "company": f"Company {n}", "location": "Bengaluru, India",
           "source_site": "greenhouse", "apply_url": f"https://jobs.test/{n}",
           "date_posted": "2026-09-27", "score": scores[best], "matched_skills": SKILLS[best],
           "best_track": best, "track_evals": json.dumps(evals, separators=(",", ":")),
           "found_by": found_by or best}
    if rec:
        row.update(recommended_tracks=";".join(rec), recommendation=kind)
        if caution is not None:
            row["recommendation_caution"] = caution
    return row


# Score-descending, as the engine ranks them. Evaluated for 3, 2, 1 tracks;
# found_by never the membership; J6 negative.
ROWS = [
    job(1, A, {A: 30, B: 12, C: 5}, [A], "clear", "", found_by=B),
    job(2, B, {B: 25, A: 24}, [B, A], "close", ""),
    job(3, C, {C: 20}, [C], "clear", "no_focus_evidence", found_by="free"),
    job(5, B, {B: 18, A: 9, C: 15}, [B, C], "split", ""),
    job(4, A, {A: 10, B: 10, C: 10}, [A, B, C], "tied", "no_focus_evidence", found_by=f"{A};{B}"),
    job(6, A, {A: -3, B: -5}, [A], "clear", ""),
]
ORDER = {None: [1, 2, 3, 5, 4, 6], A: [1, 2, 4, 5, 6], B: [2, 5, 1, 4, 6], C: [3, 5, 4, 1]}
SCORE = {A: {1: 30, 2: 24, 4: 10, 5: 9, 6: -3}, B: {2: 25, 5: 18, 1: 12, 4: 10, 6: -5},
         C: {3: 20, 5: 15, 4: 10, 1: 5}}


class Results(u1.Setup):
    """A Multi-Track run of the setup's résumés, its rows served by the worker."""

    def run_multi(self, *whos):
        with u1.fixed_ids(A, B, C):
            ids = self.free(*whos)
        self.confirm()
        self.assertEqual(self.client.post("/run").status_code, 302)
        self.run_id = self.cookie()["run_id"]
        self.settled(self.run_id)
        return ids

    def serve(self, rows=ROWS, recommend=True, caution=True):
        out = self.worker.store.output_dir(self.run_id)
        os.makedirs(out, exist_ok=True)
        cols = scraper.multi_output_columns(recommend, caution)
        with open(os.path.join(out, "jobs_2026-09-28_1200.csv"), "w", newline="",
                  encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({c: row.get(c, "") for c in cols})

    def page(self, track=None, **args):
        answer = self.client.get("/results", query_string=dict(args, **(
            {"track": track} if track else {})))
        self.assertEqual(answer.status_code, 200, answer.get_data(as_text=True)[-500:])
        return answer.get_data(as_text=True)

    def seen(self, page):
        return [int(n) for n in re.findall(r"<b>Job (\d+)</b>", page)]

    def rows_of(self, page):
        """{job n: its whole table row, markup kept and entities read}."""
        return {int(m.group(1)): html.unescape(m.group(0)) for m in re.finditer(
            r"<tr\b(?:(?!</tr>).)*?<b>Job (\d+)</b>.*?</tr>", page, re.S)}

    def flat(self, markup):
        """What a reader of the markup reads: tags gone, entities read, spaces one."""
        return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", markup))).strip()

    def said(self, row):
        """The caution and suggestion lines of one row, as text, in page order."""
        return [self.flat(re.sub(r'<span class="bang"[^>]*>.*?</span>', "", m)) for m in re.findall(
            r'<p class="(?:caution|suggest)">(.*?)</p>', row, re.S)]

    def views(self, page):
        nav = re.search(r'<nav class="views" aria-label="Which jobs to show">(.*?)</nav>',
                        page, re.S)
        return nav and [(re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", a))).strip(),
                         "aria-current" in a)
                        for a in re.findall(r"<a\b.*?</a>", nav.group(1), re.S)]

    def captured(self, **args):
        """The rows the template is handed."""
        got = []
        with mock.patch.object(app_module, "render_template",
                               side_effect=lambda name, **kw: got.append(kw) or ""):
            self.client.get("/results", query_string=args)
        return got[-1]


class Legacy(Results):
    """Items 3, 5, 55: a one-track run, or the product off — today's Results."""

    def test_a_one_track_run_is_todays_results(self):
        self.add("ada")
        self.client.post("/key/free")
        self.client.post("/configure", data=r1.FORMS["india"])
        self.client.post("/run")
        self.run_id = self.cookie()["run_id"]
        self.settled(self.run_id)
        self.assertNotIn("run_tracks", self.cookie())
        legacy = [dict({k: v for k, v in r.items() if k not in scraper.MULTI_COLUMNS
                        and k not in ("recommended_tracks", "recommendation",
                                      "recommendation_caution")}) for r in ROWS]
        out = self.worker.store.output_dir(self.run_id)
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "jobs_2026-09-28_1200.csv"), "w", newline="",
                  encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=scraper.OUTPUT_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(legacy)
        page = self.page()
        self.assertIsNone(self.views(page))
        self.assertNotIn("Suggested résumé", page)
        self.assertEqual(self.seen(page), [1, 2, 3, 5, 4])        # today's floor: no -3
        kw = self.captured()
        self.assertEqual((kw["views"], kw["view_track"], kw["export_total"], kw["total"]),
                         (None, None, 5, 5))
        self.assertTrue(all("_words" not in r for b in kw["buckets"].values() for r in b))

    def test_off_a_multi_runs_results_are_todays_page(self):
        self.run_multi("ada", "bhaskar")
        self.serve([job(1, A, {A: 30, B: 12}, [A], "clear", ""),
                    job(2, B, {B: 25, A: 24}, [B, A], "close", "")])
        os.environ.pop(worker_link.MULTI_FLAG)
        page = self.page(track=B)
        self.assertIsNone(self.views(page))
        self.assertNotIn("Suggested résumé", page)
        self.assertEqual(self.seen(page), [1, 2])
        self.assertIn('title="Match score 30 — how much of your résumé this job asks for"', page)


class AllJobs(Results):
    """Items 8, 11, 18, 30, 31, 43: every row once, in the engine's order."""

    def test_every_row_in_engine_order_with_its_recommendation(self):
        self.run_multi("ada", "bhaskar", "chen")
        self.serve()
        page = self.page()
        self.assertEqual(self.seen(page), ORDER[None])            # J6 at -3 included
        self.assertEqual(self.views(page), [("All Jobs (6) — showing", True),
                                            (f"{LA} (5)", False), (f"{LB} (5)", False),
                                            (f"{LC} (4)", False)])
        rows = self.rows_of(page)
        self.assertIn(f'title="Match score 30 for {LA} — how much of that résumé', rows[1])
        self.assertEqual(self.said(rows[1]), [f"Suggested résumé: {LA}."])
        self.assertEqual(self.said(rows[2]), [f"Suggested résumé: {LB}. {LA} is close behind."])
        self.assertIn(f'title="Match score 25 for {LB} — how much of that résumé', rows[2])
        self.assertIn(f'title="Match score 20 for {LC} — how much of that résumé', rows[3])
        self.assertEqual(self.said(rows[4])[-1], f"{LA}, {LB} and {LC} fit equally.")
        self.assertEqual(self.said(rows[5]), [f"{LB} covers more of this posting. {LC} is also suggested."])
        self.assertIn('<td class="score" title="Match score -3', rows[6])
        self.assertIn(">-3</td>", rows[6])
        for n, row in rows.items():                       # the skills are the row's own
            skills = SKILLS[next(r for r in ROWS if r["title"] == f"Job {n}")["best_track"]]
            for s in skills.split(", "):
                self.assertIn(f'<span class="tag">{s}</span>', row)

    def test_ties_keep_the_engines_order_everywhere(self):
        # Equal top scores: the engine's own (arrival) order decides All Jobs,
        # never any one résumé's scores; a view's ties fall back to it too.
        self.run_multi("ada", "bhaskar", "chen")
        self.serve([job(7, A, {A: 8, C: 1}, [A], "clear", ""),
                    job(8, B, {B: 8, C: 7}, [B], "clear", ""),
                    job(9, C, {C: 8, A: 2}, [C], "clear", ""),
                    job(10, A, {A: 8, B: 3, C: 8}, [A, C], "tied", "")])
        self.assertEqual(self.seen(self.page()), [7, 8, 9, 10])
        self.assertEqual(self.seen(self.page(track=C)), [9, 10, 8, 7])
        self.assertEqual(self.seen(self.page(track=A)), [7, 10, 9])

    def test_the_rows_are_the_rows_once(self):
        self.run_multi("ada", "bhaskar", "chen")
        self.serve()
        views = {v: self.captured(**({"track": v} if v else {})) for v in (None, A, B, C)}
        keys = {v: [r["_key"] for b in kw["buckets"].values() for r in b]
                for v, kw in views.items()}
        self.assertEqual(len(keys[None]), len(ROWS))
        self.assertEqual(len(set(keys[None])), len(ROWS))
        for v in (A, B, C):
            self.assertLessEqual(set(keys[v]), set(keys[None]))
            self.assertEqual(len(keys[v]), len(set(keys[v])))
        applied = {r["_key"]: r["applied"] for kw in views.values()
                   for b in kw["buckets"].values() for r in b}
        self.assertEqual(len(applied), len(ROWS))                 # one state per job
        self.assertFalse(any(k.startswith(("rows", "view", "_")) for k in self.room()))


class TrackViews(Results):
    """Items 13-16, 32, 35: track_evals decides a view; its own score orders it."""

    def test_each_view_is_its_tracks_evaluations_by_its_own_score(self):
        self.run_multi("ada", "bhaskar", "chen")
        self.serve()
        for tid, label in ((A, LA), (B, LB), (C, LC)):
            with self.subTest(view=label):
                page = self.page(track=tid)
                self.assertEqual(self.seen(page), ORDER[tid])
                self.assertIn(f'Match<span class="visually-hidden"> for {label}</span></th>', page)
                self.assertIn(f"{label} ({len(ORDER[tid])}) — showing", [
                    v for v, current in self.views(page) if current][0])
                for n, row in self.rows_of(page).items():
                    self.assertIn(f">{SCORE[tid][n]}</td>", row)
                    self.assertIn(f'title="Match score {SCORE[tid][n]} for {label} —', row)
                    for s in SKILLS[tid].split(", "):
                        self.assertIn(f'<span class="tag">{s}</span>', row)
                # P4-E1: the export offered here is All Jobs', and says so.
                self.assertIn("Export All Jobs: 6 listings", page)

    def test_the_recommendation_stays_the_jobs_in_every_view(self):
        self.run_multi("ada", "bhaskar", "chen")
        self.serve()
        said = {n: self.said(row) for n, row in self.rows_of(self.page()).items()}
        for tid in (A, B, C):
            for n, row in self.rows_of(self.page(track=tid)).items():
                self.assertEqual(self.said(row), said[n])

    def test_filters_apply_to_the_view_on_screen(self):
        self.run_multi("ada", "bhaskar", "chen")
        self.serve()
        self.assertEqual(self.seen(self.page(track=B, min=12)), [2, 5, 1])   # B's scores
        self.assertEqual(self.seen(self.page(min=12)), [1, 2, 3, 5])         # the rows' own
        self.assertEqual(self.seen(self.page(track=C, q="job 5")), [5])
        page = self.page(track=A, sort="recent")
        self.assertEqual(sorted(self.seen(page)), sorted(ORDER[A]))
        self.assertIn(f'<input type="hidden" name="track" value="{A}">', page)

    def test_an_id_that_is_not_one_of_this_runs_is_all_jobs(self):
        self.run_multi("ada", "bhaskar")
        self.serve([job(1, A, {A: 30, B: 12}, [A], "clear", "")])
        self.upload("chen")                       # a résumé this run never had
        later = self.ids()[2]
        stranger = self.app.test_client()
        stranger.post("/beta", data={"code": r1.CODE})
        for tid in ("0" * 16, later, C, "", "../" + A, A.upper()):
            with self.subTest(tid=tid):
                page = self.client.get("/results", query_string={"track": tid}).get_data(
                    as_text=True)
                self.assertEqual(self.views(page)[0], ("All Jobs (1) — showing", True))
        # Another browser has no run of its own: no Results, let alone a view.
        self.assertEqual(stranger.get(f"/results?track={A}").status_code, 302)

    def test_a_view_with_no_evaluations_says_so_neutrally(self):
        self.run_multi("ada", "bhaskar", "chen")
        self.serve([job(1, A, {A: 30, B: 12}, [A], "clear", "")])
        page = self.page(track=C)
        self.assertIn("No evaluated jobs for this résumé in this Sweep.", page)
        self.assertIn(f"{LC} (0) — showing", [v for v, cur in self.views(page) if cur][0])
        self.assertNotIn("didn't find any jobs", page)

    def test_an_empty_run_is_the_usual_empty_state(self):
        self.run_multi("ada", "bhaskar")
        self.serve([])
        page = self.page()
        self.assertIn("No jobs to show", page)
        # Nothing at all to switch between, filter or export: no tabs, no tools, no scoring door.
        self.assertIsNone(self.views(page))
        for chrome in ('class="bar"', "How match scores work", "Filter and sort", "Export…"):
            self.assertNotIn(chrome, page)
        self.assertIn("0 jobs found", self.flat(page))


class Words(Results):
    """Items 19-28: the engine's recommendation, in relative words."""

    def test_the_words_for_each_kind(self):
        labels = {A: "Frontend", B: "Mobile", C: "Full stack"}
        say = lambda rec, kind, caution=None: logic.recommendation_words(  # noqa: E731
            dict({"recommended_tracks": rec, "recommendation": kind},
                 **({} if caution is None else {"recommendation_caution": caution})), labels)
        self.assertEqual(say([A], "clear"), {"caution": None,
                                             "suggestion": ["Suggested résumé: Frontend."]})
        self.assertEqual(say([A, B], "close")["suggestion"],
                         ["Suggested résumé: Frontend.", "Mobile is close behind."])
        self.assertEqual(say([A, B, C], "close")["suggestion"],
                         ["Suggested résumé: Frontend.", "Mobile and Full stack are close behind."])
        self.assertEqual(say([A, B], "tied")["suggestion"], ["Frontend and Mobile fit equally."])
        self.assertEqual(say([C, A, B], "tied")["suggestion"],
                         ["Full stack, Frontend and Mobile fit equally."])
        self.assertEqual(say([A, B], "split")["suggestion"],
                         ["Frontend covers more of this posting.", "Mobile is also suggested."])
        self.assertEqual(say([A, B, C], "split")["suggestion"],
                         ["Frontend covers more of this posting.",
                          "Mobile and Full stack are also suggested."])
        self.assertEqual(say([A], "clear", "no_focus_evidence")["caution"],
                         "This posting doesn't mention the skills or role your suggested "
                         "résumé (Frontend) focuses on.")
        self.assertEqual(say([A, B], "tied", "no_focus_evidence")["caution"],
                         "This posting doesn't mention the skills or role these suggested "
                         "résumés focus on.")
        for caution in (None, ""):
            self.assertIsNone(say([A], "clear", caution)["caution"])
        self.assertIsNone(logic.recommendation_words({"best_track": A}, labels))
        self.assertEqual(logic.NO_FOCUS_EVIDENCE, scraper.NO_FOCUS_EVIDENCE)
        for words in (say(r, k, "no_focus_evidence") for r, k in
                      (([A], "clear"), ([A, B], "close"), ([A, B], "tied"), ([A, B], "split"))):
            text = " ".join([words["caution"]] + words["suggestion"]).lower()
            for bad in NEVER + ("confiden", "probab", "chance", "hire"):
                self.assertNotIn(bad, text)

    def test_the_page_says_it_caution_first_and_never_the_codes(self):
        self.run_multi("ada", "bhaskar", "chen")
        self.serve()
        page = self.page()
        rows = self.rows_of(page)
        for n in (3, 4):
            self.assertLess(rows[n].index("<b>Note:</b> This posting doesn't mention"),
                            rows[n].index("Suggested résumé" if n == 3 else "fit equally"))
        self.assertIn(f"your suggested résumé ({LC}) focuses on", self.flat(rows[3]))
        self.assertIn("these suggested résumés focus on", self.flat(rows[4]))
        for n in (1, 2, 5, 6):
            self.assertNotIn("Note:", rows[n])
        visible = re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)\b.*?</\1>", "", page, flags=re.S))
        for code in CODES:
            self.assertNotRegex(visible, rf"(?<![\w-]){code}(?!\s+behind)(?![\w-])", code)
        for bad in NEVER:
            self.assertNotIn(bad, visible.lower())
        for tid in (A, B, C):
            self.assertNotIn(tid, visible)                            # ids only in links
        self.assertNotIn("no_focus_evidence", page)

    def test_absent_and_empty_cautions_say_nothing_and_stay_distinct(self):
        self.run_multi("ada", "bhaskar")
        two = [job(1, A, {A: 30, B: 12}, [A], "clear", ""),
               job(2, B, {B: 25, A: 24}, [B, A], "close", "")]
        for caution, stored in ((True, ""), (False, None)):
            with self.subTest(caution=caution):
                self.serve(two, caution=caution)
                page = self.page()
                self.assertNotIn("Note:", page)
                self.assertIn(f"Suggested résumé: {LA}.", self.flat(page))
                rows = [r for b in self.captured()["buckets"].values() for r in b]
                for row in rows:
                    if stored is None:
                        self.assertNotIn("recommendation_caution", row)
                    else:
                        self.assertEqual(row["recommendation_caution"], "")
        self.serve(two, recommend=False, caution=False)
        page = self.page()
        self.assertNotIn("Suggested résumé", page)
        self.assertNotIn("close behind", page)

    def test_the_view_refuses_a_bad_row_even_if_a_reader_let_it_through(self):
        self.run_multi("ada", "bhaskar")
        bad = dict(job(1, A, {A: 30, B: 12}, [A], "clear", ""), track_evals="[]")
        with mock.patch.object(worker_link, "_rows", lambda run_id, strict=False: [bad]):
            answer = self.client.get("/results")
        self.assertEqual(answer.status_code, 502)
        self.assertNotIn("Job 1", answer.get_data(as_text=True))

    def test_a_row_the_engine_cannot_have_written_renders_nothing(self):
        self.run_multi("ada", "bhaskar")
        good = job(1, A, {A: 30, B: 12}, [A], "clear", "")
        broken = {"unknown caution": dict(good, recommendation_caution="<b>weak</b>"),
                  "unknown kind": dict(good, recommendation="winner"),
                  "best_track not the run's": dict(good, best_track="d" * 16),
                  "track_evals not JSON": dict(good, track_evals="{"),
                  "recommended not led by best_track": dict(good, recommended_tracks=f"{B};{A}"),
                  "recommended empty": dict(good, recommended_tracks="")}
        for label, row in broken.items():
            with self.subTest(label):
                self.serve([good, row])
                answer = self.client.get("/results")
                self.assertEqual(answer.status_code, 502, label)
                text = answer.get_data(as_text=True)
                self.assertNotIn("Job 1", text)
                self.assertNotIn("weak", text)


class Labels(Results):
    """Items 6-10, 39-42, 46: ids decide, labels follow — by id only. The label
    is the résumé's editable name (design decision 4); the file it came from is
    the secondary line."""

    def names(self, page):
        return [v for v, _current in self.views(page)][1:]

    def test_a_rename_reaches_every_view_and_the_cookie_but_nothing_it_ran(self):
        a, b = self.run_multi("ada", "bhaskar")
        before = {k: self.cookie()[k] for k in ("run_id", "run_plan_hash")}
        requests, spawned = len(self.worker.bodies("/v1/runs")), len(self.worker.spawned)
        for moment in ("before results", "while running", "after results"):
            with self.subTest(moment):
                if moment == "while running":
                    self.worker.store.update(self.run_id, state="running")
                if moment == "after results":
                    self.worker.store.update(self.run_id, state="done")
                    self.serve([job(1, A, {A: 30, B: 12}, [A, B], "close", "")])
                name = f"Mobile {moment}"
                self.assertEqual(self.act(b, "rename", name=name).status_code, 303)
                self.assertEqual(self.cookie()["run_tracks"], [[a, LA], [b, name]])
                self.assertEqual({k: self.cookie()[k] for k in before}, before)
                if moment == "after results":
                    page = self.page()
                    self.assertEqual(self.names(page), [f"{LA} (1)", f"{name} (1)"])
                    self.assertIn(f"Suggested résumé: {LA}. {name} is close behind.", self.flat(page))
                    self.assertIn(f'Match<span class="visually-hidden"> for {name}</span></th>',
                                  self.page(track=b))
        self.assertEqual((len(self.worker.bodies("/v1/runs")), len(self.worker.spawned)),
                         (requests, spawned))
        again = self.render().test_client()                         # a restart
        again.set_cookie("session", r1.cookie_of(self.client), domain="localhost")
        page = again.get("/results").get_data(as_text=True)
        # The setup is gone with the process: the label the cookie kept.
        self.assertEqual(self.names(page), [f"{LA} (1)", "Mobile after results (1)"])

    def test_the_file_is_the_secondary_line_never_the_label(self):
        a, b = self.run_multi("ada", "bhaskar", "chen")[:2]
        self.serve()
        page = self.page(track=b)
        self.assertIn(f'title="From {FB}"', page)                   # the tab's hover
        note = self.flat(re.search(r'<p class="meta view-note">(.*?)</p>', page, re.S).group(1))
        self.assertEqual(note, f"Jobs Sweep evaluated for {LB} (from {FB}), ranked by that résumé's "
                               f"own match score. Exports always hold All Jobs.")
        for name in (FA, FB, FC):                                   # never a tab, a header or a sentence
            self.assertNotIn(name, self.flat(re.sub(r"<(nav|p)\b[^>]*(view-note|views)[^>]*>.*?</(nav|p)>",
                                                    "", page, flags=re.S)))
        for name in (FA, FB, FC):
            self.assertNotIn(name, " ".join(self.names(page)))
        allp = self.page()
        self.assertIn("Every job once, with the résumé Sweep suggests for it.", self.flat(allp))
        self.assertNotIn("view-note\">Jobs Sweep evaluated", allp)

    def test_the_two_track_flow(self):
        """§56: A/B run; All Jobs; A; B; rename B; reload; delete B; reload."""
        a, b = self.run_multi("ada", "bhaskar")
        self.serve([job(1, A, {A: 30, B: 12}, [A, B], "close", ""),
                    job(2, B, {B: 20}, [B], "clear", "")])
        self.assertEqual(self.views(self.page())[0], ("All Jobs (2) — showing", True))
        self.assertEqual(self.seen(self.page(track=a)), [1])
        self.assertEqual(self.seen(self.page(track=b)), [2, 1])
        self.act(b, "rename", name="Mobile")
        for _reload in range(2):
            page = self.page(track=b)
            self.assertIn(("Mobile (2) — showing", True), self.views(page))
            self.assertIn('Match<span class="visually-hidden"> for Mobile</span></th>', page)
        self.act(b, "remove")
        for _reload in range(2):
            page = self.page()
            self.assertEqual(self.names(page), [f"{LA} (1)", "Mobile (2)"])
            self.assertIn(f"Suggested résumé: {LA}. Mobile is close behind.", self.flat(page))
            self.assertEqual(self.seen(self.page(track=b)), [2, 1])

    def test_the_run_keeps_its_tracks_whatever_the_setup_does_later(self):
        a, b = self.run_multi("ada", "bhaskar")
        self.serve([job(1, A, {A: 30, B: 12}, [A, B], "close", ""),
                    job(2, B, {B: 20}, [B], "clear", "")])
        self.act(b, "rename", name="Mobile")
        self.act(b, "remove")                                        # gone from the setup
        with u1.fixed_ids("e" * 16):
            self.upload("chen")                                      # takes its place
        self.act(a, "deselect")
        page = self.page()
        self.assertEqual(self.names(page), [f"{LA} (1)", "Mobile (2)"])
        self.assertNotIn("Résumé 2", page)
        self.assertNotIn(LC, page)
        self.assertEqual(self.seen(self.page(track=b)), [2, 1])
        self.assertEqual(self.cookie()["run_tracks"], [[a, LA], [b, "Mobile"]])

    def test_labels_fall_back_to_the_cookie_then_to_run_order(self):
        a, b = self.run_multi("ada", "bhaskar")
        self.serve([job(1, A, {A: 30, B: 12}, [A, B], "close", "")])
        again = self.render().test_client()                          # the setup is gone
        with again.session_transaction() as s:
            s.update(self.cookie(), run_tracks=[[a, "x" * 41], [b, "Mobile"]])
        page = again.get("/results").get_data(as_text=True)
        self.assertEqual(self.names(page), ["Résumé 1 (1)", "Mobile (1)"])
        self.assertIn("Suggested résumé: Résumé 1. Mobile is close behind.", self.flat(page))
        self.assertNotIn(f'title="From', page)                      # no setup, no file to name

    def test_two_labels_that_read_alike_are_told_apart(self):
        a, b = self.run_multi("ada", "bhaskar")
        self.serve([job(1, A, {A: 30, B: 12}, [A, B], "close", "")])
        again = self.render().test_client()                          # the setup is gone
        with again.session_transaction() as s:
            s.update(self.cookie(), run_tracks=[[a, "Same"], [b, "SAME"]])
        page = again.get("/results").get_data(as_text=True)
        self.assertEqual(self.names(page), ["Same · 1 (1)", "SAME · 2 (1)"])

    def test_labels_are_text_never_markup(self):
        a, b = self.run_multi("ada", "bhaskar")
        self.serve([job(1, A, {A: 30, B: 12}, [A, B], "close", "no_focus_evidence")])
        evil = """<b onmouseover="x">&'y'</b>"""
        self.act(b, "rename", name=evil)
        evil_file = """<i onmouseover="x">&'y'.pdf"""              # the file, as the browser sent it
        self.track(b)["resume_name"] = evil_file
        for page in (self.page(), self.page(track=b)):
            self.assertNotIn(evil, page)
            self.assertNotIn("<b onmouseover", page)
            self.assertIn(str(markupsafe.escape(evil)), page)
        view = self.page(track=b)
        self.assertNotIn("<i onmouseover", view)
        self.assertIn(str(markupsafe.escape(evil_file)), view)

    def test_the_cookie_holds_ids_and_labels_only(self):
        self.run_multi("ada", "bhaskar", "chen")
        self.serve()
        for tid in (None, A, B, C):
            self.page(track=tid)
        cookie = self.cookie()
        self.assertLessEqual(set(cookie), u1.COOKIE)
        raw = json.dumps(cookie, ensure_ascii=False)
        for word in ("track_evals", "python", "react", "kubernetes", "Job 1", '"s"', "cv.pdf"):
            self.assertNotIn(word, raw)
        self.assertEqual([tid for tid, _ in cookie["run_tracks"]], [A, B, C])


class Exports(Results):
    """Items 44, 49 as amended by P4-E1 (test_multi_exports has the rest): the
    page's export count is the file's, every row the page lists."""

    def test_a_multi_runs_export_holds_what_the_page_says(self):
        self.run_multi("ada", "bhaskar", "chen")
        self.serve()
        page = self.page()
        self.assertIn("Export All Jobs: 6 listings", page)          # the file's own count
        body = self.client.get("/export.csv").get_data(as_text=True)
        self.assertEqual(len(body.splitlines()), 1 + 6)              # J6 at -3 in it
        rows = json.loads(self.client.get("/export.json").get_data(as_text=True))
        self.assertEqual(len(rows), 6)


class Accessible(Results):
    """Items 44-45: text, state not by colour, wrapping controls."""

    def test_the_views_are_labelled_links_and_one_is_current(self):
        self.run_multi("ada", "bhaskar", "chen")
        long = "A rather long label for this résumé"
        self.act(C, "rename", name=long)
        self.serve()
        page = self.page(track=B)
        nav = re.search(r'<nav class="views" aria-label="Which jobs to show">(.*?)</nav>',
                        page, re.S).group(1)
        links = re.findall(r"<a\b[^>]*>", nav)
        self.assertEqual(len(links), 4)
        self.assertEqual(sum('aria-current="page"' in a for a in links), 1)
        self.assertNotIn("primary", nav)                        # tabs, not buttons
        self.assertIn('<span class="visually-hidden"> — showing</span>', nav)
        self.assertIn((long + " (4)", False), self.views(page))
        self.assertNotIn("draggable", page)

    def test_a_forty_character_label_wraps_rather_than_widening_the_page(self):
        self.run_multi("ada", "bhaskar", "chen")
        self.act(C, "rename", name="Senior Full Stack Developer (Payments)")
        self.serve()
        css = open(os.path.join(os.path.dirname(app_module.__file__), "static", "sweep.css"),
                   encoding="utf-8").read()
        rule = re.search(r"^\.views a \{([^}]*)\}", css, re.M).group(1)
        self.assertIn("overflow-wrap: anywhere", rule)
        self.assertIn("max-width: 100%", rule)
        self.assertIn("flex-wrap: wrap", re.search(r"^\.views \{([^}]*)\}", css, re.M).group(1))


if __name__ == "__main__":
    unittest.main()
