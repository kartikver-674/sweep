"""DQ2a: what THIS résumé is aiming at, recorded and nothing more.

DQ1 (MULTI_TRACK_DERIVATION_QUALITY_AUDIT.md) found that several targeted
résumés from one person derive nearly the same TrackContext, because the
derivation reads what the person has DONE (skills, employment) and never what
the résumé POSITIONS itself for. `track_intent` is that missing reading: a pure,
deterministic, sibling-independent projection of one résumé's header, summary
and verb-described projects over the evidence its derivation already recorded.

DQ2a is record-only. What these tests defend, most important first:

  * a work-only shared capability (Apex at the shared job) never becomes intent
  * contact lines, URLs and the candidate's name never become intent, and no
    résumé sentence is stored
  * no sibling, label, filename, environment variable or model reaches the
    extractor, and it never mutates the derivation it reads
  * a résumé that positions itself for nothing is "insufficient", never guessed
  * the DQ2c relevance contract: the generic floor acquires a row, it does not
    make every track relevant when some track's intent matched

Every fixture is synthetic and written here.
"""

import copy
import json
import os
import shutil
import sys
import tempfile
import unittest
from collections import Counter
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
AUTO_APPLY = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(AUTO_APPLY)
for path in (REPO_ROOT, AUTO_APPLY):
    if path not in sys.path:
        sys.path.insert(0, path)

import config                 # noqa: E402
import make_profile           # noqa: E402
import skill_evidence         # noqa: E402
import track_intent as ti     # noqa: E402

EMPTY = None


def setUpModule():
    global EMPTY
    EMPTY = tempfile.mkdtemp()      # an empty output/: the frozen market, as on Render


def tearDownModule():
    shutil.rmtree(EMPTY, ignore_errors=True)


def derive(text, skills, name=""):
    """The production evidence step (make_profile.reweight_from_evidence) over
    a hand-written skill list — so skill_importance is what _finish records."""
    data = {"candidate_name": name,
            "skill_weights": [{"term": s, "weight": 3} for s in skills]}
    return make_profile.reweight_from_evidence(
        data, text, output_dir=EMPTY, log=lambda *a, **k: None)


SHARED_WORK = """Professional Experience
Kestrel Works
Software Engineer January 2025 - Present
- Built REST integrations between a React Native app and Salesforce using Node.js.
- Wrote Apex triggers for the billing module.
"""

MOBILE = ("""Priya Raman
priya.raman@example.com | +91 98765 43210 | linkedin.com/in/priya-raman
Mobile Engineer — React Native
Summary
Mobile engineer shipping React Native applications with Expo and TypeScript.
""" + SHARED_WORK + """Projects
TrailMate | React Native, Expo, Cloudinary
- Built an offline-first React Native app with Expo push notifications.
Technical Skills
Mobile: React Native, Expo
Backend: Node.js, Apex
""")
MOBILE_SKILLS = ["react native", "expo", "typescript", "node.js", "salesforce",
                 "apex", "cloudinary"]

# The same facts in another order and layout: name then title on one line,
# skills before the summary, bullets as dots, the project before the work.
MOBILE_REORDERED = ("""Priya Raman, Mobile Engineer
+91 98765 43210 · priya.raman@example.com
Technical Skills
Mobile: React Native, Expo
Backend: Node.js, Apex
Profile
Mobile engineer shipping React Native applications with Expo and TypeScript.
Projects
TrailMate | React Native, Expo, Cloudinary
• Built an offline-first React Native app with Expo push notifications.
""" + SHARED_WORK.replace("\n- ", "\n• "))

AI = ("""Anika Rao
anika@example.org | github.com/anikarao
AI / LLM Engineer
Summary
Builds LLM agents and RAG pipelines in Python, with structured outputs served by Ollama.
""" + SHARED_WORK + """Projects
DocAgent | Python, LangChain
- Built a RAG agent in Python with Ollama and structured outputs.
Technical Skills
AI/ML: Python, RAG, LLM, Ollama
Web: React Native, Node.js
""")
AI_SKILLS = ["python", "rag", "llm", "ollama", "structured outputs", "langchain",
             "react native", "node.js", "salesforce", "apex"]

