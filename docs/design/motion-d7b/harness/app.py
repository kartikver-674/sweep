"""D7B capture harness: the real Render public app, served over HTTP, with synthetic data.

    .venv/bin/python docs/design/motion-d7b/harness/app.py            # the working tree, port 5077
    D7B_REPO=/path/to/export D7B_PORT=5177 .venv/bin/python .../app.py  # another tree (an export of the parent commit)

What is real: the application (routes, templates, static files), the worker app on loopback, the Render session
store, the engine's own dry runs. What is replaced: the model (a stub), the provider (sockets are refused by the
suite's own sealed environment), and the engine child (one the harness releases, so a Progress state is a real
worker state, not a mock of one). No provider, no key, no model call, no paid search, no external network.

It is the D3 to D6 scratch harness (which lived outside the repository) consolidated into one file, plus the
scenarios D7B needs. Every scenario is a fresh session:

    GET /__make/<scenario>   -> {"cookie": ...}   set it as the `session` cookie
    GET /__go/<scenario>?to=/path   the same, for a person: sets the cookie and redirects to the page
    GET /__step/<stage>      advance the newest run (Progress): start working some most tail done empty failed timeout stopped partial refused
    GET /__ledger/<n>        n paid searches recorded as done (tiles finish) for the newest run, without ending it
    GET /__rows/<n>          n (at most 5) listings on the run's feed, without ending it
    GET /__latency/<results|estimate|all>/<ms>   hold every answer for that path (a slow server); 0 clears it
    GET /__credit/<token>/<usd>                   what a synthetic Apify token reports as available

Scenarios (see build()): the D3 to D5 set (fresh, all_ready, all_reviewed, failed, manage3_mixed, free3, paid,
reviewed3, results, c_<free|paid|over|none>_<one|two|multi>, p_<free|paid>_<one|two|multi>_<stage>), the D6
Results set (m_all, m_long, m_nopay, m_norec, m_empty, m_emptyview, m_two, m_failed, s1, s1_empty, s1_failed),
and D7B's: m_19 and m_240 (three résumés, 19 and 240 jobs), s1_19 (one résumé, 19 jobs), edge (a key that covers
the default plan with a little to spare, so one more search crosses the cap).
"""
import copy
import csv
import json
import os
import pathlib
import random
import sys
import threading
import time
import types
from datetime import date, timedelta

REPO = pathlib.Path(os.environ.get("D7B_REPO") or pathlib.Path(__file__).resolve().parents[4]).resolve()
sys.path.insert(0, str(REPO))
os.chdir(REPO)

from werkzeug.serving import make_server  # noqa: E402

import scraper  # noqa: E402
from deploy import sweep_worker  # noqa: E402
from sweep import public, worker_client  # noqa: E402
from sweep import runs as runs_mod  # noqa: E402
from sweep.tests import test_batch_upload as b1  # noqa: E402
from sweep.tests import test_multi_render as r1  # noqa: E402
from sweep.tests import test_multi_results_view as rv  # noqa: E402
from sweep.tests import test_multi_setup as u1  # noqa: E402
from sweep.tests.test_one_track_goldens import derived_for  # noqa: E402
from sweep.tests.test_worker_link import cookie_of, render_app  # noqa: E402

PORT = int(os.environ.get("D7B_PORT", "5077"))
IDS = ("a" * 16, "b" * 16, "c" * 16)
A, B, C = IDS
JSON = {"Accept": "application/json"}
FILES = {"ada": "backend_resume.pdf", "bhaskar": "mern_fullstack_resume_2026.pdf", "chen": "platform_sre_resume.pdf"}
NAMES = {"ada": "Backend Engineer", "bhaskar": "MERN Stack Developer", "chen": "Applied AI Engineer"}
LONG_FILE = "kartik_verma_fullstack_payments_fintech_resume_final_v7.pdf"
LONG_LABEL = "Senior Full Stack Developer, Payments UK"
LONG_NAME = "Senior Full Stack Developer (Payments)"

STATE = {"delay": 0.0, "fail": None}
CHILD = {}                       # run_id -> {"ev": Event, "code": int}
CREDIT = {"apify_api_ok": 42.0, "apify_api_low": 3.0, "apify_api_none": 0.05, "apify_api_edge": 7.0}
FLAGS = {"nopaid": False}
AUTO = {"on": False}             # the older scenarios expect an engine child that finishes at once
LATENCY = {"results": 0, "estimate": 0, "all": 0}


