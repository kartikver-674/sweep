"""DQ3-2: a 2-3-track Sweep scores with each résumé's own positioning, and
nothing else moves.

make_profile.with_track_scoring attaches each résumé's own
derived["track_scoring"] when SWEEP_TRACK_SCORING_INTENT is on — deriving the
TrackIntent and TrackSearchIntent it reads itself, so the search flag stays
independent — and render_sweep projects TRACKS[i]["POSITIONING"] onto every
track, refusing a track without one. track_context compiles it into the
track's ScoringContext and evaluate() adds P3a's bounded, additive modifier:
+1 per positioned concept the track weighs and the job matches (capped at +5),
+3 once when the job title names a role qualifier. Synthetic tracks and jobs,
no network; DQ2b's fixtures are exercised in bench/test_track_scoring_wiring.py.
"""
import copy
import dataclasses
import hashlib
import json
import os
import unittest
from unittest import mock

import config
import experience_guard
import local_search
import scraper
import track_intent
import track_scoring
import track_search
from sweep.tests import test_paid_multi_account as c45
from sweep.tests.test_multi_results import Isolated, job
from sweep.tests.test_track_loading import A, B, C, CENTRALITY, GATE, PREFS, flags, literals
from sweep.tests.test_track_search_planning import carried, contexts, planned, shaped

import make_profile  # noqa: E402  (auto-apply is on the path via test_track_loading)

setUpModule, tearDownModule = c45.setUpModule, c45.tearDownModule

SEARCH, SCORING = make_profile.TRACK_SEARCH_FLAG, make_profile.TRACK_SCORING_FLAG
GATES = {GATE: "1", CENTRALITY: "1"}
MARKS = {A["id"]: (["react"], ["frontend"]),
         B["id"]: (["python"], ["python"]),
         C["id"]: (["node.js", "mongodb"], ["mern stack"])}


def positioned(track, concepts=None, qualifiers=None):
    """The track with a DQ3 scoring record; render_sweep reads two fields."""
    own_c, own_q = MARKS[track["id"]]
    record = {"version": track_scoring.VERSION, "sufficient": True, "reason": "concepts_and_titles",
              "concepts": list(own_c) if concepts is None else concepts,        # as given:
              "role_qualifiers": list(own_q) if qualifiers is None else qualifiers,  # no coercion
              "concept_sources": [], "title_sources": [], "work_backed": []}
    return dict(track, derived=dict(track["derived"], track_scoring=record))


def rendered(tracks, search="0", scoring="0", **gates):
    with flags(**gates), mock.patch.dict(os.environ, {SEARCH: search, SCORING: scoring}):
        return make_profile.render_sweep("probe", list(tracks), PREFS)