# Positions itself for nothing: a name, contacts, work and a skills list.
GENERIC = ("""Sam Okafor
sam.okafor@example.net | +44 20 7946 0958
""" + SHARED_WORK + """Technical Skills
React Native, Node.js, Apex, Salesforce
""")
GENERIC_SKILLS = ["react native", "node.js", "apex", "salesforce"]

# Every header value is a contact value, and the name is also a language.
CONTACT = ("""Julia Chen
julia.chen@example.com | +1 415 555 0100
github.com/juliachen/react-native-demo | https://juliachen.dev
""" + SHARED_WORK + """Technical Skills
Julia, React Native, Node.js
""")
CONTACT_SKILLS = ["julia", "react native", "node.js", "apex", "salesforce"]

BACKEND = ("""Omar Haddad
Backend Engineer
Summary
Backend engineer building Node.js and PostgreSQL services.
""" + SHARED_WORK + """Projects
Ledgerly | Node.js, PostgreSQL
- Built a double-entry ledger service in Node.js on PostgreSQL.
""")
BACKEND_SKILLS = ["node.js", "postgresql", "react native", "apex", "salesforce"]

WEB = ("""Lin Park
Frontend Engineer
Summary
Frontend engineer building React interfaces with Redux.
""" + SHARED_WORK)
WEB_SKILLS = ["react", "redux", "react native", "node.js", "apex", "salesforce"]


def intent(text, skills, name="", **kw):
    return ti.derive_track_intent(text, derive(text, skills, name), **kw)


class WorkOverlap(unittest.TestCase):
    """The distinction DQ1 is built on."""

    def test_work_only_capability_is_not_intent(self):
        got = intent(MOBILE, MOBILE_SKILLS, "Priya Raman")
        self.assertNotIn("apex", got.ids)
        self.assertNotIn("salesforce", got.ids)
        self.assertIn("apex", got.work_only)
        self.assertIn("salesforce", got.work_only)

    def test_positioned_work_concept_is_strong_intent(self):
        got = intent(MOBILE, MOBILE_SKILLS, "Priya Raman")
        rn = got.concept("react native")
        self.assertTrue(rn.work_overlap)
        self.assertIn("header", rn.sources)
        self.assertIn("summary", rn.sources)
        self.assertIn("project", rn.sources)

    def test_positioned_without_work_is_intent_without_overlap(self):
        expo = intent(MOBILE, MOBILE_SKILLS, "Priya Raman").concept("expo")
        self.assertFalse(expo.work_overlap)
        self.assertEqual(expo.sources, ("project", "summary"))

    def test_skills_list_and_stack_line_alone_are_not_positioning(self):
        got = intent(MOBILE, MOBILE_SKILLS, "Priya Raman")
        self.assertNotIn("node.js", got.ids)          # work + skills list only
        self.assertNotIn("cloudinary", got.ids)       # project stack line only
        self.assertIn("cloudinary", got.other_claimed)
        self.assertIn("node.js", got.work_only)


class Positioning(unittest.TestCase):

    def test_mobile_positioning(self):
        got = intent(MOBILE, MOBILE_SKILLS, "Priya Raman")
        self.assertTrue(got.sufficient)
        self.assertEqual(got.ids, frozenset({"react native", "expo", "typescript"}))
        self.assertEqual(got.titles, frozenset({"mobile engineer"}))

    def test_ai_positioning_survives_shared_full_stack_work(self):
        got = intent(AI, AI_SKILLS, "Anika Rao")
        self.assertTrue(got.sufficient)
        self.assertTrue({"python", "rag", "llm", "ollama",
                         "structured outputs"} <= got.ids, got.ids)
        for shared in ("react native", "node.js", "apex", "salesforce"):
            self.assertNotIn(shared, got.ids)
        self.assertIn("react native", got.work_only)

    def test_generic_resume_is_insufficient_and_invents_nothing(self):
        got = intent(GENERIC, GENERIC_SKILLS, "Sam Okafor")
        self.assertFalse(got.sufficient)
        self.assertEqual(got.concepts, ())
        self.assertEqual(got.declared_titles, ())
        self.assertIn("no header, summary or project positioning", got.reason)

    def test_no_evidence_record_is_insufficient(self):
        derived = {"candidate_name": "", "skill_weights": [
            {"term": "react native", "weight": 3}]}
        got = ti.derive_track_intent(MOBILE, derived)
        self.assertFalse(got.sufficient)
        self.assertEqual(got.concepts, ())
        self.assertIn("no evidence record", got.reason)

    def test_an_empty_evidence_record_is_no_record(self):
        got = ti.derive_track_intent(MOBILE, {"candidate_name": "",
                                              "skill_importance": []})
        self.assertFalse(got.sufficient)
        self.assertEqual(got.declared_titles, ())
        self.assertIn("no evidence record", got.reason)


