"""Multi-Track Phase 4 (P4-E1): a Multi-Track run's exports, and unique labels.

A Multi-Track export is the run's All Jobs, whichever résumé's view is open:
every row the strict reader passed, once, in the page's order, with no floor
unless one was asked for — so "Export All Jobs: N" is the file's N. Today's
columns come first, exactly; then one fixed set of machine fields — the
engine's own values (best_track, track_evals, found_by, recommended_tracks,
recommendation, recommendation_caution), never recomputed — beside the run's
labels (best_track_label, track_labels, recommended_track_labels) and
recommendation_caution_computed, which keeps "not computed" and "computed,
none" apart even in a CSV cell. A one-track run's exports are today's, byte
for byte. Labels are unique in a setup, compared casefolded.

Same stack as P4-R2's tests: the real Render app and worker on loopback, the
P4-U1 setup, synthetic engine-shaped rows. No model, provider or network.
"""
import copy
import csv
import io
import json
import os
import re
import unittest
from unittest import mock

import scraper
from sweep import app as app_module
from sweep import exports, worker_link
from sweep.tests import test_multi_render as r1
from sweep.tests import test_multi_results_view as r2
from sweep.tests import test_multi_setup as u1

setUpModule, tearDownModule = r1.setUpModule, r1.tearDownModule

A, B, C = r2.A, r2.B, r2.C
LA, LB, LC = r2.FA, r2.FB, r2.FC                  # what an EXPORT calls them: their files (the screen calls them by name, D6)
SA, SB = u1.LABEL["ada"], u1.LABEL["bhaskar"]     # the setup's own labels
ROWS, job = r2.ROWS, r2.job
FORMATS = ("csv", "json", "xlsx", "html")
PAGE_ORDER = [1, 2, 3, 5, 4, 6]            # All Jobs, one section: the engine's order


class Exports(r2.Results):

    def export(self, fmt="csv", **args):
        answer = self.client.get(f"/export.{fmt}", query_string=args)
        self.assertEqual(answer.status_code, 200, answer.get_data()[-400:])
        return answer

    def table(self, **args):
        """The CSV export as (header, [row dicts])."""
        body = self.export("csv", **args).get_data().decode("utf-8-sig")
        reader = csv.reader(io.StringIO(body))
        header = next(reader)
        return header, [dict(zip(header, r)) for r in reader]

    def listed(self, **args):
        return [int(r["Role"].split()[1]) for r in self.table(**args)[1]]

    def label_count(self, **args):
        page = self.page(**args)
        return int(re.search(r"Export All Jobs: (\d+) listing", page).group(1))


class Legacy(Exports):
    """Items 2, 6, 43: a one-track run's exports are today's."""

    def one_track_exports(self):
        # The one-résumé gestures, which mean the same with the setup on or off.
        self.upload("ada")
        self.client.post("/derive")
        self.client.post("/review", data={})
        self.client.post("/key/free")
        self.client.post("/configure", data=r1.FORMS["india"])
        self.client.post("/run")
        self.run_id = self.cookie()["run_id"]
        self.settled(self.run_id)
        out = self.worker.store.output_dir(self.run_id)
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "jobs_2026-09-28_1200.csv"), "w", newline="",
                  encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=scraper.OUTPUT_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(ROWS)
        with mock.patch.object(app_module, "datetime") as clock:
            clock.now.return_value = __import__("datetime").datetime(2026, 9, 28, 12, 0)
            got = {fmt: self.export(fmt) for fmt in ("csv", "json", "html")}
            got["csv_min"] = self.export("csv", min=-10)
        return got

    def test_the_setup_on_changes_no_one_track_export(self):
        on = self.one_track_exports()
        os.environ.pop(worker_link.MULTI_FLAG)
        self.app = self.render()
        self.client = self.app.test_client()
        self.client.post("/beta", data={"code": r1.CODE})
        off = self.one_track_exports()
        for fmt in on:
            self.assertEqual(on[fmt].get_data(), off[fmt].get_data(), fmt)
            self.assertEqual((on[fmt].mimetype, on[fmt].headers["Content-Disposition"]),
                             (off[fmt].mimetype, off[fmt].headers["Content-Disposition"]))
        header = on["csv"].get_data().decode("utf-8-sig").splitlines()[0]
        self.assertEqual(header.split(","), exports.HEADERS)          # no multi column
        self.assertEqual(len(on["csv"].get_data().decode("utf-8-sig").splitlines()), 1 + 5)
        self.assertEqual(len(on["csv_min"].get_data().decode("utf-8-sig").splitlines()), 1 + 6)
        self.assertNotIn(b"best_track", on["json"].get_data())


