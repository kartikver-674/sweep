"""DQ2b fixture integrity. Run: python -m unittest bench.test_targeted.

The targeted families (bench/targeted.py), their test-only ground truth
(bench/targeted_manifest.py) and their committed local-model captures
(bench/results/targeted-qwen3_8b.json). No model call, no network: every
derivation here replays a capture through today's production pipeline.

These pin what the FIXTURES are — shared facts, different positioning, no
personal data, replayable — and what today's TrackIntent reads from them.
They deliberately do NOT require DQ2c's acceptance thresholds: the suite
exists to show today's failures.
"""
import ast
import json
import os
import pwd
import re
import socket
import tempfile
import unittest
from unittest import mock

from bench import targeted
from bench import targeted_manifest as M

REPO = targeted.REPO
ENV = {"PATH": "/usr/bin:/bin", "HOME": tempfile.gettempdir(), "LANG": "en_US.UTF-8",
       "PYTHONDONTWRITEBYTECODE": "1", "SWEEP_PROFILE_ENGINE_VERSION": "v2"}
# This machine's account name: a committed fixture must not carry it.
MACHINE_USER = pwd.getpwuid(os.getuid()).pw_name.lower()
FICTIONAL_PHONE = re.compile(r"^(\+44 7700 900\d{3}|\+1 \d{3} 555 01\d{2})$")
DOCS = {}          # doc -> (text, derived, gate), replayed once for the module
INTENTS = {}       # doc -> TrackIntent
_patches = []


def setUpModule():
    """Replay every document once: sealed environment (v2, no other SWEEP_*
    flag, no .env value), sockets refused, "Present" pinned."""
    env = mock.patch.dict(os.environ, ENV, clear=True)
    env.start()
    _patches.append(env)
    refuse = mock.patch.object(socket.socket, "connect",
                               side_effect=RuntimeError("DQ2b tests opened a socket"))
    refuse.start()
    _patches.append(refuse)
    import track_intent
    captures = targeted.load_captures()
    with tempfile.TemporaryDirectory() as empty:
        for doc, _vid, _layout in targeted.documents():
            DOCS[doc] = targeted.derive(doc, captures, empty)
            INTENTS[doc] = track_intent.derive_track_intent(DOCS[doc][0], DOCS[doc][1])


def tearDownModule():
    while _patches:
        _patches.pop().stop()