class ContactAndPrivacy(unittest.TestCase):

    def test_contact_header_yields_no_intent(self):
        got = intent(CONTACT, CONTACT_SKILLS, "Julia Chen")
        self.assertNotIn("julia", got.ids)            # the name, not the language
        self.assertNotIn("react native", got.ids)     # inside a URL
        self.assertEqual(got.declared_titles, ())
        self.assertFalse(got.sufficient)

    def test_nothing_personal_or_sentence_shaped_is_stored(self):
        for text, skills, name in ((CONTACT, CONTACT_SKILLS, "Julia Chen"),
                                   (MOBILE, MOBILE_SKILLS, "Priya Raman"),
                                   (AI, AI_SKILLS, "Anika Rao")):
            record = intent(text, skills, name).as_dict()
            json.dumps(record)                           # serialisable as data
            blob = "\n".join(strings(record)).lower()
            for secret in ("julia chen", "chen", "priya", "raman", "anika",
                           "example", "415", "555", "98765", "github",
                           "linkedin", "https", "kestrel", "trailmate",
                           "docagent"):
                self.assertNotIn(secret, blob, (name, secret))
            # No sentence of the résumé travels: nothing of 25+ characters.
            for line in text.lower().splitlines():
                if len(line.strip()) >= 25:
                    self.assertNotIn(line.strip(), blob)

    def test_name_is_masked_even_when_it_shares_a_title_line(self):
        got = intent(MOBILE_REORDERED, MOBILE_SKILLS, "Priya Raman")
        self.assertEqual(got.titles, frozenset({"mobile engineer"}))

    def test_a_url_outside_the_header_is_still_masked(self):
        text = ("Priya Raman\nMobile Engineer\nSummary\nMobile engineer. Demo at "
                "github.com/priyar/flutter-shop for reviewers.\n" + SHARED_WORK)
        got = intent(text, ["flutter", "react native"], "Priya Raman")
        self.assertNotIn("flutter", got.ids)

    def test_the_name_is_masked_in_the_header_only(self):
        # "Julia" the language, in her own summary, is still her intent.
        text = (CONTACT.replace(
            "Professional Experience",
            "Summary\nScientific programmer writing simulations in Julia.\n"
            "Professional Experience"))
        got = intent(text, CONTACT_SKILLS, "Julia Chen")
        self.assertIn("julia", got.ids)
        self.assertEqual(got.concept("julia").sources, ("summary",))


