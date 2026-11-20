"""DQ4-2 on DQ2b's labelled jobs: recommendation metadata through the REAL
finalize_multi, and nothing else moved. Run:
python -m unittest bench.test_track_recommendation_wiring

Every Sweep rendered in each track search / track scoring combination, its
labelled jobs finalized with recommendation off and on, in two relevance
modes: free copies (each track's title gate decides: DQ3's View A) and copies
paid by every track (View B). With both on, every sibling order too. DQ2b's
captures under production's behaviour flags, pinned rather than inherited; no
model, sockets refused. The labels are read here only to measure.
"""
import copy
import itertools
import json
import os
import socket
import statistics
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (REPO_ROOT, os.path.join(REPO_ROOT, "auto-apply")):
    if path not in sys.path:
        sys.path.insert(0, path)

import local_search  # noqa: E402
import make_profile  # noqa: E402
import scraper  # noqa: E402
import track_recommendation as tr  # noqa: E402
from bench import targeted, targeted_eval  # noqa: E402
from bench import targeted_manifest as M  # noqa: E402
from bench.test_track_search import LIVE_ENV  # noqa: E402

DOCS, MARKET, SOURCES = {}, [], {}
MODES = ("A", "B")
_patches = []
SEARCH, SCORING = make_profile.TRACK_SEARCH_FLAG, make_profile.TRACK_SCORING_FLAG
ALIGN = make_profile.TRACK_ALIGNMENT_FLAG
EXTRA = ["recommended_tracks", "recommendation"]


def setUpModule():
    refuse = mock.patch.object(socket.socket, "connect",
                               side_effect=RuntimeError("DQ4-2 wiring tests opened a socket"))
    refuse.start()
    _patches.append(refuse)
    captures = targeted.load_captures()
    with mock.patch.dict(os.environ, LIVE_ENV, clear=True), \
            tempfile.TemporaryDirectory() as empty:
        MARKET.append(local_search.frozen_market())
        for doc, _vid, _layout in targeted.documents():
            DOCS[doc] = targeted.derive(doc, captures, empty)[:2]


def tearDownModule():
    while _patches:
        _patches.pop().stop()


def sweeps():
    for family, sibs in M.SIBLINGS.items():
        for layout in targeted.LAYOUTS:
            yield family, layout, sibs


def attach(family, layout, order, search="1", scoring="1", recommend="0", align="0",
           caution="0"):
    """What render_sweep is handed for one Sweep under these flags."""
    tracks = [{"id": targeted_eval.track_id(v), "engine": "v2",
               "derived": DOCS[f"{v}-{layout}"][1]} for v in order]
    texts = [DOCS[f"{v}-{layout}"][0] for v in order]
    with mock.patch.dict(os.environ, dict(LIVE_ENV, **{SEARCH: search, SCORING: scoring,
                                                       scraper.RECOMMENDATION_FLAG: recommend,
                                                       ALIGN: align,
                                                       scraper.CAUTION_FLAG: caution}),
                         clear=True):
        return make_profile.with_track_scoring(
            make_profile.with_track_search(tracks, texts, MARKET[0]), texts, MARKET[0])


def source(family, layout, order, search="1", scoring="1", recommend="0", align="0",
           caution="0"):
    key = (family, layout, tuple(order), search, scoring, recommend, align, caution)
    if key not in SOURCES:
        attached = attach(family, layout, order, search, scoring, recommend, align, caution)
        with mock.patch.dict(os.environ, dict(LIVE_ENV, **{SEARCH: search, SCORING: scoring,
                                                           scraper.RECOMMENDATION_FLAG: recommend,
                                                           ALIGN: align,
                                                           scraper.CAUTION_FLAG: caution}),
                             clear=True):
            SOURCES[key] = make_profile.render_sweep(f"dq2b {family} {layout}", attached,
                                                     dict(targeted.PREFS))
    return SOURCES[key]


def fed(family, mode, contexts):
    """The labelled jobs of one family as copies, in DQ3's two relevance modes."""
    rows = []
    for job in (j for j in M.JOBS if j["family"] == family):
        row = {"Source": "greenhouse:probe", "Title": job["Title"], "Company": job["Company"],
               "Location": job["Location"], "Salary": "", "Experience": "", "Posted Date": "1 day ago",
               "Job URL": f"https://example.test/dq4/{job['id']}", "hires_home": "yes",
               "Description": job["Description"]}
        row.update({scraper.FREE: True} if mode == "A"
                   else {scraper.PAID_TRACKS: [c.id for c in contexts], "Source": "linkedin"})
        rows.append(row)
    return rows


