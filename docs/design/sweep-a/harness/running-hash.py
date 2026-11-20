"""A8: is the operator console's /running byte-identical? Renders it in LOCAL mode, from the tree given as argv[1], GET only, with the
same kind of fakes the console harness uses (docs/design/motion-d7b/harness/local.py: the suite's own RUNNING_PLAN and FakeProc, a frozen
clock so "ran for 1m 35s" is the same whenever it is taken, no env file of real keys, no token, no provider), in temporary
resume/output/env/repo paths: some local pages write profiles/<name>.py, so the app gets a temporary tree. Prints a short sha256 per
state. The page embeds `progress|tojson`, so the hash covers the live feed's items: A8 adds `skills` to them in PUBLIC mode only, and
the listings below carry matched_skills precisely so that a leak into the console would change the bytes.

    git archive HEAD | tar -x -C /tmp/head-tree
    env SWEEP_PUBLIC_MODE= .venv/bin/python docs/design/sweep-a/harness/running-hash.py /tmp/head-tree
    env SWEEP_PUBLIC_MODE= .venv/bin/python docs/design/sweep-a/harness/running-hash.py "$PWD"

Pass --dump DIR as a second and third argument to also write each page, for a diff when two trees disagree.
"""
import hashlib, os, shutil, sys, tempfile
from unittest import mock
root = sys.argv[1]; sys.path.insert(0, root); os.chdir(root)
dump = sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "--dump" else None
from sweep import app as app_module
from sweep.tests import test_app as T

tmp = tempfile.mkdtemp(prefix="a8-hash-")
os.mkdir(os.path.join(tmp, "profiles"))
if dump:
    os.makedirs(dump, exist_ok=True)
out = {}
T0 = 1_000_000.0                        # a frozen clock: the run is 1m 35s old whenever it is rendered
KEYS = app_module.planned_keys({"raw_plan": T.RUNNING_PLAN})
FREE_PLAN = {"profile": "kabir", "sites": {}, "max_results": {}, "free_sources": 134}

# Engine-shaped rows, every one with matched_skills: the very column the public feed now reads.
ROWS = [{"title": t, "company": c, "source_site": s, "score": str(sc), "req_number": "", "apply_url": f"https://jobs.example.test/{i}",
         "matched_skills": sk}
        for i, (t, c, s, sc, sk) in enumerate([
            ("Senior Backend Engineer", "Kestrel Payments", "linkedin", 62, "python, django, postgresql, redis, docker"),
            ("Platform Engineer", "Halden Labs", "indeed", 55, " react , , node.js,typescript ,a,b,c,d"),
            ("Full Stack Developer", "Orrin Health", "greenhouse:orrin", 47, ""),
            ("Software Engineer II", "Brightwell", "linkedin", 44, "go"),
        ])]


def console(done=0, exit_code=None, stopped=False, free=False, authorization=None, credit=8.41, rows=(), timed_out=False,
            ready=False, found=0):
    proc = T.FakeProc()
    if exit_code is not None:
        proc.poll = lambda: exit_code
    proc.timed_out = timed_out
    raw = FREE_PLAN if free else T.RUNNING_PLAN
    lines = [] if free else [{"site": "linkedin", "label": "LinkedIn", "searches": 32, "rate": 0.045, "results": 25, "subtotal": 1.44, "free": False},
                             {"site": "indeed", "label": "Indeed", "searches": 14, "rate": 0.09, "results": 15, "subtotal": 1.26, "free": False}]
    state = {"profile": "kabir", "cap_usd": 8.41, "proc": proc, "credit_total_usd": credit, "key_credit": {"APIFY_TOKEN": credit},
             "baseline_usd": 1.0, "raw_plan": raw, "run_started_at": T0, "live_found": found, "live_items": [],
             "plan": {"total": 0.0 if free else 2.70, "total_searches": 0 if free else 46, "over_cap": False, "spend_cap": 3.38,
                      "free_sources": 134, "lines": lines}}
    if free:
        state["free_only"] = True
    if stopped:
        state["stopped_by_user"] = True
    keys = [] if free else KEYS
    env = os.path.join(tmp, "stub.env")
    with open(env, "w") as fh:
        fh.write("APIFY_TOKEN=apify_api_STUB_FOR_HASH_ONLY_0001\n")      # never sent anywhere: check_token is a lambda
    app = app_module.create_app(
        state=state, extract=lambda p: "x", derive=lambda t, p: T.DERIVED, check_token=lambda t: (credit, None),
        fetch_plan=lambda p: raw, start_sweep=lambda p: proc, read_spend=lambda: 2.42,
        read_done=lambda p, d: set(keys[:done]), read_rows=lambda p: [], read_live=lambda p, since: list(rows),
        read_authorization=lambda: authorization, read_ready=lambda: ready, wall_now=lambda: T0 + 95,
        env_path=env, output_dir=os.path.join(tmp, "out"))
    app.config.update(TESTING=True)
    app.write_profile = lambda n, src: None
    app.discard_profile = lambda n: None
    return app


PARTIAL = {"outcome": "partial", "total_planned_paid_units": 46, "placeable_paid_units": 43, "skipped_insufficient_capacity": 3,
           "skipped_budget": 0, "partial_estimate_usd": 2.1}
REFUSED = {"outcome": "refused", "total_planned_paid_units": 46, "placeable_paid_units": 0, "skipped_insufficient_capacity": 46}
try:
    with mock.patch.object(app_module, "REPO_ROOT", tmp):
        states = (
            ("paid running, listings in the feed", lambda: console(done=5, rows=ROWS, found=4)),
            ("paid running, the free pass     ", lambda: console(done=len(KEYS), rows=ROWS, found=4)),
            ("paid running, nothing yet       ", lambda: console(done=0)),
            ("paid finished                   ", lambda: console(done=len(KEYS), exit_code=0, rows=ROWS, found=4)),
            ("paid stopped                    ", lambda: console(done=3, exit_code=1, stopped=True, rows=ROWS[:2], found=2)),
            ("paid out of credit              ", lambda: console(done=3, exit_code=1, credit=0.02, rows=ROWS[:2], found=2)),
            ("paid halted                     ", lambda: console(done=3, exit_code=1, rows=ROWS[:2], found=2)),
            ("paid halted, timed out          ", lambda: console(done=3, exit_code=1, timed_out=True, rows=ROWS[:2], found=2)),
            ("paid incomplete                 ", lambda: console(done=len(KEYS), exit_code=1, rows=ROWS, found=4)),
            ("paid partial                    ", lambda: console(done=43, exit_code=0, authorization=PARTIAL, rows=ROWS, found=4)),
            ("paid credit changed             ", lambda: console(done=0, exit_code=4, authorization=REFUSED)),
            ("free running                    ", lambda: console(free=True)),
            ("free finished                   ", lambda: console(free=True, exit_code=0, found=7)),
            ("free halted                     ", lambda: console(free=True, exit_code=1)),
        )
        for name, make in states:
            r = make().test_client().get("/running")
            assert r.status_code == 200, (name, r.status_code)
            out[name] = hashlib.sha256(r.data).hexdigest()[:16]
            if dump:
                with open(os.path.join(dump, "-".join(name.split()).replace(",", "") + ".html"), "wb") as fh:
                    fh.write(r.data)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
for k, v in out.items():
    print(f"console {k} {v}")