class AllJobs(Exports):
    """Items 5, 7-10, 29, 31-32, 35: every row, the page's order and count."""

    def test_every_row_once_in_the_pages_order_under_the_pages_count(self):
        self.run_multi("ada", "bhaskar", "chen")
        self.serve()
        header, rows = self.table()
        self.assertEqual(header, exports.HEADERS + exports.MULTI_KEYS)
        self.assertEqual(self.listed(), PAGE_ORDER)                   # J6 at -3 included
        self.assertEqual((len(rows), self.label_count()), (6, 6))
        self.assertEqual([r["Score"] for r in rows], ["30", "25", "20", "18", "10", "-3"])
        for args, want in (({"min": 12}, [1, 2, 3, 5]), ({"min": 0}, [1, 2, 3, 5, 4]),
                           ({"q": "job 5"}, [5]), ({"sort": "recent"}, None)):
            with self.subTest(args):
                got = self.listed(**args)
                if want is not None:
                    self.assertEqual(got, want)
                self.assertEqual(self.label_count(**args), len(got))
                self.assertEqual(self.seen(self.page(**args)), got)   # the page's own list

    def test_the_view_open_changes_nothing_exported(self):
        self.run_multi("ada", "bhaskar", "chen")
        self.serve()
        body = {fmt: self.export(fmt).get_data() for fmt in ("csv", "json")}
        for tid in (A, B, C):
            for fmt in ("csv", "json"):
                self.assertEqual(self.export(fmt, track=tid).get_data(), body[fmt])
            page = self.page(track=tid)
            self.assertIn("Export All Jobs: 6 listings", page)          # not the view's count
            self.assertEqual(re.findall(r'href="(/export\.[^"]+)"', page),
                             re.findall(r'href="(/export\.[^"]+)"', self.page()))
        view_b = self.page(track=B, min=12)
        self.assertIn("Export All Jobs: 4 listings", view_b)           # All Jobs, min 12
        self.assertEqual(self.seen(view_b), [2, 5, 1])                   # B's own list
        self.assertIn('href="/export.csv?min=12"', view_b)

    def test_an_explicit_zero_is_a_floor_and_no_minimum_is_none(self):
        self.run_multi("ada", "bhaskar")
        self.serve([job(1, A, {A: 3, B: 1}, [A], "clear", ""),
                    job(2, A, {A: 0, B: -1}, [A], "clear", ""),
                    job(3, B, {B: -2, A: -4}, [B], "clear", "")])
        self.assertEqual(self.listed(), [1, 2, 3])
        self.assertEqual(self.listed(min=0), [1, 2])
        self.assertIn('href="/export.csv?min=0"', self.page(min=0))
        self.assertIn('href="/export.csv"', self.page())

    def test_names_and_types_are_todays(self):
        self.run_multi("ada", "bhaskar")
        self.serve([job(1, A, {A: 30, B: 12}, [A], "clear", "")])
        for fmt, mime in (("csv", "text/csv"), ("json", "application/json"),
                          ("html", "text/html"), ("xlsx", "application/vnd.openxmlformats-"
                                                          "officedocument.spreadsheetml.sheet")):
            got = self.export(fmt)
            self.assertEqual(got.mimetype, mime)
            self.assertRegex(got.headers["Content-Disposition"],
                             rf'^attachment; filename="sweep-[A-Za-z0-9_-]+-\d{{4}}-\d{{2}}-\d{{2}}\.{fmt}"$')
            for label in (LA, LB):
                self.assertNotIn(label, got.headers["Content-Disposition"])

    def test_an_empty_run_exports_an_empty_file(self):
        self.run_multi("ada", "bhaskar")
        self.serve([])
        header, rows = self.table()
        self.assertEqual((header, rows), (exports.HEADERS + exports.MULTI_KEYS, []))
        self.assertEqual(json.loads(self.export("json").get_data()), [])
        self.assertIn(b"No listings matched those filters.", self.export("html").get_data())


