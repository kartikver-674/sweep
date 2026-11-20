"""Multi-Track Phase 2B: the result side, over already-acquired copies.

finalize_multi(rows, tracks) evaluates every copy once per relevant track,
keeps it if any track is eligible, runs the Sweep's filters once, clusters
physical duplicates, picks each track's own best copy, the best track and the
representative, and returns one row per job carrying every eligible track's
evaluation. Relevance comes only from explicit provenance: PAID_TRACKS on a
paid copy, FREE on a free one (each track's title gate decides).

Nothing here runs a search: every row's provenance is attributed by hand,
standing in for what a Phase-3 run stamps (test_multi_plan runs main()).
Offline, synthetic rows and tracks.
"""
import copy
import csv
import dataclasses
import io
import itertools
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import experience_guard
import scraper
import skill_concepts
import title_gate
import track_recommendation
from sweep.tests.test_one_track_goldens import REPO, _env, _load, derived_for, prefs_for

sys.path.insert(0, os.path.join(REPO, "auto-apply"))
import make_profile  # noqa: E402

MERN, MOBILE, AI = "a1a1a1a1a1a1a1a1", "b2b2b2b2b2b2b2b2", "c3c3c3c3c3c3c3c3"


def track(tid, engine, years, skills, hints, exclude=(), penalties=None, halves=([], []),
          titles=(), bonus=0):
    return {"id": tid, "engine": engine,
            "SEARCH": {"role_keywords": [hints[0] + " developer"], "experience_years": years},
            "SETTINGS": {"max_experience_years": years + 3,
                         "candidate_experience_months": years * 12 + 4},
            "SCORING": {"skill_weights": skills, "penalty_terms": penalties or {},
                        "frontend_terms": list(halves[0]), "backend_terms": list(halves[1]),
                        "fullstack_title_terms": list(titles), "fullstack_bonus": bonus},
            "ATS_TITLE_HINTS": list(hints), "ATS_TITLE_EXCLUDE": list(exclude)}


TRACK_DATA = make_profile.check_tracks([
    track(MERN, "v2", 2, {"react": 5, "node.js": 4, "mongodb": 3, "typescript": 3},
          ["react", "node", "mern", "full stack"], halves=(["react"], ["node.js"]),
          titles=["mern"], bonus=4),
    track(MOBILE, "v2", 3, {"react native": 5, "kotlin": 4, "swift": 4, "typescript": 2},
          ["mobile", "android", "ios", "react native"]),
    track(AI, "v1", 0, {"python": 5, "pytorch": 4, "llm": 4},
          ["machine learning", "ml engineer", "ai engineer", "data scientist"],
          exclude=["intern"], penalties={"php": -6}),
])
SWEEP_SCORING = {"hard_drop_terms": ["intern", "internship"]}
FILTERS = {"max_age_days": 14, "min_comp_usd": 20000, "min_score": None,
           "drop_undated": False, "work_scope": "india", "remote_scopes": [],
           "drop_no_visa": False, "require_eor": False,
           "keep_restricted_if_hires_home": True, "drop_excluded": True,
           "experience_aggregate": "max", "home_utc_offset": 5.5}


def contexts(order=(MERN, MOBILE, AI)):
    by_id = {t["id"]: t for t in TRACK_DATA}
    return [scraper.track_context(by_id[tid], SWEEP_SCORING) for tid in order]


def job(name, title, description, paid=None, free=False, **over):
    row = {"Source": "linkedin" if paid else "greenhouse:probe", "Title": title,
           "Company": f"{name} Co", "Location": "Bengaluru, Karnataka", "Salary": "",
           "Experience": "", "Posted Date": "1 day ago",
           "Job URL": f"https://example.test/multi/{name}", "hires_home": "yes",
           "Description": description}
    if paid:
        row[scraper.PAID_TRACKS] = list(paid)
    if free:
        row[scraper.FREE] = True
    row.update(over)
    return row


# §18 of the Phase 2B brief, one row per case.
ROWS = [
    job("mern-only", "MERN Stack Developer", "React, Node.js and MongoDB.", paid=[MERN]),
    job("ai-only", "Machine Learning Engineer", "Python, PyTorch and LLM work.", paid=[AI]),
    job("shared", "Full Stack AI Engineer", "React, Node.js, Python and LLM.", paid=[AI, MERN]),
    job("free-mobile", "Android Developer", "Kotlin and React Native.", free=True),
    job("free-mern-mobile", "React Native Full Stack Developer",
        "React Native, React, Node.js and Kotlin.", free=True),
    job("a-too-senior", "React Developer",
        "React and Node.js. 8+ years of experience required.", paid=[MERN]),
    job("b-only", "React Native Developer",
        "React Native and Kotlin. 6+ years of experience required.", paid=[MERN, MOBILE]),
    job("a-wins", "React Developer", "React, Node.js, MongoDB and TypeScript.",
        paid=[MERN, MOBILE]),
    job("b-wins", "Mobile Developer", "React Native, Kotlin and Swift.", paid=[MERN, MOBILE]),
]


def urls(rows):
    return [r["apply_url"].rsplit("/", 1)[1] for r in rows]


class Isolated(unittest.TestCase):

    def setUp(self):
        bound = skill_concepts._BOUND
        self.addCleanup(setattr, skill_concepts, "_BOUND", bound)
        skill_concepts.bind(None)
        for patch in (mock.patch.dict(scraper.SETTINGS, FILTERS),
                      mock.patch.dict(os.environ, {skill_concepts.VERSION_ENV: "v1"})):
            patch.start()
            self.addCleanup(patch.stop)
        os.environ.pop(experience_guard.FLAG, None)

    def run_multi(self, rows=None, order=(MERN, MOBILE, AI)):
        return scraper.finalize_multi(copy.deepcopy(ROWS if rows is None else rows),
                                      contexts(order))

    def evals(self, out, name):
        row = next(r for r in out if r["apply_url"].endswith("/" + name))
        return row, json.loads(row["track_evals"])


# ===========================================================================
class Relevance(Isolated):

    def test_paid_copies_go_only_to_the_tracks_that_asked(self):
        tracks = contexts()
        got = {r["Job URL"].rsplit("/", 1)[1]: [t.id for t in scraper.relevant_tracks(r, tracks)]
               for r in ROWS}
        self.assertEqual(got["mern-only"], [MERN])
        self.assertEqual(got["ai-only"], [AI])
        self.assertEqual(got["shared"], [MERN, AI])            # track order, not request order

    def test_free_copies_go_to_each_track_whose_gate_admits_them(self):
        tracks = contexts()
        gate = lambda title: [t.id for t in scraper.relevant_tracks(  # noqa: E731
            job("x", title, "", free=True), tracks)]
        self.assertEqual(gate("Android Developer"), [MOBILE])
        self.assertEqual(gate("React Native Full Stack Developer"), [MERN, MOBILE])
        self.assertEqual(gate("ML Engineer Intern"), [])      # AI's own exclude wins
        self.assertEqual(gate("Accountant"), [])

    def test_repeated_ids_count_once(self):
        self.assertEqual([t.id for t in scraper.relevant_tracks(
            job("x", "React Developer", "", paid=[MERN, MERN]), contexts())], [MERN])

    def test_missing_or_malformed_provenance_is_refused_never_guessed(self):
        bad = {"no provenance": job("x", "React Developer", "React."),
               "both": job("x", "React Developer", "React.", paid=[MERN], free=True),
               "empty tracks": dict(job("x", "React Developer", "React."),
                                    **{scraper.PAID_TRACKS: []}),
               "tracks as a string": dict(job("x", "React Developer", "React."),
                                          **{scraper.PAID_TRACKS: MERN}),
               "unknown track": job("x", "React Developer", "React.", paid=["ffffffffffffffff"]),
               "free not True": dict(job("x", "React Developer", "React."),
                                     **{scraper.FREE: "yes"})}
        for label, row in bad.items():
            with self.subTest(label):
                with self.assertRaises(ValueError):
                    scraper.relevant_tracks(row, contexts())
                with self.assertRaises(ValueError):                    # the whole pass
                    self.run_multi(ROWS + [row])