def strings(obj, key=None):
    """Every string value in a record — not offsets, not digests."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from strings(v, k)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from strings(v, key)
    elif isinstance(obj, str) and key != "sha":
        yield obj


HEADER_SKILLS = ["react native", "react", "python", "node.js"]


def header_case(line, name="Jane Doe"):
    """One header line above the shared work, as a whole résumé."""
    text = f"{line}\n" + SHARED_WORK + "Technical Skills\nReact Native, Python\n"
    return text, intent(text, HEADER_SKILLS, name)


class HeaderContactSpans(unittest.TestCase):
    """Contact values and the name are masked as SPANS, so a title sharing
    their line survives while nothing sensitive is read or stored."""

    TITLED = (
        ("Jane Doe | React Native Engineer | jane@example.com | +91 99999 99999",
         "react native engineer"),
        ("Jane Doe | Mobile Engineer | jane@example.com", "mobile engineer"),
        ("+91 99999 99999 • Machine Learning Engineer", "machine learning engineer"),
        ("linkedin.com/in/jane | Backend Engineer", "backend engineer"),
        ("Mobile Engineer | jane@example.com | +91 99999 99999", "mobile engineer"),
        ("Jane Doe — AI / LLM Engineer — jane@example.com", "ai / llm engineer"),
        # No separator: the masked name must STOP the title, not join it.
        ("Jane Doe Mobile Engineer", "mobile engineer"),
    )

    CONTACT_ONLY = (
        "jane@example.com",
        "+91 99999 99999",
        "linkedin.com/in/jane",
        "Jane Doe | jane@example.com",
        "github.com/reactwizard | linkedin.com/in/python-engineer",
        "Jane Doe | python.dev@example.com | github.com/jane/react-native-lab",
        # A job-title word that is part of an address heads no title.
        "Jane Doe | Reach Engineer@example.com",
    )

    SECRETS = ("jane", "doe", "example", "99999", "linkedin", "github",
               "reactwizard", "python-engineer", "python.dev", "react-native-lab")

    def test_a_title_sharing_a_line_with_contact_values_survives(self):
        for line, title in self.TITLED:
            with self.subTest(line=line):
                _text, got = header_case(line)
                self.assertEqual(got.titles, frozenset({title}))
                self.assertEqual(got.declared_titles[0].source, "header")

    def test_contact_only_lines_contribute_nothing(self):
        for line in self.CONTACT_ONLY:
            with self.subTest(line=line):
                _text, got = header_case(line)
                self.assertEqual(got.declared_titles, ())
                header = {c.id for c in got.concepts if "header" in c.sources}
                self.assertEqual(header, set())
                for technical in ("react", "python", "react native"):
                    self.assertNotIn(technical, got.ids)

    def test_a_concept_beside_contact_values_still_counts(self):
        _text, got = header_case("Jane Doe | React Native Engineer | jane@example.com")
        self.assertIn("header", got.concept("react native").sources)

    def test_the_phone_span_itself_is_masked(self):
        # Phone digits can never form a concept or a title, so no OUTPUT shows
        # this mask; the privacy invariant is pinned at the mask itself.
        line = "Jane Doe | Mobile Engineer | +91 99999 99999"
        text = f"{line}\n" + SHARED_WORK
        header = ti._header_span(skill_evidence.sections(text))
        masks = ti._masks(text, header, "Jane Doe")
        phone = (line.index("+91"), len(line))
        self.assertIn(phone, masks)
        title = (line.index("Mobile"), line.index(" |", line.index("Mobile")))
        self.assertFalse(ti._masked(title, masks))

    def test_offsets_point_into_the_original_text(self):
        line = "Jane Doe | React Native Engineer | jane@example.com | +91 99999 99999"
        text, got = header_case(line)
        title, = got.declared_titles
        self.assertEqual(text[slice(*title.span)], "React Native Engineer")
        self.assertEqual(title.span[0], line.index("React"))
        ref = next(r for r in got.concept("react native").refs if r.source == "header")
        self.assertEqual(text[slice(*ref.span)].lower(), "react native")
        self.assertEqual(ref.span[0], line.index("React"))

    def test_nothing_sensitive_is_serialised(self):
        for line in [line for line, _t in self.TITLED] + list(self.CONTACT_ONLY):
            with self.subTest(line=line):
                _text, got = header_case(line)
                record = got.as_dict()
                json.dumps(record)
                blob = "\n".join(strings(record)).lower()
                for secret in self.SECRETS + (line.lower(),):
                    self.assertNotIn(secret, blob)


class DeclaredTitles(unittest.TestCase):

    def titles(self, header, summary="", skills=("react native",)):
        text = (f"Kai Moreno\n{header}\n"
                + (f"Summary\n{summary}\n" if summary else "") + SHARED_WORK)
        return intent(text, list(skills), "Kai Moreno").titles

    def test_slash_alternatives_keep_each_headed_part(self):
        got = intent(AI, AI_SKILLS, "Anika Rao")
        title, = got.declared_titles
        self.assertEqual(title.title, "ai / llm engineer")
        self.assertEqual(title.parts, ("llm engineer",))
        self.assertEqual(title.source, "header")

    def test_tight_slash_is_one_title(self):
        self.assertEqual(self.titles("AI/ML Engineer"), frozenset({"ai/ml engineer"}))

    def test_seniority_is_dropped_and_level_alone_is_not_a_title(self):
        self.assertEqual(self.titles("Senior React Native Engineer"),
                         frozenset({"react native engineer"}))
        self.assertEqual(self.titles("Senior Engineer"), frozenset())

    def test_generic_prose_is_not_a_title(self):
        self.assertEqual(self.titles("Curriculum Vitae",
                                     "Motivated engineer and a passionate "
                                     "problem solver who loves teams."),
                         frozenset())

    def test_lowercase_unknown_qualifier_is_not_a_title(self):
        # Precision over recall: "strong developer" names no job.
        self.assertEqual(self.titles("Curriculum Vitae",
                                     "A strong developer and a fast learner."),
                         frozenset())

    def test_sentence_case_title_in_summary(self):
        self.assertEqual(self.titles("Curriculum Vitae",
                                     "Full-stack engineer with two years of "
                                     "React Native work."),
                         frozenset({"full-stack engineer"}))

    def test_canonical_is_recorded_beside_the_declaration(self):
        titles = Counter({"llm engineer ops": 1, "react native developer": 9})
        got = intent(AI, AI_SKILLS, "Anika Rao", titles=titles, seniority=())
        title, = got.declared_titles
        self.assertEqual(title.canonical, (("llm engineer", "llm engineer ops"),))

    def test_declaration_survives_with_no_corpus_title(self):
        got = intent(MOBILE, MOBILE_SKILLS, "Priya Raman",
                     titles=Counter({"data engineer": 50}), seniority=())
        title, = got.declared_titles
        self.assertEqual(title.title, "mobile engineer")
        self.assertEqual(title.canonical, (("mobile engineer", None),))


class SummarySelfIdentification(unittest.TestCase):
    """"I am a/an …" / "I'm a/an …" in a summary: the one place a lowercase,
    unknown word may be part of a declared title, and only when the title
    fills the gap between the article and its head. Recording is all this
    does; whether a title may lead search is TrackSearchIntent's call."""

    def declared(self, summary, header="Curriculum Vitae"):
        text = f"Kai Moreno\n{header}\nSummary\n{summary}\n" + SHARED_WORK
        return text, intent(text, ["react native"], "Kai Moreno").declared_titles

    def titles(self, summary, header="Curriculum Vitae"):
        return frozenset(t.title for t in self.declared(summary, header)[1])

    def test_a_lowercase_self_identified_title_is_recorded_with_its_span(self):
        text, got = self.declared("I am a backend automation engineer.")
        title, = got
        self.assertEqual((title.title, title.source, title.parts),
                         ("backend automation engineer", "summary",
                          ("backend automation engineer",)))
        self.assertEqual(text[slice(*title.span)], "backend automation engineer")
        self.assertEqual(title.span[0], text.index("backend"))

    def test_case_inside_the_slot_is_not_semantic(self):
        lower = self.declared("i am a backend automation engineer.")[1]
        self.assertEqual(lower, self.declared("I am a backend automation engineer.")[1])
        self.assertEqual(lower, self.declared("I am a Backend Automation Engineer.")[1])

    def test_each_title_reads_from_its_own_self_identification(self):
        self.assertEqual(self.titles("I am a backend engineer. I am a data engineer."),
                         frozenset({"backend engineer", "data engineer"}))

    def test_outside_the_slot_todays_rule_holds(self):
        # Sentence-case prose and the header still need capitals or known words.
        self.assertEqual(self.titles("Backend automation engineer building services."),
                         frozenset())
        self.assertEqual(self.titles("Builds services.",
                                     header="I am a backend automation engineer"),
                         frozenset())

    def test_the_article_is_required(self):
        for summary, title in (("I am a backend engineer.", "backend engineer"),
                               ("I am an analytics engineer.", "analytics engineer"),
                               ("I'm a backend engineer.", "backend engineer"),
                               ("I’m an analytics engineer.", "analytics engineer")):
            self.assertEqual(self.titles(summary), frozenset({title}), summary)
        self.assertIsNone(ti._SELF_ID.search("I am backend engineer."))
        self.assertEqual(self.titles("I am backend engineer."), frozenset())

    def test_the_title_ends_at_its_head_and_starts_after_the_article(self):
        for summary, written in (
                ("I am a backend automation engineer with 4 years experience.",
                 "backend automation engineer"),
                ("I'm a React Native developer who builds consumer apps.",
                 "React Native developer"),
                ("I am a backend engineer at ExampleCo.", "backend engineer"),
                ("I am a backend automation engineer: I build Python services.",
                 "backend automation engineer")):
            text, got = self.declared(summary)
            title, = got
            self.assertEqual(text[slice(*title.span)], written, summary)
            self.assertEqual(title.title, written.lower(), summary)

    def test_a_bare_head_is_no_title_and_a_generic_one_is_recorded(self):
        self.assertEqual(self.titles("I am an engineer."), frozenset())
        # Recorded as declared; TrackSearchIntent later refuses it as a wildcard.
        self.assertEqual(self.titles("I am a software engineer."),
                         frozenset({"software engineer"}))

    def test_level_words_are_dropped_as_everywhere(self):
        self.assertEqual(self.titles("I am a senior backend engineer."),
                         frozenset({"backend engineer"}))

    def test_prose_after_i_am_is_not_a_title(self):
        for summary in ("I am experienced in backend systems.",
                        "I am skilled in Python.",
                        "I am currently learning React.",
                        "I am seeking backend engineer roles.",
                        "I am targeting data engineer roles.",
                        "I am hiring backend engineers.",
                        "I am on a backend engineering team.",
                        "I am part of the platform engineering team.",
                        # matched, but the title would not fill the gap
                        "I am a big fan of backend engineer tooling."):
            self.assertEqual(self.titles(summary), frozenset(), summary)

    def test_other_grammar_is_not_a_self_identification(self):
        for summary in ("I was a Backend Engineer.",
                        "I worked as a backend engineer.",
                        "I work at ExampleCo as a backend engineer.",
                        "My role is backend engineer.",
                        "As a backend engineer, I build services."):
            self.assertIsNone(ti._SELF_ID.search(summary), summary)
        # Capitalised, so today's path reads it, exactly as before.
        self.assertEqual(self.titles("I was a Backend Engineer."),
                         frozenset({"backend engineer"}))
        for summary in ("I worked as a backend engineer.",
                        "I work at ExampleCo as a backend engineer.",
                        "My role is backend engineer.",
                        "As a backend engineer, I build services."):
            self.assertEqual(self.titles(summary), frozenset(), summary)

    def test_known_limitation_praise_outside_stop_joins_the_title(self):
        """KNOWN LIMITATION, not a desired reading. "great" is not one of
        _STOP's self-praise words, so inside a self-identification it reads
        as a qualifier — the capitalised path leaks the same way ("Great
        Software Developer"). Kept rather than growing _STOP from synthetic
        probes; DQ6 measures it on real résumés."""
        self.assertEqual(self.titles("I am a great software developer."),
                         frozenset({"great software developer"}))

    def test_the_title_is_the_same_alone_and_among_siblings(self):
        text = ("Kai Moreno\nSoftware Engineer\nSummary\nI am a backend automation "
                "engineer: I build Python services.\n" + SHARED_WORK)
        own = (text, derive(text, ["python", "react native"], "Kai Moreno"))
        mobile = (MOBILE, derive(MOBILE, MOBILE_SKILLS, "Priya Raman"))
        ai = (AI, derive(AI, AI_SKILLS, "Anika Rao"))
        alone = ti.derive_track_intent(*own)
        self.assertIn("backend automation engineer", alone.titles)
        self.assertEqual(ti.for_sweep([own, mobile])[0], alone)
        self.assertEqual(ti.for_sweep([mobile, own])[1], alone)
        self.assertEqual(ti.for_sweep([ai, mobile, own])[2], alone)


