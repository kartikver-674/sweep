"""Multi-Track Phase 2A: schema-2 representation and loading, nothing more.

make_profile.render_sweep() writes a Sweep's own sections once plus TRACKS;
config loads TRACKS beside the one-profile globals without overlaying any of
them; scraper builds one immutable TrackContext per track, each from config's
pristine defaults and that track's own values. No track plans, filters, scores
or ranks anything yet, and a schema-2 profile that reaches one-profile code
fails closed rather than running as one of its tracks.

Offline, synthetic derivations only. One-profile output stays pinned by
test_one_track_goldens; scoring contexts by test_scoring_context.
"""
import ast
import contextlib
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

import config
import scraper
import skill_concepts
from sweep.tests.test_one_track_goldens import REPO, _env, derived_for, prefs_for

sys.path.insert(0, os.path.join(REPO, "auto-apply"))
import make_profile  # noqa: E402

GATE, CENTRALITY = "SWEEP_CANDIDATE_TITLE_GATE", "SWEEP_FAMILY_CENTRALITY_GATE"
FLAGS = (GATE, CENTRALITY, skill_concepts.VERSION_ENV, skill_concepts.FLAG,
         skill_concepts.EVIDENCE_FLAG)

# DQ3-2: with SWEEP_TRACK_SCORING_INTENT on, render_sweep refuses a 2-3-track
# Sweep that carries no scoring positioning (fail closed, by design). These
# tests render without it, so they pin the flag off; DQ3's tests turn it on.
_SCORING_OFF = mock.patch.dict(os.environ, {make_profile.TRACK_SCORING_FLAG: "0"})
setUpModule, tearDownModule = _SCORING_OFF.start, _SCORING_OFF.stop


@contextlib.contextmanager
def flags(**on):
    """Exactly these render-time flags set, every other one in FLAGS unset."""
    saved = {k: os.environ.get(k) for k in FLAGS}
    for k in FLAGS:
        os.environ.pop(k, None)
    os.environ.update(on)
    try:
        yield
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


def synthetic(**over):
    base = {"candidate_name": "Synthetic Person", "field_summary": "SYNTHETIC-SUMMARY",
            "notes": "SYNTHETIC-NOTES", "years_experience": 3, "experience_months": 40,
            "role_keywords": ["react developer"], "skill_weights": [], "penalty_terms": [],
            "domain_half_a": [], "domain_half_b": [], "domain_title_terms": [],
            "domain_bonus": 0, "title_hints": [], "title_exclude": [],
            "role_signals": {}, "role_evidence": None}
    base.update(over)
    return base


# Three tracks that disagree on purpose: A weights React, B penalises it; A's
# title gate admits "frontend", B's excludes it; 3, 7 and 1 years; v2, v1, v2.
A = {"id": "aaaaaaaaaaaaaaa1", "engine": "v2", "derived": synthetic(
    years_experience=3, experience_months=40,
    role_keywords=["react developer", "frontend engineer"],
    skill_weights=[{"term": "react", "weight": 5}, {"term": "react.js", "weight": 5},
                   {"term": "typescript", "weight": 3}],
    title_hints=["react", "frontend"], title_exclude=["qa"],
    role_signals={"employment_titles": ["Frontend Engineer"], "titles": ["Frontend Engineer"]},
    role_evidence={"supports": {"software_engineering": "strong"}})}
B = {"id": "bbbbbbbbbbbbbbb2", "engine": "v1", "derived": synthetic(
    years_experience=7, experience_months=86,
    role_keywords=["python developer"],
    skill_weights=[{"term": "python", "weight": 5}, {"term": "django", "weight": 4}],
    penalty_terms=[{"term": "react", "weight": 8}],
    title_hints=["python", "backend"], title_exclude=["frontend"],
    role_signals={"employment_titles": ["Python Developer"]},
    role_evidence={"supports": {"data_engineering": "strong"}})}
