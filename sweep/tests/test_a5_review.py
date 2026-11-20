"""Direction A, stage A5: the public Review screen (tap to tune).

THE CONTRACT. The weight form posts `term` (hidden) and `weight` (1 to 5) as PARALLEL lists, and logic.reweighted() zips the
i-th term with the i-th weight (it refuses lists of different lengths). A5 redrew that editor as chips, so a skill row now
lives inside a chip, its panel, a "+N more" wrapper: the tests below read the form the way a browser builds a submission
(every named, enabled control, in DOCUMENT ORDER; a checkbox only when checked) and prove that the pairing is exactly the
one the console's table renders, that the rows behind "+N more" are in it, and that posting it back saves exactly the edits
made and nothing else. They run on all three production paths: one résumé with Multi-Track off, one résumé with Multi-Track
on (review.html without `resumes`), and two or three (the unified review, the form inside the open card).

Around it: the new copy and parts (eyebrow, headline, lede, the years chip and the editor it opens, six roles and
"+N more", ten skill chips and "+N more", five dots per skill, one tip, two peeks), "no script, no hidden anything" (the
closed reveals are hidden only under `.skin-a.js`), the console untouched, and Results' re-rank editor byte-identical.
No model, provider or network (the unified review uses the P4-U1 harness: sealed env, the real worker on loopback).
"""
import copy
import hashlib
import html
import os
import pathlib
import re
import shutil
import tempfile
import unittest
from html.parser import HTMLParser
from unittest import mock

from werkzeug.datastructures import MultiDict

import skill_concepts
from sweep import app as app_module
from sweep.tests import test_multi_render as r1
from sweep.tests import test_unified_review as tur
from sweep.tests.test_app import DERIVED
from sweep.tests.test_public import public_app, unlocked, upload
from sweep.tests.test_public_guardrails import room_of

setUpModule, tearDownModule = r1.setUpModule, r1.tearDownModule

STATIC = pathlib.Path(app_module.__file__).parent / "static"
CSS = (STATIC / "sweep-a.css").read_text()
A5_CSS = CSS[CSS.rindex("/*", 0, CSS.index("==== A5: the Review screen")):]        # this stage's section, from its opening comment

# Fourteen skills, so ten show and four are behind "+N more"; weights 1 to 5 with ties (the sort must be stable and the
# same in both modes); five at or under the commodity line (2) so some are "Common"; tiers on some, a penalty term or two.
SKILLS = [("python", 5), ("django", 5), ("celery", 5), ("redis", 4), ("postgresql", 4), ("docker", 3),
          ("kubernetes", 3), ("graphql", 3), ("rabbitmq", 3), ("aws", 2), ("git", 2), ("linux", 2),
          ("javascript", 1), ("sql", 2)]
TIERS = {"celery": "CORE", "django": "CORE", "redis": "STRONG_SECONDARY", "graphql": "SUPPORTING",
         "docker": "SUPPORTING", "git": "BACKGROUND", "aws": "BACKGROUND"}
ROLES = ["backend engineer", "back end developer", "python developer", "django developer", "platform engineer",
         "site reliability engineer", "devops engineer", "cloud engineer"]
BIG = dict(
    DERIVED, field_summary="Backend engineer, about 5 years, Python and Django.", years_experience=5,
    experience_months=67, role_keywords=ROLES,
    skill_weights=[{"term": t, "weight": w} for t, w in SKILLS],
    skill_importance=[{"id": skill_concepts.resolve(t), "tier": tier, "why": f"WHY-{t}"} for t, tier in TIERS.items()],
    penalty_terms=[{"term": "salesforce", "weight": 5}, {"term": "apex", "weight": 4}],
    notes="Platform terms dominate.")
ORDER = [t for t, _ in sorted(SKILLS, key=lambda s: -s[1])]          # the sort both modes use (stable)
WEIGHT = dict(SKILLS)


def big():
    return copy.deepcopy(BIG)


