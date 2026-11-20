"""A8 browser harness, public side: the D7C harness (which is the D7B harness: the real Render app and the real worker on loopback,
synthetic data) with one difference, the listings a run's feed carries.

    .venv/bin/python docs/design/sweep-a/harness/progress-app.py                       # the working tree, port 5077 (D7B_PORT)
    D7B_REPO=/path/to/export D7B_PORT=5177 .venv/bin/python .../progress-app.py        # another tree

D7B's `give_rows` wrote five listings with no `matched_skills` column, so a feed built from them could never show why a match
matched. Here the same `/__rows/<n>` (and every `/__step/...` that writes rows) writes engine-shaped rows WITH it, one of them
deliberately without any and one with more than the six a chip row holds:

    row 1  React Native Developer      "react native, typescript, redux"
    row 2  Mobile Engineer             " react , , node.js,typescript ,a,b,c,d"      (eight entries, two blank: six show)
    row 3  Senior Backend Engineer     ""                                              (a plain row: no button, no panel)
    row 4  Full Stack Developer        "python, django"
    row 5  Platform Engineer           "go, kubernetes, terraform"

Everything else in the D7C/D7B harness (scenarios, `/__step/...`, `/__ledger/<n>`, `/__latency/...`) applies unchanged, plus
`/__step/out_of_credit` (a failed run whose key is spent: the one ending those stages did not reach). No provider, no
key, no model call, no paid search, no external network.
"""
import csv
import importlib.util
import io
import os
import pathlib
import sys

REPO = pathlib.Path(os.environ.get("D7B_REPO") or pathlib.Path(__file__).resolve().parents[4]).resolve()
sys.path.insert(0, str(REPO))
os.chdir(REPO)

_spec = importlib.util.spec_from_file_location("d7c_app", REPO / "docs/design/d7c/harness/app.py")
d7c = importlib.util.module_from_spec(_spec)
sys.modules["d7c_app"] = d7c
_spec.loader.exec_module(d7c)
d7b = d7c.d7b

LISTINGS = [
    ("React Native Developer", "Acme Ltd", 42, "linkedin", "Bengaluru, India", "react native, typescript, redux"),
    ("Mobile Engineer", "Beta Labs", 38, "indeed", "Pune, India", " react , , node.js,typescript ,a,b,c,d"),
    ("Senior Backend Engineer", "Gamma", 31, "greenhouse", "Hyderabad, India", ""),
    ("Full Stack Developer", "Delta", 27, "lever", "Chennai, India", "python, django"),
    ("Platform Engineer", "Epsilon", 24, "naukri", "Noida, India", "go, kubernetes, terraform"),
]


def give_rows(self, run_id, n):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["title", "company", "score", "source_site", "url", "location", "date_posted", "matched_skills"])
    for i, (title, company, score, site, where, skills) in enumerate(LISTINGS[:n]):
        w.writerow([title, company, score, site, f"https://x/{i}", where, "2026-09-30", skills])
    with open(os.path.join(self.out_dir(run_id), "jobs_1.csv"), "w", encoding="utf-8") as fh:
        fh.write(buf.getvalue())


d7b.Live.give_rows = give_rows

# One more ending the D7C harness does not reach: `/__step/out_of_credit` is `failed` for a run whose visitor's key has nothing left, so the
# credit is below the cheapest search still outstanding (logic.sweep_state: that, and only that, is "The credit ran out").
_apply_stage = d7c.Live.apply_stage


def apply_stage(self, rid, stage):
    if stage == "out_of_credit":
        room = self.room_of()
        room["credit_total_usd"] = 0.01
        room["key_credit"] = room.get("key_credit") or {"visitor": 0.01}
        stage = "failed"
    return _apply_stage(self, rid, stage)


d7c.Live.apply_stage = apply_stage

if __name__ == "__main__":
    import unittest
    from sweep import public
    r1 = d7c.r1
    for k in ("PARSES_PER_IP_HOUR", "PARSES_PER_IP_DAY", "PARSES_PER_SESSION_HOUR", "PLANS_PER_SESSION_MINUTE",
              "PLANS_PER_IP_MINUTE", "MAX_ROOMS_PER_IP", "DEFAULT_RUNS_PER_IP", "DEFAULT_RUNS_TOTAL",
              "DEFAULT_PER_IP", "DEFAULT_TOTAL"):
        setattr(public, k, 10 ** 6)
    _i = public.SessionStore.__init__
    _i.__defaults__ = tuple(10 ** 6 if d == 10 else d for d in _i.__defaults__)
    r1.setUpModule()
    try:
        unittest.TextTestRunner(verbosity=0).run(d7c.Live())
    finally:
        r1.tearDownModule()
