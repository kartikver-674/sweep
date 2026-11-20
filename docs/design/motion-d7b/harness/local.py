"""D7B capture harness: the operator console (local mode), served over HTTP, with synthetic everything.

    .venv/bin/python docs/design/motion-d7b/harness/local.py                 # the working tree, ports 5078 to 5081
    D7B_REPO=/path/to/export D7B_PORT=5178 .venv/bin/python .../local.py      # another tree

The console's own injected fakes (the ones the test suite uses) in a sealed temporary tree: no env file, no token, no
provider call, no model call, no paid search, no external network. Four apps, one port each (base = D7B_PORT, default 5078):

    +0  Configure, credit cap $8.41     the estimate is $2.70; switch a source off and on to re-price it
    +1  Configure, credit cap $2.00     the estimate ($2.70) is over the cap; switch Indeed off and it is under
    +2  Results                         24 listings, two of them already applied to
    +3  Running (streams)               a live run: /__done/<n> finishes n searches, /__rows/<n> lists n listings,
                                        /__finish ends it (the stream says finished, the page goes to Results 400 ms later),
                                        /__reset puts it back part-way

    GET /__latency/<ms>   on any of them: hold every /estimate answer (a slow server); 0 clears it
"""
import copy
import os
import pathlib
import re
import sys
import tempfile
import threading
import time
from unittest import mock

REPO = pathlib.Path(os.environ.get("D7B_REPO") or pathlib.Path(__file__).resolve().parents[4]).resolve()
sys.path.insert(0, str(REPO))
os.chdir(REPO)

from werkzeug.serving import make_server  # noqa: E402

import scraper  # noqa: E402
from sweep import app as app_module  # noqa: E402
from sweep.tests import test_app as T  # noqa: E402

BASE = int(os.environ.get("D7B_PORT", "5078"))
ENV = {"PATH": "/usr/bin:/bin", "HOME": tempfile.mkdtemp(prefix="d7b-home-"), "LANG": "en_US.UTF-8"}
ROOT = tempfile.mkdtemp(prefix="d7b-root-")
os.mkdir(os.path.join(ROOT, "profiles"))
OUT = tempfile.mkdtemp(prefix="d7b-out-")
LAT = {"estimate": 0.0}

TITLES = ["Senior Backend Engineer", "Platform Engineer", "Full Stack Developer", "Software Engineer II", "Backend Developer",
          "Data Platform Engineer", "Mobile Engineer (React Native)", "DevOps Engineer", "QA Automation Engineer"]
COMPANIES = ["Kestrel Payments", "Halden Labs", "Orrin Health", "Brightwell", "Tarn & Co", "Quillfeather", "Ostrava Systems",
             "Mallow Cloud", "Pebble Grid"]
SITES = ["linkedin", "greenhouse:halden", "indeed", "lever:brightwell", "naukri"]
WHERE = ["Bengaluru, India", "Pune, India", "Hyderabad, India", "Gurugram, India", "Mumbai, India", "Chennai, India", "Noida, India"]


def row(n):
    return {"score": str(62 - n * 2), "matched_skills": "python, django, postgresql, redis, docker", "is_fullstack": "True",
            "title": TITLES[n % len(TITLES)], "company": COMPANIES[n % len(COMPANIES)], "location": WHERE[n % len(WHERE)],
            "remote?": "False", "remote_scope": "", "hires_home": "yes", "tz_gap": "", "remote_regions": "", "visa": "",
            "eor": "", "timezones": "", "experience_required": ["5+", "4+", "3-5", "2+", ""][n % 5],
            "salary": ["INR 28-36 LPA", "", "INR 18-24 LPA", ""][n % 4], "hr_email": "", "hr_phone": "",
            "source_site": SITES[n % len(SITES)], "apply_url": f"https://jobs.example.test/{n + 1}",
            "date_posted": f"2026-09-{28 - n % 8:02d}", "req_number": f"R{n + 1}", "grade": "", "verified_live": ""}


ROWS = [row(n) for n in range(24)]
srv = []


def serve(app, port):
    inner = app.wsgi_app

    def wrapped(environ, start):
        if environ["PATH_INFO"].startswith("/__latency/"):
            LAT["estimate"] = int(environ["PATH_INFO"].rsplit("/", 1)[1]) / 1000.0
            start("200 OK", [("Content-Type", "application/json")])
            return [b'{"ok": true}']
        if environ["PATH_INFO"] == "/estimate" and LAT["estimate"]:
            time.sleep(LAT["estimate"])
        return inner(environ, start)
    app.wsgi_app = wrapped
    s = make_server("127.0.0.1", port, app, threaded=True)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    srv.append(s)