def strings(value):
    """Every string inside a JSON-shaped value, recursively."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from strings(k)
            yield from strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from strings(v)


class FamilyDesign(unittest.TestCase):
    def test_every_family_has_three_distinct_targets(self):
        self.assertEqual(set(M.SIBLINGS), set(targeted.FAMILIES))
        for family, sibs in M.SIBLINGS.items():
            targets = [M.VARIANTS[v]["target"] for v in sibs]
            self.assertEqual(len(set(targets)), 3, family)
            self.assertTrue(all(targets), family)

    def test_manifest_and_fixtures_name_the_same_variants(self):
        self.assertEqual(set(M.VARIANTS), set(targeted.variant_ids()))
        for vid, spec in M.VARIANTS.items():
            self.assertEqual((spec["family"], spec["variant"]), targeted.split(vid))

    def test_the_suite_has_every_difficult_case(self):
        cases = {v["case"] for v in M.VARIANTS.values()}
        self.assertEqual(cases, {"strong_headline", "generic_headline", "misheaded",
                                 "control", "control_grouped"})
        grouped = [v for v in targeted.variant_ids()
                   if "groups" in targeted.person(v)["skills"]]
        self.assertGreaterEqual(len(grouped), 6)
        twins = [v for v, s in M.VARIANTS.items() if s["twin_of"]]
        self.assertEqual(len(twins), 2)
        self.assertIn("generic_headline", {M.VARIANTS[t]["case"] for t in twins})
        # A headline sharing the contact line; one with no headline at all.
        self.assertTrue(targeted.person("data-dataeng")["headline_inline"])
        self.assertIsNone(targeted.person("data-grouped-control")["headline"])

    def test_siblings_share_every_fact(self):
        for family, fam in targeted.FAMILIES.items():
            ids = [v for v in targeted.variant_ids() if targeted.split(v)[0] == family]
            first = targeted.facts(ids[0])
            for vid in ids:
                self.assertEqual(targeted.facts(vid), first, vid)
                p = targeted.person(vid)
                self.assertEqual([(j["company"], j["title"], j["start"], j["end"])
                                  for j in p["employment"]],
                                 [(j["company"], j["title"], j["start"], j["end"])
                                  for j in fam["jobs"]], vid)
                self.assertEqual(p["education"], fam["education"], vid)
                # The SAME skills in every variant: only order and grouping move.
                self.assertEqual(sorted(targeted.skill_order(p["skills"])),
                                 sorted(fam["skills"]), vid)

    def test_variants_choose_among_true_bullets_and_projects(self):
        for vid in targeted.variant_ids():
            family, name = targeted.split(vid)
            fam, spec = targeted.FAMILIES[family], targeted.variant(family, name)
            for job, chosen in zip(fam["jobs"], spec["bullets"]):
                self.assertTrue(chosen, vid)
                self.assertLessEqual(set(chosen), set(job["bullets"]), vid)
            self.assertLessEqual({p for p, _b in spec["projects"]}, set(fam["projects"]))

    def test_flat_twins_differ_only_in_their_skills_section(self):
        for vid, spec in M.VARIANTS.items():
            if not spec["twin_of"]:
                continue
            twin, orig = targeted.person(vid), targeted.person(spec["twin_of"])
            self.assertEqual(dict(twin, skills=None), dict(orig, skills=None))
            self.assertEqual(twin["skills"], {"flat": targeted.skill_order(orig["skills"])})
            self.assertIn("groups", orig["skills"])
        self.assertEqual(targeted.person("data-grouped-control")["skills"],
                         targeted.person("data-ml")["skills"])

    def test_the_manifest_reaches_no_derivation(self):
        """Ground truth is evaluation only: neither the fixture module nor any
        production module imports it (or the fixtures)."""
        with open(os.path.join(REPO, "bench", "targeted.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        imported = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import,
                                                                     ast.ImportFrom))
                    for a in n.names} | {n.module for n in ast.walk(tree)
                                         if isinstance(n, ast.ImportFrom) and n.module}
        self.assertFalse({"targeted_manifest", "bench.targeted_manifest",
                          "targeted_eval", "track_intent"} & imported, imported)
        offenders = []
        for root, dirs, files in os.walk(REPO):
            dirs[:] = [d for d in dirs if d not in (".git", ".venv", "node_modules",
                                                    "output", "bench", "__pycache__",
                                                    "graphify-out")]
            for name in files:
                if name.endswith(".py"):
                    path = os.path.join(root, name)
                    with open(path, encoding="utf-8", errors="replace") as fh:
                        text = fh.read()
                    if re.search(r"targeted_manifest|bench\.targeted|"
                                 r"from bench import[^\n]*\btargeted", text):
                        offenders.append(os.path.relpath(path, REPO))
        self.assertEqual(offenders, [])
        with open(os.path.join(REPO, "bench", "targeted_manifest.py"),
                  encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        self.assertEqual({a.name for n in ast.walk(tree)
                          if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names},
                         {"re"})

    def test_the_sweep_preferences_are_the_apps_india_default(self):
        from sweep.tests.test_one_track_goldens import prefs_for
        self.assertEqual(targeted.PREFS, prefs_for("india"))


class NoPersonalData(unittest.TestCase):
    def test_contacts_are_reserved_fiction(self):
        for family, fam in targeted.FAMILIES.items():
            self.assertTrue(fam["email"].endswith("@example.com"), family)
            self.assertRegex(fam["phone"], FICTIONAL_PHONE)

    def test_documents_carry_only_their_own_synthetic_contact_and_no_path(self):
        for doc, (text, _derived, _gate) in DOCS.items():
            fam = targeted.FAMILIES[targeted.split(doc)[0]]
            self.assertEqual(re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text),
                             [fam["email"]], doc)
            self.assertNotIn("file://", text, doc)
            self.assertNotIn("/Users/", text, doc)
            self.assertNotIn(MACHINE_USER, text.lower(), doc)

    def test_every_sentence_survives_extraction(self):
        """A layout that clips text changes the facts; render.py's twocol grid
        does (hana-twocol), and targeted.FIT is why these do not."""
        def norm(s):
            return re.sub(r"-\s+", "-", re.sub(r"\s+", " ", s))
        for doc, vid, _layout in targeted.documents():
            text, p = norm(DOCS[doc][0]), targeted.person(vid)
            sentences = ([b for j in p["employment"] for b in j["bullets"]]
                         + [x["blurb"] for x in p["projects"]]
                         + ([p["summary"]] if p["summary"] else []))
            for sentence in sentences:
                self.assertIn(norm(sentence), text, doc)

    def test_captures_hold_no_machine_detail(self):
        with open(targeted.CAPTURES, encoding="utf-8") as fh:
            raw = fh.read()
        for needle in ("/Users/", "file://", MACHINE_USER, "11434", "127.0.0.1", "localhost"):
            self.assertNotIn(needle, raw)


class Captures(unittest.TestCase):
    def test_one_capture_per_document_from_the_local_model(self):
        data = targeted.load_captures()
        meta = data["meta"]
        self.assertEqual(meta["model"], "qwen3:8b")
        self.assertTrue(meta["backend"].startswith("local-direct"))
        self.assertEqual(meta["calls_per_document"], 2)
        import local_extract
        self.assertEqual(meta["prompt_sha256"],
                         {"fields": targeted.sha256(local_extract.FIELDS_PROMPT),
                          "employment": targeted.sha256(local_extract.EMPLOYMENT_PROMPT)})
        self.assertEqual(list(data["docs"]), [d for d, _v, _l in targeted.documents()])
        for doc, entry in data["docs"].items():
            self.assertIsInstance(entry["fields"]["parsed"], dict, doc)
            self.assertIsInstance(entry["employment"].get("employment"), list, doc)
            self.assertNotIn("error", entry, doc)

    def test_each_capture_is_of_the_committed_document(self):
        data = targeted.load_captures()
        for doc, (text, _derived, _gate) in DOCS.items():
            self.assertEqual(targeted.sha256(text), data["docs"][doc]["text_sha256"], doc)

    def test_a_capture_of_different_text_is_refused(self):
        captures = targeted.load_captures()
        doc = "app-mobile-plain"
        doctored = {"docs": {doc: dict(captures["docs"][doc], text_sha256="0" * 64)}}
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaisesRegex(ValueError, "not the text that was captured"):
                targeted.derive(doc, doctored, empty)

    def test_replay_is_deterministic(self):
        captures = targeted.load_captures()
        with tempfile.TemporaryDirectory() as empty:
            for doc in ("app-mobile-plain", "quality-reliability-twocol"):
                again = targeted.derive(doc, captures, empty)
                self.assertEqual(json.dumps(again, sort_keys=True, default=str),
                                 json.dumps(DOCS[doc], sort_keys=True, default=str), doc)

    def test_siblings_extract_the_same_person(self):
        """The model read one person in every variant: the same employment
        rows and the same experience, equal to the fixture's own dates. If a
        re-capture breaks this, the family measures extractor instability,
        not positioning."""
        import local_extract
        data = targeted.load_captures()
        for family, fam in targeted.FAMILIES.items():
            rows = [{"title": j["title"], "relevant": True,
                     "start": targeted.render.fmt_date(j["start"]),
                     "end": targeted.render.fmt_date(j["end"])} for j in fam["jobs"]]
            want = local_extract.months_from(rows, targeted.NOW)
            for doc in (d for d, v, _l in targeted.documents()
                        if targeted.split(v)[0] == family):
                got = data["docs"][doc]["employment"]["employment"]
                self.assertEqual([(r["company"], r["title"]) for r in got],
                                 [(j["company"], j["title"]) for j in fam["jobs"]], doc)
                self.assertEqual(DOCS[doc][1]["experience_months"], want, doc)

    def test_every_document_derives_without_escalation(self):
        for doc, (_text, derived, gate) in DOCS.items():
            self.assertTrue(derived["role_keywords"], doc)
            self.assertTrue(derived["skill_importance"], doc)
            self.assertGreater(len(gate), len(derived["title_hints"]) - 1, doc)


class TodaysConvergence(unittest.TestCase):
    """The failure these fixtures exist to expose, pinned so that a change to
    the per-résumé derivation shows up here and is re-measured on purpose."""

    def test_siblings_derive_identical_role_keywords_today(self):
        for family, sibs in M.SIBLINGS.items():
            keywords = {v: set(DOCS[f"{v}-plain"][1]["role_keywords"]) for v in sibs}
            self.assertEqual(len({frozenset(k) for k in keywords.values()}), 1,
                             (family, keywords))

    def test_a_machine_learning_label_leaves_the_skills_section_claimed(self):
        """Regression for the P0 fix released on main (ac93958).

        skill_evidence._LEARNING used to match "learning" in "Machine
        Learning", and a skills section has no sentence end, so every skill
        a data document listed there read LEARNING_OR_COURSEWORK. "Learning"
        now cues pedagogy only as a verb: every skills section is claimed,
        and a data document's is a plain skills-list claim."""
        for doc, (_text, derived, _gate) in DOCS.items():
            skills = [o["status"] for r in derived["skill_importance"]
                      for o in r["occurrences"] if o["section"] == "skills"]
            self.assertTrue(skills, doc)
            self.assertNotIn("LEARNING_OR_COURSEWORK", skills, doc)
            if targeted.split(doc)[0] == "data":
                self.assertEqual(set(skills), {"MENTIONED"}, doc)