def legacy_key(ctx):
    """ScoringContext.key exactly as 499967e computed it, before positioning."""
    return hashlib.sha256(json.dumps([
        ctx.engine, [[t, w, p.pattern] for t, w, p in ctx.skill_terms],
        [[c.id, c.weight, list(c.aliases)] for c in ctx.concepts],
        [[t, w, p.pattern] for t, w, p in ctx.penalties],
        [p.pattern for p in ctx.frontend], [p.pattern for p in ctx.backend],
        [p.pattern for p in ctx.fullstack_title], ctx.fullstack_bonus,
        [p.pattern for p in ctx.hard_drop], ctx.max_experience_years,
        ctx.candidate_experience_months,
    ], ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def context(weights, positioning=None, engine="v2"):
    """A ScoringContext over config's pristine tables and these skill weights."""
    scoring = dict(config.BASE_SCORING, skill_weights=dict(weights), penalty_terms={},
                   frontend_terms=[], backend_terms=[], fullstack_title_terms=[],
                   fullstack_bonus=0)
    settings = {"max_experience_years": 6, "candidate_experience_months": 40}
    return scraper.scoring_context(scoring, settings, engine, positioning)


def points(ctx, title, description=""):
    facts = scraper.job_facts({"Title": title, "Description": description})
    return scraper.positioning_points(ctx, facts.text, facts.title)


WEIGHTS = {"react": 5, "react native": 5, "node.js": 4, "graphql": 2, "typescript": 3,
           "postgresql": 3, "redux": 2, "python": 4}


# ---------------------------------------------------------------------------
class Flag(unittest.TestCase):

    def test_off_unless_set_to_a_true_word(self):
        with mock.patch.dict(os.environ):
            os.environ.pop(SCORING, None)
            self.assertFalse(make_profile.track_scoring_enabled())
            for value, want in (("", False), ("0", False), ("false", False), ("off", False),
                                ("1", True), ("true", True), ("yes", True), (" ON ", True)):
                os.environ[SCORING] = value
                self.assertEqual(make_profile.track_scoring_enabled(), want, value)

    def test_the_search_and_scoring_flags_are_independent(self):
        for search, scoring in (("1", "0"), ("0", "1")):
            with mock.patch.dict(os.environ, {SEARCH: search, SCORING: scoring}):
                self.assertEqual((make_profile.track_search_enabled(),
                                  make_profile.track_scoring_enabled()),
                                 (search == "1", scoring == "1"))


class Carrier(unittest.TestCase):
    """with_track_scoring: each résumé's own record, 2-3 tracks, flag on only."""

    @classmethod
    def setUpClass(cls):
        cls.market = local_search.frozen_market()

    def attach(self, tracks, texts, scoring, search="0"):
        with mock.patch.dict(os.environ, {SEARCH: search, SCORING: scoring}):
            return make_profile.with_track_scoring(tracks, texts, self.market)

    def test_off_or_one_track_derives_nothing(self):
        with mock.patch.object(track_scoring, "derive_track_scoring",
                               side_effect=AssertionError("derived")):
            for tracks, scoring in (([A, B, C], "0"), ([A], "1")):
                got = self.attach(tracks, ["text"] * len(tracks), scoring)
                self.assertTrue(all(g is t for g, t in zip(got, tracks)))

    def test_on_each_track_carries_its_own_record_without_the_search_flag(self):
        tracks, texts = [A, B], ["Frontend Engineer\nSummary\nReact.", "Python Developer"]
        before = copy.deepcopy(tracks)
        got = self.attach(tracks, texts, "1", search="0")
        self.assertEqual(tracks, before)
        for track, text, out in zip(tracks, texts, got):
            derived = track["derived"]
            intent = track_intent.derive_track_intent(text, derived)
            want = track_scoring.derive_track_scoring(
                intent, track_search.derive_track_search(text, derived, intent, self.market))
            self.assertEqual(out["derived"]["track_scoring"], want.as_dict())
            self.assertNotIn("track_search", out["derived"])
            self.assertIs(out["derived"]["role_keywords"], derived["role_keywords"])
        with self.assertRaises(ValueError):
            self.attach(tracks, ["only one text"], "1")

    def test_a_record_comes_from_its_own_resume_only(self):
        first = self.attach([A, B, C], ["a", "b", "c"], "1")
        other = self.attach([A, B, C], ["a", "a different b", "c"], "1")
        self.assertEqual(first[0]["derived"]["track_scoring"],
                         other[0]["derived"]["track_scoring"])


class Rendering(unittest.TestCase):

    def test_off_a_carrier_changes_no_byte(self):
        plain = rendered([A, B, C], **GATES)
        self.assertEqual(rendered([positioned(t) for t in (A, B, C)], **GATES), plain)
        self.assertNotIn(make_profile.POSITIONING, plain)

    def test_on_each_track_carries_its_positioning_and_nothing_else_moves(self):
        off = literals(rendered([positioned(t) for t in (A, B, C)], **GATES))
        on = literals(rendered([positioned(t) for t in (A, B, C)], scoring="1", **GATES))
        for track in on["TRACKS"]:
            own_c, own_q = MARKS[track["id"]]
            self.assertEqual(track.pop(make_profile.POSITIONING),
                             {"concepts": own_c, "role_qualifiers": own_q})
        self.assertEqual(on, off)

    def test_one_track_never_positions(self):
        with flags(**GATES), mock.patch.dict(os.environ, {SCORING: "1"}):
            one = make_profile.render_sweep("probe", [positioned(A)], PREFS)
        self.assertEqual(one, rendered([A], **GATES))
        self.assertNotIn(make_profile.POSITIONING, one)

    def test_on_a_missing_or_malformed_carrier_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "no track_scoring record"):
            rendered([A, B], scoring="1")
        for concepts, qualifiers in (("react", []), ([1], []), ([""], []), (["react"], None),
                                     (["react", "react"], [])):
            record = positioned(A, concepts, qualifiers)
            if qualifiers is None:
                del record["derived"]["track_scoring"]["role_qualifiers"]
            with self.assertRaises(ValueError, msg=(concepts, qualifiers)):
                rendered([record, positioned(B)], scoring="1")
        self.assertIn("TRACKS", rendered([A, B]))           # off: no carrier needed

    def test_the_rendered_positioning_loads_into_each_context(self):
        source = rendered([positioned(t) for t in (A, B, C)], scoring="1", **GATES)
        make_profile.check_tracks(literals(source)["TRACKS"])
        for ctx in contexts(source):
            own_c, own_q = MARKS[ctx.id]
            self.assertEqual((ctx.scoring.positioned, ctx.scoring.role_qualifiers),
                             (tuple(own_c), tuple(own_q)))


class Schema(unittest.TestCase):

    def tracks(self):
        return literals(rendered([positioned(t) for t in (A, B)], scoring="1"))["TRACKS"]

    def test_malformed_positioning_is_refused(self):
        def edit(fn):
            tracks = self.tracks()
            fn(tracks)
            return tracks
        cases = {
            "not a dict": lambda t: t[0].update(POSITIONING=["react"]),
            "extra key": lambda t: t[0]["POSITIONING"].update(weights={}),
            "missing key": lambda t: t[0]["POSITIONING"].pop("role_qualifiers"),
            "concepts not a list": lambda t: t[0]["POSITIONING"].update(concepts="react"),
            "qualifiers not a list": lambda t: t[0]["POSITIONING"].update(role_qualifiers=None),
            "non-string": lambda t: t[0]["POSITIONING"].update(concepts=[5]),
            "empty string": lambda t: t[0]["POSITIONING"].update(role_qualifiers=[""]),
            "untrimmed": lambda t: t[0]["POSITIONING"].update(concepts=[" react"]),
            "duplicate": lambda t: t[0]["POSITIONING"].update(concepts=["react", "react"]),
            "only some tracks": lambda t: t[1].pop("POSITIONING"),
            "unknown track key": lambda t: t[0].update(SCORING_EXTRA={}),
        }
        for name, fn in cases.items():
            with self.assertRaises(ValueError, msg=name):
                make_profile.check_tracks(edit(fn))
        one = self.tracks()[:1]
        with self.assertRaisesRegex(ValueError, "2-3-track Sweep"):
            make_profile.check_tracks(one)
        self.assertEqual(len(make_profile.check_tracks(self.tracks())), 2)


class Context(unittest.TestCase):

    def test_positioning_compiles_with_the_p3a_policy(self):
        ctx = context(WEIGHTS, {"concepts": ["react"], "role_qualifiers": ["frontend"]})
        self.assertEqual((ctx.positioned, ctx.role_qualifiers, ctx.positioning_step,
                          ctx.positioning_cap, ctx.positioning_title_bonus),
                         (("react",), ("frontend",), 1, 5, 3))

    def test_without_positioning_every_context_and_key_is_todays(self):
        plain = context(WEIGHTS)
        self.assertEqual((plain.positioned, plain.role_qualifiers, plain.positioning_step,
                          plain.positioning_cap, plain.positioning_title_bonus), ((), (), 0, 0, 0))
        empty = context(WEIGHTS, {"concepts": [], "role_qualifiers": []})
        for ctx in [plain, empty] + [c.scoring for c in contexts(rendered([A, B, C], **GATES))]:
            self.assertEqual(ctx.key, legacy_key(ctx))
        self.assertEqual(empty.key, plain.key)
        if not config.TRACKS:
            self.assertEqual(scraper.default_context().key, legacy_key(scraper.default_context()))

    def test_every_positioning_input_is_in_the_key(self):
        base = context(WEIGHTS, {"concepts": ["react"], "role_qualifiers": ["frontend"]})
        variants = [context(WEIGHTS, {"concepts": ["react", "redux"], "role_qualifiers": ["frontend"]}),
                    context(WEIGHTS, {"concepts": ["react"], "role_qualifiers": ["mobile"]}),
                    dataclasses.replace(base, positioning_step=2),
                    dataclasses.replace(base, positioning_cap=4),
                    dataclasses.replace(base, positioning_title_bonus=5)]
        keys = [base.key] + [v.key for v in variants]
        self.assertEqual(len(set(keys)), len(keys))
        self.assertNotEqual(base.key, context(WEIGHTS).key)


class Memo(Isolated):
    """Release-critical: a row evaluated for two sibling positionings is two
    verdicts, and it is the key that keeps them apart."""

    def test_one_row_under_two_positionings_is_never_reused(self):
        react = context(WEIGHTS, {"concepts": ["react"], "role_qualifiers": []})
        python = context(WEIGHTS, {"concepts": ["python"], "role_qualifiers": []})
        row = job("memo", "React Developer", "React and TypeScript.", paid=["x"])
        first, second = scraper.evaluate_once(row, react), scraper.evaluate_once(row, python)
        self.assertEqual((first.score, second.score),
                         (scraper.evaluate(row, react).score, scraper.evaluate(row, python).score))
        self.assertEqual(first.score, second.score + 1)
        self.assertEqual(len(row[scraper.EVALS]), 2)
        # A key blind to positioning would hand python the react verdict.
        blind = dataclasses.replace(python)
        blind.__dict__["key"] = react.key
        self.assertIs(scraper.evaluate_once(row, blind), first)
        self.assertNotEqual(scraper.evaluate(row, blind).score, first.score)


class ConceptPoints(Isolated):

    def test_matched_positioned_and_weighed_earns_one_step(self):
        ctx = context(WEIGHTS, {"concepts": ["graphql"], "role_qualifiers": []})
        self.assertEqual(points(ctx, "API Developer", "GraphQL APIs."), (1, 0))
        row = {"Title": "API Developer", "Description": "GraphQL APIs."}
        self.assertEqual(scraper.evaluate(row, ctx).score,
                         scraper.evaluate(row, context(WEIGHTS)).score + 1)

    def test_matched_but_not_positioned_earns_nothing(self):
        ctx = context(WEIGHTS, {"concepts": ["python"], "role_qualifiers": []})
        self.assertEqual(points(ctx, "API Developer", "GraphQL APIs."), (0, 0))

    def test_positioned_but_not_weighed_earns_nothing(self):
        """The capability firewall: positioning never creates evidence."""
        ctx = context(WEIGHTS, {"concepts": ["kubernetes"], "role_qualifiers": []})
        self.assertEqual(points(ctx, "Platform Engineer", "Kubernetes everywhere."), (0, 0))

    def test_positioned_and_weighed_but_absent_from_the_job_earns_nothing(self):
        ctx = context(WEIGHTS, {"concepts": ["graphql"], "role_qualifiers": []})
        self.assertEqual(points(ctx, "API Developer", "REST APIs."), (0, 0))

    def test_a_concept_counts_once_however_often_it_appears(self):
        ctx = context(WEIGHTS, {"concepts": ["graphql"], "role_qualifiers": []})
        self.assertEqual(points(ctx, "GraphQL Developer", "GraphQL, GraphQL and graphql."), (1, 0))

    def test_the_concept_subtotal_caps_at_five(self):
        six = ["react", "node.js", "graphql", "typescript", "postgresql", "redux"]
        ctx = context(WEIGHTS, {"concepts": six, "role_qualifiers": []})
        text = "React, Node.js, GraphQL, TypeScript, PostgreSQL and Redux."
        self.assertEqual(points(ctx, "Developer", text), (5, 0))
        self.assertEqual(points(dataclasses.replace(ctx, positioned=tuple(six[:5])),
                                "Developer", text), (5, 0))
        self.assertEqual(points(dataclasses.replace(ctx, positioned=tuple(six[:4])),
                                "Developer", text), (4, 0))

    def test_it_is_skill_scorings_own_matcher(self):
        # React inside "React Native" is React Native's, exactly as score() counts.
        ctx = context(WEIGHTS, {"concepts": ["react", "react native"], "role_qualifiers": []})
        self.assertEqual(points(ctx, "React Native Developer", ""), (1, 0))

    def test_a_v1_context_never_positions(self):
        on = context(WEIGHTS, {"concepts": ["react"], "role_qualifiers": ["react"]}, engine="v1")
        row = {"Title": "React Developer", "Description": "React."}
        self.assertEqual(points(on, row["Title"], row["Description"]), (0, 0))
        self.assertEqual(scraper.evaluate(row, on), scraper.evaluate(row, context(WEIGHTS, engine="v1")))


class TitlePoints(unittest.TestCase):

    def ctx(self, *qualifiers):
        return context(WEIGHTS, {"concepts": [], "role_qualifiers": list(qualifiers)})

    def test_a_qualifier_in_the_job_title_earns_the_bonus_once(self):
        self.assertEqual(points(self.ctx("full stack"), "Senior Full-Stack Developer"), (0, 3))
        self.assertEqual(points(self.ctx("backend"), "Backend Engineer"), (0, 3))
        self.assertEqual(points(self.ctx("backend", "python"), "Backend Python Engineer"), (0, 3))

    def test_only_the_title_is_read(self):
        self.assertEqual(points(self.ctx("backend"), "Frontend Engineer"), (0, 0))
        self.assertEqual(points(self.ctx("mobile"), "Software Engineer", "Our mobile app."), (0, 0))

    def test_case_and_joiners_are_one_spelling(self):
        for title in ("BACK-END Engineer", "back_end engineer", "Backend/Platform Engineer",
                      "  backend   engineer "):
            self.assertEqual(points(self.ctx("backend"), title), (0, 3), title)
        self.assertEqual(points(self.ctx("react native"), "React_Native/Mobile Developer"), (0, 3))

    def test_known_dq3_3_calibration_issue_a_lone_data_qualifier_aligns_data_scientist(self):
        """MEASURED, current behaviour — not final product semantics. The audited
        whole-word rule lets a data engineer's "data" align "Data Scientist";
        DQ3-3 decides whether the title bonus or its predicate changes."""
        self.assertEqual(points(self.ctx("data"), "Data Scientist"), (0, 3))

    def test_title_words_are_the_search_records_spelling(self):
        self.assertEqual(scraper.TITLE_COMPOUNDS, track_search.COMPOUNDS)
        self.assertEqual(scraper._TITLE_JOINER.pattern, track_search._JOINER.pattern)
        self.assertEqual(scraper._TITLE_TOKEN.pattern, track_search._TOKEN.pattern)
        for title in ("Senior Full-Stack Developer (Node.js/React)", "FULLSTACK engineer",
                      "Front End Engineer", "back_end dev", "C++/C# Developer", "AI/ML Engineer",
                      "Node.js. Engineer", "  React   Native  ", "Data Scientist - II", ""):
            self.assertEqual(scraper.title_words(title), track_search._tokens(title), title)


class HardFilters(Isolated):
    """Positioning is added only after every hard filter, and never undoes one."""

    def test_hard_filtered_rows_are_refused_exactly_as_before(self):
        on = context(WEIGHTS, {"concepts": ["react"], "role_qualifiers": ["react", "frontend"]})
        off = context(WEIGHTS)
        rows = [{"Title": "React Developer", "Company": "Jobgether", "Description": "React."},
                {"Title": "Frontend Engineering Manager", "Description": "React."},
                {"Title": "React Developer", "Description": "React. 9+ years of experience."}]
        for row in rows:
            self.assertEqual(scraper.evaluate(row, on), scraper.evaluate(row, off), row["Title"])
            self.assertFalse(scraper.evaluate(row, on).eligible, row["Title"])
        guarded = {"Title": "React Developer",
                   "Description": "Minimum of 8 years of professional experience required. React."}
        with mock.patch.dict(os.environ, {experience_guard.FLAG: "1"}):
            got, want = scraper.evaluate(guarded, on), scraper.evaluate(guarded, off)
        self.assertEqual(got, want)
        self.assertEqual((got.eligible, got.reason), (False, "excluded"))


class Planning(unittest.TestCase):
    """Acquisition never reads positioning: all four flag combinations."""

    def test_scoring_never_moves_a_plan(self):
        tracks = [positioned(carried(t)) for t in (A, B, C)]
        got = {}
        for search in ("0", "1"):
            for scoring in ("0", "1"):
                ctx = contexts(rendered(tracks, search, scoring, **GATES))
                got[search, scoring] = (planned(ctx), [c.role_keywords for c in ctx], ctx)
        for search in ("0", "1"):
            self.assertEqual(got[search, "1"][:2], got[search, "0"][:2], search)
            off, on = got[search, "0"][2], got[search, "1"][2]
            self.assertEqual(shaped(dataclasses.replace(o, scoring=dataclasses.replace(
                             n.scoring, positioned=(), role_qualifiers=(), positioning_step=0,
                             positioning_cap=0, positioning_title_bonus=0)) for o, n in zip(off, on)),
                             shaped(off))
        self.assertNotEqual(got["1", "0"][0], got["0", "0"][0])      # search did move it


class Results(Isolated):
    """On a fixed job set, scoring on evaluates the same tracks; only scores move."""

    def test_the_same_tracks_are_judged_and_found_only_scores_rise(self):
        tracks = [positioned(t) for t in (A, B, C)]
        off = contexts(rendered(tracks, **GATES))
        on = contexts(rendered(tracks, scoring="1", **GATES))
        ids = [t.id for t in off]
        rows = [job("react-paid", "React Developer", "React and TypeScript.", paid=ids[:1]),
                job("shared", "Frontend Engineer", "React, Node.js and MongoDB.", paid=ids),
                job("free-react", "Frontend Developer", "React and Node.js.", free=True),
                job("free-none", "Accountant", "Ledgers.", free=True)]
        out = {}
        for name, ctx in (("off", off), ("on", on)):
            rel = [[t.id for t in scraper.relevant_tracks(r, ctx)] for r in rows]
            final = scraper.finalize_multi(copy.deepcopy(rows), ctx)
            out[name] = (rel, {r["apply_url"]: (sorted(json.loads(r["track_evals"])), r["found_by"])
                               for r in final},
                         {r["apply_url"]: json.loads(r["track_evals"]) for r in final})
        self.assertEqual(out["on"][:2], out["off"][:2])
        rises = [out["on"][2][u][t]["s"] - out["off"][2][u][t]["s"]
                 for u in out["off"][2] for t in out["off"][2][u]]
        self.assertTrue(all(0 <= d <= 8 for d in rises), rises)
        self.assertTrue(any(rises))


if __name__ == "__main__":
    unittest.main()