# ---- the engine child: blocked until the harness releases it ---------------------------------------------------
def spawn(self, run_id, run_dir, profile_name, checkout, tokens, **kw):
    info = {"ev": threading.Event(), "code": 0}
    CHILD[run_id] = info
    if AUTO["on"]:
        info["ev"].set()

    def wait():
        info["ev"].wait()
        return info["code"]

    def terminate():
        info["code"] = 143
        info["ev"].set()
    self.spawned.append({"run_id": run_id, "profile": profile_name, "tokens": tokens, **kw})
    return types.SimpleNamespace(wait=wait, terminate=terminate), None


r1.Worker.spawn = spawn
_plan, _tracks = worker_client.plan, worker_client.plan_tracks


def _strip(raw):
    if FLAGS["nopaid"] and isinstance(raw, dict):
        raw = dict(raw)
        raw.pop("public_paid", None)
    return raw


worker_client.plan = lambda *a, **k: _strip(_plan(*a, **k))
worker_client.plan_tracks = lambda *a, **k: _strip(_tracks(*a, **k))


# ---- synthetic jobs ---------------------------------------------------------------------------------------------
# The D6 set (fourteen rows, every recommendation situation) and the D7A generator (19 or 240 rows, engine-shaped).
SK = {A: "python, django, postgresql, redis, docker, kafka, aws", B: "react, node.js, typescript, mongodb, express",
      C: "python, pytorch, llm, rag, docker, kubernetes"}


def R(n, title, company, where, best, scores, rec=None, kind=None, caution=None, pay="", exp="", site="linkedin",
      posted="2026-09-27", scope="", skills=None, url=None):
    evals = {t: {"s": s, "m": (skills or {}).get(t, SK[t])} for t, s in scores.items()}
    row = {"title": title, "company": company, "location": where, "source_site": site,
           "apply_url": url or f"https://jobs.example.test/{n}", "date_posted": posted,
           "score": scores[best], "matched_skills": evals[best]["m"], "best_track": best,
           "track_evals": json.dumps(evals, separators=(",", ":")), "found_by": best,
           "salary": pay, "experience_required": exp, "remote_scope": scope}
    if rec:
        row.update(recommended_tracks=";".join(rec), recommendation=kind)
        if caution is not None:
            row["recommendation_caution"] = caution
    return row


