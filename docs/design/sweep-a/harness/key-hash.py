"""A6+: is the operator console's /key byte-identical? Renders it in LOCAL mode, from the tree given as argv[1], GET only, in
temporary resume/output/env/repo paths (a local-mode upload would write the real auto-apply/resume/resume.pdf and some local
pages write profiles/<name>.py, so this posts nothing and the app gets a temporary tree). Prints a short sha256 per state.

    git archive HEAD | tar -x -C /tmp/head-tree
    env SWEEP_PUBLIC_MODE= .venv/bin/python docs/design/sweep-a/harness/key-hash.py /tmp/head-tree
    env SWEEP_PUBLIC_MODE= .venv/bin/python docs/design/sweep-a/harness/key-hash.py "$PWD"
"""
import copy, hashlib, os, shutil, sys, tempfile
from unittest import mock
root = sys.argv[1]; sys.path.insert(0, root); os.chdir(root)
from sweep import app as app_module
from sweep.tests.test_app import DERIVED

tmp = tempfile.mkdtemp(prefix="a6-hash-")
os.mkdir(os.path.join(tmp, "profiles"))
out = {}
try:
    with mock.patch.object(app_module, "REPO_ROOT", tmp):
        for name, state in (("fresh", {}), ("read", {"resume_text": "x", "profile": "probe_a6", "derived": copy.deepcopy(DERIVED)})):
            a = app_module.create_app(
                state=state, extract=lambda p: "x", derive=lambda t, p: {}, check_token=lambda t: (8.41, None),
                read_rows=lambda profile: [], list_sweeps=lambda profile: [],
                resume_dir=os.path.join(tmp, "resume"), env_path=os.path.join(tmp, "none.env"), output_dir=os.path.join(tmp, "out"))
            a.config.update(TESTING=True)
            r = a.test_client().get("/key")
            assert r.status_code == 200
            out[name] = hashlib.sha256(r.data).hexdigest()[:16]
finally:
    shutil.rmtree(tmp, ignore_errors=True)
for k, v in out.items():
    print(f"console /key {k:6s} {v}")
