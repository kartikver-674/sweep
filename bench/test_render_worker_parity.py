"""P4-R1's transport gate on DQ2b. Run: python -m unittest bench.test_render_worker_parity

For every DQ2b Sweep (4 families x 2 layouts), the Multi-Track session Render
builds — through the product builder, the ACTUAL worker_client over loopback
and the real worker app — is exactly the file render_sweep writes for it, byte
for byte: free and paid preferences, the render-time title gate on and off,
under production's behaviour flags. A key-sorting serializer is caught. DQ2b's captures, no model; every
connection but loopback refused.
"""
import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (REPO_ROOT, os.path.join(REPO_ROOT, "auto-apply")):
    if path not in sys.path:
        sys.path.insert(0, path)

import inference  # noqa: E402
import local_search  # noqa: E402
import scraper  # noqa: E402
import title_gate  # noqa: E402
from bench import targeted, targeted_eval  # noqa: E402
from bench import targeted_manifest as M  # noqa: E402
from bench.test_track_search import LIVE_ENV  # noqa: E402
from sweep import logic, worker_client, worker_link  # noqa: E402
from sweep.tests import test_multi_render as R  # noqa: E402
from sweep.tests.test_one_track_goldens import FORMS  # noqa: E402

DOCS = {}
_patches = []


def setUpModule():
    R.setUpModule()                 # the frozen corpus, and loopback only
    _patches.append(mock.patch.object(inference, "_post",
                                      side_effect=RuntimeError("P4-R1 parity made a model call")))
    for patch in _patches:
        patch.start()
    captures = targeted.load_captures()
    with mock.patch.dict(os.environ, LIVE_ENV, clear=True), tempfile.TemporaryDirectory() as empty:
        for doc, _vid, _layout in targeted.documents():
            DOCS[doc] = targeted.derive(doc, captures, empty)[:2]


def tearDownModule():
    while _patches:
        _patches.pop().stop()
    R.tearDownModule()


def dq2b_state(sibs, layout, free=True):
    """A session holding one DQ2b Sweep's siblings, with the app's India
    default — bench.targeted.PREFS, the preferences every DQ2b render used."""
    state = {"profile": "dq2b", "tracks": [
        {"id": targeted_eval.track_id(v), "name": v, "resume_text": DOCS[f"{v}-{layout}"][0],
         "derived": json.loads(json.dumps(DOCS[f"{v}-{layout}"][1])), "engine": "v2",
         "selected": True, "reviewed": True} for v in sibs]}
    state.update(logic._configure_overrides(FORMS["india"], logic.DEFAULT_SCOPE))
    if free:
        state["free_only"] = True
        state["sites_enabled"] = {s: False for s in logic.paid_sites()}
    else:
        state["cap_usd"] = 42.0
    return state


class Parity(R.Harness):

    FLAGS = dict({k: v for k, v in LIVE_ENV.items() if k.startswith("SWEEP_")},
                 **{worker_link.MULTI_FLAG: "1"}, **R.RENDER_FLAGS)

    def setUp(self):
        super().setUp()
        # Pricing all 24 Sweeps from one session in seconds is this gate's
        # method, not a visitor's. The plan limit (P4-S1C) is pinned by
        # test_public_hardening.TestPlanLimits.
        for limit in self.app.plan_limits:
            limit.per_ip = 1000

    def worker_file(self):
        source = self.worker.engine.plans[-1]["source"]
        return source[:source.index("\n# Written by sweep_worker")]

    def test_every_dq2b_sweep_is_the_same_file_on_both_sides(self):
        room = self.room()
        cases = 0
        for family, sibs in M.SIBLINGS.items():
            for layout in targeted.LAYOUTS:
                for gate, free in (("0", True), ("1", True), ("1", False)):
                    with self.subTest(family=family, layout=layout, gate=gate, free=free):
                        os.environ[title_gate.FLAG] = gate
                        for key in [k for k in room if k != "tracks"]:
                            room.pop(key)
                        room.update(dq2b_state(sibs, layout, free))
                        self.assertEqual(self.client.get("/confirm").status_code, 200)
                        self.assertEqual(self.worker_file(), R.direct(room, "NAME"))
                        sent = self.worker.bodies("/v1/plans")[-1]
                        self.assertEqual(json.dumps(sent["tracks"]), json.dumps(
                            room[worker_link.PLANNED]["snapshot"]["tracks"]))
                        cases += 1
        self.assertEqual(cases, 24)

    def test_a_key_sorting_serializer_is_caught(self):
        family, sibs = next(iter(M.SIBLINGS.items()))
        room = self.room()
        room.update(dq2b_state(sibs, targeted.LAYOUTS[0], free=False))
        self.assertEqual(self.client.get("/confirm").status_code, 200)
        mine = room[worker_link.PLANNED]["snapshot"]["tracks"]
        sorting = types.SimpleNamespace(dumps=lambda o: json.dumps(o, sort_keys=True),
                                        loads=json.loads)
        with mock.patch.object(worker_client, "json", sorting):
            self.assertEqual(self.client.get("/confirm").status_code, 200)
        self.assertNotEqual(self.worker_file(), R.direct(room, "NAME"))
        # DQ2b's sibling tables happen to be in term order already, so here a
        # sorted wire leaves ScoringContext.key alone; test_multi_render pins
        # the key moving on a table that is not.
        sent = self.worker.bodies("/v1/plans")[-1]["tracks"]
        self.assertEqual([list(t["SCORING"]["skill_weights"]) for t in mine],
                         [sorted(t["SCORING"]["skill_weights"]) for t in mine])
        self.assertNotEqual(json.dumps(sent), json.dumps(mine))


if __name__ == "__main__":
    unittest.main()