# ===========================================================================
class Evaluation(Isolated):

    def test_relevance_eligibility_and_score_are_separate(self):
        out = self.run_multi()
        row, got = self.evals(out, "b-only")
        self.assertEqual(list(got), [MOBILE])     # relevant to MERN, not eligible for it
        self.assertNotIn("a-too-senior", urls(out))        # relevant only to MERN, dropped
        _row, ai = self.evals(out, "ai-only")
        self.assertEqual(list(ai), [AI])                   # MERN would score it; not asked

    def test_every_eligible_track_is_kept_and_winners_are_right(self):
        out = self.run_multi()
        a_row, a = self.evals(out, "a-wins")
        b_row, b = self.evals(out, "b-wins")
        self.assertEqual(set(a), {MERN, MOBILE})
        self.assertEqual(set(b), {MERN, MOBILE})
        self.assertGreater(a[MERN]["s"], a[MOBILE]["s"])
        self.assertEqual(a_row["best_track"], MERN)
        self.assertGreater(b[MOBILE]["s"], b[MERN]["s"])
        self.assertEqual(b_row["best_track"], MOBILE)
        for row, got in ((a_row, a), (b_row, b)):
            best = got[row["best_track"]]
            self.assertEqual((row["score"], row["matched_skills"]), (best["s"], best["m"]))

    def test_scores_are_each_tracks_own_evaluation(self):
        out = self.run_multi()
        by_id = {t.id: t for t in contexts()}
        for name in ("shared", "a-wins", "b-wins", "free-mern-mobile"):
            source = next(r for r in ROWS if r["Job URL"].endswith("/" + name))
            _row, got = self.evals(out, name)
            for tid, e in got.items():
                direct = scraper.evaluate(copy.deepcopy(source), by_id[tid].scoring)
                with self.subTest(name=name, track=tid):
                    self.assertEqual((e["s"], e["m"]), (direct.score, direct.matched_skills))

    def test_job_facts_once_per_copy_across_tracks_and_passes(self):
        rows = copy.deepcopy(ROWS)
        real, calls = scraper.job_facts, []
        with mock.patch.object(scraper, "job_facts", lambda r: calls.append(1) or real(r)):
            first = scraper.finalize_multi(rows, contexts())
            second = scraper.finalize_multi(rows, contexts())
        self.assertEqual(first, second)
        self.assertEqual(len(calls), len(rows))          # 9 copies, 3 tracks, 2 passes

    def test_track_order_and_the_process_engine_do_not_change_evaluations(self):
        with mock.patch.object(skill_concepts, "bind", side_effect=AssertionError("rebound")):
            forward = self.run_multi()
            backward = self.run_multi(order=(AI, MOBILE, MERN))
            with mock.patch.dict(os.environ, {skill_concepts.VERSION_ENV: "v2"}):
                other_engine = self.run_multi()
        norm = lambda out: {r["apply_url"]: json.loads(r["track_evals"]) for r in out}  # noqa
        self.assertEqual(norm(forward), norm(backward))
        self.assertEqual(forward, other_engine)

    def test_nothing_is_written_that_is_one_tracks(self):
        rows = copy.deepcopy(ROWS)
        scraper.finalize_multi(rows, contexts())
        for row in rows:
            for key in ("score", "matched_skills", "is_fullstack"):
                self.assertNotIn(key, row)

    def test_min_score_is_a_per_track_test(self):
        with mock.patch.dict(scraper.SETTINGS, min_score=5):
            out = self.run_multi()
        _row, got = self.evals(out, "a-wins")
        self.assertEqual(list(got), [MERN])                  # Mobile's 2 is under the floor

    def test_guard_verdicts_carry_their_track_and_are_recorded_once(self):
        rows = [job("guard", "React Native Developer",
                    "React Native and React. We require 8+ years of experience.",
                    paid=[MERN, MOBILE])]
        mark = len(experience_guard.DROPPED)
        self.addCleanup(lambda: experience_guard.DROPPED.__delitem__(slice(mark, None)))
        with mock.patch.dict(os.environ, {experience_guard.FLAG: "1"}), \
                mock.patch.dict(scraper.SETTINGS, drop_excluded=False):
            scraper.finalize_multi(rows, contexts())
            scraper.finalize_multi(rows, contexts())
        new = experience_guard.DROPPED[mark:]
        self.assertEqual(sorted(d["track"] for d in new), sorted([MERN, MOBILE]))
        self.assertTrue(all(d["action"] != "none" for d in new))


# ===========================================================================
class SweepFilters(Isolated):

    def test_the_sweep_filters_run_once_per_copy(self):
        extra = [job("stale", "React Developer", "React.", paid=[MERN, AI],
                     **{"Posted Date": "2020-01-02"}),
                 job("low-pay", "React Developer", "React.", paid=[MERN], Salary="INR 3 LPA"),
                 # Remote locked to the US: the one kind of remote row the
                 # India scope still drops (worldwide remote is kept since
                 # 2026-11-20).
                 job("remote", "React Developer", "Fully remote. React.", paid=[MERN],
                     Location="Remote, United States"),
                 job("abroad", "React Developer", "Onsite. React.", paid=[MERN],
                     Location="Berlin, Germany", hires_home="no")]
        out = self.run_multi(ROWS + extra)
        for name in ("stale", "low-pay", "remote", "abroad"):
            self.assertNotIn(name, urls(out))
        self.assertEqual({k: scraper.LAST_STATS[k] for k in
                          ("stale", "low_salary", "wrong_arrangement", "off_geography")},
                         {"stale": 1, "low_salary": 1, "wrong_arrangement": 1,
                          "off_geography": 1})

    def test_remote_reachability(self):
        rows = [job("worldwide", "React Developer", "Fully remote. React.", paid=[MERN],
                    Location="Worldwide, Remote"),
                job("onsite", "React Developer", "Onsite. React.", paid=[MERN])]
        with mock.patch.dict(scraper.SETTINGS, work_scope=None,
                             remote_scopes=["worldwide", "remote"]):
            out = self.run_multi(rows)
        self.assertEqual(urls(out), ["worldwide"])
        self.assertEqual(scraper.LAST_STATS["unreachable"], 1)


# ===========================================================================
class Clusters(Isolated):

    def dup(self, n, description, **over):
        return job(f"dup-{n}", "Frontend Engineer", description, paid=[MERN, MOBILE],
                   req_number="R-77", **over)

    def test_each_track_keeps_its_own_copy_and_the_best_track_represents(self):
        rows = [self.dup(1, "React, Node.js and MongoDB."),
                self.dup(2, "React Native, Kotlin, Swift and TypeScript.")]
        tracks = contexts()
        acquired = copy.deepcopy(rows)
        copies, _stats = scraper.score_and_filter_multi(acquired, tracks)
        [cluster] = scraper.rank_clusters(copies, tracks, acquired)
        self.assertEqual(cluster.chosen[MERN][0], 0)           # MERN prefers copy 1
        self.assertEqual(cluster.chosen[MOBILE][0], 1)         # Mobile prefers copy 2
        out = scraper.finalize_multi(copy.deepcopy(rows), tracks)
        self.assertEqual(len(out), 1)                          # one physical job
        row, got = out[0], json.loads(out[0]["track_evals"])
        best = row["best_track"]
        self.assertEqual(row["apply_url"], rows[cluster.chosen[best][0]]["Job URL"])
        # The losing track keeps its own copy's score, not the representative's.
        for tid, index in ((MERN, 0), (MOBILE, 1)):
            direct = scraper.evaluate(copy.deepcopy(rows[index]),
                                      next(t for t in tracks if t.id == tid).scoring)
            self.assertEqual(got[tid]["s"], direct.score)

    def test_company_and_title_duplicates_tie_to_arrival(self):
        rows = [job("ct-1", "React Developer", "React and Node.js.", free=True,
                    Company="Acme Labs"),
                job("ct-2", "Developer, React", "React and Node.js.", free=True,
                    Company="Acme Labs Pvt Ltd")]
        out = self.run_multi(rows)
        self.assertEqual(urls(out), ["ct-1"])

    def test_a_best_track_tie_goes_to_track_order(self):
        tie = [job("tie", "Software Engineer", "Excel.", paid=[MERN, MOBILE])]
        self.assertEqual(self.run_multi(tie)[0]["best_track"], MERN)
        self.assertEqual(self.run_multi(tie, order=(MOBILE, MERN, AI))[0]["best_track"],
                         MOBILE)

    def test_clusters_rank_by_best_score_then_arrival(self):
        out = self.run_multi()
        scores = [r["score"] for r in out]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(len(out), len(set(r["apply_url"] for r in out)))

    def test_found_by_is_every_acquisition_in_track_order_then_free(self):
        rows = [job("fb-1", "React Developer", "React.", paid=[AI, MERN], req_number="R-9"),
                job("fb-2", "React Developer", "React.", free=True, req_number="R-9")]
        out = self.run_multi(rows)
        self.assertEqual(out[0]["found_by"], f"{MERN};{AI};free")