class RegisteredAndLiteral(unittest.TestCase):

    def test_registry_status_is_recorded(self):
        got = intent(AI, AI_SKILLS, "Anika Rao")
        self.assertTrue(got.concept("python").registered)
        for literal in ("rag", "llm", "ollama", "structured outputs"):
            self.assertFalse(got.concept(literal).registered, literal)


class SkillsEmphasis(unittest.TestCase):

    def test_groups_labels_and_order_are_measured(self):
        got = intent(MOBILE, MOBILE_SKILLS, "Priya Raman")
        self.assertEqual(got.skills_groups, ("mobile", "backend"))
        self.assertEqual(got.skills_order, (("react native", 0, 0), ("expo", 0, 1),
                                            ("node.js", 1, 0), ("apex", 1, 1)))

    def test_emphasis_never_makes_intent(self):
        # A skills group led by a concept nothing else positions.
        got = intent(GENERIC, GENERIC_SKILLS, "Sam Okafor")
        self.assertEqual(got.skills_order[0][0], "react native")
        self.assertNotIn("react native", got.ids)


class GroupLabelContract(unittest.TestCase):
    """skill_evidence reads a skills row's label as structure (GROUP_LABEL:
    kept, status intact, no evidence) by the label grammar skills groups use
    here: the text before the physical row's first colon, [a-z0-9 /&+.-]{1,40},
    at most four words. One difference, pinned rather than hidden:
    skill_evidence strips one leading bullet first and track_intent does not."""

    def read(self, rows):
        """(skills_groups, {concept: {shape, ...}}) over one skills section."""
        text = "Dana Reed\nTechnical Skills\n" + rows + "\n"
        derived = derive(text, ["ci/cd", "github actions", "python"])
        shapes = {r["id"]: {o["shape"] for o in r["occurrences"]}
                  for r in derived["skill_importance"]}
        return ti.derive_track_intent(text, derived).skills_groups, shapes

    def test_one_label_grammar(self):
        self.assertEqual(ti._LABEL.pattern, "^" + skill_evidence._GROUP_LABEL.pattern + "$")

    def test_both_read_the_same_rows_as_labelled(self):
        label = {skill_evidence.GROUP_LABEL}
        for row, group in (("CI/CD: GitHub Actions, Python", "ci/cd"),
                           ("CI/CD:", "ci/cd"),
                           ("Build & CI/CD: GitHub Actions", "build & ci/cd"),
                           ("CI/CD and release tooling today: GitHub Actions", None),
                           ("CI/CD (daily): GitHub Actions", None),
                           ("Python, CI/CD: GitHub Actions", None),
                           ("CI/CD, GitHub Actions, Python", None)):
            groups, shapes = self.read(row)
            self.assertEqual(groups[0], group, row)
            self.assertEqual(shapes["ci/cd"] == label, group is not None, (row, shapes))
        # Physical rows on both sides: a wrapped value row has no label.
        groups, shapes = self.read("CI/CD: Python,\nGitHub Actions")
        self.assertEqual(groups, ("ci/cd", None))
        self.assertEqual((shapes["ci/cd"], shapes["github actions"]),
                         (label, {skill_evidence.CLAIM_ONLY}))

    def test_known_difference_a_leading_bullet(self):
        """skill_evidence strips one bullet, so each row's CI/CD is a label
        there; track_intent reads the row as written, so "•" and "*" rows
        have no group label and a "-" row's label keeps its dash."""
        for row, group in (("• CI/CD: GitHub Actions", None),
                           ("* CI/CD: GitHub Actions", None),
                           ("- CI/CD: GitHub Actions", "- ci/cd")):
            groups, shapes = self.read(row)
            self.assertEqual(shapes["ci/cd"], {skill_evidence.GROUP_LABEL}, row)
            self.assertEqual(groups[0], group, row)


