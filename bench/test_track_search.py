"""DQ2c-1 / DQ2c-3: track-specific search intent (track_search.py), pure.
Run: python -m unittest bench.test_track_search

Fixtures are DQ2b's synthetic résumés replayed from their committed captures
(bench/results/targeted-qwen3_8b.json): no model, sockets refused. Each is
derived in a sealed environment, and the few that exercise the derivation's
guards again under production's behaviour flags, pinned here rather than
inherited from the caller's shell. It lives in bench/ because DQ2b's fixtures
may be read only from here (test_targeted: the manifest reaches no derivation).
"""
import copy
import dataclasses
import inspect
import json
import os
import socket
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (REPO_ROOT, os.path.join(REPO_ROOT, "auto-apply")):
    if path not in sys.path:
        sys.path.insert(0, path)

import config  # noqa: E402
import local_search  # noqa: E402
import make_profile  # noqa: E402
import scraper  # noqa: E402
import track_intent  # noqa: E402
import track_scoring  # noqa: E402
import track_search as ts  # noqa: E402
from bench import targeted  # noqa: E402

SEALED_ENV = {"PATH": "/usr/bin:/bin", "HOME": tempfile.gettempdir(), "LANG": "en_US.UTF-8",
              "PYTHONDONTWRITEBYTECODE": "1", "SWEEP_PROFILE_ENGINE_VERSION": "v2"}
# Production's behaviour flags, so the derivation runs the guards it runs there.
LIVE_ENV = dict(SEALED_ENV, SWEEP_PROFILE_ENGINE="local", SWEEP_ROLE_EVIDENCE="1",
                SWEEP_ROLE_ATTACHMENT_GUARD="1", SWEEP_CANONICAL_REVALIDATION="1",
                SWEEP_CANONICAL_FALLBACK="discard", SWEEP_CANDIDATE_HARD_DROP="1",
                SWEEP_UNKNOWN_FAMILY_GUARD="1", SWEEP_ORPHAN_ROLE_GUARD="0",
                SWEEP_SEMANTIC_SCOPE="1", SWEEP_SEMANTIC_SCOPE_NEGATION_VERBS="0",
                SWEEP_CANDIDATE_TITLE_GATE="1", SWEEP_FAMILY_CENTRALITY_GATE="1",
                SWEEP_MARKET_COMPOUND_SPLIT="1")
SEALED_DOCS = ("platform-backend-plain", "platform-backend-twocol", "platform-platform-plain",
               "platform-platform-twocol", "platform-generic-plain", "quality-reliability-plain",
               "quality-reliability-twocol", "quality-sdet-plain", "quality-sdet-twocol",
               "quality-automation-plain", "data-ml-plain", "data-ml-twocol",
               "data-analytics-plain", "data-grouped-control-plain", "app-fullstack-plain",
               "app-mobile-plain")
LIVE_DOCS = ("data-ml-plain", "quality-automation-plain", "platform-generic-plain")
SEALED, LIVE = {}, {}       # doc -> (text, derived, intent)
MARKET = []
_patches = []


def setUpModule():
    refuse = mock.patch.object(socket.socket, "connect",
                               side_effect=RuntimeError("track_search tests opened a socket"))
    refuse.start()
    _patches.append(refuse)
    captures = targeted.load_captures()
    for store, env, docs in ((SEALED, SEALED_ENV, SEALED_DOCS), (LIVE, LIVE_ENV, LIVE_DOCS)):
        with mock.patch.dict(os.environ, env, clear=True), \
                tempfile.TemporaryDirectory() as empty:
            if not MARKET:
                MARKET.append(local_search.frozen_market())
            for doc in docs:
                text, derived, _gate = targeted.derive(doc, captures, empty)
                store[doc] = (text, derived, track_intent.derive_track_intent(text, derived))


def tearDownModule():
    while _patches:
        _patches.pop().stop()


def search(store, doc):
    text, derived, intent = store[doc]
    return ts.derive_track_search(text, derived, intent, MARKET[0])


def concept(cid, sources=("summary",)):
    return track_intent.IntentConcept(cid, False, tuple(sources), False, ())


def intent_of(concepts, groups=(), order=(), titles=()):
    return track_intent.TrackIntent(
        concepts=tuple(concepts), declared_titles=tuple(titles), work_only=(),
        other_claimed=(), skills_groups=tuple(groups), skills_order=tuple(order),
        provenance=(), sufficient=True, reason="")


def declared(title, source="summary"):
    return track_intent.DeclaredTitle(title, source, (0, 0), (title,), ())


class NoVocabulary:
    """A corpus that knows none of a track's concepts, so retrieval is broad.
    Enough for a track sufficient by its concepts alone: no title to validate."""
    vocab = {}


