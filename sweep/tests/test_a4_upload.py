"""Direction A, stage A4: the public Upload screen (`/`) and the public reading screen (`/review` while a résumé is read).

What changed, and only on public pages: a hero (eyebrow, one line that says the trick, one sentence), the add-résumé form as the
screen's one card with three peeks under it (is it free, is it kept, why text PDFs), the brush desk in the rail (server-rendered,
aria-hidden, static without JavaScript; static/desk.js moves it), three steps closing the page, a list of résumés that is no longer
beside a rail, and the working screen's brush mark. What did NOT change: every form contract, the single-résumé path, every
management form, and every byte of the operator console.

The pages are rendered, not read from templates, because "the console is unchanged" and "the desk is on this page and no other" are
claims about what a visitor is sent. Fakes only: no model, provider or network; every app here has a temporary directory.
"""
import html as htmllib
import os
import pathlib
import re
import shutil
import tempfile
import unittest
from unittest import mock

from sweep import app as app_module
from sweep.tests import test_multi_render as r1
from sweep.tests import test_multi_setup as u1
from sweep.tests.test_app import DERIVED
from sweep.tests.test_batch_upload import Batch
from sweep.tests.test_public import PDF, public_app, unlocked, upload
from sweep.tests.test_public_copy import public_screens

setUpModule, tearDownModule = r1.setUpModule, r1.tearDownModule

ROOT = pathlib.Path(app_module.__file__).parent
CSS = (ROOT / "static" / "sweep-a.css").read_text(encoding="utf-8")
BARE = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
TEMPLATES = {p.name: p.read_text(encoding="utf-8") for p in (ROOT / "templates").glob("*.html")}

EYEBROW = '<span class="eyebrow">Step 1 · your résumé</span>'
H1 = '<h1>Messy job boards in. A <span class="hl">tidy shortlist</span> out.</h1>'
LEDE = '<p class="lede">Drop in your résumé. Sweep works out what to look for, then ranks what it finds.</p>'
OLD_H1 = "Find jobs that match your résumé"
PEEKS = [
    ("Is it free?", "Yes", [
        "Reading your résumé spends no credit. Sweep reads it with an AI model to work out what to search for.",
        "A Quick Sweep is free too. A Deep Sweep adds LinkedIn, Indeed and Naukri through your own Apify account, which bills per search. "
        "Apify’s free plan includes $5 in monthly credits, with no card required; actual search usage varies."]),
    ("Is my résumé kept?", "No", [
        "Your résumé is read once to work out what to search for. The PDF itself is never saved, and everything "
        "Sweep read from it is forgotten within two hours."]),
    ("Why only text PDFs?", None, [
        "Sweep reads the words in the file. A scanned image with no text layer has none to read."]),
]
SCAN_SENTENCE = "A scanned image with no text layer will not work."
TRAIL = ('<ol class="trail3" aria-label="What happens next"><li><span class="k">1</span>We read it</li>'
         '<li class="arw" aria-hidden="true">→</li><li><span class="k">2</span>You pick how wide</li>'
         '<li class="arw" aria-hidden="true">→</li><li><span class="k">3</span>We sweep and rank</li></ol>')
# company, title, where, raw score (not a percentage; it can be negative), x, y, rotation, depth, pill
CARDS = [
    ("Kestrel Payments", "Staff Backend Engineer", "Bengaluru", 104, 2, 4, -7, 18, "hi"),
    ("Pebble & Co", "Growth Marketer", "Mumbai", 12, 32, 2, 6, 30, "lo"),
    ("Orrin Health", "Platform Engineer", "Hyderabad", 55, 5, 29, 4, 24, "mid"),
    ("Halden Labs", "Senior Backend Engineer", "Pune", 62, 34, 27, -5, 14, "hi"),
    ("Lumen Bank", "Sales Associate", "Delhi", -3, 2, 54, 7, 28, "lo"),
    ("Brightwell", "Product Engineer", "Bengaluru", 47, 32, 53, -3, 20, "mid"),
    ("Tidepool", "Visual Designer, Ads", "Gurugram", 21, 16, 77, -9, 34, "lo"),
]
NEW_MARKUP = ('class="eyebrow"', 'class="hl"', "data-desk", "desk-fig", "trail3", 'class="peeks"', "desk.js",
              "stack-tight hero", "upload fresh", "upload solo", "jc-pill", "mark_a")


def flat(s):
    return " ".join(s.split())


def main_of(page):
    return page.split("<main", 1)[1].split("</main>", 1)[0]


