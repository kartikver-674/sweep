"""D7C browser harness, public side: the D7B harness (the real Render app and the real worker on loopback, synthetic data) plus the
things D7C needs and D7B did not.

    .venv/bin/python docs/design/d7c/harness/app.py                        # the working tree, port 5077 (D7B_PORT)
    D7B_REPO=/path/to/export D7B_PORT=5177 .venv/bin/python .../app.py     # another tree (an export of the parent commit)

Everything in docs/design/motion-d7b/harness/app.py applies unchanged (its docstring lists the scenarios and the controls). Added:

    GET /__step/incomplete          a PAID run whose every search is in the ledger and whose process then fails   (blocker 3)
    GET /__step/incomplete_timeout  the same, with the worker's own run_timeout
    GET /__step/worker_stopped      the WORKER records `stopped`; no Stop click was made in the web session        (blocker 4)
    GET /__step/interrupted         the worker's `interrupted` (it restarted): neither a stop nor a timeout
    GET /__restart                  the web process forgets every session room (a redeploy). The cookie keeps the run id and
                                    rehydrate puts back only what the worker still says                            (blocker 4)
    GET /__serve_live               the newest multi-résumé run's jobs (the D6 set) written on its own tracks' real ids, so a
                                    journey driven through the screens ends on a Results with a tab for each
    GET /__hostile/<0|1>            the reading carries hostile diagnostics (paths, a stack trace, secrets, internal names) in
                                    `notes`, `skills_added`, `role_evidence`, ...                                  (blocker 5)

    D7C_PLAIN_COOKIE=1              serve the session cookie without `Secure` (the WebKit run only: see render())

No provider, no key, no model call, no paid search, no external network.
"""
import copy
import importlib.util
import json
import os
import pathlib
import sys
import time

REPO = pathlib.Path(os.environ.get("D7B_REPO") or pathlib.Path(__file__).resolve().parents[4]).resolve()
sys.path.insert(0, str(REPO))
os.chdir(REPO)

_spec = importlib.util.spec_from_file_location("d7b_app", REPO / "docs/design/motion-d7b/harness/app.py")
d7b = importlib.util.module_from_spec(_spec)
sys.modules["d7b_app"] = d7b
_spec.loader.exec_module(d7b)

from werkzeug.serving import make_server  # noqa: E402

from deploy import sweep_worker  # noqa: E402
from sweep import public, worker_link  # noqa: E402
from sweep.tests import test_multi_render as r1  # noqa: E402
from sweep.tests import test_multi_setup as u1  # noqa: E402
from sweep.tests.test_one_track_goldens import derived_for  # noqa: E402
from sweep.tests.test_public_privacy import hostile  # noqa: E402
from sweep.tests.test_worker_link import cookie_of, render_app  # noqa: E402

CHILD, STATE, LATENCY, CREDIT, FLAGS = d7b.CHILD, d7b.STATE, d7b.LATENCY, d7b.CREDIT, d7b.FLAGS
HOSTILE = {"on": False}
PLAIN_COOKIE = bool(os.environ.get("D7C_PLAIN_COOKIE"))        # read now: the test setUp clears os.environ before render() runs
NEW_STAGES = ("incomplete", "incomplete_timeout", "worker_stopped", "interrupted")


