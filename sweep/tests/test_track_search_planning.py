"""DQ2c-2: a 2-3-track Sweep searches its TrackSearchIntent, and nothing else moves.

make_profile.with_track_search attaches each résumé's own derived["track_search"]
when SWEEP_TRACK_SEARCH_INTENT is on; render_sweep projects its role_keywords
into TRACKS[i].SEARCH. The planner (multi_plans, request_key, round_robin,
plan_hash), Himalayas, the free title gate and evaluation are unchanged: other
keywords simply build other requests. Synthetic tracks, no network; DQ2b's
fixtures are exercised in bench/test_track_search_wiring.py.
"""
import copy
import dataclasses
import json
import os
import unittest
from unittest import mock

import local_search
import scraper
import track_search
from sources import feeds
from sweep.tests import test_paid_multi_account as c45
from sweep.tests.test_multi_plan import sweep_env, unified
from sweep.tests.test_multi_results import Isolated, job
from sweep.tests.test_track_loading import A, B, C, CENTRALITY, GATE, PREFS, flags, literals

import make_profile  # noqa: E402  (auto-apply is on the path via test_track_loading)

# DQ3-2: with SWEEP_TRACK_SCORING_INTENT on, render_sweep refuses a 2-3-track
# Sweep that carries no scoring positioning (fail closed, by design). These
# tests render without it, so they pin the flag off; DQ3's tests turn it on.
_SCORING_OFF = mock.patch.dict(os.environ, {make_profile.TRACK_SCORING_FLAG: "0"})


def setUpModule():
    c45.setUpModule()
    _SCORING_OFF.start()


def tearDownModule():
    _SCORING_OFF.stop()
    c45.tearDownModule()

FLAG = make_profile.TRACK_SEARCH_FLAG
GATES = {GATE: "1", CENTRALITY: "1"}          # production's title-gate flags
SPECIAL = {A["id"]: ["frontend engineer", "software developer", "web developer"],
           B["id"]: ["python developer", "software developer", "web developer"],
           C["id"]: ["mern stack developer", "software developer", "web developer"]}


def carried(track, keywords=None):
    """The track with a DQ2c search record; render_sweep reads only role_keywords."""
    keywords = SPECIAL[track["id"]] if keywords is None else keywords
    return dict(track, derived=dict(track["derived"],
                                    track_search={"role_keywords": list(keywords)}))


def rendered(tracks, search="0", **gates):
    with flags(**gates), mock.patch.dict(os.environ, {FLAG: search}):
        return make_profile.render_sweep("probe", list(tracks), PREFS)


def contexts(source):
    sweep = literals(source)
    return [scraper.track_context(t, sweep["SCORING"]) for t in sweep["TRACKS"]]


def shaped(tracks):
    """A TrackContext by value: its scoring context by content digest (the
    evaluation memo key), since its compiled tables compare by identity."""
    return [(t.id, t.role_keywords, t.experience_years, t.title_hints, t.title_exclude,
             t.engine, t.scoring.key) for t in tracks]


def planned(tracks, **sweep):
    with sweep_env(**sweep):
        plans = unified(tracks)
        return plans, scraper.plan_hash(plans, tracks)


# ---------------------------------------------------------------------------
class Flag(unittest.TestCase):

    def test_off_unless_set_to_a_true_word(self):
        with mock.patch.dict(os.environ):
            os.environ.pop(FLAG, None)
            self.assertFalse(make_profile.track_search_enabled())
            for value, want in (("", False), ("0", False), ("false", False), ("off", False),
                                ("1", True), ("true", True), ("yes", True), (" ON ", True)):
                os.environ[FLAG] = value
                self.assertEqual(make_profile.track_search_enabled(), want, value)


