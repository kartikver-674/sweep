"""Multi-Track Phase 4 (P4-R1): Render's plumbing to the worker's `tracks` API.

Render is the derivation authority and the worker the execution authority.
For 2-3 selected résumés Render builds ONE snapshot from one capture of the
session — each track's engine-ready TRACKS entry (with_track_search,
with_track_scoring, render_sweep: the accepted derivation) plus the Sweep's
preferences and free_only — prices it (/v1/plans, which must attest
plan_version 2 and a plan_hash), keeps it with the worker's hash in the
session's server-side room, and runs exactly it (/v1/runs, expected_plan_hash
always). Any change to the session since the plan sends the visitor back to
Confirm; so does plan_changed, from the worker's 409 or a run's exit 4. The
run's status must be the planned Sweep's (schema, ids in order, hash), and its
rows read as the engine wrote them. One résumé is the legacy path, untouched.

Everything runs for real except provider work: the Render public app through
its own routes, the actual worker_client over loopback to the real worker app,
and the real engine's dry run (sockets refused) for every plan. No run child
starts. The environment is sealed and synthetic; tracks and jobs are too.
"""
import contextlib
import copy
import csv
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock

from flask import jsonify, request

import local_search
import scraper
import skill_concepts
import track_recommendation
from deploy import sweep_worker
from sweep import logic, public, worker_client, worker_link
from sweep.tests import test_multi_results as mr
from sweep.tests.test_one_track_goldens import FORMS, REPO, derived_for
from sweep.tests.test_worker_link import BETA_ENV, CODE, WORKER_TOKEN, cookie_of, render_app
from sweep.tests.test_worker_tracks import Engine

sys.path.insert(0, os.path.join(REPO, "auto-apply"))
import make_profile  # noqa: E402

A, B, C = mr.A, mr.B, mr.C          # the ids test_multi_results' engine rows carry
KEY = "apify_api_P4R1FAKEKEY0123456789abcdef"
STALE = "0" * 64
RENDER_FLAGS = {make_profile.TRACK_SEARCH_FLAG: "1", make_profile.TRACK_SCORING_FLAG: "1",
                make_profile.TRACK_ALIGNMENT_FLAG: "1"}
PERSONAS = {A: "ada-plain", B: "bhaskar-plain", C: "chen-plain"}
TEXTS = {
    A: "Ada Okonkwo\nBackend Engineer | Node.js\nada@example.test\n\nSummary\nBackend engineer "
       "building Node.js and Python APIs for payments teams.\n",
    B: "Bhaskar Rao\nMobile Developer | React Native\nbhaskar@example.test\n\nSummary\nMobile "
       "developer shipping React Native apps with TypeScript.\n",
    C: "Chen Wei\nData Scientist | Machine Learning\nchen@example.test\n\nSummary\nData scientist "
       "training machine learning models in Python.\n",
}
_MARKET_SAVED, _GUARD = [], []
_CONNECT = socket.socket.connect


def loopback_only():
    """Every connection refused but loopback's: Render reaches the worker on
    127.0.0.1 and nothing else is reachable at all."""
    def connect(sock, address, *a):
        if (address[0] if isinstance(address, tuple) else address) not in ("127.0.0.1", "::1"):
            raise RuntimeError("P4-R1 tests reach nothing but loopback")
        return _CONNECT(sock, address, *a)
    return mock.patch.object(socket.socket, "connect", connect)


def setUpModule():
    # The committed corpus, not whatever sweeps this machine has in output/.
    _MARKET_SAVED[:] = list(worker_link._MARKET)
    worker_link._MARKET[:] = [local_search.frozen_market()]
    _GUARD[:] = [loopback_only()]
    _GUARD[0].start()


def tearDownModule():
    worker_link._MARKET[:] = _MARKET_SAVED
    while _GUARD:
        _GUARD.pop().stop()


def multi_state(order=(A, B, C), free=True, form="india"):
    """A session holding 2-3 derived and reviewed résumés (design §D.2) and
    the Sweep's preferences — what the upload/review screens leave (P4-U1)."""
    state = {"profile": "beta_multi", "tracks": [
        {"id": tid, "name": f"Résumé for {PERSONAS[tid]}", "resume_text": TEXTS[tid],
         "derived": copy.deepcopy(derived_for(PERSONAS[tid])), "engine": "v2", "selected": True,
         "reviewed": True}
        for tid in order]}
    state.update(logic._configure_overrides(FORMS[form], logic.DEFAULT_SCOPE))
    if free:
        state["free_only"] = True
        state["sites_enabled"] = {s: False for s in logic.paid_sites()}
    return state


def direct(state, name):
    """Render's own schema-2 profile for this session: render_sweep over the
    accepted derivation, with the snapshot's preferences."""
    tracks = worker_link.selected(state)
    texts = [t["resume_text"] for t in tracks]
    market = worker_link._market()
    attached = make_profile.with_track_scoring(make_profile.with_track_search(
        [{"id": t["id"], "engine": t["engine"], "derived": t["derived"]} for t in tracks],
        texts, market), texts, market)
    return make_profile.render_sweep(name, attached, worker_link._plan_prefs(state))


class Worker:
    """The real worker app on loopback. Every dry run is the real engine
    (test_worker_tracks.Engine: sockets refused, file recorded); no run child
    starts — `spawn` records and answers with `code`. Every request is kept as
    received: path, raw body, owner."""

    def __init__(self, home):
        from werkzeug.serving import make_server
        self.checkout = os.path.join(home, "checkout")
        os.makedirs(os.path.join(self.checkout, "profiles"))
        open(os.path.join(self.checkout, "profiles", "__init__.py"), "w").close()
        self.trip = os.path.join(home, "tripwire")
        self.engine = Engine(self.trip)
        self._patch = mock.patch.object(sweep_worker, "subprocess", self.engine)
        self._patch.start()
        self.spawned, self.requests, self.code = [], [], 0
        self.store = sweep_worker.RunStore(os.path.join(home, "runs"))
        queue = sweep_worker.Queue(self.store, spawn=self.spawn, checkout=self.checkout)
        app = sweep_worker.create_app(store=self.store, queue=queue, accepted={WORKER_TOKEN},
                                      checkout=self.checkout)

        @app.before_request
        def keep():
            self.requests.append({"method": request.method, "path": request.path,
                                  "body": request.get_data(),
                                  "owner": request.headers.get("X-Sweep-Owner")})

        self._server = make_server("127.0.0.1", 0, app, threaded=True)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self._server.server_port}"

    def spawn(self, run_id, run_dir, profile_name, checkout, tokens, **kw):
        self.spawned.append({"run_id": run_id, "profile": profile_name, "tokens": tokens, **kw})
        code = self.code
        return types.SimpleNamespace(wait=lambda: code, terminate=lambda: None), None

    def bodies(self, path, method="POST"):
        return [json.loads(r["body"]) for r in self.requests
                if r["path"] == path and r["method"] == method]

    def stop(self):
        self._server.shutdown()
        self._patch.stop()


