"""What the sweep worker must guarantee before it is put on Oracle.

The worker starts processes that spend a visitor's money, on the same box
as the inference fallback. So these tests are about the boundaries rather
than the happy path: whose run is whose, where a credential is allowed to
exist, whether structured data can become code, and what a restart does
to work that was in flight.

No real sweep runs here. `spawn` is injected, because what is under test
is the worker's bookkeeping, not scraper.py.
"""

import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
for path in (REPO_ROOT, os.path.join(REPO_ROOT, "auto-apply")):
    if path not in sys.path:
        sys.path.insert(0, path)

from deploy import sweep_worker  # noqa: E402

TOKEN = "worker-token"
APIFY = "apify_live_SECRETVALUE_0123456789"

# A derived profile, the shape make_profile.render() takes.
PROFILE = {
    "candidate_name": "Ada Okonkwo",
    "field_summary": "React Native developer, about 4 years.",
    "years_experience": 4,
    "role_keywords": ["react native developer", "mobile engineer"],
    "skill_weights": [{"term": "react native", "weight": 4},
                      {"term": "typescript", "weight": 3}],
    "penalty_terms": [{"term": "salesforce", "weight": 5}],
    "domain_half_a": [], "domain_half_b": [], "domain_title_terms": [],
    "domain_bonus": 0, "notes": "",
}
PREFS = {
    "locations": ["Remote"],
    "exclude_levels": ["intern", "fresher"],
    "avoid": [], "min_comp_usd": None, "max_spend_usd": None,
    "remote_scopes": None, "max_age_days": None, "max_results": None,
    "linkedin_locations": None, "linkedin_remote_only": None,
    "sites_enabled": None,
}


class FakeChild:
    """A scraper.py that does nothing, on demand."""

    def __init__(self, code=0, block=None):
        self.code, self.block = code, block
        self.terminated = False
        self.env = None

    def wait(self):
        if self.block:
            self.block.wait(5)
        return self.code

    def terminate(self):
        self.terminated = True
        if self.block:
            self.block.set()


class Harness(unittest.TestCase):
    """A worker with a temp runs directory and a temp checkout."""

    def setUp(self):
        self.runs = tempfile.mkdtemp(prefix="runs-")
        self.checkout = tempfile.mkdtemp(prefix="checkout-")
        os.makedirs(os.path.join(self.checkout, "profiles"), exist_ok=True)
        self.addCleanup(shutil.rmtree, self.runs, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.checkout, ignore_errors=True)
        self.spawned = []
        self.now = [1_000.0]

    def spawn(self, code=0, block=None):
        def spawner(run_id, run_dir, profile_name, checkout, token):
            child = FakeChild(code, block)
            self.spawned.append({"run_id": run_id, "profile": profile_name,
                                 "token": token, "dir": run_dir})
            return child, None
        return spawner

    def build(self, spawner=None, max_active=1, max_waiting=None):
        store = sweep_worker.RunStore(self.runs)
        queue = sweep_worker.Queue(store, spawn=spawner or self.spawn(),
                                   checkout=self.checkout,
                                   clock=lambda: self.now[0],
                                   max_active=max_active, max_waiting=max_waiting)
        app = sweep_worker.create_app(store=store, queue=queue,
                                      accepted={TOKEN},
                                      checkout=self.checkout,
                                      clock=lambda: self.now[0])
        app.config["TESTING"] = True
        return app, store, queue

    def post_run(self, client, owner="session-a", free_only=True,
                 apify_token=None, profile=None, prefs=None):
        body = {"profile": profile if profile is not None else PROFILE,
                "prefs": prefs if prefs is not None else PREFS,
                "free_only": free_only, "owner": owner}
        if apify_token:
            body["apify_token"] = apify_token
        return client.post("/v1/runs", json=body,
                           headers={"Authorization": f"Bearer {TOKEN}"})

    def auth(self, owner="session-a"):
        return {"Authorization": f"Bearer {TOKEN}", "X-Sweep-Owner": owner}


class TestBearerAuth(Harness):
    """Every endpoint. Only Render calls this, and an unauthenticated
    route is a route somebody else can map."""

    def test_every_endpoint_refuses_without_the_token(self):
        app, _store, _queue = self.build()
        client = app.test_client()
        run = self.post_run(client).get_json()["run_id"]
        for method, path in (("get", "/healthz"),
                             ("post", "/v1/runs"),
                             ("get", f"/v1/runs/{run}"),
                             ("get", f"/v1/runs/{run}/rows"),
                             ("post", f"/v1/runs/{run}/stop")):
            with self.subTest(path=path):
                bare = getattr(client, method)(path)
                self.assertEqual(bare.status_code, 401)
                wrong = getattr(client, method)(
                    path, headers={"Authorization": "Bearer nope"})
                self.assertEqual(wrong.status_code, 401)

    def test_a_worker_with_no_token_configured_refuses_to_start(self):
        with self.assertRaises(SystemExit):
            sweep_worker.accepted_tokens({})

    def test_a_worker_with_an_unusable_checkout_refuses_to_start(self):
        """Found by a real two-process smoke: a checkout missing
        auto-apply/ let the worker boot and then 500 on the first run."""
        bare = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, bare, ignore_errors=True)
        with self.assertRaises(SystemExit) as caught:
            sweep_worker.check_checkout(bare)
        self.assertIn("make_profile", str(caught.exception))

        # A checkout carrying the renderer but with nowhere to write a
        # profile is refused too.
        os.makedirs(os.path.join(bare, "auto-apply"), exist_ok=True)
        open(os.path.join(bare, "auto-apply", "make_profile.py"), "w").close()
        with self.assertRaises(SystemExit) as caught:
            sweep_worker.check_checkout(bare)
        self.assertIn("profiles", str(caught.exception))
        # The real repo satisfies both.
        self.assertEqual(sweep_worker.check_checkout(REPO_ROOT), REPO_ROOT)