class Projection(unittest.TestCase):
    """Only SEARCH.role_keywords of a 2-3-track Sweep may change."""

    def test_off_a_carrier_changes_no_byte(self):
        for gates in ({}, GATES):
            self.assertEqual(rendered([carried(t) for t in (A, B, C)], "0", **gates),
                             rendered([A, B, C], "0", **gates))

    def test_on_search_is_the_carrier_and_everything_else_is_todays(self):
        for n in (2, 3):
            plain, special = [A, B, C][:n], [carried(t) for t in (A, B, C)][:n]
            off = literals(rendered(plain, "0", **GATES))
            on = literals(rendered(special, "1", **GATES))
            for key in off:
                if key != "TRACKS":
                    self.assertEqual(on[key], off[key], (n, key))
            for before, after in zip(off["TRACKS"], on["TRACKS"]):
                self.assertEqual(after["SEARCH"]["role_keywords"], SPECIAL[after["id"]])
                self.assertEqual(dict(after, SEARCH=None), dict(before, SEARCH=None), n)
                self.assertEqual(after["SEARCH"]["experience_years"],
                                 before["SEARCH"]["experience_years"])

    def test_the_title_gate_never_reads_the_carrier(self):
        """Non-vacuous: were the gate fed the carrier's keywords it would move."""
        fed = [dict(t, derived=dict(t["derived"], role_keywords=SPECIAL[t["id"]]))
               for t in (A, B, C)]
        gate = lambda src: [(t["ATS_TITLE_HINTS"], t["ATS_TITLE_EXCLUDE"])  # noqa: E731
                            for t in literals(src)["TRACKS"]]
        today = gate(rendered([A, B, C], "0", **GATES))
        self.assertNotEqual(gate(rendered(fed, "0", **GATES)), today)
        self.assertEqual(gate(rendered([carried(t) for t in (A, B, C)], "1", **GATES)), today)

    def test_one_track_never_specialises(self):
        self.assertEqual(rendered([carried(A)], "1", **GATES), rendered([A], "0", **GATES))
        with flags(**GATES), mock.patch.dict(os.environ, {FLAG: "1"}):
            one_on = make_profile.render("probe", carried(A)["derived"], PREFS)
        with flags(**GATES), mock.patch.dict(os.environ, {FLAG: "0"}):
            one_off = make_profile.render("probe", A["derived"], PREFS)
        self.assertEqual(one_on, one_off)                      # schema 1 never reads it

    def test_a_track_without_a_carrier_keeps_its_own_list(self):
        on = literals(rendered([carried(A), B], "1"))["TRACKS"]
        self.assertEqual([t["SEARCH"]["role_keywords"] for t in on],
                         [SPECIAL[A["id"]], B["derived"]["role_keywords"]])

    def test_rendering_writes_no_input(self):
        tracks = [carried(t) for t in (A, B, C)]
        before = copy.deepcopy(tracks)
        rendered(tracks, "1", **GATES)
        self.assertEqual(tracks, before)


class Attach(unittest.TestCase):
    """with_track_search: each résumé's own record, 2-3 tracks, flag on only."""

    @classmethod
    def setUpClass(cls):
        cls.market = local_search.frozen_market()

    def attach(self, tracks, texts, search):
        with mock.patch.dict(os.environ, {FLAG: search}):
            return make_profile.with_track_search(tracks, texts, self.market)

    def test_off_or_one_track_derives_nothing(self):
        with mock.patch.object(track_search, "derive_track_search",
                               side_effect=AssertionError("derived")):
            for tracks, search in (([A, B, C], "0"), ([A], "1")):
                got = self.attach(tracks, ["text"] * len(tracks), search)
                self.assertEqual(len(got), len(tracks))
                self.assertTrue(all(g is t for g, t in zip(got, tracks)))

    def test_on_each_track_carries_its_own_record_and_keeps_role_keywords(self):
        tracks = [A, B]
        before = copy.deepcopy(tracks)
        got = self.attach(tracks, ["Frontend Engineer", "Python Developer"], "1")
        self.assertEqual(tracks, before)
        for track, out in zip(tracks, got):
            carrier = out["derived"]["track_search"]
            self.assertEqual(out["derived"]["role_keywords"], track["derived"]["role_keywords"])
            self.assertEqual(json.loads(json.dumps(carrier)), carrier)
            # No skill_importance in these synthetic derivations: insufficient,
            # so the record keeps today's list exactly.
            self.assertEqual(carrier["role_keywords"], track["derived"]["role_keywords"])
        with self.assertRaises(ValueError):
            self.attach(tracks, ["only one text"], "1")

    def test_a_record_comes_from_its_own_resume_only(self):
        seen = []
        real = track_search.derive_track_search

        def spy(text, derived, intent, market):
            seen.append((text, derived["role_keywords"]))
            return real(text, derived, intent, market)

        with mock.patch.object(track_search, "derive_track_search", spy):
            first = self.attach([A, B, C], ["a", "b", "c"], "1")
            other = self.attach([A, B, C], ["a", "a different b", "c"], "1")
        self.assertEqual(seen[:3], [("a", A["derived"]["role_keywords"]),
                                    ("b", B["derived"]["role_keywords"]),
                                    ("c", C["derived"]["role_keywords"])])
        self.assertEqual(first[0]["derived"]["track_search"], other[0]["derived"]["track_search"])