# ---------------------------------------------------------------------------
class Normalization(unittest.TestCase):

    def check(self, pairs):
        for raw, want in pairs:
            self.assertEqual(ts.normalize_query(raw), want, raw)

    def test_a_joiner_between_words_is_a_space(self):
        self.check((("Full-Stack Engineer", "full stack engineer"),
                    ("React-Native Developer", "react native developer"),
                    ("AI/ML Engineer", "ai ml engineer"),
                    ("data_engineer", "data engineer")))

    def test_punctuation_inside_a_technology_token_stays(self):
        self.check((("Node.js Developer", "node.js developer"),
                    ("C++/C# Developer", "c++ c# developer"),
                    ("C# Engineer", "c# engineer")))

    def test_only_the_three_role_compounds(self):
        self.check((("FullStack Developer", "full stack developer"),
                    ("Front-End Engineer", "frontend engineer"),
                    ("front end engineer", "frontend engineer"),
                    ("Back-End Developer", "backend developer"),
                    ("back end developer", "backend developer"),
                    ("front endpoint developer", "front endpoint developer")))

    def test_no_semantic_alias(self):
        self.check((("React Developer", "react developer"), ("AI Engineer", "ai engineer"),
                    ("ML Engineer", "ml engineer"), ("MERN Stack Developer", "mern stack developer"),
                    ("Mobile Engineer", "mobile engineer")))

    def test_whitespace_collapses_and_a_spaced_slash_stays(self):
        self.check((("  Backend   Engineer ", "backend engineer"),
                    ("backend / platform engineer", "backend / platform engineer")))

    def test_qualifier_is_the_title_without_its_role_words(self):
        for title, want in (("Backend Engineer", "backend"),
                            ("React Native Developer", "react native"),
                            ("Full-Stack Engineer", "full stack"),
                            ("Machine Learning Engineer", "machine learning"),
                            ("Software Engineer", ""), ("Developer", "")):
            self.assertEqual(ts.qualifier(title), want, title)


# ---------------------------------------------------------------------------
class HeadFreeConcepts(unittest.TestCase):

    def test_a_generic_word_alone_does_not_position(self):
        ids = ("engineer", "engineering", "developer", "development", "software", "data",
               "tools", "languages", "software engineering")
        kept, excluded = ts.positioning_concepts(intent_of(concept(c) for c in ids))
        self.assertEqual(kept, ())
        self.assertEqual(excluded, tuple((c, "generic") for c in ids))

    def test_a_phrase_with_a_specialist_residue_positions(self):
        ids = ("data engineering", "software testing", "mobile development", "kubernetes",
               "react native")
        kept, excluded = ts.positioning_concepts(intent_of(concept(c) for c in ids))
        self.assertEqual(tuple(c.id for c in kept), ids)
        self.assertEqual(excluded, ())

    def test_a_skills_label_read_as_a_skill_is_excluded(self):
        label_only = intent_of([concept("test automation")], groups=("Test Automation", "Tools"),
                               order=(("test automation", 0, 0),))
        self.assertEqual(ts.positioning_concepts(label_only)[1],
                         (("test automation", "group_label"),))
        listed_too = dataclasses.replace(label_only, skills_order=(
            ("test automation", 0, 0), ("test automation", 1, 2)))
        self.assertEqual(ts.positioning_concepts(listed_too)[1], ())
        other_label = dataclasses.replace(label_only, skills_groups=("Testing", "Tools"))
        self.assertEqual(ts.positioning_concepts(other_label)[1], ())

    def test_the_label_leaks_dq2b_measured_and_the_layouts_then_agree(self):
        for variant, leak, leaked_layout in (("data-ml", "machine learning", "plain"),
                                             ("quality-sdet", "test automation", "twocol")):
            got = {layout: search(SEALED, f"{variant}-{layout}")
                   for layout in targeted.LAYOUTS}
            for layout, result in got.items():
                want = ((leak, "group_label"),) if layout == leaked_layout else ()
                self.assertEqual(result.excluded_concepts, want, (variant, layout))
            self.assertEqual(set(got["plain"].concepts), set(got["twocol"].concepts), variant)


# A synthetic résumé whose summary names a methodology and two AI coding
# assistants beside its frontend stack (Scrum and Cursor only in the list).
PRACTICE_TEXT = """Summary
Frontend developer building React apps with Redux in Agile teams, using Claude and GitHub Copilot.
Technical Skills
Frontend: React, Redux
Practice: Agile, Scrum, Unit Testing
Tools: Claude, GitHub Copilot, Cursor
"""
PRACTICE_SKILLS = ("react", "redux", "agile", "scrum", "unit testing", "claude",
                   "github copilot", "cursor")
PRACTICE_IDS = ("agile", "scrum", "claude", "github copilot", "cursor")


def practice_resume():
    """(text, derived, intent): the production evidence step
    (make_profile.reweight_from_evidence) over a hand-written skill list, as
    auto-apply/tests/test_track_intent derives. No model."""
    with tempfile.TemporaryDirectory() as empty:
        derived = make_profile.reweight_from_evidence(
            {"candidate_name": "",
             "skill_weights": [{"term": s, "weight": 3} for s in PRACTICE_SKILLS]},
            PRACTICE_TEXT, output_dir=empty, log=lambda *a, **k: None)
    return PRACTICE_TEXT, derived, track_intent.derive_track_intent(PRACTICE_TEXT, derived)