# ---- the form, the way a browser reads it -------------------------------------------------------------------------
class Editor(HTMLParser):
    """The `data-editor` form: its action and every control a browser would submit, in document order. An unchecked
    checkbox is absent, a disabled control is absent, a button and a nameless control contribute nothing."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.action, self.fields, self.inside, self.texts = None, [], False, []
        self._select, self._textarea = None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form" and "data-editor" in a:
            self.inside, self.action = True, a.get("action")
        elif not self.inside:
            return
        elif tag == "input" and a.get("name") and "disabled" not in a:
            kind = (a.get("type") or "text").lower()
            if kind in ("submit", "button", "image", "reset", "file"):
                return
            if kind in ("checkbox", "radio") and "checked" not in a:
                return
            self.fields.append((a["name"], a.get("value", "on" if kind in ("checkbox", "radio") else "")))
        elif tag == "select" and a.get("name") and "disabled" not in a:
            self._select = [a["name"], None, None]
        elif tag == "option" and self._select:
            if self._select[2] is None:
                self._select[2] = a.get("value", "")
            if "selected" in a:
                self._select[1] = a.get("value", "")
        elif tag == "textarea" and a.get("name") and "disabled" not in a:
            self._textarea = [a["name"], ""]

    def handle_data(self, data):
        if self._textarea:
            self._textarea[1] += data

    def handle_endtag(self, tag):
        if tag == "form" and self.inside:
            self.inside = False
        elif tag == "select" and self._select:
            name, chosen, first = self._select
            self.fields.append((name, chosen if chosen is not None else (first or "")))
            self._select = None
        elif tag == "textarea" and self._textarea:
            self.fields.append(tuple(self._textarea))
            self._textarea = None


def editor(body):
    parser = Editor()
    parser.feed(body)
    assert parser.action is not None, "no form[data-editor] on the page"
    return parser.action, parser.fields


def pairs(fields):
    """[(term, weight)] the way logic.reweighted() reads them: the i-th term with the i-th weight."""
    terms = [v for n, v in fields if n == "term"]
    weights = [v for n, v in fields if n == "weight"]
    return list(zip(terms, weights)), len(terms), len(weights)


def problems(fields, expected):
    """Why this form would silently reassign a weight, if it would. `expected` is [(term, weight-as-string)] in order."""
    got, nterms, nweights = pairs(fields)
    out = []
    if nterms != nweights:
        out.append(f"{nterms} terms but {nweights} weights")
    if nterms != len(expected):
        out.append(f"{nterms} terms for {len(expected)} skills")
    if got != expected:
        out.append("the (term, weight) pairs differ from the console's")
    return out


def tune_rows(body):
    """[(classes, term, weight, filled dots)] for each tune-row, in order, read from the markup."""
    out = []
    for m in re.finditer(r'<div class="tune-row([^"]*)"[^>]*>(.*?)\n    </div>', body, re.S):
        row = m.group(2)
        term = html.unescape(re.search(r'name="term" value="(.*?)"', row).group(1))
        weight = re.search(r'name="weight" min="1" max="5"\s+value="(\d+)"', row).group(1)
        dots = re.search(r'<span\s+class="dots" aria-hidden="true">(.*?)</span>', row, re.S).group(1)
        out.append((m.group(1).split(), term, weight, len(re.findall(r'<i class="f"', dots)), len(re.findall(r"<i[\s>]", dots))))
    return out


def edited(fields):
    """The same submission after a visitor: moved one weight (celery 5 to 2), ticked Remove on one skill (redis), typed one
    skill ("grpc", at 4) and corrected the experience (7 years 3 months). Cross-name order does not matter to a browser's
    getlist, only order within a name does, so the checkbox is inserted where the row is."""
    out = []
    for name, value in fields:
        if name == "weight" and out and out[-1] == ("term", "celery"):
            value = "2"
        if name == "add_skills":
            value = "grpc"
        if name == "add_weight":
            value = "4"
        if name == "experience_years":
            value = "7"
        if name == "experience_months":
            value = "3"
        out.append((name, value))
        if (name, value) == ("term", "redis"):
            out.append(("drop", "redis"))
    return out


EXPECTED = {t: w for t, w in SKILLS if t != "redis"}
EXPECTED["celery"] = 2
EXPECTED["grpc"] = 4


def submit(client, body, change=edited):
    action, fields = editor(body)
    return client.post(action, data=MultiDict(change(fields)))


def saved_weights(derived):
    return {w["term"]: w["weight"] for w in derived["skill_weights"]}


def flat(text):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text)).split())


# ---- one résumé, Multi-Track off (the plain public flow) ------------------------------------------------------------
def main_heading_levels(body):
    """The heading levels inside <main>, in document order (the page's own outline, not the header's or the dialogs')."""
    main = re.search(r"<main>.*?</main>", body, re.S).group(0)
    return [int(n) for n in re.findall(r"<h([1-6])\b", main)]


class OneResume(unittest.TestCase):
    def setUp(self):
        self.app = public_app(derive=lambda text, prefs: big())
        self.client = unlocked(self.app)
        self.assertEqual(upload(self.client).status_code, 302)
        self.assertEqual(self.client.post("/derive").status_code, 302)
        self.body = self.client.get("/review").get_data(as_text=True)

    # -- the contract ----------------------------------------------------------------------------------------------
    def test_term_and_weight_are_parallel_and_match_the_consoles_table(self):
        _, fields = editor(self.body)
        expected = [(t, str(WEIGHT[t])) for t in ORDER]
        self.assertEqual(problems(fields, expected), [])
        got, nterms, nweights = pairs(fields)
        self.assertEqual((nterms, nweights), (14, 14), "every skill, the four behind +N more included")
        self.assertEqual(got, console_pairs(), "tune mode and the console's table post the same pairs, in the same order")

    def test_the_other_fields_are_there_with_their_names_and_limits(self):
        _, fields = editor(self.body)
        names = [n for n, _ in fields]
        self.assertEqual(names.count("experience_years"), 1)
        self.assertEqual(names.count("experience_months"), 1)
        self.assertEqual(names.count("add_skills"), 1)
        self.assertEqual(names.count("add_weight"), 1)
        self.assertEqual(set(names), {"term", "weight", "experience_years", "experience_months", "add_skills", "add_weight"})
        self.assertRegex(self.body, r'name="experience_years" min="0" max="60"')
        self.assertRegex(self.body, r'name="experience_months" min="0" max="11"')
        self.assertRegex(self.body, r'name="add_weight" min="1" max="5" value="3"')
        self.assertRegex(self.body, r'name="add_skills"\s+placeholder="kubernetes, terraform, grpc"')
        # nothing is pre-ticked, and no control is disabled (hidden rows still submit)
        self.assertNotIn(("drop", "redis"), editor(self.body)[1])
        form = re.search(r"<form[^>]*\bdata-editor\b.*?</form>", self.body, re.S).group(0)
        self.assertNotRegex(form, r"<input[^>]*(?<![:\w-])disabled\b")

    def test_the_pairing_checker_does_catch_a_broken_form(self):
        """The check above is only worth something if it fails when the pairing breaks."""
        _, fields = editor(self.body)
        expected = [(t, str(WEIGHT[t])) for t in ORDER]
        self.assertEqual(problems(fields, expected), [])
        no_term = list(fields)
        no_term.remove(("term", "python"))                                   # a hidden term input dropped
        self.assertTrue(problems(no_term, expected))
        no_weight = list(fields)
        no_weight.remove(("weight", "5"))                                    # a weight input dropped
        self.assertTrue(problems(no_weight, expected))
        extra = fields + [("weight", "3")]                                   # a third value under `weight`
        self.assertTrue(problems(extra, expected))
        at = [k for k, f in enumerate(fields) if f[0] == "weight"]
        swapped = list(fields)
        swapped[at[0]], swapped[at[3]] = swapped[at[3]], swapped[at[0]]      # two weights traded: same lengths, wrong pairs
        self.assertTrue(problems(swapped, expected))
        doctored = self.body.replace('<input type="hidden" name="term" value="python">', "", 1)
        self.assertNotEqual(doctored, self.body)
        self.assertTrue(problems(editor(doctored)[1], expected), "the page itself, one term input removed")

    def test_posting_the_form_back_saves_exactly_the_edits(self):
        r = submit(self.client, self.body)
        self.assertEqual((r.status_code, r.headers["Location"]), (302, "/key"))
        derived = room_of(self.app, self.client)["derived"]
        self.assertEqual(saved_weights(derived), EXPECTED)
        self.assertEqual([w["term"] for w in derived["skill_weights"]],
                         [t for t, _ in SKILLS if t != "redis"] + ["grpc"], "order kept, the added one last")
        self.assertEqual((derived["years_experience"], derived["experience_months"]), (7, 87))
        for k in ("role_keywords", "penalty_terms", "skill_importance", "field_summary"):
            self.assertEqual(derived[k], BIG[k], k)

    def test_posting_it_untouched_changes_nothing(self):
        r = submit(self.client, self.body, change=lambda fields: fields)
        self.assertEqual(r.status_code, 302)
        derived = room_of(self.app, self.client)["derived"]
        self.assertEqual(saved_weights(derived), WEIGHT)
        self.assertEqual((derived["years_experience"], derived["experience_months"]), (5, 67))

    # -- the headline, the parts ----------------------------------------------------------------------------------
    def test_the_three_findings_are_h2_under_the_h1_so_no_level_is_skipped(self):
        """Pre-merge polish: they were h3 straight under the h1. They are h2 now (one look, `read-h`), so the outline is h1, h2, h2, h2."""
        levels = main_heading_levels(self.body)
        self.assertEqual(levels, [1, 2, 2, 2])
        self.assertTrue(all(b <= a + 1 for a, b in zip(levels, levels[1:])), levels)
        self.assertNotIn("<h3", re.search(r"<main>.*?</main>", self.body, re.S).group(0))
        self.assertEqual(re.findall(r'<h2 class="read-h">(.*?)</h2>', self.body),
                         ["You", "Roles Sweep will search for", "Your skills · tap one to tune it"])

    def test_the_headline(self):
        self.assertIn('<span class="eyebrow">Step 2 · profile check</span>', self.body)
        self.assertIn('<h1>Did we get you <span class="scrib">right</span>?</h1>', self.body)
        self.assertIn('Read from <b class="filename">cv.pdf</b>. Tap anything that looks off.', " ".join(self.body.split()))
        for gone in ("Here's what Sweep understood about you", "Check it over", "this is what your job search will be based on"):
            self.assertNotIn(gone, self.body)
        self.assertLess(self.body.index("eyebrow"), self.body.index("<h1>"))

    def test_the_lede_keeps_its_fallback_name(self):
        lede = re.search(r'<p class="lede">(.*?)</p>', self.body, re.S).group(1)
        self.assertEqual(" ".join(re.sub(r"<[^>]+>", "", lede).split()), "Read from cv.pdf. Tap anything that looks off.")
        template = (pathlib.Path(app_module.__file__).parent / "templates" / "review.html").read_text()
        self.assertIn("{%- else %} your résumé{% endif %}. Tap anything that looks off.", template)

    def test_the_years_chip_holds_the_editor_it_opens(self):
        chip = re.search(r'<button type="button" class="xp-chip" aria-controls="xp-edit"([^>]*)>(.*?)</button>',
                         self.body, re.S)
        self.assertIsNotNone(chip)
        # Its state comes only from Alpine: without JavaScript the editor is open, so a fixed aria-expanded="false" would
        # tell a screen reader the opposite of what is on screen (A5 review).
        self.assertNotRegex(chip.group(1), r'(?<!:)aria-expanded=')
        self.assertIn(':aria-expanded="open ? \'true\' : \'false\'"', chip.group(1))
        text = chip.group(2)
        self.assertEqual(flat(text), "5 years 7 months of experience")
        self.assertIn('aria-hidden="true"', text)                                         # the pencil
        start = self.body.index('<div class="xp-edit" id="xp-edit"')
        edit = " ".join(self.body[start:self.body.index('<div class="read-block">', start)].split())
        for needle in ('name="experience_years"', 'name="experience_months"', 'id="exp-label">Experience<',
                       'id="exp-why">Sweep uses this to skip jobs asking for far more experience than you have.',
                       'aria-label="One year more"', 'aria-label="One month less"', 'min="0" max="60"', 'min="0" max="11"'):
            self.assertIn(needle, edit)
        self.assertLess(self.body.index('class="xp-chip"'), self.body.index('class="xp-edit"'))
        self.assertNotIn('<p class="muted">5 years 7 months of experience</p>', self.body)
        self.assertEqual(self.body.count('class="xp-chip"'), 1)

    def test_six_roles_then_plus_n_more(self):
        block = re.search(r'<p class="chips" x-data="\{ all: false \}".*?</p>', self.body, re.S).group(0)
        tags = re.findall(r'<span\s+class="tag( extra)?">(.*?)</span>', block, re.S)
        self.assertEqual([t for _, t in tags], ROLES)
        self.assertEqual([bool(e) for e, _ in tags], [False] * 6 + [True] * 2)
        self.assertRegex(block, r'<button type="button" class="chip more"[^>]*>\+2 more</button>')
        self.assertIn("Taken from the roles on your résumé.", self.body)
        self.assertIn("Roles Sweep will search for", self.body)
        self.assertIn('<span class="meta">8 found</span>', self.body)

    def test_few_roles_have_no_more_button(self):
        app = public_app(derive=lambda text, prefs: dict(big(), role_keywords=ROLES[:6]))
        client = unlocked(app)
        upload(client)
        client.post("/derive")
        body = client.get("/review").get_data(as_text=True)
        self.assertNotIn('class="chip more"', body.split("Your skills")[0])
        self.assertNotIn(" extra", body.split("Your skills")[0].split("Roles Sweep")[1])

    def test_ten_skill_chips_then_plus_n_more(self):
        rows = tune_rows(self.body)
        self.assertEqual([r[1] for r in rows], ORDER)
        self.assertEqual(["extra" in r[0] for r in rows], [False] * 10 + [True] * 4)
        self.assertEqual(self.body.count('class="tune-chip"'), 14)
        self.assertRegex(self.body, r'<button type="button" class="chip more" @click="all = !all"[^>]*\s+x-text="all \? \'Show fewer\' : \'\+4 more\'">\+4 more</button>')
        self.assertEqual(self.body.count('class="chip more"'), 2, "the roles' and the skills'")
        self.assertIn('<h2 class="read-h">Your skills · tap one to tune it</h2>', self.body)
        self.assertIn('<span class="meta">14 found</span>', self.body)
        self.assertIn('<div class="tunes" data-tunes :class="{ all: all }">', self.body)

    def test_every_row_has_five_dots_filled_to_its_weight(self):
        rows = tune_rows(self.body)
        self.assertEqual(len(rows), 14)
        for classes, term, weight, filled, total in rows:
            with self.subTest(term=term):
                self.assertEqual((total, filled), (5, int(weight)))
        # the dots follow `n`, so they move with the stepper
        self.assertEqual(len(re.findall(r':class="\{ f: n >= [1-5] \}"', self.body)), 70)
        for k in range(1, 6):
            self.assertEqual(self.body.count(f':class="{{ f: n >= {k} }}"'), 14)

    def test_a_row_is_chip_then_term_then_panel_in_that_order(self):
        row = re.search(r'<div class="tune-row"[^>]*>.*?\n    </div>', self.body, re.S).group(0)
        order = [row.index(x) for x in ('class="tune-chip"', 'name="term" value="python"', 'class="tune-pop" id="tune-1"',
                                        'name="weight"', 'class="tune-word"', 'class="remove"', 'class="tune-why"')]
        self.assertEqual(order, sorted(order))
        self.assertIn('aria-controls="tune-1"', row)
        self.assertIn(':aria-expanded="open ? \'true\' : \'false\'"', row)
        self.assertIn("x-data='{ n: 5, open: false }'", row)
        self.assertIn('aria-label="Lower the weight for python"', row)
        self.assertIn('aria-label="Raise the weight for python"', row)
        self.assertIn('aria-label="Weight for python"', row)
        self.assertIn('x-model.number="n"', row)
        self.assertRegex(row, r'<span class="tune-word" x-text="[^"]*">a huge amount</span>')
        self.assertRegex(row, r'<span class="visually-hidden">, weight <span\s+x-text="n">5</span> of 5</span>')
        self.assertRegex(row, r'<span class="remove-off">Remove</span><span\s+class="remove-on">Undo</span>')
        self.assertIn('<input type="checkbox" name="drop" value="python">', row)

    def test_the_word_for_the_level_is_server_rendered_for_every_weight(self):
        words = {r[1]: re.search(r'class="tune-word"[^>]*>(.*?)</span>', blk).group(1)
                 for r, blk in zip(tune_rows(self.body), re.findall(r'<div class="tune-pop".*?</p>\s*</div>', self.body, re.S))}
        self.assertEqual(words["python"], "a huge amount")
        self.assertEqual(words["redis"], "a lot")
        self.assertEqual(words["docker"], "some")
        self.assertEqual(words["aws"], "a little")
        self.assertEqual(words["javascript"], "barely")

    def test_the_badges_and_the_reason_under_each_skill(self):
        blocks = dict(zip((r[1] for r in tune_rows(self.body)), re.findall(r'<div class="tune-pop".*?</p>\s*</div>', self.body, re.S)))
        core = blocks["celery"]
        self.assertIn('<span class="tag core" title="WHY-celery">Used at work</span>', core)
        self.assertIn('<p class="tune-why">WHY-celery</p>', core)
        self.assertNotIn(">Common<", core)
        self.assertIn('<span class="tag strong" title="WHY-redis">Built with</span>', blocks["redis"])
        self.assertIn('<span class="tag support" title="WHY-graphql">Listed</span>', blocks["graphql"])
        # a common term with a tier: both badges, the tier's reason
        both = blocks["git"]
        self.assertIn('<span class="tag low" title="WHY-git">Background</span>', both)
        self.assertIn('title="Common in job descriptions, so it separates listings less — not a judgement about your skill">Common</span>', both)
        self.assertIn('<p class="tune-why">WHY-git</p>', both)
        # a common term with no tier: the market sentence; a plain one: the ranking sentence
        self.assertIn("<p class=\"tune-why\">Most job posts mention linux, so it separates listings less. That is about the market, "
                      "not about you — it stays in.</p>", blocks["linux"])
        self.assertIn(">Common</span>", blocks["linux"])
        self.assertIn('<p class="tune-why">Jobs that ask for kubernetes rank higher the more you weight it.</p>', blocks["kubernetes"])
        self.assertNotIn(">Common<", blocks["kubernetes"])

    def test_the_add_row_moved_here_and_opens_from_a_chip(self):
        self.assertEqual(self.body.count('name="add_skills"'), 1)
        self.assertRegex(self.body, r'<button type="button" class="tune-chip tune-add" @click="add = !add"[^>]*aria-controls="add-skills">\+ Add a skill</button>')
        self.assertRegex(self.body, r'<div class="add-skills" id="add-skills" :class="\{ open: add \}"><div class="row">')
        self.assertIn("Add skills the parse missed", self.body)
        self.assertLess(self.body.rindex('class="tune-row'), self.body.index('class="tune-chip tune-add"'))
        self.assertLess(self.body.index('class="tune-chip tune-add"'), self.body.index('name="add_skills"'))

    def test_one_tip_above_the_skills(self):
        self.assertEqual(self.body.count('data-tip="review-tune"'), 1)
        self.assertIn('<p class="tip-say">Tap a skill to tell Sweep how much it matters.</p>', self.body)
        self.assertLess(self.body.index('data-tip="review-tune"'), self.body.index('class="tunes"'))
        self.assertGreater(self.body.index('data-tip="review-tune"'), self.body.index("Your skills"))
        self.assertIn('<script defer src="/static/tips.js"></script>', self.body)

    def test_two_peeks_with_the_sentences_that_were_in_the_adjust_door(self):
        peeks = re.findall(r'<details class="peek"><summary><span class="peek-label">(.*?)</span></summary>'
                           r'<div class="peek-body">(.*?)</div></details>', self.body, re.S)
        self.assertEqual([p[0] for p in peeks], ["How does ranking work?", "What counts against a match?"])
        rank = flat(peeks[0][1])
        self.assertIn("A higher weight means a job asking for that skill ranks higher. Weighted by how well a skill picks out the "
                      "jobs you want — a word that also appears in jobs you do not want scores low however good you are at it.", rank)
        self.assertIn("aws, git, linux, javascript and sql appear in most job descriptions, so they separate listings less than "
                      "the rest. That is about the market, not about you — they are kept. Open one to remove it.", rank)
        self.assertNotIn("Tick one", rank)
        against = peeks[1][1]
        self.assertEqual(re.findall(r'<span\s+class="tag">(.*?)</span>', against), ["salesforce", "apex"])
        self.assertIn("Read as outside your field, so a job asking for one ranks lower. Nothing is excluded outright.", flat(against))
        # closed at first, native details, and not inside the page's chips
        self.assertNotRegex(self.body, r'<details class="peek" open')

    def test_no_commodity_sentence_and_no_penalty_peek_when_there_is_nothing_to_say(self):
        plain = dict(big(), penalty_terms=[], skill_weights=[{"term": t, "weight": 4} for t in ("python", "django")],
                     skill_importance=[])
        app = public_app(derive=lambda text, prefs: copy.deepcopy(plain))
        client = unlocked(app)
        upload(client)
        client.post("/derive")
        body = client.get("/review").get_data(as_text=True)
        self.assertEqual(body.count('<details class="peek">'), 1)
        self.assertNotIn("What counts against a match?", body)
        self.assertNotIn("appear in most job descriptions", body)
        self.assertNotIn('class="chip more"', body.split("Your skills")[1], "two skills, no +N more")

    def test_an_unverified_work_history_asks_for_the_years_and_saving_clears_it(self):
        """local_extract.route: when the work history could not be checked the reader keeps the profile, counts only the
        rows it could, and flags it. Review opens the experience editor and says why; saving it is the person's answer."""
        app = public_app(derive=lambda text, prefs: dict(big(), years_experience=0, experience_months=0,
                                                         experience_unverified=True))
        client = unlocked(app)
        upload(client)
        client.post("/derive")
        body = client.get("/review").get_data(as_text=True)
        self.assertIn("Set your years of experience", body)
        self.assertIn('<div class="xp-edit open" id="xp-edit"', body)
        self.assertIn("Sweep couldn't check the dates in your work history,", body)
        self.assertNotIn("Set your years of experience", self.body)       # a clean read says nothing of it
        from sweep import logic
        saved = logic.with_experience({"years_experience": 0, "experience_unverified": True}, "3", "2")
        self.assertEqual(saved, {"years_experience": 3, "experience_months": 38})

    def test_there_is_no_adjust_door_and_no_table_in_public(self):
        for gone in ('class="adjust"', "Adjust what Sweep looks for", "Your strongest skills", 'class="weights"',
                     "How your skills are weighted", "Counted against a match", "Sweep already filled all of this in",
                     "Jobs are ranked on how many of these they ask for", 'class="tag more"'):
            self.assertNotIn(gone, self.body)

    def test_the_footer_is_as_it_was(self):
        bar = re.search(r'<div class="actionbar">.*?</form>', self.body, re.S).group(0)
        self.assertIn('<a class="tertiary" href="/">Start over with a different résumé</a>', bar)
        self.assertRegex(bar, r'<button class="primary" type="submit" :disabled="sent">Continue to job search<span class="go"\s+'
                              r'aria-hidden="true">&rarr;</span></button>')
        self.assertIn("Setting up your search…", bar)

    def test_the_reveals_are_a_script_job_without_one_everything_is_open(self):
        """The server writes no `hidden`, no x-cloak and no display:none on a reveal; closed is a class Alpine sets, and the
        stylesheet hides it only under .skin-a.js (which theme.js adds)."""
        form = re.search(r"<form[^>]*\bdata-editor\b.*?</form>", self.body, re.S).group(0)
        scope = form[form.index('class="read"'):]
        self.assertNotRegex(re.sub(r'<button[^>]*data-tip-dismiss[^>]*>', "", scope), r'<[a-z]+[^>]*\shidden[\s>]')   # the tip's own button ships hidden
        self.assertNotIn("x-cloak", scope.replace('x-show="sent" x-cloak', ""))
        self.assertNotIn("display: none", scope)
        self.assertNotIn("display:none", scope)
        self.assertNotRegex(scope, r'<[a-z]+[^>]*(?<![:\w-])class="[^"]*\b(open|all)\b')   # nothing is served already open or expanded
        css = re.sub(r"/\*.*?\*/", "", A5_CSS, flags=re.S)
        hiding = [(sel.strip(), body) for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css) if re.search(r"display:\s*none", body)]
        self.assertTrue(hiding)
        # Not reveals: these hide what is EMPTY or ABSENT (A9's card cells with no location or skills, a pay/experience cell that
        # says "Not stated", A10's tracker chip with no current step) — there is nothing in them for a script to open, so they
        # are hidden with or without one. Named one by one, so a new reveal that is not under .skin-a.js still fails here.
        empty_or_absent = {".skin-a .res-a .jobs td.loc:empty", ".skin-a .res-a .jobs td.none",
                           ".skin-a .res-a .jobs td.skills:empty", ".skin-a .tracker-at:empty"}
        for sel, _ in hiding:
            for part in sel.split(","):
                if ":not(.js)" in part:
                    continue                                                   # the two "no script" rules, which hide a button
                if " ".join(part.split()) in empty_or_absent:
                    continue
                self.assertIn(".skin-a.js ", part.strip() + " ", sel)
        theme = (STATIC / "theme.js").read_text()
        self.assertIn('root.classList.add("js")', theme)

    def test_no_x_cloak_hides_a_reveal(self):
        template = (pathlib.Path(app_module.__file__).parent / "templates" / "_weights.html").read_text()
        self.assertNotIn("x-cloak", template)
        self.assertNotIn("x-show", template)

    def test_the_public_form_is_still_the_one_guarded_editor(self):
        self.assertEqual(len(re.findall(r"<form[^>]*\bdata-editor\b", self.body)), 1)
        self.assertIn("static/dirty.js", self.body)
        self.assertIn('<form method="post" action="/review" class="stack review-form"', self.body)