def peeks(page):
    """[(label, aside, [paragraph, ...])] in page order."""
    out = []
    for m in re.finditer(r'<details class="peek"><summary><span class="peek-label">([^<]*)</span>'
                         r'(?:<span class="peek-aside(?: yes| no)?">([^<]*)</span>)?</summary><div class="peek-body">(.*?)</div></details>',
                         page, re.S):
        out.append((m.group(1), m.group(2), [flat(p) for p in re.findall(r"<p>(.*?)</p>", m.group(3), re.S)]))
    return out


def desk_cards(page):
    out = []
    for m in re.finditer(r'<div class="jc c(\d+)" data-x="(-?\d+)" data-y="(-?\d+)" data-r="(-?\d+)" data-d="(-?\d+)" '
                         r'data-m="(-?\d+)">\s*<div class="jc-co">(.*?)</div>\s*<div class="jc-t">(.*?)</div>\s*'
                         r'<div class="jc-ft"><span class="jc-loc">(.*?)</span><span class="jc-pill (\w+)">(-?\d+)</span></div>',
                         page, re.S):
        n, x, y, r, d, m_, co, title, where, pill, shown = m.groups()
        assert m_ == shown, "the pill must print the raw score"
        out.append((htmllib.unescape(co), htmllib.unescape(title), where, int(m_), int(x), int(y), int(r), int(d), pill, int(n)))
    return out


class Quiet:
    """assertIn that names the needle and never prints a page (a mixin, ahead of unittest.TestCase or Batch)."""

    def assertIn(self, needle, hay, msg=None):
        self.assertTrue(needle in hay, msg or f"missing: {needle!r}")

    def assertNotIn(self, needle, hay, msg=None):
        self.assertTrue(needle not in hay, msg or f"unexpected: {needle!r}")


class Checks(Quiet, unittest.TestCase):
    pass


def hero_and_desk(test, page):
    """The fresh state, whichever way it is reached: hero, desk, trail, peeks. `page` is the whole HTML."""
    body = main_of(page)
    test.assertIn(EYEBROW, body)
    test.assertIn(H1, body)
    test.assertIn(LEDE, body)
    test.assertNotIn(OLD_H1, page)
    test.assertEqual(body.count("<h1"), 1)
    test.assertIn('<div class="stack-tight hero">', body)
    test.assertEqual(peeks(body), PEEKS)
    test.assertEqual(body.count(TRAIL), 1)
    test.assertEqual(body.count('data-desk aria-hidden="true"'), 1)
    test.assertLess(body.index('class="desk-fig"'), body.index(TRAIL))     # the steps close the page
    test.assertLess(body.index("</form>"), body.index('class="peeks"'))    # the peeks follow the form, with its submit
    test.assertNotIn("free-note", body)
    test.assertNotIn("next-steps", body)
    test.assertNotIn("Nothing is kept", body)