class PracticeConcepts(unittest.TestCase):
    """How someone works — a methodology, an AI coding assistant — is
    capability evidence, never role positioning: it cannot say which of one
    person's résumés this is (DQ6-F1-B)."""

    def test_methodology_and_coding_assistants_never_position(self):
        ids = ("agile", "scrum", "claude", "github copilot", "cursor", "github-copilot")
        kept, excluded = ts.positioning_concepts(intent_of(concept(c) for c in ids))
        self.assertEqual(kept, ())
        self.assertEqual(excluded, tuple((c, "practice") for c in ids))

    def test_role_and_broad_capability_concepts_still_position(self):
        ids = ("react", "react native", "redux toolkit", "javascript", "machine learning",
               "unit testing", "testing", "code reviews", "ci/cd", "debugging", "rest api",
               "sql", "caching", "git")
        kept, excluded = ts.positioning_concepts(intent_of(concept(c) for c in ids))
        self.assertEqual(tuple(c.id for c in kept), ids)
        self.assertEqual(excluded, ())

    def test_search_and_scoring_drop_them_together_and_evidence_keeps_them(self):
        text, derived, intent = practice_resume()
        before = copy.deepcopy(derived)
        self.assertLessEqual({"react", "redux", "agile", "claude", "github copilot"}, intent.ids)
        found = ts.derive_track_search(text, derived, intent, MARKET[0])
        record = track_scoring.derive_track_scoring(intent, found)
        self.assertEqual(found.concepts, ("react", "redux"))
        self.assertEqual(found.excluded_concepts,
                         tuple((c, "practice") for c in ("agile", "claude", "github copilot")))
        self.assertEqual(record.concepts, found.concepts)
        self.assertEqual(derived, before)
        evidence = {row["id"] for row in derived["skill_importance"]}
        weights = {w["term"]: w["weight"] for w in derived["skill_weights"]}
        for cid in PRACTICE_IDS:
            self.assertIn(cid, evidence)
            self.assertGreater(weights[cid], 0, cid)

    def test_they_still_score_as_evidence_and_earn_no_positioning(self):
        text, derived, intent = practice_resume()
        record = track_scoring.derive_track_scoring(
            intent, ts.derive_track_search(text, derived, intent, MARKET[0]))
        scoring = dict(config.BASE_SCORING, penalty_terms={}, frontend_terms=[],
                       backend_terms=[], fullstack_title_terms=[], fullstack_bonus=0,
                       skill_weights={w["term"]: w["weight"] for w in derived["skill_weights"]})
        settings = {"max_experience_years": 6, "candidate_experience_months": 40}
        base = scraper.scoring_context(scoring, settings, "v2")
        positioned = scraper.scoring_context(scoring, settings, "v2", {
            "concepts": list(record.concepts), "role_qualifiers": list(record.role_qualifiers)})
        row = {"Title": "Frontend Developer", "Company": "Example", "Location": "Remote",
               "Description": "An Agile, Scrum team shipping React with Claude, "
                              "GitHub Copilot and Cursor."}
        facts = scraper.job_facts(row)
        plain, scored = (scraper.evaluate(dict(row), c, facts) for c in (base, positioned))
        self.assertEqual(scored.matched_skills, plain.matched_skills)
        self.assertLessEqual(set(PRACTICE_IDS),
                             {s.strip().lower() for s in plain.matched_skills.split(",")})
        self.assertEqual(scraper.positioning_points(positioned, facts.text, facts.title), (1, 3))
        self.assertEqual(scored.score, plain.score + 4)

    def test_one_resume_never_reaches_the_rule_and_keeps_every_weight(self):
        text, derived, _intent = practice_resume()
        data = dict(derived, years_experience=3, role_keywords=["frontend developer"],
                    penalty_terms=[], domain_half_a=[], domain_half_b=[], domain_title_terms=[],
                    domain_bonus=0, field_summary="", notes="")
        one = [{"id": "solo", "engine": "v2", "derived": data}]
        on = dict(SEALED_ENV, **{make_profile.TRACK_SEARCH_FLAG: "1",
                                 make_profile.TRACK_SCORING_FLAG: "1"})
        with mock.patch.object(ts, "positioning_concepts",
                               side_effect=AssertionError("one résumé positioned")), \
                mock.patch.dict(os.environ, on, clear=True):
            got = make_profile.with_track_scoring(
                make_profile.with_track_search(one, [text], MARKET[0]), [text], MARKET[0])
            source = make_profile.render("solo", data, dict(targeted.PREFS), engine="v2")
        self.assertIs(got[0], one[0])
        ns = {}
        exec(compile(source, "<solo>", "exec"), ns)
        weights = {w["term"]: w["weight"] for w in derived["skill_weights"]}
        self.assertEqual({c: ns["SCORING"]["skill_weights"][c] for c in PRACTICE_IDS},
                         {c: weights[c] for c in PRACTICE_IDS})


# Synthetic résumés for header specialisms: a header, a summary, optional body
# sections, one skills line; derived by the production evidence step with a
# legacy title list like today's derivation carries.
SPEC_SKILLS = ("react", "node.js", "python")
SPEC_LEGACY = ("react developer", "node.js developer", "mern stack developer")
SECURITY = "Software engineer focused on application security, building React and Node.js services."


def spec_text(header, summary, body="", label="Core", skills=SPEC_SKILLS):
    return (f"{header}\nSummary\n{summary}\n{body}Technical Skills\n"
            f"{label}: {', '.join(skills)}\n")