class Planning(unittest.TestCase):
    """The planner is generic: the carrier's keywords simply build its units."""

    def test_the_planner_receives_the_specialised_keywords(self):
        ctx = contexts(rendered([carried(t) for t in (A, B, C)], "1"))
        self.assertEqual([list(t.role_keywords) for t in ctx], [SPECIAL[t.id] for t in ctx])
        plans, _hash = planned(ctx)
        for units in plans.values():
            for unit in units:
                self.assertTrue(all(unit["keywords"] in SPECIAL[tid]
                                    for tid in unit[scraper.PAID_TRACKS]), unit)

    def test_off_contexts_plans_keys_and_hash_are_todays(self):
        today = contexts(rendered([A, B, C], "0"))
        off = contexts(rendered([carried(t) for t in (A, B, C)], "0"))
        self.assertEqual(shaped(off), shaped(today))
        self.assertEqual(planned(off), planned(today))

    def test_one_track_plans_as_today_with_the_flag_on(self):
        today = contexts(rendered([A], "0"))
        on = contexts(rendered([carried(A)], "1"))
        self.assertEqual(shaped(on), shaped(today))
        self.assertEqual(planned(on), planned(today))

    def test_an_identical_built_request_runs_once_for_both_tracks(self):
        same = ["full stack engineer"]
        ctx = contexts(rendered([carried(A, same), carried(B, same)], "1"))
        indeed, _h = planned(ctx, sites=("indeed",))              # reads no experience
        self.assertEqual([(u["keywords"], u[scraper.PAID_TRACKS]) for u in indeed["indeed"]],
                         [("full stack engineer", [A["id"], B["id"]])])
        linkedin, _h = planned(ctx, sites=("linkedin",))          # f_E 4 vs 5: two inputs
        self.assertEqual([(u["keywords"], u[scraper.PAID_TRACKS]) for u in linkedin["linkedin"]],
                         [("full stack engineer", [A["id"]]),
                          ("full stack engineer", [B["id"]])])

    def test_each_tracks_specialty_leads_the_budget(self):
        for group in ((A, B), (A, B, C)):
            ctx = contexts(rendered([carried(t) for t in group], "1"))
            heads = [SPECIAL[t["id"]][0] for t in group]
            plans, _h = planned(ctx, sites=("indeed",))
            units = plans["indeed"]
            self.assertEqual([u["keywords"] for u in units[:len(group)]], heads)
            self.assertTrue(all(u["keywords"] not in heads for u in units[len(group):]))
            capped, _h = planned(ctx, sites=("indeed",), max_searches_per_site=len(group))
            self.assertEqual([u["keywords"] for u in capped["indeed"]], heads)

    def test_the_plan_hash_follows_the_executable_requests(self):
        special = [carried(t) for t in (A, B, C)]
        first = planned(contexts(rendered(special, "1")))[1]
        self.assertEqual(planned(contexts(rendered(special, "1")))[1], first)
        changed = [carried(A, ["backend engineer"]), *special[1:]]
        self.assertNotEqual(planned(contexts(rendered(changed, "1")))[1], first)
        self.assertEqual(planned(contexts(rendered(special, "0")))[1],
                         planned(contexts(rendered([A, B, C], "0")))[1])
        self.assertNotEqual(planned(contexts(rendered(special, "0")))[1], first)

    def test_himalayas_reads_the_specialised_keywords_specialty_first(self):
        ctx = contexts(rendered([carried(t) for t in (A, B, C)], "1"))
        queries = scraper.himalayas_queries(ctx)
        self.assertEqual(queries[:3], [SPECIAL[t.id][0] for t in ctx])
        self.assertEqual(queries, scraper.round_robin([SPECIAL[t.id] for t in ctx]))
        many = [carried(t, [f"{t['id'][:4]} role {i}" for i in range(6)]) for t in (A, B, C)]
        urls = feeds._himalayas_urls({"queries": scraper.himalayas_queries(
            contexts(rendered(many, "1")))})
        self.assertEqual(len(urls), 8)                       # the total cap, unchanged


class Results(Isolated):
    """Search targeting only: fixed copies evaluate identically on or off."""

    def test_fixed_jobs_evaluate_identically(self):
        off = contexts(rendered([A, B, C], "0", **GATES))
        on = contexts(rendered([carried(t) for t in (A, B, C)], "1", **GATES))
        self.assertEqual(shaped(dataclasses.replace(b, role_keywords=a.role_keywords)
                                for a, b in zip(off, on)), shaped(off))
        ids = [t.id for t in off]
        rows = [job("react-paid", "React Developer", "React and TypeScript.", paid=ids[:1]),
                job("python-paid", "Python Developer", "Python and Django.", paid=ids[1:2]),
                job("shared", "Frontend Engineer", "React, Node.js and MongoDB.", paid=ids),
                job("free-react", "Frontend Developer", "React and Node.js.", free=True),
                job("free-python", "Backend Python Developer", "Python and Django.", free=True),
                job("free-none", "Accountant", "Ledgers.", free=True)]
        results = []
        for ctx in (off, on):
            rel = [[t.id for t in scraper.relevant_tracks(r, ctx)] for r in rows]
            results.append((rel, scraper.finalize_multi(copy.deepcopy(rows), ctx),
                            dict(scraper.LAST_STATS), dict(scraper.LAST_TRACK_STATS)))
        self.assertTrue(results[0][1])
        self.assertEqual(results[1], results[0])


if __name__ == "__main__":
    unittest.main()
