"""Direction A, stages A1 and A2: the public skin's colours, the shell that carries them, and the shared components.

sweep-a.css re-points sweep.css's custom properties under `html.skin-a` (public
mode only), in light and dark. These tests read that stylesheet the way
test_visual_rules.py reads sweep.css: the arithmetic is the contract. They also
render the real shell once in each mode, because "the console is unchanged" is a
claim about what a visitor to `/` is actually sent. A2 adds the component tokens (--a-*), the rule that components are shaped
here but page layout is not, the motion rule (everything that moves sits behind no-preference), and the _a.html macros.
"""
import os
import pathlib
import re
import unittest
from unittest import mock

from sweep import app as app_module
from sweep.tests.test_app import DERIVED
from sweep.tests.test_public import public_app, unlocked

ROOT = pathlib.Path(app_module.__file__).parent
CSS = (ROOT / "static" / "sweep-a.css").read_text()
BASE = (ROOT / "templates" / "base.html").read_text()

TOKENS = ["--ground", "--well", "--surface", "--surface-low", "--surface-high", "--surface-edge", "--chalk",
          "--chalk-lift", "--warm", "--slate", "--dim", "--paid", "--paid-lift", "--free", "--free-lift", "--over",
          "--rule", "--control", "--pending-slate", "--display", "--text"]
A_TOKENS = ["--a-line", "--a-shadow", "--a-primary", "--a-on-primary", "--a-link", "--a-focus", "--a-lav", "--a-cit",
            "--a-pch", "--a-ink", "--a-tint"]
SURFACES = ["--ground", "--well", "--surface", "--surface-low", "--surface-high", "--surface-edge"]
TEXT = ["--chalk", "--warm", "--slate", "--paid", "--paid-lift", "--free", "--free-lift", "--over"]

SCOPES = {
    "light": re.search(r"^\.skin-a \{([^}]*)\}", CSS, re.M).group(1),
    "dark-media": re.search(r'@media \(prefers-color-scheme: dark\) \{\s*\.skin-a:not\(\[data-theme="light"\]\) \{([^}]*)\}',
                            CSS).group(1),
    "dark-attr": re.search(r'^\.skin-a\[data-theme="dark"\] \{([^}]*)\}', CSS, re.M).group(1),
}


def declared(block):
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"(--[\w-]+)\s*:\s*([^;]+);", block)}


VALUES = {name: declared(block) for name, block in SCOPES.items()}
THEMES = {"light": VALUES["light"], "dark": VALUES["dark-attr"]}


def rgb(hexcolor):
    h = hexcolor.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def luminance(c):
    lin = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def blend(fg, bg, alpha):
    return tuple(alpha * f + (1 - alpha) * b for f, b in zip(fg, bg))


class TestTheTokens(unittest.TestCase):
    def test_every_token_is_declared_in_each_scope(self):
        for scope, values in VALUES.items():
            for token in TOKENS:
                with self.subTest(scope=scope, token=token):
                    self.assertIn(token, values)

    def test_the_two_dark_scopes_carry_identical_values(self):
        self.assertEqual(VALUES["dark-media"], VALUES["dark-attr"])

    def test_the_type_stacks_are_direction_a_in_both_themes(self):
        for theme, values in THEMES.items():
            with self.subTest(theme=theme):
                self.assertEqual(values["--display"],
                                 '"Bricolage Grotesque", "Instrument Sans", system-ui, sans-serif')
                self.assertEqual(values["--text"],
                                 '"Instrument Sans", system-ui, -apple-system, sans-serif')

    def test_color_scheme_follows_the_theme(self):
        self.assertIn("color-scheme: light", SCOPES["light"])
        self.assertIn("color-scheme: dark", SCOPES["dark-media"])
        self.assertIn("color-scheme: dark", SCOPES["dark-attr"])

    def test_the_light_theme_is_the_base_and_an_explicit_light_needs_nothing_more(self):
        self.assertNotIn('[data-theme="light"] {', CSS)  # only ever excluded, never restyled