def spec_derived(text, skills=SPEC_SKILLS):
    with tempfile.TemporaryDirectory() as empty:
        derived = make_profile.reweight_from_evidence(
            {"candidate_name": "", "skill_weights": [{"term": s, "weight": 3} for s in skills]},
            text, output_dir=empty, log=lambda *a, **k: None)
    return dict(derived, role_keywords=list(SPEC_LEGACY))


def spec_records(text, skills=SPEC_SKILLS):
    """(intent, search, scoring) of one synthetic résumé, frozen market."""
    derived = spec_derived(text, skills)
    intent = track_intent.derive_track_intent(text, derived)
    found = ts.derive_track_search(text, derived, intent, MARKET[0])
    return intent, found, track_scoring.derive_track_scoring(intent, found)


def spec_dicts(text, skills=SPEC_SKILLS):
    return tuple(r.as_dict() for r in spec_records(text, skills))


def blank(text, segment):
    """The same résumé without `segment`, every offset kept."""
    assert segment in text, segment
    return text.replace(segment, " " * len(segment))


def title_points(qualifiers, title):
    scoring = dict(config.BASE_SCORING, skill_weights={}, penalty_terms={}, frontend_terms=[],
                   backend_terms=[], fullstack_title_terms=[], fullstack_bonus=0)
    ctx = scraper.scoring_context(scoring, {"max_experience_years": 6}, "v2",
                                  {"concepts": [], "role_qualifiers": list(qualifiers)})
    return scraper.positioning_points(ctx, "", scraper.job_facts({"Title": title}).title)[1]


