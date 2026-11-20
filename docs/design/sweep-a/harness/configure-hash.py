"""A7: are the operator console's /configure and /confirm byte-identical? Renders them in LOCAL mode, from the tree given as argv[1],
GET only, with the same fakes the console harness uses (docs/design/motion-d7b/harness/local.py: the suite's own RAW_PLAN, a credit cap
that answers /estimate, no env file, no token, no provider), in temporary resume/output/env/repo paths: some local pages write
profiles/<name>.py, so the app gets a temporary tree and its profile writer is replaced. Prints a short sha256 per state.

    git archive HEAD | tar -x -C /tmp/head-tree
    env SWEEP_PUBLIC_MODE= .venv/bin/python docs/design/sweep-a/harness/configure-hash.py /tmp/head-tree
    env SWEEP_PUBLIC_MODE= .venv/bin/python docs/design/sweep-a/harness/configure-hash.py "$PWD"

Pass --dump DIR as a second and third argument to also write each page, for a diff when two trees disagree.
"""
import copy, hashlib, os, shutil, sys, tempfile
from unittest import mock
root = sys.argv[1]; sys.path.insert(0, root); os.chdir(root)
dump = sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "--dump" else None
from sweep import app as app_module
from sweep.tests import test_app as T

tmp = tempfile.mkdtemp(prefix="a7-hash-")
os.mkdir(os.path.join(tmp, "profiles"))
if dump:
    os.makedirs(dump, exist_ok=True)
out = {}


def console(cap, free=False, plan=None, keys=1, done=0, **state):
    # /confirm re-reads the credit from the env file, so the file carries obviously fake stand-ins (never sent anywhere: check_token is
    # a lambda) or the cap would reset to nothing and "over the cap" could not be rendered.
    env = os.path.join(tmp, f"stub-{keys}.env")
    with open(env, "w") as fh:
        fh.write("".join(f"APIFY_TOKEN{'' if n == 1 else '_' + str(n)}=apify_api_STUB_FOR_HASH_ONLY_{n:04d}\n" for n in range(1, keys + 1)))
    base = {"profile": "kabir", "derived": copy.deepcopy(T.DERIVED), "cap_usd": cap, "credit_total_usd": cap}
    if free:
        base.update(free_only=True, sites_enabled={s: False for s in app_module.paid_sites()})
    base.update(state)
    app = app_module.create_app(
        state=base, extract=lambda p: "x", derive=lambda t, p: copy.deepcopy(T.DERIVED), check_token=lambda t: (cap, None),
        fetch_plan=lambda name: dict(copy.deepcopy(plan or T.RAW_PLAN), profile=name),
        read_rows=lambda profile: [], list_sweeps=lambda profile: [], hour_now=lambda: hour[0],
        read_done=lambda profile, day: set(app_module.planned_keys({"raw_plan": T.RAW_PLAN})[:done]),
        resume_dir=os.path.join(tmp, "resume"), env_path=env, output_dir=os.path.join(tmp, "out"))
    app.config.update(TESTING=True)
    app.write_profile = lambda n, src: None
    app.discard_profile = lambda n: None
    return app


hour = [12]
try:
    with mock.patch.object(app_module, "REPO_ROOT", tmp):
        states = (
            ("configure  cap $8.41       ", lambda: console(8.41), "/configure"),
            ("configure  over the cap    ", lambda: console(2.0), "/configure"),
            ("configure  free-only       ", lambda: console(8.41, free=True), "/configure"),
            ("confirm    cap $8.41       ", lambda: console(8.41), "/confirm"),
            ("confirm    over the cap    ", lambda: console(2.0), "/confirm"),
            ("confirm    free-only       ", lambda: console(8.41, free=True), "/confirm"),
            ("confirm    late (23:00)    ", lambda: console(8.41), "/confirm", 23),
            ("confirm    over, late      ", lambda: console(2.0), "/confirm", 23),
            ("confirm    over, 2 keys    ", lambda: console(2.0, keys=2), "/confirm"),
            ("confirm    already done    ", lambda: console(8.41, done=5), "/confirm"),
        )
        for item in states:
            name, make, path = item[:3]
            hour[0] = item[3] if len(item) > 3 else 12
            r = make().test_client().get(path)
            assert r.status_code == 200, (name, r.status_code)
            out[name] = hashlib.sha256(r.data).hexdigest()[:16]
            if dump:
                with open(os.path.join(dump, name.split()[0] + "-" + "-".join(name.split()[1:]).replace("$", "") + ".html"), "wb") as fh:
                    fh.write(r.data)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
for k, v in out.items():
    print(f"console {k} {v}")