def final(family, layout, order, mode, recommend, search="1", scoring="1", align="0",
          caution=False):
    """([(job id, output row)] in output order, LAST_TRACK_STATS) for one run."""
    src = source(family, layout, order, search, scoring, align=align)
    ns = {}
    exec(compile(src, "<dq2b sweep>", "exec"), ns)
    contexts = targeted_eval.contexts(src)
    rows = fed(family, mode, contexts)
    with mock.patch.dict(scraper.SETTINGS, ns["SETTINGS"]):
        out = scraper.finalize_multi(rows, contexts, recommend=recommend, caution=caution)
        stats = copy.deepcopy(scraper.LAST_TRACK_STATS)
    return [(r["apply_url"].rsplit("/", 1)[1], r) for r in out], stats


class RecommendationIsAdditive(unittest.TestCase):

    def test_on_adds_two_fields_and_moves_nothing(self):
        for family, layout, sibs in sweeps():
            for search, scoring in itertools.product("01", "01"):
                for mode in MODES:
                    off, off_stats = final(family, layout, sibs, mode, False, search, scoring)
                    on, on_stats = final(family, layout, sibs, mode, True, search, scoring)
                    where = (family, layout, search, scoring, mode)
                    self.assertEqual([j for j, _r in on], [j for j, _r in off], where)
                    self.assertEqual(on_stats, off_stats, where)
                    for (_j, a), (_k, b) in zip(off, on):
                        self.assertEqual(list(a), scraper.MULTI_OUTPUT_COLUMNS)
                        self.assertEqual(list(b), scraper.MULTI_OUTPUT_COLUMNS + EXTRA)
                        self.assertEqual({k: b[k] for k in a}, a, where)

    def test_every_recommendation_is_its_track_evals_read_by_the_helper(self):
        for family, layout, sibs in sweeps():
            ids = [targeted_eval.track_id(v) for v in sibs]
            for search, scoring in itertools.product("01", "01"):
                for mode in MODES:
                    for _j, row in final(family, layout, sibs, mode, True, search, scoring)[0]:
                        evals = json.loads(row["track_evals"])
                        want = tr.recommend({t: e["s"] for t, e in evals.items()},
                                            [t for t in ids if t in evals])
                        self.assertEqual((row["recommended_tracks"], row["recommendation"]),
                                         (";".join(want.tracks), want.kind))
                        self.assertEqual(want.tracks[0], row["best_track"])


class OrderIndependence(unittest.TestCase):

    def test_membership_and_kind_never_follow_track_order(self):
        for family, layout, sibs in sweeps():
            for mode in MODES:
                seen = {}
                for order in itertools.permutations(sibs):
                    for job, row in final(family, layout, order, mode, True)[0]:
                        listed = row["recommended_tracks"].split(";")
                        self.assertIn(row["best_track"], listed)
                        seen.setdefault(job, set()).add((
                            frozenset(listed), row["recommendation"],
                            json.dumps(json.loads(row["track_evals"]), sort_keys=True)))
                for job, got in seen.items():
                    self.assertEqual(len(got), 1, (family, layout, mode, job, got))


class Gates(unittest.TestCase):
    """DQ4's policy gates, now through finalize_multi (search and scoring on)."""

    @classmethod
    def setUpClass(cls):
        cls.cells = {mode: [] for mode in MODES}
        for family, layout, sibs in sweeps():
            ids = {targeted_eval.track_id(v): v for v in sibs}
            for mode in MODES:
                rows = dict(final(family, layout, sibs, mode, True)[0])
                for job in (j for j in M.JOBS if j["family"] == family and j["kind"] == "specific"):
                    row = rows.get(job["id"])
                    cls.cells[mode].append((job["primary"], None if row is None else (
                        {ids[t] for t in json.loads(row["track_evals"])},
                        [ids[t] for t in row["recommended_tracks"].split(";")])))

    def measure(self, mode):
        evaluated = [(i, got[1]) for i, got in self.cells[mode] if got and i in got[0]]
        sizes = [len(got[1]) if got else 0 for _i, got in self.cells[mode]]
        return (len(self.cells[mode]), len(evaluated), sum(i in rec for i, rec in evaluated),
                sum(i not in rec for i, rec in evaluated), sizes)

    def test_view_a(self):
        cells, evaluated, included, wrong_only, _sizes = self.measure("A")
        self.assertEqual((cells, evaluated), (48, 40))
        self.assertGreaterEqual(included, 36)
        self.assertLessEqual(wrong_only, 3)

    def test_view_b(self):
        cells, evaluated, included, wrong_only, sizes = self.measure("B")
        self.assertEqual((cells, evaluated), (48, 48))
        self.assertGreaterEqual(included, 44)
        self.assertLessEqual(wrong_only, 3)
        self.assertLessEqual(statistics.mean(sizes), 1.35)


