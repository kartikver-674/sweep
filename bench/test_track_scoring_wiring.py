"""DQ3-2 on DQ2b's documents: each 3-track Sweep scores with its own résumés'
TrackScoringIntent, and acquisition, relevance and eligibility do not move.
Run: python -m unittest bench.test_track_scoring_wiring

DQ2b's captures replayed under production's behaviour flags, pinned rather
than inherited; no model, sockets refused. Every Sweep is planned by the real
planner in all four search/scoring flag combinations. Lives in bench/ because
DQ2b's fixtures may be read only from here (test_targeted: the manifest reaches
no derivation). Final DQ3 quality gates are DQ3-3's; these are the safety ones.
"""
import copy
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
import make_profile  # noqa: E402
import scraper  # noqa: E402
import track_intent  # noqa: E402
import track_scoring  # noqa: E402
import track_search  # noqa: E402
from bench import targeted, targeted_eval  # noqa: E402
from bench import targeted_manifest as M  # noqa: E402
from bench.test_track_search import LIVE_ENV  # noqa: E402
from bench.test_track_search_wiring import dry_run  # noqa: E402

DOCS = {}           # doc -> (text, derived), derived under LIVE_ENV
MARKET = []
_patches = []
SEARCH, SCORING = make_profile.TRACK_SEARCH_FLAG, make_profile.TRACK_SCORING_FLAG
MAX_MODIFIER = scraper.POSITIONING_CAP + scraper.POSITIONING_TITLE_BONUS


def setUpModule():
    refuse = mock.patch.object(socket.socket, "connect",
                               side_effect=RuntimeError("DQ3 wiring tests opened a socket"))
    refuse.start()
    _patches.append(refuse)
    captures = targeted.load_captures()
    with mock.patch.dict(os.environ, LIVE_ENV, clear=True), \
            tempfile.TemporaryDirectory() as empty:
        MARKET.append(local_search.frozen_market())
        for doc, _vid, _layout in targeted.documents():
            text, derived, _gate = targeted.derive(doc, captures, empty)
            DOCS[doc] = (text, derived)


def tearDownModule():
    while _patches:
        _patches.pop().stop()


def sweeps():
    for family, sibs in M.SIBLINGS.items():
        for layout in targeted.LAYOUTS:
            yield family, layout, sibs


def sweep(family, layout, sibs, search="0", scoring="0"):
    """(what the carriers returned, the rendered source) for one Sweep: the
    real render path, both carriers applied, each under its own flag."""
    tracks = [{"id": targeted_eval.track_id(v), "engine": "v2",
               "derived": DOCS[f"{v}-{layout}"][1]} for v in sibs]
    texts = [DOCS[f"{v}-{layout}"][0] for v in sibs]
    with mock.patch.dict(os.environ, dict(LIVE_ENV, **{SEARCH: search, SCORING: scoring}),
                         clear=True):
        attached = make_profile.with_track_scoring(
            make_profile.with_track_search(tracks, texts, MARKET[0]), texts, MARKET[0])
        source = make_profile.render_sweep(f"dq2b {family} {layout}", attached,
                                           dict(targeted.PREFS))
    return attached, source


class Carrier(unittest.TestCase):

    def test_off_nothing_is_attached_and_every_byte_is_todays(self):
        for family, layout, sibs in sweeps():
            attached, source = sweep(family, layout, sibs)
            self.assertTrue(all("track_scoring" not in a["derived"] for a in attached))
            self.assertNotIn(make_profile.POSITIONING, source)
            for ctx in targeted_eval.contexts(source):
                self.assertEqual((ctx.scoring.positioned, ctx.scoring.role_qualifiers), ((), ()))

    def test_on_each_track_positions_with_its_own_record_and_nothing_else_moves(self):
        for family, layout, sibs in sweeps():
            for search in ("0", "1"):
                attached, on = sweep(family, layout, sibs, search, "1")
                _a, off = sweep(family, layout, sibs, search, "0")
                on_ctx, off_ctx = targeted_eval.contexts(on), targeted_eval.contexts(off)
                for v, a, c, o in zip(sibs, attached, on_ctx, off_ctx):
                    text, derived = DOCS[f"{v}-{layout}"]
                    intent = track_intent.derive_track_intent(text, derived)
                    record = track_scoring.derive_track_scoring(
                        intent, track_search.derive_track_search(text, derived, intent, MARKET[0]))
                    self.assertEqual(a["derived"]["track_scoring"], record.as_dict(), v)
                    self.assertEqual((c.scoring.positioned, c.scoring.role_qualifiers),
                                     (record.concepts, record.role_qualifiers), v)
                    self.assertEqual((c.role_keywords, c.title_hints, c.title_exclude),
                                     (o.role_keywords, o.title_hints, o.title_exclude), v)
                    self.assertIs(a["derived"]["role_keywords"], derived["role_keywords"])
                    self.assertEqual("track_search" in a["derived"], search == "1", v)


class Acquisition(unittest.TestCase):
    """All four flag combinations through the real planner: scoring never
    moves a request, a key, a count or the plan hash."""

    def test_scoring_never_moves_a_plan(self):
        for family, layout, sibs in sweeps():
            name = f"dq2b_{family}_{layout}"
            plans = {(s, p): dry_run(sweep(family, layout, sibs, s, p)[1], name)
                     for s in ("0", "1") for p in ("0", "1")}
            self.assertEqual(plans["0", "1"], plans["0", "0"], (family, layout))
            self.assertEqual(plans["1", "1"], plans["1", "0"], (family, layout))
            self.assertNotEqual(plans["1", "0"], plans["0", "0"], (family, layout))


class Scores(unittest.TestCase):
    """The labelled jobs, every track: the same verdicts and relevance, and
    scores that only rise, by at most CAP + TITLE_BONUS."""

    def test_only_scores_move_and_only_up_within_the_bound(self):
        changed = 0
        for family, layout, sibs in sweeps():
            off = targeted_eval.contexts(sweep(family, layout, sibs, "1", "0")[1])
            on = targeted_eval.contexts(sweep(family, layout, sibs, "1", "1")[1])
            for job in (j for j in M.JOBS if j["family"] == family):
                row = {k: job[k] for k in ("Title", "Company", "Location", "Description")}
                facts = scraper.job_facts(row)
                for o, n in zip(off, on):
                    before = scraper.evaluate(copy.deepcopy(row), o.scoring, facts)
                    after = scraper.evaluate(copy.deepcopy(row), n.scoring, facts)
                    self.assertEqual((after.eligible, after.reason, after.matched_skills),
                                     (before.eligible, before.reason, before.matched_skills))
                    self.assertEqual(scraper.title_admits(row["Title"], n.title_hints, n.title_exclude),
                                     scraper.title_admits(row["Title"], o.title_hints, o.title_exclude))
                    if before.eligible:
                        delta = after.score - before.score
                        self.assertTrue(0 <= delta <= MAX_MODIFIER, (job["id"], delta))
                        changed += delta > 0
                        concept, title = scraper.positioning_points(n.scoring, facts.text, facts.title)
                        self.assertEqual(delta, concept + title, job["id"])
                        if job["kind"] == "generic":
                            self.assertEqual(title, 0, job["id"])
        self.assertGreater(changed, 0)


if __name__ == "__main__":
    unittest.main()
