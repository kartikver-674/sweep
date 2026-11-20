"""A9: is the operator console's /results byte-identical? Renders the console (LOCAL mode) Results in nine states from the
tree given as argv[1] (GET only, in temporary resume/output/env/repo paths: a local-mode upload would write the real
auto-apply/resume/resume.pdf and some local pages write profiles/<name>.py, so this posts nothing), and prints a short sha256 of
each page. Rows carry no posting date, so a page does not change with the day it is rendered on.

    git archive HEAD | tar -x -C /tmp/head-tree
    env SWEEP_PUBLIC_MODE= .venv/bin/python docs/design/sweep-a/harness/results-hash.py /tmp/head-tree
    env SWEEP_PUBLIC_MODE= .venv/bin/python docs/design/sweep-a/harness/results-hash.py "$PWD"

`states(root)` is also what sweep/tests/test_a9_results.py pins HEAD's hashes with.
"""
import copy, hashlib, os, shutil, sys, tempfile
from unittest import mock


def states(root):
    sys.path.insert(0, root)
    from sweep import app as app_module
    from sweep.tests import test_app
    from sweep.tests.test_app import DERIVED

    derived = dict(copy.deepcopy(DERIVED), skill_weights=[{"term": t, "weight": w} for t, w in (
        ("react native", 5), ("node.js", 5), ("javascript", 2), ("git", 1), ("typescript", 4))])
    rows = [dict(r, date_posted="") for r in test_app.ROWS]
    # a Multi-Track row's columns, to prove a console that is handed them still draws its own table
    multi = [dict(r, best_track="a" * 16, recommended_tracks="a" * 16, recommendation="clear") for r in rows]
    tmp = tempfile.mkdtemp(prefix="a9-hash-")
    os.mkdir(os.path.join(tmp, "profiles"))
    out = {}
    try:
        with mock.patch.object(app_module, "REPO_ROOT", tmp):
            def make(state=None, read=rows, sweeps=()):
                st = {"profile": "kabir", "cap_usd": 8.41, "derived": copy.deepcopy(derived), "resume_text": "x"}
                st.update(state or {})
                a = app_module.create_app(
                    state=st, extract=lambda p: "x", derive=lambda t, p: derived, check_token=lambda t: (8.41, None),
                    fetch_plan=lambda profile: test_app.RAW_PLAN, read_rows=lambda profile: [dict(r) for r in read],
                    read_done=lambda profile, day: [], read_spend=lambda: 4.12, list_sweeps=lambda profile: list(sweeps),
                    resume_dir=os.path.join(tmp, "resume"), env_path=os.path.join(tmp, "none.env"),
                    output_dir=os.path.join(tmp, "out"))
                a.config.update(TESTING=True)
                a.write_profile = lambda n, src: None
                return a

            def get(app, path="/results"):
                return hashlib.sha256(app.test_client().get(path).data).hexdigest()[:16]

            out["console /results (one sweep)"] = get(make())
            out["console /results merged"] = get(make(read=[dict(r, _merged="1") for r in rows]))
            out["console /results earlier sweeps"] = get(make(sweeps=["/x/jobs_2026-09-09_1800.json", "/x/jobs_2026-08-26_1651.json"]))
            out["console /results free-only"] = get(make({"free_only": True}))
            out["console /results filtered to nothing"] = get(make(), "/results?q=zzzz-no-such-job")
            out["console /results multi-track view"] = get(make(read=multi), "/results?track=" + "a" * 16)
            out["console /results sorted, minimum"] = get(make(), "/results?sort=recent&min=40&source=himalayas")
            many = [dict(rows[3], title=f"Role {i}", score=str(100 - i)) for i in range(40)]
            out["console /results capped section"] = get(make(read=many))
            out["console /results show all"] = get(make(read=many), "/results?full=1")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


if __name__ == "__main__":
    root = sys.argv[1]
    os.chdir(root)
    for k, v in states(root).items():
        print(f"{k:40s} {v}")