# ===========================================================================
class TestTheSingleResumeFrontDoor(Checks):
    """`tracks is none`: the one-résumé product, the primary path. Same form, same POST; only the copy and arrangement change."""

    @classmethod
    def setUpClass(cls):
        cls.page = unlocked(public_app()).get("/").get_data(as_text=True)
        cls.body = main_of(cls.page)

    def test_the_hero_is_an_eyebrow_a_line_with_a_highlight_and_a_sentence(self):
        self.assertIn(EYEBROW + "\n    " + H1 + "\n    " + LEDE, self.body)
        hero_and_desk(self, self.page)
        self.assertNotIn("searches job boards for you, then ranks what it finds", self.page)

    def test_the_three_peeks_say_exactly_this_in_this_order(self):
        self.assertEqual(peeks(self.body), PEEKS)

    def test_the_asides_are_capitalised_sticker_chips_yes_and_no(self):
        """A11 polish: "yes" / "no" were lowercase words; they are chips, "Yes" and "No", each with its own class for its colour."""
        self.assertIn('<span class="peek-aside yes">Yes</span>', self.body)
        self.assertIn('<span class="peek-aside no">No</span>', self.body)
        self.assertNotRegex(self.body, r'peek-aside[^>]*>(yes|no)<')
        self.assertEqual(self.body.count("peek-aside"), 2)                                  # "Why only text PDFs?" has none

    def test_peek_aside_is_a_small_chip_centred_in_its_line_and_never_peach(self):
        rules = {sel: body for sel, body in re.findall(r"\.skin-a \.(peek-aside[\w.]*)\s*\{([^}]*)\}", BARE)}
        self.assertTrue({"peek-aside", "peek-aside.yes", "peek-aside.no"} <= set(rules))
        base = rules["peek-aside"]
        self.assertRegex(base, r"align-self:\s*center")                                     # vertically centred
        self.assertRegex(base, r"border-radius:\s*999px")                                   # a chip
        self.assertRegex(base, r"font:\s*700 12\.5px")                                      # small
        self.assertIn("margin-left: auto", base)
        yes, no = rules["peek-aside.yes"], rules["peek-aside.no"]
        self.assertIn("background: var(--a-cit)", yes)                                      # ink on citrus
        self.assertIn("background: var(--a-lav)", no)                                       # ink on a tint with no peach in it
        both = re.search(r"\.skin-a \.peek-aside\.yes, \.skin-a \.peek-aside\.no \{([^}]*)\}", BARE).group(1)
        self.assertIn("color: var(--a-ink)", both)
        for body in (base, yes, no, both):
            self.assertNotRegex(body, r"--a-pch|--paid|#[0-9A-Fa-f]{3,8}\b|rgba?\(")      # peach is money's; tokens only

    def test_the_peeks_are_native_details_with_no_open_attribute(self):
        self.assertEqual(self.body.count("<details"), 3)
        self.assertNotIn("<details open", self.body)

    def test_the_scan_sentence_left_the_drop_zone_and_the_size_sentence_stayed(self):
        drop = self.body[self.body.index('<label class="drop"'):self.body.index("</label>")]
        self.assertIn('<span class="meta">PDF only, up to 15 MB.</span>', drop)
        self.assertNotIn("scanned", drop)
        self.assertNotIn(SCAN_SENTENCE, self.page)
        self.assertEqual(self.page.count("A scanned image with no text layer"), 1)   # only the peek, in its own words

    def test_the_form_contract_is_exactly_as_it_was(self):
        form = self.body[self.body.index('<form class="upload-form"'):self.body.index("</form>")]
        # data-going: "Read my résumé" opens the reading splash (going.js) rather than the painted line.
        self.assertIn('<form class="upload-form" method="post" action="/resume" data-going="splash"\n              enctype="multipart/form-data"', form)
        self.assertIn('<input type="file" name="resume" accept="application/pdf"\n                   x-ref="picker" @change="take()">', form)
        self.assertNotIn("multiple", form)
        for binding in ('x-data="{ sent: false, over: false, file: null, bad: \'\'', "take() {", "drop(e) {",
                        '@submit="sent = true"', '<label class="drop" :class="{ over: over }"', 'x-show="!file"',
                        '@dragover.prevent="over = true"', '@dragleave.prevent="over = false"', '@drop.prevent="drop($event)"',
                        '<p class="error" x-show="bad" x-cloak x-text="bad" role="alert"></p>',
                        'class="primary" type="submit" :disabled="sent">Read my résumé</button>',
                        '@click="$refs.picker.click()">Replace file</button>'):
            self.assertIn(binding, form)
        self.assertEqual(self.body.count('type="file"'), 1)
        self.assertEqual(len(re.findall(r'class="primary[^"]*"', self.body)), 1)
        self.assertNotIn("sweepPicker", self.page)
        self.assertNotIn("pick.js", self.page)

    def test_a_single_visitor_has_no_empty_note_beside_the_button(self):
        self.assertNotIn("upload-note", self.body)         # the free-note was all it held

    def test_the_landmarks_and_the_skip_link_are_kept(self):
        self.assertIn('<a class="skip-link" href="#main-content">Skip to main content</a>', self.page)
        self.assertIn('<a id="main-content"></a>\n  <main>', self.page)
        self.assertIn('<aside class="aside rail" aria-label="What to expect">', self.body)

    def test_the_desk_is_illustration_with_seven_cards_and_the_brush(self):
        self.assertEqual(self.body.count('class="desk" data-desk aria-hidden="true"'), 1)
        found = desk_cards(self.body)
        self.assertEqual([c[:9] for c in found], CARDS)
        for i, (co, title, where, score, x, y, r, d, pill, n) in enumerate(found, 1):
            # Each card rests where its c<n> class puts it (no Jinja inside a style attribute: test_app), and that place is
            # exactly the data-* numbers desk.js reads, so the page without a script and the page with one agree.
            self.assertEqual(n, i)
            rule = re.search(rf"\.skin-a \.desk \.jc\.c{n} \{{([^}}]*)\}}", CSS).group(1).strip()
            self.assertEqual(rule, f"left: {x}%; top: {y}%; z-index: {d}; transform: rotate({r}deg);")
            self.assertEqual(pill, "hi" if score >= 60 else "mid" if score >= 40 else "lo")
        self.assertEqual(sum(1 for c in found if c[3] >= 40), 4)          # the strong ones
        self.assertIn('<span class="sl-ct" data-desk-count>0 / 4</span>', self.body)
        self.assertIn("<span>Your shortlist</span>", self.body)
        self.assertIn('<p class="sl-empty" data-desk-empty>Brush the desk. <span>Best matches land here, ranked.</span></p>', self.body)
        self.assertIn('<p class="sl-foot" data-desk-weak hidden></p>', self.body)
        self.assertIn('<polyline data-desk-trail points=""/>', self.body)
        self.assertIn('<div class="brush" data-desk-brush>', self.body)
        # the desk is a picture: nothing inside it can be reached, so there is no control, link or heading in it
        desk = self.body[self.body.index('class="desk" data-desk'):self.body.index("<figcaption")]
        for control in ("<button", "<a ", "<input", "tabindex", "<h2", "<h3"):
            self.assertNotIn(control, desk)

    def test_the_buttons_are_the_way_in_and_ship_hidden(self):
        self.assertIn('<figcaption class="fig-bar">\n    <p>Try it: drag the brush. Good matches stay, weak ones get swept.</p>', self.body)
        self.assertIn('<button type="button" class="secondary" data-desk-sweep hidden>Sweep it for me</button>', self.body)
        self.assertIn('<button type="button" class="tertiary" data-desk-reset hidden>Start over</button>', self.body)
        caption = self.body[self.body.index("<figcaption"):self.body.index("</figcaption>")]
        self.assertNotIn("aria-hidden", caption)             # outside the desk, so a screen reader finds them

    def test_the_script_is_deferred_and_loaded_once_here(self):
        self.assertEqual(self.page.count('<script defer src="/static/desk.js"></script>'), 1)
        self.assertEqual(self.page.count("desk.js"), 1)
        self.assertTrue((ROOT / "static" / "desk.js").is_file())