# ===========================================================================
class AcquisitionProvenance(Isolated):
    """found_by is which searches surfaced a job — every acquired copy of it,
    whatever became of that copy — never which tracks it suits."""

    def same_job(self, name, title, description, **kw):
        return job(name, title, description, req_number="R-500", **kw)

    def test_a_discarded_paid_copy_still_counts_and_stays_out_of_track_evals(self):
        rows = [self.same_job("p-mobile", "Mobile Developer", "React Native, Kotlin and Swift.",
                              paid=[MOBILE]),
                self.same_job("f-android", "Android Developer", "Kotlin.", free=True),
                # MERN's own copy: too senior for MERN, so dropped.
                self.same_job("p-mern", "React Developer",
                              "React. 8+ years of experience required.", paid=[MERN])]
        [row] = self.run_multi(rows)
        self.assertEqual(row["best_track"], MOBILE)
        self.assertEqual(list(json.loads(row["track_evals"])), [MOBILE])
        self.assertEqual(row["found_by"], f"{MERN};{MOBILE};free")   # MERN surfaced it

    def test_a_filtered_free_copy_still_counts(self):
        rows = [self.same_job("f-stale", "React Developer", "React.", free=True,
                              **{"Posted Date": "2020-01-02"}),
                self.same_job("p-mern", "React Developer", "React and Node.js.", paid=[MERN])]
        [row] = self.run_multi(rows)
        self.assertEqual(row["apply_url"], "https://example.test/multi/p-mern")
        self.assertEqual(row["found_by"], f"{MERN};free")

    def test_a_job_whose_every_copy_fails_leaves_no_result(self):
        doomed = [self.same_job("d-1", "React Developer", "React.", paid=[MERN, AI],
                                **{"Posted Date": "2020-01-02"}),
                  self.same_job("d-2", "React Developer",
                                "React. 8+ years of experience required.", paid=[MERN]),
                  job("keyless", "Accountant", "Ledgers.", free=True, Company="",
                      **{"Job URL": ""})]
        out = self.run_multi(ROWS + doomed)
        self.assertEqual(len(out), len(self.run_multi()))              # no ghost rows
        self.assertFalse({"d-1", "d-2", "keyless"} & set(urls(out)))

    def test_order_is_track_order_then_free_whatever_the_arrival(self):
        import itertools
        base = [self.same_job("p-mobile", "Mobile Developer", "React Native and Kotlin.",
                              paid=[MOBILE]),
                self.same_job("f-android", "Android Developer", "Kotlin.", free=True),
                self.same_job("p-ai-mern", "React Developer", "React.", paid=[AI, MERN])]
        seen = {self.run_multi(list(p))[0]["found_by"] for p in itertools.permutations(base)}
        self.assertEqual(seen, {f"{MERN};{MOBILE};{AI};free"})


# ===========================================================================
class FreeTitleGate(Isolated):
    """The free title gate end to end: fetch_free_multi keeps a title ANY
    track's own gate admits, then each track judges only what its own gate
    admits. sources.fetch_free stands in for the adapters, which keep what the
    wrapper's keep_title admits; fetch_free_multi itself runs for real."""

    def acquire(self, rows, order):
        adapters = lambda _boards, _feeds, keep_title, *_a, **_kw: [  # noqa: E731
            copy.deepcopy(r) for r in rows if keep_title(r["Title"])]
        with mock.patch.object(scraper.sources, "fetch_free", adapters):
            return scraper.fetch_free_multi(contexts(order))

    def admitted(self, title, order):
        return [t.id for t in contexts(order)
                if scraper.title_admits(title, t.title_hints, t.title_exclude)]

    def evaluated(self, row, order):
        memo = row.get(scraper.EVALS, {})
        return [t.id for t in contexts(order) if t.scoring.key in memo]

    def judge(self, row, order):
        """(the acquired copy, its result row), through both real stages."""
        [got] = self.acquire([row], order)
        [out] = scraper.finalize_multi([got], contexts(order))
        return got, out

    def test_two_tracks_one_admits_the_job_is_that_tracks_alone(self):
        order = (MERN, MOBILE)
        row = job("android", "Android Developer", "Kotlin and React Native.")
        self.assertEqual(self.admitted(row["Title"], order), [MOBILE])
        got, out = self.judge(row, order)
        self.assertIs(got[scraper.FREE], True)
        self.assertEqual(self.evaluated(got, order), [MOBILE])      # MERN never asked
        self.assertEqual(list(json.loads(out["track_evals"])), [MOBILE])
        self.assertEqual(out["best_track"], MOBILE)

    def test_three_tracks_the_one_whose_gate_refuses_is_absent(self):
        order = (MERN, AI, MOBILE)                    # the refusing track in the middle
        row = job("rn-full-stack", "React Native Full Stack Developer",
                  "React Native, React, Node.js and Kotlin.")
        self.assertEqual(self.admitted(row["Title"], order), [MERN, MOBILE])
        got, out = self.judge(row, order)
        self.assertEqual(self.evaluated(got, order), [MERN, MOBILE])
        self.assertEqual(list(json.loads(out["track_evals"])), [MERN, MOBILE])
        self.assertIn(out["best_track"], (MERN, MOBILE))

    def test_a_title_no_track_admits_is_never_acquired(self):
        order = (MERN, MOBILE, AI)
        self.assertEqual(self.admitted("Accountant", order), [])
        got = self.acquire([job("accountant", "Accountant", "Ledgers and audits."),
                            job("android", "Android Developer", "Kotlin.")], order)
        self.assertEqual([r["Title"] for r in got], ["Android Developer"])

    def test_a_title_every_track_admits_is_judged_by_every_track(self):
        order = (MERN, MOBILE, AI)
        row = job("rn-ai", "React Native AI Engineer",
                  "React Native, React, Node.js, Kotlin, Python, PyTorch and LLM.")
        self.assertEqual(self.admitted(row["Title"], order), list(order))
        got, out = self.judge(row, order)
        self.assertEqual(self.evaluated(got, order), list(order))
        self.assertEqual(list(json.loads(out["track_evals"])), list(order))
        self.assertIn(out["best_track"], order)

    def test_no_track_whose_gate_refuses_a_free_job_is_evaluated_or_best(self):
        order = (MERN, MOBILE, AI)
        rows = [job(n, t, d) for n, t, d in (
            ("android", "Android Developer", "Kotlin and React Native."),
            ("rn-full-stack", "React Native Full Stack Developer", "React Native and Node.js."),
            ("rn-ai", "React Native AI Engineer", "React Native, Python and PyTorch."),
            ("ml-intern", "ML Engineer Intern", "Python."),        # AI's own exclude wins
            ("accountant", "Accountant", "Ledgers."))]
        acquired = self.acquire(rows, order)
        out = scraper.finalize_multi(acquired, contexts(order))
        self.assertTrue(out)
        for got in acquired:
            self.assertLessEqual(set(self.evaluated(got, order)),
                                 set(self.admitted(got["Title"], order)), got["Title"])
        for row in out:
            title = next(r["Title"] for r in rows if r["Job URL"] == row["apply_url"])
            allowed = self.admitted(title, order)
            self.assertLessEqual(set(json.loads(row["track_evals"])), set(allowed), title)
            self.assertIn(row["best_track"], allowed, title)
            self.assertEqual(row["found_by"], "free", title)   # provenance, not suitability

    def test_a_paid_copy_is_judged_by_the_tracks_that_fetched_it_whatever_their_gate(self):
        [mern] = contexts((MERN,))
        self.assertFalse(scraper.title_admits("Mobile Developer", mern.title_hints,
                                              mern.title_exclude))
        _row, got = self.evals(self.run_multi(), "b-wins")      # paid by MERN and MOBILE
        self.assertEqual(set(got), {MERN, MOBILE})


