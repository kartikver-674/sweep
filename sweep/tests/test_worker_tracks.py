"""Multi-Track Phase 4 (P4-W1): the sweep worker's `tracks` contract.

`tracks` in place of `profile` is Render's engine-ready TRACKS entries. The
worker validates them (check_tracks), writes them with the Sweep's preferences
as ONE schema-2 profile (make_profile.render_tracks), prices it with the
engine's own dry run — which must attest plan_version 2 and a plan_hash, or
the engine is stale and refused — and binds a run to it: a preflight dry run
of the very file the run executes decides whether expected_plan_hash is
required (any provider search) and checks it whenever given, and the child
carries it as SWEEP_EXPECTED_PLAN_HASH, whose exit 4 is "plan_changed".

Every dry run and run child here is the REAL engine in a fresh interpreter,
sockets refused (test_engine_propagation's technique), in exactly the
environment the worker built; a run child's acquisition and account entry
points are tripwires. The worker's own environment is sealed and synthetic:
no .env, no real credential. Tracks and jobs are synthetic.
"""
import ast
import copy
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

import scraper
import skill_concepts
import title_gate
from deploy import sweep_worker
from deploy.test_sweep_worker import PREFS, PROFILE
from sweep.tests import test_multi_results as mr
from sweep.tests.test_one_track_goldens import REPO, derived_for

sys.path.insert(0, os.path.join(REPO, "auto-apply"))
import make_profile  # noqa: E402

WORKER_TOKEN = "p4w1-worker-bearer"
KEY = "apify_api_P4W1FAKEKEY0123456789abcdef"      # never valid, never reaches a socket
OPERATOR = {"APIFY_TOKEN": "p4w1-operator-key-1", "APIFY_TOKEN_2": "p4w1-operator-key-2",
            "SWEEP_PAID_ACCOUNT_CAP_USD": "3", "SWEEP_BYOK_CREDENTIALS": "stdin"}
RECOMMEND, CAUTION = scraper.RECOMMENDATION_FLAG, scraper.CAUTION_FLAG
RENDER_FLAGS = (make_profile.TRACK_SEARCH_FLAG, make_profile.TRACK_SCORING_FLAG,
                make_profile.TRACK_ALIGNMENT_FLAG, title_gate.FLAG)
STALE_HASH = "0" * 64
MERN, MOBILE, AI = mr.MERN, mr.MOBILE, mr.AI


def entry(tid, keywords, years, hints, skills, engine="v2", focus=None):
    """One engine-ready TRACKS entry; `focus` = (concept, qualifier, title)
    adds POSITIONING and ALIGNMENT."""
    t = {"id": tid, "engine": engine,
         "SEARCH": {"role_keywords": list(keywords), "experience_years": years},
         "SETTINGS": {"max_experience_years": years + 3,
                      "candidate_experience_months": years * 12 + 4},
         "SCORING": {"skill_weights": dict(skills), "penalty_terms": {"salesforce": -5},
                     "frontend_terms": [], "backend_terms": [],
                     "fullstack_title_terms": [], "fullstack_bonus": 0},
         "ATS_TITLE_HINTS": list(hints), "ATS_TITLE_EXCLUDE": ["intern"]}
    if focus:
        concept, qualifier, title = focus
        t["POSITIONING"] = {"concepts": [concept], "role_qualifiers": [qualifier]}
        t["ALIGNMENT"] = {"role_titles": [title]}
    return t


# "react developer" is asked by all three: one Indeed request (Indeed reads no
# experience), and on LinkedIn one for MERN and Mobile (2 years) and another
# for AI (6 years) — test_multi_plan's shape, as the wire carries it.
SPECS = ((MERN, ["mern stack developer", "react developer"], 2, ["mern", "react"],
          {"react": 5, "mongodb": 3}, "v2", ("mongodb", "mern stack", "mern stack developer")),
         (MOBILE, ["react native developer", "react developer"], 2, ["mobile", "react native"],
          {"react native": 5, "kotlin": 4}, "v2",
          ("kotlin", "react native", "react native developer")),
         (AI, ["machine learning engineer", "react developer"], 6, ["machine learning"],
          {"python": 5, "pytorch": 4}, "v1",
          ("pytorch", "machine learning", "machine learning engineer")))
FOCUSED = make_profile.check_tracks([entry(*s) for s in SPECS])
BARE = make_profile.check_tracks([entry(*s[:6]) for s in SPECS])
TWO = FOCUSED[:2]

BOOT = (
    "import os, socket, sys\n"
    "def _no(*a, **k):\n"
    "    raise RuntimeError('a worker child must not open a connection')\n"
    "socket.socket.connect = _no\n"
    "socket.create_connection = _no\n"
    "checkout, repo, trip = sys.argv[1:4]\n"
    "sys.argv = ['scraper.py'] + sys.argv[4:]\n"
    "sys.path[:0] = [checkout, repo, os.path.join(repo, 'auto-apply')]\n"
    "import scraper\n"
    "def tripwire(what):\n"
    "    def fired(*a, **k):\n"
    "        with open(trip, 'a') as fh:\n"
    "            fh.write(what + '\\n')\n"
    "        raise RuntimeError(what)\n"
    "    return fired\n"
    "for name in ('fetch_free', 'fetch_free_multi', 'scrape_search', 'paid_phase_c2',\n"
    "             'byok_tokens', '_require_token', 'account_usage_usd'):\n"
    "    setattr(scraper, name, tripwire(name))\n"
    "scraper.AccountPool.open = tripwire('AccountPool.open')\n"
    "scraper.main()\n")
REAL_RUN, REAL_POPEN = subprocess.run, subprocess.Popen