# ===========================================================================
class TestThePressThatLeaves(Checks):
    """going.css / going.js: the painted line on every public page, the reading splash on Upload only, none of it on the console."""

    def test_every_public_page_carries_the_line_and_upload_alone_the_splash(self):
        client = unlocked(public_app())
        for path, splash in (("/", True), ("/privacy", False)):
            page = client.get(path).get_data(as_text=True)
            with self.subTest(path=path):
                self.assertIn("going.js", page)
                self.assertEqual(page.count("data-going-line"), 1)
                self.assertEqual("data-going-splash" in page, splash)
                self.assertEqual('data-going="splash"' in page, splash)

    def test_the_console_has_none_of_it(self):
        page = TestTheConsoleIsUntouched.local(self, {})
        for token in ("going.js", "going.css", "data-going"):
            self.assertNotIn(token, page)


class TestTheSpeakerSwitch(Checks):
    """sound.js: a speaker switch in every public header, hidden until the script finds it (so never a dead control), and
    the two forms that end in a moment say which; the console has none of it."""

    def test_public_pages_carry_the_switch_and_the_script(self):
        page = unlocked(public_app()).get("/").get_data(as_text=True)
        self.assertIn("sound.js", page)
        self.assertIn('<button type="button" class="sound-toggle" data-sound-toggle aria-pressed="false" hidden>', page)
        self.assertLess(page.index("data-sound-toggle"), page.index("data-theme-toggle"))

    def test_the_console_has_none_of_it(self):
        page = TestTheConsoleIsUntouched.local(self, {})
        for token in ("sound.js", "data-sound"):
            self.assertNotIn(token, page)