class AlignmentCarrier(unittest.TestCase):
    """DQ6-F1-C1 on DQ2b's real derivations: the carrier is exactly the
    accepted leading titles, it moves nothing else, and it adds nothing here
    — every DIRECT, evidenced sibling is already inside the fit margin."""

    def test_it_is_the_accepted_leading_titles_and_nothing_else_moves(self):
        for family, layout, sibs in sweeps():
            on, off = attach(family, layout, sibs, align="1"), attach(family, layout, sibs)
            for a, b in zip(on, off):
                d, e = a["derived"], b["derived"]
                self.assertEqual({k: v for k, v in d.items() if k != "track_alignment"}, e)
                leading = [t["query"] for t in d["track_search"]["leading_titles"]]
                titles = d["track_alignment"]["role_titles"]
                self.assertEqual(titles, leading, (family, layout))
                retrieval = set(d["track_search"]["role_keywords"]) - set(leading)
                self.assertFalse(set(titles) & retrieval, (family, layout))
            src_on, src_off = source(family, layout, sibs, align="1"), source(family, layout, sibs)
            ns_on, ns_off = {}, {}
            exec(compile(src_on, "<on>", "exec"), ns_on)
            exec(compile(src_off, "<off>", "exec"), ns_off)
            self.assertEqual([{k: v for k, v in t.items() if k != "ALIGNMENT"} for t in ns_on["TRACKS"]],
                             ns_off["TRACKS"])
            self.assertEqual({k: v for k, v in ns_on.items() if k not in ("TRACKS", "__builtins__")},
                             {k: v for k, v in ns_off.items() if k not in ("TRACKS", "__builtins__")})

    def test_dq2b_recommendations_are_unchanged(self):
        """Both views, recommendation on: every row identical with the carrier."""
        for family, layout, sibs in sweeps():
            for mode in MODES:
                on = final(family, layout, sibs, mode, True, align="1")
                off = final(family, layout, sibs, mode, True)
                self.assertEqual(on, off, (family, layout, mode))


class RecommendationCaution(unittest.TestCase):
    """AS-2 on DQ2b's real derivations: one field after the recommendation,
    exactly the rule over each recommended track's P3a points, and nothing
    else moved; without POSITIONING it refuses rather than guess."""

    def test_one_field_and_nothing_else_moves(self):
        for family, layout, sibs in sweeps():
            for align in "01":
                for mode in MODES:
                    off, off_stats = final(family, layout, sibs, mode, True, align=align)
                    on, on_stats = final(family, layout, sibs, mode, True, align=align, caution=True)
                    where = (family, layout, align, mode)
                    self.assertEqual([j for j, _r in on], [j for j, _r in off], where)
                    self.assertEqual(on_stats, off_stats, where)
                    for (_j, a), (_k, b) in zip(off, on):
                        self.assertEqual(list(b), list(a) + ["recommendation_caution"], where)
                        self.assertEqual({k: b[k] for k in a}, a, where)

    def test_the_value_is_the_rule_over_each_recommended_tracks_p3a(self):
        for family, layout, sibs in sweeps():
            contexts = {c.id: c for c in targeted_eval.contexts(source(family, layout, sibs))}
            for mode in MODES:
                jobs = {r["Job URL"].rsplit("/", 1)[1]: scraper.job_facts(r)
                        for r in fed(family, mode, list(contexts.values()))}
                for job, row in final(family, layout, sibs, mode, True, caution=True)[0]:
                    facts = jobs[job]
                    focus = [scraper.positioning_points(contexts[t].scoring, facts.text, facts.title)
                             != (0, 0) for t in row["recommended_tracks"].split(";")]
                    self.assertEqual(row["recommendation_caution"],
                                     "" if any(focus) else scraper.NO_FOCUS_EVIDENCE,
                                     (family, layout, mode, job))

    def test_without_positioning_it_fails_closed(self):
        for family, layout, sibs in sweeps():
            with self.assertRaises(ValueError):
                final(family, layout, sibs, "B", True, scoring="0", caution=True)
            final(family, layout, sibs, "B", True, scoring="0")        # the same Sweep runs