class HeaderSpecialisms(unittest.TestCase):
    """DQ6-F1-A. "Software Engineer | Applied AI & Full-Stack": a header names a
    profession, then its specialisms without repeating the role word. Each
    borrows the title's head, only there; it counts only when the résumé's own
    summary or project text says it and the market uses the title; and then
    the résumé has named its roles, which replace — never add to — retrieval."""

    AI = spec_text("Software Engineer | Applied AI & Full-Stack",
                   "Builds AI-backed applications and full-stack web products with Python, "
                   "React and Node.js.")

    def test_a_grounded_specialism_names_the_search_and_keeps_its_head(self):
        derived = spec_derived(self.AI)
        before = copy.deepcopy(derived)
        intent = track_intent.derive_track_intent(self.AI, derived)
        found = ts.derive_track_search(self.AI, derived, intent, MARKET[0])
        scoring = track_scoring.derive_track_scoring(intent, found)
        self.assertEqual([(t.title, t.parts) for t in intent.declared_titles
                          if t.source == ts.SPECIALISM],
                         [("applied ai", ("ai engineer",)), ("full-stack", ("full-stack engineer",))])
        self.assertEqual(found.leading_titles, (ts.SearchTitle("ai engineer", ts.SPECIALISM),
                                                ts.SearchTitle("full stack engineer", ts.SPECIALISM)))
        self.assertEqual((found.retrieval, found.role_keywords, found.focused_titles,
                          found.fallback_used),
                         (ts.SPECIALISM, ("ai engineer", "full stack engineer"), (), False))
        self.assertEqual(scoring.role_qualifiers, ("ai engineer", "full stack engineer"))
        self.assertEqual(derived, before)       # evidence read, never written

    def test_title_alignment_needs_the_role_phrase_not_the_word(self):
        qualifiers = spec_records(self.AI)[2].role_qualifiers
        self.assertTrue(all(set(q.split()) & ts.ROLE_WORDS for q in qualifiers), qualifiers)
        for title in ("Senior AI Engineer", "Applied AI Engineer", "Gen AI Engineer",
                      "Full Stack Engineer"):
            self.assertEqual(title_points(qualifiers, title), scraper.POSITIONING_TITLE_BONUS, title)
        for title in ("AI Product Manager", "AI Training Specialist", "AI Video Recorder",
                      "AI Go-To-Market Lead", "Software Engineer using AI tools",
                      "Full Stack Developer"):
            self.assertEqual(title_points(qualifiers, title), 0, title)

    def test_an_ungrounded_or_tool_only_specialism_changes_nothing(self):
        for text, segment in (
                (spec_text("Software Engineer | Payments", "Builds React and Node.js services."),
                 " | Payments"),
                (spec_text("Software Engineer | Applied AI",
                           "Ships React and Node.js apps, pairing with GitHub Copilot and Claude.",
                           body="Experience\nAcme Labs\nEngineer 2021 - 2024\n"
                                "- Built AI features for the billing product.\n",
                           label="AI Tools", skills=SPEC_SKILLS + ("github copilot", "claude")),
                 " | Applied AI")):
            skills = SPEC_SKILLS + (("github copilot", "claude") if "Copilot" in text else ())
            self.assertEqual(spec_dicts(text, skills), spec_dicts(blank(text, segment), skills),
                             segment)
        _i, found, _s = spec_records(text, skills)
        self.assertLessEqual({("github copilot", "practice"), ("claude", "practice")},
                             set(found.excluded_concepts))

    def test_only_a_title_the_market_uses_leads(self):
        for header, summary, segment in (
                ("Software Engineer | Payments", "Builds payments systems with React and Node.js.",
                 " | Payments"),
                ("Software Engineer | Random Hobby",
                 "Enjoys a random hobby while building React and Node.js services.",
                 " | Random Hobby")):
            text = spec_text(header, summary)
            intent, found, _s = spec_records(text)
            self.assertTrue(any(t.source == ts.SPECIALISM for t in intent.declared_titles), header)
            self.assertTrue(all(r.reason == ts.VALIDATION for r in found.rejected_titles
                                if r.source == ts.SPECIALISM), found.rejected_titles)
            plain = spec_records(blank(text, segment))[1]
            self.assertEqual((found.leading_titles, found.retrieval, found.role_keywords),
                             (plain.leading_titles, plain.retrieval, plain.role_keywords), header)

    def test_a_specialism_led_track_searches_only_its_named_roles(self):
        inferred = spec_records(spec_text("Software Engineer", SECURITY))[1]
        titled = spec_records(spec_text("Security Engineer", SECURITY))[1]
        led = spec_records(spec_text("Software Engineer | Security", SECURITY))[1]
        self.assertNotEqual(inferred.retrieval, ts.SPECIALISM)
        self.assertEqual(inferred.role_keywords, ("react developer", "node.js developer"))
        self.assertEqual(titled.leading_titles, (ts.SearchTitle("security engineer", "header"),))
        self.assertEqual(titled.role_keywords,                   # a plain title keeps retrieval
                         ("security engineer", "react developer", "node.js developer"))
        self.assertEqual(led.leading_titles, (ts.SearchTitle("security engineer", ts.SPECIALISM),))
        self.assertEqual((led.role_keywords, led.focused_titles, led.fallback_used),
                         (("security engineer",), (), False))   # one title, no top-up
        self.assertLess(len(led.role_keywords), ts.MIN_TOP_UP)

    def test_at_most_two_specialisms_lead(self):
        found = spec_records(spec_text(
            "Software Engineer | Security & DevOps & Cloud",
            "Works on security, DevOps pipelines and cloud infrastructure with Python, React "
            "and Node.js."))[1]
        self.assertEqual(found.role_keywords, ("security engineer", "devops engineer"))
        self.assertIn(ts.RejectedTitle("cloud engineer", ts.SPECIALISM, ts.LIMIT),
                      found.rejected_titles)

    def test_a_suffix_the_body_never_names_leaves_every_record_as_it_was(self):
        text = spec_text("Full-Stack Software Engineer | MERN",
                         "Full-stack engineer building React and Node.js services.",
                         body="Experience\nAcme Labs\nEngineer 2021 - 2024\n"
                              "- Built MERN stack apps for retail clients.\n",
                         label="MERN")
        self.assertEqual(spec_dicts(text), spec_dicts(blank(text, " | MERN")))

    def test_only_the_header_can_lend_a_head(self):
        text = spec_text("Software Engineer",
                         "Backend Engineer | Security\nFocused on application security with "
                         "React and Node.js.")
        intent, found, _s = spec_records(text)
        self.assertIn(("backend engineer", "summary"),
                      [(t.title, t.source) for t in intent.declared_titles])
        self.assertFalse(any(t.source == ts.SPECIALISM for t in intent.declared_titles))
        self.assertNotEqual(found.retrieval, ts.SPECIALISM)

    def test_slash_semantics_are_unchanged(self):
        summary = "Runs cloud platforms and DevOps pipelines with Python, React and Node.js."
        text = spec_text("Platform Engineer | Cloud / DevOps", summary)
        self.assertEqual(spec_dicts(text), spec_dicts(blank(text, " | Cloud / DevOps")))
        declared = spec_records(spec_text("Cloud / DevOps Engineer", summary))[0].declared_titles
        self.assertEqual([(t.title, t.source, t.parts) for t in declared],
                         [("cloud / devops engineer", "header", ("devops engineer",))])

    def test_one_resume_never_reads_a_specialism(self):
        derived = spec_derived(self.AI)
        data = dict(derived, years_experience=3, penalty_terms=[], domain_half_a=[],
                    domain_half_b=[], domain_title_terms=[], domain_bonus=0, field_summary="",
                    notes="")
        one = [{"id": "solo", "engine": "v2", "derived": data}]
        on = dict(SEALED_ENV, **{make_profile.TRACK_SEARCH_FLAG: "1",
                                 make_profile.TRACK_SCORING_FLAG: "1"})
        with mock.patch.object(track_intent, "_specialisms",
                               side_effect=AssertionError("one résumé read a specialism")), \
                mock.patch.dict(os.environ, on, clear=True):
            got = make_profile.with_track_scoring(
                make_profile.with_track_search(one, [self.AI], MARKET[0]), [self.AI], MARKET[0])
            source = make_profile.render("solo", data, dict(targeted.PREFS), engine="v2")
        self.assertIs(got[0], one[0])
        ns = {}
        exec(compile(source, "<solo>", "exec"), ns)
        self.assertEqual(ns["SEARCH"]["role_keywords"], list(SPEC_LEGACY))

    def test_no_dq2b_document_declares_a_specialism(self):
        for store in (SEALED, LIVE):
            for doc in store:
                intent = store[doc][2]
                self.assertFalse([t for t in intent.declared_titles if t.source == ts.SPECIALISM],
                                 doc)
                self.assertNotEqual(search(store, doc).retrieval, ts.SPECIALISM, doc)


