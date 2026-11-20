"""DQ4-1 on DQ2b's labelled jobs: track_recommendation over the final scores,
pure and unwired. Run: python -m unittest bench.test_track_recommendation

Each Sweep is rendered with track search and track scoring on (DQ3's final
P3a), every labelled job evaluated by every track, and the helper handed only
what production would hand it: the scores of the tracks evaluated and eligible
for that job. Two views, as DQ3's gates: A, a track is evaluated when its free
title gate admits the job (production relevance for a free copy); B, every
eligible track (diagnostic). A job no track evaluates gets no recommendation
and no helper call. DQ2b's captures under production's behaviour flags,
pinned rather than inherited; no model, sockets refused. Lives in bench/
because DQ2b's labels may be read only from here, and only to MEASURE: the
helper never sees them.
"""
import copy
import itertools
import os
import socket
import statistics
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

CELLS = []          # (view, job, sibling ids in track order, {sibling: score} evaluated)
_patches = []


def setUpModule():
    refuse = mock.patch.object(socket.socket, "connect",
                               side_effect=RuntimeError("DQ4 benchmark opened a socket"))
    refuse.start()
    _patches.append(refuse)
    captures = targeted.load_captures()
    on = dict(LIVE_ENV, **{make_profile.TRACK_SEARCH_FLAG: "1", make_profile.TRACK_SCORING_FLAG: "1"})
    with mock.patch.dict(os.environ, on, clear=True), tempfile.TemporaryDirectory() as empty:
        market = local_search.frozen_market()
        docs = {doc: targeted.derive(doc, captures, empty)[:2] for doc, _v, _l in targeted.documents()}
        for family, sibs in M.SIBLINGS.items():
            for layout in targeted.LAYOUTS:
                tracks = [{"id": targeted_eval.track_id(v), "engine": "v2",
                           "derived": docs[f"{v}-{layout}"][1]} for v in sibs]
                texts = [docs[f"{v}-{layout}"][0] for v in sibs]
                attached = make_profile.with_track_scoring(
                    make_profile.with_track_search(tracks, texts, market), texts, market)
                contexts = targeted_eval.contexts(make_profile.render_sweep(
                    f"dq2b {family} {layout}", attached, dict(targeted.PREFS)))
                for job in (j for j in M.JOBS if j["family"] == family):
                    row = {k: job[k] for k in ("Title", "Company", "Location", "Description")}
                    facts = scraper.job_facts(row)
                    got = {v: (scraper.evaluate(copy.deepcopy(row), c.scoring, facts),
                               scraper.title_admits(row["Title"], c.title_hints, c.title_exclude))
                           for v, c in zip(sibs, contexts)}
                    for view in ("A", "B"):
                        CELLS.append((view, job, tuple(sibs),
                                      {v: e.score for v, (e, admitted) in got.items()
                                       if e.eligible and (view == "B" or admitted)}))


def tearDownModule():
    while _patches:
        _patches.pop().stop()


def recommended(view, kind=None):
    """[(job, sibs, scores, Recommendation | None)] for one view."""
    return [(job, sibs, scores, tr.recommend(scores, [v for v in sibs if v in scores]) if scores else None)
            for v_, job, sibs, scores in CELLS if v_ == view and (kind is None or job["kind"] == kind)]


def own_specific(view):
    rows = recommended(view, "specific")
    evaluated = [(job, rec) for job, _s, scores, rec in rows if job["primary"] in scores]
    return {"cells": len(rows), "evaluated": len(evaluated),
            "included": sum(job["primary"] in rec.tracks for job, rec in evaluated),
            "wrong_only": sum(job["primary"] not in rec.tracks for job, rec in evaluated),
            "sizes": [len(rec.tracks) if rec else 0 for _j, _s, _sc, rec in rows]}


class Gates(unittest.TestCase):
    """DQ4-1's gates on the policy. Not tightened to what it measures today."""

    def test_view_a(self):
        got = own_specific("A")
        self.assertEqual((got["cells"], got["evaluated"]), (48, 40))
        self.assertGreaterEqual(got["included"], 36)
        self.assertLessEqual(got["wrong_only"], 3)

    def test_view_b(self):
        got = own_specific("B")
        self.assertEqual((got["cells"], got["evaluated"]), (48, 48))
        self.assertGreaterEqual(got["included"], 44)
        self.assertLessEqual(got["wrong_only"], 3)
        self.assertLessEqual(statistics.mean(got["sizes"]), 1.35)


class Contract(unittest.TestCase):

    def test_membership_never_depends_on_track_order(self):
        calls = 0
        for view in ("A", "B"):
            for _job, sibs, scores, rec in recommended(view):
                if not scores:
                    continue
                for order in itertools.permutations(scores):
                    again = tr.recommend(scores, order)
                    self.assertEqual((set(again.tracks), again.kind), (set(rec.tracks), rec.kind))
                    calls += 1
        self.assertGreater(calls, 0)

    def test_first_is_best_track_and_members_come_from_the_scores(self):
        for view in ("A", "B"):
            for _job, sibs, scores, rec in recommended(view):
                if not scores:
                    continue
                order = [v for v in sibs if v in scores]
                self.assertEqual(rec.tracks[0], min(order, key=lambda v: (-scores[v], order.index(v))))
                self.assertLessEqual(set(rec.tracks), set(scores))

    def test_the_track_limit_is_the_sweeps(self):
        self.assertEqual(tr.MAX_TRACKS, make_profile.MAX_TRACKS)


if __name__ == "__main__":
    unittest.main()