C = {"id": "ccccccccccccccc3", "engine": "v2", "derived": synthetic(
    years_experience=1, experience_months=14,
    role_keywords=["mern developer"],
    skill_weights=[{"term": "node.js", "weight": 4}, {"term": "mongodb", "weight": 3}],
    domain_half_a=["React"], domain_half_b=["Node.js"], domain_title_terms=["MERN"],
    domain_bonus=4, title_hints=["node", "full stack"],
    role_signals={"titles": ["MERN Stack Developer"]})}
PERSONAS = [{"id": f"{n}0000000", "engine": e, "derived": derived_for(name)}
            for n, e, name in (("d1", "v1", "ada-plain"), ("d2", "v2", "chen-plain"),
                               ("d3", "v2", "bhaskar-plain"))]
# exclude_levels is pinned: these tests are about which section a choice is
# written to, and since 2026-11-20 the default cut follows each résumé's
# years (make_profile.levels_for, tested in test_seniority_cut), which would
# make tracks of different seniority legitimately differ here.
PREFS = dict(prefs_for("global_custom"), max_spend_usd=12.5, allow_partial_paid_sweep=True,
             exclude_levels=make_profile.levels_for(None))


def literals(source):
    """{top-level name: value} of rendered source, read without executing it."""
    return {n.targets[0].id: ast.literal_eval(n.value) for n in ast.parse(source).body
            if isinstance(n, ast.Assign)}


def schema1(track, prefs=PREFS):
    with flags(**{skill_concepts.VERSION_ENV: track["engine"]},
               **{k: v for k, v in os.environ.items() if k in (GATE, CENTRALITY)}):
        return literals(make_profile.render("probe", track["derived"], prefs))


def by_id(tracks):
    return {t["id"]: t for t in tracks}


class EngineIsolated(unittest.TestCase):

    def setUp(self):
        bound = skill_concepts._BOUND
        self.addCleanup(setattr, skill_concepts, "_BOUND", bound)
        skill_concepts.bind(None)
        stack = contextlib.ExitStack()
        stack.enter_context(flags())
        self.addCleanup(stack.close)


def valid_tracks(n=3):
    return literals(make_profile.render_sweep("probe", [A, B, C][:n], PREFS))["TRACKS"]