class Harness(unittest.TestCase):
    """A Render public process and a worker, both real, in a sealed env."""

    FLAGS = {worker_link.MULTI_FLAG: "1", **RENDER_FLAGS}

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="p4r1-")
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        env = mock.patch.dict(os.environ, dict(
            {"PATH": "/usr/bin:/bin", "HOME": self.home, "LANG": "en_US.UTF-8",
             "PYTHONDONTWRITEBYTECODE": "1"}, **BETA_ENV, **self.FLAGS), clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.worker = Worker(self.home)
        self.addCleanup(self.worker.stop)
        os.environ.update({worker_client.URL_ENV: self.worker.url,
                           worker_client.TOKEN_ENV: WORKER_TOKEN})
        self.app = self.render()
        self.client = self.app.test_client()
        self.client.post("/beta", data={"code": CODE})

    def render(self):
        """A Render process (a restart builds another) with two read-only
        probes of what the Results screen reads: the rows, and their parse."""
        app = render_app(self.worker.url, check_token=lambda token: (42.0, None))

        @app.get("/t/rows")
        def t_rows():
            return jsonify(worker_link._rows(public.current_run_id(), strict=True))

        @app.get("/t/parsed")
        def t_parsed():
            ids = public.current_run_tracks()[0]
            return jsonify([worker_link.multi_row(r, ids)
                            for r in worker_link._rows(public.current_run_id(), strict=True)])

        allow = mock.patch.object(public, "PUBLIC_ENDPOINTS",
                                  public.PUBLIC_ENDPOINTS | {"t_rows", "t_parsed"})
        allow.start()
        self.addCleanup(allow.stop)
        return app

    def room(self, app=None, client=None):
        """This browser's server-side session dict — made, when it has none
        yet, the way a first write makes one: reading no longer does
        (P4-S1B's lazy rooms)."""
        app, client = app or self.app, client or self.client
        client.get("/activity")
        with client.session_transaction() as sess:
            if "sid" not in sess:
                sess["sid"], sess.permanent = f"test-{id(client)}", True
            sid = sess["sid"]
        rooms = app.session_store._rooms
        if sid not in rooms:
            import time
            rooms[sid] = {"seen": time.monotonic(), "data": {}, "ip": "127.0.0.1"}
        return rooms[sid]["data"]

    def cookie(self, client=None, app=None):
        app, client = app or self.app, client or self.client
        return app.session_interface.get_signing_serializer(app).loads(cookie_of(client))

    def session(self, **kw):
        room = self.room()
        room.update(multi_state(**kw))
        return room

    def planned(self, **kw):
        room = self.session(**kw)
        answer = self.client.get("/configure")
        self.assertEqual(answer.status_code, 200, answer.get_data(as_text=True)[-400:])
        return room

    def start(self, **form):
        return self.client.post("/run", data=form)

    def settled(self, run_id):
        """The run once its (instant) fake child has finished and the
        worker's queue thread has written its last status: after this, the
        test may edit the status without racing that thread."""
        for _ in range(500):
            status = self.worker.store.read(run_id)
            if status["state"] in sweep_worker.TERMINAL:
                return status
            threading.Event().wait(0.01)
        self.fail(f"run {run_id} never settled")

    def only_run(self):
        runs = self.worker.store.all()
        self.assertEqual(len(runs), 1)
        return runs[0]

    def nothing_started(self):
        self.assertEqual((self.worker.store.all(), self.worker.spawned), ([], []))
        self.assertEqual(self.worker.bodies("/v1/runs"), [])


# ===========================================================================
class Contract(unittest.TestCase):

    def test_the_names_are_the_workers_and_the_engines(self):
        self.assertEqual((worker_client.PLAN_VERSION, worker_client.PLAN_CHANGED),
                         (sweep_worker.PLAN_VERSION, sweep_worker.PLAN_CHANGED))
        self.assertEqual(worker_client.PLAN_HASH.pattern, sweep_worker.PLAN_HASH.pattern)
        self.assertEqual(worker_link.KINDS, (track_recommendation.CLEAR, track_recommendation.CLOSE,
                                             track_recommendation.TIED, track_recommendation.SPLIT))
        self.assertEqual(worker_link.CAUTIONS, scraper.CAUTIONS)
        self.assertEqual(worker_link.MULTI_FLAG, "SWEEP_MULTI_TRACK")

    def test_the_gate_is_off_unless_said(self):
        for value, on in (("1", True), (" yes ", True), ("On", True), ("", False), ("0", False),
                          ("no", False), ("off", False)):
            self.assertIs(worker_link.multi_enabled({worker_link.MULTI_FLAG: value}), on, value)
        self.assertFalse(worker_link.multi_enabled({}))


class Dark(Harness):
    """Off, or in a session with fewer than two résumés, nothing is Multi-Track."""

    FLAGS = dict(RENDER_FLAGS)          # the product gate off

    def test_off_a_multi_session_takes_no_multi_path(self):
        room = self.session()
        room["derived"] = copy.deepcopy(derived_for("ada-plain"))     # a legacy résumé too
        self.assertEqual(self.client.get("/configure").status_code, 200)
        body, = self.worker.bodies("/v1/plans")
        self.assertEqual(sorted(body), ["free_only", "owner", "prefs", "profile"])
        self.assertNotIn(worker_link.PLANNED, room)

    def test_on_one_selected_resume_is_still_the_legacy_path(self):
        os.environ[worker_link.MULTI_FLAG] = "1"
        room = self.session(order=(A,))
        room["derived"] = copy.deepcopy(derived_for("ada-plain"))
        self.assertEqual(self.client.get("/configure").status_code, 200)
        body, = self.worker.bodies("/v1/plans")
        self.assertIn("profile", body)
        self.assertNotIn("tracks", body)


class Builder(Harness):
    """One capture, the accepted derivation, render_sweep's own entries."""

    def snapshot(self, state):
        with self.app.test_request_context():
            return worker_link.build_snapshot(state)

    def test_two_or_three_tracks_in_the_users_order(self):
        for order in ((A, B), (A, B, C), (C, A, B), (B, A)):
            with self.subTest(order=order):
                state = multi_state(order)
                snap = self.snapshot(state)
                self.assertEqual(snap["track_ids"], list(order))
                self.assertEqual([t["id"] for t in snap["tracks"]], list(order))
                self.assertEqual(snap["tracks"], worker_link._tracks_of(direct(state, "x")))
                self.assertTrue(all("POSITIONING" in t and "ALIGNMENT" in t for t in snap["tracks"]))

    def test_it_carries_no_resume_text(self):
        body = json.dumps(self.snapshot(multi_state()), ensure_ascii=False)
        for text in TEXTS.values():
            for line in text.splitlines():
                if len(line) > 25:
                    self.assertNotIn(line, body)
        self.assertNotIn("example.test", body)

    def test_tracks_and_prefs_come_from_one_capture(self):
        """A session edited while the snapshot is being built cannot give it
        tracks from one state and preferences from another."""
        room = multi_state()
        room["avoid"] = []
        real = make_profile.with_track_search

        def edit_mid_build(*a, **kw):
            room["avoid"] = ["salesforce"]            # would change every penalty_terms
            room["exclude_levels"] = ["senior"]
            return real(*a, **kw)

        with mock.patch.object(make_profile, "with_track_search", edit_mid_build):
            snap = self.snapshot(room)
        self.assertEqual((snap["prefs"]["avoid"], snap["prefs"]["exclude_levels"]),
                         ([], worker_link._prefs_of({})["exclude_levels"]))
        penalties = [t["SCORING"]["penalty_terms"] for t in snap["tracks"]]
        self.assertTrue(all(p.get("salesforce") != -make_profile.PENALTY_RANGE[1] for p in penalties))
        before = dict(room, avoid=[], exclude_levels=None)
        self.assertEqual(snap["tracks"], worker_link._tracks_of(direct(before, "x")))
        self.assertNotEqual(snap["inputs"], worker_link.inputs(room))   # and the edit is seen

    def test_an_edit_racing_the_capture_is_all_or_nothing(self):
        """Edited the instant after the capture, before anything reads it:
        the snapshot is the state as captured — its tracks AND its prefs —
        never the captured tracks with the edited preferences."""
        room = multi_state()
        room["avoid"] = []
        before = copy.deepcopy(room)
        real = worker_link.selected
        calls = []

        def edit_after_capture(state):
            if not calls:
                room["avoid"] = ["salesforce"]
                room["tracks"][0]["derived"]["skill_weights"][0]["weight"] = 1
            calls.append(1)
            return real(state)

        with mock.patch.object(worker_link, "selected", edit_after_capture):
            snap = self.snapshot(room)
        self.assertEqual(snap["prefs"], worker_link._plan_prefs(before))
        self.assertEqual(snap["tracks"], worker_link._tracks_of(direct(before, "x")))
        self.assertEqual(snap["inputs"], worker_link.inputs(before))

    def test_not_two_or_three_or_not_configured_fails_closed(self):
        for order in ((A,), ()):
            with self.subTest(order=order), self.assertRaises(worker_link.MultiTrackUnavailable):
                self.snapshot(multi_state(order) if order else {"tracks": []})
        four = multi_state()
        four["tracks"].append(dict(four["tracks"][0], id="dd" * 8))
        with self.assertRaises(worker_link.MultiTrackUnavailable):
            self.snapshot(four)
        for flag in RENDER_FLAGS:
            with self.subTest(off=flag), mock.patch.dict(os.environ, {flag: "0"}), \
                    self.assertRaises(worker_link.MultiTrackUnavailable):
                self.snapshot(multi_state())


class Transport(Harness):
    """G, H: Render's profile, through the ACTUAL worker_client, is the file
    the worker writes — byte for byte."""

    def test_the_worker_writes_renders_own_profile_byte_for_byte(self):
        for kw in ({"order": (A, B, C)}, {"order": (B, C)}, {"order": (C, B, A), "form": "remote"}):
            with self.subTest(**kw):
                self.worker.engine.plans.clear()
                room = self.planned(**kw)
                call, = self.worker.engine.plans
                source = call["source"]
                self.assertEqual(source[:source.index("\n# Written by sweep_worker")],
                                 direct(room, "NAME"))
                sent = self.worker.bodies("/v1/plans")[-1]["tracks"]
                self.assertEqual(json.dumps(sent), json.dumps(room[worker_link.PLANNED]
                                                              ["snapshot"]["tracks"]))

    def test_a_key_sorting_serializer_would_be_caught(self):
        room = self.session()
        # A table whose order is not term order, so a sorted wire moves the
        # scoring context as well as the file.
        room["tracks"][0]["derived"]["skill_weights"].reverse()
        sorting = types.SimpleNamespace(dumps=lambda o: json.dumps(o, sort_keys=True),
                                        loads=json.loads)
        with mock.patch.object(worker_client, "json", sorting):
            self.assertEqual(self.client.get("/configure").status_code, 200)
        source = self.worker.engine.plans[-1]["source"]
        self.assertNotEqual(source[:source.index("\n# Written by sweep_worker")],
                            direct(room, "NAME"))
        mine = room[worker_link.PLANNED]["snapshot"]["tracks"]
        sent = self.worker.bodies("/v1/plans")[-1]["tracks"]
        keys = lambda tracks: [scraper.track_context(t, {}).scoring.key for t in tracks]
        self.assertNotEqual(keys(sent)[0], keys(mine)[0])


class Plans(Harness):
    """K, N, 17, 30: a plan is the stored snapshot plus the worker's hash."""

    def test_a_plan_stores_the_snapshot_and_the_workers_hash(self):
        room = self.planned()
        planned = room[worker_link.PLANNED]
        body, = self.worker.bodies("/v1/plans")
        self.assertEqual(sorted(body), ["free_only", "owner", "prefs", "tracks"])
        self.assertEqual((body["tracks"], body["prefs"], body["free_only"]),
                         (planned["snapshot"]["tracks"], planned["snapshot"]["prefs"], True))
        raw = json.loads(self.worker.engine.plans[-1]["stdout"])
        self.assertEqual(planned["plan_hash"], raw["plan_hash"])
        self.assertEqual(room["raw_plan"]["plan_hash"], raw["plan_hash"])
        self.assertEqual(planned["snapshot"]["inputs"], worker_link.inputs(room))

    def test_a_plan_without_the_attestation_is_no_plan(self):
        for label, canned in (("none", {"profile": "x", "sites": {}}),
                              ("version 1", {"plan_version": 1, "plan_hash": "a" * 64, "sites": {}}),
                              ("no hash", {"plan_version": 2, "sites": {}})):
            with self.subTest(label):
                room = self.session()
                with mock.patch.object(worker_client, "_call", lambda *a, **k: dict(canned)):
                    answer = self.client.get("/configure")
                self.assertNotEqual(answer.status_code, 200)
                self.assertNotIn(worker_link.PLANNED, room)
                with self.assertRaises(worker_client.ProtocolError), \
                        mock.patch.object(worker_client, "_call", lambda *a, **k: dict(canned)), \
                        self.app.test_request_context():
                    worker_client.plan_tracks([], {})

    def test_a_failed_plan_leaves_no_earlier_approval_behind(self):
        room = self.planned()
        earlier = room[worker_link.PLANNED]
        self.assertIn(worker_link.PLANNED, room)
        with mock.patch.object(worker_client, "_call",
                               lambda *a, **k: {"plan_version": 1, "sites": {}}):
            self.assertNotEqual(self.client.get("/configure").status_code, 200)
            self.assertNotIn(worker_link.PLANNED, room)
            # T2: a run plans again itself, so it meets the same failure: nothing runs on the approval that was dropped
            self.assertNotEqual(self.start().status_code, 302)
            self.assertNotIn(worker_link.PLANNED, room)
        self.nothing_started()
        # ...and once the worker answers, the run is the new plan's, never the earlier approval
        self.assertTrue(self.start().headers["Location"].endswith("/running"))
        self.assertIsNot(room[worker_link.PLANNED], earlier)
        body, = self.worker.bodies("/v1/runs")
        self.assertEqual(body["expected_plan_hash"], room[worker_link.PLANNED]["plan_hash"])

    def test_the_worker_engine_failing_is_its_own_error(self):
        self.worker.engine.canned = (1, "")
        with self.app.test_request_context(), self.assertRaises(worker_client.EngineFailed):
            worker_client.plan_tracks(copy.deepcopy(mr.TRACK_DATA[:2]), worker_link._prefs_of({}))


class Runs(Harness):
    """L, O, P, 19, 33, 36: the run is the planned snapshot, hash and all."""

    def test_the_run_is_exactly_the_planned_snapshot_with_its_hash(self):
        room = self.planned()
        planned = copy.deepcopy(room[worker_link.PLANNED])
        answer = self.start(expected_plan_hash=STALE, plan_hash=STALE)    # the browser's word: ignored
        self.assertEqual(answer.status_code, 302)
        self.assertTrue(answer.headers["Location"].endswith("/running"))
        body, = self.worker.bodies("/v1/runs")
        self.assertEqual(sorted(body), ["expected_plan_hash", "free_only", "owner", "prefs", "tracks"])
        self.assertEqual(body["expected_plan_hash"], planned["plan_hash"])
        self.assertEqual(json.dumps(body["tracks"]), json.dumps(planned["snapshot"]["tracks"]))
        self.assertEqual(body["prefs"], dict(planned["snapshot"]["prefs"],
                                             max_spend_usd=room["max_spend_usd"],
                                             allow_partial_paid_sweep=None))
        self.assertIs(body["free_only"], True)                       # free: the hash all the same
        status = self.only_run()
        self.assertEqual((status["schema"], status["track_ids"], status["plan_hash"]),
                         (2, [A, B, C], planned["plan_hash"]))
        cookie = self.cookie()
        self.assertEqual(cookie["run_tracks"], [[t["id"], t["name"]] for t in room["tracks"]])
        self.assertEqual((cookie["run_id"], cookie["run_plan_hash"]),
                         (status["run_id"], planned["plan_hash"]))
        self.assertEqual(room[worker_link.PLANNED]["run_id"], status["run_id"])

    def test_no_run_without_a_stored_plan_but_the_one_it_makes(self):
        """T2: a run with no approval plans the session itself, from what it holds, and runs THAT. A plan the session was handed
        (forged, or left by a restart) is never what runs: it is replaced by the worker's own."""
        room = self.session()
        forged = room["plan"] = {"total": 0, "lines": [], "spend_cap": 0.0, "coverage": None}  # a forged plan
        answer = self.start()
        self.assertTrue(answer.headers["Location"].endswith("/running"))
        planned = room[worker_link.PLANNED]
        self.assertEqual(len(self.worker.bodies("/v1/plans")), 1)
        self.assertNotEqual(room["plan"], forged)                          # the worker's plan, not the forged one
        self.assertEqual(room["raw_plan"]["plan_hash"], planned["plan_hash"])
        body, = self.worker.bodies("/v1/runs")
        self.assertEqual(body["expected_plan_hash"], planned["plan_hash"])
        self.assertEqual(json.dumps(body["tracks"]), json.dumps(planned["snapshot"]["tracks"]))

    def test_an_approval_runs_once(self):
        room = self.planned()
        first = room[worker_link.PLANNED]
        self.start()
        self.settled(self.only_run()["run_id"])
        self.assertIn("run_id", first)                                  # spent
        plans = len(self.worker.bodies("/v1/plans"))
        answer = self.start()
        # T2: not refused back to a screen of its own: the spent approval is never run again, a new one is made and runs
        self.assertTrue(answer.headers["Location"].endswith("/running"))
        self.assertEqual(len(self.worker.bodies("/v1/plans")), plans + 1)
        self.assertIsNot(room[worker_link.PLANNED], first)
        first_run, second_run = self.worker.bodies("/v1/runs")
        self.assertEqual(second_run["expected_plan_hash"], room[worker_link.PLANNED]["plan_hash"])
        self.assertNotEqual(self.worker.store.all()[0]["run_id"], self.worker.store.all()[-1]["run_id"])


class Edits(Harness):
    """M, 11, 12, 27, 35: an edited session is a new Sweep to plan."""

    EDITS = {
        "résumé text": lambda s: s["tracks"][0].update(resume_text=s["tracks"][0]["resume_text"] + "x"),
        "a skill weight": lambda s: s["tracks"][1]["derived"]["skill_weights"][0].update(weight=1),
        "track order": lambda s: s["tracks"].reverse(),
        "selection": lambda s: s["tracks"][2].update(selected=False),
        "engine": lambda s: s["tracks"][0].update(engine="v1"),
        "avoid list": lambda s: s.update(avoid=["php"]),
        "exclude levels": lambda s: s.update(exclude_levels=["senior"]),
        "max age": lambda s: s.update(max_age_days=3),
        "sources": lambda s: s.update(sites_enabled={"linkedin": False}),
    }

    def test_every_edit_after_the_plan_is_planned_again_and_the_run_is_that_plan(self):
        """T2: an edited session is a new Sweep to plan, and /run plans it itself before it starts anything (it used to refuse the
        run back to Confirm). What runs is the plan made from the session as it now stands: the new snapshot, the worker's hash
        for it, never the approval the edit outdated."""
        for label, edit in self.EDITS.items():
            with self.subTest(edit=label):
                self.setUp()
                room = self.planned()
                before = copy.deepcopy(room[worker_link.PLANNED])
                plans = len(self.worker.bodies("/v1/plans"))
                edit(room)
                self.assertNotEqual(before["snapshot"]["inputs"], worker_link.inputs(room))
                answer = self.start()
                self.assertTrue(answer.headers["Location"].endswith("/running"), label)
                self.assertEqual(len(self.worker.bodies("/v1/plans")), plans + 1, label)       # planned again, not run from memory
                now = room[worker_link.PLANNED]
                self.assertEqual(now["snapshot"]["inputs"], worker_link.inputs(room), label)     # from exactly what the session holds
                self.assertNotEqual(now["snapshot"]["inputs"], before["snapshot"]["inputs"], label)
                self.assertNotIn(worker_link.REPLAN, room)
                body, = self.worker.bodies("/v1/runs")
                self.assertEqual(body["expected_plan_hash"], now["plan_hash"], label)
                self.assertEqual(json.dumps(body["tracks"]), json.dumps(now["snapshot"]["tracks"]), label)
                self.assertEqual(self.worker.bodies("/v1/plans")[-1]["tracks"], body["tracks"], label)

    def test_free_or_paid_is_part_of_the_planned_sweep(self):
        room = multi_state()
        self.assertNotEqual(worker_link.inputs(room), worker_link.inputs(dict(room, free_only=False)))
        self.assertEqual(worker_link.inputs(room),
                         worker_link.inputs(dict(room, max_spend_usd=3.0,
                                                 allow_partial_paid_sweep=True)))

    def test_an_edit_the_provider_plan_cannot_see_still_needs_a_new_plan(self):
        """Same provider units, same plan_hash — and still never A's approval."""
        room = self.planned()
        approval_a = room[worker_link.PLANNED]
        hash_a = approval_a["plan_hash"]
        tracks_a = copy.deepcopy(room[worker_link.PLANNED]["snapshot"]["tracks"])
        room["tracks"][1]["derived"]["skill_weights"][0]["weight"] = 1     # scoring only
        with self.app.test_request_context():
            edited = worker_link.build_snapshot(room)
            same_hash = worker_client.plan_tracks(edited["tracks"], edited["prefs"],
                                                  free_only=True, owner="probe")["plan_hash"]
        self.assertEqual(same_hash, hash_a)                     # the provider plan did not move
        self.assertNotEqual(edited["tracks"], tracks_a)         # the Sweep did
        # T2: the run plans it again and is the edited Sweep, not approval A (whose hash it shares)
        plans = len(self.worker.bodies("/v1/plans"))
        self.assertTrue(self.start().headers["Location"].endswith("/running"))
        self.assertEqual(len(self.worker.bodies("/v1/plans")), plans + 1)
        self.assertIsNot(room[worker_link.PLANNED], approval_a)
        body, = self.worker.bodies("/v1/runs")
        self.assertEqual(body["tracks"], edited["tracks"])
        self.assertNotEqual(body["tracks"], tracks_a)

    def test_no_edit_runs_the_planned_snapshot_unchanged(self):
        room = self.planned()
        tracks = copy.deepcopy(room[worker_link.PLANNED]["snapshot"]["tracks"])
        with mock.patch.object(make_profile, "render_sweep",
                               side_effect=AssertionError("a run must not re-derive")):
            self.start()
        body, = self.worker.bodies("/v1/runs")
        self.assertEqual(json.dumps(body["tracks"]), json.dumps(tracks))


class PlanChanged(Harness):
    """Q, R: plan_changed, from the worker's 409 or a run's exit 4, is Confirm."""

    def test_the_workers_409_returns_the_visitor_to_confirm(self):
        room = self.planned()
        room[worker_link.PLANNED]["plan_hash"] = "e" * 64      # the worker's plan moved on
        answer = self.start()
        self.assertTrue(answer.headers["Location"].endswith("/confirm"))
        self.assertNotIn(worker_link.PLANNED, room)
        self.assertIs(room[worker_link.REPLAN], True)
        self.assertEqual(self.worker.store.all(), [])          # refused by its preflight
        self.assertEqual(self.worker.spawned, [])
        self.assertEqual(self.client.get("/running").headers["Location"][-8:], "/confirm")

    def test_an_exit_4_returns_the_visitor_to_confirm_and_a_new_plan_holds(self):
        room = self.planned()
        self.worker.code = sweep_worker.PLAN_CHANGED_EXIT
        self.start()
        status = self.only_run()
        self.assertEqual(self.settled(status["run_id"])["error"], "plan_changed")
        self.assertEqual(self.client.get("/progress").status_code, 200)
        self.assertIs(room[worker_link.REPLAN], True)
        self.assertNotIn(worker_link.PLANNED, room)
        for path in ("/running", "/results"):
            self.assertTrue(self.client.get(path).headers["Location"].endswith("/confirm"), path)
        self.client.get("/configure")                              # planned again
        self.assertNotIn(worker_link.REPLAN, room)
        self.client.get("/activity")                             # the strip still reads the old run
        self.client.get("/progress")
        self.assertIn(worker_link.PLANNED, room)                 # ...and leaves the new plan be
        self.worker.code = 0
        self.start()
        self.assertEqual(len(self.worker.bodies("/v1/runs")), 2)


class Status(Harness):
    """S, T: a multi run's status must be the planned Sweep's, in order."""

    TAMPER = {"track order": {"track_ids": [C, B, A]}, "a track": {"track_ids": [A, B]},
              "hash": {"plan_hash": "f" * 64}, "schema": {"schema": 1}}

    def test_a_status_that_is_not_the_planned_sweep_fails_closed(self):
        for label, change in self.TAMPER.items():
            with self.subTest(tamper=label):
                room = self.planned()
                self.start()
                run_id = self.cookie()["run_id"]
                self.settled(run_id)
                self.worker.store.update(run_id, state="running", **change)
                self.assertEqual(self.client.get("/progress").status_code, 200)
                self.assertEqual(room["proc"]._code, 1)                  # terminal, not "retry"
                self.assertEqual(self.client.get("/results").status_code, 502)
                self.assertEqual(self.client.get("/t/rows").status_code, 502)
                self.worker.store.update(run_id, state="done")

    def test_a_one_track_status_is_never_checked(self):
        self.client.post("/resume", data={"resume": (__import__("io").BytesIO(b"%PDF-1.7 x"),
                                                     "cv.pdf")}, content_type="multipart/form-data")
        self.client.post("/derive")
        self.client.post("/review", data={"name": "beta_user"})
        self.client.post("/key/free")
        self.client.get("/configure")
        self.client.post("/run")
        run_id = self.cookie()["run_id"]
        self.assertNotIn("run_tracks", self.cookie())
        self.settled(run_id)
        self.worker.store.update(run_id, schema=1, track_ids=["nonsense"])   # irrelevant to it
        self.assertEqual(self.client.get("/t/rows").status_code, 200)


class Rows(Harness):
    """U-AB, AE: rows exactly as the engine wrote them, parsed strictly."""

    FLAGS = dict(Harness.FLAGS, **{skill_concepts.VERSION_ENV: "v1"})

    def setUp(self):
        super().setUp()
        bound = skill_concepts._BOUND
        self.addCleanup(setattr, skill_concepts, "_BOUND", bound)
        skill_concepts.bind(None)
        patch = mock.patch.dict(scraper.SETTINGS, mr.FILTERS)
        patch.start()
        self.addCleanup(patch.stop)
        self.planned()
        self.start()
        self.run_id = self.cookie()["run_id"]

    def serve(self, recommend=True, caution=True, rows=None):
        out = self.worker.store.output_dir(self.run_id)
        engine_rows = rows if rows is not None else scraper.finalize_multi(
            mr.focus_jobs(), mr.focus_contexts(), recommend=recommend, caution=caution)
        cols = scraper.multi_output_columns(recommend, caution)
        with mock.patch.dict(scraper.SETTINGS, {"output_dir": out}):
            scraper.write_outputs(engine_rows, os.path.join(out, "jobs_2026-09-28_1200.csv"),
                                  os.path.join(out, "jobs_2026-09-28_1200.json"), cols)
        with open(os.path.join(out, "jobs_2026-09-28_1200.csv"), newline="",
                  encoding="utf-8-sig") as fh:
            return engine_rows, list(csv.DictReader(fh))

    def test_every_engine_field_arrives_as_written(self):
        engine_rows, written = self.serve()
        rows = self.client.get("/t/rows").get_json()
        self.assertEqual(rows, written)
        parsed = self.client.get("/t/parsed").get_json()
        self.assertEqual({p["recommendation"] for p in parsed}, set(worker_link.KINDS))
        for want, got in zip(engine_rows, parsed):
            self.assertEqual(got["best_track"], want["best_track"])
            self.assertEqual(got["track_evals"], json.loads(want["track_evals"]))
            self.assertEqual(";".join(got["found_by"]), want["found_by"])
            self.assertEqual(";".join(got["recommended_tracks"]), want["recommended_tracks"])
            self.assertEqual(got["recommendation"], want["recommendation"])
            self.assertEqual(got["recommendation_caution"], want["recommendation_caution"])

    def test_caution_absent_empty_and_coded_stay_three_things(self):
        self.serve(caution=False)
        absent = self.client.get("/t/parsed").get_json()
        self.assertTrue(all("recommendation_caution" not in p for p in absent))
        self.assertTrue(all("recommendation_caution" not in r
                            for r in self.client.get("/t/rows").get_json()))
        self.serve()
        cautions = {p["recommendation_caution"] for p in self.client.get("/t/parsed").get_json()}
        self.assertEqual(cautions, {"", scraper.NO_FOCUS_EVIDENCE})
        self.serve(recommend=False, caution=False)
        bare = self.client.get("/t/parsed").get_json()
        self.assertTrue(all(set(p) == {"best_track", "track_evals", "found_by"} for p in bare))

    def test_a_row_the_engine_cannot_have_written_is_refused(self):
        _engine, written = self.serve()
        good = written[0]
        broken = {
            "track_evals not JSON": dict(good, track_evals="{nope"),
            "track_evals a list": dict(good, track_evals="[]"),
            "an unknown track": dict(good, best_track="ee" * 8),
            "a score that is text": dict(good, track_evals=json.dumps(
                {k: {"s": str(v["s"]), "m": v["m"]} for k, v in json.loads(good["track_evals"]).items()})),
            "found_by empty": dict(good, found_by=""),
            "a kind the engine has not": dict(good, recommendation="suggested"),
            "a caution the engine has not": dict(good, recommendation_caution="weak"),
            "recommended not led by best_track": dict(good, recommended_tracks=";".join(
                reversed(good["recommended_tracks"].split(";")))) if ";" in good["recommended_tracks"]
            else dict(good, recommended_tracks="ee" * 8),
            "a caution without a recommendation": {k: v for k, v in good.items()
                                                   if k not in ("recommendation", "recommended_tracks")},
        }
        ids = [A, B, C]
        for label, row in broken.items():
            with self.subTest(row=label), self.assertRaises(worker_client.ProtocolError):
                worker_link.multi_row(row, ids)
        self.serve(rows=[dict(scraper.finalize_multi(mr.focus_jobs(), mr.focus_contexts(),
                                                     recommend=True, caution=True)[0],
                              recommendation="suggested")])
        self.assertEqual(self.client.get("/t/rows").status_code, 502)
        self.assertEqual(self.client.get("/results").status_code, 502)

    def test_nothing_reads_the_row_key_order(self):
        _engine, written = self.serve()
        for row in written:
            self.assertEqual(worker_link.multi_row(dict(reversed(list(row.items()))), [A, B, C]),
                             worker_link.multi_row(row, [A, B, C]))
        served = self.client.get("/t/rows").get_json()
        self.assertEqual(list(served[0]), sorted(served[0]))   # jsonify's order, not the CSV's


class Privacy(Harness):
    """I, AC, 38: the engine-ready tracks never reach the browser."""

    def test_no_page_json_or_cookie_carries_a_track(self):
        room = self.planned()
        tracks = room[worker_link.PLANNED]["snapshot"]["tracks"]
        private = {"skill_weights", "penalty_terms", "POSITIONING", "ALIGNMENT", "ATS_TITLE_HINTS",
                   WORKER_TOKEN, "example.test"}
        for t in tracks:
            private |= set(t["POSITIONING"]["concepts"]) | set(t["ALIGNMENT"]["role_titles"])
            private |= {term for term in t["SCORING"]["skill_weights"] if len(term) > 6}
        self.start()
        pages = [self.client.get(p) for p in ("/confirm", "/running", "/progress", "/activity",
                                              "/results", "/export.json", "/export.csv", "/configure")]
        for page in pages:
            text = page.get_data(as_text=True)
            leaked = sorted(p for p in private if p in text)
            self.assertEqual(leaked, [], page.request.path)
        cookie = self.cookie()
        self.assertLessEqual(set(cookie), {"sid", "beta_grant", "run_id", "run_tracks",
                                           "run_plan_hash", "_permanent"})
        self.assertEqual([tid for tid, _label in cookie["run_tracks"]], [A, B, C])
        self.assertFalse(any(p in json.dumps(cookie, ensure_ascii=False) for p in private))


class Reload(Harness):
    """AF, 41: a reload, and a Render restart, reconnect to the right run."""

    def test_a_reload_keeps_the_snapshot_and_its_run(self):
        room = self.planned()
        self.start()
        run_id = self.cookie()["run_id"]
        for _ in range(2):
            self.assertIn(self.client.get("/running").status_code, (200, 302))
        self.assertEqual(room[worker_link.PLANNED]["run_id"], run_id)
        self.assertEqual(self.cookie()["run_plan_hash"], room[worker_link.PLANNED]["plan_hash"])

    def test_a_restart_reconnects_by_the_cookie_and_checks_the_run(self):
        self.planned()
        self.start()
        run_id = self.cookie()["run_id"]
        self.settled(run_id)
        self.worker.store.update(run_id, state="running")
        second = self.render()
        returning = second.test_client()
        returning.set_cookie("session", cookie_of(self.client), domain="localhost")
        self.assertEqual(returning.get("/running").status_code, 200)
        room = self.room(second, returning)
        self.assertEqual(room["proc"].run_id, run_id)
        self.assertEqual(returning.get("/progress").status_code, 200)
        self.assertIsNone(room["proc"]._code)                          # still its run, running
        self.worker.store.update(run_id, track_ids=[B, A, C])                # not the planned Sweep
        third = self.render()
        again = third.test_client()
        again.set_cookie("session", cookie_of(self.client), domain="localhost")
        again.get("/running")
        self.assertNotIn("proc", self.room(third, again))


class Paid(Harness):
    """49: owner, key ids and the visitor's key, as the legacy paid run has them."""

    def test_a_paid_multi_run_is_funded_exactly_as_a_legacy_one(self):
        room = self.session(free=False)
        self.assertEqual(self.client.post("/key", data={"token": KEY}).status_code, 302)
        self.assertEqual(self.client.get("/configure").status_code, 200)
        plan = room["plan"]
        self.assertTrue(any(not line["free"] for line in plan["lines"]))
        self.start(over_cap_ack="1")
        body, = self.worker.bodies("/v1/runs")
        self.assertEqual(body["key_ids"], plan["coverage"]["funding_ids"])
        self.assertNotIn("apify_token", body)
        self.assertIs(body["free_only"], False)
        self.assertEqual(body["expected_plan_hash"], room[worker_link.PLANNED]["plan_hash"])
        owners = {r["owner"] for r in self.worker.requests}
        self.assertEqual(len(owners), 1)
        spawned, = self.worker.spawned
        self.assertEqual((spawned["tokens"], spawned["plan_hash"]),
                         ([KEY], room[worker_link.PLANNED]["plan_hash"]))
        self.assertNotIn(KEY, json.dumps(self.cookie()))
        for path in ("/running", "/confirm", "/progress"):
            self.assertNotIn(KEY, self.client.get(path).get_data(as_text=True))


class PlanCache(Harness):
    """P4-S1C with the shipped cache and status windows on: Confirm reuses an
    UNUSED, un-invalidated approval for the same snapshot inputs; any edit,
    a used approval or plan_changed asks the worker again; POST /run still
    runs only the approved plan, bound to its hash and re-checked by the
    worker's preflight; and what the connected accounts cover is worked out
    afresh on every visit."""

    def setUp(self):
        from sweep import app as app_module
        from sweep.tests import PRODUCTION
        for patch in (mock.patch.object(app_module, "PLAN_CACHE_SECONDS",
                                        PRODUCTION["plan_cache_seconds"]),
                      mock.patch.object(worker_link, "STATUS_TTL", PRODUCTION["status_ttl"])):
            patch.start()
            self.addCleanup(patch.stop)
        worker_link._ASKED.clear()
        super().setUp()
        # These tests are about reuse, not the plan limit (TestPlanLimits).
        for limit in self.app.plan_limits:
            limit.per_ip = 1000

    def plans(self):
        return len(self.worker.bodies("/v1/plans"))

    def test_an_unchanged_setup_is_planned_once(self):
        room = self.planned()
        approval = copy.deepcopy(room[worker_link.PLANNED])
        for _ in range(3):
            self.assertEqual(self.client.get("/configure").status_code, 200)
        self.assertEqual(self.plans(), 1)
        self.assertEqual(room[worker_link.PLANNED]["plan_hash"], approval["plan_hash"])

    def test_every_snapshot_edit_is_planned_again(self):
        for label, edit in Edits.EDITS.items():
            with self.subTest(edit=label):
                room = self.planned()
                before = self.plans()
                edit(room)
                self.client.get("/configure")
                self.assertEqual(self.plans(), before + 1, label)

    def test_a_used_approval_is_planned_again_and_run_is_bound_to_its_hash(self):
        room = self.planned()
        self.client.get("/configure")
        planned = copy.deepcopy(room[worker_link.PLANNED])
        self.start()
        body, = self.worker.bodies("/v1/runs")
        self.assertEqual(body["expected_plan_hash"], planned["plan_hash"])
        status = self.settled(self.only_run()["run_id"])
        self.assertEqual(status["plan_hash"], planned["plan_hash"])   # the worker's preflight
        before = self.plans()
        self.client.get("/configure")
        self.assertEqual(self.plans(), before + 1, "a used approval was reused")

    def test_plan_changed_still_sends_the_visitor_back_with_the_windows_on(self):
        room = self.planned()
        self.worker.code = sweep_worker.PLAN_CHANGED_EXIT
        self.start()
        self.assertEqual(self.settled(self.only_run()["run_id"])["error"], "plan_changed")
        worker_link._ASKED.clear()          # the window a browser's next poll would wait out
        self.assertEqual(self.client.get("/progress").status_code, 200)   # reads the status
        self.assertTrue(self.client.get("/running").headers["Location"].endswith("/confirm"))
        self.assertNotIn(worker_link.PLANNED, room)
        before = self.plans()
        self.client.get("/configure")
        self.assertEqual(self.plans(), before + 1)

    def test_the_accounts_are_counted_afresh_even_from_a_reused_plan(self):
        room = self.session(order=(A,), free=False)
        room["derived"] = copy.deepcopy(derived_for(PERSONAS[A]))
        for key in (KEY, KEY + "2"):
            self.assertEqual(self.client.post("/key", data={"token": key}).status_code, 302)
        self.client.get("/configure")
        first, second = [k["id"] for k in room["byok_keys"]]
        # This engine plans "single": the one account with the most room funds
        # it, the first added on a tie.
        self.assertEqual(room["plan"]["coverage"]["funding_ids"], [first])
        self.client.post("/key/forget", data={"key": first})
        self.assertEqual(self.client.get("/configure").status_code, 200)
        self.assertEqual(self.plans(), 1, "the unchanged plan was not reused")
        self.assertEqual(room["plan"]["coverage"]["funding_ids"], [second])


class RunQuota(Harness):
    """P4-S1B: a Sweep is ONE run of SWEEP_DAILY_RUNS_* whatever it searches —
    one résumé or three, free or paid — and the wire is exactly as before."""

    FLAGS = {**Harness.FLAGS, public.RUNS_PER_IP_ENV: "2"}

    def launch(self, order, free=True):
        room = self.session(order=order, free=free)
        room.pop("derived", None)
        if len(order) == 1:
            room["derived"] = copy.deepcopy(derived_for(PERSONAS[order[0]]))
        if not free:
            self.assertEqual(self.client.post("/key", data={"token": KEY}).status_code, 302)
        self.assertEqual(self.client.get("/configure").status_code, 200)
        return self.start(**({} if free else {"over_cap_ack": "1"}))

    def test_one_two_or_three_resumes_free_or_paid_are_each_one_run(self):
        for order, free, wire in (((A, B), True, "tracks"), ((A, B, C), True, "tracks"),
                                  ((A, B), False, "tracks"), ((A,), True, "profile"),
                                  ((A,), False, "profile")):
            with self.subTest(tracks=len(order), free=free):
                self.app.run_limit = public.DailyLimit(5, 150)
                answer = self.launch(order, free)
                self.assertTrue(answer.headers["Location"].endswith("/running"),
                                answer.get_data(as_text=True)[-300:])
                body = self.worker.bodies("/v1/runs")[-1]
                self.assertEqual(("tracks" in body, "profile" in body),
                                 (wire == "tracks", wire == "profile"))
                if wire == "tracks":
                    self.assertEqual([t["id"] for t in body["tracks"]], list(order))
                self.assertIs(body["free_only"], free)
                self.assertEqual(self.app.run_limit.taken(), 1)
                self.settled(self.cookie()["run_id"])

    def test_the_per_ip_limit_refuses_the_third_before_the_worker(self):
        for _ in range(2):
            self.launch((A, B))
            self.settled(self.cookie()["run_id"])
        room = self.session(order=(A,))
        room["derived"] = copy.deepcopy(derived_for(PERSONAS[A]))
        self.assertEqual(self.client.get("/configure").status_code, 200)
        plans, runs = len(self.worker.bodies("/v1/plans")), len(self.worker.bodies("/v1/runs"))
        answer = self.start()
        self.assertEqual(answer.status_code, 429)
        self.assertEqual((len(self.worker.bodies("/v1/plans")), len(self.worker.bodies("/v1/runs"))),
                         (plans, runs), "a refused Sweep was planned or sent")
        self.assertEqual(self.app.run_limit.taken(), 2)


if __name__ == "__main__":
    unittest.main()