# ===========================================================================
class ResultRows(Isolated):

    def test_columns_values_and_nothing_private(self):
        out = self.run_multi()
        for row in out:
            self.assertEqual(list(row), scraper.MULTI_OUTPUT_COLUMNS)
            got = json.loads(row["track_evals"])
            self.assertIn(row["best_track"], got)
            self.assertTrue(all(set(v) == {"s", "m"} for v in got.values()))
            self.assertTrue(set(row["found_by"].split(";")) <= {MERN, MOBILE, AI, "free"})
        # The exact column list above already keeps every private key out;
        # this keeps the description text out of every value.
        blob = json.dumps(out)
        for text in ("Kotlin and React Native.", "8+ years of experience required"):
            self.assertNotIn(text, blob)

    def test_track_evals_are_deterministic_json(self):
        a, b = self.run_multi(), self.run_multi()
        self.assertEqual([r["track_evals"] for r in a], [r["track_evals"] for r in b])
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=scraper.MULTI_OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(a)
        back = list(csv.DictReader(io.StringIO(buffer.getvalue())))
        self.assertEqual([json.loads(r["track_evals"]) for r in back],
                         [json.loads(r["track_evals"]) for r in a])

    def test_track_stats(self):
        self.run_multi()
        stats = scraper.LAST_TRACK_STATS
        self.assertEqual(stats["copies"], len(ROWS))
        self.assertEqual(stats["eligible_copies"], len(ROWS) - 1)   # a-too-senior
        self.assertEqual(set(stats["eligible_by_track"]), {MERN, MOBILE, AI})
        self.assertEqual(stats["clusters"], scraper.LAST_STATS["kept"])
        self.assertEqual(stats["eligible_by_track"][AI], 2)          # ai-only, shared


# ===========================================================================
PARITY = """
import copy, json, socket, sys
mode, name, repo, rows_path = sys.argv[1:5]
socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network"))
sys.argv = ["scraper.py", "--profile", name]
sys.path[:0] = [".", repo, repo + "/auto-apply"]
import config, scraper
rows = json.load(open(rows_path))
paid = [r for r in rows if r.get("_tracks")]
free = [{k: v for k, v in r.items() if k != "_free"} for r in rows if r.get("_free")]
# The adapters inside sources.fetch_free: each keeps what the wrapper's own
# keep_title admits. fetch_free / fetch_free_multi run for real, so each mode
# acquires through its production gate. keep_location is checked, not applied:
# two free rows exist to reach the arrangement and geography filters.
handed = []
def adapters(_boards, _feeds, keep_title, keep_location, *_a, **_kw):
    handed.append(keep_location is scraper.location_allowed)
    return [copy.deepcopy(r) for r in free if keep_title(r["Title"])]
scraper.sources.fetch_free = adapters
stages = []
collect = lambda s, got: stages.append([s, len(got)])
if mode == "one":
    for r in paid:
        r.pop("_tracks")
    acquired = scraper.fetch_free()
    rows = paid + acquired                    # main(): the paid phase, then free
    scraper.score_and_filter(copy.deepcopy(rows), collect)
    out = scraper.finalize(rows)
    blocked = None
else:
    acquired = scraper.fetch_free_multi(scraper.TRACK_CONTEXTS)
    rows = paid + acquired
    scraper.score_and_filter_multi(copy.deepcopy(rows), scraper.TRACK_CONTEXTS, collect)
    out = scraper.finalize_multi(rows, scraper.TRACK_CONTEXTS)
    import contextlib, io
    printed = io.StringIO()
    try:
        sys.argv = ["scraper.py", "--profile", name, "--dry-run", "--json"]
        with contextlib.redirect_stdout(printed):
            scraper.main()
        blocked = json.loads(printed.getvalue())["plan_version"]
    except SystemExit as exc:
        blocked = str(exc)
print(json.dumps({"acquired": [r["Job URL"] for r in acquired], "location_gate": handed,
                  "out": out, "stats": dict(scraper.LAST_STATS), "stages": stages,
                  "blocked": blocked}))
"""


class OneTrackParity(unittest.TestCase):
    """A schema-2 Sweep of one track decides exactly as the schema-1 profile of
    the same résumé: same acquired free rows, jobs, scores, survivors, order,
    stats and funnel — with the candidate title gate off and on, pinned here
    rather than inherited from the caller's shell."""

    def test_schema_1_and_a_one_track_sweep_agree(self):
        home = tempfile.mkdtemp(prefix="multi-parity-")
        self.addCleanup(shutil.rmtree, home, True)
        os.makedirs(os.path.join(home, "profiles"))
        open(os.path.join(home, "profiles", "__init__.py"), "w").close()
        tid = "d4d4d4d4d4d4d4d4"
        rows = []
        for n, r in enumerate(_load("scoring_rows.json")["rows"]):
            r = {k: v for k, v in r.items() if k != "_case"}
            r.update({scraper.PAID_TRACKS: [tid]} if r["Source"] == "linkedin"
                     else {scraper.FREE: True})
            rows.append(r)
        # A second copy of a paid job, found by the free half too: dedupe across
        # the paid/free line must match schema 1's.
        rows.append(dict(rows[0], **{"Job URL": "https://example.test/jobs/01-free-copy",
                                     "Source": "lever:acmelabs"}))
        rows_path = os.path.join(home, "rows.json")
        with open(rows_path, "w") as fh:
            json.dump(rows, fh)
        n_free = sum(1 for r in rows if r.get(scraper.FREE))
        derived, prefs = derived_for("scoring"), prefs_for("scoring")
        for gate, engine in ((g, e) for g in ("0", "1") for e in ("v1", "v2")):
            # Rendering reads the gate and the engine, and nothing else from
            # the caller's shell: the free title gate is baked in here.
            with mock.patch.dict(os.environ, {title_gate.FLAG: gate,
                                              skill_concepts.VERSION_ENV: engine}, clear=True):
                one = make_profile.render(f"one_{engine}_{gate}", derived, prefs)
                sweep = make_profile.render_sweep(f"sweep_{engine}_{gate}", [
                    {"id": tid, "engine": engine, "derived": derived}], prefs)
            for name, source in ((f"one_{engine}_{gate}", one),
                                 (f"sweep_{engine}_{gate}", sweep)):
                with open(os.path.join(home, "profiles", f"{name}.py"), "w") as fh:
                    fh.write(source)
            got = {}
            for mode, name in (("one", f"one_{engine}_{gate}"),
                               ("multi", f"sweep_{engine}_{gate}")):
                run = subprocess.run([sys.executable, "-c", PARITY, mode, name, REPO, rows_path],
                                     capture_output=True, text=True, cwd=home, env=_env(home),
                                     timeout=120)
                self.assertEqual(run.returncode, 0, run.stderr[-3000:])
                got[mode] = json.loads(run.stdout)
            with self.subTest(engine=engine, title_gate=gate):
                self.assertEqual(got["multi"]["acquired"], got["one"]["acquired"])
                if gate == "1":        # the candidate gate must refuse some free titles here
                    self.assertLess(len(got["one"]["acquired"]), n_free)
                self.assertEqual(got["one"]["location_gate"] + got["multi"]["location_gate"],
                                 [True, True])
                one_out, multi_out = got["one"]["out"], got["multi"]["out"]
                self.assertGreater(len(one_out), 5)
                self.assertEqual([{k: r[k] for k in scraper.OUTPUT_COLUMNS} for r in multi_out],
                                 one_out)
                self.assertEqual(got["multi"]["stats"], got["one"]["stats"])
                self.assertEqual(got["multi"]["stages"], got["one"]["stages"])
                self.assertTrue(all(r["best_track"] == tid for r in multi_out))
                self.assertTrue(all(list(json.loads(r["track_evals"])) == [tid]
                                    for r in multi_out))
                self.assertIn("free", {p for r in multi_out for p in r["found_by"].split(";")})
                # Phase 3 lifted main()'s refusal: the same process now plans
                # the Sweep (test_multi_plan runs it whole).
                self.assertEqual(got["multi"]["blocked"], 2)


