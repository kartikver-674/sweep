"""DQ4-1: track_recommendation.recommend, pure and unwired; DQ6-F1-C1: the
DIRECT role-alignment reader and the aligned alternative it may add.

Which of a job's already-evaluated tracks to recommend, and how their scores
relate. Imports nothing but the helper: no profile, environment, scraper,
provider or network.
"""
import itertools
import json
import os
import unittest
from unittest import mock

import track_recommendation as tr
from track_recommendation import CLEAR, CLOSE, SPLIT, TIED, direct, readings, recommend


def pick(scores, order=None):
    got = recommend(scores, list(scores) if order is None else order)
    return got.tracks, got.kind


class Kinds(unittest.TestCase):

    def test_the_margin_is_one_named_point(self):
        self.assertEqual(tr.RECOMMENDATION_MARGIN, 1)

    def test_one_track_is_clear_whatever_its_score(self):
        self.assertEqual(pick({"mobile": 20}), (("mobile",), CLEAR))
        self.assertEqual(pick({"mobile": -4}), (("mobile",), CLEAR))

    def test_two_tracks(self):
        for b, want in ((20, (("a", "b"), TIED)), (19, (("a", "b"), CLOSE)),
                        (18, (("a",), CLEAR)), (17, (("a",), CLEAR))):
            self.assertEqual(pick({"a": 20, "b": b}), want, b)

    def test_three_tracks(self):
        for scores, want in (((20, 20, 20), (("a", "b", "c"), TIED)),
                             ((20, 20, 19), (("a", "b", "c"), TIED)),
                             ((20, 20, 18), (("a", "b"), TIED)),
                             ((20, 19, 19), (("a", "b", "c"), CLOSE)),
                             ((20, 19, 18), (("a", "b"), CLOSE)),
                             ((20, 18, 18), (("a",), CLEAR)),
                             ((20, 18, 17), (("a",), CLEAR))):
            self.assertEqual(pick(dict(zip("abc", scores))), want, scores)

    def test_tied_is_about_the_top_not_every_member(self):
        """A and B share the top score; C is a close follower. The kind says
        the top is tied; C's lower score is in track_evals, not here."""
        self.assertEqual(pick({"a": 25, "b": 25, "c": 24}), (("a", "b", "c"), TIED))

    def test_clear_is_not_a_high_score(self):
        self.assertEqual(pick({"a": 2, "b": 0}), (("a",), CLEAR))

    def test_close_needs_one_top(self):
        self.assertEqual(pick({"a": 25, "b": 24, "c": 20}), (("a", "b"), CLOSE))
        self.assertEqual(pick({"a": 25, "b": 23, "c": 20}), (("a",), CLEAR))

    def test_negative_scores_compare_like_any_other(self):
        self.assertEqual(pick({"a": -3, "b": -4, "c": -9}), (("a", "b"), CLOSE))


class Ordering(unittest.TestCase):

    def test_score_first_then_the_supplied_order(self):
        self.assertEqual(pick({"a": 25, "b": 24, "c": 24}, ["c", "a", "b"]),
                         (("a", "c", "b"), CLOSE))

    def test_membership_and_kind_never_depend_on_order(self):
        for scores in ((20, 20), (20, 19), (20, 18), (20, 20, 20), (20, 20, 19),
                       (20, 19, 19), (20, 19, 18), (20, 18, 18)):
            ids = dict(zip("abc", scores))
            seen = set()
            for order in itertools.permutations(ids):
                got = recommend(ids, order)
                seen.add((frozenset(got.tracks), got.kind))
                self.assertEqual([ids[t] for t in got.tracks],
                                 sorted((ids[t] for t in got.tracks), reverse=True))
                equal = [t for t in order if t in got.tracks]
                for score in set(ids.values()):
                    self.assertEqual([t for t in got.tracks if ids[t] == score],
                                     [t for t in equal if ids[t] == score], (scores, order))
            self.assertEqual(len(seen), 1, scores)

    def test_first_is_the_track_best_track_would_pick(self):
        """rank_clusters' best_track: highest score, ties to track order."""
        for scores in ((20, 20), (20, 19), (19, 20, 20), (18, 20, 19), (20, 20, 20)):
            ids = dict(zip("abc", scores))
            for order in itertools.permutations(ids):
                best = min(order, key=lambda t: (-ids[t], order.index(t)))
                self.assertEqual(recommend(ids, order).tracks[0], best, (scores, order))