class Fields(Exports):
    """Items 11-22: the engine's fields exactly, labels beside them."""

    def test_the_engine_fields_go_out_exactly(self):
        self.run_multi("ada", "bhaskar", "chen")
        self.serve()
        _header, rows = self.table()
        served = {r["title"]: r for r in ROWS}
        labels = {A: LA, B: LB, C: LC}
        for got in rows:
            want = served[got["Role"]]
            self.assertEqual(got["best_track"], want["best_track"])
            self.assertEqual(got["track_evals"], want["track_evals"])      # byte for byte
            self.assertEqual(json.loads(got["found_by"]), want["found_by"].split(";"))
            rec = want["recommended_tracks"].split(";")
            self.assertEqual(json.loads(got["recommended_tracks"]), rec)   # engine order
            self.assertEqual(json.loads(got["recommended_track_labels"]),
                             [labels[t] for t in rec])                      # same order
            self.assertEqual(got["recommendation"], want["recommendation"])
            self.assertEqual(got["recommendation_caution"], want["recommendation_caution"])
            self.assertEqual(got["recommendation_caution_computed"], "true")
            self.assertEqual(got["best_track_label"], labels[want["best_track"]])
            self.assertEqual(got["track_labels"], json.dumps(labels, ensure_ascii=False,
                                                             separators=(",", ":")))
            self.assertEqual(got["Score"], str(want["score"]))              # the representative's
        tied = next(r for r in rows if r["recommendation"] == "tied")
        self.assertEqual(json.loads(tied["recommended_track_labels"]), [LA, LB, LC])
        split = next(r for r in rows if r["recommendation"] == "split")
        self.assertEqual(json.loads(split["recommended_tracks"]), [B, C])
        self.assertEqual(split["best_track"], B)

    def test_the_fields_are_the_engines_where_a_rule_would_say_otherwise(self):
        # A tie the engine broke by track order (its evaluations arrived C
        # first), and a split that recommends a lower score over a higher one:
        # nothing here re-derives either.
        self.run_multi("ada", "bhaskar", "chen")
        self.serve([job(2, B, {B: 18, A: 16, C: 9}, [B, C], "split", ""),
                    job(1, A, {C: 10, A: 10}, [A, C], "tied", "")])
        rows = {r["Role"]: r for r in json.loads(self.export("json").get_data())}
        tie, split = rows["Job 1"], rows["Job 2"]
        self.assertEqual((tie["best_track"], list(tie["track_evals"])), (A, [C, A]))
        self.assertEqual(tie["recommended_tracks"], [A, C])
        self.assertEqual((split["recommended_tracks"], split["recommended_track_labels"]),
                         ([B, C], [LB, LC]))

    def test_json_is_native_and_keeps_absence(self):
        self.run_multi("ada", "bhaskar", "chen")
        self.serve()
        rows = json.loads(self.export("json").get_data())
        self.assertEqual(len(rows), 6)
        first = rows[0]
        self.assertEqual(list(first)[:len(exports.HEADERS)], exports.HEADERS)
        self.assertEqual(list(first)[len(exports.HEADERS):], exports.MULTI_KEYS)
        self.assertEqual(first["track_evals"], json.loads(ROWS[0]["track_evals"]))
        self.assertEqual(list(first["track_evals"]), [A, B, C])
        self.assertEqual(first["track_labels"], {A: LA, B: LB, C: LC})
        self.assertEqual(list(first["track_labels"]), [A, B, C])       # run order
        self.assertEqual((first["found_by"], first["recommended_tracks"]), ([B], [A]))
        self.assertIs(first["recommendation_caution_computed"], True)
        self.assertEqual(first["Score"], 30)

    def test_three_caution_states_in_every_format(self):
        self.run_multi("ada", "bhaskar")
        cases = {"absent": dict(recommend=True, caution=False),
                 "empty": dict(recommend=True, caution=True),
                 "not computed at all": dict(recommend=False, caution=False)}
        rows = [job(1, A, {A: 30, B: 12}, [A, B], "close", ""),
                job(2, B, {B: 20, A: 2}, [B], "clear", "no_focus_evidence")]
        want = {"absent": [("false", ""), ("false", "")],
                "empty": [("true", ""), ("true", "no_focus_evidence")],
                "not computed at all": [("false", ""), ("false", "")]}
        for label, kw in cases.items():
            with self.subTest(label):
                self.serve(rows, **kw)
                _h, flat = self.table()
                self.assertEqual([(r["recommendation_caution_computed"],
                                   r["recommendation_caution"]) for r in flat], want[label])
                native = json.loads(self.export("json").get_data())
                for got, (computed, caution) in zip(native, want[label]):
                    self.assertIs(got["recommendation_caution_computed"], computed == "true")
                    if computed == "true":
                        self.assertEqual(got["recommendation_caution"], caution)
                    else:
                        self.assertNotIn("recommendation_caution", got)
                if not kw["recommend"]:
                    for got in native:
                        for key in ("recommended_tracks", "recommended_track_labels",
                                    "recommendation"):
                            self.assertNotIn(key, got)
                    self.assertEqual({(r["recommendation"], r["recommended_tracks"]) for r in flat},
                                     {("", "")})

    def test_the_spreadsheet_keeps_every_value_as_it_was(self):
        from openpyxl import load_workbook
        self.run_multi("ada", "bhaskar")
        self.track(B)["resume_name"] = "=HYPERLINK(1).pdf"
        self.serve([job(1, A, {A: 30, B: 12}, [A, B], "close", ""),
                    job(2, B, {B: -2}, [B], "clear", "no_focus_evidence")])
        book = load_workbook(io.BytesIO(self.export("xlsx").get_data()))
        sheet = book["Listings"]
        head = [c.value for c in sheet[1]]
        self.assertEqual(head, exports.HEADERS + exports.MULTI_KEYS)
        values = [[c.value for c in row] for row in sheet.iter_rows(min_row=2)]
        self.assertEqual(len(values), 2)
        by = [dict(zip(head, v)) for v in values]
        self.assertEqual(by[1]["Score"], -2)                                # a real number
        self.assertEqual(by[1]["best_track"], B)                             # text, as it was
        self.assertEqual(by[1]["best_track_label"], "'=HYPERLINK(1).pdf")    # defused
        self.assertEqual(json.loads(by[0]["track_evals"]),
                         {A: {"s": 30, "m": r2.SKILLS[A]}, B: {"s": 12, "m": r2.SKILLS[B]}})
        self.assertTrue(all(isinstance(v, (str, int, type(None))) for row in values for v in row))
        self.assertTrue(all(not str(c.value or "").startswith("=")
                            for row in sheet.iter_rows() for c in row))
        self.assertEqual(sheet.auto_filter.ref, f"A1:Z3")
        about = {r[0].value: r[1].value for r in book["About this export"].iter_rows()}
        self.assertEqual(about["Minimum score"], "no minimum")
        self.assertEqual(about["Résumés"], f"{LA} · =HYPERLINK(1).pdf")

    def test_the_web_page_says_it_as_the_results_page_does(self):
        self.run_multi("ada", "bhaskar", "chen")
        self.serve()
        page = self.export("html").get_data().decode()
        self.assertIn(f"Note: This posting doesn&#x27;t mention", page)
        self.assertIn(f"Suggested résumé: {LB}. {LA} is close behind.", page)
        self.assertIn(f"Match by résumé: {LA} 30 · {LB} 12 · {LC} 5", page)
        self.assertIn(f"Match by résumé: {LC} 20</div>", page)
        self.assertLess(page.index("Note: This posting"), page.index(f"Suggested résumé: {LC}."))
        for code in ("clear", "close", "tied", "split", "no_focus_evidence"):
            self.assertNotRegex(re.sub(r"<[^>]+>", " ", page.split("<main>")[1]),
                                rf"(?<![\w-]){code}(?!\s+behind)(?![\w-])")