# ===========================================================================
# DQ4-2: recommendation metadata, after ranking, from track_evals alone
# ===========================================================================
A, B, C = "da" * 8, "db" * 8, "dc" * 8
ORDERS = [(MERN, MOBILE, AI), (AI, MOBILE, MERN), (MOBILE, AI, MERN)]


def weighted(scores, order=(A, B, C)):
    """Contexts whose score on a "Kafka" job is exactly `scores[id]`."""
    data = make_profile.check_tracks([track(tid, "v1", 2, {"kafka": w}, ["kafka"])
                                      for tid, w in scores.items()])
    by_id = {t["id"]: t for t in data}
    return [scraper.track_context(by_id[tid], SWEEP_SCORING) for tid in order]


def kafka(name="kafka", paid=(A, B, C), **over):
    """One physical job, "Kafka Engineer" at Kafka Co; `name` names the copy."""
    return job(name, "Kafka Engineer", "Kafka streams.", paid=list(paid),
               **dict({"Company": "Kafka Co"}, **over))


class Recommendations(Isolated):

    def final(self, rows, ctx, recommend=True):
        return scraper.finalize_multi(copy.deepcopy(rows), ctx, recommend=recommend)

    def rec(self, row):
        return row["recommended_tracks"], row["recommendation"], row["best_track"]

    def test_the_flag_is_off_unless_said_and_needs_two_tracks(self):
        self.assertEqual(scraper.RECOMMENDATION_FLAG, "SWEEP_TRACK_RECOMMENDATION")
        two = weighted({A: 5, B: 4}, (A, B))
        for value, want in (("1", True), ("true", True), (" YES ", True), ("On", True),
                            ("0", False), ("", False), ("no", False), ("off", False)):
            with mock.patch.dict(os.environ, {scraper.RECOMMENDATION_FLAG: value}):
                self.assertIs(scraper.track_recommendation_enabled(two), want, value)
                self.assertFalse(scraper.track_recommendation_enabled(two[:1]))
                self.assertFalse(scraper.track_recommendation_enabled(()))
        with mock.patch.dict(os.environ):
            os.environ.pop(scraper.RECOMMENDATION_FLAG, None)
            self.assertFalse(scraper.track_recommendation_enabled(two))
        self.assertEqual(scraper.multi_output_columns(), scraper.MULTI_OUTPUT_COLUMNS)
        self.assertEqual(scraper.multi_output_columns(True), scraper.MULTI_OUTPUT_COLUMNS
                         + ["recommended_tracks", "recommendation"])

    def test_off_the_fields_are_absent_and_on_they_are_all_that_is_added(self):
        for order in ORDERS:
            off = self.run_multi(order=order)
            on = scraper.finalize_multi(copy.deepcopy(ROWS), contexts(order), recommend=True)
            self.assertTrue(all(list(r) == scraper.MULTI_OUTPUT_COLUMNS for r in off))
            self.assertEqual([list(r) for r in on],
                             [scraper.multi_output_columns(True)] * len(off))
            self.assertEqual([{k: r[k] for k in scraper.MULTI_OUTPUT_COLUMNS} for r in on], off)
            for row in on:
                got = row["recommended_tracks"].split(";")
                self.assertEqual(got[0], row["best_track"])
                self.assertLessEqual(set(got), set(json.loads(row["track_evals"])))
                self.assertIn(row["recommendation"], ("clear", "close", "tied"))

    def test_an_exact_tie_follows_track_order_in_best_track_and_the_listing_only(self):
        for order, best, listed in (((A, B, C), A, f"{A};{B}"), ((B, A, C), B, f"{B};{A}")):
            row, = self.final([kafka()], weighted({A: 25, B: 25, C: 20}, order))
            self.assertEqual(self.rec(row), (listed, "tied", best))
            self.assertEqual(json.loads(row["track_evals"]),
                             {t: {"s": {A: 25, B: 25, C: 20}[t], "m": "kafka"} for t in order})

    def test_tied_names_the_top_not_every_member(self):
        """A and B share the top; C is a close follower, recommended too."""
        row, = self.final([kafka()], weighted({A: 25, B: 25, C: 24}, (B, A, C)))
        self.assertEqual(self.rec(row), (f"{B};{A};{C}", "tied", B))

    def test_close_and_clear(self):
        row, = self.final([kafka()], weighted({A: 25, B: 24, C: 20}))
        self.assertEqual(self.rec(row), (f"{A};{B}", "close", A))
        row, = self.final([kafka()], weighted({A: 25, B: 23, C: 20}))
        self.assertEqual(self.rec(row), (A, "clear", A))

    def test_a_track_that_did_not_ask_is_never_recommended(self):
        row, = self.final([kafka(paid=(B, C))], weighted({A: 30, B: 25, C: 24}))
        self.assertEqual(list(json.loads(row["track_evals"])), [B, C])
        self.assertEqual(self.rec(row), (f"{B};{C}", "close", B))

    def test_an_ineligible_track_is_never_recommended(self):
        ctx = [scraper.track_context(t, SWEEP_SCORING) for t in make_profile.check_tracks([
            track(A, "v1", 0, {"kafka": 30}, ["kafka"]),         # at most 3 years
            track(B, "v1", 6, {"kafka": 25}, ["kafka"]),
            track(C, "v1", 6, {"kafka": 24}, ["kafka"])])]
        row, = self.final([kafka(Description="Kafka streams. 6+ years of experience required.")], ctx)
        self.assertEqual(list(json.loads(row["track_evals"])), [B, C])
        self.assertEqual(self.rec(row), (f"{B};{C}", "close", B))

    def test_a_track_under_min_score_is_never_recommended(self):
        with mock.patch.dict(scraper.SETTINGS, min_score=25):
            row, = self.final([kafka()], weighted({A: 25, B: 24, C: 20}))
        self.assertEqual(list(json.loads(row["track_evals"])), [A])
        self.assertEqual(self.rec(row), (A, "clear", A))

    def test_one_evaluated_track_is_clear(self):
        row, = self.final([kafka(paid=(B,))], weighted({A: 25, B: 3, C: 20}))
        self.assertEqual(self.rec(row), (B, "clear", B))

    def test_found_by_is_not_a_recommendation(self):
        """C fetched a copy the Sweep's filters then dropped: provenance, not fit."""
        rows = [kafka("fresh", paid=(A,)),
                kafka("stale", paid=(C,), **{"Posted Date": "2020-01-01"})]
        row, = self.final(rows, weighted({A: 20, B: 5, C: 30}))
        self.assertEqual(row["found_by"], f"{A};{C}")
        self.assertEqual(list(json.loads(row["track_evals"])), [A])
        self.assertEqual(self.rec(row), (A, "clear", A))

    def test_the_representative_copy_is_best_tracks_whatever_the_flag(self):
        """The DQ4 audit's two-copy tie: each tied track chose its own copy."""
        rows = [kafka("copy-x", paid=(A,), Source="linkedin", Salary="INR 30,00,000"),
                kafka("copy-y", paid=(B,), Source="indeed", Salary="INR 40,00,000")]
        for order, url in (((A, B, C), "copy-x"), ((B, A, C), "copy-y")):
            ctx = weighted({A: 25, B: 25, C: 20}, order)
            off, = self.final(rows, ctx, recommend=False)
            on, = self.final(rows, ctx)
            self.assertEqual(off["apply_url"].rsplit("/", 1)[1], url)
            self.assertEqual({k: on[k] for k in off}, off)
            self.assertEqual(on["recommended_tracks"].split(";")[0], off["best_track"])

    def test_an_impossible_state_fails_closed(self):
        ctx = weighted({A: 25, B: 24, C: 20})
        ev = scraper.Evaluation(True, None, 25, "kafka", False)
        low = scraper.Evaluation(True, None, 24, "kafka", False)
        with self.assertRaises(RuntimeError):          # the leader is not best_track
            scraper.recommendation(scraper.Cluster(B, {A: (0, {}, ev), B: (1, {}, low)}, []), ctx)
        with self.assertRaises(ValueError):            # nothing evaluated
            scraper.recommendation(scraper.Cluster(None, {}, []), ctx)
        with self.assertRaises(ValueError):            # a track this Sweep does not have
            scraper.recommendation(scraper.Cluster("ee" * 8, {"ee" * 8: (0, {}, ev)}, []), ctx)
        with self.assertRaises(ValueError):            # one track has nothing to choose
            scraper.finalize_multi([kafka(paid=(A,))], ctx[:1], recommend=True)

    def test_written_and_read_back(self):
        out_dir = tempfile.mkdtemp(prefix="multi-recommend-")
        self.addCleanup(shutil.rmtree, out_dir, True)
        rows = self.final(ROWS, contexts())
        path, jpath = os.path.join(out_dir, "jobs.csv"), os.path.join(out_dir, "jobs.json")
        with mock.patch.dict(scraper.SETTINGS, output_dir=out_dir):
            scraper.write_outputs(rows, path, jpath, scraper.multi_output_columns(True))
        with open(path, newline="", encoding="utf-8-sig") as fh:
            header = next(csv.reader(fh))
            fh.seek(0)
            back = list(csv.DictReader(fh))
        self.assertEqual(header, scraper.multi_output_columns(True))
        self.assertEqual(back, [{k: "" if v is None else str(v) for k, v in r.items()}
                                for r in rows])
        with open(jpath, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), rows)