# ===========================================================================
class SchemaValidation(EngineIsolated):

    def test_stamps(self):
        read = lambda stamp: make_profile.profile_schema(types.SimpleNamespace(PROFILE_SCHEMA=stamp))
        for ok in ({"version": 1, "engine": "v1"}, {"version": 1, "engine": "v2"},
                   {"version": 2, "engine": "multi"}):
            self.assertTrue(read(ok)["readable"], ok)
        for bad in ({"version": 3, "engine": "multi"}, {"version": 2, "engine": "v2"},
                    {"version": 1, "engine": "multi"}, 2):
            self.assertFalse(read(bad)["readable"], bad)
        self.assertIn("newer build", read({"version": 3, "engine": "multi"})["why"])
        self.assertEqual(make_profile.PROFILE_SCHEMA, 1)          # render() still writes 1

    def test_one_to_three_valid_tracks_pass(self):
        for n in (1, 2, 3):
            self.assertEqual(len(make_profile.check_tracks(valid_tracks(n))), n)

    def test_malformed_tracks_are_refused(self):
        good = valid_tracks()
        cases = {"no tracks": [], "four tracks": good + [dict(good[0], id="dddddddddddddddd")],
                 "not a list": {"a": good[0]}}
        for field, value in (("id", "Track A"), ("id", "ABCDEF1234"), ("id", "abc"),
                             ("engine", "v3"), ("engine", "mixed"), ("engine", None)):
            cases[f"{field}={value!r}"] = [dict(good[0], **{field: value})]
        cases["duplicate id"] = [good[0], dict(good[1], id=good[0]["id"])]
        cases["missing engine"] = [{k: v for k, v in good[0].items() if k != "engine"}]
        cases["display name"] = [dict(good[0], name="React Native Developer")]
        cases["résumé filename"] = [dict(good[0], resume_name="cv.pdf")]
        cases["missing scoring key"] = [dict(good[0], SCORING={
            k: v for k, v in good[0]["SCORING"].items() if k != "fullstack_bonus"})]
        cases["sweep key in a track"] = [dict(good[0], SETTINGS=dict(good[0]["SETTINGS"],
                                                                     min_comp_usd=1))]
        cases["keywords not a list"] = [dict(good[0], SEARCH=dict(good[0]["SEARCH"],
                                                                  role_keywords="react"))]
        cases["weight not a number"] = [dict(good[0], SCORING=dict(
            good[0]["SCORING"], skill_weights={"react": "5"}))]
        cases["years negative"] = [dict(good[0], SEARCH=dict(good[0]["SEARCH"],
                                                             experience_years=-1))]
        for label, tracks in cases.items():
            with self.subTest(label):
                with self.assertRaises(ValueError):
                    make_profile.check_tracks(tracks)

    def test_render_sweep_refuses_what_check_tracks_refuses(self):
        for tracks in ([], [A, B, C, dict(A, id="dddddddddddddddd")], [A, dict(B, id=A["id"])],
                       [dict(A, engine="multi")], [dict(A, id="Frontend")]):
            with self.assertRaises(ValueError):
                make_profile.render_sweep("probe", tracks, PREFS)

    def module(self, name, **attrs):
        made = types.ModuleType(f"profiles.{name}")
        for key, value in attrs.items():
            setattr(made, key, value)
        sys.modules[f"profiles.{name}"] = made
        self.addCleanup(sys.modules.pop, f"profiles.{name}", None)

    def test_the_real_loader(self):
        sweep = literals(make_profile.render_sweep("probe", [A, B], PREFS))
        self.module("sweepok", **sweep)
        module, stamp = config.load_profile_module("sweepok")
        self.assertEqual((stamp["version"], stamp["engine"]), (2, "multi"))
        refused = {
            "tracks_in_schema_1": dict(sweep, PROFILE_SCHEMA={"version": 1, "engine": "v2"}),
            "track_key_at_sweep_level": dict(sweep, SEARCH=dict(sweep["SEARCH"],
                                                                role_keywords=["x"])),
            "gate_at_sweep_level": dict(sweep, ATS_TITLE_HINTS=["x"]),
            "no_tracks": {k: v for k, v in sweep.items() if k != "TRACKS"},
            "bad_track": dict(sweep, TRACKS=[dict(sweep["TRACKS"][0], engine="v9")]),
        }
        for name, attrs in refused.items():
            with self.subTest(name):
                self.module(name, **attrs)
                with self.assertRaises(SystemExit):
                    config.load_profile_module(name)
                with self.assertRaises(ValueError):
                    make_profile.load_profile(name)


# ===========================================================================
class RenderParity(EngineIsolated):
    """A schema-2 track is what render() writes for the same résumé."""

    def test_every_track_matches_its_schema_1_render(self):
        conditions = ({}, {GATE: "1"}, {GATE: "1", CENTRALITY: "1"})
        for condition in conditions:
            for group in ([A, B, C], PERSONAS):
                with flags(**condition):
                    # The process engine says v1 throughout: render_sweep must
                    # not read it, render() stamps each track's own below.
                    os.environ[skill_concepts.VERSION_ENV] = "v1"
                    sweep = literals(make_profile.render_sweep("probe", group, PREFS))
                    for track in group:
                        one = schema1(track)
                        got = by_id(sweep["TRACKS"])[track["id"]]
                        with self.subTest(condition=condition, track=track["id"]):
                            self.assertEqual(got["engine"], track["engine"])
                            self.assertEqual(one["PROFILE_SCHEMA"]["engine"], track["engine"])
                            for section, keys in make_profile.TRACK_SECTIONS.items():
                                for key in keys:
                                    self.assertEqual(got[section][key], one[section][key],
                                                     f"{section}.{key}")
                            self.assertEqual(got["ATS_TITLE_HINTS"], one["ATS_TITLE_HINTS"])
                            self.assertEqual(got["ATS_TITLE_EXCLUDE"], one["ATS_TITLE_EXCLUDE"])
                            self.assertEqual(sweep["SCORING"]["hard_drop_terms"],
                                             one["SCORING"]["hard_drop_terms"])

    def test_the_candidate_gate_is_really_exercised(self):
        with flags():
            off = schema1(PERSONAS[0])["ATS_TITLE_HINTS"]
        with flags(**{GATE: "1"}):
            on = literals(make_profile.render_sweep("probe", PERSONAS, PREFS))["TRACKS"][0]
        self.assertNotEqual(on["ATS_TITLE_HINTS"], off)

    def test_the_output_is_deterministic(self):
        first = make_profile.render_sweep("probe", [A, B, C], PREFS)
        self.assertEqual(make_profile.render_sweep("probe", [A, B, C], PREFS), first)


