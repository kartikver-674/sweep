"""Direction A, stage A6: the public Search coverage screen (/key).

THE CONTRACT (A6 changes none of it). The visitor's Apify key is the one credential this product protects, so what the page may
do with it is pinned here: the Deep form posts the one `token` field (a password input with no `value`) to /key, the privacy
sentence stays visible beside it, a refused key is never echoed back, and the Quick Sweep form (a real submit button INSIDE
form[action=/key/free]) still posts to key_free. The two radios that choose between them are in neither form and are never sent.

Around it: the new words and parts (eyebrow, headline, lede, two radio cards, the coverage diagram with one outer chip per paid
board, the Quick / Deep call to action, the "Does Deep Sweep cost money?" peek holding the three A3 paragraphs in their order, the
three-step setup, one tip), "no script, nothing hidden" (the closed parts are hidden only under `.skin-a.js`), a refused key
reopening the paste step, and the operator's console untouched. Fakes only: the loopback worker the public suites use and a
stubbed Apify check; no network, no model, no real token.
"""
import hashlib
import pathlib
import re
import unittest
from html.parser import HTMLParser
from unittest import mock

from sweep import app as app_module
from sweep.logic import paid_sites, site_label
from sweep.tests.test_a3_copy import APIFY_KEY, console_pages
from sweep.tests.test_public_paid import VISITOR_KEY, apify
from sweep.tests.test_public_sweep import reviewed, stack
from sweep.tests.test_worker_link import render_app

ROOT = pathlib.Path(app_module.__file__).parent
TEMPLATE = (ROOT / "templates" / "key.html").read_text()
CSS = (ROOT / "static" / "sweep-a.css").read_text()
A6_CSS = re.sub(r"/\*.*?\*/", "", CSS[CSS.rindex("/*", 0, CSS.index("==== A6: Search coverage")):CSS.rindex("/*", 0, CSS.index("==== A7: Configure and Confirm"))], flags=re.S)   # this stage's section, comments out

REJECTED = "That token was rejected by Apify. Check and retry."
PAID = [site_label(s) for s in paid_sites()]          # what the page must name: from the engine's own table, never typed
JOINED = ", ".join(PAID)


def flat(text):
    return " ".join(text.split())


# ---- a small DOM: enough to ask "is this inside that" ------------------------------------------------------------------
VOID = {"input", "img", "br", "hr", "meta", "link", "source", "wbr"}


class Node:
    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.parent, self.kids = tag, dict(attrs), parent, []

    def walk(self):
        yield self
        for k in self.kids:
            if isinstance(k, Node):
                yield from k.walk()

    def text(self):
        return flat("".join(k if isinstance(k, str) else k.text() for k in self.kids))

    def classes(self):
        return (self.attrs.get("class") or "").split()

    def within(self, tag=None, cls=None):
        n = self.parent
        while n is not None:
            if (tag is None or n.tag == tag) and (cls is None or cls in n.classes()):
                return n
            n = n.parent
        return None

    def find(self, tag=None, cls=None, **attrs):
        return [n for n in self.walk() if n is not self and (tag is None or n.tag == tag) and (cls is None or cls in n.classes())
                and all(n.attrs.get(k.replace("_", "-")) == v for k, v in attrs.items())]

    def one(self, tag=None, cls=None, **attrs):
        found = self.find(tag, cls, **attrs)
        assert len(found) == 1, f"{len(found)} of {tag}.{cls} {attrs}"
        return found[0]


class Dom(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.root = self.cur = Node("#root", {}, None)
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.cur)
        self.cur.kids.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.kids.append(data)


def main_of(body):
    return Dom(body[body.index("<main>"):body.index("</main>")]).root


def key_page(guide=None):
    """GET /key for a visitor who has just reviewed their profile: (the raw body, the DOM of <main>)."""
    with stack() as (url, _store):
        app = render_app(url, check_token=lambda t: (4.25, None))
        if guide is not None:
            app.config["APIFY_GUIDE"] = guide
        client = reviewed(app)
        response = client.get("/key")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
    return body, main_of(body)


def refused_page(token="not-a-real-token-xyz"):
    """POST /key with a token Apify refuses: (status, body, DOM of <main>)."""
    with stack() as (url, store):
        with apify(None, REJECTED) as (_seen, check):
            app = render_app(url, check_token=check)
            client = reviewed(app)
            response = client.post("/key", data={"token": token})
            body = response.get_data(as_text=True)
            assert store.all() == []
    return response.status_code, body, main_of(body)


class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body, cls.main = key_page()

    def section(self, cls):
        return self.main.one(cls=cls)


class TestTheWords(Page):
    def test_eyebrow_headline_and_lede(self):
        top = self.main.one(cls="cov-top")
        self.assertEqual(top.one(cls="eyebrow").text(), "Step 3 · coverage")
        h1 = top.one("h1")
        self.assertEqual(h1.text(), "How wide should we sweep?")
        self.assertEqual(h1.one(cls="scrib").text(), "sweep")
        self.assertEqual(top.one(cls="lede").text(), f"Same ranking either way. Deep Sweep adds {JOINED}.")

    def test_the_boards_are_the_engines_not_typed(self):
        """The names are joined from paid_sites(): patch the table to one board and every mention follows."""
        with mock.patch.object(app_module, "paid_sites", lambda: ["linkedin"]):
            _body, main = key_page()
        text = main.text()
        self.assertEqual(main.one(cls="lede").text(), "Same ranking either way. Deep Sweep adds LinkedIn.")
        for where in ("cov-choose", "cov-side"):             # the choice's diagram and the one beside the setup
            self.assertEqual([c.text() for c in main.one(cls=where).find(cls="o-chip") if "out" in c.classes()], ["LinkedIn"])
        self.assertIn("+1 big boards", text)
        self.assertNotIn("Naukri", text)
        self.assertNotIn("Indeed", text)

    def test_the_cards(self):
        quick, deep = self.main.one(cls="q"), self.main.one(cls="d")
        self.assertEqual(quick.one(cls="nm").text(), "Quick Sweep")
        self.assertEqual(quick.one(cls="ds").text(), "Company career pages and public job boards. Free, no setup.")
        self.assertEqual(deep.one(cls="nm").text(), "Deep Sweep")
        self.assertEqual(deep.one(cls="ds").text(), f"Everything in Quick, plus {JOINED} — on your own free Apify account.")
        sticker = deep.one(cls="sticker")
        self.assertEqual(sticker.text(), f"+{len(PAID)} big boards")
        self.assertEqual(sticker.attrs.get("aria-hidden"), "true")
        self.assertEqual(sticker.classes(), ["sticker", "cit"])      # pre-merge polish: citrus with ink, not peach (peach is money's; this is not a price)
        self.assertEqual(quick.find(cls="sticker"), [])

    def test_no_count_of_sources_anywhere(self):
        """The free-board count is not known on this screen, so the page states none (the sticker counts the paid boards only)."""
        text = self.main.text()
        self.assertNotRegex(text, r"\d+\s+(?:free\s+|job\s+|public\s+)*(?:sources|boards)\b")
        self.assertNotRegex(text, r"\bsources\b")
        for stale in ("133", "136"):
            self.assertNotIn(stale, self.body)

    def test_no_stale_copy_from_the_old_page(self):
        for gone in ("How should Sweep search?", "Recommended", "No account or API key needed", "Nothing to pay", "Don't have an Apify key yet?",
                     "Create a free Apify account", "Open your API token page", "Copy your Personal API token"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, self.main.text())
        self.assertEqual(self.main.find("details", "disclosure"), [])
        self.assertEqual(self.main.find("details", "howto"), [])