def console_pairs():
    """The (term, weight) pairs the CONSOLE's table renders for BIG: the macro in table mode, the console's own call."""
    with public_app().test_request_context("/"):
        env = public_app().jinja_env
        out = env.from_string('{% from "_weights.html" import weight_editor %}'
                              "{{ weight_editor(skill_weights, commodity, importance) }}").render(
            skill_weights=BIG["skill_weights"], commodity=[w["term"] for w in BIG["skill_weights"] if w["weight"] <= 2],
            importance={})
    terms = re.findall(r'<input type="hidden" name="term" value="(.*?)">', out)
    weights = re.findall(r'<input type="number" name="weight" min="1" max="5"\s+value="(\d+)"', out)
    assert len(terms) == len(weights) == 14
    return list(zip(terms, weights))


# ---- one résumé, Multi-Track on (production's primary path) and two or three (the unified review) -------------------
class Harness(tur.Unified):
    """The P4-U1 harness with the model answering BIG for every résumé."""

    def setUp(self):
        patch = mock.patch.object(tur, "derived_for", lambda fixture: copy.deepcopy(BIG))
        patch.start()
        self.addCleanup(patch.stop)
        super().setUp()

    def read_all(self):
        while self.read()[1]["state"] != "idle":
            pass


class OneResumeMultiTrackOn(Harness):
    """The setup holds ONE résumé: review.html without `resumes`, and a track in the form's action."""

    def setUp(self):
        super().setUp()
        self.act(self.b, "remove", back="review")
        self.act(self.c, "remove", back="review")
        self.assertEqual(self.client.post(f"/derive?track={self.a}").status_code, 302)
        self.body = self.view()

    def test_it_is_the_one_resume_review_not_the_unified_one(self):
        self.assertNotIn("data-resumes", self.body)
        self.assertNotIn('id="resumes-banner"', self.body)
        self.assertIn('<h1>Did we get you <span class="scrib">right</span>?</h1>', self.body)
        self.assertIn('<span class="eyebrow">Step 2 · profile check</span>', self.body)
        self.assertEqual(len(tune_rows(self.body)), 14)
        self.assertIn(f'<form method="post" action="/review?track={self.a}"', self.body)
        self.assertEqual(main_heading_levels(self.body), [1, 2, 2, 2], "one résumé with Multi-Track on is the same page: h1, then h2s")

    def test_term_and_weight_are_parallel_and_match_the_consoles_table(self):
        _, fields = editor(self.body)
        self.assertEqual(problems(fields, [(t, str(WEIGHT[t])) for t in ORDER]), [])
        self.assertEqual(pairs(fields)[0], console_pairs())

    def test_posting_the_form_back_saves_exactly_the_edits(self):
        r = submit(self.client, self.body)
        self.assertEqual(r.status_code, 302)
        derived = self.track(self.a)["derived"]
        self.assertTrue(self.track(self.a)["reviewed"])
        self.assertEqual(saved_weights(derived), EXPECTED)
        self.assertEqual((derived["years_experience"], derived["experience_months"]), (7, 87))