# ===========================================================================
class SweepSeparation(EngineIsolated):

    def test_sweep_choices_are_written_once(self):
        source = make_profile.render_sweep("probe", [A, B, C], PREFS)
        got = literals(source)
        self.assertEqual(set(got), {"PROFILE_SCHEMA", "LOCATION_HINTS", "SITES", "SEARCH",
                                    "SETTINGS", "SCORING", "TRACKS"})
        self.assertEqual(got["SEARCH"], {"locations": PREFS["locations"], "salary_min": None,
                                         "max_results": 25})
        self.assertEqual(set(got["SETTINGS"]), {"min_comp_usd", "max_age_days", "remote_scopes",
                                                "work_scope", "max_spend_usd",
                                                "allow_partial_paid_sweep"})
        self.assertEqual(got["SCORING"], {"hard_drop_terms": PREFS["exclude_levels"]})
        sweep_keys = set(got["SEARCH"]) | set(got["SETTINGS"])
        for track in got["TRACKS"]:
            flat = {k for s in make_profile.TRACK_SECTIONS for k in track[s]}
            self.assertFalse(flat & sweep_keys)
        self.assertNotIn("FEEDS", got)      # the Himalayas union is Phase 3's

    def test_no_name_file_or_prose_reaches_the_file(self):
        source = make_profile.render_sweep("probe", [A, B, C], PREFS)
        for text in ("Synthetic Person", "SYNTHETIC-SUMMARY", "SYNTHETIC-NOTES", ".pdf"):
            self.assertNotIn(text, source)


