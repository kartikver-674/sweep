"""A4+: is the operator console's Upload byte-identical? Renders `/` in LOCAL mode, fresh and with a résumé read, from
the tree given as argv[1], GET only, in temporary resume/output/env paths (a local-mode upload would write the real
auto-apply/resume/resume.pdf, so this never posts one). Prints a short sha256 per state.

    git archive HEAD | tar -x -C /tmp/head-tree
    env SWEEP_PUBLIC_MODE= .venv/bin/python docs/design/sweep-a/harness/console-hash.py /tmp/head-tree
    env SWEEP_PUBLIC_MODE= .venv/bin/python docs/design/sweep-a/harness/console-hash.py "$PWD"
"""
import copy, hashlib, os, sys, tempfile
root = sys.argv[1]; sys.path.insert(0, root); os.chdir(root)
from sweep import app as app_module
from sweep.tests.test_app import DERIVED
out = {}
for name, state in (("fresh", {}), ("read", {"profile": "probe_a4", "derived": copy.deepcopy(DERIVED)})):
    a = app_module.create_app(state=state, extract=lambda p: "x", derive=lambda t, p: {}, resume_dir=tempfile.mkdtemp(),
                              output_dir=tempfile.mkdtemp(), env_path=tempfile.mktemp())
    a.config.update(TESTING=True)
    out[name] = hashlib.sha256(a.test_client().get("/").data).hexdigest()[:16]
print(out)