class TestTheChoice(Page):
    def test_two_radios_outside_both_forms(self):
        radios = self.main.find("input", type="radio")
        self.assertEqual([(r.attrs["name"], r.attrs["value"]) for r in radios], [("sweep-mode", "quick"), ("sweep-mode", "deep")])
        for radio in radios:
            self.assertIsNone(radio.within("form"), "a radio inside a form would be submitted")
        group = radios[0].within("fieldset")
        self.assertIs(group, radios[1].within("fieldset"))
        legend = group.one("legend")
        self.assertEqual(legend.text(), "Choose a sweep")
        self.assertIn("visually-hidden", legend.classes())
        self.assertIn("checked", radios[0].attrs)
        self.assertNotIn("checked", radios[1].attrs)
        self.assertEqual([r.attrs.get("x-model") for r in radios], ["mode", "mode"])

    def test_the_radios_are_the_only_inputs_outside_a_form(self):
        loose = [i for i in self.main.find("input") if i.within("form") is None]
        self.assertEqual({i.attrs["type"] for i in loose}, {"radio"})

    def test_the_scope(self):
        scope = self.section("cov-page")
        self.assertEqual(scope.attrs["x-data"], "{ mode: 'quick', setup: false, step: 1 }")
        # the choice and the setup are both inside it, so one `mode` / `setup` / `step` drives both
        self.assertEqual(len(scope.find("section")), 2)

    def test_the_quick_submit_is_inside_the_quick_form(self):
        forms = [f for f in self.main.find("form") if f.attrs["action"].endswith("/key/free")]
        self.assertEqual(len(forms), 1)
        form = forms[0]
        self.assertEqual(form.attrs["method"], "post")
        buttons = form.find("button")
        self.assertEqual(len(buttons), 1)
        button = buttons[0]
        self.assertEqual((button.attrs["type"], button.text()), ("submit", "Start Quick Sweep→"))
        self.assertEqual(button.attrs[":disabled"], "sent")
        self.assertEqual({"primary", "big"} - set(button.classes()), set())
        self.assertEqual(form.attrs["x-data"], "{ sent: false }")
        self.assertEqual(form.attrs["@submit"], "sent = true")
        self.assertEqual(form.one(cls="sending").text(), "Setting up your search…")
        self.assertEqual(form.find("input"), [])

    def test_the_set_up_button_is_a_button_not_a_form_and_opens_the_setup_at_step_one(self):
        button = self.main.one(cls="cov-deepgo")
        self.assertEqual((button.tag, button.attrs["type"]), ("button", "button"))
        self.assertIsNone(button.within("form"))
        self.assertEqual(button.text(), "Set up Deep Sweep→")
        self.assertEqual({"primary", "big"} - set(button.classes()), set())
        self.assertIn("setup = true", button.attrs["@click"])
        self.assertIn("step = 1", button.attrs["@click"])
        self.assertIn("$refs.setuph.focus()", button.attrs["@click"])
        self.assertEqual(button.attrs["aria-controls"], "deep-setup")

    def test_the_peek_holds_the_three_paragraphs_in_the_a3_order(self):
        peeks = [p for p in self.main.find("details", "peek") if p.one(cls="peek-label").text() == "Does Deep Sweep cost money?"]
        self.assertEqual(len(peeks), 1)
        peek = peeks[0]
        self.assertNotIn("open", peek.attrs)
        paragraphs = peek.one(cls="peek-body").find("p")
        self.assertEqual([p.text() for p in paragraphs], [
            f"Sweep can also search {JOINED}. Those boards are read through Apify, a service that runs the searches for you and charges per search.",
            APIFY_KEY,
            "Sweep uses your own Apify account, so the searches are billed to you and never to us. You will see the estimated cost "
            "before anything runs, and nothing is charged until you start the sweep."])
        self.assertEqual(paragraphs[0].find("b")[0].text(), "Apify")
        self.assertEqual(paragraphs[1].classes(), [])
        self.assertEqual(paragraphs[2].classes(), ["muted"])
        self.assertEqual(paragraphs[2].find("b")[0].text(), "your own")
        # a bare "<p>" + sentence + "</p>", as test_a3_copy has always pinned it
        self.assertIn("<p>" + APIFY_KEY + "</p>", flat(self.body))

    def test_the_peek_sits_after_the_call_to_action_and_before_the_setup(self):
        order = [n for n in self.section("cov-page").walk()
                 if "cov-cta" in n.classes() or "peek" in n.classes() or "cov-setup" in n.classes()]
        self.assertEqual([n.classes()[0] for n in order], ["cov-cta", "peek", "cov-setup"])


class TestTheDiagram(Page):
    def box(self):
        return self.section("cov-choose").one(cls="orbit-box")        # the choice's diagram (the setup has a second drawing: TestTheSetupDiagram)

    def test_it_is_decoration_with_a_live_sentence_beside_it(self):
        box = self.box()
        self.assertEqual(box.attrs["aria-hidden"], "true")
        self.assertEqual(box.attrs[":class"], "{ 'is-deep': mode === 'deep' }")
        self.assertNotIn("is-deep", box.classes())
        live = [n for n in self.main.find("span", "visually-hidden") if n.attrs.get("aria-live") == "polite"]
        self.assertEqual(len(live), 1)
        self.assertIsNone(live[0].within(cls="orbit-box"), "a live region inside aria-hidden is never announced")
        self.assertIn("x-text", live[0].attrs)
        self.assertEqual(live[0].text(), "Quick Sweep searches company career pages and public job boards.")
        self.assertIn(f"Deep Sweep searches company career pages and public job boards, plus {JOINED}.", live[0].attrs["x-text"])

    def test_the_inner_chips_the_core_and_one_outer_chip_per_paid_board(self):
        box = self.box()
        inner = [c.text() for c in box.find(cls="o-chip") if "in" in c.classes()]
        outer = [c.text() for c in box.find(cls="o-chip") if "out" in c.classes()]
        self.assertEqual(inner, ["Career pages", "Public boards"])
        self.assertEqual(outer, PAID)
        self.assertEqual(box.one(cls="orbit-core").text(), "Your résumés")
        # the paid boards sit on the spinning ring and are spread evenly round it, from the top
        spin = box.one(cls="orbit-spin")
        self.assertEqual(len(spin.find(cls="o-chip")), len(PAID))
        # by class, never an inline style (test_app: no Jinja inside a style attribute)
        self.assertIn(f"n{len(PAID)}", spin.classes())
        points = spin.find(cls="orbit-pt")
        self.assertTrue(all("style" not in p.attrs for p in points))
        def angle(k):
            if k == 1:
                return float(re.search(r"\.skin-a \.orbit-pt\.out \{ --ang: ([\d.]+)deg; \}", CSS).group(1))
            return float(re.search(rf"\.skin-a \.n{len(PAID)} > \.orbit-pt\.out:nth-child\({k}\) \{{ --ang: ([\d.]+)deg; \}}", CSS).group(1))
        self.assertEqual([angle(k) for k in range(1, len(points) + 1)], [round(i * 360 / len(PAID), 1) for i in range(len(PAID))])

    def test_the_two_rings(self):
        rings = [r.classes() for r in self.box().find(cls="orbit-ring")]
        self.assertEqual(rings, [["orbit-ring", "outer"], ["orbit-ring", "inner"]])