# ===========================================================================
class TrackContexts(EngineIsolated):
    """Each track from pristine defaults plus its own values; nothing shared."""

    def build(self, order=(0, 1, 2)):
        sweep = literals(make_profile.render_sweep("probe", [A, B, C], PREFS))
        return {t.id: t for t in (scraper.track_context(sweep["TRACKS"][i], sweep["SCORING"])
                                  for i in order)}

    def test_shape_and_immutability(self):
        a = self.build()[A["id"]]
        self.assertEqual((a.engine, a.role_keywords, a.experience_years),
                         ("v2", ("react developer", "frontend engineer"), 3))
        self.assertIsInstance(a.scoring, scraper.ScoringContext)
        with self.assertRaises(AttributeError):
            a.role_keywords = ()
        self.assertFalse({"name", "resume_text", "token"} & set(vars(a)))

    def test_no_track_leaks_into_another(self):
        got = self.build()
        terms = {tid: {t for t, _w, _p in c.scoring.skill_terms} for tid, c in got.items()}
        self.assertEqual(terms[A["id"]], {"react", "react.js", "typescript"})
        self.assertEqual(terms[B["id"]], {"python", "django"})
        self.assertEqual(terms[C["id"]], {"node.js", "mongodb"})
        penalties = {tid: {t: w for t, w, _p in c.scoring.penalties} for tid, c in got.items()}
        self.assertEqual(penalties[B["id"]]["react"], -8)
        self.assertNotIn("react", penalties[A["id"]])
        self.assertEqual({tid: (c.scoring.max_experience_years, c.scoring.fullstack_bonus,
                                "frontend" in c.title_hints, "frontend" in c.title_exclude)
                          for tid, c in got.items()},
                         # C admits "frontend" through config's generic floor:
                         # B's exclude never reached it.
                         {A["id"]: (6, 0, True, False), B["id"]: (10, 0, False, True),
                          C["id"]: (4, 4, True, False)})
        self.assertEqual({c.engine for c in got.values()}, {"v1", "v2"})

    def test_construction_order_does_not_matter(self):
        forward, backward = self.build((0, 1, 2)), self.build((2, 1, 0))
        self.assertEqual({k: v.scoring.key for k, v in forward.items()},
                         {k: v.scoring.key for k, v in backward.items()})

    def test_built_on_pristine_defaults_never_on_the_live_globals(self):
        before = {k: v.scoring.key for k, v in self.build().items()}
        pristine = copy.deepcopy(config.BASE_SCORING)
        saved = copy.deepcopy(config.SCORING), dict(scraper.HARD_DROP_PATTERNS)
        def restore():
            config.SCORING.clear(); config.SCORING.update(saved[0])
            scraper.HARD_DROP_PATTERNS.clear(); scraper.HARD_DROP_PATTERNS.update(saved[1])
        self.addCleanup(restore)
        config.SCORING["skill_weights"] = {"zorb": 5}           # as a profile overlay would
        config.SCORING["hard_drop_terms"] = ["zorb"]
        scraper.HARD_DROP_PATTERNS["zorb"] = scraper._compile("zorb")
        self.assertEqual({k: v.scoring.key for k, v in self.build().items()}, before)
        # And the Sweep's own hard_drop_terms, when omitted, fall back to the
        # pristine default — not to what the overlay left in the globals.
        track = literals(make_profile.render_sweep("probe", [A], PREFS))["TRACKS"][0]
        bare = scraper.track_context(track, {})
        self.assertEqual([p.pattern for p in bare.scoring.hard_drop],
                         [scraper._compile(t).pattern for t in pristine["hard_drop_terms"]])
        self.assertEqual(config.BASE_SCORING, pristine)           # never written

    def test_each_scoring_context_is_the_schema_1_one(self):
        got = self.build()
        for track in (A, B, C):
            one = schema1(track)
            standalone = scraper.scoring_context({**config.BASE_SCORING, **one["SCORING"]},
                                                 one["SETTINGS"], track["engine"])
            with self.subTest(track=track["id"]):
                self.assertEqual(got[track["id"]].scoring.key, standalone.key)

    def test_one_job_three_tracks_independent_of_the_process_engine(self):
        got = self.build()
        job = {"Title": "Frontend Engineer", "Company": "Probe Co", "Location": "Bengaluru",
               "Description": "React, React.js, TypeScript, Python, Node.js and MongoDB."}
        answers = []
        with mock.patch.object(skill_concepts, "bind", side_effect=AssertionError("rebound")):
            for pinned in ("v1", "v2"):
                with flags(**{skill_concepts.VERSION_ENV: pinned}):
                    answers.append({tid: scraper.evaluate(job, c.scoring).score
                                    for tid, c in got.items()})
        self.assertEqual(answers[0], answers[1])
        self.assertEqual(len(set(answers[0].values())), 3)       # three different answers
        self.assertLess(answers[0][B["id"]], 0)                  # B penalises React


# ===========================================================================
PROBE = """
import contextlib, io, json, socket, sys
name, repo = sys.argv[1], sys.argv[2]
def no_network(*a, **k):
    raise RuntimeError("probe opened a connection")
socket.socket.connect = no_network
sys.argv = ["scraper.py", "--profile", name, "--dry-run", "--json"]
sys.path[:0] = [".", repo, repo + "/auto-apply"]
import config, scraper, skill_concepts
out = {"tracks": [[t["id"], t["engine"]] for t in config.TRACKS],
       "contexts": {c.id: c.scoring.key for c in scraper.TRACK_CONTEXTS},
       "profile_engine": config.PROFILE_ENGINE, "bound": skill_concepts._BOUND,
       "globals_hold_no_track": config.SCORING["skill_weights"]
           == config.BASE_SCORING["skill_weights"]
           and all(list(config.SEARCH["role_keywords"]) != t["SEARCH"]["role_keywords"]
                   for t in config.TRACKS)}
if config.TRACKS:
    row = {"Title": "React Developer", "Company": "Probe Co", "Description": "React."}
    for label, call in (("default_context", scraper.default_context),
                        ("score_job", lambda: scraper.score_job(dict(row))),
                        ("finalize", lambda: scraper.finalize([dict(row)]))):
        try:
            call(); out[label] = "ran"
        except RuntimeError as exc:
            out[label] = str(exc)
    printed = io.StringIO()
    try:
        with contextlib.redirect_stdout(printed):
            scraper.main()
        out["main"] = "ran"
    except SystemExit as exc:
        out["main"] = str(exc)
    out["main_printed"] = printed.getvalue()
else:
    out["default_key"] = scraper.default_context().key
print(json.dumps(out))
"""