class UnifiedReview(Harness):
    """Two or three résumés: the form is inside the open card, and the page is read one résumé after another."""

    def setUp(self):
        super().setUp()
        self.read_all()
        self.body = self.view(self.a)

    def test_the_banner_keeps_its_server_written_title_and_gets_the_eyebrow(self):
        banner = re.search(r'<div class="stack-tight" id="resumes-banner">(.*?)</div>', self.body, re.S).group(1)
        self.assertRegex(banner, r'^\s*<span class="eyebrow">Step 2 · profile check</span>\s*<h1>Review your résumés</h1>\s*'
                                 r'<p class="lede" role="status">')
        self.assertEqual(self.body.count('class="eyebrow"'), 1)
        self.assertNotIn("Did we get you", self.body, "the one-résumé headline is not the unified page's")
        self.assertEqual(self.banner(self.body)[0], "Review your résumés")
        self.assertIn('data-reading="0"', self.body)
        self.assertIn('id="resumes-continue"', self.body)

    def test_the_open_cards_form_is_the_editor_and_carries_the_same_contract(self):
        card = re.search(r'<section class="resume" data-card="%s" data-open.*?</section>' % self.a, self.body, re.S).group(0)
        self.assertIn("<form", card)
        self.assertIn("data-editor", card)
        _, fields = editor(self.body)
        self.assertEqual(problems(fields, [(t, str(WEIGHT[t])) for t in ORDER]), [])
        self.assertEqual(pairs(fields)[0], console_pairs())
        self.assertEqual(len(tune_rows(self.body)), 14)
        self.assertEqual(self.body.count('data-editor'), 1)

    def test_posting_the_form_back_saves_exactly_the_edits_on_that_resume_only(self):
        others = {t: copy.deepcopy(self.track(t)["derived"]) for t in (self.b, self.c)}
        r = submit(self.client, self.body)
        self.assertEqual(r.status_code, 302)
        derived = self.track(self.a)["derived"]
        self.assertTrue(self.track(self.a)["reviewed"])
        self.assertEqual(saved_weights(derived), EXPECTED)
        self.assertEqual((derived["years_experience"], derived["experience_months"]), (7, 87))
        for t in (self.b, self.c):
            self.assertEqual(self.track(t)["derived"], others[t], "another résumé's profile changed")
            self.assertFalse(self.track(t)["reviewed"])

    def test_each_of_the_three_cards_posts_its_own_form_the_same_way(self):
        for tid in (self.a, self.b, self.c):
            with self.subTest(track=tid):
                body = self.view(tid)
                action, fields = editor(body)
                self.assertEqual(action, f"/review?track={tid}")
                self.assertEqual(problems(fields, [(t, str(WEIGHT[t])) for t in ORDER]), [])

    def test_the_cards_are_the_markup_reading_js_swaps(self):
        self.assertEqual(self.body.count("data-card="), 3)
        self.assertEqual(self.body.count("data-open"), 1)
        self.assertIn('<script src="/static/reading.js"></script>', self.body)
        self.assertIn('id="resumes-banner"', self.body)
        self.assertIn('id="resumes-continue"', self.body)

    def test_inside_a_resume_card_the_findings_stay_h3_under_that_cards_h2(self):
        """The form sits in the open card, whose own h2 is the section: h1 (banner), h2 per card, and the open card's three findings as h3.
        Same `read-h` look as the h2s on the one-résumé page."""
        levels = main_heading_levels(self.body)
        self.assertEqual(levels[0], 1)
        self.assertEqual(levels.count(1), 1)
        self.assertTrue(all(b <= a + 1 for a, b in zip(levels, levels[1:])), levels)
        self.assertEqual(re.findall(r'<h3 class="read-h">(.*?)</h3>', self.body),
                         ["You", "Roles Sweep will search for", "Your skills · tap one to tune it"])
        self.assertNotIn('<h2 class="read-h">', self.body)

    def test_the_stickers_are_css_only_no_card_markup_changed(self):
        # the three macros write the same section the same way; the look is selectors on it
        self.assertRegex(self.body, r'<section class="resume" data-card="\w+" aria-labelledby="resume-\d">')
        self.assertRegex(self.body, r'<section class="resume" data-card="\w+" data-open aria-labelledby="resume-\d">')