class TestTheSetupDiagram(Page):
    """A11 polish: on a wide screen the Deep setup has the diagram beside its card, in its Deep state, with the three boards "waiting"
    until the paste step. A second, aria-hidden drawing (the macro both use), with no live region of its own."""

    def side(self):
        return self.section("cov-side")

    def test_the_setup_card_and_the_side_are_one_row_and_the_row_follows_the_setups_own_open(self):
        row = self.section("cov-setup-row")
        self.assertEqual(row.attrs[":class"], "{ open: setup }")
        self.assertEqual([n.classes()[0] for n in row.kids if not isinstance(n, str)], ["cov-setup", "cov-side"])
        self.assertNotIn("open", row.classes())

    def test_the_side_is_aria_hidden_decoration_with_no_live_region_and_the_choice_keeps_the_only_one(self):
        side = self.side()
        self.assertEqual(side.attrs["aria-hidden"], "true")
        self.assertEqual(side.find(cls="visually-hidden"), [])
        self.assertEqual([n for n in side.walk() if "aria-live" in n.attrs or "x-text" in n.attrs or n.attrs.get("role")], [])
        live = [n for n in self.main.walk() if n.attrs.get("aria-live") == "polite" and "visually-hidden" in n.classes()]
        self.assertEqual(len(live), 1)
        self.assertIsNone(live[0].within(cls="cov-side"))

    def test_it_is_the_same_drawing_in_its_deep_state_with_the_boards_the_engine_names(self):
        side = self.side()
        box = side.one(cls="orbit-box")
        self.assertEqual(box.attrs["aria-hidden"], "true")
        self.assertEqual(box.classes(), ["orbit-box", "is-deep", "setup-box"])
        self.assertNotIn(":class", box.attrs)                                  # K2: firm is the server's word, once a key checks out
        self.assertEqual([c.text() for c in box.find(cls="o-chip") if "out" in c.classes()], PAID)
        self.assertEqual([c.text() for c in box.find(cls="o-chip") if "in" in c.classes()], ["Career pages", "Public boards"])
        self.assertEqual(box.one(cls="orbit-core").text(), "Your résumés")
        self.assertIn(f"n{len(PAID)}", box.one(cls="orbit-spin").classes())
        choice = self.section("cov-choose").one(cls="orbit-box")
        self.assertEqual([c.text() for c in choice.walk() if isinstance(c, Node) and "o-chip" in c.classes()],
                         [c.text() for c in box.walk() if isinstance(c, Node) and "o-chip" in c.classes()])

    def test_the_sticker_says_what_it_unlocks(self):
        sticker = self.side().one(cls="sticker")
        self.assertEqual(sticker.text(), "Unlocks with your Apify key")
        self.assertIn("cit", sticker.classes())
        self.assertNotIn("pch", " ".join(sticker.classes()))

    def test_the_boards_are_waiting_until_a_key_checks_out(self):
        """K2: the boards stay waiting through the paste step; they firm up only on the page that says the key checked out."""
        self.assertNotIn("firm", self.side().one(cls="orbit-box").classes())                # step 1 on arrival
        self.assertEqual(self.main.one(cls="wsteps").find("li", "wstep")[2].one("h3").text(), "Paste it here")

    def test_it_is_a_second_copy_only_of_markup_the_diagram_already_had(self):
        self.assertEqual(len(self.main.find(cls="orbit-box")), 2)
        self.assertEqual(len(self.main.find(cls="orbit-spin")), 2)
        self.assertEqual(len(self.main.find("input")), len(self.main.find("input", type="radio")) + 1)       # the token field and the two radios: no new input

    def test_a_refused_key_lands_on_the_paste_step_with_the_boards_still_waiting(self):
        _status, _body, main = refused_page()
        self.assertNotIn("firm", main.one(cls="cov-side").one(cls="orbit-box").classes())
        self.assertIn("open", main.one(cls="cov-setup-row").classes())