class TestContrast(unittest.TestCase):
    def test_text_colours_pass_aa_on_every_surface(self):
        for theme, v in THEMES.items():
            for fg in TEXT:
                for bg in SURFACES:
                    with self.subTest(theme=theme, fg=fg, bg=bg):
                        self.assertGreaterEqual(contrast(rgb(v[fg]), rgb(v[bg])), 4.5)

    def test_control_edges_pass_3_to_1_on_every_surface(self):
        for theme, v in THEMES.items():
            for bg in SURFACES:
                with self.subTest(theme=theme, bg=bg):
                    self.assertGreaterEqual(contrast(rgb(v["--control"]), rgb(v[bg])), 3.0)

    def test_the_dimmed_muted_text_still_passes_at_85_percent(self):
        for theme, v in THEMES.items():
            for bg in ("--surface", "--well", "--ground"):
                with self.subTest(theme=theme, bg=bg):
                    fg = blend(rgb(v["--pending-slate"]), rgb(v[bg]), 0.85)
                    self.assertGreaterEqual(contrast(fg, rgb(v[bg])), 4.5)

    def test_the_primary_button_text_passes_on_its_fill(self):
        for theme, v in THEMES.items():
            with self.subTest(theme=theme):
                self.assertGreaterEqual(contrast(rgb(v["--ground"]), rgb(v["--chalk"])), 4.5)


class TestComponentsNotPageLayout(unittest.TestCase):
    """A2 shapes components (boxes, borders, shadows, the bar). It does not lay a page out: no rule here sets a grid or flex
    direction, an order, columns, or a width on `.stack .split .grid2 main .cards .listings body header`."""

    CONTAINER = re.compile(r"(?<![\w.#-])(?:main|body|header)(?![\w-])|\.(?:stack|split|grid2|cards|listings)(?![\w-])")
    FORBIDDEN = re.compile(r"(?<![\w-])(?:grid-template\w*|flex-direction|order|columns|(?:max-)?width)\s*:")

    def test_no_rule_lays_out_a_page_container(self):
        bare = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
        seen = 0
        for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", bare):
            selector, body = m.group(1).strip(), m.group(2)
            if not any(self.CONTAINER.search(part) for part in selector.split(",")):
                continue
            seen += 1
            with self.subTest(selector=selector):
                self.assertIsNone(self.FORBIDDEN.search(body), body)
        self.assertGreater(seen, 0)  # the method found the header rule; an empty scan would prove nothing

    def test_the_method_does_catch_a_violation(self):
        probe = ".skin-a main { max-width: 40rem; }"
        m = re.search(r"([^{}]+)\{([^{}]*)\}", probe)
        self.assertTrue(self.CONTAINER.search(m.group(1)))
        self.assertTrue(self.FORBIDDEN.search(m.group(2)))


class TestComponentTokens(unittest.TestCase):
    def test_every_component_token_is_declared_in_all_three_scopes(self):
        for scope, values in VALUES.items():
            for token in A_TOKENS:
                with self.subTest(scope=scope, token=token):
                    self.assertIn(token, values)

    def test_the_values_are_the_decided_ones(self):
        want = {
            "light": {"--a-line": "#1E1530", "--a-shadow": "#1E1530", "--a-primary": "#5B3FD0", "--a-on-primary": "#FFFFFF",
                      "--a-link": "#5B3FD0", "--a-focus": "#5B3FD0", "--a-lav": "#B9A6F5", "--a-cit": "#E4F25C",
                      "--a-pch": "#FFB38A", "--a-ink": "#1E1530", "--a-tint": "#F2EDFF"},
            "dark": {"--a-line": "#EDE6FF", "--a-shadow": "#7A5CF0", "--a-primary": "#B9A6F5", "--a-on-primary": "#1E1530",
                     "--a-link": "#CDBEFF", "--a-focus": "#E4F25C", "--a-lav": "#B9A6F5", "--a-cit": "#E4F25C",
                     "--a-pch": "#FFB38A", "--a-ink": "#1E1530", "--a-tint": "#2D2453"},
        }
        for theme, tokens in want.items():
            for name, value in tokens.items():
                with self.subTest(theme=theme, token=name):
                    self.assertEqual(THEMES[theme][name], value)

    def test_the_dark_scopes_agree_on_the_component_tokens(self):
        for token in A_TOKENS:
            with self.subTest(token=token):
                self.assertEqual(VALUES["dark-media"][token], VALUES["dark-attr"][token])

    def test_radius_is_set_once_in_the_base_block(self):
        self.assertEqual(declared(SCOPES["light"]).get("--radius"), "12px")
        self.assertNotIn("--radius", VALUES["dark-media"])
        self.assertNotIn("--radius", VALUES["dark-attr"])

    def test_component_contrast(self):
        for theme, v in THEMES.items():
            with self.subTest(theme=theme, pair="on-primary"):
                self.assertGreaterEqual(contrast(rgb(v["--a-on-primary"]), rgb(v["--a-primary"])), 4.5)
            for bg in SURFACES:
                with self.subTest(theme=theme, bg=bg, token="--a-link"):
                    self.assertGreaterEqual(contrast(rgb(v["--a-link"]), rgb(v[bg])), 4.5)
                for token in ("--a-focus", "--a-line"):
                    with self.subTest(theme=theme, bg=bg, token=token):
                        self.assertGreaterEqual(contrast(rgb(v[token]), rgb(v[bg])), 3.0)
            for fill in ("--a-lav", "--a-cit", "--a-pch"):
                with self.subTest(theme=theme, fill=fill):
                    self.assertGreaterEqual(contrast(rgb(v["--a-ink"]), rgb(v[fill])), 4.5)