class Contract(unittest.TestCase):

    def test_an_empty_job_has_no_recommendation(self):
        with self.assertRaises(ValueError):
            recommend({}, [])

    def test_more_tracks_than_a_sweep_can_have(self):
        with self.assertRaises(ValueError):
            recommend({t: 5 for t in "abcd"}, "abcd")

    def test_order_lists_exactly_the_scored_tracks(self):
        scores = {"a": 5, "b": 4}
        for order in (["a"], ["a", "b", "b"], ["a", "b", "c"], ["b", "c"]):
            with self.subTest(order=order), self.assertRaises(ValueError):
                recommend(scores, order)

    def test_only_a_mapping_so_ids_are_unique(self):
        for scores in ([("a", 5), ("a", 4)], (("a", 5),), None, "a"):
            with self.subTest(scores=scores), self.assertRaises(TypeError):
                recommend(scores, ["a"])

    def test_scores_are_whole_numbers(self):
        for bad in (True, False, 5.0, float("nan"), float("inf"), "5", None):
            with self.subTest(score=bad), self.assertRaises(TypeError):
                recommend({"a": 5, "b": bad}, ["a", "b"])

    def test_ids_are_non_empty_strings(self):
        for bad in ("", 1, None):
            with self.subTest(tid=bad), self.assertRaises(TypeError):
                recommend({"a": 5, bad: 4}, ["a", bad])

    def test_the_scores_are_not_touched(self):
        scores, order = {"a": 20, "b": 19}, ["b", "a"]
        recommend(scores, order)
        self.assertEqual((scores, order), ({"a": 20, "b": 19}, ["b", "a"]))

    def test_the_record_is_immutable_and_carries_ids_and_kind_only(self):
        got = recommend({"a": 20, "b": 19}, ["a", "b"])
        with self.assertRaises(Exception):
            got.kind = CLEAR
        self.assertEqual(got.as_dict(), {"tracks": ["a", "b"], "kind": CLOSE})
        self.assertEqual(set(vars(got)), {"tracks", "kind"})

    def test_deterministic_and_environment_blind(self):
        args = ({"a": 20, "b": 20, "c": 19}, ["c", "b", "a"])
        first = recommend(*args)
        with mock.patch.dict(os.environ, {"SWEEP_TRACK_RECOMMENDATION": "1",
                                          "SWEEP_TRACK_SCORING_INTENT": "1"}):
            again = [recommend(*args) for _ in range(5)]
        self.assertTrue(all(g == first for g in again))
        self.assertEqual({json.dumps(g.as_dict()) for g in again}, {json.dumps(first.as_dict())})
        self.assertEqual(first, tr.Recommendation(("b", "a", "c"), TIED))


# ===========================================================================
# DQ6-F1-C1: DIRECT role alignment, and the aligned alternative
# ===========================================================================
FRONTEND, MOBILE, FULLSTACK, AI = (["frontend engineer"], ["react native engineer"],
                                   ["full stack developer"], ["ai engineer", "full stack engineer"])


class Readings(unittest.TestCase):
    """A job title as its roles: (qualifier words, head) per segment."""

    def read(self, title):
        return [(" ".join(q), h) for q, h in readings(title)]

    def test_the_head_and_its_qualifier(self):
        for title, want in (("Frontend Engineer", [("frontend", "engineer")]),
                            ("Senior Frontend Engineer", [("frontend", "engineer")]),
                            ("Sr. Full-Stack Developer", [("full stack", "developer")]),
                            ("Staff Front End Engineer", [("frontend", "engineer")]),
                            ("Senior React Native Developer", [("react native", "developer")])):
            self.assertEqual(self.read(title), want, title)

    def test_a_specific_head_keeps_its_own_specialisation(self):
        """The distinction 2223 turns on: the headed segment already names a
        specialisation, so the trailing one is not read as a role of its own."""
        self.assertEqual(self.read("Mobile Engineer - Frontend"), [("mobile", "engineer")])
        self.assertEqual(self.read("Mobile Engineer (React Native)"), [("mobile", "engineer")])

    def test_only_a_generic_head_borrows_a_segment(self):
        self.assertEqual(self.read("Senior Software Engineer - React Native"),
                         [("react native", "engineer")])
        self.assertEqual(self.read("Senior Engineer - Frontend (Onboarding & Activation)"),
                         [("frontend", "engineer"), ("onboarding activation", "engineer")])
        self.assertEqual(self.read("Staff Engineer - Fullstack"), [("full stack", "engineer")])
        self.assertEqual(self.read("Engineering Manager, Frontend"), [("frontend", "manager")])

    def test_the_head_is_the_right_most_role_word(self):
        self.assertEqual(self.read("Developer Platform Engineer"), [("platform", "engineer")])
        self.assertEqual(self.read("Android Developer with Kotlin"), [("android", "developer")])

    def test_segments(self):
        self.assertEqual(self.read("ERDS-MJ - Gen AI Engineer"), [("gen ai", "engineer")])
        self.assertEqual(self.read("Senior Backend Engineer- AI Agents"), [("backend", "engineer")])
        self.assertEqual(self.read("AI Solutions Specialist -Implementations"),
                         [("ai solutions", "specialist")])
        self.assertEqual(self.read("Senior AI Engineer \u2013 Artificial Intelligence"),
                         [("ai", "engineer")])
        self.assertEqual(self.read("DevOps / SRE Engineer"), [("sre", "engineer")])

    def test_no_head_or_nothing_specific_is_no_reading(self):
        for title in ("Software Engineer", "Senior Staff Software Engineer", "Senior Full Stack",
                      "SDE - 3 - Frontend", "Enterprise GTM Lead, Inference and Agentic AI",
                      "Senior Associate, AI Solutions", "Recorder - Videos, AI training",
                      "Frontend Lead", "", None):
            self.assertEqual(readings(title), (), title)