class TodaysTrackIntent(unittest.TestCase):
    """What DQ2a reads from these fixtures today. Characterisation, not a
    DQ2c requirement."""

    def test_strong_headline_variants_are_sufficient_with_their_declared_title(self):
        for vid, spec in M.VARIANTS.items():
            if spec["case"] != "strong_headline":
                continue
            for layout in targeted.LAYOUTS:
                intent = INTENTS[f"{vid}-{layout}"]
                self.assertTrue(intent.sufficient, (vid, layout, intent.reason))
                parts = {p for t in intent.declared_titles for p in t.parts}
                self.assertTrue(any(M.has_phrase(p, term) for p in parts
                                    for term in spec["title_terms"]), (vid, layout, parts))

    def test_the_no_headline_control_is_insufficient(self):
        for layout in targeted.LAYOUTS:
            intent = INTENTS[f"data-grouped-control-{layout}"]
            self.assertFalse(intent.sufficient, (layout, intent.reason))
            self.assertEqual(intent.declared_titles, ())
            self.assertEqual(intent.concepts, ())

    def test_the_generic_control_positions_nothing_but_a_wildcard_title(self):
        """platform-generic: "Software Engineer", no summary, no projects.
        DQ2a's provisional rule counts ANY declared title as sufficient, so it
        reads sufficient — on a title that matches over a quarter of the
        market and no positioned concept. DQ2c's fail-open must discount it."""
        import local_search
        market = local_search.frozen_market()
        titles = [(t, s) for t, s, _sk, _c in market.rows]
        for layout in targeted.LAYOUTS:
            intent = INTENTS[f"platform-generic-{layout}"]
            self.assertEqual(intent.concepts, (), layout)
            parts = [p for t in intent.declared_titles for p in t.parts]
            self.assertEqual(parts, ["software engineer"], layout)
            share = local_search.profile_of(parts[0], titles, ())["share"]
            self.assertGreater(share, local_search.WILDCARD_SHARE)

    def test_the_lowercase_self_identified_title_is_read_in_every_layout(self):
        """quality-automation (and its flat-skills twin) writes its role only
        as "I am a backend automation engineer: …", in lower case. It is read
        from that sentence, starting right after the article; no other
        document's summary has the form, so nothing else can change."""
        import skill_evidence as se
        import track_intent
        for doc, intent in INTENTS.items():
            text = DOCS[doc][0]
            summaries = [(s, e) for k, _n, s, e in se.sections(text) if k == se.SUMMARY]
            selves = [m for s, e in summaries
                      for m in track_intent._SELF_ID.finditer(text, s, e)]
            if not doc.startswith("quality-automation-"):
                self.assertEqual(selves, [], doc)
                continue
            self.assertEqual(len(selves), 1, doc)
            self.assertEqual([(t.title, t.source) for t in intent.declared_titles],
                             [("software engineer", "header"),
                              ("backend automation engineer", "summary")], doc)
            title = intent.declared_titles[1]
            self.assertEqual(text[slice(*title.span)], "backend automation engineer", doc)
            self.assertEqual(title.span[0], selves[0].end(), doc)
            self.assertTrue(any(s <= title.span[0] and title.span[1] <= e
                                for s, e in summaries), doc)

    def test_layouts_agree_on_declared_titles_and_sufficiency(self):
        for vid in M.VARIANTS:
            plain, twocol = INTENTS[f"{vid}-plain"], INTENTS[f"{vid}-twocol"]
            self.assertEqual(plain.titles, twocol.titles, vid)
            self.assertEqual(plain.sufficient, twocol.sufficient, vid)

    def test_layouts_agree_on_experience(self):
        for vid in M.VARIANTS:
            self.assertEqual(DOCS[f"{vid}-plain"][1]["experience_months"],
                             DOCS[f"{vid}-twocol"][1]["experience_months"], vid)

    def test_grouped_skills_are_recorded_and_flat_ones_are_not(self):
        for doc, intent in INTENTS.items():
            vid = doc.rsplit("-", 1)[0]
            grouped = "groups" in targeted.person(vid)["skills"]
            labelled = [g for g in intent.skills_groups if g is not None]
            if grouped:
                self.assertGreaterEqual(len(labelled), 4, doc)
            else:
                self.assertEqual(labelled, [], doc)

    def test_the_intent_record_holds_no_resume_text_or_contact(self):
        for doc, intent in INTENTS.items():
            fam = targeted.FAMILIES[targeted.split(doc)[0]]
            text = DOCS[doc][0]
            banned = [fam["name"], *fam["name"].split(), fam["email"],
                      fam["phone"].replace(" ", ""),
                      *(j["company"] for j in fam["jobs"]),
                      *(p["name"] for p in fam["projects"].values())]
            # A headline that IS a declared title is stored by design (a
            # validated title phrase); every other long line must not be.
            titles = {t.title for t in intent.declared_titles}
            lines = [line.strip() for line in text.splitlines()
                     if len(line.strip()) >= 25 and line.strip().lower() not in titles]
            record = intent.as_dict()
            for value in strings({k: v for k, v in record.items()}):
                if re.fullmatch(r"[0-9a-f]{8,64}", value):
                    continue      # a sentence digest
                low = value.lower()
                for item in banned:
                    self.assertNotIn(item.lower(), low, (doc, value))
                for line in lines:
                    self.assertNotIn(line.lower(), low, (doc, value))


if __name__ == "__main__":
    unittest.main()