class TestTheReadSummaryAfterAnUpload(Checks):
    """The same front door once a résumé has been read: `tracks` is still none, so the hero and the desk stay, and the one
    block the rail kept ("What Sweep read last time") shows because it has something to say."""

    @classmethod
    def setUpClass(cls):
        cm = public_screens(free=True)
        cls.pages = cm.__enter__()
        cls.cm = cm

    @classmethod
    def tearDownClass(cls):
        cls.cm.__exit__(None, None, None)

    def test_the_front_door_after_an_upload(self):
        page = self.pages["/"]
        hero_and_desk(self, page)
        body = main_of(page)
        self.assertEqual(body.count('class="rail-block"'), 1)
        self.assertIn('<h2 class="rail-title">What Sweep read last time</h2>', body)
        self.assertIn("Uploading a new résumé replaces", flat(body))
        for label in ("Job titles to search", "Skills found", "Experience"):
            self.assertIn(f"<dt>{label}</dt>", body)
        self.assertLess(body.index("data-desk-brush"), body.index("What Sweep read last time"))   # the desk leads the rail

    def test_no_other_public_screen_has_the_desk_or_the_script(self):
        for path, page in self.pages.items():
            if path == "/":
                continue
            with self.subTest(path=path):
                for needle in ("desk.js", "data-desk", "desk-fig", "trail3"):
                    self.assertNotIn(needle, page)
                # A5: the Review screen opens with the same eyebrow ("Step 2 · profile check"); A6: so does Search ("Step 3 ·
                # coverage"); A7: and Configure (this walk is the free path: "Step 3 · Quick Sweep"); A8: and Progress ("Step 3 · Quick
                # Sweep", the free path again); no other screen has one.
                if path == "/review":
                    self.assertEqual(page.count('class="eyebrow"'), 1)
                    self.assertIn('<span class="eyebrow">Step 2 · profile check</span>', page)
                elif path == "/key":
                    self.assertEqual(page.count('class="eyebrow"'), 1)
                    self.assertIn('<span class="eyebrow">Step 3 · coverage</span>', page)
                elif path in ("/configure", "/confirm"):         # T2: "/confirm" is followed to the plan screen, which is /configure
                    self.assertEqual(page.count('class="eyebrow"'), 1)
                    self.assertIn('<span class="eyebrow">Step 3 · Quick Sweep</span>', page)
                elif path == "/running":
                    self.assertEqual(page.count('class="eyebrow"'), 1)
                    self.assertIn('<span class="eyebrow">Step 3 · Quick Sweep</span>', page)
                elif path == "/results":                     # A9: and Results ("Step 4 · your jobs")
                    self.assertEqual(page.count('class="eyebrow"'), 1)
                    self.assertIn('<span class="eyebrow">Step 4 · your jobs</span>', page)
                else:
                    self.assertNotIn('class="eyebrow"', page)

    def test_the_script_is_in_one_template_and_only_a_fresh_upload_includes_it(self):
        self.assertEqual([n for n, t in TEMPLATES.items() if "desk.js" in t], ["_desk.html"])
        self.assertEqual([n for n, t in TEMPLATES.items() if "_desk.html" in t], ["upload.html"])
        self.assertIn('{%- if fresh %}\n      {% include "_desk.html" %}', TEMPLATES["upload.html"])
        self.assertIn("{%- set fresh = public_mode and not tracks %}", TEMPLATES["upload.html"])


# ===========================================================================
class TestTheSetupFrontDoor(Quiet, Batch):
    """The 1-3 résumé setup, nothing added yet (`tracks == []`): the same hero and desk, with the picker."""

    def test_fresh_has_the_hero_the_desk_the_trail_and_the_peeks(self):
        page = self.page()
        hero_and_desk(self, page)
        self.assertIn('class="split upload fresh"', page)

    def test_the_picker_contract_is_kept_and_the_count_note_stays(self):
        body = main_of(self.page())
        for keep in ('x-data="sweepPicker(3, 15)"', "<script src=\"/static/pick.js\"></script>", " multiple", "x-ref=\"picker\"",
                     "x-show=\"files.length < room\"", "@click=\"remove(files.indexOf(f))\"", ":aria-label=\"'Remove ' + f.name\"",
                     'x-text="size(f)"', ':disabled="sent"', '<h3>Selected résumés</h3>', 'class="picked-row"'):
            self.assertIn(keep, body)
        # the note beside the button keeps the count; the free-note is a peek now
        self.assertIn('<div class="upload-note">', body)
        self.assertIn("files.length + ' of ' + room + ' selected.'", body)
        self.assertNotIn("free-note", body)

    def test_the_drop_zone_still_names_the_limit(self):
        body = flat(main_of(self.page()))
        self.assertIn("PDFs only, up to 15 MB in total.", body)
        self.assertNotIn(SCAN_SENTENCE, body)