class Direct(unittest.TestCase):
    """DIRECT on its own: no title gate, eligibility or sibling behind it."""

    def test_critical_positives(self):
        for mine, title in ((FRONTEND, "Senior Frontend Engineer"),
                            (FRONTEND, "Senior Frontend Developer"),
                            (MOBILE, "Senior React Native Engineer"),
                            (MOBILE, "Senior React Native Developer"),
                            (MOBILE, "Senior Software Engineer - React Native"),
                            (["ai engineer"], "Senior AI Engineer"),
                            (["ai engineer"], "ERDS-MJ - Gen AI Engineer"),
                            (["full stack engineer"], "Senior Full Stack Developer"),
                            (FULLSTACK, "Staff Engineer - Fullstack")):
            self.assertTrue(direct(mine, title), (mine, title))

    def test_critical_negatives(self):
        for mine, title in ((FRONTEND, "Frontend Recruiter"),
                            (FRONTEND, "Frontend Product Manager"),
                            (FRONTEND, "Engineering Manager, Frontend"),
                            (FRONTEND, "Frontend Designer"),
                            (FRONTEND, "Frontend Architect"),
                            (FRONTEND, "Technical Recruiter - Frontend"),
                            (MOBILE, "React Native Recruiter"),
                            (MOBILE, "React Native Programmer"),
                            (["ai engineer"], "AI Product Manager"),
                            (["ai engineer"], "AI Specialist"),
                            (["security engineer"], "Security Analyst"),
                            (["data engineer"], "Data Scientist"),
                            (["software engineer"], "Software Engineer")):
            self.assertFalse(direct(mine, title), (mine, title))

    def test_mobile_engineer_frontend_aligns_no_sibling(self):
        """An accepted false negative: no ontology puts React Native in mobile."""
        for mine in (FRONTEND, FULLSTACK, MOBILE):
            self.assertFalse(direct(mine, "Mobile Engineer - Frontend"), mine)

    def test_only_engineer_and_developer_are_one_head(self):
        self.assertEqual(tr.HEAD_CLASS, {"engineer", "developer"})
        for head in ("architect", "specialist", "analyst", "scientist", "consultant",
                     "manager", "recruiter", "designer", "programmer", "lead"):
            self.assertFalse(direct(FRONTEND, f"Frontend {head.title()}"), head)
        self.assertTrue(direct(["frontend developer"], "Staff Frontend Engineer"))

    def test_a_generic_resume_role_never_aligns(self):
        for mine in (["software engineer"], ["software developer"], ["data engineer"]):
            for title in ("Software Engineer", "Senior Software Developer", "Data Engineer",
                          "Senior Data Engineer"):
                self.assertFalse(direct(mine, title), (mine, title))
        self.assertEqual(tr.roles(["software engineer", "data engineer", "frontend engineer"]),
                         ((("frontend",), "engineer"),))
        self.assertFalse(direct([], "Senior Frontend Engineer"))

    def test_ai_wording_is_not_an_ai_engineering_role(self):
        for title in ("AI Training Specialist", "AI Video Recorder", "AI GTM Lead",
                      "Recorder - Videos for Data Collection Project, AI training",
                      "Narrator - Videos for Data Collection Project, AI training",
                      "Enterprise GTM Lead, Inference and Agentic AI",
                      "AI Solutions Specialist -Implementations", "Senior Associate, AI Solutions",
                      "Partner AI Deployment Engineer - AWS", "Senior Backend Engineer- AI Agents",
                      "Senior Machine Learning Engineer", "Software Engineer using AI tools"):
            self.assertFalse(direct(AI, title), title)
        for title in ("Senior AI Engineer", "Gen AI Engineer", "Staff Software Engineer - AI Engineer"):
            self.assertTrue(direct(AI, title), title)

    def test_the_resume_role_keeps_its_head(self):
        self.assertEqual(tr.roles(FRONTEND + FULLSTACK + ["ai engineer"]),
                         ((("frontend",), "engineer"), (("full", "stack"), "developer"),
                          (("ai",), "engineer")))