class TheRulesInTheStylesheet(unittest.TestCase):
    BARE = re.sub(r"/\*.*?\*/", "", A5_CSS, flags=re.S)

    def rule(self, selector):
        for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", self.BARE):
            if " ".join(sel.split()) == selector:
                return body
        self.fail("no rule for " + selector)

    def test_the_sticker_cards(self):
        body = self.rule(".skin-a .ledger > section.resume")
        for want in ("padding: 18px", "background: var(--surface)", "border: 2px solid var(--a-line)", "border-radius: 22px",
                     "box-shadow: 4px 4px 0 var(--a-shadow)"):
            self.assertIn(want, body)
        ring = self.rule(".skin-a .ledger > section.resume[data-open]")
        self.assertIn("outline: 3px solid var(--a-lav)", ring)
        self.assertIn("outline-offset: 3px", ring)
        self.assertIn("box-shadow: 6px 6px 0 var(--a-shadow)", ring)
        self.assertIn("background: var(--a-cit)", self.rule(".skin-a .ledger > section.resume .status.reviewed"))

    def test_the_findings_headings_keep_the_h3_look_whatever_the_level(self):
        body = self.rule(".skin-a .read-name .read-h")
        for want in ("margin: 0", "font: 600 14px/20px var(--text)", "letter-spacing: normal", "text-wrap: wrap"):      # sweep.css's h3, not the h2's display face
            self.assertIn(want, body)

    def test_the_years_chip_and_its_panel(self):
        chip = self.rule(".skin-a .xp-chip")
        for want in ("display: inline-flex", "2px dashed var(--a-line)", "border-radius: 12px", "background: var(--a-tint)"):
            self.assertIn(want, chip)
        self.assertIn("font: 600", chip)
        self.assertIn("border-style: solid", self.rule(".skin-a .xp-chip:hover"))
        edit = self.rule(".skin-a .xp-edit")
        for want in ("var(--a-tint)", "2px solid var(--a-line)", "border-radius: 18px", "padding: 14px 16px"):
            self.assertIn(want, edit)

    def test_the_skill_chip_and_its_dots(self):
        chip = self.rule(".skin-a .tune-chip")
        for want in ("min-height: 44px", "2px solid var(--a-line)", "border-radius: 999px", "background: var(--surface)"):
            self.assertIn(want, chip)
        self.assertIn("var(--a-tint)", self.rule(".skin-a .tune-chip:hover"))
        opened = self.rule(".skin-a .tune-row.open .tune-chip")
        for want in ("background: var(--a-lav)", "color: var(--a-ink)", "3px 3px 0 var(--a-shadow)", "rotate(-2deg)"):
            self.assertIn(want, opened)
        dot = self.rule(".skin-a .dots i")
        for want in ("width: 7px", "height: 7px", "1.5px solid currentColor", "border-radius: 50%"):
            self.assertIn(want, dot)
        self.assertIn("background: currentColor", self.rule(".skin-a .dots i.f"))
        self.assertIn("text-decoration: line-through",
                      self.rule('.skin-a .tune-row:has(input[name="drop"]:checked) .tune-chip'))

    def test_the_panel_and_the_reason(self):
        pop = self.rule(".skin-a .tune-pop")
        for want in ("flex-wrap: wrap", "var(--a-tint)", "2px solid var(--a-line)", "border-radius: 18px"):
            self.assertIn(want, pop)
        why = self.rule(".skin-a .tune-why")
        self.assertIn("font-size: 14.5px", why)
        self.assertIn("color: var(--warm)", why)
        self.assertIn("flex: 1 0 100%", why)

    def test_on_a_phone_the_bar_with_save_is_pinned(self):
        phone = self.BARE[self.BARE.index("@media (max-width: 40rem)"):]
        phone = phone[:phone.index("@media (prefers-reduced-motion")]
        bar = re.search(r"\.skin-a \.review-form > \.actionbar \{([^}]*)\}", phone).group(1)
        for want in ("position: sticky", "bottom: 0", "background: var(--ground)", "border-top: 2px solid var(--a-line)",
                     "env(safe-area-inset-bottom)"):
            self.assertIn(want, bar)

    def test_the_pop_in_and_the_rotation_transition_are_behind_no_preference(self):
        block = self.BARE[self.BARE.index("@media (prefers-reduced-motion: no-preference)"):]
        self.assertIn("animation: a-pop", block)
        self.assertIn("transition: transform", block)
        before = self.BARE[:self.BARE.index("@media (prefers-reduced-motion: no-preference)")]
        self.assertNotRegex(before, r"(animation|transition)\s*:")

    def test_no_raw_colour(self):
        self.assertNotRegex(self.BARE, r"#[0-9A-Fa-f]{3,8}\b")
        self.assertNotRegex(self.BARE, r"rgba?\(")