# ===========================================================================
class TestTheListOfResumes(Quiet, Batch):
    """Résumés exist: the management view. The desk is the whole rail (owner, 2026-10-03: the wide screen was half empty
    on coming back); no trail, no hero, no other rail block; every form and action is kept."""

    def test_the_desk_alone_in_the_rail_and_no_trail_no_hero(self):
        self.send("ada", "bhaskar")
        page = self.page()
        body = main_of(page)
        for needle in ("trail3", 'class="eyebrow"', 'class="hl"', "rail-block", "What happens next", "stack-tight hero",
                       "upload fresh"):
            self.assertNotIn(needle, page)
        self.assertEqual(body.count('<aside class="aside rail" aria-label="How Sweep ranks">'), 1)
        self.assertEqual(body.count('class="desk" data-desk aria-hidden="true"'), 1)
        self.assertIn("desk.js", page)
        self.assertIn('data-desk-sweep hidden>Sweep it for me</button>', body)
        self.assertIn("<h1>Your résumés</h1>", body)
        self.assertIn('class="split upload solo"', body)
        self.assertIn('<p class="lede">2 of 3 added. Sweep searches\n      for every résumé that is in this search, in the order below, together.</p>', body)

    def test_every_management_form_and_action_is_kept(self):
        self.send("ada", "bhaskar")
        body = main_of(self.page())
        self.assertIn('<ol class="ledger manage" aria-label="Your résumés, in the order they are searched">', body)
        self.assertEqual(body.count('<li class="resume"'), 2)
        for do in ("rename", "deselect", "down", "up", "remove"):
            self.assertTrue(re.search(rf'name="do"\s+value="{do}"', body), f"no {do} button")
        for word in ("Rename", "Leave out", "Move down", "Move up", "Remove"):
            self.assertIn(f">{word}<span", body)
        self.assertIn('action="/tracks"', body)
        self.assertEqual(body.count('class="row-actions"'), 2)
        for group in ("a-main", "a-state", "a-arrange", "a-danger"):
            self.assertIn(f'<span class="{group}">', body)
        self.assertIn('<span class="status waiting">Not read yet</span>', body)
        # the one add form is still here, as the card, with its peeks and without a free-note
        self.assertIn('<div class="add after">', body)
        self.assertEqual(peeks(body), PEEKS)
        self.assertNotIn("free-note", body)
        self.assertIn("<h2>Add another résumé</h2>", body)           # one place left: the one-file picker
        self.assertNotIn(" multiple", body)

    def test_the_add_form_keeps_the_picker_that_fits_what_is_left(self):
        self.send("ada")
        body = main_of(self.page())
        self.assertIn('x-data="sweepPicker(2, 15)"', body)
        self.assertIn(" multiple", body)
        self.assertIn("<h2>Add up to 2 more résumés</h2>", body)
        self.assertEqual(peeks(body), PEEKS)
        self.assertIn('<div class="upload-note">', body)          # the count note, for the batch picker

    def test_review_and_edit_links_and_the_way_on(self):
        a = self.add("ada")
        b = self.add("bhaskar")
        body = main_of(self.page())
        self.assertTrue(re.search(rf'<a class="tertiary" href="/review\?track={a}">Edit', body))
        self.assertTrue(re.search(rf'<a class="tertiary" href="/review\?track={b}">Edit', body))
        self.assertIn('<a class="primary" href="/key">Continue to job search<span\n                class="go" aria-hidden="true">&rarr;</span></a>', body)
        self.assertNotIn("To search, include at least one résumé", body)
        # adding another is the outline beside Continue, so the page still has one primary
        self.assertEqual(len(re.findall(r'class="primary[^"]*"', body)), 1)

    def test_not_ready_says_what_is_missing_and_review_is_the_outline(self):
        self.send("ada")
        body = main_of(self.page())
        self.assertTrue(re.search(r'<a class="secondary" href="/review\?track=\w+">Review', body))
        self.assertIn("To search, include at least one résumé and review every", flat(body))
        self.assertNotIn("Continue to job search", body)

    def test_a_full_list_has_no_add_form_and_no_peeks(self):
        self.send("ada", "bhaskar", "chen")
        body = main_of(self.page())
        self.assertIn("A search takes up to 3 résumés. Remove one to add another.", flat(body))
        self.assertNotIn("peek", body)
        self.assertNotIn('type="file"', body)


