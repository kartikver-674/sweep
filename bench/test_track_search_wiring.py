"""DQ2c-2 on DQ2b's documents: each 3-track Sweep searches its own résumés'
TrackSearchIntent, and nothing else moves. DQ2c-3: its closing gates.
Run: python -m unittest bench.test_track_search_wiring

DQ2b's captures replayed under production's behaviour flags, pinned rather than
inherited; no model, sockets refused. Lives in bench/ because DQ2b's fixtures
may be read only from here (test_targeted: the manifest reaches no derivation).
"""
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
import track_intent  # noqa: E402
import track_search  # noqa: E402
from bench import targeted, targeted_eval  # noqa: E402
from bench import targeted_manifest as M  # noqa: E402
from bench.test_track_search import LIVE_ENV  # noqa: E402

DOCS = {}           # doc -> (text, derived), derived under LIVE_ENV
MARKET = []
_patches = []


def setUpModule():
    refuse = mock.patch.object(socket.socket, "connect",
                               side_effect=RuntimeError("DQ2c wiring tests opened a socket"))
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


def sweep(family, layout, sibs, search):
    """(tracks, what with_track_search returned, rendered source) for one Sweep."""
    tracks = [{"id": targeted_eval.track_id(v), "engine": "v2",
               "derived": DOCS[f"{v}-{layout}"][1]} for v in sibs]
    texts = [DOCS[f"{v}-{layout}"][0] for v in sibs]
    with mock.patch.dict(os.environ, dict(LIVE_ENV, **{make_profile.TRACK_SEARCH_FLAG: search}),
                         clear=True):
        attached = make_profile.with_track_search(tracks, texts, MARKET[0])
        source = make_profile.render_sweep(f"dq2b {family} {layout}", attached,
                                           dict(targeted.PREFS))
    return tracks, attached, source


class Wiring(unittest.TestCase):

    def test_off_nothing_is_attached_and_search_is_todays(self):
        for family, layout, sibs in sweeps():
            tracks, attached, source = sweep(family, layout, sibs, "0")
            self.assertTrue(all(a is t for a, t in zip(attached, tracks)), (family, layout))
            for track, ctx in zip(tracks, targeted_eval.contexts(source)):
                self.assertEqual(list(ctx.role_keywords), track["derived"]["role_keywords"])

    def test_on_each_track_searches_its_own_pure_intent(self):
        for family, layout, sibs in sweeps():
            tracks, attached, source = sweep(family, layout, sibs, "1")
            for v, track, out, ctx in zip(sibs, tracks, attached,
                                          targeted_eval.contexts(source)):
                text, derived = DOCS[f"{v}-{layout}"]
                alone = track_search.derive_track_search(
                    text, derived, track_intent.derive_track_intent(text, derived), MARKET[0])
                self.assertEqual(out["derived"]["track_search"], alone.as_dict(), v)
                self.assertEqual(ctx.role_keywords, alone.role_keywords, v)
                self.assertIs(out["derived"]["role_keywords"], derived["role_keywords"])
                self.assertNotIn("track_search", derived, v)

    def test_the_free_title_gate_does_not_move(self):
        with mock.patch.dict(os.environ, LIVE_ENV, clear=True):
            config = make_profile._load_config()
        for family, layout, sibs in sweeps():
            _t, _a, off = sweep(family, layout, sibs, "0")
            _t, attached, on = sweep(family, layout, sibs, "1")
            for a, b in zip(targeted_eval.contexts(off), targeted_eval.contexts(on)):
                self.assertEqual((a.title_hints, a.title_exclude),
                                 (b.title_hints, b.title_exclude), (family, layout))
            for v, out in zip(sibs, attached):
                with mock.patch.dict(os.environ, LIVE_ENV, clear=True):
                    self.assertEqual(make_profile._title_gate(out["derived"], config),
                                     make_profile._title_gate(DOCS[f"{v}-{layout}"][1], config), v)

    def test_free_relevance_of_the_labelled_jobs_does_not_move(self):
        for family, layout, sibs in sweeps():
            modes = []
            for search in ("0", "1"):
                ctx = targeted_eval.contexts(sweep(family, layout, sibs, search)[2])
                modes.append([[t.id for t in ctx
                               if scraper.title_admits(job["Title"], t.title_hints,
                                                       t.title_exclude)]
                              for job in M.JOBS if job["family"] == family])
            self.assertEqual(modes[1], modes[0], (family, layout))