# ---- the console, and Results ---------------------------------------------------------------------------------------
def console_review():
    """GET /review in LOCAL mode, from a temporary tree (never the repository's profiles/ or auto-apply/)."""
    tmp = tempfile.mkdtemp(prefix="a5-console-")
    os.mkdir(os.path.join(tmp, "profiles"))
    try:
        with mock.patch.dict(os.environ, {"SWEEP_PUBLIC_MODE": ""}, clear=False), mock.patch.object(app_module, "REPO_ROOT", tmp):
            app = app_module.create_app(
                state={"resume_text": "x", "derived": big(), "profile": "probe_a5"},
                derive=lambda text, prefs: big(), read_rows=lambda profile: [], list_sweeps=lambda profile: [],
                resume_dir=os.path.join(tmp, "resume"), env_path=os.path.join(tmp, "none.env"),
                output_dir=os.path.join(tmp, "out"))
            app.config["TESTING"] = True
            r = app.test_client().get("/review")
            assert r.status_code == 200
            return r.get_data(as_text=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class TheConsoleIsUntouched(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = console_review()

    def test_it_renders_none_of_the_new_markup(self):
        for needle in ("tune-row", "tune-chip", "tune-pop", "tunes", "tune-wrap", "xp-chip", "xp-edit", "add-skills", "data-tunes",
                       "Did we get you", "Step 2 · profile check", 'class="eyebrow"', 'class="peek"', "data-tip", "How does ranking work",
                       "What counts against a match", "tap one to tune it", 'class="dots"', "chip more", "skin-a"):
            with self.subTest(needle=needle):
                self.assertNotIn(needle, self.body)

    def test_it_keeps_its_table_and_its_words(self):
        self.assertIn('<table class="weights">', self.body)
        self.assertIn("<h1>Review what it read</h1>", self.body)
        self.assertIn("Skill weights, 1 to 5", self.body)
        self.assertIn("Terms that push a listing down", self.body)
        self.assertEqual(self.body.count('name="weight"'), 14)
        self.assertEqual(self.body.count('name="term"'), 14)

    def test_its_pairs_are_the_ones_tune_mode_posts(self):
        _, fields = editor(self.body)
        self.assertEqual(pairs(fields)[0], console_pairs())

    def test_the_unified_banner_without_the_eyebrow_is_byte_identical(self):
        """The eyebrow is a parameter of the banner macro, empty everywhere but the public review: with none, the macro writes
        exactly the bytes it wrote before A5 (sha256 of the macro's output for this input, taken from the A4 template)."""
        app = public_app()
        card = {"title": "Review your résumés", "status": "All read", "reading": True}
        with app.test_request_context("/"):
            out = app.jinja_env.from_string('{% from "_resumes.html" import banner %}{{ banner(r) }}').render(r=card)
            with_none = app.jinja_env.from_string('{% from "_resumes.html" import banner %}{{ banner(r, "") }}').render(r=card)
            with_one = app.jinja_env.from_string('{% from "_resumes.html" import banner %}{{ banner(r, "Step 2") }}').render(r=card)
        self.assertEqual(hashlib.sha256(out.encode()).hexdigest(), "90b26d601ec040eb1625b244e30ddaee4473139bf9253853c9fa06f504a494e3")
        self.assertEqual(with_none, out)
        self.assertEqual(with_one, out.replace('id="resumes-banner">\n', 'id="resumes-banner">\n  <span class="eyebrow">Step 2</span>\n', 1))


# sha256 of the table-mode macro, rendered by the template as it was at the end of A4 (HEAD of A5's start): Results'
# re-rank editor calls weight_editor(skill_weights) and the console review calls it with the commodity list and the badges.
RESULTS_EDITOR = "b200dd0dd866d4698e2eed5e755e9be41bdc978c251d122e6fe77cf4a216df49"
CONSOLE_EDITOR = "aad5e99e2636b5c97249da3c37ff25cb8d24169625e4ae3c69e338ef59dca452"


class ResultsEditorIsByteIdentical(unittest.TestCase):
    def render(self, call):
        app = public_app()
        with app.test_request_context("/"):
            return app.jinja_env.from_string('{% from "_weights.html" import weight_editor %}{{ ' + call + ' }}').render(
                skill_weights=BIG["skill_weights"], commodity=["aws", "git", "linux", "javascript", "sql"],
                importance={"celery": {"label": "Used at work", "css": "core", "why": "WHY-celery"}})

    def test_the_rerank_editor_is_what_it_was(self):
        out = self.render("weight_editor(skill_weights)")
        self.assertEqual(hashlib.sha256(out.encode()).hexdigest(), RESULTS_EDITOR)

    def test_the_console_editor_is_what_it_was(self):
        out = self.render("weight_editor(skill_weights, commodity, importance)")
        self.assertEqual(hashlib.sha256(out.encode()).hexdigest(), CONSOLE_EDITOR)

    def test_tune_false_is_the_default_and_tune_true_is_the_only_new_markup(self):
        plain = self.render("weight_editor(skill_weights, commodity, importance)")
        self.assertEqual(plain, self.render("weight_editor(skill_weights, commodity, importance, tune=false)"))
        self.assertNotIn("tune-", plain)
        self.assertIn('<table class="weights">', plain)
        tuned = self.render("weight_editor(skill_weights, commodity, importance, tune=true)")
        self.assertIn("tune-row", tuned)
        self.assertNotIn('<table class="weights">', tuned)

    def test_results_calls_the_macro_without_tune(self):
        template = (pathlib.Path(app_module.__file__).parent / "templates" / "results.html").read_text()
        self.assertIn("{{ weight_editor(derived.skill_weights) }}", template)
        self.assertNotIn("tune", template)
        review = (pathlib.Path(app_module.__file__).parent / "templates" / "review.html").read_text()
        self.assertEqual(review.count("tune=true"), 1)
        self.assertEqual(review.count("weight_editor(derived.skill_weights, commodity, importance|default({}))"), 1,
                         "the console's call, unchanged")


if __name__ == "__main__":
    unittest.main()