class Engine:
    """Stands in for the worker's `subprocess` module. Every child is the real
    engine (BOOT) in the environment the worker handed it; each records its
    argv, environment, the file it was given and that file's mode. `canned`
    answers a dry run with (returncode, stdout) instead."""

    SubprocessError = subprocess.SubprocessError
    PIPE, DEVNULL = subprocess.PIPE, subprocess.DEVNULL

    def __init__(self, trip):
        self.trip, self.plans, self.runs, self.canned = trip, [], [], None

    def _seen(self, argv, cwd, env):
        path = os.path.join(cwd, "profiles", f"{argv[3]}.py")
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        return {"argv": list(argv), "env": dict(env), "mode": os.stat(path).st_mode & 0o777,
                "source": source.replace(argv[3], "NAME")}

    def run(self, argv, cwd, env, timeout, **_kw):
        self.plans.append(self._seen(argv, cwd, env))
        if self.canned is not None:
            return subprocess.CompletedProcess(argv, self.canned[0], self.canned[1], "")
        out = REAL_RUN([sys.executable, "-c", BOOT, cwd, REPO, self.trip] + list(argv[2:]),
                       cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
        self.plans[-1]["stdout"] = out.stdout
        return out

    def Popen(self, argv, cwd, env, **kw):
        self.runs.append(self._seen(argv, cwd, env))
        return REAL_POPEN([sys.executable, "-c", BOOT, cwd, REPO, self.trip] + list(argv[2:]),
                          cwd=cwd, env=env, **kw)


class Harness(unittest.TestCase):
    """The real worker app over a temp checkout (profiles/ a package) and a
    sealed, synthetic environment; `spawn` records and starts nothing unless
    a test hands the queue default_spawn."""

    EXTRA_ENV = {}

    def setUp(self):
        # A server's usual umask, so a file's own mode is what is checked.
        self.addCleanup(os.umask, os.umask(0o022))
        self.runs = tempfile.mkdtemp(prefix="p4w1-runs-")
        self.checkout = tempfile.mkdtemp(prefix="p4w1-checkout-")
        self.home = tempfile.mkdtemp(prefix="p4w1-home-")
        for path in (self.runs, self.checkout, self.home):
            self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        os.makedirs(os.path.join(self.checkout, "profiles"))
        open(os.path.join(self.checkout, "profiles", "__init__.py"), "w").close()
        self.trip = os.path.join(self.home, "tripwire")
        env = mock.patch.dict(os.environ, dict(
            {"PATH": "/usr/bin:/bin", "HOME": self.home, "LANG": "en_US.UTF-8",
             "PYTHONDONTWRITEBYTECODE": "1", sweep_worker.TOKEN_ENV: WORKER_TOKEN},
            **OPERATOR, **self.EXTRA_ENV), clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.engine = Engine(self.trip)
        patcher = mock.patch.object(sweep_worker, "subprocess", self.engine)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.spawned = []
        self.store = sweep_worker.RunStore(self.runs)
        self.queue = sweep_worker.Queue(self.store, spawn=self.spawn, checkout=self.checkout)
        self.app = sweep_worker.create_app(store=self.store, queue=self.queue,
                                           accepted={WORKER_TOKEN}, checkout=self.checkout)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def spawn(self, run_id, run_dir, profile_name, checkout, tokens, **kw):
        self.spawned.append({"run_id": run_id, "profile": profile_name,
                             "tokens": tokens, **kw})
        return types.SimpleNamespace(wait=lambda: 0, terminate=lambda: None), None

    def post(self, path, body):
        # As sweep/worker_client sends it: json.dumps, key order kept. (The
        # test client's json= would sort keys, and entry order is data.)
        return self.client.post(path, data=json.dumps(body), content_type="application/json",
                                headers={"Authorization": f"Bearer {WORKER_TOKEN}"})

    def multi(self, path, tracks=FOCUSED, free_only=True, **extra):
        body = {"tracks": copy.deepcopy(list(tracks)), "prefs": PREFS,
                "free_only": free_only, "owner": "session-a", **extra}
        if not free_only and "apify_token" not in body:
            body["apify_token"] = KEY
        return self.post(path, body)

    def plan(self, tracks=FOCUSED, **extra):
        answer = self.multi("/v1/plans", tracks, **extra)
        self.assertEqual(answer.status_code, 200, answer.get_data(as_text=True))
        return answer.get_json()

    def refused(self, answer, status, message):
        self.assertEqual(answer.status_code, status, answer.get_data(as_text=True))
        self.assertEqual(answer.get_json(), {"error": {"message": message}})

    def nothing_left(self):
        """No run, no child, no profile, no tripwire: a refusal did no work."""
        self.assertEqual(self.store.all(), [])
        self.assertEqual(os.listdir(self.runs), [])
        self.assertEqual(os.listdir(os.path.join(self.checkout, "profiles")), ["__init__.py"])
        self.assertEqual((self.spawned, self.engine.runs), ([], []))
        self.assertFalse(os.path.exists(self.trip))

    def status(self, answer):
        self.assertEqual(answer.status_code, 201, answer.get_data(as_text=True))
        return self.store.read(answer.get_json()["run_id"])

    def wait(self, run_id, seconds=90):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            status = self.store.read(run_id)
            if status["state"] in sweep_worker.TERMINAL:
                return status
            time.sleep(0.05)
        self.fail(f"run {run_id} did not finish")


def tracks_of(source):
    return next(ast.literal_eval(n.value) for n in ast.parse(source).body
                if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) == "TRACKS")


# ===========================================================================
class Contract(unittest.TestCase):

    def test_the_worker_names_the_engines_own_values(self):
        self.assertEqual((sweep_worker.PLAN_VERSION, sweep_worker.PLAN_HASH_ENV,
                          sweep_worker.PLAN_CHANGED_EXIT),
                         (scraper.PLAN_VERSION, scraper.PLAN_HASH_ENV, scraper.PLAN_CHANGED_EXIT))
        self.assertEqual((sweep_worker.MIN_TRACKS, sweep_worker.MAX_TRACKS),
                         (2, make_profile.MAX_TRACKS))
        self.assertEqual(sweep_worker.RENDER_TIME_ENV, RENDER_FLAGS)
        for flag in (RECOMMEND, CAUTION):       # execution-time: the child reads them
            self.assertNotIn(flag, sweep_worker.RENDER_TIME_ENV)
        self.assertEqual(sweep_worker.MULTI_FIELDS,
                         {"tracks", "prefs", "free_only", "apify_token", "owner", "key_ids"})


class Materializer(unittest.TestCase):
    """render_tracks is render_sweep's last step, and reads nothing else."""

    PREFS = PREFS

    def derived(self, persona, carriers):
        data = copy.deepcopy(derived_for(persona))
        if carriers:            # the records with_track_* attach, by hand
            data["track_search"] = {"role_keywords": data["role_keywords"][:2]}
            data["track_scoring"] = {"concepts": ["python"], "role_qualifiers": ["backend"]}
            data["track_alignment"] = {"role_titles": ["backend engineer"]}
        return data

    def sweeps(self):
        """render_sweep's source for 2 and 3 personas, every flag state."""
        for n in (2, 3):
            for s, c, a, gate in (("0", "0", "0", "0"), ("0", "0", "0", "1"),
                                  ("1", "1", "1", "0"), ("1", "1", "1", "1")):
                tracks = [{"id": f"{k + 1:x}" * 16, "engine": "v2",
                           "derived": self.derived(p, c == "1")}
                          for k, p in enumerate(["ada-plain", "bhaskar-plain", "chen-plain"][:n])]
                env = dict(zip(RENDER_FLAGS, (s, c, a, gate)))
                with mock.patch.dict(os.environ, env):
                    yield (n, s, c, a, gate), make_profile.render_sweep("p4w1 sweep", tracks,
                                                                        copy.deepcopy(self.PREFS))

    def test_render_sweep_is_render_tracks_of_the_entries_it_built(self):
        seen = set()
        for case, source in self.sweeps():
            with self.subTest(case=case):
                entries = tracks_of(source)
                self.assertEqual(("POSITIONING" in entries[0], "ALIGNMENT" in entries[0]),
                                 (case[2] == "1", case[3] == "1"))
                self.assertEqual(make_profile.render_tracks("p4w1 sweep", entries,
                                                            copy.deepcopy(self.PREFS)), source)
                seen.add(source)
        self.assertEqual(len(seen), 8, "the flags and the title gate must reach render_sweep")

    def test_it_reads_no_resume_no_carrier_and_no_render_time_flag(self):
        sources = dict(self.sweeps())
        entries = tracks_of(sources[(3, "1", "1", "1", "1")])
        refuse = mock.Mock(side_effect=AssertionError("render_tracks derived something"))
        patches = [mock.patch.object(make_profile, name, refuse) for name in (
            "_title_gate", "with_track_search", "with_track_scoring", "_positioning",
            "_alignment", "_search_keywords", "_specialises", "_positions", "_aligns",
            "track_search_enabled", "track_scoring_enabled", "track_alignment_enabled")]
        patches.append(mock.patch.object(title_gate, "enabled", refuse))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        got = set()
        for values in (("0",) * 4, ("1",) * 4, ("1", "0", "1", "0")):
            with mock.patch.dict(os.environ, dict(zip(RENDER_FLAGS, values))):
                got.add(make_profile.render_tracks("p4w1 sweep", copy.deepcopy(entries),
                                                   copy.deepcopy(self.PREFS)))
        self.assertEqual(got, {sources[(3, "1", "1", "1", "1")]})

    def test_what_check_tracks_refuses_it_refuses(self):
        for broken in ([], FOCUSED + FOCUSED[:1], [dict(FOCUSED[0], resume_text="x")],
                       [FOCUSED[0], dict(FOCUSED[1], id=FOCUSED[0]["id"])]):
            with self.assertRaises(ValueError):
                make_profile.check_tracks(copy.deepcopy(broken))
            with self.assertRaises(ValueError):
                make_profile.render_tracks("p4w1", copy.deepcopy(broken), dict(PREFS))


# ===========================================================================
class Requests(Harness):
    """The API matrix, A-L: both endpoints, each refusal before any work."""

    def test_a_profile_only_is_the_legacy_path(self):
        os.environ.update(dict.fromkeys(RENDER_FLAGS, "1"))        # the legacy child keeps them
        answer = self.post("/v1/plans", {"profile": PROFILE, "prefs": PREFS,
                                         "free_only": True, "owner": "session-a"})
        self.assertEqual(answer.status_code, 200)
        self.assertNotIn("plan_hash", answer.get_json())
        status = self.status(self.post("/v1/runs", {"profile": PROFILE, "prefs": PREFS,
                                                    "free_only": True, "owner": "session-a"}))
        self.assertNotIn("plan_hash", status)
        self.assertEqual(os.stat(status["profile_path"]).st_mode & 0o777, 0o644)   # as today
        # P4-S1C: never the worker's own bearer; the render flags still arrive.
        self.assertEqual(self.engine.plans[0]["env"],
                         {k: v for k, v in os.environ.items()
                          if not k.startswith("APIFY_TOKEN") and k != sweep_worker.TOKEN_ENV})

    def test_b_c_two_or_three_tracks_are_one_multi_sweep(self):
        for tracks in (TWO, FOCUSED):
            with self.subTest(n=len(tracks)):
                raw = self.plan(tracks)
                self.assertEqual(raw["plan_version"], 2)
                status = self.status(self.multi("/v1/runs", tracks))
                self.assertEqual(status["track_ids"], [t["id"] for t in tracks])
                self.assertEqual(status["plan_hash"], raw["plan_hash"])

    def test_d_e_both_or_neither_take_the_legacy_refusals(self):
        both = {"profile": PROFILE, "tracks": copy.deepcopy(FOCUSED), "prefs": PREFS,
                "free_only": True, "owner": "session-a"}
        neither = {"prefs": PREFS, "free_only": True, "owner": "session-a"}
        for path in ("/v1/plans", "/v1/runs"):
            with self.subTest(path=path):
                self.refused(self.post(path, both), 400, "unknown field(s): tracks")
                self.refused(self.post(path, neither), 400, "profile and prefs must be objects")
        self.assertEqual(self.engine.plans, [])
        self.nothing_left()

    def test_f_g_only_two_or_three_tracks(self):
        message = "tracks must be a list of 2 to 3 tracks (one résumé is a profile)"
        for tracks in ([], FOCUSED[:1], FOCUSED + [entry("d4" * 8, ["x developer"], 1, ["x"],
                                                         {"x": 1})], {"a": 1}, None, "tracks"):
            for path in ("/v1/plans", "/v1/runs"):
                with self.subTest(tracks=tracks, path=path):
                    self.refused(self.post(path, {"tracks": tracks, "prefs": PREFS,
                                                  "free_only": True, "owner": "session-a"}),
                                 400, message)
        self.assertEqual(self.engine.plans, [])
        self.nothing_left()

    def test_h_to_k_check_tracks_decides_every_entry(self):
        bad_positioning = copy.deepcopy(FOCUSED)
        bad_positioning[1]["POSITIONING"]["concepts"] = ["kotlin", "kotlin"]
        missing_positioning = copy.deepcopy(FOCUSED)
        del missing_positioning[2]["POSITIONING"]
        bad_alignment = copy.deepcopy(FOCUSED)
        bad_alignment[0]["ALIGNMENT"]["role_titles"] = ["kotlin wizard"]
        alignment_alone = copy.deepcopy(BARE)
        for t in alignment_alone:
            t["ALIGNMENT"] = {"role_titles": []}
        cases = {
            "duplicate ids": [FOCUSED[0], dict(FOCUSED[1], id=FOCUSED[0]["id"])],
            "a name for an id": [dict(FOCUSED[0], id="ada-okonkwo"), FOCUSED[1]],
            "unknown engine": [dict(FOCUSED[0], engine="mixed"), FOCUSED[1]],
            "bad SEARCH": [dict(FOCUSED[0], SEARCH={"role_keywords": "react"}), FOCUSED[1]],
            "bad SETTINGS": [dict(FOCUSED[0], SETTINGS={"max_experience_years": -1,
                                                        "candidate_experience_months": None}),
                             FOCUSED[1]],
            "bad SCORING": [dict(FOCUSED[0], SCORING=dict(FOCUSED[0]["SCORING"],
                                                          skill_weights={"react": "5"})),
                            FOCUSED[1]],
            "malformed POSITIONING": bad_positioning,
            "POSITIONING on some tracks": missing_positioning,
            "malformed ALIGNMENT": bad_alignment,
            "ALIGNMENT without POSITIONING": alignment_alone,
            "unknown track key": [dict(FOCUSED[0], LOCATIONS=["Remote"]), FOCUSED[1]],
            "a Sweep key in a track": [dict(FOCUSED[0], SITES={}), FOCUSED[1]],
        }
        for label, tracks in cases.items():
            for path in ("/v1/plans", "/v1/runs"):
                with self.subTest(case=label, path=path):
                    self.refused(self.multi(path, tracks), 400,
                                 "the tracks were refused by the renderer (ValueError)")
        self.assertEqual(self.engine.plans, [])
        self.nothing_left()

    def test_l_no_field_can_carry_resume_content(self):
        for field in ("resume", "resume_text", "raw_resume", "pdf", "file", "source_text",
                      "extracted_text", "derived", "profile_text", "engine", "plan_hash"):
            for path in ("/v1/plans", "/v1/runs"):
                with self.subTest(field=field, path=path):
                    self.refused(self.multi(path, **{field: "Ada Okonkwo, 4 years"}), 400,
                                 f"unknown field(s): {field}")
                    inside = [dict(FOCUSED[0], **{field: "Ada Okonkwo"}), FOCUSED[1]]
                    self.refused(self.multi(path, inside), 400,
                                 "the tracks were refused by the renderer (ValueError)")
        self.assertEqual(self.engine.plans, [])
        self.nothing_left()

    def test_expected_plan_hash_belongs_to_a_multi_run_only(self):
        self.refused(self.multi("/v1/plans", expected_plan_hash=STALE_HASH), 400,
                     "unknown field(s): expected_plan_hash")
        for path in ("/v1/plans", "/v1/runs"):
            with self.subTest(path=path):
                self.refused(self.post(path, {"profile": PROFILE, "prefs": PREFS,
                                              "free_only": True, "owner": "session-a",
                                              "expected_plan_hash": STALE_HASH}),
                             400, "unknown field(s): expected_plan_hash")
        for bad in ("", "abc", "A" * 64, STALE_HASH + "0", 7, ["x"]):
            with self.subTest(bad=bad):
                self.refused(self.multi("/v1/runs", expected_plan_hash=bad), 400,
                             "expected_plan_hash must be a plan_hash /v1/plans returned")
        self.assertEqual(self.engine.plans, [])
        self.nothing_left()

    def test_the_legacy_field_rules_hold_for_tracks(self):
        for extra, message in (({"owner": ""}, "owner must be a short opaque string"),
                               ({"free_only": "yes"}, "free_only must be true or false"),
                               ({"apify_token": KEY}, "a free sweep must not carry an Apify token"),
                               ({"key_ids": ["k1"]}, "a free sweep must not name Apify keys"),
                               ({"prefs": "Remote"}, "profile and prefs must be objects")):
            with self.subTest(extra=extra):
                self.refused(self.multi("/v1/runs", **extra), 400, message)
        self.nothing_left()


# ===========================================================================
class Plans(Harness):
    """M, Q and the unified plan: the engine's dry run, verbatim."""

    def test_m_the_engines_plan_version_and_hash_verbatim(self):
        raw = self.plan()
        call, = self.engine.plans
        self.assertEqual(raw, json.loads(call["stdout"]))       # jsonify re-sorts, nothing else
        self.assertEqual(call["argv"][1:3] + call["argv"][4:],
                         ["scraper.py", "--profile", "--dry-run", "--json"])
        self.assertEqual((raw["plan_version"], len(raw["plan_hash"])), (2, 64))
        self.assertEqual(call["mode"], 0o600)
        self.assertEqual(tracks_of(call["source"]), FOCUSED)    # the tracks exactly as sent
        self.assertEqual(os.listdir(os.path.join(self.checkout, "profiles")), ["__init__.py"])
        self.assertFalse(os.path.exists(self.trip))

    def test_the_file_is_render_tracks_bytes_in_the_order_the_entries_arrive(self):
        """Key order inside an entry is data — ScoringContext.key reads it —
        so the worker writes what it was sent, in that order, and nothing else."""
        turned = copy.deepcopy(FOCUSED)
        for t in turned:
            t["SCORING"]["skill_weights"] = dict(reversed(t["SCORING"]["skill_weights"].items()))
        for tracks in (FOCUSED, turned):
            self.plan(tracks, free_only=False)
            call = self.engine.plans[-1]
            want = make_profile.render_tracks("NAME", copy.deepcopy(tracks), copy.deepcopy(PREFS))
            self.assertEqual(call["source"][:call["source"].index("\n# Written by sweep_worker")],
                             want)
            self.assertEqual([list(t["SCORING"]["skill_weights"]) for t in tracks_of(call["source"])],
                             [list(t["SCORING"]["skill_weights"]) for t in tracks])

    def test_one_profile_one_plan_shared_requests_once_with_every_requester(self):
        raw = self.plan(free_only=False)
        call, = self.engine.plans
        module = {n.targets[0].id: ast.literal_eval(n.value)
                  for n in ast.parse(call["source"]).body if isinstance(n, ast.Assign)
                  and isinstance(n.targets[0], ast.Name)}
        self.assertEqual(module["PROFILE_SCHEMA"], {"version": 2, "engine": "multi"})
        self.assertEqual(len(module["TRACKS"]), 3)
        shared = {}
        for site, entries in raw["sites"].items():
            for e in entries:
                if e["keywords"] == "react developer":
                    shared.setdefault((site, e["location"]), []).append(e["tracks"])
        places = {site: {loc for s, loc in shared if s == site} for site in ("indeed", "linkedin")}
        self.assertTrue(places["indeed"] and places["linkedin"])
        for (site, _loc), groups in shared.items():
            # Indeed reads no experience: one request for all three. LinkedIn's
            # f_E splits 2 years from 6: one for MERN and Mobile, one for AI.
            self.assertEqual(sorted(groups), [[MERN, MOBILE, AI]] if site == "indeed"
                             else [[MERN, MOBILE], [AI]], site)
        for site in raw["sites"].values():
            self.assertEqual(len({e["ledger"] for e in site}), len(site))
            self.assertTrue(all(set(e) == {"keywords", "location", "company", "tracks", "ledger"}
                                for e in site))

    def test_q_a_stale_engine_prices_nothing(self):
        good = {"plan_version": 2, "plan_hash": "a" * 64, "sites": {}}
        for label, canned in (
                ("no attestation", (0, json.dumps({"profile": "x", "sites": {}}))),
                ("plan_version 1", (0, json.dumps(dict(good, plan_version=1)))),
                ("no hash", (0, json.dumps({k: v for k, v in good.items() if k != "plan_hash"}))),
                ("empty hash", (0, json.dumps(dict(good, plan_hash="")))),
                ("not a hash", (0, json.dumps(dict(good, plan_hash="v2")))),
                ("no sites", (0, json.dumps({k: v for k, v in good.items() if k != "sites"})))):
            self.engine.canned = canned
            for path in ("/v1/plans", "/v1/runs"):
                with self.subTest(case=label, path=path):
                    self.refused(self.multi(path), 502, "the engine could not price that plan "
                                                        "(it attests no schema-2 plan hash)")
        self.engine.canned = (1, "")         # an engine that refuses schema 2 exits non-zero
        for path in ("/v1/plans", "/v1/runs"):
            self.refused(self.multi(path), 502, "the engine could not price that plan")
        self.engine.canned = (0, "not json")
        self.refused(self.multi("/v1/runs"), 502,
                     "the engine could not price that plan (JSONDecodeError)")
        self.nothing_left()

    def test_render_time_flags_and_the_title_gate_move_nothing(self):
        """R-9 for schema 2: the worker's copy of every render-time flag, the
        title gate included, cannot move the file, the plan or the hash — the
        entries arrive decided, and the engine is never handed the flags."""
        answers = []
        for values in (("0",) * 4, ("1",) * 4, ("0", "0", "0", "1"), ("1", "1", "1", "0")):
            with mock.patch.dict(os.environ, dict(zip(RENDER_FLAGS, values))):
                answers.append({k: v for k, v in self.plan(free_only=False).items()
                                if k != "profile"})
        self.assertEqual([a == answers[0] for a in answers], [True] * 4)
        self.assertEqual(len({c["source"] for c in self.engine.plans}), 1)
        for call in self.engine.plans:
            self.assertFalse(set(call["env"]) & set(RENDER_FLAGS))

    def test_recommendation_and_caution_never_move_the_plan(self):
        answers = []
        for recommend in ("0", "1"):
            for caution in ("0", "1"):
                with mock.patch.dict(os.environ, {RECOMMEND: recommend, CAUTION: caution}):
                    answers.append({k: v for k, v in self.plan(free_only=False).items()
                                    if k != "profile"})
        self.assertEqual([a == answers[0] for a in answers], [True] * 4)
        # Forwarded as the child reads them: the run reads them, never the plan.
        self.assertEqual(self.engine.plans[-1]["env"][CAUTION], "1")

    def test_the_plan_env_is_the_run_env_less_what_only_a_run_carries(self):
        with mock.patch.dict(os.environ, {RECOMMEND: "1", title_gate.FLAG: "1",
                                          sweep_worker.PLAN_HASH_ENV: STALE_HASH}):
            self.plan()
            call, = self.engine.plans
            self.assertEqual(call["env"], {k: v for k, v in os.environ.items()
                                           if k in ("PATH", "HOME", "LANG",
                                                    "PYTHONDONTWRITEBYTECODE", RECOMMEND)})


# ===========================================================================
class Runs(Harness):
    """The hash matrix and the preflight: the plan decides, never the caller."""

    EXTRA_ENV = {"SWEEP_PUBLIC_PAID": "1"}

    def priced(self, free_only):
        return self.plan(free_only=free_only)["plan_hash"]

    def assert_plan_changed(self, answer, preflights=1):
        self.refused(answer, 409, "plan_changed")
        self.assertEqual(len(self.engine.plans), preflights)
        self.nothing_left()

    def test_paid_needs_the_hash_it_was_priced_with(self):
        priced = self.priced(False)
        self.assertTrue(any(self.plan(free_only=False)["sites"].values()))
        self.engine.plans.clear()
        self.refused(self.multi("/v1/runs", free_only=False), 400,
                     "expected_plan_hash is required: this Sweep's plan has paid searches")
        self.assertEqual(len(self.engine.plans), 1)
        self.nothing_left()
        self.engine.plans.clear()
        self.assert_plan_changed(self.multi("/v1/runs", free_only=False,
                                            expected_plan_hash=STALE_HASH))
        self.engine.plans.clear()
        status = self.status(self.multi("/v1/runs", free_only=False, expected_plan_hash=priced))
        spawned, = self.spawned
        self.assertEqual((spawned["plan_hash"], spawned["tokens"]), (priced, [KEY]))
        self.assertEqual((status["plan_hash"], status["free_only"]), (priced, False))
        preflight, = self.engine.plans
        self.assertEqual(preflight["argv"][3], status["profile_name"])   # the run's own file

    def test_free_may_omit_the_hash_but_a_stale_one_is_never_ignored(self):
        priced = self.priced(True)
        self.assertEqual(self.plan()["sites"], {})
        self.engine.plans.clear()
        self.assert_plan_changed(self.multi("/v1/runs", expected_plan_hash=STALE_HASH))
        self.assertEqual(self.status(self.multi("/v1/runs"))["plan_hash"], priced)
        self.assertEqual(self.status(self.multi("/v1/runs", expected_plan_hash=priced))["plan_hash"],
                         priced)
        self.assertEqual([s["plan_hash"] for s in self.spawned], [priced, priced])

    def test_free_only_is_not_proof_of_a_free_plan(self):
        paid = {"plan_version": 2, "plan_hash": "b" * 64,
                "sites": {"linkedin": [{"keywords": "react developer", "location": "Remote",
                                        "company": "", "tracks": [MERN], "ledger": "x"}]}}
        self.engine.canned = (0, json.dumps(paid))
        self.refused(self.multi("/v1/runs"), 400,
                     "expected_plan_hash is required: this Sweep's plan has paid searches")
        self.nothing_left()
        self.assertEqual(self.status(self.multi("/v1/runs", expected_plan_hash="b" * 64))
                         ["plan_hash"], "b" * 64)

    def test_the_hash_differs_by_track_set_and_order_never_by_name(self):
        first, again = self.priced(False), self.priced(False)
        self.assertEqual(first, again)          # plan_<hex> each time: names never enter it
        self.assertNotEqual(self.plan(TWO, free_only=False)["plan_hash"], first)
        self.assertNotEqual(self.plan(FOCUSED[::-1], free_only=False)["plan_hash"], first)

    def test_one_profile_one_child_and_status_that_carries_no_resume(self):
        status = self.status(self.multi("/v1/runs", free_only=False,
                                        expected_plan_hash=self.priced(False)))
        run_id = status["run_id"]
        self.assertEqual(sorted(os.listdir(os.path.join(self.checkout, "profiles"))),
                         ["__init__.py", f"beta_{run_id}.py"])
        self.assertEqual(len(self.spawned), 1)
        for path in (status["profile_path"], os.path.join(self.store.dir(run_id), "profile.py")):
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(len(tracks_of(fh.read())), 3)
        self.assertEqual(set(status) - {"state", "started_at", "finished_at", "exit_code"},
                         {"run_id", "owner", "created_at", "free_only", "profile_name",
                          "profile_path", "error", "schema", "track_ids", "plan_hash"})
        self.assertEqual((status["schema"], status["track_ids"]), (2, [MERN, MOBILE, AI]))
        with open(os.path.join(self.store.dir(run_id), "status.json"), encoding="utf-8") as fh:
            raw = fh.read()
        for secret in ("react developer", "mongodb", "kotlin", "machine learning", KEY):
            self.assertNotIn(secret, raw)
        public = self.client.get(f"/v1/runs/{run_id}",
                                 headers={"Authorization": f"Bearer {WORKER_TOKEN}",
                                          "X-Sweep-Owner": "session-a"}).get_json()
        self.assertEqual((public["track_ids"], public["plan_hash"]),
                         (status["track_ids"], status["plan_hash"]))
        self.assertNotIn("owner", public)

    def test_a_legacy_run_is_exactly_todays(self):
        status = self.status(self.post("/v1/runs", {"profile": PROFILE, "prefs": PREFS,
                                                    "free_only": True, "owner": "session-a"}))
        self.assertEqual(set(status) - {"state", "started_at", "finished_at", "exit_code"},
                         {"run_id", "owner", "created_at", "free_only", "profile_name",
                          "profile_path", "error"})
        spawned, = self.spawned
        self.assertEqual(set(spawned), {"run_id", "profile", "tokens"})   # no plan_hash
        self.assertEqual(self.engine.plans, [])                           # no preflight


# ===========================================================================
class ChildEnvironment(unittest.TestCase):
    """default_spawn: what each child is handed, with Popen recorded."""

    def spawn(self, **kw):
        seen = {}

        def popen(argv, cwd, env, **_kw):
            seen.update(argv=argv, env=dict(env))
            return types.SimpleNamespace(stdin=mock.Mock(), wait=lambda: 0)

        run_dir = tempfile.mkdtemp(prefix="p4w1-spawn-")
        self.addCleanup(shutil.rmtree, run_dir, ignore_errors=True)
        with mock.patch.object(sweep_worker.subprocess, "Popen", popen):
            _child, closer = sweep_worker.default_spawn("ab" * 16, run_dir, "beta_x", run_dir,
                                                        [KEY], **kw)
        return seen

    ENV = dict(OPERATOR, PATH="/usr/bin:/bin", HOME="/nowhere", **{
        sweep_worker.TOKEN_ENV: WORKER_TOKEN, RECOMMEND: "1", CAUTION: "1",
        sweep_worker.PLAN_HASH_ENV: STALE_HASH, "SWEEP_PUBLIC_PAID": "1"},
        **dict.fromkeys(RENDER_FLAGS, "1"))

    def test_a_multi_child_gets_its_hash_and_nothing_render_time(self):
        with mock.patch.dict(os.environ, self.ENV, clear=True):
            env = self.spawn(plan_hash="c" * 64)["env"]
        self.assertEqual(env, {"PATH": "/usr/bin:/bin", "HOME": "/nowhere",
                               RECOMMEND: "1", CAUTION: "1", "SWEEP_PUBLIC_PAID": "1",
                               "SWEEP_BYOK_CREDENTIALS": "stdin", "JOB_PROFILE": "beta_x",
                               "SWEEP_RUN_ID": "ab" * 16,
                               sweep_worker.PLAN_HASH_ENV: "c" * 64})
        self.assertNotIn(KEY, json.dumps(env))

    def test_a_legacy_child_is_handed_exactly_what_it_always_was(self):
        with mock.patch.dict(os.environ, self.ENV, clear=True):
            env = self.spawn()["env"]
            # P4-S1C: never the worker's own bearer; everything else as ever.
            want = {k: v for k, v in os.environ.items()
                    if not k.startswith("APIFY_TOKEN") and k not in sweep_worker.DEVELOPER_ONLY_ENV
                    and k != sweep_worker.TOKEN_ENV}
            self.assertIn(sweep_worker.TOKEN_ENV, os.environ)
        self.assertNotIn(sweep_worker.TOKEN_ENV, env)
        self.assertEqual(env, dict(want, SWEEP_BYOK_CREDENTIALS="stdin", JOB_PROFILE="beta_x",
                                   SWEEP_RUN_ID="ab" * 16))


# ===========================================================================
class Outcomes(Harness):
    """Exit 4, restart, and two real children that must do no work."""

    EXTRA_ENV = {"SWEEP_PUBLIC_PAID": "1"}

    def fake_code(self, code):
        def spawner(run_id, run_dir, profile_name, checkout, tokens, **kw):
            self.spawned.append(kw)
            return types.SimpleNamespace(wait=lambda: code, terminate=lambda: None), None
        self.queue.spawn = spawner

    def test_exit_4_is_plan_changed_for_a_multi_run_only(self):
        self.fake_code(4)
        multi = self.wait(self.status(self.multi("/v1/runs"))["run_id"])
        legacy = self.wait(self.status(self.post("/v1/runs", {
            "profile": PROFILE, "prefs": PREFS, "free_only": True, "owner": "session-a"}))["run_id"])
        self.assertEqual((multi["state"], multi["exit_code"], multi["error"]),
                         ("failed", 4, "plan_changed"))
        self.assertEqual((legacy["state"], legacy["exit_code"], legacy["error"]),
                         ("failed", 4, "the engine exited with status 4"))

    def test_a_restart_requeues_a_free_multi_run_with_its_hash(self):
        self.queue.max_active = 0
        status = self.status(self.multi("/v1/runs"))
        queue = sweep_worker.Queue(self.store, spawn=self.spawn, checkout=self.checkout)
        queue.recover()
        self.assertEqual([s["plan_hash"] for s in self.spawned], [status["plan_hash"]])

    def real_child(self, answer, edit=None):
        """Let the queued run start, as the real engine, after `edit`."""
        self.queue.spawn = sweep_worker.default_spawn
        status = self.status(answer)
        if edit:
            with open(status["profile_path"], encoding="utf-8") as fh:
                source = fh.read()
            with open(status["profile_path"], "w", encoding="utf-8") as fh:
                fh.write(edit(source))
        with self.queue._lock:
            self.queue.max_active = 1
            self.queue._pump()
        return self.wait(status["run_id"]), status

    def assert_no_work(self, status):
        self.assertFalse(os.path.exists(self.trip), "the child reached acquisition")
        self.assertEqual(os.listdir(self.store.output_dir(status["run_id"])), [])
        self.assertEqual(self.client.get(f"/v1/runs/{status['run_id']}/rows", headers={
            "Authorization": f"Bearer {WORKER_TOKEN}", "X-Sweep-Owner": "session-a"}).get_json(),
            {"rows": [], "total": 0, "since": 0})

    def test_the_child_refuses_a_plan_that_changed_after_the_preflight(self):
        self.queue.max_active = 0
        priced = self.priced_paid()
        done, status = self.real_child(
            self.multi("/v1/runs", free_only=False, expected_plan_hash=priced),
            edit=lambda s: s.replace("'mern stack developer'", "'mean stack developer'", 1))
        self.assertEqual((done["state"], done["exit_code"], done["error"]),
                         ("failed", 4, "plan_changed"))
        child, = self.engine.runs
        self.assertEqual(child["env"][sweep_worker.PLAN_HASH_ENV], priced)
        self.assertEqual(child["env"]["SWEEP_BYOK_CREDENTIALS"], "stdin")
        self.assertNotIn(KEY, json.dumps(child["env"]))
        self.assert_no_work(status)

    def priced_paid(self):
        return self.plan(free_only=False)["plan_hash"]

    def test_a_caution_it_cannot_compute_fails_the_run_before_any_fetch(self):
        self.queue.max_active = 0
        with mock.patch.dict(os.environ, {RECOMMEND: "1", CAUTION: "1"}):
            done, status = self.real_child(self.multi("/v1/runs", BARE))
        self.assertEqual((done["state"], done["exit_code"], done["error"]),
                         ("failed", 1, "the engine exited with status 1"))
        with open(os.path.join(self.store.dir(status["run_id"]), "engine.log"),
                  encoding="utf-8") as fh:
            self.assertIn(f"{CAUTION} needs every track's POSITIONING", fh.read())
        self.assertFalse(os.path.exists(self.trip))
        self.assertFalse(any(n.endswith(".csv") for n in
                             os.listdir(self.store.output_dir(status["run_id"]))))


# ===========================================================================
class Rows(Harness):
    """N, O: the engine's own rows through /rows, additive fields verbatim."""

    EXTRA_ENV = {skill_concepts.VERSION_ENV: "v1"}

    def setUp(self):
        super().setUp()
        bound = skill_concepts._BOUND
        self.addCleanup(setattr, skill_concepts, "_BOUND", bound)
        skill_concepts.bind(None)
        patch = mock.patch.dict(scraper.SETTINGS, mr.FILTERS)
        patch.start()
        self.addCleanup(patch.stop)

    def served(self, recommend, caution):
        run_id = self.status(self.multi("/v1/runs"))["run_id"]
        out_dir = self.store.output_dir(run_id)
        rows = scraper.finalize_multi(mr.focus_jobs(), mr.focus_contexts(),
                                      recommend=recommend, caution=caution)
        csv_path = os.path.join(out_dir, "jobs_2026-09-28_1200.csv")
        with mock.patch.dict(scraper.SETTINGS, {"output_dir": out_dir}):
            scraper.write_outputs(rows, csv_path, os.path.join(out_dir, "jobs.json"),
                                  scraper.multi_output_columns(recommend, caution))
        with open(csv_path, newline="", encoding="utf-8-sig") as fh:
            written = list(csv.DictReader(fh))
        got = self.client.get(f"/v1/runs/{run_id}/rows", headers={
            "Authorization": f"Bearer {WORKER_TOKEN}", "X-Sweep-Owner": "session-a"}).get_json()
        return rows, written, got

    def test_every_additive_field_is_forwarded_as_the_engine_wrote_it(self):
        rows, written, got = self.served(True, True)
        self.assertEqual(got["rows"], written)
        self.assertEqual(got["total"], len(mr.FOCUS_CASES))
        for want, row in zip(rows, got["rows"]):
            for key in ("best_track", "track_evals", "found_by", "recommended_tracks",
                        "recommendation", "recommendation_caution"):
                self.assertEqual(row[key], str(want[key]), key)
        kinds = {r["recommendation"] for r in got["rows"]}
        self.assertEqual(kinds, {"clear", "close", "tied", "split"})

    def test_caution_absent_empty_and_coded_stay_three_things(self):
        _rows, _w, off = self.served(True, False)
        _rows, _w, on = self.served(True, True)
        self.assertTrue(all("recommendation_caution" not in r for r in off["rows"]))
        cautions = {r["apply_url"].rsplit("/", 1)[1]: r["recommendation_caution"]
                    for r in on["rows"]}
        self.assertEqual(cautions, {f"f{n}": case[4] for n, case in enumerate(mr.FOCUS_CASES)})
        self.assertEqual(set(cautions.values()), {"", scraper.NO_FOCUS_EVIDENCE})
        _rows, _w, bare = self.served(False, False)
        self.assertTrue(all("recommendation" not in r and "recommended_tracks" not in r
                            for r in bare["rows"]))


if __name__ == "__main__":
    unittest.main()