# ===========================================================================
# DQ6-F1-C1: a DIRECT, evidenced alternative, from each track's own copy
# ===========================================================================
def positioned(tid, skills, concepts, qualifiers, titles=None, years=3):
    """A v2 track with POSITIONING, and ALIGNMENT when `titles` is given."""
    t = track(tid, "v2", years, skills, ["kafka", "react", "frontend", "backend"])
    t["POSITIONING"] = {"concepts": list(concepts), "role_qualifiers": list(qualifiers)}
    if titles is not None:
        t["ALIGNMENT"] = {"role_titles": list(titles)}
    return t


def aligned_contexts(alignment=True, order=(A, B, C), years=(3, 3, 3)):
    """A: the broad fit leader; B and C: two frontend résumés, C weaker."""
    specs = ((A, {"kafka": 30, "react": 2}, ["kafka"], ["backend"], ["backend engineer"]),
             (B, {"react": 12, "redux": 6}, ["react"], ["frontend"], ["frontend engineer"]),
             (C, {"react": 3, "redux": 2}, ["react"], ["frontend"], ["frontend engineer"]))
    data = make_profile.check_tracks([
        positioned(tid, skills, cs, qs, titles if alignment else None, years=y)
        for (tid, skills, cs, qs, titles), y in zip(specs, years)])
    by_id = {t["id"]: t for t in data}
    return [scraper.track_context(by_id[tid], SWEEP_SCORING) for tid in order]


def frontend_job(name="fe", title="Frontend Engineer", description="Kafka and React.",
                 paid=(A, B, C), **over):
    return job(name, title, description, paid=list(paid), **dict({"Company": "Front Co"}, **over))


class AlignedRecommendations(Isolated):

    def final(self, rows, ctx, recommend=True):
        return scraper.finalize_multi(copy.deepcopy(rows), ctx, recommend=recommend)

    def rec(self, row):
        return row["recommended_tracks"], row["recommendation"], row["best_track"]

    def test_a_direct_evidenced_track_joins_from_outside_the_margin(self):
        for order in itertools.permutations((A, B, C)):
            on, = self.final([frontend_job()], aligned_contexts(order=order))
            off, = self.final([frontend_job()], aligned_contexts(False, order=order))
            self.assertEqual(json.loads(on["track_evals"]),
                             {A: {"s": 33, "m": "kafka, React"}, B: {"s": 16, "m": "React"},
                              C: {"s": 7, "m": "React"}}, order)
            self.assertEqual(self.rec(on), (f"{A};{B}", "split", A), order)   # C: dominated by B
            self.assertEqual(self.rec(off), (A, "clear", A), order)
            self.assertEqual({k: on[k] for k in scraper.MULTI_OUTPUT_COLUMNS},
                             {k: off[k] for k in scraper.MULTI_OUTPUT_COLUMNS})

    def test_direct_without_positioned_evidence_is_not_added(self):
        """B's title names the job and it matches Redux, which it weighs but
        does not position: the P3a concept subtotal is 0, so B stays out."""
        rows = [frontend_job(description="Kafka and Redux.")]
        row, = self.final(rows, aligned_contexts())
        ctx = aligned_contexts()
        facts = scraper.job_facts(rows[0])
        self.assertTrue(track_recommendation.direct(ctx[1].role_titles, rows[0]["Title"]))
        self.assertEqual(scraper.positioning_points(ctx[1].scoring, facts.text, facts.title), (0, 3))
        self.assertEqual(json.loads(row["track_evals"])[B], {"s": 9, "m": "Redux"})
        self.assertEqual(self.rec(row), (A, "clear", A))

    def test_the_evidence_is_the_p3a_concept_subtotal(self):
        """direct_evidenced's evidence is exactly positioning_points()[0] > 0,
        the subtotal evaluate() adds before the title bonus."""
        ctx, plain = aligned_contexts(), aligned_contexts(False)
        for title, text in (("Frontend Engineer", "Kafka and React."),
                            ("Frontend Engineer", "Kafka and Redux."),
                            ("Frontend Developer", "React, Redux and Kafka."),
                            ("Frontend Recruiter", "React."), ("Backend Engineer", "Kafka.")):
            row = frontend_job(title=title, description=text)
            facts = scraper.job_facts(row)
            for track_, same in zip(ctx, plain):
                concepts, bonus = scraper.positioning_points(track_.scoring, facts.text, facts.title)
                bare = dataclasses.replace(track_.scoring, positioned=(), role_qualifiers=())
                self.assertEqual(scraper.evaluate(row, track_.scoring).score
                                 - scraper.evaluate(row, bare).score, concepts + bonus)
                self.assertIs(scraper.direct_evidenced(track_, row),
                              track_recommendation.direct(track_.role_titles, title) and concepts > 0)
                self.assertFalse(scraper.direct_evidenced(same, row))       # no ALIGNMENT

    def test_the_tracks_own_chosen_copy_decides(self):
        """One requisition, two copies with different titles. B is aligned by
        ITS copy only: never by the representative's, never by a sibling's.
        (A's own copy names no role of A's, so A is not an aligned rival.)"""
        own = [frontend_job("x", title="Kafka Engineer", paid=(A,), req_number="R-1"),
               frontend_job("y", title="Frontend Engineer", paid=(B,), req_number="R-1")]
        row, = self.final(own, aligned_contexts())
        self.assertEqual(row["apply_url"].rsplit("/", 1)[1], "x")         # A's copy represents
        self.assertEqual(self.rec(row), (f"{A};{B}", "split", A))
        borrowed = [frontend_job("x", title="Frontend Engineer", paid=(A,), req_number="R-1"),
                    frontend_job("y", title="Kafka Engineer", paid=(B,), req_number="R-1")]
        row, = self.final(borrowed, aligned_contexts())
        self.assertEqual(row["apply_url"].rsplit("/", 1)[1], "x")
        self.assertEqual(json.loads(row["track_evals"])[B]["s"], 13)
        self.assertEqual(self.rec(row), (A, "clear", A))

    def test_best_track_and_the_representative_never_follow_alignment(self):
        rows = [frontend_job("x", title="Kafka Engineer", paid=(A,), req_number="R-2"),
                frontend_job("y", title="Frontend Engineer", paid=(B, C), req_number="R-2")]
        for order in itertools.permutations((A, B, C)):
            on, = self.final(rows, aligned_contexts(order=order))
            off, = self.final(rows, aligned_contexts(order=order), recommend=False)
            self.assertEqual({k: on[k] for k in off}, off, order)
            self.assertEqual((on["best_track"], on["apply_url"].rsplit("/", 1)[1]), (A, "x"))
            self.assertEqual(self.rec(on), (f"{A};{B}", "split", A), order)

    def test_without_a_recommendation_the_carrier_is_inert(self):
        rows = [frontend_job(), frontend_job("be", title="Backend Engineer", Company="Back Co")]
        on = self.final(rows, aligned_contexts(), recommend=False)
        self.assertEqual(on, self.final(rows, aligned_contexts(False), recommend=False))
        self.assertTrue(all(list(r) == scraper.MULTI_OUTPUT_COLUMNS for r in on))

    def test_only_an_evaluated_track_can_be_recommended(self):
        row, = self.final([frontend_job(paid=(A, C))], aligned_contexts())   # B did not ask
        self.assertEqual(list(json.loads(row["track_evals"])), [A, C])
        self.assertEqual(self.rec(row), (f"{A};{C}", "split", A))
        row, = self.final([frontend_job(description="Kafka and React. 6+ years of experience "
                                                     "required.")],
                          aligned_contexts(years=(6, 1, 1)))                  # B and C too junior
        self.assertEqual(list(json.loads(row["track_evals"])), [A])
        self.assertEqual(self.rec(row), (A, "clear", A))
        with mock.patch.dict(scraper.SETTINGS, min_score=20):
            row, = self.final([frontend_job()], aligned_contexts())
        self.assertEqual(self.rec(row), (A, "clear", A))

    def test_alignment_never_reaches_scoring(self):
        on, off = aligned_contexts(), aligned_contexts(False)
        for a, b in zip(on, off):
            self.assertEqual(a.scoring.key, b.scoring.key)
            self.assertEqual((a.scoring.positioned, a.scoring.role_qualifiers),
                             (b.scoring.positioned, b.scoring.role_qualifiers))
            self.assertEqual(b.role_titles, ())
        self.assertEqual([t.role_titles for t in on],
                         [("backend engineer",), ("frontend engineer",), ("frontend engineer",)])
        self.assertNotIn("role_titles", {f.name for f in dataclasses.fields(scraper.ScoringContext)})