class TestTheStylesheetPolish(unittest.TestCase):
    """A11 polish, the stylesheet's side of the diagram, the radios and the orbit's pointer."""

    def rules_with(self, selector):
        return [body for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", A6_CSS) if " ".join(sel.split()) == selector]

    def test_the_diagram_is_anchored_to_the_top_of_its_column(self):
        body = self.rules_with(".skin-a .cov")[0]
        self.assertIn("align-items: start", body)
        self.assertNotIn("align-items: center", body)
        self.assertIn("grid-template-columns: minmax(0, 1fr) minmax(0, 1fr)", body)          # two columns, unchanged
        phone = A6_CSS[A6_CSS.index("@media (max-width: 56rem)"):A6_CSS.index("@media (max-width: 40rem)")]
        self.assertIn("order: -1", phone)                                                     # the diagram is still above the cards on a phone
        self.assertNotRegex(phone, r"\.skin-a \.cov \{[^}]*align-items")

    def test_the_radios_are_drawn_here_and_are_still_the_native_inputs(self):
        body, = self.rules_with(".skin-a .cov-choices .choice > input")
        for want in ("appearance: none", "-webkit-appearance: none", "border: 2.5px solid var(--rc)", "border-radius: 50%", "--rc: var(--a-line)"):
            self.assertIn(want, body)
        dot, = self.rules_with(".skin-a .cov-choices .choice > input:checked")
        self.assertIn("radial-gradient(circle closest-side, var(--rc)", dot)                  # an ink dot once checked
        deep, = self.rules_with(".skin-a .cov-choices .choice.d:has(:checked) > input")
        self.assertEqual(deep.strip(), "--rc: var(--a-ink);")                                 # on the lavender card the ink is the fixed ink
        focus, = self.rules_with(".skin-a .cov-choices .choice > input:focus-visible")
        self.assertIn("outline: 3px solid var(--a-focus)", focus)                             # the A focus token
        self.assertNotIn("display: none", body)                                                # kept in the page and the tab order
        self.assertNotIn("opacity: 0", body)
        self.assertNotIn("visibility", body)

    def test_the_radio_markup_is_the_same_name_value_and_model(self):
        _body, main = key_page()
        radios = main.find("input", type="radio")
        self.assertEqual([(r.attrs["name"], r.attrs["value"], r.attrs["x-model"]) for r in radios],
                         [("sweep-mode", "quick", "mode"), ("sweep-mode", "deep", "mode")])
        self.assertEqual(radios[1].attrs["x-ref"], "deepradio")

    def test_the_setup_row_is_beside_the_diagram_only_on_wide_screens_and_only_with_a_script(self):
        self.assertIn(".skin-a.js .cov-setup-row:not(.open) { display: none; }", A6_CSS)
        self.assertIn(".skin-a:not(.js) .cov-side { display: none; }", A6_CSS)
        self.assertRegex(A6_CSS, r"@media \(max-width: 63\.99rem\) \{\s*\.skin-a\.js \.cov-side \{ display: none; \}")
        wide = A6_CSS[A6_CSS.index("@media (min-width: 64rem)"):]
        wide = wide[:wide.index("\n}\n")]
        self.assertIn(".skin-a.js .cov-setup-row { display: grid;", wide)
        self.assertIn(".skin-a.js .cov-setup-row > .cov-setup { max-width: none; }", wide)

    def test_waiting_boards_are_dashed_and_muted_and_firm_ones_are_the_diagrams_own_solid_chips(self):
        waiting, = self.rules_with(".skin-a .setup-box:not(.firm) .o-chip.out")
        self.assertIn("border: 2px dashed var(--control)", waiting)
        self.assertIn("color: var(--slate)", waiting)
        self.assertIn("background: var(--surface)", waiting)                                    # opaque: the ring's dashes do not cross the word
        firm = self.rules_with(".skin-a .setup-box.firm .o-chip.out")
        self.assertEqual(len(firm), 1, "firm is the chip's own look: the one rule for it is the pop")
        self.assertIn("a-firm", firm[0])

    def test_the_pop_when_they_firm_up_is_motion_only_in_no_preference(self):
        block = A6_CSS[A6_CSS.index("@media (prefers-reduced-motion: no-preference)"):]
        self.assertIn(".skin-a .setup-box.firm .o-chip.out { animation: a-orbit 46s linear infinite reverse, a-firm .5s cubic-bezier(.3, 1.6, .5, 1); }", block)
        self.assertRegex(block, r"@keyframes a-firm \{ 0% \{ scale: 1; \} 45% \{ scale: 1\.18; \} 100% \{ scale: 1; \} \}")
        self.assertNotIn("a-firm", A6_CSS[:A6_CSS.index("@media (prefers-reduced-motion: no-preference)")])

    def test_the_orbit_follows_the_pointer_only_with_motion_and_a_fine_hovering_pointer(self):
        at = A6_CSS.index("@media (prefers-reduced-motion: no-preference) {\n  @media (hover: hover) and (pointer: fine) {")
        block = A6_CSS[at:]
        self.assertNotIn("--ox", A6_CSS[:at])                                                  # nothing reads the pointer outside it
        self.assertNotIn("animation-play-state", A6_CSS[:at])
        inner = re.search(r"\.orbit-ring\.inner, [^{]*\{\s*transform: translate\(calc\(var\(--ox, 0\) \* (\d+)px\), calc\(var\(--oy, 0\) \* (\d+)px\)\);", block)
        outer = re.search(r"\.orbit-ring\.outer, [^{]*\{\s*transform: translate\(calc\(var\(--ox, 0\) \* (\d+)px\), calc\(var\(--oy, 0\) \* (\d+)px\)\);", block)
        self.assertEqual(inner.group(1), inner.group(2))
        self.assertGreater(int(outer.group(1)), int(inner.group(1)))                           # the outer ring moves more
        self.assertGreaterEqual(int(inner.group(1)), 3)                                        # a few pixels, not a flinch...
        self.assertLessEqual(int(outer.group(1)), 20)                                          # ...and not a swing
        self.assertIn("transform .45s cubic-bezier(.22, .61, .36, 1)", block)                  # it eases back when the pointer leaves
        for sel, _ in re.findall(r"([^{}]+)\{([^{}]*)\}", block):
            for part in sel.split(","):
                part = " ".join(part.split())
                if part.startswith(".skin-a"):
                    self.assertIn(".skin-a .cov-choose .orbit", part, "only the choice's diagram, never the setup's")

    def test_hovering_a_board_lifts_it_and_pauses_the_orbit(self):
        lift = [b for s, b in re.findall(r"([^{}]+)\{([^{}]*)\}", A6_CSS) if " ".join(s.split()) == ".skin-a .cov-choose .orbit-box.is-deep .o-chip.out:hover"]
        self.assertEqual(len(lift), 1)
        self.assertIn("scale: 1.14", lift[0])
        self.assertIn("box-shadow: 3px 3px 0 var(--a-shadow)", lift[0])
        self.assertRegex(A6_CSS, r"\.orbit-box\.is-deep:has\(\.o-chip\.out:hover\) \.orbit-spin,\s*\.skin-a \.cov-choose \.orbit-box\.is-deep:has\(\.o-chip\.out:hover\) \.o-chip\.out \{ animation-play-state: paused; \}")

    def test_the_orbit_script_is_plain_dom_scoped_to_the_choice_and_asks_for_a_fine_hovering_pointer_and_motion(self):
        js = (ROOT / "static" / "orbit.js").read_text()
        self.assertIn('document.querySelector(".cov-choose .orbit-box")', js)
        self.assertIn('"(hover: hover) and (pointer: fine)"', js)
        self.assertIn('"(prefers-reduced-motion: reduce)"', js)
        self.assertIn('e.pointerType === "touch"', js)
        self.assertNotIn("Alpine", js.replace("no Alpine", ""))
        self.assertNotIn("aria-hidden", re.sub(r"/\*.*?\*/", "", js, flags=re.S))            # it never touches what a reader hears


class TestTheOrbitScriptLoadsOnlyOnKey(unittest.TestCase):
    TAG = '<script defer src="/static/orbit.js"></script>'

    def test_the_public_key_page_loads_it_once_in_the_head(self):
        body, _main = key_page()
        self.assertEqual(body.count(self.TAG), 1)
        self.assertLess(body.index(self.TAG), body.index("<header>"))

    def test_the_refused_key_page_loads_it_too_because_it_is_the_same_screen(self):
        _status, body, _main = refused_page()
        self.assertEqual(body.count(self.TAG), 1)

    def test_no_other_public_page_loads_it(self):
        with stack() as (url, _store):
            client = reviewed(render_app(url, check_token=lambda t: (4.25, None)))
            for path in ("/", "/review"):
                with self.subTest(path=path):
                    got = client.get(path, follow_redirects=True).get_data(as_text=True)
                    self.assertNotIn("orbit.js", got)

    def test_the_console_key_page_does_not(self):
        self.assertNotIn("orbit.js", console_pages()["/key"])

    def test_base_never_loads_it_and_only_key_html_names_it(self):
        named = [p.name for p in (ROOT / "templates").glob("*.html") if "orbit.js" in p.read_text()]
        self.assertEqual(named, ["key.html"])


class TestTheDeepForm(Page):
    def form(self):
        forms = [f for f in self.main.find("form") if f.attrs["action"].endswith("/key")]
        self.assertEqual(len(forms), 1)
        return forms[0]

    def test_the_form_and_its_one_field(self):
        form = self.form()
        self.assertEqual(form.attrs["method"], "post")
        token = form.one("input", name="token")
        self.assertEqual(token.attrs["type"], "password")
        self.assertEqual(token.attrs["autocomplete"], "off")
        self.assertIn("required", token.attrs)
        self.assertNotIn("value", token.attrs, "the page never writes a token into the field")
        self.assertEqual(token.attrs["aria-describedby"], "key-privacy")
        self.assertEqual([i.attrs.get("name") for i in form.find("input")], ["token"])
        self.assertEqual(self.main.find("li", "wstep")[0].find("input"), [])      # step 1 holds no field at all

    def test_every_described_by_id_exists_exactly_once(self):
        token = self.form().one("input", name="token")
        for ident in token.attrs["aria-describedby"].split():
            with self.subTest(id=ident):
                self.assertEqual(len([n for n in self.main.walk() if n.attrs.get("id") == ident]), 1)

    def test_the_submit(self):
        form = self.form()
        submit = [b for b in form.find("button") if b.attrs["type"] == "submit"]
        self.assertEqual(len(submit), 1)
        self.assertEqual(submit[0].text(), "Check my key")
        self.assertEqual(submit[0].attrs[":disabled"], "sent")
        self.assertEqual(form.attrs["x-data"], "{ sent: false }")
        self.assertEqual(form.attrs["@submit"], "sent = true")
        self.assertEqual(form.one(cls="sending").text(), "Checking your key with Apify…")
        # K2: while the check is out, the first fact is under way and the other two wait; hidden until a submit
        run = form.one("ol", "key-run")
        self.assertIn("hidden", run.attrs)
        self.assertEqual(run.attrs[":hidden"], "!sent")
        self.assertEqual([li.classes() for li in run.find("li")], [["now"], [], []])

    def test_the_privacy_sentence_is_visible_beside_the_field(self):
        form = self.form()
        note = form.one("p", id="key-privacy")
        self.assertEqual(note.text(), "Your Apify key is used for this Sweep only and is never saved: not to a file, a cookie or a log. "
                                      "Checking it costs nothing; Sweep only reads the balance.")
        self.assertEqual(note.find("b")[0].text(), "Your Apify key is used for this Sweep only and is never saved:")
        self.assertIsNone(note.within("details"), "the privacy sentence is never hidden in a disclosure or a peek")
        self.assertIsNone(note.within(cls="peek"))
        # it is in the same form, a sibling of the label that holds the field: right next to it
        self.assertIs(note.parent, form)
        self.assertIs(form.one("input", name="token").within("label").parent, form)

    def test_the_token_is_nowhere_else_in_the_page(self):
        # the only field a visitor can type a key into is that one
        typed = [i for i in self.main.find("input") if i.attrs.get("type") in (None, "text", "password", "search")]
        self.assertEqual([i.attrs["name"] for i in typed], ["token"])
        self.assertNotRegex(self.body, r"(?i)localstorage|sessionstorage|\$persist")


class TestTheSetup(Page):
    def steps(self):
        return self.section("wsteps").find("li", "wstep")

    def test_three_steps_in_order(self):
        steps = self.steps()
        self.assertEqual([s.one("h3").text() for s in steps], ["Grab a free Apify account", "Copy your API token", "Paste it here"])
        for s in steps:
            self.assertEqual(s.one("h3").attrs["tabindex"], "-1")
        self.assertEqual(self.section("wsteps").tag, "ol")
        self.assertEqual([s.attrs[":class"] for s in steps], ["{ open: step === 1 }", "{ open: step === 2 }", "{ open: step === 3 }"])
        self.assertEqual([("open" in s.classes()) for s in steps], [True, False, False])

    def test_the_setup_heading(self):
        setup = self.section("cov-setup")
        self.assertEqual(setup.attrs["id"], "deep-setup")
        h2 = setup.one("h2")
        self.assertEqual(h2.text(), "Three more boards, one key.")
        self.assertEqual(h2.one(cls="scrib").text(), "one key")
        self.assertEqual((h2.attrs["tabindex"], h2.attrs["x-ref"]), ("-1", "setuph"))
        self.assertNotIn("open", setup.classes())
        self.assertEqual(setup.attrs[":class"], "{ open: setup }")

    def test_step_one(self):
        s = self.steps()[0]
        self.assertEqual(s.one(cls="sticker").text(), "$5 free every month")
        self.assertEqual(s.one("p").text(), f"Apify runs the {JOINED} searches, on your own account. The free plan includes $5 of credit every month — no card.")
        link = s.one("a")
        self.assertEqual(link.attrs["href"], "https://apify.com/sign-up")
        self.assertEqual((link.attrs["target"], link.attrs["rel"]), ("_blank", "noopener noreferrer"))
        self.assertIn("primary", link.classes())
        self.assertEqual(link.text(), "Sign up at apify.com↗")
        buttons = {b.text().strip("→"): b for b in s.find("button")}
        self.assertEqual(set(buttons), {"I already have one", "Already have a key? Paste it"})
        self.assertIn("step = 2", buttons["I already have one"].attrs["@click"])
        self.assertIn("$refs.step2.focus()", buttons["I already have one"].attrs["@click"])
        self.assertIn("tertiary", buttons["Already have a key? Paste it"].classes())
        self.assertIn("step = 3", buttons["Already have a key? Paste it"].attrs["@click"])
        self.assertIn("$refs.step3.focus()", buttons["Already have a key? Paste it"].attrs["@click"])

    def test_step_two_without_a_screenshot_shows_the_mock_row(self):
        s = self.steps()[1]
        self.assertEqual([p.text() for p in s.find("p")], [
            "Signed in? This opens the right page — Settings, then API & Integrations.",
            "Copy the Personal API token with the button beside it. Apify calls it the token created on sign-up — that is the one."])
        link = s.one("a")
        self.assertEqual(link.attrs["href"], "https://console.apify.com/settings/integrations")
        self.assertEqual((link.attrs["target"], link.attrs["rel"]), ("_blank", "noopener noreferrer"))
        self.assertIn("primary", link.classes())
        mock_row = s.one(cls="mocktok")
        self.assertEqual(mock_row.attrs["aria-hidden"], "true")
        self.assertEqual([k.text() for k in mock_row.kids], ["Settings › API & Integrations", "Personal API token", "••••••••••", "Copy"])
        self.assertEqual(s.find("figure"), [])
        button = s.one("button")
        self.assertEqual(button.text(), "I’ve copied it→")
        self.assertIn("step = 3", button.attrs["@click"])
        self.assertIn("$refs.step3.focus()", button.attrs["@click"])

    def test_step_three_is_the_form_and_goes_back_a_step(self):
        s = self.steps()[2]
        self.assertEqual(len(s.find("form")), 1)
        back = [b for b in s.find("button") if b.text() == "← Back a step"]
        self.assertEqual(len(back), 1)
        self.assertEqual(back[0].attrs["type"], "button", "Back must not submit the key form")
        self.assertIn("tertiary", back[0].classes())
        self.assertIn("step = 2", back[0].attrs["@click"])
        self.assertEqual(s.find(cls="error"), [], "no error on a fresh page")

    def test_the_setup_has_the_back_button_the_dots_and_the_count(self):
        setup = self.section("cov-setup")
        back = [b for b in setup.find("button") if b.text() == "← Back to the options"]
        self.assertEqual(len(back), 1)
        self.assertEqual(back[0].attrs["type"], "button")
        self.assertIn("tertiary", back[0].classes())
        self.assertIn("setup = false", back[0].attrs["@click"])
        self.assertIn("$refs.deepradio.focus()", back[0].attrs["@click"])
        nav = setup.one(cls="wnav")
        dots = nav.one(cls="wdots")
        self.assertEqual(dots.attrs["aria-hidden"], "true")
        self.assertEqual(len(dots.find("i")), 3)
        self.assertEqual(nav.one(cls="wcount").text(), "Step 1 of 3")
        self.assertEqual(nav.one(cls="wcount").find("span")[0].attrs["x-text"], "step")
        # the Deep radio is the thing Back to the options focuses
        self.assertEqual(self.main.one("input", value="deep").attrs["x-ref"], "deepradio")

    def test_everything_that_needs_a_script_says_so(self):
        """Controls that do nothing without Alpine carry `js-only`, which sweep-a.css does not draw without a script."""
        setup = self.section("cov-setup")
        doing = [n for n in setup.walk() if "@click" in n.attrs]
        self.assertEqual(len(doing), 5)       # Back to the options, I already have one, Paste it, I've copied it, Back a step
        for n in doing:
            with self.subTest(button=n.text()):
                self.assertTrue("js-only" in n.classes() or n.within(cls="js-only"), n.text())
        self.assertIn("js-only", setup.one(cls="wnav").classes())

    def test_exactly_one_tip_and_it_is_in_the_setup(self):
        tips = [n for n in self.main.walk() if "data-tip" in n.attrs]
        self.assertEqual([t.attrs["data-tip"] for t in tips], ["key-setup"])
        self.assertIsNotNone(tips[0].within(cls="cov-setup"))
        self.assertEqual(tips[0].one(cls="tip-say").text(), "About a minute, start to finish.")
        self.assertEqual(self.body.count('data-tip="key-setup"'), 1)

    def test_the_tip_shows_on_steps_one_and_two_only_and_once_without_a_script(self):
        """Pre-merge polish: "About a minute, start to finish." is stale at the paste step. The tip sits in a wrapper that Alpine's `step`
        turns on for steps 1 and 2 (`on`), the server starts it on (step 1 here), and sweep-a.css hides an off one only under `.js`:
        so a visitor without a script sees the tip once, as before."""
        tip = [n for n in self.main.walk() if "data-tip" in n.attrs][0]
        wrap = tip.within(cls="wtip")
        self.assertIsNotNone(wrap)
        self.assertIn("on", wrap.classes())                                              # step 1: shown at first paint
        self.assertEqual(wrap.attrs[":class"], "{ on: step < 3 }")
        self.assertEqual(len(wrap.find(cls="tip")), 1)
        self.assertIsNotNone(wrap.within(cls="cov-setup"))
        self.assertEqual(self.body.count('class="wtip'), 1)
        self.assertNotIn("x-show", wrap.attrs)                                           # a class like the steps' own: no x-cloak, no flash at the paste step


class TestTheScreenshotsStayOptional(unittest.TestCase):
    GUIDE = {"1-signup": "apify/1-signup.png", "2-console": "apify/2-console.png", "3-token": "apify/3-token.png"}

    def test_each_shot_is_in_its_step_with_its_alt_text_and_the_mock_gives_way(self):
        _body, main = key_page(guide=self.GUIDE)
        steps = main.one(cls="wsteps").find("li", "wstep")
        alts = [[img.attrs["alt"] for img in s.find("img")] for s in steps]
        self.assertEqual([flat(a[0]) for a in alts], [
            "The apify.com home page. Log in and Get started are at the top right.",
            "The apify.com home page once signed in, with Go to Console at the top right.",
            "The Apify console under Settings, API and Integrations, showing the Personal API tokens section with a copy button beside the token."])
        self.assertEqual([[img.attrs["src"].rsplit("/", 1)[-1] for img in s.find("img")] for s in steps],
                         [["1-signup.png"], ["2-console.png"], ["3-token.png"]])
        self.assertEqual(main.find(cls="mocktok"), [], "the mock row only stands in for a missing screenshot")
        for s in steps:
            self.assertEqual(len(s.find("figure", "shot")), 1)
        # the paste step's picture is inside the form's step, not inside the form's fields
        self.assertEqual(steps[2].one("form").find("input")[0].attrs["name"], "token")

    def test_with_none_there_is_no_picture_and_the_mock_row_is_the_only_stand_in(self):
        _body, main = key_page(guide={})
        self.assertEqual(main.find("img"), [])
        self.assertEqual(len(main.find(cls="mocktok")), 1)

    def test_only_the_missing_one_gets_the_mock(self):
        _body, main = key_page(guide={"1-signup": "apify/1-signup.png"})
        self.assertEqual(len(main.find("img")), 1)
        self.assertEqual(len(main.find(cls="mocktok")), 1)


class TestOutboundLinks(Page):
    def test_every_link_off_the_site_is_safe_to_open(self):
        links = [a for a in self.main.find("a") if a.attrs.get("href", "").startswith("https://")]
        self.assertEqual([a.attrs["href"] for a in links], ["https://apify.com/sign-up", "https://console.apify.com/settings/integrations"])
        for a in links:
            self.assertEqual(a.attrs["target"], "_blank")
            self.assertEqual(a.attrs["rel"], "noopener noreferrer")


class TestNoScriptNothingIsHidden(Page):
    """Without a script the page is the plain one. The closed parts are hidden only under `.skin-a.js` (theme.js puts `js` on <html>)."""

    def test_the_markup_starts_in_the_state_a_script_would_set(self):
        self.assertNotIn("away", self.section("cov-choose").classes())
        self.assertIn("on", self.section("cov-quick").classes())
        self.assertNotIn("on", self.section("cov-deepgo").classes())
        self.assertIn("js-only", self.section("cov-deepgo").classes())        # no script, no button
        self.assertIn("checked", self.main.one("input", value="quick").attrs)

    def test_no_x_cloak_hides_a_reveal(self):
        for n in self.main.walk():
            if "x-cloak" in n.attrs:
                with self.subTest(n=n.tag + "." + " ".join(n.classes())):
                    self.assertIn("sending", n.classes())          # only the "…ing" lines, which are hidden until a submit

    def test_every_rule_that_hides_something_is_under_js(self):
        hiders = []
        for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", A6_CSS):
            if re.search(r"display:\s*none", body):
                hiders.append(" ".join(selector.split()))
        self.assertTrue(hiders)
        for sel in hiders:
            for part in (p.strip() for p in sel.split(",")):
                with self.subTest(selector=part):
                    self.assertTrue(part.startswith((".skin-a.js ", ".skin-a:not(.js) ")), part)

    def test_the_four_reveals_and_the_two_js_only_rules(self):
        for want in (".skin-a.js .cov-choose.away", ".skin-a.js .cov-setup:not(.open)", ".skin-a.js .wstep:not(.open)",
                     ".skin-a.js .cov-quick:not(.on)", ".skin-a.js .cov-deepgo:not(.on)", ".skin-a.js .wtip:not(.on)",
                     ".skin-a:not(.js) .cov-page .js-only"):
            with self.subTest(want=want):
                self.assertIn(want, A6_CSS)


class TestARefusedKeyReopensThePasteStep(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.token = "not-a-real-token-xyz"
        cls.status, cls.body, cls.main = refused_page(cls.token)

    def test_it_is_a_400_with_the_screen_again(self):
        self.assertEqual(self.status, 400)
        self.assertEqual(self.main.one("h1").text(), "How wide should we sweep?")

    def test_it_lands_with_deep_chosen_and_the_setup_open_at_step_three(self):
        self.assertEqual(self.main.one(cls="cov-page").attrs["x-data"], "{ mode: 'deep', setup: true, step: 3 }")
        self.assertIn("checked", self.main.one("input", value="deep").attrs)
        self.assertNotIn("checked", self.main.one("input", value="quick").attrs)
        self.assertIn("away", self.main.one(cls="cov-choose").classes())
        self.assertIn("open", self.main.one(cls="cov-setup").classes())
        self.assertNotIn("on", self.main.one(cls="wtip").classes())              # the paste step: the "about a minute" tip is not there (under a script)
        steps = self.main.one(cls="wsteps").find("li", "wstep")
        self.assertEqual([("open" in s.classes()) for s in steps], [False, False, True])
        self.assertIn("is-deep", self.main.one(cls="cov-choose").one(cls="orbit-box").classes())
        self.assertIn("on", self.main.one(cls="cov-deepgo").classes())
        self.assertNotIn("on", self.main.one(cls="cov-quick").classes())
        self.assertEqual(self.main.one(cls="wcount").text(), "Step 3 of 3")
        self.assertEqual([i.classes() for i in self.main.one(cls="wdots").find("i")], [["ok"], ["ok"], ["on"]])

    def test_the_error_is_in_step_three_next_to_the_field_and_only_there(self):
        errors = self.main.find(cls="error")
        self.assertEqual(len(errors), 1)
        error = errors[0]
        self.assertEqual(error.tag, "p")
        self.assertEqual(error.attrs["role"], "alert")
        self.assertEqual(error.text(), REJECTED)
        step = error.within("li", "wstep")
        self.assertEqual(step.one("h3").text(), "Paste it here")
        self.assertIn("open", step.classes())
        self.assertIs(error.within("form"), step.one("form"))

    def test_the_token_is_not_echoed_anywhere_and_the_field_is_empty(self):
        self.assertNotIn(self.token, self.body)
        field = self.main.one("input", name="token")
        self.assertNotIn("value", field.attrs)

    def test_the_privacy_sentence_and_the_form_are_still_there(self):
        self.assertEqual(len(self.main.find("p", id="key-privacy")), 1)
        self.assertEqual(len(self.main.find("form", action="/key")), 1)

    def test_a_malformed_key_reopens_it_the_same_way_and_is_not_echoed(self):
        with stack() as (url, store):
            with apify() as (seen, check):
                client = reviewed(render_app(url, check_token=check))
                response = client.post("/key", data={"token": "has spaces in it"})
                body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(seen, [], "a malformed key never reaches Apify")
        self.assertIn("{ mode: 'deep', setup: true, step: 3 }", body)
        self.assertNotIn("has spaces in it", body)


class TestAnErrorThatIsNotAboutTheKeyStaysOnTheChoice(unittest.TestCase):
    """key_screen also shows Quick's profile-rewrite failure and the plan and run limits. None is about a key, so none may
    open the paste step or sit beside the token field: only a refusal from POST /key does that."""
    @classmethod
    def setUpClass(cls):
        def broken(*_a, **_k):
            raise KeyError("track")
        with stack() as (url, _store):
            app = render_app(url, check_token=lambda t: (4.25, None))
            client = reviewed(app)
            app.write_profile = broken
            response = client.post("/key/free")
            cls.status, body = response.status_code, response.get_data(as_text=True)
        cls.main = main_of(body)

    def test_it_lands_on_the_choice_with_quick_chosen(self):
        self.assertEqual(self.status, 500)
        self.assertEqual(self.main.one(cls="cov-page").attrs["x-data"], "{ mode: 'quick', setup: false, step: 1 }")
        self.assertIn("checked", self.main.one("input", value="quick").attrs)
        self.assertNotIn("away", self.main.one(cls="cov-choose").classes())
        self.assertNotIn("open", self.main.one(cls="cov-setup").classes())
        self.assertIn("on", self.main.one(cls="cov-quick").classes())

    def test_the_error_is_under_the_headline_and_not_in_the_key_step(self):
        errors = self.main.find(cls="error")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].attrs["role"], "alert")
        self.assertIn("could not be rewritten", errors[0].text())
        self.assertIsNotNone(errors[0].within("section", "cov-choose"))
        self.assertIsNone(errors[0].within("li", "wstep"))