NF = "no_focus_evidence"
ALL = [
    R(1, "Staff Backend Engineer", "Kestrel Payments", "Bengaluru, India", A, {A: 104, B: 41, C: 30}, [A], "clear", "", "INR 45–60 LPA", "8+", "linkedin", "2026-09-28"),
    R(2, "Senior Backend Engineer", "Halden Labs", "Pune, India", A, {A: 62, B: 31}, [A], "clear", "", "INR 28–36 LPA", "5+", "indeed", "2026-09-27"),
    R(3, "Platform Engineer", "Orrin Health", "Hyderabad, India", A, {A: 55, B: 53}, [A, B], "close", "", "", "4+", "greenhouse", "2026-09-25"),
    R(4, "Product Engineer", "Brightwell", "Bengaluru, India", B, {B: 47, A: 46, C: 44}, [B, A, C], "close", "", "INR 18–24 LPA", "3–5", "lever", "2026-09-24"),
    R(5, "Full Stack Developer", "Mallow Cloud", "Noida, India", B, {B: 51, A: 49, C: 10}, [B, A], "split", "", "", "", "naukri", "2026-09-22"),
    R(6, "Software Engineer", "Quillfeather", "Mumbai, India", A, {A: 45, B: 40, C: 38}, [A, B, C], "split", "", "", "", "linkedin", "2026-09-20"),
    R(7, "Software Engineer II", "Pebble Grid", "Bengaluru, India", A, {A: 47, B: 47, C: 47}, [A, B, C], "tied", "", "", "", "greenhouse", "2026-09-19"),
    R(8, "Data Platform Engineer", "Ostrava Systems", "Chennai, India", A, {A: 39, C: 39}, [A, C], "tied", "", "", "2–4", "lever", "2026-09-10"),
    R(9, "Principal Software Engineer, Distributed Systems and Developer Platform (Remote, India)",
      "Tarn & Co Infrastructure Research Group International", "Gurugram, India", A, {A: 44, B: 12}, [A], "clear", NF,
      "INR 40–55 LPA", "8+", "linkedin", "2026-09-05"),
    R(10, "Machine Learning Engineer", "Fenwick Analytics", "Gurugram, India", C, {C: 33, A: 33}, [C, A], "tied", NF, "", "", "indeed", "2026-09-03"),
    R(11, "Support Engineer", "Loam Software", "Indore, India", A, {A: 7, B: 2}, [A], "clear", "", "", "", "greenhouse", "2026-08-29"),
    R(12, "QA Automation Engineer", "Pebble Grid", "Bengaluru, India", A, {A: -3, B: -5}, [A], "clear", "", "", "2–4", "greenhouse", "2026-08-20"),
    R(13, "Full Stack Engineer", "Northwind Remote", "Remote", B, {B: 37, A: 30}, [B], "clear", "", "USD 70–90k", "4+", "lever", "2026-09-26", "worldwide"),
    R(14, "Senior Software Engineer", "Kleist GmbH", "Berlin, Germany", A, {A: 28, B: 20}, [A, B], "close", "", "EUR 70–85k", "6+", "linkedin", "2026-09-15"),
]
LONG = [
    R(1, "Principal Software Engineer, Distributed Systems and Developer Platform (Remote, India)",
      "Tarn & Co Infrastructure Research Group International", "Gurugram, India", A, {A: 62, B: 40}, [A, B], "split", NF,
      "INR 40–55 LPA", "8+", "linkedin", "2026-09-28",
      skills={A: "python, distributed-systems, kubernetes, terraform, grpc, postgresql, kafka, redis, aws, golang"}),
    R(2, "Backend Engineer", "Halden Labs", "Pune, India", A, {A: 48, B: 30}, [A], "clear", NF, "", "", "greenhouse", "2026-09-27"),
    R(3, "Platform Engineer", "Orrin Health", "Hyderabad, India", B, {B: 41, A: 40}, [B, A], "close", "", "", "5+", "lever", "2026-09-26"),
    R(4, "Software Engineer", "Brightwell", "Bengaluru, India", A, {A: -3, B: -5, C: -8}, [A, B, C], "tied", NF, "", "", "indeed", "2026-09-25"),
]
NOPAYEXP = [dict(r, salary="", experience_required="") for r in ALL[2:8]]
MULTI_ONLY = set(scraper.MULTI_COLUMNS) | {"recommended_tracks", "recommendation", "recommendation_caution"}
LEGACY = [{k: v for k, v in r.items() if k not in MULTI_ONLY} for r in
          [ALL[0], ALL[1], ALL[2], ALL[3], ALL[4], ALL[8], ALL[10], ALL[12], ALL[13]]]

TITLES = {
    A: ["Senior Backend Engineer", "Backend Engineer, Payments", "Python Developer", "Staff Software Engineer, APIs",
        "Backend Engineer (Django)", "Software Engineer II, Data Services", "Principal Engineer, Billing"],
    B: ["Full Stack Engineer", "Senior Full Stack Developer", "Frontend Engineer, Growth", "Software Engineer, Web",
        "Product Engineer", "Full Stack Developer (React, Node)"],
    C: ["Platform Engineer", "Site Reliability Engineer", "Infrastructure Engineer", "Senior DevOps Engineer",
        "Cloud Platform Engineer", "Kubernetes Engineer"],
}
SKILLS = {A: ["python", "django", "postgresql", "aws", "rest apis", "celery", "redis"],
          B: ["react", "node.js", "typescript", "graphql", "next.js", "tailwind"],
          C: ["go", "kubernetes", "terraform", "aws", "prometheus", "linux"]}
COMPANIES = ["Kestrel", "Halcyon Freight", "Marrow Labs", "Northwind Ledger", "Tessellate", "Ostrava Systems", "Fennel",
             "Pinecrest Health", "Quillon", "Brightwater", "Lumen & Co", "Vantage Ridge", "Copperline", "Alder Analytics",
             "Stonebridge", "Hollow Oak", "Meridian Works", "Tallow", "Juniper Row", "Cobalt Harbour"]
INDIA = ["Bengaluru, India", "Pune, India", "Hyderabad, India", "Gurugram, India (Hybrid)", "Mumbai, India",
         "Chennai, India", "Noida, India"]
ABROAD = ["Berlin, Germany", "Amsterdam, Netherlands", "Toronto, Canada", "Dublin, Ireland"]
PAY = ["", "", "INR 18-26 LPA", "INR 28-40 LPA", "", "INR 45-60 LPA", ""]
EXP = ["", "3-5", "5-8", "8+", "", "2-4", ""]
SITES = ["greenhouse", "lever", "ashby", "linkedin", "naukri", "indeed"]