# ---------------------------------------------------------------------------
class LeadingTitles(unittest.TestCase):

    def test_a_supported_header_leads_in_both_layouts(self):
        for layout in targeted.LAYOUTS:
            got = search(SEALED, f"platform-backend-{layout}")
            self.assertEqual(got.leading_titles, (ts.SearchTitle("backend engineer", "header"),))
            self.assertEqual(got.role_keywords[0], "backend engineer")

    def test_a_misleading_header_is_rejected_and_the_summary_title_leads(self):
        for layout in targeted.LAYOUTS:
            got = search(SEALED, f"platform-platform-{layout}")
            self.assertIn(ts.RejectedTitle("backend engineer", "header", ts.UNSUPPORTED_HEADER),
                          got.rejected_titles, layout)
            self.assertEqual(got.leading_titles,
                             (ts.SearchTitle("platform engineer", "summary"),), layout)
            self.assertNotIn("backend engineer", got.role_keywords, layout)

    def test_a_misleading_header_alone_leaves_the_track_to_its_concepts(self):
        for layout in targeted.LAYOUTS:
            got = search(SEALED, f"quality-reliability-{layout}")
            self.assertEqual(got.leading_titles, (), layout)
            self.assertEqual(got.rejected_titles, (ts.RejectedTitle(
                "qa automation engineer", "header", ts.UNSUPPORTED_HEADER),), layout)
            self.assertEqual((got.sufficient, got.reason), (True, "concepts"), layout)
            self.assertNotIn("qa automation engineer", got.role_keywords, layout)

    def test_a_wildcard_title_never_leads_nor_suffices(self):
        full = search(SEALED, "app-fullstack-plain")
        self.assertIn(ts.RejectedTitle("software engineer", "header", ts.WILDCARD),
                      full.rejected_titles)
        self.assertEqual(full.leading_titles, (ts.SearchTitle("full stack engineer", "summary"),))
        generic = search(SEALED, "platform-generic-plain")
        self.assertEqual(generic.rejected_titles,
                         (ts.RejectedTitle("software engineer", "header", ts.WILDCARD),))
        self.assertEqual((generic.sufficient, generic.leading_titles), (False, ()))

    def test_the_declared_wording_leads_never_a_corpus_title(self):
        for doc, (_text, _derived, intent) in SEALED.items():
            parts = {ts.normalize_query(p) for d in intent.declared_titles for p in d.parts}
            for title in search(SEALED, doc).leading_titles:
                self.assertIn(title.query, parts, doc)

    def test_validation_the_role_gate_and_the_limit_reject_a_declared_title(self):
        text, derived, intent = LIVE["data-ml-plain"]
        extra = dataclasses.replace(intent, declared_titles=intent.declared_titles + (
            declared("engineering manager"), declared("flutter developer")))
        got = ts.derive_track_search(text, derived, extra, MARKET[0])
        reasons = {t.query: t.reason for t in got.rejected_titles}
        self.assertEqual(reasons["engineering manager"], ts.VALIDATION)
        self.assertEqual(reasons["flutter developer"], ts.ROLE_GATE)
        text, derived, intent = SEALED["app-mobile-plain"]
        more = dataclasses.replace(intent, declared_titles=intent.declared_titles + (
            declared("react native developer"), declared("android developer")))
        got = ts.derive_track_search(text, derived, more, MARKET[0])
        self.assertEqual([t.query for t in got.leading_titles],
                         ["mobile engineer", "react native developer"])
        self.assertIn(ts.RejectedTitle("android developer", "summary", ts.LIMIT),
                      got.rejected_titles)


# ---------------------------------------------------------------------------
class Retrieval(unittest.TestCase):

    def test_the_tier_follows_sufficiency_and_corpus_known_concepts(self):
        for doc in SEALED:
            got = search(SEALED, doc)
            self.assertEqual(got.corpus_known,
                             tuple(c for c in got.concepts if MARKET[0].vocab.get(c, 0) > 0), doc)
            want = ("fallback" if not got.sufficient else
                    "focused" if len(got.corpus_known) >= ts.MIN_CORPUS_KNOWN else "broad")
            self.assertEqual(got.retrieval, want, doc)
        self.assertEqual(search(SEALED, "quality-sdet-plain").retrieval, "broad")
        self.assertEqual(search(SEALED, "app-mobile-plain").retrieval, "focused")

    def test_anchoring_keeps_focused_titles_and_drops_hubs(self):
        dropped = []
        for doc in SEALED:
            got = search(SEALED, doc)
            if got.retrieval != "focused":
                continue
            _text, derived, intent = SEALED[doc]
            raw = ts.focused_candidates(got.corpus_known, derived, MARKET[0],
                                        derived["role_keywords"])
            words = ts.anchors(got.leading_titles, ts.positioning_concepts(intent)[0])
            self.assertEqual(list(got.focused_titles), ts.anchored(raw, words), doc)
            dropped += [t for t in raw if t not in got.focused_titles]
        self.assertIn("professional services consultant", dropped)
        self.assertEqual(ts.anchored(["react native developer", "professional services consultant",
                                      "software engineer", "mobile app developer"],
                                     {"react", "native", "mobile"}),
                         ["react native developer", "mobile app developer"])

    def test_generic_words_are_never_anchors(self):
        words = ts.anchors((ts.SearchTitle("backend engineer", "header"),),
                           [concept("go"), concept("software engineering")])
        self.assertEqual(words, {"backend", "go"})
        self.assertEqual(ts.anchored(["software engineer", "senior developer"], words), [])

    def test_todays_guards_judge_focused_titles(self):
        """Production's canonical guard refuses a search-operator title that the
        unguarded corpus tier would propose — here and in the derivation alike."""
        for store, present in ((SEALED, True), (LIVE, False)):
            got = search(store, "quality-automation-plain")
            _text, derived, _intent = store["quality-automation-plain"]
            raw = ts.focused_candidates(got.corpus_known, derived, MARKET[0],
                                        derived["role_keywords"])
            self.assertEqual("software engineer -python developer" in raw, present)

    def test_guards_follow_the_derivations_records_never_the_environment(self):
        for doc in ("quality-automation-plain", "data-ml-plain", "platform-generic-plain"):
            plain = search(SEALED, doc)
            with mock.patch.dict(os.environ, LIVE_ENV, clear=True):
                self.assertEqual(search(SEALED, doc), plain, doc)