# ===========================================================================
class TestTheReadingScreen(Checks):
    """/review while the résumé is still being read: the public page gets the brush mark, the console keeps its own."""

    def public(self):
        client = unlocked(public_app())
        upload(client)
        r = client.get("/review")
        self.assertEqual(r.status_code, 200)
        return r.get_data(as_text=True)

    def test_public_uses_the_brush_mark_at_56(self):
        page = self.public()
        self.assertIn('<svg class="mark" width="56" height="56" viewBox="0 0 36 36"', page)
        self.assertIn('fill="var(--a-lav)"', main_of(page))
        self.assertNotIn('viewBox="0 0 32 32"', main_of(page))

    def test_no_copy_changed_on_the_reading_screen(self):
        body = main_of(self.public())
        for line in ("<h1>Reading your résumé</h1>", "Sweep is turning your résumé into a search profile",
                     "No scraping credit is spent\n    reading it.", '<div class="activity live">', "<b>Working</b>",
                     '<span class="activity-count">reading your document</span>', '<div class="working-bar"><span></span></div>',
                     "What Sweep is preparing", "Your profile", "You do not need to refresh this page",
                     'id="derive-now" method="post" action="/derive"'):
            self.assertIn(line, body)

    def test_the_wiggle_is_for_the_working_screen_only_and_waits_for_no_preference(self):
        i = BARE.index(".skin-a .working:has(.activity) > .mark")
        self.assertIn("animation: a-bob", BARE[i:i + 160])
        enclosing = BARE[:i].rsplit("@media", 1)[-1]
        self.assertTrue(enclosing.startswith(" (prefers-reduced-motion: no-preference)"), enclosing[:60])
        # the error screen has no .activity row, so the rule cannot match it
        self.assertIn("{% if not error %}", TEMPLATES["deriving.html"])