def make_rows(n, seed=7):
    """`n` engine rows, best-score first (the D7A generator): ~60% India, ~25% remote, the rest abroad; every
    recommendation state; a negative score or two. Fictional people, companies and postings."""
    rng = random.Random(seed)
    today = date(2026, 9, 30)
    rows = []
    for i in range(n):
        best = rng.choice([A, A, B, C, B, A, C])
        top = 62 - int(i * 58 / max(n - 1, 1)) + rng.randint(-1, 1)
        scores = {best: top}
        for t in (A, B, C):
            if t != best and rng.random() < 0.72:
                scores[t] = top - rng.choice([0, 1, 3, 6, 9, 14, 20])
        ranked = sorted(scores, key=lambda t: -scores[t])
        gap = scores[ranked[0]] - (scores[ranked[1]] if len(ranked) > 1 else -99)
        if len(ranked) == 1 or gap >= 6:
            rec, kind = [ranked[0]], "clear"
        elif gap == 0:
            rec, kind = ranked[: min(len(ranked), 3)], "tied"
        elif gap <= 2:
            rec, kind = ranked[:2], "close"
        else:
            rec, kind = ranked[:2], "split"
        caution = "no_focus_evidence" if i % 7 == 3 else ""
        roll = rng.random()
        if roll < 0.60:
            where, scope = rng.choice(INDIA), ""
        elif roll < 0.85:
            where, scope = "Remote", "worldwide"
        else:
            where, scope = rng.choice(ABROAD), ""
        row = rv.job(i + 1, best, scores, rec, kind, caution)
        row.update({
            "title": rng.choice(TITLES[best]), "company": COMPANIES[i % len(COMPANIES)],
            "location": where, "remote_scope": scope,
            "salary": rng.choice(PAY), "experience_required": rng.choice(EXP),
            "source_site": rng.choice(SITES),
            "matched_skills": ", ".join(rng.sample(SKILLS[best], rng.randint(3, 6))),
            "date_posted": (today - timedelta(days=rng.randint(0, 9))).isoformat(),
            "apply_url": f"https://jobs.example.test/{i + 1}",
        })
        evals = {t: {"s": s, "m": ", ".join(rng.sample(SKILLS[t], rng.randint(3, 6)))} for t, s in scores.items()}
        evals[best]["m"] = row["matched_skills"]
        row["track_evals"] = json.dumps(evals, separators=(",", ":"))
        rows.append(row)
    return rows