class AlignedRecommendation(unittest.TestCase):
    """recommend(..., direct_evidenced): the margin set, plus the best-scoring
    DIRECT and evidenced tracks; `split` when one sits outside the margin."""

    def pick(self, scores, aligned, order=None):
        got = recommend(scores, list(scores) if order is None else order, direct_evidenced=aligned)
        return got.tracks, got.kind

    def test_nothing_aligned_is_dq4_exactly(self):
        for scores in ((20,), (20, 20), (20, 19), (20, 18), (20, 20, 20), (20, 20, 19),
                       (20, 20, 18), (20, 19, 19), (20, 19, 18), (20, 18, 18), (-3, -4, -9)):
            ids = dict(zip("abc", scores))
            for order in itertools.permutations(ids):
                want = recommend(ids, order)
                for none in ((), [], frozenset(), set()):
                    self.assertEqual(recommend(ids, order, direct_evidenced=none), want)

    def test_an_aligned_track_outside_the_margin_is_split(self):
        self.assertEqual(self.pick({"a": 20, "b": 12}, {"b"}), (("a", "b"), SPLIT))
        self.assertEqual(self.pick({"a": 20, "b": 19, "c": 12}, {"c"}), (("a", "b", "c"), SPLIT))

    def test_split_outranks_tied(self):
        self.assertEqual(self.pick({"a": 20, "b": 20, "c": 12}, {"c"}), (("a", "b", "c"), SPLIT))
        self.assertEqual(self.pick({"a": 20, "b": 20, "c": 12}, {"c"}, ["b", "a", "c"]),
                         (("b", "a", "c"), SPLIT))

    def test_an_aligned_track_already_in_the_margin_changes_nothing(self):
        self.assertEqual(self.pick({"a": 20, "b": 20, "c": 12}, {"b"}), (("a", "b"), TIED))
        self.assertEqual(self.pick({"a": 20, "b": 20, "c": 19}, {"c"}), (("a", "b", "c"), TIED))
        self.assertEqual(self.pick({"a": 20, "b": 19}, {"b"}), (("a", "b"), CLOSE))
        self.assertEqual(self.pick({"a": 20, "b": 12}, {"a"}), (("a",), CLEAR))

    def test_only_the_best_scoring_aligned_tracks_join(self):
        self.assertEqual(self.pick({"a": 30, "b": 20, "c": 15}, {"b", "c"}), (("a", "b"), SPLIT))
        self.assertEqual(self.pick({"a": 30, "b": 20, "c": 20}, {"b", "c"}),
                         (("a", "b", "c"), SPLIT))
        self.assertEqual(self.pick({"a": 30, "b": 20, "c": 15}, {"a", "c"}), (("a",), CLEAR))

    def test_membership_and_kind_never_depend_on_order(self):
        for scores, aligned in (((20, 20, 12), {"c"}), ((30, 20, 20), {"b", "c"}),
                                ((30, 20, 15), {"b", "c"}), ((20, 12, 12), {"b"})):
            ids = dict(zip("abc", scores))
            seen = {(frozenset(g.tracks), g.kind) for g in
                    (recommend(ids, order, direct_evidenced=aligned)
                     for order in itertools.permutations(ids))}
            self.assertEqual(len(seen), 1, scores)
            for order in itertools.permutations(ids):
                got = recommend(ids, order, direct_evidenced=aligned)
                self.assertEqual(got.tracks[0], min(order, key=lambda t: (-ids[t], order.index(t))))

    def test_an_aligned_track_must_be_scored(self):
        with self.assertRaises(ValueError):
            recommend({"a": 20, "b": 12}, ["a", "b"], direct_evidenced={"c"})
        scores, aligned = {"a": 20, "b": 12}, {"b"}
        recommend(scores, ["a", "b"], direct_evidenced=aligned)
        self.assertEqual((scores, aligned), ({"a": 20, "b": 12}, {"b"}))


if __name__ == "__main__":
    unittest.main()