def enclosing_media(css, pos):
    """The stack of at-rule preludes open at `pos`, found by walking the braces from the top."""
    stack, start = [], 0
    for i, ch in enumerate(css[:pos]):
        if ch == "{":
            stack.append(css[start:i].strip())
            start = i + 1
        elif ch == "}":
            stack.pop()
            start = i + 1
        elif ch == ";":
            start = i + 1
    return stack


class TestMotion(unittest.TestCase):
    """A2's motion sits behind prefers-reduced-motion: no-preference; sweep.css's own blanket rule covers the rest."""

    BARE = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group(0)), CSS, flags=re.S)

    def test_every_keyframes_is_behind_no_preference(self):
        found = list(re.finditer(r"@keyframes\s+([\w-]+)", self.BARE))
        self.assertEqual({m.group(1) for m in found}, {"a-bob", "a-pop", "a-orbit", "a-wobble", "a-drop", "a-sweep", "a-sweep-paint", "a-sweep-brush", "a-tile-pop", "a-firm", "a-stamp", "a-ink"})  # A6 added the orbit (Search coverage); A7 the credit jar's wobble; A8 the match that drops in; A11 polish: a-sweep (the free bar's brush paints across the track, replacing a-ride), a-tile-pop (a finished search), a-firm (the setup diagram's boards firm up), a-stamp (Confirm's stamp pressed); T2: a-ink (a plan-ticket line that changed is written in again: a citrus wash); pre-merge polish: a-sweep is now only the fade, with a-sweep-paint (a clip-path) and a-sweep-brush (a transform) beside it, so the free bar animates no width
        for m in found:
            with self.subTest(name=m.group(1)):
                self.assertIn("@media (prefers-reduced-motion: no-preference)", enclosing_media(self.BARE, m.start()))

    def test_no_keyframes_animates_a_box_property(self):
        """Pre-merge polish: the free bar's a-sweep animated `width` on an infinite loop (layout, every frame). Nothing in this stylesheet's
        keyframes moves or sizes a box with a layout property: transform, opacity, scale, rotate, clip-path and the like only."""
        layout = r"(?<![\w-])(width|height|min-width|max-width|top|left|right|bottom|inset|margin[\w-]*|padding[\w-]*|flex[\w-]*|gap)\s*:"
        names = re.findall(r"@keyframes\s+([\w-]+)", self.BARE)
        self.assertTrue(names)
        for name in names:
            with self.subTest(keyframes=name):
                body = re.search(r"@keyframes\s+" + re.escape(name) + r"\s*\{((?:[^{}]|\{[^{}]*\})*)\}", self.BARE).group(1)
                self.assertNotRegex(body, layout)

    def test_every_animation_and_transition_is_behind_no_preference_or_is_none(self):
        seen = 0
        for m in re.finditer(r"(?<![\w-])(animation|transition)(?:-[\w-]+)?\s*:\s*([^;}]*)", self.BARE):
            seen += 1
            if m.group(2).strip() == "none":  # the reduce block's harmless override
                continue
            with self.subTest(prop=m.group(0)[:50]):
                self.assertIn("@media (prefers-reduced-motion: no-preference)", enclosing_media(self.BARE, m.start()))
        self.assertGreater(seen, 4)

    def test_the_theme_switch_transition_moved_into_it(self):
        m = re.search(r"\.theme-toggle-knob \{ transition: transform", self.BARE)
        self.assertIsNotNone(m)
        self.assertIn("@media (prefers-reduced-motion: no-preference)", enclosing_media(self.BARE, m.start()))
        self.assertRegex(self.BARE, r"@media \(prefers-reduced-motion: reduce\) \{\s*\.theme-toggle-knob \{ transition: none; \}")

    def test_the_method_does_catch_an_unguarded_declaration(self):
        css = ".a { color: red; }\n@media (prefers-reduced-motion: no-preference) { .b { animation: x 1s; } }\n.c { transition: all 1s; }"
        self.assertEqual(enclosing_media(css, css.index("animation")), ["@media (prefers-reduced-motion: no-preference)", ".b"])
        self.assertEqual(enclosing_media(css, css.index("transition")), [".c"])