class Purity(unittest.TestCase):

    def test_derived_is_not_mutated(self):
        derived = derive(MOBILE, MOBILE_SKILLS, "Priya Raman")
        before = copy.deepcopy(derived)
        ti.derive_track_intent(MOBILE, derived)
        self.assertEqual(derived, before)

    def test_deterministic(self):
        derived = derive(AI, AI_SKILLS, "Anika Rao")
        self.assertEqual(ti.derive_track_intent(AI, derived),
                         ti.derive_track_intent(AI, derived))

    def test_environment_cannot_change_the_answer(self):
        derived = derive(AI, AI_SKILLS, "Anika Rao")
        plain = ti.derive_track_intent(AI, derived)
        with mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin",
                                          "SWEEP_SEMANTIC_SCOPE": "1",
                                          "SWEEP_PROFILE_ENGINE_VERSION": "v1",
                                          "SWEEP_CANDIDATE_TITLE_GATE": "1",
                                          "SWEEP_ROLE_EVIDENCE": "1"}, clear=True):
            self.assertEqual(ti.derive_track_intent(AI, derived), plain)

    def test_layouts_of_the_same_facts_agree(self):
        a = intent(MOBILE, MOBILE_SKILLS, "Priya Raman")
        b = intent(MOBILE_REORDERED, MOBILE_SKILLS, "Priya Raman")
        self.assertEqual(a.ids, b.ids)
        self.assertEqual(a.titles, b.titles)
        self.assertEqual(a.work_only, b.work_only)