# ===========================================================================
class TestTheConsoleIsUntouched(Checks):
    """Local mode renders none of A4. (The byte-for-byte comparison against HEAD is in the stage record; this is what stays true.)"""

    def local(self, state, path="/"):
        tmp = tempfile.mkdtemp(prefix="a4-console-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        os.mkdir(os.path.join(tmp, "profiles"))
        with mock.patch.object(app_module, "REPO_ROOT", tmp):      # GET only, and nothing it could write is the repo's
            app = app_module.create_app(
                state=state, derive=lambda text, prefs: dict(DERIVED), read_rows=lambda profile: [],
                list_sweeps=lambda profile: [], resume_dir=os.path.join(tmp, "resume"),
                env_path=os.path.join(tmp, "none.env"), output_dir=os.path.join(tmp, "out"))
            app.config["TESTING"] = True
            return app.test_client().get(path).get_data(as_text=True)

    def test_console_upload_has_none_of_the_new_markup(self):
        for state in ({}, {"resume_text": "x", "derived": dict(DERIVED), "profile": "kartik", "cap_usd": 4.25,
                                  "credit_total_usd": 4.25}):
            page = self.local(state)
            for needle in NEW_MARKUP + ("skin-a", "sweep-a.css", "peek", "Step 1", "Messy job boards"):
                with self.subTest(state=bool(state), needle=needle):
                    self.assertNotIn(needle, page)

    def test_console_upload_keeps_its_own_words(self):
        page = flat(self.local({}))
        self.assertIn("<h1>Sweep</h1>", page)
        self.assertIn("Job search you can meter.", page)
        self.assertIn('<p class="free-note"><b>Nothing is charged yet.</b>', page)
        self.assertIn(f'<span class="meta">PDF only, up to 15 MB. {SCAN_SENTENCE}</span>', page)
        self.assertIn('<div class="upload-note">', page)
        self.assertEqual(page.count('class="rail-block"'), 5)    # what the model reads out, and the four notes
        for line in ("What happens next", '<h2 class="label free">Free</h2>', '<h2 class="label paid">Paid, and optional</h2>',
                     "Runs on this machine", "You check the titles and skill weights it derived"):
            self.assertIn(line, page)

    def test_console_reading_screen_keeps_the_quiet_ledger_mark(self):
        page = self.local({"resume_text": "x", "derived": None}, "/review")
        self.assertIn('<svg class="mark" width="56" height="56" viewBox="0 0 32 32"', page)
        self.assertNotIn("--a-lav", main_of(page))
        self.assertNotIn("skin-a", page)


# ===========================================================================
class TestTheStylesheet(Checks):
    """A few pins on the A4 section of sweep-a.css: what must hold for the page to look and behave as designed."""

    SECTION = re.sub(r"/\*.*?\*/", "", CSS[CSS.index("==== A4"):], flags=re.S)

    def rule(self, selector):
        for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", self.SECTION):
            if m.group(1).strip() == selector:
                return m.group(2)
        self.fail("no rule for " + selector)

    def test_buttons_that_ship_hidden_stay_hidden_despite_display_inline_flex(self):
        self.assertIn("display: none", self.rule(".skin-a .desk-fig [hidden]"))

    def test_the_brush_cursor_exists_only_while_the_script_runs(self):
        self.assertIn("cursor: none", self.rule(".skin-a .desk.desk-live"))
        self.assertEqual(len(re.findall(r"cursor:\s*none", self.SECTION)), 1)
        self.assertNotIn("cursor", self.rule(".skin-a .desk"))

    def test_the_desk_lets_the_page_scroll_on_a_phone(self):
        self.assertIn("touch-action: pan-y", self.rule(".skin-a .desk"))
        self.assertIn("height: 540px", self.rule(".skin-a .desk"))
        self.assertIn(".skin-a .desk { height: 480px; border-radius: 22px; }", self.SECTION)

    def test_pill_colours_follow_the_score_bands_in_tokens(self):
        self.assertIn("background: var(--a-cit)", self.rule(".skin-a .jc-pill.hi"))
        self.assertIn("background: var(--a-lav)", self.rule(".skin-a .jc-pill.mid"))
        self.assertIn("background: var(--a-pch)", self.rule(".skin-a .jc-pill.lo"))
        self.assertIn("color: var(--a-ink)", self.rule(".skin-a .jc-pill"))

    def test_the_shortlist_is_the_inverse_of_the_desk(self):
        body = self.rule(".skin-a .shortlist")
        self.assertIn("background: var(--chalk)", body)
        self.assertIn("color: var(--ground)", body)
        self.assertIn("border-radius: 22px", body)

    def test_everything_that_moves_is_in_no_preference(self):
        moving = re.compile(r"(?<![\w-])(animation|transition)(?:-[\w-]+)?\s*:\s*([^;}]*)")
        seen = 0
        for m in moving.finditer(self.SECTION):
            if m.group(2).strip() == "none":
                continue
            seen += 1
            before = self.SECTION[:m.start()]
            self.assertGreater(before.rfind("@media (prefers-reduced-motion: no-preference)"), before.rfind("\n}\n"),
                               m.group(0)[:60])
        self.assertGreaterEqual(seen, 6)

    def test_the_phone_grid_areas_are_not_touched_here(self):
        self.assertNotIn("grid-template-areas", BARE)
        self.assertIn(".skin-a .ledger.manage > li.resume { grid-template-columns: 2.5rem minmax(0, 1fr); }", self.SECTION)

    def test_a_list_row_is_a_sticker_card_with_a_big_numeral_and_a_status_pill(self):
        card = self.rule(".skin-a .ledger.manage > li.resume")
        for part in ("background: var(--surface)", "border: 2px solid var(--a-line)", "border-radius: 22px",
                     "box-shadow: 4px 4px 0 var(--a-shadow)", "padding: 18px"):
            self.assertIn(part, card)
        self.assertIn("gap: 14px", self.rule(".skin-a .ledger.manage"))
        self.assertIn("font: 800 28px/1 var(--display)", self.rule(".skin-a .ledger.manage .resume-head .rank"))
        status = self.rule(".skin-a .ledger.manage .resume .status")
        for part in ("padding: 2px 10px", "border-radius: 999px", "border: 1.5px solid var(--control)"):
            self.assertIn(part, status)

    def test_the_add_card_and_the_drop_zone_are_the_decided_shape(self):
        card = self.rule(".skin-a .add, .skin-a .add.after")
        for part in ("background: var(--surface)", "border: 2px solid var(--a-line)", "border-radius: 26px",
                     "padding: 24px", "box-shadow: 8px 8px 0 var(--a-shadow)"):
            self.assertIn(part, card)
        drop = self.rule(".skin-a .drop")
        for part in ("border: 2px dashed var(--a-line)", "border-radius: 20px", "background: var(--well)"):
            self.assertIn(part, drop)
        self.assertIn("background: var(--a-tint)", self.rule(".skin-a .drop:hover, .skin-a .drop.over"))
        row = self.rule(".skin-a .picked-row")
        for part in ("border-radius: 14px", "background: var(--a-tint)", "1.5px solid var(--a-lav)"):
            self.assertIn(part, row)

    def test_the_hero_and_the_highlight(self):
        self.assertIn("font-size: clamp(40px, 5.4vw, 72px)", self.rule(".skin-a .hero h1"))
        hl = self.rule(".skin-a .hl")
        for part in ("background: var(--a-lav)", "color: var(--a-ink)", "border-radius: 12px", "padding: 0 .12em",
                     "box-decoration-break: clone"):
            self.assertIn(part, hl)
        eyebrow = self.rule(".skin-a .eyebrow")
        for part in ("background: var(--a-cit)", "color: var(--a-ink)", "2px solid var(--a-ink)", "font-size: 12.5px",
                     "letter-spacing: .05em", "rotate(-2deg)"):
            self.assertIn(part, eyebrow)


if __name__ == "__main__":
    unittest.main()