class KnownCases(unittest.TestCase):
    """DQ4's named jobs, frozen: the scores of the tracks that matter, the set
    recommended and its kind. The margin is 1 whatever the scores are: no
    absolute floor, and no widening to reach app01's mobile (a scorer limit)."""

    # job, layout, views, {sibling: score}, kind. Every named track is
    # recommended, but for a clear job's runner-up, named to show it is not.
    CASES = (
        ("app05", "plain", "AB", {"app-frontend": 31, "app-fullstack": 31}, "tied"),
        ("app05", "twocol", "AB", {"app-frontend": 31, "app-fullstack": 31}, "tied"),
        ("qa04", "twocol", "AB", {"quality-sdet": 20, "quality-reliability": 20}, "tied"),
        ("plt03", "twocol", "AB", {"platform-platform": 25, "platform-cloud": 25}, "tied"),
        ("app06", "plain", "AB", {"app-frontend": 34, "app-fullstack": 33}, "close"),
        ("plt03", "plain", "AB", {"platform-platform": 25, "platform-cloud": 24}, "close"),
        ("qa02", "plain", "B", {"quality-automation": 18, "quality-sdet": 17}, "close"),
        ("app01", "plain", "AB", {"app-fullstack": 31, "app-mobile": 26}, "clear"),
    )

    def test_named_jobs(self):
        for job_id, layout, views, scores, kind in self.CASES:
            family = next(j["family"] for j in M.JOBS if j["id"] == job_id)
            sibs = M.SIBLINGS[family]
            ids = {targeted_eval.track_id(v): v for v in sibs}
            listed = {v for v in scores if kind != "clear" or scores[v] == max(scores.values())}
            for view in views:
                row = dict(final(family, layout, sibs, view, True)[0])[job_id]
                evals = {ids[t]: e["s"] for t, e in json.loads(row["track_evals"]).items()}
                where = (job_id, layout, view)
                self.assertEqual({v: evals[v] for v in scores}, scores, where)
                self.assertEqual({ids[t] for t in row["recommended_tracks"].split(";")}, listed, where)
                self.assertEqual(row["recommendation"], kind, where)


class Acquisition(unittest.TestCase):
    """The flag is read only where results are written: a Sweep's plan, run
    by the real planner with it on in the process, is the same plan."""

    def plan(self, source_text, recommend, **extra):
        env = {"PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8", "PYTHONIOENCODING": "utf-8",
               "PYTHONDONTWRITEBYTECODE": "1", scraper.RECOMMENDATION_FLAG: recommend, **extra}
        with tempfile.TemporaryDirectory() as home:
            os.makedirs(os.path.join(home, "profiles"))
            open(os.path.join(home, "profiles", "__init__.py"), "w").close()
            with open(os.path.join(home, "profiles", "p.py"), "w", encoding="utf-8") as fh:
                fh.write(source_text)
            got = subprocess.run([sys.executable, "-c", targeted_eval.PLAN, "p", REPO_ROOT],
                                 capture_output=True, text=True, cwd=home,
                                 env=dict(env, HOME=home), timeout=300)
        self.assertEqual(got.returncode, 0, got.stderr[-3000:])
        return json.loads(got.stdout)

    def test_the_flag_never_moves_a_plan(self):
        for family, layout, sibs in sweeps():
            text = source(family, layout, sibs)
            self.assertEqual(self.plan(text, "1"), self.plan(text, "0"), (family, layout))

    def test_the_alignment_carrier_never_moves_a_plan_or_a_scoring_key(self):
        """With track search on and off: off, a track's role_keywords are the
        derivation's own and need not hold the titles ALIGNMENT carries."""
        for family, layout, sibs in sweeps():
            for search in "10":
                on = source(family, layout, sibs, search=search, align="1")
                off = source(family, layout, sibs, search=search)
                self.assertNotEqual(on, off, (family, layout, search))
                self.assertEqual(self.plan(on, "1"), self.plan(off, "1"), (family, layout, search))
                self.assertEqual([c.scoring.key for c in targeted_eval.contexts(on)],
                                 [c.scoring.key for c in targeted_eval.contexts(off)])

    def test_the_caution_flag_never_moves_a_plan_a_profile_or_a_scoring_key(self):
        """AS-2 is engine-side only: no render reads it, and nothing a track
        searches or scores changes with it on in the process."""
        for family, layout, sibs in sweeps():
            text = source(family, layout, sibs, align="1")
            self.assertEqual(source(family, layout, sibs, align="1", caution="1"), text,
                             (family, layout))
            with mock.patch.dict(os.environ, {scraper.CAUTION_FLAG: "1"}):
                keys = [c.scoring.key for c in targeted_eval.contexts(text)]
            self.assertEqual(keys, [c.scoring.key for c in targeted_eval.contexts(text)])
            self.assertEqual(self.plan(text, "1", **{scraper.CAUTION_FLAG: "1"}),
                             self.plan(text, "1"), (family, layout))

    def test_nor_a_profile_or_its_scoring_contexts(self):
        """Not a Render or profile flag: the rendered Sweep (search intent
        included) and every ScoringContext memo key are the same with it on."""
        for family, layout, sibs in sweeps():
            on, off = source(family, layout, sibs, recommend="1"), source(family, layout, sibs)
            self.assertEqual(on, off, (family, layout))
            with mock.patch.dict(os.environ, {scraper.RECOMMENDATION_FLAG: "1"}):
                keys = [c.scoring.key for c in targeted_eval.contexts(on)]
            self.assertEqual(keys, [c.scoring.key for c in targeted_eval.contexts(off)])


if __name__ == "__main__":
    unittest.main()