class Labels(Exports):
    """Items 10-11, 22-26, 30-32: labels by id, unique, and only presentation."""

    def test_a_rename_after_the_run_changes_nothing_exported(self):
        a, b = self.run_multi("ada", "bhaskar")
        self.serve([job(1, A, {A: 30, B: 12}, [A, B], "close", "")])
        before = self.table()[1][0]
        self.act(b, "rename", name="Mobile")
        self.assertEqual(self.table()[1][0], before)
        self.assertEqual(json.loads(before["recommended_track_labels"]), [LA, LB])
        self.assertEqual(json.loads(before["track_labels"]), {a: LA, b: LB})
        self.act(b, "remove")                                            # its file is gone
        after = self.table()[1][0]
        self.assertEqual(json.loads(after["track_labels"]), {a: LA, b: "Résumé 2"})
        for key in ("best_track", "track_evals", "found_by", "recommended_tracks",
                    "recommendation", "recommendation_caution"):
            self.assertEqual(after[key], before[key], key)
        again = self.render().test_client()                               # a restart
        again.set_cookie("session", r1.cookie_of(self.client), domain="localhost")
        again.get("/results")
        body = again.get("/export.json").get_json()
        self.assertEqual(body[0]["track_labels"], {a: "Résumé 1", b: "Résumé 2"})

    def test_labels_are_data_exactly(self):
        a, b = self.run_multi("ada", "bhaskar")
        self.serve([job(1, B, {B: 30, A: 12}, [B, A], "close", "")])
        name = """Mö, "b" & <c> it's.pdf"""
        self.track(b)["resume_name"] = name
        _h, rows = self.table()
        self.assertEqual(rows[0]["best_track_label"], name)
        self.assertEqual(json.loads(rows[0]["recommended_track_labels"]), [name, LA])
        native = json.loads(self.export("json").get_data())
        self.assertEqual(native[0]["best_track_label"], name)
        self.assertEqual(native[0]["track_labels"][b], name)
        page = self.export("html").get_data().decode()
        self.assertNotIn("<c>", page)
        self.assertIn("&lt;c&gt;", page)

    def test_a_run_whose_setup_is_gone_exports_by_number(self):
        a, b = self.run_multi("ada", "bhaskar")
        self.serve([job(1, A, {A: 30, B: 12}, [A, B], "close", "")])
        again = self.render().test_client()
        with again.session_transaction() as s:
            s.update(self.cookie(), run_tracks=[[a, "Same"], [b, "Same"]])
        again.get("/results")
        got = again.get("/export.json").get_json()[0]
        self.assertEqual(got["track_labels"], {a: "Résumé 1", b: "Résumé 2"})
        self.assertEqual((got["best_track"], got["recommended_tracks"]), (a, [a, b]))

    def test_the_setup_as_it_stands_decides_nothing_exported(self):
        a, b = self.run_multi("ada", "bhaskar")
        self.serve([job(1, B, {B: 20, A: 5}, [B], "clear", "")])
        exported = self.export("csv").get_data()
        self.act(a, "deselect")
        with u1.fixed_ids("e" * 16):
            self.upload("chen")
        self.assertEqual(self.export("csv").get_data(), exported)