class TestThePostsAreAsTheyWere(unittest.TestCase):
    def test_a_good_key_comes_back_to_say_what_the_check_found_then_goes_on_to_configure(self):
        """K2: the key step's POST comes back to /key?checked: the three facts, all in (the credit is the account's own
        figure), the boards firm, and the way on is a link to Configure. The key is in neither page."""
        with stack() as (url, _store):
            with apify() as (seen, check):
                client = reviewed(render_app(url, check_token=check))
                page = client.get("/key").get_data(as_text=True)
                answer = client.post("/key", data={"token": VISITOR_KEY})
                checked = client.get(answer.headers["Location"]).get_data(as_text=True)
                stale = client.get("/key?checked=1")
        self.assertEqual(seen, [VISITOR_KEY])
        self.assertEqual((answer.status_code, answer.headers["Location"].rsplit("/", 1)[-1]), (302, "key?checked=1"))
        self.assertNotIn(VISITOR_KEY, page)
        self.assertNotIn(VISITOR_KEY, checked)
        main = main_of(checked)
        run = main.one("ol", "key-run")
        self.assertIn("is-done", run.classes())
        facts = [li.text() for li in run.find("li")]
        self.assertEqual(facts[0], "Reached Apify")
        self.assertRegex(facts[1], r"^Credit on this account: \$\d+\.\d\d$")
        self.assertTrue(facts[2].endswith(" unlocked for this sweep"))
        self.assertEqual([li.classes() for li in run.find("li")], [["on"]] * 3)
        self.assertEqual(main.find("input", name="token"), [])                  # no field to paste into again
        go = [a for a in main.find("a") if a.text().startswith("Continue to your plan")]
        self.assertEqual(len(go), 1)
        self.assertTrue(go[0].attrs["href"].endswith("/configure"))
        self.assertIn("firm", main.one(cls="cov-side").one(cls="orbit-box").classes())
        self.assertEqual(main.one(cls="cov-side").one(cls="sticker").text(), "Unlocked for this sweep")
        self.assertIn("open", main.one(cls="cov-setup-row").classes())
        self.assertEqual(stale.status_code, 200)

    def test_checked_with_no_key_held_is_the_plain_screen(self):
        with stack() as (url, _store):
            client = reviewed(render_app(url, check_token=lambda t: (4.25, None)))
            page = client.get("/key?checked=1").get_data(as_text=True)
        self.assertNotIn("key-run is-done", page)
        self.assertIn('name="token"', page)

    def test_quick_sweep_still_redirects_to_configure(self):
        with stack() as (url, _store):
            client = reviewed(render_app(url, check_token=lambda t: (4.25, None)))
            answer = client.post("/key/free")
        self.assertEqual((answer.status_code, answer.headers["Location"].rsplit("/", 1)[-1]), (302, "configure"))