class TestComponentRules(unittest.TestCase):
    BARE = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)

    def rule(self, selector):
        for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", self.BARE):
            if m.group(1).strip() == selector:
                return m.group(2)
        self.fail("no rule for " + selector)

    def test_links_take_their_base_colour_at_element_specificity(self):
        self.assertIn("color: var(--a-link)", self.rule(":where(.skin-a) a"))
        self.assertIn("color: var(--chalk)", self.rule(":where(.skin-a) a:where(:hover)"))

    def test_the_peek_marker_fully_resets_sweep_css_s_triangle(self):
        body = self.rule(".skin-a .peek > summary::before")
        self.assertRegex(body, r"border:\s*2px solid var\(--a-line\)")  # a shorthand, so border-right-width:0 and the transparent sides go
        self.assertNotRegex(body, r"border-(left|top|right|bottom)")
        self.assertIn("transform: none", body)
        self.assertRegex(body, r"width:\s*24px")
        self.assertRegex(body, r"height:\s*24px")
        self.assertIn("transform: none", self.rule(".skin-a .peek[open] > summary::before"))

    def test_the_sticker_buttons_press_and_lift(self):
        self.assertIn("translate(-2px, -2px)", self.rule(".skin-a button.primary:hover, .skin-a a.primary:hover"))
        self.assertIn("translate(2px, 2px)", self.rule(".skin-a button.primary:active, .skin-a a.primary:active,\n"
                                                      ".skin-a button.secondary:active, .skin-a a.secondary:active"))

    def test_a_disabled_button_is_not_yet_and_stays_readable(self):
        """A2 review: a disabled primary can be the screen's one decision (Confirm over credit, before "run anyway").
        At opacity .5 its label measured 2.39:1. It stays at full opacity: slate words on the tint, no lift."""
        base = self.rule(".skin-a button[disabled], .skin-a button[disabled]:hover, .skin-a button[disabled]:active")
        self.assertIn("opacity: 1", base)
        self.assertIn("transform: none", base)
        look = self.rule(
            ".skin-a button.primary[disabled], .skin-a button.primary[disabled]:hover, .skin-a button.primary[disabled]:active,\n"
            ".skin-a button.secondary[disabled], .skin-a button.secondary[disabled]:hover, .skin-a button.secondary[disabled]:active")
        self.assertIn("background: var(--a-tint)", look)
        self.assertIn("color: var(--slate)", look)
        self.assertIn("box-shadow: none", look)
        for theme, v in THEMES.items():
            with self.subTest(theme=theme):
                self.assertGreaterEqual(contrast(rgb(v["--slate"]), rgb(v["--a-tint"])), 4.5)

    def test_hidden_tips_stay_hidden_despite_display_flex(self):
        self.assertIn("display: none", self.rule(".skin-a .tip[hidden], .skin-a .tip-x[hidden]"))

    def test_no_component_rule_uses_a_raw_colour(self):
        a2 = re.sub(r"/\*.*?\*/", "", CSS[CSS.index("==== A2: the shared components"):], flags=re.S)
        self.assertNotRegex(a2, r"#[0-9A-Fa-f]{3,8}\b")
        self.assertNotRegex(a2, r"rgba?\(")


class TestTheShell(unittest.TestCase):
    def test_the_skin_class_exists_only_for_public_mode(self):
        self.assertEqual(BASE.count('class="skin-a"'), 1)
        self.assertRegex(BASE, r'<html lang="en"\{% if public_mode %\} class="skin-a"\{% endif %\}>')

    def test_the_skin_assets_are_referenced_and_the_console_meta_is_kept(self):
        for needle in ("sweep-a.css", "theme.js", "tips.js", "mark_a", "Instrument+Sans", "data-theme-toggle",
                       '<meta name="theme-color" content="#03161c">'):
            with self.subTest(needle=needle):
                self.assertIn(needle, BASE)
        self.assertNotIn("defer src=\"{{ url_for('static', filename='theme.js')", BASE)  # it must run before first paint

    def test_the_switch_is_a_real_button_with_a_name_and_a_state(self):
        tag = re.search(r"<button[^>]*data-theme-toggle[^>]*>", BASE).group(0)
        for attr in ('type="button"', 'aria-pressed="false"'):
            self.assertIn(attr, tag)
        # Its name is real text, as every button in the app carries (test_multi_setup), not only an aria-label.
        body = re.search(r"<button[^>]*data-theme-toggle[^>]*>(.*?)</button>", BASE, re.S).group(1)
        self.assertIn('<span class="visually-hidden">Dark mode</span>', body)