# ===========================================================================
# AS-2: one factual caution, from each recommended track's own chosen copy
# ===========================================================================
def focus_contexts(order=(A, B, C), c_kafka=26):
    """A: the broad fit leader, positioned on GraphQL; B: frontend, on React;
    C: mobile, on Redux. Every track can show focus (v2, with POSITIONING)."""
    specs = ((A, {"kafka": 30, "react": 2, "graphql": 1}, ["graphql"], ["backend", "full stack"],
              ["backend engineer"]),
             (B, {"react": 12, "redux": 6}, ["react"], ["frontend"], ["frontend engineer"]),
             (C, {"kafka": c_kafka, "redux": 2}, ["redux"], ["mobile"], ["mobile engineer"]))
    data = make_profile.check_tracks([positioned(*spec) for spec in specs])
    by_id = {t["id"]: t for t in data}
    return [scraper.track_context(by_id[tid], SWEEP_SCORING) for tid in order]


# (title, description, recommended, kind, caution) with focus_contexts().
FOCUS_CASES = (
    ("Frontend Engineer", "Kafka and React.", {A, B}, "split", ""),         # best none, B aligned
    ("Kafka Engineer", "Kafka.", {A}, "clear", scraper.NO_FOCUS_EVIDENCE),   # 30 points, no focus
    ("Mobile Engineer", "Kafka.", {A, C}, "close", ""),                     # C: title bonus only
    ("Kafka Engineer", "Kafka and Redux.", {A, C}, "close", ""),            # C: a concept only
    ("Senior Full-Stack Developer - Marketplace Web & Mobile", "Kafka.", {A}, "clear", ""),
    ("Kafka Engineer", "Kafka and GraphQL.", {A}, "clear", ""),
    ("Mobile Engineer", "Kafka, React and Redux.", {A, C}, "tied", ""),
    ("Accountant", "Ledgers and audits.", {A, B, C}, "tied", scraper.NO_FOCUS_EVIDENCE),
    ("Kafka Engineer", "React.", {A}, "clear", scraper.NO_FOCUS_EVIDENCE),   # B's focus: not listed
    ("Platform Engineer", "Kafka and GraphQL.", {A}, "clear", ""),          # no DIRECT, still focus
)


def focus_jobs():
    return [frontend_job(f"f{n}", title=title, description=text, Company=f"F{n} Co")
            for n, (title, text, *_rest) in enumerate(FOCUS_CASES)]