class LoadedSweep(EngineIsolated):
    """A schema-2 file through the real import path, in fresh interpreters."""

    def probe(self, home, name):
        got = subprocess.run([sys.executable, "-c", PROBE, name, REPO], capture_output=True,
                             text=True, cwd=home, env=_env(home), timeout=120)
        self.assertEqual(got.returncode, 0, got.stderr[-3000:])
        return json.loads(got.stdout)

    def test_loads_contexts_fails_closed_and_matches_schema_1(self):
        home = tempfile.mkdtemp(prefix="track-loading-")
        self.addCleanup(shutil.rmtree, home, True)
        os.makedirs(os.path.join(home, "profiles"))
        open(os.path.join(home, "profiles", "__init__.py"), "w").close()

        def write(name, source):
            with open(os.path.join(home, "profiles", f"{name}.py"), "w", encoding="utf-8") as fh:
                fh.write(source)
        write("sweep3", make_profile.render_sweep("sweep3", [A, B, C], PREFS))
        for track in (A, B, C):
            with flags(**{skill_concepts.VERSION_ENV: track["engine"]}):
                write(f"one_{track['id']}", make_profile.render("one", track["derived"], PREFS))

        sweep = self.probe(home, "sweep3")
        self.assertEqual(sweep["tracks"], [[t["id"], t["engine"]] for t in (A, B, C)])
        self.assertIsNone(sweep["profile_engine"])
        self.assertIsNone(sweep["bound"])
        self.assertTrue(sweep["globals_hold_no_track"])
        refusal = "multi-context finalization not enabled"
        for label in ("default_context", "score_job", "finalize"):
            self.assertIn(refusal, sweep[label], label)          # never run as track 0
        # Phase 3 lifted main()'s refusal: its dry run is now the unified plan
        # (test_multi_plan). One-profile scoring above still refuses.
        self.assertEqual(sweep["main"], "ran")
        self.assertEqual(json.loads(sweep["main_printed"])["plan_version"], 2)
        for track in (A, B, C):
            one = self.probe(home, f"one_{track['id']}")
            with self.subTest(track=track["id"]):
                self.assertEqual(one["tracks"], [])
                self.assertEqual(one["contexts"], {})
                self.assertEqual(one["profile_engine"], track["engine"])
                self.assertEqual(sweep["contexts"][track["id"]], one["default_key"])


# ===========================================================================
# DQ6-F1-C1: the ALIGNMENT carrier — dark, beside POSITIONING, strict
# ===========================================================================
ALIGN, SCORE = make_profile.TRACK_ALIGNMENT_FLAG, make_profile.TRACK_SCORING_FLAG
CARRIED = {A["id"]: (["react", "typescript"], ["frontend"], ["frontend engineer"]),
           B["id"]: (["python", "django"], ["python"], ["python developer"]),
           C["id"]: (["node.js", "mongodb"], ["mern stack"], ["mern stack developer"])}
ALIGNMENT_BLOCK = re.compile(r'        "ALIGNMENT": \{\n(?:            .*\n)*?        \},\n')


def carried(track, alignment=True):
    """A track whose derivation carries what with_track_scoring would attach."""
    concepts, qualifiers, titles = CARRIED[track["id"]]
    extra = {"track_scoring": {"concepts": concepts, "role_qualifiers": qualifiers}}
    if alignment:
        extra["track_alignment"] = {"role_titles": titles}
    return dict(track, derived=dict(track["derived"], **extra))


