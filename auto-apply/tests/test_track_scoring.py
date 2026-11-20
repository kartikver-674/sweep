"""DQ3-1: TrackScoringIntent, the positioning one track may later score with.

Pure and unwired: derive_track_scoring(intent, search_intent) reads one
résumé's TrackIntent and, of its TrackSearchIntent, only the accepted leading
titles and the head-free positioning concepts. What these tests defend, most
important first:

  * no search artefact (role_keywords, focused_titles, fallback_used,
    retrieval) can reach the record
  * the record holds positioning, never capability: no weight, no evidence,
    no alias, no scoring constant — and only the résumé's own titles/concepts
  * work_overlap is a diagnostic and changes nothing else
  * no sibling can reach a track's record; the same inputs give the same bytes

Every fixture is synthetic and built here.
"""
import ast
import dataclasses
import inspect
import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import track_intent as ti      # noqa: E402
import track_scoring           # noqa: E402
import track_search as ts      # noqa: E402


def concept(cid, sources=("summary",), work=False):
    return ti.IntentConcept(cid, True, tuple(sources), work, ())


def declared(title, source, parts=None):
    return ti.DeclaredTitle(title, source, (0, 0), tuple(parts or (title,)), ())


def intent_of(concepts=(), titles=()):
    return ti.TrackIntent(concepts=tuple(concepts), declared_titles=tuple(titles),
                          work_only=(), other_claimed=(), skills_groups=(), skills_order=(),
                          provenance=(), sufficient=True, reason="")


def search_of(concepts=(), leading=()):
    return ts.TrackSearchIntent(
        version=ts.VERSION, sufficient=True, reason="title_and_concepts",
        leading_titles=tuple(ts.SearchTitle(q, s) for q, s in leading), rejected_titles=(),
        concepts=tuple(concepts), excluded_concepts=(), corpus_known=(), retrieval="focused",
        focused_titles=("mobile app developer",), fallback_used=False,
        role_keywords=tuple(q for q, _s in leading) + ("mobile app developer",))


# A mobile résumé: React Native positioned everywhere and used at work, Expo in
# a project, a generic concept the search record already excluded, and a
# misleading header the search record already rejected.
MOBILE = intent_of(
    [concept("react native", ("header", "project", "summary"), work=True),
     concept("expo", ("project",)), concept("software engineering", ("summary",)),
     concept("typescript", ("summary",))],
    [declared("mobile engineer", "header"), declared("react native developer", "summary"),
     declared("data engineer", "summary")])
MOBILE_SEARCH = search_of(["react native", "expo", "typescript"],
                          [("mobile engineer", "header"), ("react native developer", "summary")])


def derive(intent=MOBILE, search=MOBILE_SEARCH):
    return track_scoring.derive_track_scoring(intent, search)