class SiblingIndependence(unittest.TestCase):

    def test_a_is_the_same_alone_and_among_siblings(self):
        items = [(MOBILE, derive(MOBILE, MOBILE_SKILLS, "Priya Raman")),
                 (AI, derive(AI, AI_SKILLS, "Anika Rao")),
                 (BACKEND, derive(BACKEND, BACKEND_SKILLS, "Omar Haddad"))]
        together = ti.for_sweep(items)
        self.assertEqual(together[0], ti.derive_track_intent(*items[0]))
        self.assertEqual(together[1], ti.derive_track_intent(*items[1]))
        self.assertEqual(ti.for_sweep(items[:2])[0], together[0])

    def test_a_single_resume_never_gets_an_intent(self):
        one = [(MOBILE, derive(MOBILE, MOBILE_SKILLS, "Priya Raman"))]
        with self.assertRaises(ValueError):
            ti.for_sweep(one)
        with self.assertRaises(ValueError):
            ti.for_sweep(one * 4)


class Diagnostics(unittest.TestCase):

    def setUp(self):
        self.intents = {
            "mobile": intent(MOBILE, MOBILE_SKILLS, "Priya Raman"),
            "ai": intent(AI, AI_SKILLS, "Anika Rao"),
            "backend": intent(BACKEND, BACKEND_SKILLS, "Omar Haddad"),
        }

    def test_compare_measures_and_transforms_nothing(self):
        before = dict(self.intents)
        report = ti.compare(self.intents)
        self.assertEqual(self.intents, before)
        self.assertEqual(report["pairs"]["mobile|ai"]["concepts"], 0.0)
        self.assertEqual(report["unique"]["mobile"],
                         ["expo", "react native", "typescript"])
        self.assertEqual(report["sufficient"],
                         {"mobile": True, "ai": True, "backend": True})
        self.assertEqual(report["provenance"]["mobile"]["work_overlap"], 1)

    def test_two_empty_intents_are_undefined_not_identical(self):
        empty = intent(GENERIC, GENERIC_SKILLS, "Sam Okafor")
        report = ti.compare({"a": empty, "b": empty})
        self.assertEqual(report["pairs"]["a|b"], {"concepts": None, "titles": None})


