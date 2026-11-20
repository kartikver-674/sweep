"""DQ3-1 on DQ2b's documents: each résumé's TrackScoringIntent, pure and unwired.
Run: python -m unittest bench.test_track_scoring

DQ2b's captures replayed under production's behaviour flags, pinned rather
than inherited; no model, sockets refused. Lives in bench/ because DQ2b's
fixtures may be read only from here (test_targeted: the manifest reaches no
derivation). Characterisation of what the record holds; no score is computed.
"""
import dataclasses
import json
import os
import socket
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (REPO_ROOT, os.path.join(REPO_ROOT, "auto-apply")):
    if path not in sys.path:
        sys.path.insert(0, path)

import local_search  # noqa: E402
import skill_concepts  # noqa: E402
import track_intent  # noqa: E402
import track_scoring  # noqa: E402
import track_search  # noqa: E402
from bench import targeted  # noqa: E402
from bench import targeted_manifest as M  # noqa: E402
from bench.test_track_search import LIVE_ENV  # noqa: E402

DOCS = {}           # doc -> (derived, intent, search intent)
_patches = []


def setUpModule():
    refuse = mock.patch.object(socket.socket, "connect",
                               side_effect=RuntimeError("track_scoring tests opened a socket"))
    refuse.start()
    _patches.append(refuse)
    captures = targeted.load_captures()
    with mock.patch.dict(os.environ, LIVE_ENV, clear=True), \
            tempfile.TemporaryDirectory() as empty:
        market = local_search.frozen_market()
        for doc, _vid, _layout in targeted.documents():
            text, derived, _gate = targeted.derive(doc, captures, empty)
            intent = track_intent.derive_track_intent(text, derived)
            DOCS[doc] = (derived, intent,
                         track_search.derive_track_search(text, derived, intent, market))


def tearDownModule():
    while _patches:
        _patches.pop().stop()


def scoring(doc):
    _derived, intent, search = DOCS[doc]
    return track_scoring.derive_track_scoring(intent, search)


class Records(unittest.TestCase):

    def test_each_record_is_its_own_search_records_positioning_decisions(self):
        for doc, (_derived, _intent, search) in DOCS.items():
            got = scoring(doc)
            self.assertEqual(got.concepts, search.concepts, doc)
            want = list(dict.fromkeys(track_search.qualifier(t.query)
                                      for t in search.leading_titles))
            self.assertEqual(list(got.role_qualifiers), [q for q in want if q], doc)
            self.assertEqual(got.sufficient, bool(got.concepts or got.role_qualifiers), doc)

    def test_search_artifacts_cannot_move_any_record(self):
        for doc, (_derived, intent, search) in DOCS.items():
            junk = dataclasses.replace(search, role_keywords=("gen ai engineer",),
                                       focused_titles=("gen ai engineer",),
                                       fallback_used=not search.fallback_used,
                                       retrieval="fallback")
            self.assertEqual(track_scoring.derive_track_scoring(intent, junk), scoring(doc), doc)

    def test_every_positioned_concept_is_one_the_track_already_weighs(self):
        """DQ2b measured, not assumed: DQ3-2 must still intersect with the
        ScoringContext, because the record never creates evidence."""
        for doc, (derived, _intent, _search) in DOCS.items():
            weighed = {c.id for c in skill_concepts.from_weights(
                {e["term"]: e["weight"] for e in derived["skill_weights"]})}
            self.assertLessEqual(set(scoring(doc).concepts), weighed, doc)

    def test_the_same_bytes_every_time_and_in_any_sibling_order(self):
        for family, sibs in M.SIBLINGS.items():
            for layout in targeted.LAYOUTS:
                docs = [f"{v}-{layout}" for v in sibs]
                forward = {d: json.dumps(scoring(d).as_dict()) for d in docs}
                backward = {d: json.dumps(scoring(d).as_dict()) for d in reversed(docs)}
                self.assertEqual(forward, backward, (family, layout))


class KnownCases(unittest.TestCase):

    def test_a_skills_group_label_read_as_a_skill_never_scores(self):
        for doc, (_derived, intent, search) in DOCS.items():
            labels = {cid for cid, why in search.excluded_concepts if why == "group_label"}
            self.assertFalse(labels & set(scoring(doc).concepts), doc)
        _d, intent, _s = DOCS["quality-sdet-twocol"]
        self.assertIn("test automation", intent.ids)
        self.assertNotIn("test automation", scoring("quality-sdet-twocol").concepts)

    def test_the_ambiguities_are_recorded_as_each_resume_states_them(self):
        for layout in targeted.LAYOUTS:
            mobile, full = scoring(f"app-mobile-{layout}"), scoring(f"app-fullstack-{layout}")
            self.assertIn("react native", mobile.concepts)
            self.assertIn("react native", full.concepts)        # shared, as both résumés say
            self.assertEqual((mobile.role_qualifiers, full.role_qualifiers),
                             (("mobile",), ("full stack",)))
            self.assertEqual(scoring(f"quality-sdet-{layout}").role_qualifiers, ("test automation",))
            self.assertEqual(scoring(f"quality-automation-{layout}").role_qualifiers,
                             ("backend automation",))
            reliability = scoring(f"quality-reliability-{layout}")
            self.assertEqual((reliability.role_qualifiers, reliability.reason), ((), "concepts"))
            self.assertEqual(scoring(f"data-dataeng-{layout}").role_qualifiers, ("data",))


if __name__ == "__main__":
    unittest.main()