def dry_run(source, name):
    """[(site, keywords, [track ids])]: the Sweep's executable requests, one per
    request_key, from a dry run of the rendered profile in a fresh interpreter
    — the real planner, exactly as bench.targeted_eval plans DQ2b."""
    env = {"PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8", "PYTHONIOENCODING": "utf-8",
           "PYTHONDONTWRITEBYTECODE": "1"}
    with tempfile.TemporaryDirectory() as home:
        os.makedirs(os.path.join(home, "profiles"))
        open(os.path.join(home, "profiles", "__init__.py"), "w").close()
        with open(os.path.join(home, "profiles", f"{name}.py"), "w", encoding="utf-8") as fh:
            fh.write(source)
        got = subprocess.run([sys.executable, "-c", targeted_eval.PLAN, name, REPO_ROOT],
                             capture_output=True, text=True, cwd=home,
                             env=dict(env, HOME=home), timeout=300)
    if got.returncode:
        raise RuntimeError(f"{name} dry run failed:\n{got.stderr[-3000:]}")
    return [(site, keywords, who) for site, units in json.loads(got.stdout)["units"].items()
            for keywords, who in units]


class FinalGates(unittest.TestCase):
    """DQ2c's closing gates on DQ2b (DQ2c-3): the flag on against today, every
    Sweep planned by the real planner. Spend is gated per Sweep — no Sweep may
    buy more requests than it does today, whatever the total does."""

    @classmethod
    def setUpClass(cls):
        cls.requests = {}
        for family, layout, sibs in sweeps():
            for search in ("0", "1"):
                source = sweep(family, layout, sibs, search)[2]
                cls.requests[family, layout, search] = dry_run(source, f"dq2b_{family}_{layout}")
        cls.search = {doc: track_search.derive_track_search(
            text, derived, track_intent.derive_track_intent(text, derived), MARKET[0])
            for doc, (text, derived) in DOCS.items()}

    def test_no_sweep_buys_more_requests_than_today(self):
        for family, layout, _sibs in sweeps():
            today = len(self.requests[family, layout, "0"])
            self.assertLessEqual(len(self.requests[family, layout, "1"]), today, (family, layout))
        total = {s: sum(len(r) for (_f, _l, on), r in self.requests.items() if on == s)
                 for s in ("0", "1")}
        self.assertLessEqual(total["1"], total["0"])

    def test_siblings_search_apart_and_lead_with_their_own_request(self):
        pairs, heads, tracks = [], 0, 0
        for family, layout, sibs in sweeps():
            kws = {v: self.search[f"{v}-{layout}"].role_keywords for v in sibs}
            pairs += [len(set(kws[a]) & set(kws[b])) / len(set(kws[a]) | set(kws[b]))
                      for a, b in itertools.combinations(sibs, 2)]
            for v in sibs:
                if self.search[f"{v}-{layout}"].sufficient:
                    tracks += 1
                    own = [targeted_eval.track_id(v)]
                    heads += any(who == own and k in kws[v][:2]
                                 for _s, k, who in self.requests[family, layout, "1"])
        self.assertLessEqual(statistics.median(pairs), 0.30)
        self.assertGreaterEqual(heads, 22)
        self.assertEqual(tracks, 24)

    def test_the_specialism_leads_and_no_track_loses_its_own_jobs(self):
        leads, targeted_docs = 0, 0
        for doc, vid, _layout in targeted.documents():
            got = self.search[doc]
            if M.VARIANTS[vid]["case"] in ("control", "control_grouped") or not got.sufficient:
                continue
            targeted_docs += 1
            leads += any(M.has_phrase(k, term) for k in got.role_keywords[:2]
                         for term in M.VARIANTS[vid]["title_terms"])
            own = [j["Title"] for j in M.JOBS if j["kind"] == "specific" and j["primary"] == vid]
            found = {name: sum(any(M.has_phrase(t, k) for k in kws) for t in own)
                     for name, kws in (("today", DOCS[doc][1]["role_keywords"]),
                                       ("dq2c", got.role_keywords))}
            self.assertGreaterEqual(found["dq2c"], found["today"], doc)
        self.assertEqual(targeted_docs, 28)
        self.assertGreaterEqual(leads, 26)


if __name__ == "__main__":
    unittest.main()
