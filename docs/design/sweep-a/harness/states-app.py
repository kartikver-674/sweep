"""A10 browser harness, public side: the A8 harness (progress-app.py: the real Render app and the real worker on loopback, synthetic
data) with the controls the states the design canvas never drew need. Nothing here touches the application: every control patches
this process only, and `/_x/reset` puts them all back.

    .venv/bin/python docs/design/sweep-a/harness/states-app.py                       # the working tree, port 5077 (D7B_PORT)

Controls (GET, JSON answer):
    /_x/limit/<on|off>        this network has used today's résumé reads            -> POST /derive answers BetaLimited (429)
    /_x/rooms/<on|off>        this network holds as many sessions as it may          -> a new visitor's POST /resume answers RoomsFull (429)
    /_x/trouble/<kind>        the worker refuses to start the run: needs_key | gone | busy | paid_off | down   (0 clears)
                              plan_fail: the plan cannot be made at all (plan_error.html)
    /_x/done/<some|all|off>   searches "already done today" in the plan              (Confirm's two callouts)
    /_x/late/<on|off>         the wall clock reads 23:10                              (Confirm's past-midnight warning)
    /_x/public/<rescore|off>  let POST /rescore through the public door (it is OPERATOR_ONLY in public mode, so Results' error and notice
                              are otherwise unreachable; both paths return before anything is launched)
    /_x/reset                 every control off

Scenarios added to /__make/<name> (every earlier scenario applies unchanged):
    x_reading                 one résumé being read right now (the strip's "reading" phase)
    x_failed_one              one résumé whose reading failed (Review shows deriving.html's error)
    x_q<k>                    a paid sweep queued behind k others (one running, the rest waiting): the worker's queue_position is k
    x_late                    (nothing: use /_x/late) -- see states-a.mjs
Extract: a PDF whose text is `refuse` is refused by the real reader's own words (safe_pdf.Unreadable("encrypted")).
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

_spec = importlib.util.spec_from_file_location("progress_app", REPO / "docs/design/sweep-a/harness/progress-app.py")
pa = importlib.util.module_from_spec(_spec)
sys.modules["progress_app"] = pa
_spec.loader.exec_module(pa)
d7c, d7b = pa.d7c, pa.d7b

import datetime as _dt  # noqa: E402

from sweep import app as app_module  # noqa: E402
from sweep import public, safe_pdf, worker_client  # noqa: E402
from sweep import runs as runs_mod  # noqa: E402
from sweep.tests import test_multi_setup as u1  # noqa: E402
from sweep.tests.test_one_track_goldens import derived_for  # noqa: E402
from sweep.tests.test_worker_link import render_app  # noqa: E402

X = {"trouble": None, "done": None, "late": False, "public": False}

# ---- the worker refuses plans -------------------------------------------------------------------------------------
_TROUBLE = {"needs_key": worker_client.NeedsKey, "gone": worker_client.RunNotFound, "busy": worker_client.QueueFull,
            "paid_off": worker_client.PaidUnavailable, "down": worker_client.WorkerError,
            "plan_fail": RuntimeError}
# plan_fail: any failure of the plan itself is PlanUnavailable -> plan_error.html. The five WorkerErrors only reach their handler (key.html)
# from a call that is not a plan: the one that starts the run.
def _wrap(name, kinds):
    inner = getattr(worker_client, name)

    def call(*a, **k):
        if X["trouble"] in kinds:
            raise _TROUBLE[X["trouble"]]("harness")
        return inner(*a, **k)
    setattr(worker_client, name, call)


for _name in ("plan", "plan_tracks"):
    _wrap(_name, ("plan_fail",))
for _name in ("create_run", "create_tracks_run"):
    _wrap(_name, ("needs_key", "gone", "busy", "paid_off", "down"))

# ---- searches already done today ----------------------------------------------------------------------------------
_remaining = runs_mod.remaining_plan


def remaining_plan(raw_plan, done, day):
    if X["done"] == "all":
        return dict(raw_plan, sites={}), sum(len(v) for v in raw_plan["sites"].values())
    if X["done"] == "some":
        sites, dropped = {}, 0
        for site, searches in raw_plan["sites"].items():
            cut = min(len(searches) // 2, 12) if not sites else 0
            dropped += cut
            sites[site] = searches[cut:]
        return dict(raw_plan, sites={k: v for k, v in sites.items() if v}), dropped
    return _remaining(raw_plan, done, day)


runs_mod.remaining_plan = remaining_plan


# ---- 23:10 ------------------------------------------------------------------------------------------------------------
class _Clock(_dt.datetime):
    @classmethod
    def now(cls, tz=None):
        real = super().now(tz)
        return real.replace(hour=23, minute=10) if X["late"] else real


app_module.datetime = _Clock

# ---- the door for /rescore ------------------------------------------------------------------------------------------
_PUBLIC = public.PUBLIC_ENDPOINTS


class _Door(frozenset):
    def __contains__(self, item):
        return item in _PUBLIC or (X["public"] and item == "rescore")


public.PUBLIC_ENDPOINTS = _Door()


class States(d7c.Live):
    def render(self):
        """d7c's own app, plus a reader that refuses a PDF and a derive that can be told to fail."""
        self.derived_texts, self.failing, self.while_reading = [], set(), None
        self.extracted = []

        def extract(path):
            with open(path, "rb") as fh:
                who = fh.read()[len(b"%PDF-1.7 "):].decode()
            if who == "refuse":
                raise safe_pdf.Unreadable("encrypted")
            return {"blank": "  ", **u1.TEXT}.get(who, who)

        def derive(text, prefs):
            who = next(k for k, v in u1.TEXT.items() if v == text)
            if d7b.STATE["fail"] == who:
                raise RuntimeError("the model did not answer")
            return copy.deepcopy(derived_for(u1.PERSONA[who]))

        app = render_app(self.worker.url, check_token=lambda token: (d7b.CREDIT.get(token, 42.0), None), extract=extract, derive=derive)
        me, inner = self, app.wsgi_app

        def controls(environ, start):
            path = environ["PATH_INFO"]
            if not path.startswith("/_x/"):
                return inner(environ, start)
            cmd, _, arg = path[4:].partition("/")
            try:
                live = me.app
                if cmd == "limit":
                    lim = live.beta_limit
                    lim.per_ip, lim._slots = (3, {"127.0.0.1": [time.time()] * 3}) if arg == "on" else (10 ** 6, {})
                elif cmd == "rooms":
                    live.session_store._per_ip = 0 if arg == "on" else 10 ** 6
                elif cmd == "trouble":
                    X["trouble"] = None if arg in ("0", "off") else arg
                elif cmd == "done":
                    X["done"] = None if arg == "off" else arg
                elif cmd == "late":
                    X["late"] = arg == "on"
                elif cmd == "public":
                    X["public"] = arg == "rescore"
                elif cmd == "reset":
                    live.beta_limit.per_ip, live.beta_limit._slots = 10 ** 6, {}
                    live.session_store._per_ip = 10 ** 6
                    X.update(trouble=None, done=None, late=False, public=False)
                    d7b.STATE["fail"] = None
                body = {"ok": True}
            except Exception as exc:                                       # the harness says what it could not do
                body = {"ok": False, "error": repr(exc)}
            start("200 OK", [("Content-Type", "application/json")])
            return [json.dumps(body).encode()]

        app.wsgi_app = controls
        return app

    def build(self, name):
        if name == "x_reading":
            super().build("manage1")
            self.room_of()["tracks"][0]["parse"] = {"state": "reading", "at": time.time()}
        elif name == "x_failed_one":
            super().build("manage1")
            d7b.STATE["fail"] = "ada"
            self.client.post("/derive")
            d7b.STATE["fail"] = None
        elif name.startswith("x_q"):
            k = int(name[3:])
            super().build("fresh")
            d7b.AUTO["on"] = False                   # an engine child that stays until the harness releases it
            for _ in range(k):
                self.running(1, False)
            self.running(1, True)
            assert self.worker.store.read(self.newest())["state"] == "queued", "the last one should be waiting"
        else:
            super().build(name)


if __name__ == "__main__":
    import unittest
    for k in ("PARSES_PER_IP_HOUR", "PARSES_PER_IP_DAY", "PARSES_PER_SESSION_HOUR", "PLANS_PER_SESSION_MINUTE",
              "PLANS_PER_IP_MINUTE", "MAX_ROOMS_PER_IP", "DEFAULT_RUNS_PER_IP", "DEFAULT_RUNS_TOTAL",
              "DEFAULT_PER_IP", "DEFAULT_TOTAL"):
        setattr(public, k, 10 ** 6)
    _i = public.SessionStore.__init__
    _i.__defaults__ = tuple(10 ** 6 if d == 10 else d for d in _i.__defaults__)
    d7c.r1.setUpModule()
    try:
        unittest.TextTestRunner(verbosity=0).run(States())
    finally:
        d7c.r1.tearDownModule()