class AlignmentCarrier(EngineIsolated):

    def render(self, tracks, **env):
        with mock.patch.dict(os.environ, env):
            return make_profile.render_sweep("probe", tracks, PREFS)

    def test_the_flag_is_dark_and_parsed_like_the_others(self):
        self.assertEqual(ALIGN, "SWEEP_TRACK_ALIGNMENT_RECOMMENDATION")
        for value, want in (("1", True), ("true", True), (" YES ", True), ("On", True),
                            ("0", False), ("", False), ("no", False), ("off", False)):
            with mock.patch.dict(os.environ, {ALIGN: value}):
                self.assertIs(make_profile.track_alignment_enabled(), want, value)
        with mock.patch.dict(os.environ):
            os.environ.pop(ALIGN, None)
            self.assertFalse(make_profile.track_alignment_enabled())

    def test_off_the_render_is_byte_identical(self):
        for group in ([A, B], [A, B, C]):
            plain = self.render([carried(t, False) for t in group], **{SCORE: "1"})
            for value in ("0", ""):
                off = self.render([carried(t) for t in group], **{SCORE: "1", ALIGN: value})
                self.assertEqual(off, plain)
            self.assertNotIn("ALIGNMENT", plain)

    def test_on_it_adds_the_alignment_section_and_nothing_else(self):
        for group in ([A, B], [A, B, C]):
            off = self.render([carried(t) for t in group], **{SCORE: "1"})
            on = self.render([carried(t) for t in group], **{SCORE: "1", ALIGN: "1"})
            self.assertEqual(ALIGNMENT_BLOCK.sub("", on), off)
            tracks = literals(on)["TRACKS"]
            for t in tracks:
                self.assertEqual(t["ALIGNMENT"], {"role_titles": CARRIED[t["id"]][2]})
                self.assertEqual(t["POSITIONING"], dict(zip(make_profile.POSITIONING_KEYS,
                                                            CARRIED[t["id"]][:2])))
            self.assertEqual([{k: v for k, v in t.items() if k != "ALIGNMENT"} for t in tracks],
                             literals(off)["TRACKS"])

    def test_it_needs_positioning_and_fails_closed(self):
        for group in ([A, B], [A, B, C]):
            for scoring in ("0", ""):
                with self.assertRaisesRegex(ValueError, ALIGN):
                    self.render([carried(t) for t in group], **{SCORE: scoring, ALIGN: "1"})
            with self.assertRaisesRegex(ValueError, "track_alignment"):
                self.render([carried(t, False) for t in group], **{SCORE: "1", ALIGN: "1"})

    def test_one_resume_never_carries_it(self):
        for scoring in ("0", "1"):
            base = self.render([A], **{SCORE: scoring})
            self.assertEqual(self.render([A], **{SCORE: scoring, ALIGN: "1"}), base)
            self.assertEqual(self.render([carried(A)], **{SCORE: scoring, ALIGN: "1"}), base)
            self.assertNotIn("ALIGNMENT", base)
            with mock.patch.dict(os.environ, {SCORE: scoring, ALIGN: "1"}):
                one = make_profile.render("probe", A["derived"], PREFS)
            self.assertEqual(one, make_profile.render("probe", A["derived"], PREFS))

    def good(self):
        return literals(self.render([carried(t) for t in (A, B, C)], **{SCORE: "1", ALIGN: "1"}))["TRACKS"]

    def test_strict_validation(self):
        good = self.good()
        self.assertEqual(make_profile.check_tracks(copy.deepcopy(good)), good)
        empty = copy.deepcopy(good)
        empty[1]["ALIGNMENT"]["role_titles"] = []
        make_profile.check_tracks(empty)                        # a track may carry none
        ai = copy.deepcopy(good)                                # a header specialism's phrase
        ai[0]["POSITIONING"]["role_qualifiers"] = ["ai engineer", "frontend"]
        ai[0]["ALIGNMENT"]["role_titles"] = ["ai engineer", "frontend engineer"]
        make_profile.check_tracks(ai)

        def with_(value=None, drop_positioning=False, **section):
            tracks = copy.deepcopy(good)
            if value is not None:
                tracks[0]["ALIGNMENT"] = value
            if section:
                tracks[0]["ALIGNMENT"] = dict(tracks[0]["ALIGNMENT"], **section)
            if drop_positioning:
                for t in tracks:
                    t.pop("POSITIONING")
            return tracks
        cases = {
            "not a dict": with_(["frontend engineer"]),
            "extra key": with_(role_titles=["frontend engineer"], sources=["summary"]),
            "no role_titles": with_({}),
            "not a list": with_(role_titles="frontend engineer"),
            "not strings": with_(role_titles=[3]),
            "empty title": with_(role_titles=[""]),
            "untrimmed": with_(role_titles=[" frontend engineer"]),
            "duplicate": with_(role_titles=["frontend engineer", "frontend engineer"]),
            "three titles": with_(role_titles=["frontend engineer", "frontend developer",
                                               "frontend architect"]),
            "not normalised": with_(role_titles=["Frontend Engineer"]),
            "compound spelling": with_(role_titles=["front end engineer"]),
            "no role head": with_(role_titles=["frontend"]),
            "a qualifier POSITIONING lacks": with_(role_titles=["backend engineer"]),
            "without POSITIONING": with_(drop_positioning=True),
            "on some tracks only": [dict(t) if i else {k: v for k, v in t.items()
                                                       if k != "ALIGNMENT"}
                                    for i, t in enumerate(copy.deepcopy(good))],
            "one track": copy.deepcopy(good)[:1],
            "an unknown track key": [dict(t, ALIGNMENTS=t["ALIGNMENT"]) for t in copy.deepcopy(good)],
        }
        for label, tracks in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                make_profile.check_tracks(tracks)

    def test_a_contract_without_alignment_refuses_it(self):
        """A stale engine's exact track keys: with ALIGNMENT unknown to the
        validator, a profile carrying it is refused, never half-read."""
        tracks = self.good()
        with mock.patch.object(make_profile, "ALIGNMENT", "__before_dq6_f1c1__"):
            with self.assertRaisesRegex(ValueError, "must have exactly"):
                make_profile.check_tracks(tracks)

    def test_the_loader_reads_it_into_the_track_context_only(self):
        """C's role title is not one of its role_keywords: whatever ALIGNMENT
        carries, the track searches, gates and scores exactly as without it."""
        good = literals(self.render([carried(t) for t in (A, B, C)], **{SCORE: "1", ALIGN: "1"}))
        bare = literals(self.render([carried(t) for t in (A, B, C)], **{SCORE: "1"}))
        self.assertNotIn("mern stack developer", good["TRACKS"][2]["SEARCH"]["role_keywords"])
        mod = types.ModuleType("profiles.aligned")
        for key, value in good.items():
            setattr(mod, key, value)
        sys.modules["profiles.aligned"] = mod
        self.addCleanup(sys.modules.pop, "profiles.aligned", None)
        module, stamp = config.load_profile_module("aligned")
        self.assertEqual((stamp["version"], stamp["engine"]), (2, "multi"))
        on = [scraper.track_context(t, good["SCORING"]) for t in module.TRACKS]
        off = [scraper.track_context(t, bare["SCORING"]) for t in bare["TRACKS"]]
        self.assertEqual([t.role_titles for t in on], [("frontend engineer",), ("python developer",),
                                                       ("mern stack developer",)])
        self.assertEqual([t.role_titles for t in off], [(), (), ()])
        self.assertEqual([t.scoring.key for t in on], [t.scoring.key for t in off])
        for a, b in zip(on, off):
            self.assertEqual((a.id, a.role_keywords, a.experience_years, a.title_hints, a.title_exclude),
                             (b.id, b.role_keywords, b.experience_years, b.title_hints, b.title_exclude))


class SchemaOneUnchanged(unittest.TestCase):

    def test_a_schema_1_process_has_no_tracks(self):
        self.assertEqual(config.TRACKS, ())
        self.assertEqual(config.SWEEP_SCORING, {})
        self.assertEqual(scraper.TRACK_CONTEXTS, ())
        self.assertNotIn("TRACKS", config.OVERLAYABLE)


if __name__ == "__main__":
    unittest.main()
