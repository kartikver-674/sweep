"""D7C browser harness, operator side: the console (local mode), served over HTTP, with synthetic everything except two things that
are the point of D7C, which are REAL: the profile file the console writes and the engine's own dry run that reads it.

    .venv/bin/python docs/design/d7c/harness/console.py                    # the working tree, ports 5078 to 5080 (D7B_PORT)
    D7B_REPO=/path/to/export D7B_PORT=5178 .venv/bin/python .../console.py   # another tree (an export of the parent commit)

    +0  flow    a paid console, key credit $25. Review -> Configure -> Confirm -> Run with the REAL profiles/<name>.py writer and the REAL
                `scraper.py --dry-run --json` (the price Confirm shows is the engine's reading of the file that was just saved). After
                every write the file's modification time is set to one fixed second, so "two saves inside one second" is exactly
                what happens: that is the same-second same-size bytecode defect (blocker 1) made deterministic. Set a depth of 20,
                Save, then 40, Save: Confirm must quote the second. On the tree before D7C it quotes the first.
    +1  free    a free console: Configure, Confirm, Running (a live run; /__finish ends it), Results. The operator's header on a
                sweep that costs nothing (blocker 6D).
    +2  review  the console's Review with a reading whose notes carry hostile diagnostics: the operator keeps them (escaped), a
                visitor never sees them (blocker 5).

    GET /__reset      (on +0) the session as it was at the start, and the profile file gone
    GET /__finish     (on +1) the live run ends cleanly;  /__running puts it back

Nothing is sent to a provider: no key, no model, no paid search, sockets as the machine has them but nothing here opens one. The profile
file is written to the real profiles/ directory under a name of its own (_d7c_console_<hex>) and removed when the harness exits.
"""
import atexit
import copy
import glob
import os
import pathlib
import secrets
import signal
import sys
import tempfile
import threading
from unittest import mock

REPO = pathlib.Path(os.environ.get("D7B_REPO") or pathlib.Path(__file__).resolve().parents[4]).resolve()
sys.path.insert(0, str(REPO))
os.chdir(REPO)

from werkzeug.serving import make_server  # noqa: E402

import scraper  # noqa: E402
from sweep import app as app_module  # noqa: E402
from sweep.tests import test_app as T  # noqa: E402
from sweep.tests.test_public_privacy import HOSTILE_NOTES  # noqa: E402

BASE = int(os.environ.get("D7B_PORT", "5078"))
PIN = 1_790_000_000                      # the one second every profile write is stamped with
NAME = "_d7c_console_" + secrets.token_hex(4)
TMP = tempfile.mkdtemp(prefix="d7c-console-")
ENV = os.path.join(TMP, ".env")
pathlib.Path(ENV).write_text("APIFY_TOKEN=synthetic-token-never-sent\n")
OUT = tempfile.mkdtemp(dir=TMP)


def cleanup():
    for f in glob.glob(f"profiles/{NAME}.py") + glob.glob(f"profiles/__pycache__/{NAME}.*"):
        try:
            os.remove(f)
        except OSError:
            pass


atexit.register(cleanup)
signal.signal(signal.SIGTERM, lambda *_a: sys.exit(0))

HOSTILE_DERIVED = dict(copy.deepcopy(T.DERIVED), notes=HOSTILE_NOTES.replace("INTERNAL-DIAGNOSTIC-MARKER", "operator can read this"))


def serve(app, port, extra=None):
    inner = app.wsgi_app

    def wrapped(environ, start):
        path = environ["PATH_INFO"]
        if path.startswith("/__") and extra:
            body = extra(path) or b'{"ok": true}'
            start("200 OK", [("Content-Type", "application/json")])
            return [body]
        return inner(environ, start)
    app.wsgi_app = wrapped
    s = make_server("127.0.0.1", port, app, threaded=True)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


def console(state, **kw):
    fakes = dict(extract=lambda p: "x", derive=lambda t, p: copy.deepcopy(T.DERIVED), check_token=lambda t: (25.0, None),
                 start_sweep=lambda p: T.FakeProc(), read_spend=lambda: 1.0, read_done=lambda p, d: set(), read_rows=lambda p: [],
                 start_rescore=lambda p, h: None)
    app = app_module.create_app(state=state, env_path=ENV, output_dir=tempfile.mkdtemp(dir=OUT), **{**fakes, **kw})
    app.config.update(TESTING=True)
    return app


# ---- +0 the flow -----------------------------------------------------------------------------------------------------
def flow_state():
    return {"profile": NAME, "cap_usd": 25.0, "derived": copy.deepcopy(T.DERIVED), "resume_text": "x"}


flow = console(flow_state())                               # fetch_plan is the default: the engine's own dry run
_write = flow.write_profile


def pinned(name, source):
    path = _write(name, source)
    os.utime(path, (PIN, PIN))                              # the same second, every time
    return path


flow.write_profile = pinned


def flow_ctl(path):
    if path == "/__reset":
        flow.state.clear()
        flow.state.update(flow_state())
        cleanup()


serve(flow, BASE, flow_ctl)

# ---- +1 a free console -----------------------------------------------------------------------------------------------
ROWS = [{"score": str(62 - n * 4), "matched_skills": "python, django", "is_fullstack": "True", "title": f"Backend Engineer {n}",
         "company": f"Company {n}", "location": "Pune, India", "remote?": "False", "remote_scope": "", "hires_home": "yes",
         "tz_gap": "", "remote_regions": "", "visa": "", "eor": "", "timezones": "", "experience_required": "3-5", "salary": "",
         "hr_email": "", "hr_phone": "", "source_site": "greenhouse", "apply_url": f"https://jobs.example.test/{n}",
         "date_posted": "2026-09-28", "req_number": "", "grade": "", "verified_live": ""} for n in range(8)]
live = {"alive": True}
proc = T.FakeProc()
proc.poll = lambda: None if live["alive"] else 0
free = console({"profile": "kabir", "cap_usd": 8.41, "free_only": True, "derived": copy.deepcopy(T.DERIVED), "proc": proc,
                "baseline_usd": 0.0, "raw_plan": {"profile": "kabir", "sites": {}, "max_results": {}, "free_sources": 134},
                "plan": {"total": 0.0, "total_searches": 0, "over_cap": False, "lines": [], "spend_cap": 0.0, "free_sources": 134},
                "run_started_at": 1_000_000.0, "resume_text": "x"},
               fetch_plan=lambda name: {"profile": name, "sites": {}, "max_results": {}, "free_sources": 134},
               read_rows=lambda p: [dict(r) for r in ROWS])


def free_ctl(path):
    live["alive"] = path == "/__running"


serve(free, BASE + 1, free_ctl)

# ---- +2 the console's Review, with notes the operator keeps ---------------------------------------------------------
review = console({"resume_text": "x", "derived": copy.deepcopy(HOSTILE_DERIVED)}, fetch_plan=lambda name: {"profile": name, "sites": {}})
serve(review, BASE + 2)

print("READY", BASE, NAME, flush=True)
threading.Event().wait()