class UniqueLabels(Exports):
    """Items 22-24: one label per résumé, casefolded, refused cleanly."""

    def test_a_label_another_resume_has_is_refused(self):
        a, b = self.free("ada", "bhaskar")
        self.confirm()
        approval, cookie = self.planned(), self.cookie()
        for name in (SA, SA.lower(), f"  {SA.upper()}  ", SA.casefold()):
            with self.subTest(name=name):
                answer = self.act(b, "rename", name=name)
                self.assertEqual(answer.status_code, 400)
                self.assertIn("Another résumé already has that name", answer.get_data(as_text=True))
                self.assertEqual((self.track(b)["name"], self.track(b)["id"]), (SB, b))
                self.assertIs(self.planned(), approval)
                self.assertEqual(self.cookie(), cookie)
        self.assertEqual(self.act(a, "rename", name=f" {SA.lower()} ").status_code, 303)  # itself
        self.assertEqual(self.track(a)["name"], SA.lower())
        self.assertIs(self.planned(), approval)

    def test_a_rename_during_a_run_still_refuses_a_duplicate(self):
        a, b = self.run_multi("ada", "bhaskar")
        self.serve([job(1, A, {A: 30, B: 12}, [A, B], "close", "")])
        run = {k: self.cookie()[k] for k in ("run_id", "run_tracks", "run_plan_hash")}
        self.assertEqual(self.act(a, "rename", name=SB.upper()).status_code, 400)
        self.assertEqual({k: self.cookie()[k] for k in run}, run)
        self.assertEqual(json.loads(self.table()[1][0]["track_labels"]), {a: LA, b: LB})

    def test_default_and_placeholder_labels_avoid_a_casefolded_clash(self):
        self.upload("ada")
        a = self.ids()[0]
        self.act(a, "rename", name="résumé 2")
        self.upload("bhaskar")
        b = self.ids()[1]
        self.assertEqual(self.track(b)["name"], "Résumé 3")
        self.act(a, "rename", name=SB.lower())
        self.client.post(f"/derive?track={b}")
        self.assertEqual(self.track(b)["name"], SB + " (2)")


