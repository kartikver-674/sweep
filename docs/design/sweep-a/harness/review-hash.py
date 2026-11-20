"""A5+: are the operator console's Review and its Results re-rank editor byte-identical? Renders both in LOCAL mode from the tree
given as argv[1], GET only, in temporary resume/output/env/repo paths (a local-mode upload would write the real
auto-apply/resume/resume.pdf and some local pages write profiles/<name>.py, so this posts nothing and the app gets a temporary
tree). Prints a short sha256 per page, and the sha256 of the weight editor's table markup on its own.

    git archive HEAD | tar -x -C /tmp/head-tree
    env SWEEP_PUBLIC_MODE= .venv/bin/python docs/design/sweep-a/harness/review-hash.py /tmp/head-tree
    env SWEEP_PUBLIC_MODE= .venv/bin/python docs/design/sweep-a/harness/review-hash.py "$PWD"
"""
import copy, hashlib, os, shutil, sys, tempfile
from unittest import mock
root = sys.argv[1]; sys.path.insert(0, root); os.chdir(root)
from sweep import app as app_module
from sweep.tests import test_app
from sweep.tests.test_app import DERIVED

derived = dict(copy.deepcopy(DERIVED), skill_weights=[{"term": t, "weight": w} for t, w in (
    ("react native", 5), ("node.js", 5), ("javascript", 2), ("git", 1), ("typescript", 4), ("redis", 3), ("docker", 2))],
    skill_importance=[{"id": "react native", "tier": "CORE", "why": "You used it at work."}],
    penalty_terms=[{"term": "salesforce", "weight": 5}], role_keywords=["a", "b", "c", "d", "e", "f", "g", "h"])
tmp = tempfile.mkdtemp(prefix="a5-hash-")
os.mkdir(os.path.join(tmp, "profiles"))
out = {}
try:
    with mock.patch.object(app_module, "REPO_ROOT", tmp):
        def make(state):
            a = app_module.create_app(
                state=state, extract=lambda p: "x", derive=lambda t, p: derived, check_token=lambda t: (8.41, None),
                fetch_plan=lambda profile: test_app.RAW_PLAN, read_rows=lambda profile: list(test_app.ROWS),
                read_done=lambda profile, day: [], read_spend=lambda: 4.12, list_sweeps=lambda profile: [],
                resume_dir=os.path.join(tmp, "resume"), env_path=os.path.join(tmp, "none.env"),
                output_dir=os.path.join(tmp, "out"))
            a.config.update(TESTING=True)
            a.write_profile = lambda n, src: None
            return a
        review = make({"resume_text": "x", "derived": copy.deepcopy(derived), "profile": "probe_a5"}).test_client().get("/review")
        out["console /review"] = hashlib.sha256(review.data).hexdigest()[:16]
        results = make({"profile": "kabir", "cap_usd": 8.41, "derived": copy.deepcopy(derived), "resume_text": "x"}).test_client().get("/results")
        out["console /results"] = hashlib.sha256(results.data).hexdigest()[:16]
        body = results.get_data(as_text=True)
        panel = body[body.index('class="weights"') - 40: body.index("</table>", body.index('class="weights"')) + 8]
        out["results re-rank table"] = hashlib.sha256(panel.encode()).hexdigest()[:16]
finally:
    shutil.rmtree(tmp, ignore_errors=True)
for k, v in out.items():
    print(f"{k:24s} {v}")