class Api(unittest.TestCase):

    def test_the_signature_has_room_for_one_resumes_two_records(self):
        self.assertEqual(list(inspect.signature(track_scoring.derive_track_scoring).parameters),
                         ["intent", "search_intent"])

    def test_it_imports_no_scorer_planner_or_renderer(self):
        with open(track_scoring.__file__, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        imported |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imported, {"dataclasses", "track_search"})

    def test_the_record_is_immutable(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            derive().concepts = ()


class Concepts(unittest.TestCase):

    def test_they_are_the_search_records_positioning_concepts_in_order(self):
        got = derive()
        self.assertEqual(got.concepts, ("react native", "expo", "typescript"))
        self.assertEqual(got.concept_sources, (("react native", ("header", "project", "summary")),
                                               ("expo", ("project",)),
                                               ("typescript", ("summary",))))

    def test_a_concept_the_search_record_excluded_never_scores(self):
        self.assertNotIn("software engineering", derive().concepts)

    def test_skills_section_and_work_only_records_never_become_scoring_concepts(self):
        noisy = dataclasses.replace(MOBILE, work_only=("apex", "salesforce"),
                                    other_claimed=("kotlin",), skills_groups=("mobile", "web"),
                                    skills_order=(("kotlin", 0, 0), ("apex", 1, 0)))
        self.assertEqual(derive(noisy), derive())

    def test_a_concept_this_resume_never_positioned_is_refused(self):
        with self.assertRaisesRegex(ValueError, "not in this résumé's TrackIntent"):
            derive(search=dataclasses.replace(MOBILE_SEARCH, concepts=("react native", "go")))


class Capability(unittest.TestCase):
    """Positioning is recorded, never evidence: DQ3-2 may only add to a concept
    the job matched AND the track's own ScoringContext already weighs."""

    def test_the_record_holds_ids_and_phrases_only(self):
        record = derive().as_dict()
        self.assertEqual(set(record), {"version", "sufficient", "reason", "concepts",
                                       "role_qualifiers", "concept_sources", "title_sources",
                                       "work_backed"})
        numbers = [v for v in json.loads(json.dumps(record)).values()
                   if isinstance(v, (int, float)) and not isinstance(v, bool)]
        self.assertEqual(numbers, [track_scoring.VERSION])

    def test_ids_are_kept_as_resolved_never_expanded(self):
        # React Native covers React for scoring; the record does not invent React.
        self.assertNotIn("react", derive().concepts)
        self.assertEqual(derive().concepts[0], "react native")


class RoleQualifiers(unittest.TestCase):

    def test_each_accepted_title_gives_its_qualifier_in_order(self):
        self.assertEqual(derive().role_qualifiers, ("mobile", "react native"))
        self.assertEqual(derive().title_sources, (("mobile", "header"), ("react native", "summary")))
        for query, want in (("full stack engineer", "full stack"),
                            ("backend engineer", "backend"),
                            ("mobile engineer", "mobile"),
                            ("data engineer", "data")):     # recorded as declared, never special-cased
            got = derive(intent_of((), [declared(query, "summary")]),
                         search_of((), [(query, "summary")]))
            self.assertEqual(got.role_qualifiers, (want,), query)

    def test_a_declared_title_that_did_not_lead_never_scores(self):
        self.assertNotIn("data", derive().role_qualifiers)

    def test_at_most_max_leading_titles_and_each_qualifier_once(self):
        titles = [declared(t, "summary") for t in ("backend engineer", "backend developer",
                                                    "platform engineer", "devops engineer")]
        got = derive(intent_of((), titles),
                     search_of((), [(t.title, "summary") for t in titles]))
        self.assertEqual(got.role_qualifiers, ("backend",))
        self.assertLessEqual(len(got.role_qualifiers), ts.MAX_LEADING_TITLES)

    def test_a_leading_title_this_resume_never_declared_is_refused(self):
        for leading in ([("react native engineer", "summary")],     # a corpus title
                        [("react native developer", "header")]):    # declared, other source
            with self.assertRaisesRegex(ValueError, "not a title this résumé declared"):
                derive(search=dataclasses.replace(MOBILE_SEARCH, leading_titles=tuple(
                    ts.SearchTitle(q, s) for q, s in leading)))


class SearchArtifactFirewall(unittest.TestCase):

    def test_only_leading_titles_and_concepts_are_read(self):
        base = derive()
        for field, junk in (("role_keywords", ("gen ai engineer", "data scientist")),
                            ("focused_titles", ("gen ai engineer",)),
                            ("fallback_used", True),
                            ("retrieval", "broad"),
                            ("rejected_titles", (ts.RejectedTitle("data engineer", "summary",
                                                                  ts.LIMIT),)),
                            ("excluded_concepts", (("software engineering", "generic"),)),
                            ("corpus_known", ("react native",)),
                            ("sufficient", False), ("reason", "insufficient")):
            got = derive(search=dataclasses.replace(MOBILE_SEARCH, **{field: junk}))
            self.assertEqual(got, base, field)
            self.assertEqual(json.dumps(got.as_dict()), json.dumps(base.as_dict()), field)


class WorkOverlap(unittest.TestCase):

    def test_it_is_a_diagnostic_and_changes_nothing_else(self):
        self.assertEqual(derive().work_backed, ("react native",))
        every = dataclasses.replace(MOBILE, concepts=tuple(
            dataclasses.replace(c, work_overlap=True) for c in MOBILE.concepts))
        none = dataclasses.replace(MOBILE, concepts=tuple(
            dataclasses.replace(c, work_overlap=False) for c in MOBILE.concepts))
        for variant, backed in ((every, ("react native", "expo", "typescript")), (none, ())):
            got = derive(variant)
            self.assertEqual(got.work_backed, backed)
            self.assertEqual(dataclasses.replace(got, work_backed=()),
                             dataclasses.replace(derive(), work_backed=()))


class Sufficiency(unittest.TestCase):

    def test_some_positioning_concept_or_role_qualifier(self):
        both = derive()
        concepts = derive(search=dataclasses.replace(MOBILE_SEARCH, leading_titles=()))
        titles = derive(search=dataclasses.replace(MOBILE_SEARCH, concepts=()))
        neither = derive(intent_of(), search_of())
        self.assertEqual([(r.sufficient, r.reason) for r in (both, concepts, titles, neither)],
                         [(True, "concepts_and_titles"), (True, "concepts"), (True, "titles"),
                          (False, "none")])
        self.assertEqual((neither.concepts, neither.role_qualifiers), ((), ()))

    def test_search_sufficiency_is_not_reused(self):
        # One positioned concept is too little to focus a search, but it is
        # still positioning a later score may use.
        one = dataclasses.replace(MOBILE_SEARCH, sufficient=False, reason="insufficient",
                                  leading_titles=(), concepts=("expo",))
        self.assertEqual((derive(search=one).sufficient, derive(search=one).reason),
                         (True, "concepts"))


class Determinism(unittest.TestCase):

    def test_the_same_inputs_give_the_same_bytes_whatever_the_environment(self):
        first = derive()
        with mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin",
                                          "SWEEP_TRACK_SEARCH_INTENT": "1",
                                          "SWEEP_PROFILE_ENGINE_VERSION": "v1"}, clear=True):
            again = derive()
        self.assertEqual(again, first)
        self.assertEqual(json.dumps(again.as_dict()), json.dumps(first.as_dict()))
        self.assertEqual(json.loads(json.dumps(first.as_dict())), first.as_dict())

    def test_inputs_are_never_written(self):
        before = (MOBILE.as_dict(), MOBILE_SEARCH.as_dict())
        derive()
        self.assertEqual((MOBILE.as_dict(), MOBILE_SEARCH.as_dict()), before)


class SiblingIndependence(unittest.TestCase):

    def test_a_track_is_the_same_alone_or_beside_any_siblings_in_any_order(self):
        backend = (intent_of([concept("go")], [declared("backend engineer", "header")]),
                   search_of(["go"], [("backend engineer", "header")]))
        data = (intent_of([concept("dbt")], [declared("data engineer", "summary")]),
                search_of(["dbt"], [("data engineer", "summary")]))
        alone = json.dumps(derive().as_dict())
        for others in ([], [backend], [backend, data], [data, backend]):
            for sibling in others:
                track_scoring.derive_track_scoring(*sibling)
            self.assertEqual(json.dumps(derive().as_dict()), alone, len(others))


if __name__ == "__main__":
    unittest.main()