# ---------------------------------------------------------------------------
class Assembly(unittest.TestCase):

    def test_titles_lead_then_retrieval_normalised_deduplicated_and_capped(self):
        for doc in SEALED:
            got = search(SEALED, doc)
            if not got.sufficient:
                continue
            kws = got.role_keywords
            self.assertEqual(kws[:len(got.leading_titles)],
                             tuple(t.query for t in got.leading_titles), doc)
            self.assertEqual(len(kws), len(set(kws)), doc)
            self.assertTrue(all(ts.normalize_query(k) == k for k in kws), doc)
            self.assertLessEqual(len(kws), ts.MAX_ROLE_KEYWORDS, doc)
            self.assertTrue(kws, doc)
            focused = [k for k in kws if k in got.focused_titles]
            self.assertEqual(focused, [t for t in got.focused_titles if t in kws], doc)

    def test_every_keyword_is_the_tracks_own_unless_nothing_is(self):
        for doc, (_text, derived, intent) in SEALED.items():
            got = search(SEALED, doc)
            if not got.sufficient:
                continue
            words = ts.anchors(got.leading_titles, ts.positioning_concepts(intent)[0])
            own = ({t.query for t in got.leading_titles} | set(got.focused_titles)
                   | {ts.normalize_query(k) for k in ts.anchored(derived["role_keywords"], words)})
            if own:
                self.assertLessEqual(set(got.role_keywords), own, doc)
            else:
                floor = list(dict.fromkeys(map(ts.normalize_query, derived["role_keywords"])))
                self.assertEqual(got.role_keywords, tuple(floor[:ts.MIN_TOP_UP]), doc)

    def search_broad(self, legacy, concept_ids):
        """A track sufficient by its concepts alone, over NoVocabulary; checks
        that its derivation's list is read and never written."""
        derived = {"role_keywords": list(legacy)}
        got = ts.derive_track_search("", derived, intent_of(concept(c) for c in concept_ids),
                                     NoVocabulary())
        self.assertEqual(derived, {"role_keywords": list(legacy)})
        return got

    def search_titled(self, legacy, title="backend automation engineer"):
        """A track sufficient by one summary title and nothing else (broad)."""
        derived = {"role_keywords": list(legacy)}
        got = ts.derive_track_search("", derived, intent_of((), titles=(declared(title),)),
                                     MARKET[0])
        self.assertEqual(derived, {"role_keywords": list(legacy)})
        self.assertEqual((got.leading_titles, got.retrieval),
                         ((ts.SearchTitle(title, "summary"),), "broad"))
        return got

    def test_the_broad_tier_keeps_agreeing_titles_in_todays_order(self):
        got = self.search_broad(["Terraform Developer", "Data Scientist", "Kubernetes Engineer",
                                 "QA Engineer"], ["kubernetes", "terraform"])
        self.assertEqual((got.retrieval, got.role_keywords, got.fallback_used),
                         ("broad", ("terraform developer", "kubernetes engineer"), True))

    def test_a_role_word_alone_is_no_agreement(self):
        # "engineer" is in the title too; "software engineer" still says nothing
        # about backend automation.
        got = self.search_titled(["Software Engineer", "Senior Developer", "QA Engineer",
                                  "Automation Tester", "Backend Developer"])
        self.assertEqual(got.role_keywords, ("backend automation engineer", "automation tester",
                                             "backend developer"))

    def test_a_track_may_search_only_its_own_title(self):
        got = self.search_titled(["Software Engineer", "QA Engineer", "Data Scientist"])
        self.assertEqual((got.role_keywords, got.fallback_used),
                         (("backend automation engineer",), False))
        # DQ2b: the broad SDET tier and the focused ML tier each keep only the title.
        self.assertEqual(search(SEALED, "quality-sdet-plain").role_keywords,
                         ("test automation engineer",))
        self.assertEqual(search(SEALED, "data-ml-plain").role_keywords,
                         ("machine learning engineer",))
        self.assertEqual(search(LIVE, "quality-automation-plain").role_keywords,
                         ("backend automation engineer",))

    def test_a_thin_focused_tier_is_topped_up_only_from_agreeing_titles(self):
        for layout in targeted.LAYOUTS:
            got = search(SEALED, f"platform-backend-{layout}")
            legacy = SEALED[f"platform-backend-{layout}"][1]["role_keywords"]
            self.assertEqual((got.retrieval, got.focused_titles), ("focused", ()), layout)
            # "back end developer" agrees once spelled "backend"; the other
            # eight of today's titles (ai/ml, data scientist, mobile, …) do not.
            self.assertIn("back end developer", legacy)
            self.assertEqual((got.role_keywords, got.fallback_used),
                             (("backend engineer", "backend developer"), True), layout)

    def test_with_nothing_of_its_own_a_track_searches_todays_first_titles_normalised(self):
        got = self.search_broad(["Full-Stack Developer", "fullstack developer", "Software Engineer",
                                 "QA Engineer", "Data Scientist"], ["kubernetes", "terraform"])
        self.assertEqual((got.role_keywords, got.fallback_used),
                         (("full stack developer", "software engineer", "qa engineer"), True))
        for layout in targeted.LAYOUTS:
            got = search(SEALED, f"quality-reliability-{layout}")
            self.assertEqual((got.leading_titles, got.focused_titles), ((), ()), layout)
            self.assertEqual(got.role_keywords, ("qa engineer", "data scientist",
                                                 "mobile developer"), layout)

    def test_an_insufficient_track_is_never_normalised_filtered_or_capped(self):
        legacy = ["Full-Stack Developer", "full stack developer", "AI/ML Engineer",
                  "Back End Developer", "Kubernetes Engineer", "Data Scientist", "QA Engineer",
                  "Mobile Developer", "Web Developer", "Gen AI Engineer"]
        got = self.search_broad(legacy, ["kubernetes"])
        self.assertEqual((got.sufficient, got.role_keywords), (False, tuple(legacy)))

    def test_an_insufficient_track_searches_exactly_todays_list(self):
        for store, doc in ((SEALED, "platform-generic-plain"),
                           (SEALED, "data-grouped-control-plain"),
                           (LIVE, "platform-generic-plain")):
            got = search(store, doc)
            legacy = store[doc][1]["role_keywords"]
            self.assertEqual((got.sufficient, got.retrieval, got.leading_titles),
                             (False, "fallback", ()), doc)
            self.assertEqual(got.role_keywords, tuple(legacy), doc)
            self.assertTrue(all(a is b for a, b in zip(got.role_keywords, legacy)), doc)