class GenericFloorContract(unittest.TestCase):
    """DQ2c's relevance contract, recorded here and implemented nowhere yet:
    the floor preserves ACQUISITION; it must not erase track identity."""

    def setUp(self):
        self.intents = {
            "mobile": intent(MOBILE, MOBILE_SKILLS, "Priya Raman"),
            "backend": intent(BACKEND, BACKEND_SKILLS, "Omar Haddad"),
        }
        self.floor = config.ATS_TITLE_HINTS

    def test_intent_match_wins_over_the_floor(self):
        got = ti.relevance_contract("React Native Engineer", self.intents, self.floor)
        self.assertTrue(got["floor_admits"])            # "react native" is in it
        self.assertTrue(got["acquire"])
        self.assertEqual(got["intent_matches"], ["mobile"])
        self.assertEqual(got["relevant"], ["mobile"])   # NOT mobile + backend
        self.assertFalse(got["fallback"])

    def test_floor_only_falls_back_to_every_track(self):
        got = ti.relevance_contract("Software Engineer", self.intents, self.floor)
        self.assertEqual(got["intent_matches"], [])
        self.assertEqual(got["relevant"], ["mobile", "backend"])
        self.assertTrue(got["fallback"])

    def test_intent_alone_acquires_outside_the_floor(self):
        got = ti.relevance_contract("PostgreSQL Specialist", self.intents, self.floor)
        self.assertFalse(got["floor_admits"])
        self.assertTrue(got["acquire"])
        self.assertEqual(got["relevant"], ["backend"])

    def test_nothing_matches(self):
        got = ti.relevance_contract("Pastry Chef", self.intents, self.floor)
        self.assertEqual((got["acquire"], got["relevant"]), (False, []))

    def test_react_intent_does_not_claim_react_native(self):
        web = intent(WEB, WEB_SKILLS, "Lin Park")
        self.assertIn("react", web.ids)
        got = ti.relevance_contract("React Native Engineer",
                                    {"mobile": self.intents["mobile"], "web": web},
                                    self.floor)
        self.assertEqual(got["relevant"], ["mobile"])
        self.assertTrue(ti.admits(web, "React Developer"))


if __name__ == "__main__":
    unittest.main()