class RecommendationCautions(Isolated):

    def final(self, rows, ctx, recommend=True, caution=True):
        return scraper.finalize_multi(copy.deepcopy(rows), ctx, recommend=recommend,
                                      caution=caution)

    def test_the_flag_is_off_unless_said_and_needs_two_tracks(self):
        self.assertEqual(scraper.CAUTION_FLAG, "SWEEP_TRACK_RECOMMENDATION_CAUTION")
        self.assertEqual((scraper.NO_FOCUS_EVIDENCE, scraper.CAUTIONS, scraper.CAUTION_COLUMNS),
                         ("no_focus_evidence", ("", "no_focus_evidence"),
                          ["recommendation_caution"]))
        ctx = focus_contexts()
        for value, want in (("1", True), ("true", True), (" YES ", True), ("On", True),
                            ("0", False), ("", False), ("no", False), ("off", False)):
            with mock.patch.dict(os.environ, {scraper.CAUTION_FLAG: value}):
                self.assertIs(scraper.track_caution_enabled(ctx), want, value)
                self.assertFalse(scraper.track_caution_enabled(ctx[:1]))
                self.assertFalse(scraper.track_caution_enabled(()))
        with mock.patch.dict(os.environ):
            os.environ.pop(scraper.CAUTION_FLAG, None)
            self.assertFalse(scraper.track_caution_enabled(ctx))
            self.assertFalse(scraper.track_caution_enabled(weighted({A: 5, B: 4}, (A, B))))
        self.assertEqual(scraper.multi_output_columns(True, True), scraper.MULTI_OUTPUT_COLUMNS
                         + ["recommended_tracks", "recommendation", "recommendation_caution"])
        self.assertEqual(scraper.multi_output_columns(True, False), scraper.multi_output_columns(True))
        with self.assertRaises(ValueError):
            scraper.multi_output_columns(False, True)

    def test_a_track_that_cannot_show_focus_fails_closed(self):
        """No POSITIONING, an empty one, a v1 engine, or one such track among
        positioned ones: refused, on the flag and in finalize_multi, and never
        read as having no focus. Without the caution the same Sweep runs."""
        v1 = track(B, "v1", 3, {"kafka": 4}, ["kafka"])
        v1["POSITIONING"] = {"concepts": ["kafka"], "role_qualifiers": ["kafka"]}
        mixed = focus_contexts()
        mixed[1] = dataclasses.replace(mixed[1], scoring=dataclasses.replace(
            mixed[1].scoring, positioned=(), role_qualifiers=()))
        blind = {
            "none": (weighted({A: 5, B: 4}, (A, B)), [A, B]),
            "empty": ([scraper.track_context(t, SWEEP_SCORING) for t in make_profile.check_tracks(
                [positioned(A, {"kafka": 5}, [], []), positioned(B, {"kafka": 4}, [], [])])], [A, B]),
            "v1": ([scraper.track_context(t, SWEEP_SCORING) for t in make_profile.check_tracks(
                [positioned(A, {"kafka": 5}, ["kafka"], ["kafka"]), v1])], [B]),
            "mixed": (mixed, [B]),
        }
        for how, (ctx, refused) in blind.items():
            with mock.patch.dict(os.environ, {scraper.CAUTION_FLAG: "1"}):
                with self.assertRaises(ValueError) as err:
                    scraper.track_caution_enabled(ctx)
            self.assertIn(scraper.CAUTION_FLAG, str(err.exception), how)
            self.assertEqual([t.id for t in ctx if t.id in str(err.exception)], refused, how)
            rows = [kafka(paid=[t.id for t in ctx])]
            with self.assertRaises(ValueError):
                self.final(rows, ctx)
            row, = self.final(rows, ctx, caution=False)
            self.assertEqual(list(row), scraper.multi_output_columns(True), how)
        with self.assertRaises(ValueError):                  # never without a recommendation
            self.final([kafka()], focus_contexts(), recommend=False)

    def test_the_named_cases_in_every_order(self):
        for order in itertools.permutations((A, B, C)):
            out = self.final(focus_jobs(), focus_contexts(order))
            got = {r["apply_url"].rsplit("/", 1)[1]: r for r in out}
            for n, (title, _text, listed, kind, caution) in enumerate(FOCUS_CASES):
                row = got[f"f{n}"]
                where = (order, title)
                self.assertEqual(set(row["recommended_tracks"].split(";")), listed, where)
                self.assertEqual(row["recommendation"], kind, where)
                self.assertEqual(row["recommendation_caution"], caution, where)

    def test_it_is_one_field_after_the_recommendation_and_nothing_else_moves(self):
        for order in itertools.permutations((A, B, C)):
            ctx = focus_contexts(order)
            on = self.final(focus_jobs(), ctx)
            off = self.final(focus_jobs(), ctx, caution=False)
            bare = self.final(focus_jobs(), ctx, recommend=False, caution=False)
            self.assertEqual([list(r) for r in on],
                             [scraper.multi_output_columns(True, True)] * len(off))
            self.assertEqual([{k: r[k] for k in scraper.multi_output_columns(True)} for r in on],
                             off)
            self.assertEqual([{k: r[k] for k in scraper.MULTI_OUTPUT_COLUMNS} for r in on], bare)
            for row in on:
                self.assertIs(type(row["recommendation_caution"]), str)
                self.assertIn(row["recommendation_caution"], scraper.CAUTIONS)

    def test_focus_evidence_is_the_p3a_total_on_the_copy(self):
        """positioning_points(...) != (0, 0): exactly what P3a adds to the
        evaluation, concepts and title bonus alike — never concepts alone."""
        for title, text, *_rest in FOCUS_CASES:
            row = frontend_job(title=title, description=text)
            facts = scraper.job_facts(row)
            for t in focus_contexts():
                points = scraper.positioning_points(t.scoring, facts.text, facts.title)
                bare = dataclasses.replace(t.scoring, positioned=(), role_qualifiers=())
                added = scraper.evaluate(row, t.scoring).score - scraper.evaluate(row, bare).score
                self.assertIs(scraper.focus_evidence(t, row), points != (0, 0), (title, t.id))
                self.assertIs(scraper.focus_evidence(t, row), added > 0, (title, t.id))
        facts = scraper.job_facts(frontend_job(title=FOCUS_CASES[4][0], description="Kafka."))
        self.assertEqual(scraper.positioning_points(focus_contexts()[0].scoring, facts.text,
                                                    facts.title), (0, 3))     # a title, no concept

    def test_the_pure_rule(self):
        no = scraper.NO_FOCUS_EVIDENCE
        self.assertEqual(scraper.recommendation_caution([A], {A: False}), no)
        self.assertEqual(scraper.recommendation_caution([A, B], {A: False, B: False, C: True}), no)
        self.assertEqual(scraper.recommendation_caution([A, B], {A: False, B: True}), "")
        self.assertEqual(scraper.recommendation_caution([A, B], {A: True, B: False}), "")
        with self.assertRaises(ValueError):
            scraper.recommendation_caution([], {})
        with self.assertRaises(KeyError):                    # every listed track is judged
            scraper.recommendation_caution([A, B], {A: False})

    def test_each_recommended_tracks_own_chosen_copy_decides(self):
        """One requisition, one copy per track. B's focus is on ITS copy only,
        and lifts the caution; the representative's title would give C focus,
        but C's own copy has none, so the caution stands."""
        own = [frontend_job("x", title="Kafka Engineer", description="Kafka.", paid=(A,),
                            req_number="R-1"),
               frontend_job("y", title="Frontend Engineer", description="Kafka and React.",
                            paid=(B,), req_number="R-1")]
        row, = self.final(own, focus_contexts())
        self.assertEqual(row["apply_url"].rsplit("/", 1)[1], "x")
        self.assertEqual((row["recommended_tracks"], row["recommendation"],
                          row["recommendation_caution"]), (f"{A};{B}", "split", ""))
        borrowed = [frontend_job("x", title="Mobile Engineer", description="Kafka.", paid=(A,),
                                 req_number="R-2"),
                    frontend_job("y", title="Kafka Engineer", description="Kafka.", paid=(C,),
                                 req_number="R-2")]
        row, = self.final(borrowed, focus_contexts(c_kafka=29))
        self.assertEqual(row["apply_url"].rsplit("/", 1)[1], "x")
        self.assertEqual(json.loads(row["track_evals"]), {A: {"s": 30, "m": "kafka"},
                                                          C: {"s": 29, "m": "kafka"}})
        self.assertEqual((row["recommended_tracks"], row["recommendation"],
                          row["recommendation_caution"]),
                         (f"{A};{C}", "close", scraper.NO_FOCUS_EVIDENCE))

    def test_neither_score_min_score_nor_direct_is_an_input(self):
        """A 30-point fit with no focus is cautioned; a −34 one with focus is
        not, whatever min_score; focus without DIRECT counts."""
        penalised = track(A, "v2", 3, {"graphql": 2}, ["graphql"], penalties={"php": -40})
        penalised["POSITIONING"] = {"concepts": ["graphql"], "role_qualifiers": ["backend"]}
        ctx = [scraper.track_context(t, SWEEP_SCORING) for t in make_profile.check_tracks(
            [penalised, positioned(B, {"kafka": 2}, ["kafka"], ["data"])])]
        for floor in (None, -40):
            with mock.patch.dict(scraper.SETTINGS, min_score=floor):
                row, = self.final([frontend_job(title="Backend Engineer",
                                                description="GraphQL and PHP.", paid=(A,))], ctx)
            self.assertEqual(json.loads(row["track_evals"]), {A: {"s": -34, "m": "GraphQL"}})
            self.assertEqual((row["recommendation"], row["recommendation_caution"]), ("clear", ""))
        out = {r["apply_url"].rsplit("/", 1)[1]: r for r in self.final(focus_jobs(), focus_contexts())}
        self.assertEqual((json.loads(out["f1"]["track_evals"])[A]["s"],
                          out["f1"]["recommendation_caution"]), (30, scraper.NO_FOCUS_EVIDENCE))
        self.assertFalse(track_recommendation.direct(focus_contexts()[0].role_titles,
                                                     "Platform Engineer"))
        self.assertEqual(out["f9"]["recommendation_caution"], "")

    def test_written_and_read_back(self):
        out_dir = tempfile.mkdtemp(prefix="multi-caution-")
        self.addCleanup(shutil.rmtree, out_dir, True)
        rows = self.final(focus_jobs(), focus_contexts())
        path, jpath = os.path.join(out_dir, "jobs.csv"), os.path.join(out_dir, "jobs.json")
        with mock.patch.dict(scraper.SETTINGS, output_dir=out_dir):
            scraper.write_outputs(rows, path, jpath, scraper.multi_output_columns(True, True))
        with open(path, newline="", encoding="utf-8-sig") as fh:
            header = next(csv.reader(fh))
            fh.seek(0)
            back = list(csv.DictReader(fh))
        self.assertEqual(header, scraper.multi_output_columns(True, True))
        self.assertEqual(back, [{k: "" if v is None else str(v) for k, v in r.items()}
                                for r in rows])
        with open(jpath, encoding="utf-8") as fh:
            got = json.load(fh)
        self.assertEqual(got, rows)
        self.assertTrue(all(list(r)[-3:] == ["recommended_tracks", "recommendation",
                                             "recommendation_caution"] for r in got))


class SchemaOneUntouched(unittest.TestCase):

    def test_finalize_is_the_one_profile_path(self):
        self.assertEqual(scraper.TRACK_CONTEXTS, ())
        out = scraper.finalize([dict(job("plain", "React Developer", "React."),
                                     **{"Posted Date": scraper.datetime.now().strftime("%Y-%m-%d")})])
        for row in out:
            self.assertEqual(list(row), scraper.OUTPUT_COLUMNS)


if __name__ == "__main__":
    unittest.main()