class TestTheConsoleIsUntouched(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = console_pages()

    def test_it_renders_none_of_the_new_markup(self):
        html = self.pages["/key"]
        for needle in ("cov-page", "cov-choose", "cov-setup", "cov-choices", "cov-quick", "orbit-box", "orbit-ring", "o-chip", "wsteps", "wstep",
                       "wdots", "mocktok", "js-only", "sweep-mode", "Step 3 · coverage", "How wide should we", "Three more boards", "data-tip",
                       'class="peek"', "Does Deep Sweep cost money?", "Grab a free Apify account", "Paste it here", "key-privacy",
                       "deep-setup", "skin-a", "Quick Sweep", "Deep Sweep"):
            with self.subTest(needle=needle):
                self.assertNotIn(needle, html)

    def test_it_keeps_its_words_and_its_two_forms(self):
        html = self.pages["/key"]
        for kept in ("<h1>How far should this sweep go?</h1>", "<h2>Free sources only</h2>", "<h2>Free sources and the paid boards</h2>",
                     'aria-describedby="env-note"', 'id="env-note"', "Search the free sources", ">Verify key<", 'action="/key/free"', 'action="/key"'):
            with self.subTest(kept=kept):
                self.assertIn(kept, html)

    def test_the_console_branch_of_the_template_is_byte_for_byte_what_it_was(self):
        """sha256 of key.html's `{% else %}` branch as it stood at the end of A5; A6 only replaced the `public_mode` branch above it."""
        branch = TEMPLATE[TEMPLATE.index("  {% else %}\n    {# ---- The operator's console, unchanged"):TEMPLATE.index("  {% endif %}\n</div>\n{% endblock %}")]
        self.assertEqual(hashlib.sha256(branch.encode()).hexdigest(), "4180ea7be91dfe2b69f7cfd9c42e50a93c48d783850f6d2a9b37daced37c93b8")


class TestTheStylesheet(unittest.TestCase):
    def rule(self, selector):
        for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", A6_CSS):
            if " ".join(sel.split()) == selector:
                return body
        self.fail("no rule for " + selector)

    def test_the_cards(self):
        card = self.rule(".skin-a .cov-choices .choice")
        for want in ("padding: 22px", "border-radius: 24px", "background: var(--surface)", "2px solid var(--a-line)"):
            self.assertIn(want, card)
        name = self.rule(".skin-a .cov-choices .nm")
        self.assertIn("800 30px", name)
        self.assertIn("var(--display)", name)
        quick = self.rule(".skin-a .cov-choices .choice.q:has(:checked), .skin-a .cov-choices .choice.q:has(:checked):hover")
        self.assertIn("var(--cov-tint)", quick)
        deep = self.rule(".skin-a .cov-choices .choice.d:has(:checked), .skin-a .cov-choices .choice.d:has(:checked):hover")
        self.assertIn("background: var(--a-lav)", deep)
        self.assertIn("color: var(--a-ink)", deep)
        self.assertIn("color-mix(in srgb, var(--a-cit) 22%, var(--surface))", A6_CSS)

    def test_the_diagram(self):
        self.assertIn("max-width: 400px", self.rule(".skin-a .orbit-box"))
        self.assertIn("2.5px dashed var(--a-line)", self.rule(".skin-a .orbit-ring.outer"))
        inner = self.rule(".skin-a .orbit-ring.inner")
        self.assertIn("2.5px solid var(--a-line)", inner)
        self.assertIn("var(--cov-tint)", inner)
        core = self.rule(".skin-a .orbit-core")
        self.assertIn("background: var(--chalk)", core)
        self.assertIn("color: var(--ground)", core)
        chip = self.rule(".skin-a .o-chip")
        self.assertIn("2px solid var(--a-ink)", chip)
        self.assertIn("border-radius: 999px", chip)
        self.assertIn("background: var(--a-lav)", chip)
        self.assertIn("background: var(--a-cit)", self.rule(".skin-a .o-chip.in"))

    def test_the_setup_card(self):
        card = self.rule(".skin-a .cov-setup")
        for want in ("max-width: 720px", "2px solid var(--a-line)", "box-shadow: 6px 6px 0 var(--a-shadow)"):
            self.assertIn(want, card)

    def test_on_a_phone_the_diagram_is_above_and_smaller_and_the_call_to_action_is_the_bar(self):
        wide = A6_CSS[A6_CSS.index("@media (max-width: 56rem)"):A6_CSS.index("@media (max-width: 40rem)")]
        self.assertIn("max-width: 260px", wide)
        self.assertIn("order: -1", wide)
        phone = A6_CSS[A6_CSS.index("@media (max-width: 40rem)"):A6_CSS.index("@media (prefers-reduced-motion")]
        bar = re.search(r"\.skin-a \.cov-cta \{([^}]*)\}", phone).group(1)
        for want in ("position: sticky", "bottom: 0", "background: var(--ground)", "border-top: 2px solid var(--a-line)", "env(safe-area-inset-bottom)"):
            self.assertIn(want, bar)

    def test_motion_is_only_in_no_preference_and_reduced_motion_has_no_spin(self):
        block_at = A6_CSS.index("@media (prefers-reduced-motion: no-preference)")
        self.assertNotRegex(A6_CSS[:block_at], r"(animation|transition)\s*:")
        block = A6_CSS[block_at:]
        self.assertIn("animation: a-orbit 46s linear infinite;", block)
        self.assertIn("animation: a-orbit 46s linear infinite reverse;", block)
        self.assertIn("@keyframes a-orbit", block)
        self.assertNotIn("@media (prefers-reduced-motion: reduce)", A6_CSS)

    def test_no_raw_colour(self):
        self.assertNotRegex(A6_CSS, r"#[0-9A-Fa-f]{3,8}\b")
        self.assertNotRegex(A6_CSS, r"rgba?\(")


if __name__ == "__main__":
    unittest.main()