# ---- the stack ------------------------------------------------------------------------------------------------------
class Live(rv.Results):
    # the app's own daily per-IP beta limits would refuse the dozens of sessions a capture run builds;
    # raised for THIS harness only
    FLAGS = dict(rv.Results.FLAGS, **{public.PER_IP_ENV: "1000000", public.TOTAL_ENV: "1000000"})

    def render(self):
        self.derived_texts, self.failing, self.while_reading = [], set(), None
        self.extracted = []

        def extract(path):
            with open(path, "rb") as fh:
                raw = fh.read()[len(b"%PDF-1.7 "):]
            try:
                who = raw.decode()
            except UnicodeDecodeError:
                # A real PDF picked by a person trying the page: it reads as the first sample résumé.
                return next(iter(u1.TEXT.values()))
            return {"blank": "  ", **u1.TEXT}.get(who, who)

        def derive(text, prefs):
            time.sleep(STATE["delay"])
            who = next(k for k, v in u1.TEXT.items() if v == text)
            f = STATE["fail"]
            if f == who:
                raise RuntimeError("the model did not answer")
            if f == "limit:" + who:
                raise public.BetaLimited("Today's limit of résumé reads has been reached. It resets tomorrow.")
            return copy.deepcopy(derived_for(u1.PERSONA[who]))

        return render_app(self.worker.url, check_token=lambda token: (CREDIT.get(token, 42.0), None),
                          extract=extract, derive=derive)

    # ---- setup helpers (D3, D4) --------------------------------------------------------------------------
    def new(self):
        c = self.app.test_client()
        c.post("/beta", data={"code": r1.CODE})
        self.client = c
        return c

    def put(self, *whos):
        self.new()
        with u1.fixed_ids(*IDS[:len(whos)]):
            self.client.post("/resume", data={"resume": [b1.part(w, FILES[w]) for w in whos]},
                             content_type="multipart/form-data")

    def put_named(self, pairs):
        self.new()
        with u1.fixed_ids(*IDS[:len(pairs)]):
            self.client.post("/resume", data={"resume": [b1.part(w, n) for w, n in pairs]},
                             content_type="multipart/form-data")

    def read(self, n=1):
        for _ in range(n):
            self.client.post("/derive", headers=JSON)

    def save(self, *tids):
        for t in tids:
            self.client.post(f"/review?track={t}", data=u1.EDIT)

    def paid_key(self):
        self.client.post("/key", data={"token": "apify_api_synthetic_token_for_layout_only", "back": "configure"})

    # ---- setup helpers (D5) --------------------------------------------------------------------------------
    def room_of(self, client=None):
        client = client or self.client
        client.get("/activity")
        with client.session_transaction() as sess:
            sid = sess["sid"]
        return self.app.session_store._rooms[sid]["data"]

    def drain(self):
        for _ in range(1000):
            for info in CHILD.values():
                info["ev"].set()
            if all(r["state"] in sweep_worker.TERMINAL for r in self.worker.store.all()):
                return
            time.sleep(0.02)
        raise AssertionError("the worker never went idle")

    def out_dir(self, run_id):
        d = self.worker.store.output_dir(run_id)
        os.makedirs(d, exist_ok=True)
        return d

    def settle(self, run_id, states, tries=400):
        for _ in range(tries):
            if self.worker.store.read(run_id)["state"] in states:
                return
            time.sleep(0.02)
        raise AssertionError(f"{run_id} never reached {states}: {self.worker.store.read(run_id)['state']}")

    def give_ledger(self, run_id, room, n):
        keys = runs_mod.combo_keys(room["raw_plan"], runs_mod.today())[:n]
        with open(os.path.join(self.out_dir(run_id), ".done_combos"), "w") as fh:
            fh.write("".join(k + "\n" for k in keys))
        return len(keys), len(runs_mod.combo_keys(room["raw_plan"], runs_mod.today()))

    def give_rows(self, run_id, n):
        rows = ["title,company,score,source_site,url,location,date_posted"]
        names = [("React Native Developer", "Acme Ltd", 42, "linkedin", "Bengaluru, India"), ("Mobile Engineer", "Beta Labs", 38, "indeed", "Pune, India"),
                 ("Senior Backend Engineer", "Gamma", 31, "greenhouse", "Hyderabad, India"), ("Full Stack Developer", "Delta", 27, "lever", "Chennai, India"),
                 ("Platform Engineer", "Epsilon", 24, "naukri", "Noida, India")]
        for i in range(min(n, len(names))):
            t, c, s, site, where = names[i]            # every row reachable from India, so Results opens its first section
            rows.append(f'{t},{c},{s},{site},https://x/{i},"{where}",2026-09-30')
        with open(os.path.join(self.out_dir(run_id), "jobs_1.csv"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(rows) + "\n")

    def give_auth(self, run_id, **fields):
        with open(os.path.join(self.out_dir(run_id), sweep_worker.AUTH_RECORD), "w") as fh:
            json.dump(fields, fh)

    def token(self, name):
        self.client.post("/key", data={"token": name, "back": "configure"})

    def setup(self, n, paid=None, key="apify_api_ok"):
        """n reviewed résumés, free or paid (a key), configured, and ready for Confirm."""
        whos = ("ada", "bhaskar", "chen")[:n]
        self.put(*whos)
        self.read(n)
        self.save(*IDS[:n])
        if paid:
            self.token(key)
        else:
            self.client.post("/key/free")
        self.client.post("/configure", data=r1.FORMS["india"])

    def start(self, **form):
        self.client.get("/confirm")
        return self.client.post("/run", data=form)

    def running(self, n, paid, key="apify_api_ok", **form):
        self.setup(n, paid, key)
        r = self.start(**form)
        assert r.status_code == 302, (r.status_code, r.get_data(as_text=True)[:300])
        rid = self.cookie()["run_id"]
        self.settle(rid, {"running", "queued"})
        return rid

    def age(self, seconds):
        self.room_of()["run_started_at"] = time.time() - seconds

    def newest(self):
        return max(self.worker.store.all(), key=lambda r: r.get("created_at") or r.get("started_at") or 0)["run_id"]

    # ---- D6: Results ---------------------------------------------------------------------------------------
    def multi(self, whos, names, rows=ALL, recommend=True, caution=True, state=None):
        self.new()
        with u1.fixed_ids(*IDS[:len(whos)]):
            self.free(*whos)
        self.confirm()
        self.client.post("/run")
        self.run_id = self.cookie()["run_id"]
        self.settled(self.run_id)
        for tid, name in zip(IDS, names):
            self.act(tid, "rename", name=name)
        self.serve(rows, recommend=recommend, caution=caution)
        if state:
            self.worker.store.update(self.run_id, state=state)

    def legacy(self, rows, state=None):
        self.new()
        self.add("ada")
        self.client.post("/key/free")
        self.client.post("/configure", data=r1.FORMS["india"])
        self.client.post("/run")
        self.run_id = self.cookie()["run_id"]
        self.settled(self.run_id)
        out = self.worker.store.output_dir(self.run_id)
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "jobs_2026-09-28_1200.csv"), "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=scraper.OUTPUT_COLUMNS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        if state:
            self.worker.store.update(self.run_id, state=state)

    # ---- the scenarios ---------------------------------------------------------------------------------------
    def build(self, name):
        STATE["delay"], STATE["fail"] = 0.0, None
        FLAGS["nopaid"] = False
        AUTO["on"] = not name.startswith(("c_", "p_"))
        self.drain()
        a, b, c = IDS
        three = ("ada", "bhaskar", "chen")
        names3 = [NAMES[w] for w in three]
        if name.startswith("c_"):
            kind, n = name[2:].rsplit("_", 1)
            n = {"one": 1, "multi": 3, "two": 2}[n]
            if kind == "free":
                self.setup(n, False)
            elif kind == "paid":
                self.setup(n, True)
            elif kind == "over":
                self.setup(n, True, "apify_api_low")
            elif kind == "none":
                self.setup(n, True, "apify_api_none")
            else:
                raise KeyError(name)
            return
        if name.startswith("p_"):
            _, mode, n, stage = name.split("_", 3)
            n, paid = {"one": 1, "two": 2, "multi": 3}[n], mode == "paid"
            if stage == "queued":
                self.running(1, False)
                rid = self.running(n, paid)
                assert self.worker.store.read(rid)["state"] == "queued"
                return
            rid = self.running(n, paid)
            self.apply_stage(rid, stage)
            return
        # D6 / D7B Results
        if name == "m_all":
            self.multi(three, names3)
        elif name == "m_19":
            self.multi(three, names3, rows=make_rows(19))
        elif name == "m_240":
            self.multi(three, names3, rows=make_rows(240, seed=11))
        elif name == "s1_19":
            self.legacy([{k: v for k, v in r.items() if k not in MULTI_ONLY} for r in make_rows(19)])
        elif name == "m_nopay":
            self.multi(three, names3, rows=NOPAYEXP)
        elif name == "m_long":
            self.multi(three, [LONG_NAME, NAMES["bhaskar"], NAMES["chen"]], rows=LONG)
        elif name == "m_norec":
            self.multi(three, names3, recommend=False, caution=False)
        elif name == "m_empty":
            self.multi(three, names3, rows=[])
        elif name == "m_emptyview":
            self.multi(three, names3, rows=[R(1, "Backend Engineer", "Halden Labs", "Pune, India", A, {A: 48, B: 30}, [A], "clear", "")])
        elif name == "m_two":
            self.multi(("ada", "bhaskar"), [NAMES["ada"], NAMES["bhaskar"]],
                       rows=[r for r in ALL if set(json.loads(r["track_evals"])) <= {A, B}])
        elif name == "m_failed":
            self.multi(three, names3, state="failed")
        elif name == "s1":
            self.legacy(LEGACY)
        elif name == "s1_empty":
            self.legacy([])
        elif name == "s1_failed":
            self.legacy(LEGACY, state="failed")
        # D3 / D4
        elif name == "waiting":
            self.put(*three)
        elif name == "one_ready":
            self.put(*three); self.read(1)
        elif name == "all_ready":
            self.put(*three); self.read(3)
        elif name == "mixed":
            self.put(*three); self.read(2); self.save(a)
        elif name == "two_reviewed":
            self.put(*three); self.read(3); self.save(a, b)
        elif name == "all_reviewed":
            self.put(*three); self.read(3); self.save(a, b, c)
        elif name == "failed":
            self.put(*three); self.read(1)
            STATE["fail"] = "bhaskar"; self.read(1); STATE["fail"] = None
            self.read(1)
            self.client.post("/tracks", data={"track": c, "do": "deselect", "back": "review"})
        elif name == "limited":
            self.put(*three); self.read(1)
            STATE["fail"] = "limit:bhaskar"; self.read(1); STATE["fail"] = None
        elif name in ("configured", "confirmed", "running", "results"):
            self.new()
            with u1.fixed_ids(*IDS):
                self.free(*three)
            if name != "configured":
                self.confirm()
                if name in ("running", "results"):
                    self.client.post("/run")
                    if name == "results":
                        self.run_id = self.cookie()["run_id"]
                        self.settled(self.run_id)
                        self.serve()
        elif name == "fresh":
            self.new()
        elif name == "single":
            self.new()
            self.client.post("/resume", data=u1.pdf("ada", FILES["ada"]), content_type="multipart/form-data")
        elif name == "manage1":
            self.put("ada")
        elif name == "manage2":
            self.put("ada", "bhaskar")
        elif name == "manage3":
            self.put(*three)
        elif name == "manage1_reviewed":
            self.put("ada"); self.read(1); self.save(a)
        elif name == "manage2_mixed":
            self.put("ada", "bhaskar"); self.read(2); self.save(a)
        elif name == "manage3_mixed":
            self.put(*three); self.read(2); self.save(a)
        elif name == "manage3_long":
            self.put_named([("ada", LONG_FILE), ("bhaskar", FILES["bhaskar"]), ("chen", FILES["chen"])])
            self.read(3); self.save(a, b, c)
            self.client.post("/tracks", data={"track": a, "do": "rename", "name": LONG_LABEL})
        elif name == "manage3_left_out":
            self.put(*three); self.read(3); self.save(a, b, c)
            self.client.post("/tracks", data={"track": b, "do": "deselect", "back": "upload"})
        elif name == "manage3_failed":
            self.put(*three); self.read(1)
            STATE["fail"] = "bhaskar"; self.read(1); STATE["fail"] = None
        elif name == "paid":
            self.put(*three); self.read(3); self.save(a, b, c); self.paid_key()
        elif name == "paid_one":
            self.put("ada"); self.read(1); self.save(a); self.paid_key()
        elif name == "free_one":
            self.put("ada"); self.read(1); self.save(a); self.client.post("/key/free")
        elif name == "free3":
            self.put(*three); self.read(3); self.save(a, b, c); self.client.post("/key/free")
        elif name == "reviewed3":
            self.put(*three); self.read(3); self.save(a, b, c)
        elif name == "edge":
            # a paid key that covers the default plan with a little to spare: one more search crosses the cap
            self.put(*three); self.read(3); self.save(a, b, c); self.token("apify_api_edge")
        else:
            raise KeyError(name)

    def apply_stage(self, rid, stage):
        for _ in range(300):                      # the worker says "queued" a moment before it spawns the child
            if rid in CHILD:
                break
            time.sleep(0.02)
        room = self.room_of()
        if stage == "start":
            self.age(3)
        elif stage == "working":
            self.age(95)
        elif stage == "some":
            self.age(400); self.give_ledger(rid, room, 5); self.give_rows(rid, 4)
        elif stage == "most":
            self.age(900)
            done, total = self.give_ledger(rid, room, 10 ** 6)
            self.give_ledger(rid, room, total - 2); self.give_rows(rid, 5)
        elif stage == "tail":
            self.age(1300); self.give_ledger(rid, room, 10 ** 6); self.give_rows(rid, 5)
        elif stage == "done":
            self.age(1500); self.give_ledger(rid, room, 10 ** 6); self.give_rows(rid, 5)
            CHILD[rid]["ev"].set(); self.settle(rid, {"done"})
        elif stage == "empty":
            self.age(1500); self.give_ledger(rid, room, 10 ** 6)
            CHILD[rid]["ev"].set(); self.settle(rid, {"done"})
        elif stage == "failed":
            self.age(600); self.give_ledger(rid, room, 3); self.give_rows(rid, 2)
            CHILD[rid]["code"] = 1; CHILD[rid]["ev"].set(); self.settle(rid, {"failed"})
        elif stage == "timeout":
            self.age(7300); self.give_ledger(rid, room, 4); self.give_rows(rid, 3)
            CHILD[rid]["code"] = 1; CHILD[rid]["ev"].set(); self.settle(rid, {"failed"})
            self.worker.store.update(rid, error=sweep_worker.RUN_TIMEOUT)
        elif stage == "stopped":
            self.age(500); self.give_ledger(rid, room, 3); self.give_rows(rid, 2)
            self.client.post("/stop"); self.settle(rid, {"stopped"})
        elif stage == "partial":
            self.age(900)
            done, total = self.give_ledger(rid, room, 10 ** 6)
            self.give_ledger(rid, room, total - 3); self.give_rows(rid, 4)
            self.give_auth(rid, outcome="partial", partial_authorized_by_user=True, total_planned_paid_units=total,
                           placeable_paid_units=total - 3, skipped_insufficient_capacity=3, skipped_budget=0,
                           executed_paid_units=total - 3, partial_estimate_usd=4.21, full_estimate_usd=7.02)
            CHILD[rid]["ev"].set(); self.settle(rid, {"done"})
        elif stage == "refused":
            self.age(40)
            done, total = self.give_ledger(rid, room, 0)
            self.give_auth(rid, outcome="refused", total_planned_paid_units=total, placeable_paid_units=0,
                           skipped_insufficient_capacity=total, executed_paid_units=0, full_estimate_usd=7.02)
            CHILD[rid]["code"] = 4; CHILD[rid]["ev"].set(); self.settle(rid, {"failed"})
        else:
            raise KeyError(stage)

    # ---- the server -----------------------------------------------------------------------------------------
    def runTest(self):
        inner = self.app.wsgi_app
        me = self

        def app(environ, start):
            path = environ["PATH_INFO"]
            if path.startswith("/__"):
                parts = path.split("/")[1:]
                cmd, arg = parts[0], parts[1:]
                if cmd == "__go":
                    # For a person in a real browser (A11's manual check): build the scenario, hand this browser its
                    # session cookie, and land on the page. Only a same-site path is followed.
                    from urllib.parse import parse_qs
                    me.build(arg[0])
                    to = parse_qs(environ.get("QUERY_STRING", "")).get("to", ["/"])[0]
                    if not to.startswith("/") or to.startswith("//"):
                        to = "/"
                    start("302 Found", [("Location", to),
                                        ("Set-Cookie", f"session={cookie_of(me.client)}; Path=/; HttpOnly; SameSite=Lax")])
                    return [b""]
                body = {"ok": True}
                try:
                    if cmd == "__make":
                        me.build(arg[0]); body["cookie"] = cookie_of(me.client)
                    elif cmd == "__step":
                        me.apply_stage(me.newest(), arg[0])
                    elif cmd == "__ledger":
                        rid = me.newest(); me.give_ledger(rid, me.room_of(), int(arg[0]))
                    elif cmd == "__rows":
                        me.give_rows(me.newest(), int(arg[0]))
                    elif cmd == "__latency":
                        LATENCY[arg[0]] = int(arg[1]) / 1000.0
                    elif cmd == "__credit":
                        CREDIT[arg[0]] = float(arg[1])
                    elif cmd == "__nopaid":
                        FLAGS["nopaid"] = arg[0] == "1"
                except Exception as exc:              # the harness says what it could not build
                    import traceback
                    body = {"ok": False, "error": repr(exc), "trace": traceback.format_exc()[-1500:]}
                start("200 OK", [("Content-Type", "application/json")])
                return [json.dumps(body).encode()]
            hold = LATENCY["all"] or (LATENCY["results"] if path == "/results" else 0) \
                or (LATENCY["estimate"] if path == "/estimate" else 0)
            if hold:
                time.sleep(hold)
            return inner(environ, start)

        self.app.wsgi_app = app
        srv = make_server("127.0.0.1", PORT, self.app, threaded=True)
        print("READY", PORT, flush=True)
        srv.serve_forever()


if __name__ == "__main__":
    import unittest
    for k in ("PARSES_PER_IP_HOUR", "PARSES_PER_IP_DAY", "PARSES_PER_SESSION_HOUR", "PLANS_PER_SESSION_MINUTE",
              "PLANS_PER_IP_MINUTE", "MAX_ROOMS_PER_IP", "DEFAULT_RUNS_PER_IP", "DEFAULT_RUNS_TOTAL",
              "DEFAULT_PER_IP", "DEFAULT_TOTAL"):
        setattr(public, k, 10 ** 6)
    _i = public.SessionStore.__init__
    _i.__defaults__ = tuple(10 ** 6 if d == 10 else d for d in _i.__defaults__)
    r1.setUpModule()
    try:
        unittest.TextTestRunner(verbosity=0).run(Live())
    finally:
        r1.tearDownModule()