class Live(d7b.Live):
    def render(self):
        """D7B's own app, except that a reading can be asked to carry hostile diagnostics."""
        self.derived_texts, self.failing, self.while_reading = [], set(), None
        self.extracted = []

        def extract(path):
            with open(path, "rb") as fh:
                who = fh.read()[len(b"%PDF-1.7 "):].decode()
            return {"blank": "  ", **u1.TEXT}.get(who, who)

        def derive(text, prefs):
            time.sleep(STATE["delay"])
            who = next(k for k, v in u1.TEXT.items() if v == text)
            if STATE["fail"] == who:
                raise RuntimeError("the model did not answer")
            data = copy.deepcopy(derived_for(u1.PERSONA[who]))
            if HOSTILE["on"]:
                data.update({k: v for k, v in hostile().items() if k != "field_summary"})
            return data

        app = render_app(self.worker.url, check_token=lambda token: (CREDIT.get(token, 42.0), None),
                         extract=extract, derive=derive)
        if PLAIN_COOKIE:
            # WebKit does not keep a `Secure` cookie that plain http on loopback sets (Chromium and Firefox treat loopback as a secure
            # origin), so a journey that lets the app set its own session cookie has no session there. The harness, for that engine
            # only, serves the same cookie without `Secure`; production is https and is unchanged.
            app.config["SESSION_COOKIE_SECURE"] = False
        return app

    def apply_stage(self, rid, stage):
        if stage not in NEW_STAGES:
            return super().apply_stage(rid, stage)
        for _ in range(300):                       # the worker says "queued" a moment before it spawns the child
            if rid in CHILD:
                break
            time.sleep(0.02)
        room = self.room_of()
        if stage in ("incomplete", "incomplete_timeout"):
            self.age(1500)
            self.give_ledger(rid, room, 10 ** 6)                  # every planned search is in the ledger
            self.give_rows(rid, 5)
            CHILD[rid]["code"] = 1
            CHILD[rid]["ev"].set()
            self.settle(rid, {"failed"})
            if stage == "incomplete_timeout":
                self.worker.store.update(rid, error=sweep_worker.RUN_TIMEOUT)
        elif stage in ("worker_stopped", "interrupted"):
            self.age(500)
            self.give_ledger(rid, room, 3)
            self.give_rows(rid, 2)
            state = sweep_worker.STOPPED if stage == "worker_stopped" else sweep_worker.INTERRUPTED
            self.worker.store.update(rid, state=state, finished_at=time.time())
            CHILD[rid]["code"] = 143 if stage == "worker_stopped" else 1
            CHILD[rid]["ev"].set()
            self.settle(rid, {state})

    def runTest(self):
        inner = self.app.wsgi_app
        me = self

        def app(environ, start):
            path = environ["PATH_INFO"]
            if path.startswith("/__"):
                parts = path.split("/")[1:]
                cmd, arg = parts[0], parts[1:]
                if cmd == "__go":
                    # For a person in a real browser (A11's manual check): build the scenario, hand this browser its
                    # session cookie, and land on the page. Only a same-site path is followed.
                    from urllib.parse import parse_qs
                    me.build(arg[0])
                    to = parse_qs(environ.get("QUERY_STRING", "")).get("to", ["/"])[0]
                    if not to.startswith("/") or to.startswith("//"):
                        to = "/"
                    start("302 Found", [("Location", to),
                                        ("Set-Cookie", f"session={cookie_of(me.client)}; Path=/; HttpOnly; SameSite=Lax")])
                    return [b""]
                body = {"ok": True}
                try:
                    if cmd == "__make":
                        me.build(arg[0])
                        body["cookie"] = cookie_of(me.client)
                    elif cmd == "__step":
                        me.apply_stage(me.newest(), arg[0])
                    elif cmd == "__ledger":
                        me.give_ledger(me.newest(), me.room_of(), int(arg[0]))
                    elif cmd == "__rows":
                        me.give_rows(me.newest(), int(arg[0]))
                    elif cmd == "__latency":
                        LATENCY[arg[0]] = int(arg[1]) / 1000.0
                    elif cmd == "__credit":
                        CREDIT[arg[0]] = float(arg[1])
                    elif cmd == "__nopaid":
                        FLAGS["nopaid"] = arg[0] == "1"
                    elif cmd == "__restart":
                        me.app.session_store._rooms.clear()      # a redeploy: memory is gone, the cookie is not
                        worker_link._ASKED.clear()
                    elif cmd == "__serve_live":               # the newest (multi-résumé) run's jobs, on its own tracks' real ids
                        rid = me.newest()
                        ids = list(me.worker.store.read(rid)["track_ids"])
                        text = json.dumps(d7b.ALL)
                        for old, new in zip(d7b.IDS, ids):
                            text = text.replace(old, new)
                        me.run_id = rid
                        me.serve(json.loads(text))
                    elif cmd == "__hostile":
                        HOSTILE["on"] = arg[0] == "1"
                except Exception as exc:              # the harness says what it could not build
                    import traceback
                    body = {"ok": False, "error": repr(exc), "trace": traceback.format_exc()[-1500:]}
                start("200 OK", [("Content-Type", "application/json")])
                return [json.dumps(body).encode()]
            hold = LATENCY["all"] or (LATENCY["results"] if path == "/results" else 0) \
                or (LATENCY["estimate"] if path == "/estimate" else 0)
            if hold:
                time.sleep(hold)
            return inner(environ, start)

        self.app.wsgi_app = app
        srv = make_server("127.0.0.1", d7b.PORT, self.app, threaded=True)
        print("READY", d7b.PORT, flush=True)
        srv.serve_forever()


if __name__ == "__main__":
    import unittest
    for k in ("PARSES_PER_IP_HOUR", "PARSES_PER_IP_DAY", "PARSES_PER_SESSION_HOUR", "PLANS_PER_SESSION_MINUTE",
              "PLANS_PER_IP_MINUTE", "MAX_ROOMS_PER_IP", "DEFAULT_RUNS_PER_IP", "DEFAULT_RUNS_TOTAL",
              "DEFAULT_PER_IP", "DEFAULT_TOTAL"):
        setattr(public, k, 10 ** 6)
    _i = public.SessionStore.__init__
    _i.__defaults__ = tuple(10 ** 6 if d == 10 else d for d in _i.__defaults__)
    r1.setUpModule()
    try:
        unittest.TextTestRunner(verbosity=0).run(Live())
    finally:
        r1.tearDownModule()