with mock.patch.dict(os.environ, ENV, clear=True), mock.patch.object(app_module, "REPO_ROOT", ROOT):
    env_path = os.path.join(ROOT, ".env")
    pathlib.Path(env_path).write_text("")

    def configure(cap):
        """Configure with a price that answers to the form: the console prices a candidate profile the dry run reads; here
        the candidate is captured as it is written and the fixed plan is cut down to the sites it enables, so switching
        a source off or on really re-prices it (the suite's own fake returns one plan whatever the form says)."""
        written = {}
        raw = copy.deepcopy(T.RAW_PLAN)

        def plan_for(name):
            plan = copy.deepcopy(raw)
            src = written.get(name) if "_est_" in name else None     # only a candidate the form just sent is cut down
            if src:
                on = {m.group(1) for m in re.finditer(r'"(\w+)": \{\s*"actor": \'[^\']*\',\s*"enabled": True', src)}
                plan["sites"] = {k: v for k, v in plan["sites"].items() if k in on}
            return plan

        app = app_module.create_app(
            state={"profile": "kabir", "cap_usd": cap, "derived": copy.deepcopy(T.DERIVED)},
            extract=lambda p: "x", derive=lambda t, p: copy.deepcopy(T.DERIVED), check_token=lambda t: (cap, None),
            fetch_plan=plan_for, env_path=env_path, output_dir=tempfile.mkdtemp(dir=OUT))
        app.config.update(TESTING=True)
        app.write_profile = lambda name, source: written.__setitem__(name, source)
        app.discard_profile = lambda name: written.pop(name, None)
        return app

    serve(configure(8.41), BASE)
    serve(configure(2.0), BASE + 1)

    results = app_module.create_app(
        state={"profile": "kabir", "cap_usd": 8.41}, extract=lambda p: "x", derive=lambda t, p: T.DERIVED,
        check_token=lambda t: (8.41, None), read_rows=lambda profile: ROWS, start_rescore=lambda p, h: None,
        env_path=env_path, output_dir=OUT)
    results.config.update(TESTING=True)
    c = results.test_client()
    for n in (2, 5):
        c.post("/applied", data={"key": scraper._seen_key(dict(ROWS[n - 1])), "on": "1"})
    serve(results, BASE + 2)

    # ---- a live run ------------------------------------------------------------------------------------------------
    T0 = 1_000_000.0                   # a frozen clock: the screen says 1m 35s whenever it is captured
    live = {"done": 0, "alive": True, "spend": 1.0}
    proc = T.FakeProc()
    proc.poll = lambda: None if live["alive"] else 0
    state = {"profile": "kabir", "cap_usd": 8.41, "proc": proc, "baseline_usd": 1.0, "raw_plan": T.RUNNING_PLAN,
             "plan": {"total": 2.70, "total_searches": 46, "over_cap": False, "lines": []}, "run_started_at": T0}
    keys = app_module.planned_keys(state)
    feed_dir = os.path.join(OUT, "kabir")
    os.makedirs(feed_dir, exist_ok=True)

    def write_rows(n):
        lines = ["score,title,company,source_site,req_number,apply_url"] + [
            ",".join(str(x) for x in (r["score"], r["title"], r["company"], r["source_site"].split(":")[0], "", r["apply_url"]))
            for r in ROWS[:n]]
        pathlib.Path(feed_dir, "jobs_2026-09-30_1200.csv").write_text("\n".join(lines) + "\n")

    write_rows(4)
    live["done"] = 5
    running = app_module.create_app(
        state=state, extract=lambda p: "x", derive=lambda t, p: T.DERIVED, check_token=lambda t: (8.41, None),
        fetch_plan=lambda profile: T.RUNNING_PLAN, start_sweep=lambda profile: proc,
        read_spend=lambda: live["spend"], read_done=lambda profile, day: set(keys[:live["done"]]),
        read_rows=lambda profile: ROWS, start_rescore=lambda p, h: None, env_path=env_path, output_dir=OUT,
        wall_now=lambda: T0 + 95)
    running.config.update(TESTING=True)
    inner = running.wsgi_app

    def control(environ, start):
        path = environ["PATH_INFO"]
        if path.startswith("/__"):
            cmd, *arg = path.split("/")[1:]
            if cmd == "__done":
                live["done"] = int(arg[0])
            elif cmd == "__rows":
                write_rows(int(arg[0]))
            elif cmd == "__spend":
                live["spend"] = 1.0 + float(arg[0])
            elif cmd == "__finish":
                live["done"] = len(keys)
                live["alive"] = False
            elif cmd == "__reset":                                   # a run part-way again: 5 searches done, 4 listings, none shown yet
                live.update(done=5, alive=True, spend=1.0)
                for k in ("live_seen", "live_items", "live_found"):       # what the screen has already been told about
                    state.pop(k, None)
                write_rows(4)
            start("200 OK", [("Content-Type", "application/json")])
            return [b'{"ok": true}']
        return inner(environ, start)
    running.wsgi_app = control
    serve(running, BASE + 3)
    print("READY", BASE, flush=True)
    while True:
        time.sleep(3600)