# ---------------------------------------------------------------------------
class Purity(unittest.TestCase):

    def test_no_input_is_mutated(self):
        market = MARKET[0]
        vocab, rows, total = dict(market.vocab), list(market.rows), market.total
        for store in (SEALED, LIVE):
            for doc, (text, derived, intent) in store.items():
                before, legacy = copy.deepcopy(derived), list(derived["role_keywords"])
                shape = intent.as_dict()
                ts.derive_track_search(text, derived, intent, market)
                self.assertEqual(derived, before, doc)
                self.assertEqual(derived["role_keywords"], legacy, doc)
                self.assertEqual(intent.as_dict(), shape, doc)
        self.assertEqual((dict(market.vocab), list(market.rows), market.total),
                         (vocab, rows, total))

    def test_the_record_is_immutable_serialisable_and_holds_no_resume_text(self):
        for doc, (text, _derived, intent) in SEALED.items():
            got = search(SEALED, doc)
            with self.assertRaises(dataclasses.FrozenInstanceError):
                got.role_keywords = ()
            blob = json.dumps(got.as_dict(), sort_keys=True)
            self.assertEqual(json.loads(blob), got.as_dict())
            self.assertEqual(got.as_dict(), search(SEALED, doc).as_dict())
            # A headline that IS a declared title is stored by design (a
            # validated title phrase, as in DQ2b); no other long line may be.
            titles = {ts.normalize_query(p) for d in intent.declared_titles for p in d.parts}
            for line in text.splitlines():
                line = line.strip().lower()
                if len(line) >= 25 and ts.normalize_query(line) not in titles:
                    self.assertNotIn(line, blob, doc)


# ---------------------------------------------------------------------------
class SiblingIndependence(unittest.TestCase):

    def test_the_signature_has_room_for_one_resume_only(self):
        self.assertEqual(list(inspect.signature(ts.derive_track_search).parameters),
                         ["resume_text", "derived", "intent", "market"])

    def test_a_track_is_the_same_alone_or_beside_any_siblings(self):
        alone = search(SEALED, "platform-backend-plain")
        for sibling in ("platform-platform-plain", "platform-generic-plain",
                        "quality-reliability-plain"):
            search(SEALED, sibling)
            self.assertEqual(search(SEALED, "platform-backend-plain"), alone, sibling)

    def test_changing_another_resume_cannot_change_a_track(self):
        alone = search(SEALED, "platform-backend-plain")
        text, derived, intent = SEALED["platform-platform-plain"]
        changed = dict(copy.deepcopy(derived), role_keywords=["rust developer"])
        other = dataclasses.replace(intent, declared_titles=(declared("rust engineer"),))
        ts.derive_track_search(text.replace("Platform", "Rust"), changed, other, MARKET[0])
        self.assertEqual(search(SEALED, "platform-backend-plain"), alone)


if __name__ == "__main__":
    unittest.main()