class TestOwnership(Harness):
    """Render is the only caller, but the worker does not take its word
    for whose run is whose."""

    def test_one_session_cannot_read_or_stop_anothers_run(self):
        app, _store, _queue = self.build()
        client = app.test_client()
        mine = self.post_run(client, owner="session-a").get_json()["run_id"]

        for method, path in (("get", f"/v1/runs/{mine}"),
                             ("get", f"/v1/runs/{mine}/rows"),
                             ("post", f"/v1/runs/{mine}/stop")):
            with self.subTest(path=path):
                stranger = getattr(client, method)(
                    path, headers=self.auth("session-b"))
                # 404, not 403: a refusal that confirms the id exists is
                # itself a disclosure.
                self.assertEqual(stranger.status_code, 404)
        # ... and the run is untouched by the attempt.
        self.assertEqual(
            client.get(f"/v1/runs/{mine}",
                       headers=self.auth("session-a")).status_code, 200)

    def test_a_run_id_alone_is_not_authority(self):
        app, _store, _queue = self.build()
        client = app.test_client()
        run = self.post_run(client).get_json()["run_id"]
        no_owner = client.get(f"/v1/runs/{run}",
                              headers={"Authorization": f"Bearer {TOKEN}"})
        self.assertEqual(no_owner.status_code, 404)

    def test_the_owner_string_is_never_handed_back(self):
        app, _store, _queue = self.build()
        client = app.test_client()
        run = self.post_run(client, owner="session-a").get_json()["run_id"]
        body = client.get(f"/v1/runs/{run}", headers=self.auth()).get_json()
        self.assertNotIn("owner", body)


