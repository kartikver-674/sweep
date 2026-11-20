"""Direction A, the A11 owner-feedback polish: the parts that are not one screen's own (each screen's polish is pinned in its A-stage
test). The favicon (the A brush mark on public pages, the console's own icon untouched), the theme-colour metas (A1's, still right), and
peek.js (the open / close animation of every disclosure: loaded once, deferred, public pages only; its behaviour is peek_test.js).
Fakes only: no network, no model, no real token."""
import hashlib
import pathlib
import re
import unittest
import xml.etree.ElementTree as ET

from sweep import app as app_module
from sweep.tests.test_a3_copy import console_pages
from sweep.tests.test_a6_key import key_page

ROOT = pathlib.Path(app_module.__file__).parent
STATIC = ROOT / "static"
BASE = (ROOT / "templates" / "base.html").read_text()
MARK = (ROOT / "templates" / "_mark.html").read_text()
CSS = (STATIC / "sweep-a.css").read_text()
SVG = "{http://www.w3.org/2000/svg}"

CONSOLE_ICON = '<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">'
FAVICON_SHA = "015e0722b98b025a0115833eab991592408641df22f138e251635a534b5fdbfb"          # the console's favicon.svg at HEAD (54a014a), which this polish does not touch
PUBLIC_ICON = '<link rel="icon" type="image/svg+xml" href="/static/favicon-a.svg">'


class TestFavicon(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.public, _ = key_page()
        cls.console = console_pages()

    def test_public_pages_point_at_the_a_mark(self):
        self.assertEqual(self.public.count(PUBLIC_ICON), 1)
        self.assertEqual(self.public.count('rel="icon"'), 1)
        self.assertNotIn("/static/favicon.svg", self.public)

    def test_the_console_keeps_its_own_icon_byte_for_byte(self):
        for path, html in self.console.items():
            with self.subTest(path=path):
                self.assertEqual(html.count(CONSOLE_ICON), 1)
                self.assertNotIn("favicon-a", html)
        self.assertEqual(hashlib.sha256((STATIC / "favicon.svg").read_bytes()).hexdigest(), FAVICON_SHA)

    def test_the_a_icon_is_the_brush_mark_mark_a_draws_on_a_lavender_tile(self):
        root = ET.parse(STATIC / "favicon-a.svg").getroot()
        self.assertEqual(root.attrib["viewBox"], "0 0 36 36")                      # the grid mark_a is drawn on
        rect, handle, bristles = list(root)
        self.assertEqual((rect.tag, rect.attrib["fill"], rect.attrib["stroke"], rect.attrib["rx"]), (SVG + "rect", "#B9A6F5", "#1E1530", "11"))
        self.assertEqual((handle.attrib["stroke"], bristles.attrib["fill"], bristles.attrib["stroke"]), ("#1E1530", "#E4F25C", "#1E1530"))
        macro = MARK[MARK.index("macro mark_a"):]
        self.assertEqual([handle.attrib["d"], bristles.attrib["d"]], re.findall(r'<path d="([^"]+)"', macro))
        self.assertEqual(re.findall(r'<rect x="(\d+)" y="(\d+)" width="(\d+)" height="(\d+)"', macro),
                         [(rect.attrib["x"], rect.attrib["y"], rect.attrib["width"], rect.attrib["height"])])

    def test_the_a_icon_uses_the_tokens_values_not_variables_because_a_tab_has_no_page_to_inherit_from(self):
        text = (STATIC / "favicon-a.svg").read_text()
        self.assertNotIn("var(", text)
        for token, value in (("--a-lav", "#B9A6F5"), ("--a-cit", "#E4F25C"), ("--a-ink", "#1E1530")):
            self.assertIn(f"{token}: {value};", CSS.split("@media")[0])           # the light tokens, which are the same in dark for these three
            self.assertIn(value, text)

    def test_it_is_served(self):
        client = app_module.create_app(state={}).test_client()
        got = client.get("/static/favicon-a.svg")
        self.assertEqual((got.status_code, got.mimetype), (200, "image/svg+xml"))


class TestThemeColourMetas(unittest.TestCase):
    """A1's metas are the page ground in each theme, and still are."""

    def test_they_equal_the_grounds(self):
        light = re.search(r"\.skin-a \{[^}]*--ground: (#[0-9A-Fa-f]{6});", CSS).group(1)
        dark = re.search(r'\.skin-a\[data-theme="dark"\] \{[^}]*--ground: (#[0-9A-Fa-f]{6});', CSS).group(1)
        self.assertIn(f'<meta name="theme-color" content="{light}" media="(prefers-color-scheme: light)">', BASE)
        self.assertIn(f'<meta name="theme-color" content="{dark}" media="(prefers-color-scheme: dark)">', BASE)
        self.assertIn('<meta name="theme-color" content="#03161c">', BASE)      # the console's, as it was


class TestPeekScriptIsLoadedOnPublicPagesOnly(unittest.TestCase):
    TAG = '<script defer src="/static/peek.js"></script>'

    def test_public_pages_load_it_once_deferred_after_tips(self):
        body, _ = key_page()
        self.assertEqual(body.count(self.TAG), 1)
        self.assertLess(body.index("tips.js"), body.index("peek.js"))

    def test_the_console_does_not(self):
        for path, html in console_pages().items():
            with self.subTest(path=path):
                self.assertNotIn("peek.js", html)

    def test_base_names_it_inside_the_public_branch_only(self):
        at = BASE.index("peek.js")
        self.assertLess(BASE.rindex("{% if public_mode %}", 0, at), at)
        self.assertLess(at, BASE.index("{% endif %}", at))
        self.assertNotIn("{% else %}", BASE[BASE.rindex("{% if public_mode %}", 0, at):at])
        self.assertEqual(BASE.count("peek.js"), 1)

    def test_it_is_plain_dom_listens_on_the_capture_phase_and_leaves_reduced_motion_to_the_browser(self):
        js = (STATIC / "peek.js").read_text()
        code = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
        self.assertNotIn("Alpine", code)
        self.assertIn("}, true);", code)                                          # capture: Why it matched stops its own clicks (@click.stop)
        self.assertIn('"(prefers-reduced-motion: reduce)"', code)
        self.assertIn("e.preventDefault();", code)
        self.assertEqual(len(re.findall(r"addEventListener\(", code)), 1)
        self.assertNotIn("keydown", code)                                         # Enter and Space reach it as the click they become

    def test_the_results_row_script_still_leaves_a_summary_click_alone(self):
        results = (ROOT / "templates" / "results.html").read_text()
        self.assertIn('if (e.target.closest("a, button, input, label, summary")) {', results)
        self.assertIn("<details class=\"why\" @click.stop>", results)


if __name__ == "__main__":
    unittest.main()