class Strict(Exports):
    """Items 27, 33-34: nothing private, nothing malformed."""

    def test_no_resume_or_engine_carrier_in_any_format(self):
        self.run_multi("ada", "bhaskar", "chen")
        self.serve()
        forbidden = [t.splitlines()[-1][:40] for t in u1.TEXT.values()] + [
            "SCORING", "SEARCH", "POSITIONING", "ALIGNMENT", "TRACKS", "skill_weights",
            "role_qualifiers", "plan_hash", r1.WORKER_TOKEN, r1.KEY, self.cookie()["sid"],
            self.cookie()["run_id"], self.cookie()["run_plan_hash"], "celery", "bazel"]
        for fmt in FORMATS:
            body = self.export(fmt).get_data()
            if fmt == "xlsx":
                import zipfile
                with zipfile.ZipFile(io.BytesIO(body)) as z:
                    body = b"".join(z.read(n) for n in z.namelist())
            text = body.decode("utf-8", "replace")
            for word in forbidden:
                self.assertNotIn(word, text, (fmt, word[:20]))

    def test_a_row_the_engine_cannot_have_written_exports_nothing(self):
        self.run_multi("ada", "bhaskar")
        good = job(1, A, {A: 30, B: 12}, [A], "clear", "")
        for label, bad in (("caution", dict(good, recommendation_caution="weak")),
                           ("kind", dict(good, recommendation="winner")),
                           ("foreign id", dict(good, best_track="d" * 16)),
                           ("track_evals", dict(good, track_evals="[]"))):
            with self.subTest(label):
                self.serve([good, bad])
                for fmt in ("csv", "json"):
                    answer = self.client.get(f"/export.{fmt}")
                    self.assertEqual(answer.status_code, 502, (label, fmt))
                    self.assertNotIn(b"Job 1", answer.get_data())
        with mock.patch.object(worker_link, "_rows", lambda run_id, strict=False: [
                dict(good, track_evals="[]")]):
            self.assertEqual(self.client.get("/export.csv").status_code, 502)

    def test_one_applied_state_per_job(self):
        self.run_multi("ada", "bhaskar", "chen")
        self.serve()
        header, rows = self.table()
        self.assertEqual(header.count("Applied"), 1)
        self.assertFalse([h for h in header if "applied" in h.lower() and h != "Applied"])
        self.assertEqual(len(rows), 6)


class Flow(Exports):
    """Item 44, end to end."""

    def test_export_view_rename_duplicate_delete(self):
        a, b = self.run_multi("ada", "bhaskar")
        self.serve([job(1, A, {A: 30, B: 12}, [A, B], "close", ""),
                    job(2, B, {B: 20, A: -1}, [B], "clear", "no_focus_evidence")])
        self.page()
        first = self.export("csv").get_data()
        self.page(track=b)
        self.assertEqual(self.export("csv", track=b).get_data(), first)
        self.act(b, "rename", name="Mobile")
        self.assertEqual(self.export("csv").get_data(), first)             # by file, as before
        self.assertEqual(self.act(a, "rename", name="mobile").status_code, 400)
        self.assertEqual(self.export("csv").get_data(), first)
        self.act(b, "remove")
        self.assertEqual(self.export("csv").get_data(),                    # still decodable
                         first.replace(LB.encode(), "Résumé 2".encode()))


if __name__ == "__main__":
    unittest.main()