class TestWhatIsSent(unittest.TestCase):
    """The real `/` in each mode."""

    def test_a_public_visitor_gets_the_skin(self):
        html = unlocked(public_app()).get("/").get_data(as_text=True)
        for needle in ('<html lang="en" class="skin-a">', "sweep-a.css", "theme.js", "data-theme-toggle",
                       'viewBox="0 0 36 36"', 'fill="var(--a-lav)"',
                       '<script defer src="/static/tips.js"></script>',
                       "Instrument+Sans", 'content="#FFF6EE" media="(prefers-color-scheme: light)"',
                       'content="#151024" media="(prefers-color-scheme: dark)"'):
            with self.subTest(needle=needle):
                self.assertIn(needle, html)
        self.assertNotIn("Geist", html)
        self.assertNotIn("#03161c", html)
        self.assertLess(html.index("theme.js"), html.index("<body") if "<body" in html else len(html))
        self.assertLess(html.index("theme.js"), html.index("tips.js"))
        self.assertNotIn('viewBox="0 0 32 32"', html)  # the console's mark is not the public one

    def test_the_console_gets_none_of_it(self):
        with mock.patch.dict(os.environ, {"SWEEP_PUBLIC_MODE": ""}, clear=False):
            app = app_module.create_app(state={"derived": dict(DERIVED), "resume_text": "x"},
                                        extract=lambda p: "x", derive=lambda t, p: DERIVED)
        app.config["TESTING"] = True
        html = app.test_client().get("/").get_data(as_text=True)
        for needle in ("skin-a", "sweep-a.css", "theme.js", "tips.js", "data-theme-toggle", "Instrument+Sans", "FFF6EE",
                       "--a-lav", 'viewBox="0 0 36 36"'):
            with self.subTest(needle=needle):
                self.assertNotIn(needle, html)
        self.assertIn('<html lang="en">', html)
        self.assertIn('theme-color" content="#03161c"', html)
        self.assertIn("family=Geist:wght@400;500;600;700", html)
        self.assertIn('viewBox="0 0 32 32"', html)  # the old mark, unchanged
        self.assertIn('width="22" height="22"', html)


class TestTheMacros(unittest.TestCase):
    """_a.html through the app's own Jinja environment."""

    @classmethod
    def setUpClass(cls):
        cls.app = public_app()

    def render(self, source):
        with self.app.test_request_context("/"):
            return self.app.jinja_env.from_string('{% from "_a.html" import peek, tip, stamp, mbar %}' + source).render()

    def test_peek_is_a_native_details_with_a_summary_and_a_body(self):
        html = self.render('{% call peek("More", "optional") %}<p>Inside</p>{% endcall %}')
        self.assertIn('<details class="peek"><summary>', html)
        self.assertIn('<span class="peek-label">More</span>', html)
        self.assertIn('<span class="peek-aside">optional</span>', html)
        self.assertIn('<div class="peek-body"><p>Inside</p></div></details>', html)
        self.assertNotIn(" open", html)

    def test_peek_without_an_aside_has_no_aside_and_escapes_its_label(self):
        html = self.render('{% call peek("A <b>") %}x{% endcall %}')
        self.assertNotIn("peek-aside", html)
        self.assertIn("A &lt;b&gt;", html)

    def test_tip_carries_its_id_a_decorative_face_and_a_hidden_dismiss(self):
        html = self.render('{{ tip("upload-1", "Try a PDF.") }}')
        self.assertIn('<aside class="tip" data-tip="upload-1" aria-label="Tip">', html)
        self.assertIn('<span class="tip-face" aria-hidden="true">', html)
        self.assertIn('<p class="tip-say">Try a PDF.</p>', html)
        self.assertRegex(html, r'<button type="button" class="tip-x" data-tip-dismiss aria-label="Dismiss tip" hidden>')
        self.assertNotIn("tabindex", html)

    def test_tip_text_is_escaped(self):
        self.assertIn("&lt;script&gt;", self.render('{{ tip("x", "<script>") }}'))

    def test_stamp(self):
        self.assertEqual(self.render('{{ stamp("Free") }}').strip(), '<span class="stamp">Free</span>')

    def test_mbar_wraps_what_it_is_given(self):
        html = self.render('{% call mbar() %}<span class="mbar-text"><b>3</b> picked</span>{% endcall %}')
        self.assertEqual(html.strip(), '<div class="mbar"><span class="mbar-text"><b>3</b> picked</span></div>')


if __name__ == "__main__":
    unittest.main()