class TestTheApifyToken(Harness):
    """A visitor's credential. It exists to reach one child process."""

    def test_it_reaches_the_child_and_nothing_else(self):
        app, store, _queue = self.build()
        client = app.test_client()
        run = self.post_run(client, free_only=False,
                            apify_token=APIFY).get_json()["run_id"]
        # The child got it...
        self.assertEqual(self.spawned[0]["token"], [APIFY])
        # ... and nothing on disk has it.
        for root in (self.runs, self.checkout):
            for dirpath, _dirs, files in os.walk(root):
                for name in files:
                    with open(os.path.join(dirpath, name), "rb") as fh:
                        self.assertNotIn(APIFY.encode(), fh.read(),
                                         f"{os.path.join(dirpath, name)}")
        # ... nor does the status the API hands back.
        body = client.get(f"/v1/runs/{run}", headers=self.auth()).get_json()
        self.assertNotIn(APIFY, json.dumps(body))
        self.assertNotIn(APIFY, json.dumps(store.read(run)))

    def test_it_is_dropped_from_memory_once_the_child_has_it(self):
        app, _store, queue = self.build()
        client = app.test_client()
        run = self.post_run(client, free_only=False,
                            apify_token=APIFY).get_json()["run_id"]
        self.assertNotIn(run, queue._tokens)
        self.assertNotIn(APIFY, json.dumps(list(queue._tokens.values())))

    def test_it_is_never_in_a_log_line(self):
        import logging
        records = []


        class Sink(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage() % () if not record.args
                               else record.getMessage())

        logger = sweep_worker.log
        handler = Sink()
        logger.addHandler(handler)
        previous = logger.level
        logger.setLevel(logging.INFO)
        self.addCleanup(logger.setLevel, previous)
        self.addCleanup(logger.removeHandler, handler)
        app, _store, _queue = self.build()
        self.post_run(app.test_client(), free_only=False, apify_token=APIFY)
        self.assertTrue(records, "the worker logged nothing at all")
        self.assertNotIn(APIFY, " ".join(records))

    def test_a_free_run_renders_every_paid_board_switched_off(self):
        """Found in production: the engine only asks for a token when a
        paid plan exists, so a free run with the boards left on died in
        seconds asking for a credential it must never hold."""
        app, _store, _queue = self.build()
        run = self.post_run(app.test_client()).get_json()["run_id"]
        source = open(os.path.join(self.runs, run, "profile.py"),
                      encoding="utf-8").read()
        for site in sweep_worker.paid_sites(REPO_ROOT):
            self.assertRegex(source, rf'"{site}": {{[^}}]*"enabled": False',
                             f"{site} is still enabled on a free run")

    def test_it_does_not_take_the_callers_word_for_that(self):
        app, _store, _queue = self.build()
        greedy = dict(PREFS, sites_enabled={s: True for s
                                            in sweep_worker.paid_sites(REPO_ROOT)})
        run = self.post_run(app.test_client(), prefs=greedy
                            ).get_json()["run_id"]
        source = open(os.path.join(self.runs, run, "profile.py"),
                      encoding="utf-8").read()
        # The free FEEDS are enabled and should be; it is the billed
        # boards that must come out off however they were asked for.
        for site in sweep_worker.paid_sites(REPO_ROOT):
            self.assertRegex(source, rf'"{site}": {{[^}}]*"enabled": False',
                             f"the caller talked {site} back on")

    def test_the_paid_sites_come_from_the_live_config(self):
        self.assertTrue(set(sweep_worker.paid_sites(REPO_ROOT))
                        >= {"linkedin", "indeed", "naukri"})

    def test_a_free_sweep_may_not_carry_one(self):
        app, _store, _queue = self.build()
        r = self.post_run(app.test_client(), free_only=True, apify_token=APIFY)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.spawned, [])

    def test_a_paid_sweep_with_no_key_held_is_refused_not_borrowed(self):
        """Never the operator's key: a paid run is funded by whoever asked
        for it or it does not happen."""
        app, _store, _queue = self.build()
        r = self.post_run(app.test_client(), free_only=False)
        self.assertEqual(r.status_code, 409)
        self.assertIn("no Apify key is held", r.get_json()["error"]["message"])
        self.assertEqual(self.spawned, [])

    def test_a_held_key_reaches_that_visitors_child_and_no_other(self):
        app, _store, queue = self.build()
        client = app.test_client()
        auth = {"Authorization": f"Bearer {TOKEN}"}
        held = client.post("/v1/tokens", json={"owner": "ada",
                                               "apify_token": APIFY},
                           headers=auth)
        self.assertEqual(held.status_code, 201)

        # Somebody else's run does not get it.
        refused = self.post_run(client, owner="ben", free_only=False)
        self.assertEqual(refused.status_code, 409)
        # Ada's does.
        ok = self.post_run(client, owner="ada", free_only=False)
        self.assertEqual(ok.status_code, 201)
        self.assertEqual(self.spawned[-1]["token"], [APIFY])
        # And it is spent: a second run needs it pasted again.
        self.assertIsNone(queue.held_token("ada"))
        self.assertEqual(self.post_run(client, owner="ada",
                                       free_only=False).status_code, 409)

    def test_a_held_key_is_written_nowhere_and_logged_nowhere(self):
        import logging
        records = []

        class Sink(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        logger = sweep_worker.log
        handler = Sink()
        logger.addHandler(handler)
        previous = logger.level
        logger.setLevel(logging.INFO)
        self.addCleanup(logger.setLevel, previous)
        self.addCleanup(logger.removeHandler, handler)

        app, _store, _queue = self.build()
        client = app.test_client()
        client.post("/v1/tokens", json={"owner": "ada", "apify_token": APIFY},
                    headers={"Authorization": f"Bearer {TOKEN}"})
        self.post_run(client, owner="ada", free_only=False)

        self.assertNotIn(APIFY, " ".join(records))
        for root in (self.runs, self.checkout):
            for dirpath, _dirs, files in os.walk(root):
                for name in files:
                    with open(os.path.join(dirpath, name), "rb") as fh:
                        self.assertNotIn(APIFY.encode(), fh.read(),
                                         os.path.join(dirpath, name))

    def test_a_key_held_for_too_long_is_forgotten(self):
        app, _store, queue = self.build()
        client = app.test_client()
        client.post("/v1/tokens", json={"owner": "ada", "apify_token": APIFY},
                    headers={"Authorization": f"Bearer {TOKEN}"})
        self.assertEqual(queue.held_token("ada"), APIFY)
        self.now[0] += sweep_worker.HOLD_SECONDS + 1
        self.assertIsNone(queue.held_token("ada"))

    def test_a_restart_drops_every_held_key(self):
        """It was never written down, which is the point: a queued paid run
        is interrupted and its owner asked again."""
        app, _store, queue = self.build()
        client = app.test_client()
        client.post("/v1/tokens", json={"owner": "ada", "apify_token": APIFY},
                    headers={"Authorization": f"Bearer {TOKEN}"})
        after = sweep_worker.Queue(sweep_worker.RunStore(self.runs),
                                   spawn=self.spawn(),
                                   checkout=self.checkout,
                                   clock=lambda: self.now[0])
        after.recover()
        self.assertIsNone(after.held_token("ada"))

    def test_the_child_environment_is_scrubbed_of_the_operators_keys(self):
        """default_spawn builds the env; a free run must not inherit an
        APIFY_TOKEN that happens to be set on the box."""
        from unittest import mock
        captured = {}

        class FakePopen:
            def __init__(self, argv, cwd=None, env=None, stdout=None,
                         stderr=None):
                captured["argv"], captured["env"] = argv, env

        run_dir = os.path.join(self.runs, "abc")
        os.makedirs(run_dir, exist_ok=True)
        with mock.patch.dict(os.environ, {"APIFY_TOKEN": "OPERATOR-KEY",
                                          "APIFY_TOKEN_2": "OPERATOR-TWO"}):
            with mock.patch.object(sweep_worker.subprocess, "Popen", FakePopen):
                _child, closer = sweep_worker.default_spawn(
                    "abc", run_dir, "beta_abc", self.checkout, None)
            if closer:
                closer.close()
        self.assertNotIn("APIFY_TOKEN", captured["env"])
        self.assertNotIn("APIFY_TOKEN_2", captured["env"])
        # ... and a token never rides on the command line, where
        # /proc/<pid>/cmdline would publish it to every user on the box.
        self.assertNotIn("APIFY_TOKEN", " ".join(captured["argv"]))


class TestNoArbitraryPython(Harness):
    """Structured data in, literals out — proven, not assumed."""

    def test_a_term_that_looks_like_code_stays_a_string(self):
        app, store, _queue = self.build()
        client = app.test_client()
        nasty = "'); import os; os.system('touch /tmp/pwned'); ('"
        profile = dict(PROFILE, skill_weights=[{"term": nasty, "weight": 3}])
        run = self.post_run(client, profile=profile).get_json()["run_id"]
        source = open(os.path.join(self.runs, run, "profile.py"),
                      encoding="utf-8").read()
        # It appears ONLY as a quoted literal — repr() is what makes the
        # difference between data and code here.
        self.assertIn(repr(nasty.strip().lower()), source)
        sweep_worker.assert_only_literals(source)
        # ... and running the module defines a dict, nothing else.
        namespace = {}
        exec(compile(source, "profile.py", "exec"), namespace)  # noqa: S102
        self.assertIn(nasty.strip().lower(), namespace["SCORING"]["skill_weights"])
        self.assertFalse(os.path.exists("/tmp/pwned"))

    def test_the_literal_check_refuses_anything_that_is_not_data(self):
        for source in ('import os\n',
                       'X = os.system("id")\n',
                       'X = [i for i in range(3)]\n',
                       'def f():\n    pass\n',
                       'X = f"{1+1}"\n',
                       'SETTINGS["output_dir"] = os.getcwd()\n'):
            with self.subTest(source=source.strip()[:28]):
                with self.assertRaises(sweep_worker.Refused):
                    sweep_worker.assert_only_literals(source)

    def test_it_accepts_the_shape_the_renderer_actually_produces(self):
        app, _store, _queue = self.build()
        run = self.post_run(app.test_client()).get_json()["run_id"]
        source = open(os.path.join(self.runs, run, "profile.py"),
                      encoding="utf-8").read()
        self.assertIn("SETTINGS[\"output_dir\"]", source.replace("'", '"'))

    def test_a_malformed_body_never_reaches_the_renderer(self):
        app, _store, _queue = self.build()
        client = app.test_client()
        for body in ({"profile": "not a dict", "owner": "s"},
                     {"profile": PROFILE, "prefs": [], "owner": "s"},
                     {"profile": PROFILE, "owner": ""},
                     {"profile": PROFILE, "owner": "s", "surprise": 1},
                     {"profile": {}, "prefs": PREFS, "owner": "s"}):
            with self.subTest(body=sorted(body)):
                r = client.post("/v1/runs", json=body,
                                headers={"Authorization": f"Bearer {TOKEN}"})
                self.assertEqual(r.status_code, 400)
        self.assertEqual(self.spawned, [])

    def test_the_run_id_cannot_walk_out_of_the_runs_directory(self):
        app, store, _queue = self.build()
        client = app.test_client()
        for bad in ("../../etc", "..%2f..", "beta_x", "NOTHEX"):
            with self.subTest(bad):
                r = client.get(f"/v1/runs/{bad}", headers=self.auth())
                self.assertIn(r.status_code, (404, 308))
        with self.assertRaises(sweep_worker.Refused):
            store.dir("../escape")


class TestTheQueue(Harness):
    """One at a time, in the order they arrived."""

    def test_concurrent_submissions_give_one_running_and_a_fifo_queue(self):
        gate = threading.Event()
        app, store, queue = self.build(spawner=self.spawn(block=gate))
        client = app.test_client()
        ids = [self.post_run(client, owner=f"s{i}").get_json()["run_id"]
               for i in range(4)]

        states = [client.get(f"/v1/runs/{r}",
                             headers=self.auth(f"s{i}")).get_json()
                  for i, r in enumerate(ids)]
        self.assertEqual([s["state"] for s in states],
                         [sweep_worker.RUNNING] + [sweep_worker.QUEUED] * 3)
        self.assertEqual([s["queue_position"] for s in states], [0, 1, 2, 3])
        self.assertEqual(len(self.spawned), 1, "more than one sweep started")

        # The first finishes; the next in line starts, and only that one.
        gate.set()
        for _ in range(50):
            if len(self.spawned) > 1:
                break
            time.sleep(0.05)
        self.assertEqual(self.spawned[1]["run_id"], ids[1],
                         "the queue did not run in arrival order")

    def test_stopping_a_queued_run_takes_it_out_of_the_line(self):
        gate = threading.Event()
        app, store, queue = self.build(spawner=self.spawn(block=gate))
        client = app.test_client()
        first = self.post_run(client, owner="s0").get_json()["run_id"]
        second = self.post_run(client, owner="s1").get_json()["run_id"]
        client.post(f"/v1/runs/{second}/stop", headers=self.auth("s1"))
        self.assertEqual(store.read(second)["state"], sweep_worker.STOPPED)
        gate.set()
        self.assertEqual(len(self.spawned), 1)
        self.assertEqual(self.spawned[0]["run_id"], first)


class TestTheQueueCap(Harness):
    """P4-S1B: at most SWEEP_MAX_QUEUED_RUNS wait behind the active run. A
    run with no place is 503 queue_full before any of it exists, and a held
    key is not spent on it."""

    def fill(self, client, waiting):
        """One active run and `waiting` behind it, from other visitors."""
        return [self.post_run(client, owner=f"filler-{i}") for i in range(1 + waiting)]

    def files(self):
        return (sorted(os.listdir(self.runs)),
                sorted(os.listdir(os.path.join(self.checkout, "profiles"))))

    def test_ten_wait_behind_the_active_run_and_the_eleventh_waiting_is_refused(self):
        gate = threading.Event()
        self.addCleanup(gate.set)
        app, store, queue = self.build(spawner=self.spawn(block=gate))
        self.assertEqual(queue.max_waiting, sweep_worker.DEFAULT_MAX_QUEUED)
        client = app.test_client()
        answers = self.fill(client, 10)
        self.assertEqual({a.status_code for a in answers}, {201})
        self.assertEqual(queue.active(), (1, 10))
        before = self.files()
        refused = self.post_run(client, owner="one-too-many")
        self.assertEqual(refused.status_code, 503)
        self.assertEqual(refused.get_json(), {"error": {"message": sweep_worker.QUEUE_FULL}})
        self.assertEqual(self.files(), before, "a refused run left something behind")
        self.assertEqual((queue.active(), len(store.all())), ((1, 10), 11))

    def test_a_run_that_can_start_at_once_needs_no_waiting_place(self):
        gate = threading.Event()
        self.addCleanup(gate.set)
        app, _store, queue = self.build(spawner=self.spawn(block=gate), max_waiting=0)
        client = app.test_client()
        self.assertEqual(self.post_run(client, owner="a").status_code, 201)
        self.assertEqual(self.post_run(client, owner="b").status_code, 503)
        self.assertEqual(queue.active(), (1, 0))

    def test_concurrent_submissions_cannot_pass_the_cap(self):
        gate = threading.Event()
        self.addCleanup(gate.set)
        app, store, queue = self.build(spawner=self.spawn(block=gate), max_waiting=3)
        begin, codes, lock = threading.Event(), [], threading.Lock()

        def submit(n):
            begin.wait(5)
            code = self.post_run(app.test_client(), owner=f"racer-{n}").status_code
            with lock:
                codes.append(code)

        threads = [threading.Thread(target=submit, args=(n,)) for n in range(20)]
        for t in threads:
            t.start()
        begin.set()
        for t in threads:
            t.join(10)
        self.assertEqual((codes.count(201), codes.count(503)), (4, 16), codes)
        self.assertEqual((queue.active(), len(store.all())), ((1, 3), 4))
        self.assertEqual(queue._pending, 0)

    def test_a_full_queue_spends_no_held_key(self):
        gate = threading.Event()
        self.addCleanup(gate.set)
        app, store, queue = self.build(spawner=self.spawn(block=gate), max_waiting=1)
        client = app.test_client()
        held = client.post("/v1/tokens", json={"owner": "payer", "apify_token": APIFY},
                           headers=self.auth("payer")).get_json()["key_id"]
        self.fill(client, 1)
        paid = {"profile": PROFILE, "prefs": PREFS, "free_only": False,
                "owner": "payer", "key_ids": [held]}
        refused = client.post("/v1/runs", json=paid, headers=self.auth("payer"))
        self.assertEqual(refused.status_code, 503)
        self.assertEqual(queue.held_tokens("payer", [held]), [APIFY],
                         "the key was spent on a run that was never made")
        gate.set()
        for _ in range(200):
            if queue.active() == (0, 0):
                break
            time.sleep(0.02)
        accepted = client.post("/v1/runs", json=paid, headers=self.auth("payer"))
        self.assertEqual(accepted.status_code, 201)
        self.assertIsNone(queue.held_tokens("payer"), "used once, as before")

    def test_a_multi_track_sweep_meets_the_same_line(self):
        gate = threading.Event()
        self.addCleanup(gate.set)
        app, _store, _queue = self.build(spawner=self.spawn(block=gate), max_waiting=0)
        client = app.test_client()
        self.fill(client, 0)
        before = self.files()
        body = {"tracks": [{"id": "a" * 16}, {"id": "b" * 16}], "prefs": PREFS,
                "free_only": True, "owner": "multi"}
        refused = client.post("/v1/runs", json=body, headers=self.auth("multi"))
        self.assertEqual(refused.status_code, 503)
        self.assertEqual(refused.get_json()["error"]["message"], sweep_worker.QUEUE_FULL)
        self.assertEqual(self.files(), before)

    def test_plans_are_not_behind_the_line(self):
        gate = threading.Event()
        self.addCleanup(gate.set)
        app, _store, _queue = self.build(spawner=self.spawn(block=gate), max_waiting=0)
        client = app.test_client()
        self.fill(client, 0)
        done = mock.Mock(returncode=0, stdout=json.dumps({"sites": {}}))
        with mock.patch.object(sweep_worker.subprocess, "run", return_value=done):
            r = client.post("/v1/plans", json={"profile": PROFILE, "prefs": PREFS,
                                               "free_only": True, "owner": "planner"},
                            headers=self.auth("planner"))
        self.assertEqual(r.status_code, 200)

    def test_health_reports_the_line_behind_the_bearer(self):
        gate = threading.Event()
        self.addCleanup(gate.set)
        app, _store, _queue = self.build(spawner=self.spawn(block=gate), max_waiting=4)
        client = app.test_client()
        self.fill(client, 2)
        self.assertEqual(client.get("/healthz").status_code, 401)
        body = client.get("/healthz", headers=self.auth()).get_json()
        self.assertEqual((body["active_runs"], body["queued_runs"], body["queue_limit"]),
                         (1, 2, 4))

    def test_the_limit_comes_from_the_environment(self):
        self.assertEqual(sweep_worker.max_queued({}), 10)
        self.assertEqual(sweep_worker.max_queued({sweep_worker.QUEUE_ENV: " 3 "}), 3)
        self.assertEqual(sweep_worker.max_queued({sweep_worker.QUEUE_ENV: "-4"}), 0)
        with self.assertRaises(SystemExit):
            sweep_worker.max_queued({sweep_worker.QUEUE_ENV: "ten"})
        with mock.patch.dict(os.environ, {sweep_worker.QUEUE_ENV: "7"}):
            self.assertEqual(sweep_worker.Queue(sweep_worker.RunStore(self.runs)).max_waiting, 7)

    def test_a_refusal_logs_no_token(self):
        import logging
        gate = threading.Event()
        self.addCleanup(gate.set)
        app, _store, _queue = self.build(spawner=self.spawn(block=gate), max_waiting=0)
        client = app.test_client()
        self.fill(client, 0)
        with self.assertLogs("sweep-worker", logging.INFO) as caught:
            self.assertEqual(self.post_run(client, owner="payer-owner", free_only=False,
                                           apify_token=APIFY).status_code, 503)
        lines = [r.getMessage() for r in caught.records]
        self.assertIn(f"run refused: {sweep_worker.QUEUE_FULL}", lines)
        self.assertFalse(any(APIFY in line or "payer-owner" in line for line in lines))


SECRET_BEARER = "super-secret-test-value"


class TestTheBearerStaysInTheWorker(Harness):
    """P4-S1C: no engine child — a legacy run, a legacy dry run, or a
    Multi-Track one — is handed the token Render uses to reach this worker.
    Everything else the engine reads from the environment still arrives."""

    KEEP = {"SWEEP_RESULTS_READY_EARLY": "1", "SWEEP_PAID_CONCURRENCY": "1",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin")}

    def test_a_legacy_run_child_lacks_the_bearer_and_keeps_its_flags(self):
        captured = {}

        class FakePopen:
            def __init__(self, argv, cwd=None, env=None, stdout=None, stderr=None,
                         stdin=None):
                captured["env"] = env

        run_dir = os.path.join(self.runs, "abc")
        os.makedirs(run_dir, exist_ok=True)
        with mock.patch.dict(os.environ, {sweep_worker.TOKEN_ENV: SECRET_BEARER, **self.KEEP}), \
                mock.patch.object(sweep_worker.subprocess, "Popen", FakePopen):
            _child, closer = sweep_worker.default_spawn("abc", run_dir, "beta_abc",
                                                        self.checkout, None)
            if closer:
                closer.close()
        env = captured["env"]
        self.assertNotIn(sweep_worker.TOKEN_ENV, env)
        self.assertNotIn(SECRET_BEARER, json.dumps(env))
        for name, value in self.KEEP.items():
            self.assertEqual(env[name], value)
        self.assertEqual((env["JOB_PROFILE"], env["SWEEP_RUN_ID"]), ("beta_abc", "abc"))

    def test_a_legacy_dry_run_lacks_the_bearer_and_keeps_its_flags(self):
        seen = {}

        def run(argv, **kw):
            seen.update(kw["env"])
            return mock.Mock(returncode=0, stdout=json.dumps({"sites": {}}))

        app, _store, _queue = self.build()
        with mock.patch.dict(os.environ, {sweep_worker.TOKEN_ENV: SECRET_BEARER, **self.KEEP}), \
                mock.patch.object(sweep_worker.subprocess, "run", run):
            r = app.test_client().post("/v1/plans", json={
                "profile": PROFILE, "prefs": PREFS, "free_only": True, "owner": "p"},
                headers=self.auth("p"))
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(sweep_worker.TOKEN_ENV, seen)
        for name, value in self.KEEP.items():
            self.assertEqual(seen[name], value)

    def test_a_multi_track_child_still_lacks_it(self):
        with mock.patch.dict(os.environ, {sweep_worker.TOKEN_ENV: SECRET_BEARER}):
            self.assertNotIn(sweep_worker.TOKEN_ENV, sweep_worker.multi_env())

    def test_the_worker_itself_still_checks_the_bearer(self):
        with mock.patch.dict(os.environ, {sweep_worker.TOKEN_ENV: SECRET_BEARER}):
            self.assertEqual(sweep_worker.accepted_tokens(), {SECRET_BEARER})
        app, _store, _queue = self.build()
        client = app.test_client()
        self.assertEqual(client.get("/healthz").status_code, 401)
        self.assertEqual(client.get("/healthz", headers=self.auth()).status_code, 200)


class TestMalformedJson(Harness):
    """P4-S1C: a body nested past the recursion limit is a 400, not a 500."""

    DEEP = b"[" * 200_000 + b"]" * 200_000

    def test_deep_or_broken_json_is_refused_on_every_route(self):
        app, store, _queue = self.build()
        app.config.update(TESTING=False, PROPAGATE_EXCEPTIONS=False)
        client = app.test_client()
        for path in ("/v1/runs", "/v1/plans", "/v1/tokens"):
            for body in (self.DEEP, b"{not json", b'{"a": ' * 5000 + b"1" + b"}" * 5000):
                with self.subTest(path=path, body=body[:12]):
                    r = client.post(path, data=body, headers={
                        **self.auth(), "Content-Type": "application/json"})
                    self.assertEqual(r.status_code, 400)
                    self.assertIn("error", r.get_json())
                    self.assertNotIn(b"Traceback", r.data)
        self.assertEqual(store.all(), [])

    def test_the_body_cap_is_still_413(self):
        app, _store, _queue = self.build()
        r = app.test_client().post("/v1/runs", data=b"[" + b" " * (600 * 1024) + b"]",
                                   headers={**self.auth(), "Content-Type": "application/json"})
        self.assertEqual(r.status_code, 413)


class TestPlanOrder(Harness):
    def test_a_plan_keeps_the_engines_site_order(self):
        """Render reads the plan's order as the run order (the running grid,
        the partial prefix), so the reply must not alphabetise it."""
        done = mock.Mock(returncode=0, stdout=json.dumps(
            {"sites": {"linkedin": [], "indeed": [], "naukri": []}}))
        app, _store, _queue = self.build()
        with mock.patch.object(sweep_worker.subprocess, "run", return_value=done):
            r = app.test_client().post("/v1/plans", json={
                "profile": PROFILE, "prefs": PREFS, "free_only": True, "owner": "p"},
                headers=self.auth("p"))
        self.assertEqual(list(r.get_json()["sites"]), ["linkedin", "indeed", "naukri"])


class ClockedChild:
    """A child that runs until it is terminated — or, with `stubborn`, until
    it is killed."""

    def __init__(self, stubborn=False):
        self.stubborn, self.done = stubborn, threading.Event()
        self.terminated = self.killed = False

    def wait(self):
        self.done.wait(10)
        return -15 if self.terminated and not self.stubborn else -9

    def terminate(self):
        self.terminated = True
        if not self.stubborn:
            self.done.set()

    def kill(self):
        self.killed = True
        self.done.set()


class TestTheRunClock(Harness):
    """P4-S1C: an engine child that outlives SWEEP_RUN_TIMEOUT_SECONDS fails
    with run_timeout, is terminated (killed if it will not go), frees the one
    slot, and the next run starts. It is never re-queued."""

    def build_clocked(self, stubborn=False, timeout=0.3, grace=0.3):
        children = []

        def spawner(run_id, run_dir, profile_name, checkout, token):
            children.append(ClockedChild(stubborn and not children))
            self.spawned.append({"run_id": run_id, "token": token})
            return children[-1], None

        store = sweep_worker.RunStore(self.runs)
        queue = sweep_worker.Queue(store, spawn=spawner, checkout=self.checkout,
                                   timeout=timeout, kill_grace=grace)
        app = sweep_worker.create_app(store=store, queue=queue, accepted={TOKEN},
                                      checkout=self.checkout)
        app.config["TESTING"] = True
        return app, store, queue, children

    def wait_for(self, check, seconds=5):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if check():
                return True
            time.sleep(0.02)
        return False

    def test_a_run_past_its_clock_fails_and_the_next_one_starts(self):
        app, store, queue, children = self.build_clocked()
        client = app.test_client()
        first = self.post_run(client, owner="a").get_json()["run_id"]
        second = self.post_run(client, owner="b").get_json()["run_id"]
        self.assertEqual(queue.active(), (1, 1))
        self.assertTrue(self.wait_for(lambda: len(children) == 2), "the next run never started")
        status = store.read(first)
        self.assertEqual((status["state"], status["error"]),
                         (sweep_worker.FAILED, sweep_worker.RUN_TIMEOUT))
        self.assertTrue(children[0].terminated)
        self.assertIsNotNone(status["finished_at"])
        self.assertTrue(self.wait_for(lambda: store.read(first).get("exit_code") == -15))
        self.assertEqual(store.read(second)["state"], sweep_worker.RUNNING)
        self.assertNotIn(first, queue._waiting, "a timed-out run was queued again")
        children[1].terminate()

    def test_a_child_that_ignores_terminate_is_killed(self):
        app, store, queue, children = self.build_clocked(stubborn=True)
        client = app.test_client()
        first = self.post_run(client, owner="a").get_json()["run_id"]
        self.post_run(client, owner="b")
        self.assertTrue(self.wait_for(lambda: children[0].killed), "never killed")
        self.assertTrue(self.wait_for(lambda: len(children) == 2))
        self.assertEqual(store.read(first)["error"], sweep_worker.RUN_TIMEOUT)
        children[1].terminate()

    def test_a_paid_run_that_times_out_is_not_retried_and_keeps_its_record(self):
        app, store, queue, children = self.build_clocked()
        client = app.test_client()
        run_id = self.post_run(client, owner="payer", free_only=False,
                               apify_token=APIFY).get_json()["run_id"]
        out = store.output_dir(run_id)
        with open(os.path.join(out, sweep_worker.AUTH_RECORD), "w") as fh:
            json.dump({"outcome": "full", "executed_paid_units": 3}, fh)
        self.assertTrue(self.wait_for(
            lambda: store.read(run_id)["state"] == sweep_worker.FAILED))
        self.assertEqual(len(self.spawned), 1, "the provider work was started twice")
        self.assertEqual((queue._tokens, queue.held_tokens("payer")), ({}, None))
        status = client.get(f"/v1/runs/{run_id}", headers=self.auth("payer")).get_json()
        self.assertEqual(status["error"], sweep_worker.RUN_TIMEOUT)
        self.assertEqual(status["paid_authorization"]["executed_paid_units"], 3)
        self.assertNotIn(APIFY, json.dumps(status))
        recovered = sweep_worker.Queue(store, spawn=self.spawn(), checkout=self.checkout)
        recovered.recover()
        self.assertEqual(recovered.active(), (0, 0), "a restart re-queued it")

    def test_a_stopped_run_is_not_rewritten_by_the_clock(self):
        app, store, queue, children = self.build_clocked(timeout=0.4)
        client = app.test_client()
        run_id = self.post_run(client, owner="a").get_json()["run_id"]
        client.post(f"/v1/runs/{run_id}/stop", headers=self.auth("a"))
        time.sleep(0.6)
        self.assertEqual(store.read(run_id)["state"], sweep_worker.STOPPED)

    def test_a_run_inside_its_clock_is_left_alone(self):
        app, store, _queue, children = self.build_clocked(timeout=30)
        run_id = self.post_run(app.test_client(), owner="a").get_json()["run_id"]
        time.sleep(0.3)
        self.assertEqual(store.read(run_id)["state"], sweep_worker.RUNNING)
        self.assertFalse(children[0].terminated)
        children[0].terminate()

    def test_the_clock_logs_no_token(self):
        app, store, _queue, children = self.build_clocked()
        with self.assertLogs("sweep-worker", "INFO") as caught:
            self.post_run(app.test_client(), owner="payer-owner", free_only=False,
                          apify_token=APIFY)
            self.assertTrue(self.wait_for(lambda: children and children[0].terminated))
        lines = [r.getMessage() for r in caught.records]
        self.assertTrue(any(sweep_worker.RUN_TIMEOUT in line for line in lines))
        self.assertFalse(any(APIFY in line or "payer-owner" in line for line in lines))

    def test_the_limit_comes_from_the_environment(self):
        self.assertEqual(sweep_worker.run_timeout({}), 2 * 60 * 60)
        self.assertEqual(sweep_worker.run_timeout({sweep_worker.RUN_TIMEOUT_ENV: "5400"}), 5400)
        self.assertEqual(sweep_worker.run_timeout({sweep_worker.RUN_TIMEOUT_ENV: "5"}), 60)
        self.assertEqual(sweep_worker.run_timeout({sweep_worker.RUN_TIMEOUT_ENV: "0"}), 60)
        with self.assertRaises(SystemExit):
            sweep_worker.run_timeout({sweep_worker.RUN_TIMEOUT_ENV: "2h"})
        app, _store, queue = self.build()
        body = app.test_client().get("/healthz", headers=self.auth()).get_json()
        self.assertEqual(body["run_timeout_seconds"], queue.timeout)


class TestRowsAreParsedOnce(Harness):
    """P4-S1C: Render walks a run's rows a page at a time; the file is parsed
    once per version of it, not once per page."""

    def test_pages_share_one_parse_and_a_rewrite_is_read_again(self):
        out = os.path.join(self.runs, "parsed", "output")
        os.makedirs(out)
        path = os.path.join(out, "jobs_2026-09-28_0000.csv")

        def write(n, tag):
            with open(path, "w", newline="") as fh:
                fh.write("title,company\n" + "".join(f"{tag}{i},Acme\n" for i in range(n)))

        write(1200, "a")
        real, calls = sweep_worker.csv.DictReader, []

        def counting(*a, **kw):
            calls.append(1)
            return real(*a, **kw)

        with mock.patch.object(sweep_worker.csv, "DictReader", counting):
            pages = [sweep_worker.rows_since(out, since) for since in (0, 500, 1000)]
            self.assertEqual(len(calls), 1)
            self.assertEqual([len(rows) for rows, _total in pages], [500, 500, 200])
            self.assertEqual([r["title"] for r in pages[1][0][:2]], ["a500", "a501"])
            write(1300, "b")
            os.utime(path, ns=(time.time_ns() + 10**9,) * 2)
            rows, total = sweep_worker.rows_since(out, 0)
        self.assertEqual((len(calls), total, rows[0]["title"]), (2, 1300, "b0"))


class TestRestart(Harness):
    """A worker restart is normal. Losing somebody's sweep silently is not."""

    def test_queued_work_and_finished_results_survive(self):
        gate = threading.Event()
        app, store, _queue = self.build(spawner=self.spawn(block=gate))
        client = app.test_client()
        running = self.post_run(client, owner="s0").get_json()["run_id"]
        queued = self.post_run(client, owner="s1").get_json()["run_id"]

        # A second worker over the same directory: the restart.
        store2 = sweep_worker.RunStore(self.runs)
        queue2 = sweep_worker.Queue(store2, spawn=self.spawn(),
                                    checkout=self.checkout,
                                    clock=lambda: self.now[0])
        queue2.recover()

        self.assertEqual(store2.read(queued)["state"], sweep_worker.RUNNING,
                         "the queued run was not picked up after restart")
        after = store2.read(running)
        self.assertEqual(after["state"], sweep_worker.INTERRUPTED)
        self.assertIn("restarted", after["error"])
        gate.set()

    def test_a_paid_run_queued_at_restart_is_interrupted_not_retried(self):
        """Its token was deliberately never written down, so it cannot be
        started again on the visitor's behalf — and must never reach for
        anybody else's."""
        gate = threading.Event()
        app, store, _queue = self.build(spawner=self.spawn(block=gate))
        client = app.test_client()
        self.post_run(client, owner="s0").get_json()["run_id"]
        paid = self.post_run(client, owner="s1", free_only=False,
                             apify_token=APIFY).get_json()["run_id"]

        queue2 = sweep_worker.Queue(sweep_worker.RunStore(self.runs),
                                    spawn=self.spawn(),
                                    checkout=self.checkout,
                                    clock=lambda: self.now[0])
        queue2.recover()
        after = sweep_worker.RunStore(self.runs).read(paid)
        self.assertEqual(after["state"], sweep_worker.INTERRUPTED)
        self.assertIn("token is never kept", after["error"])
        gate.set()

    def test_a_completed_run_keeps_its_result_metadata(self):
        app, store, _queue = self.build()
        client = app.test_client()
        run = self.post_run(client).get_json()["run_id"]
        for _ in range(50):
            if store.read(run)["state"] in sweep_worker.TERMINAL:
                break
            time.sleep(0.05)
        before = store.read(run)
        self.assertEqual(before["state"], sweep_worker.DONE)

        queue2 = sweep_worker.Queue(sweep_worker.RunStore(self.runs),
                                    spawn=self.spawn(),
                                    checkout=self.checkout,
                                    clock=lambda: self.now[0])
        queue2.recover()
        self.assertEqual(sweep_worker.RunStore(self.runs).read(run), before)


class TestCleanup(Harness):
    """48 hours, and never something somebody is watching."""

    def test_it_deletes_only_what_is_past_its_ttl(self):
        app, store, queue = self.build()
        client = app.test_client()
        old = self.post_run(client).get_json()["run_id"]
        for _ in range(50):
            if store.read(old)["state"] in sweep_worker.TERMINAL:
                break
            time.sleep(0.05)
        self.now[0] += sweep_worker.TTL_SECONDS + 1
        fresh = self.post_run(client).get_json()["run_id"]

        removed = queue.cleanup()
        self.assertEqual(removed, [old])
        self.assertFalse(os.path.exists(os.path.join(self.runs, old)))
        self.assertTrue(os.path.exists(os.path.join(self.runs, fresh)))

    def test_it_also_removes_the_rendered_profile_from_the_checkout(self):
        """The profile has to live in the checkout's profiles/ package for
        the engine to select it, so the runs directory is not the only
        place a finished run leaves something behind."""
        app, store, queue = self.build()
        client = app.test_client()
        run = self.post_run(client).get_json()["run_id"]
        for _ in range(50):
            if store.read(run)["state"] in sweep_worker.TERMINAL:
                break
            time.sleep(0.05)
        profile_path = store.read(run)["profile_path"]
        self.assertTrue(os.path.exists(profile_path))

        self.now[0] += sweep_worker.TTL_SECONDS + 1
        self.assertEqual(queue.cleanup(), [run])
        self.assertFalse(os.path.exists(profile_path),
                         "a stranger's profile outlived their run")

    def test_it_cannot_delete_a_running_or_queued_run(self):
        gate = threading.Event()
        app, store, queue = self.build(spawner=self.spawn(block=gate))
        client = app.test_client()
        running = self.post_run(client, owner="s0").get_json()["run_id"]
        queued = self.post_run(client, owner="s1").get_json()["run_id"]

        # Far past any TTL, and still somebody's sweep.
        self.now[0] += sweep_worker.TTL_SECONDS * 10
        self.assertEqual(queue.cleanup(), [])
        self.assertEqual(store.read(running)["state"], sweep_worker.RUNNING)
        self.assertEqual(store.read(queued)["state"], sweep_worker.QUEUED)
        gate.set()


class TestResults(Harness):
    """What Render reads back while a sweep runs and after it ends."""

    def test_rows_are_served_from_the_runs_own_output_directory(self):
        app, store, _queue = self.build()
        client = app.test_client()
        run = self.post_run(client).get_json()["run_id"]
        out = store.output_dir(run)
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "jobs_1.csv"), "w", encoding="utf-8") as fh:
            fh.write("title,company,score\nRN Dev,Acme,42\nMobile Eng,Beta,31\n")

        body = client.get(f"/v1/runs/{run}/rows",
                          headers=self.auth()).get_json()
        self.assertEqual(body["total"], 2)
        self.assertEqual(body["rows"][0]["title"], "RN Dev")

        later = client.get(f"/v1/runs/{run}/rows?since=1",
                           headers=self.auth()).get_json()
        self.assertEqual([r["title"] for r in later["rows"]], ["Mobile Eng"])

    def test_no_rows_yet_is_not_an_error(self):
        app, _store, _queue = self.build()
        client = app.test_client()
        run = self.post_run(client).get_json()["run_id"]
        body = client.get(f"/v1/runs/{run}/rows",
                          headers=self.auth()).get_json()
        self.assertEqual((body["rows"], body["total"]), ([], 0))


if __name__ == "__main__":
    unittest.main()
