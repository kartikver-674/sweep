"""The shared visual rules (design phase D3): what the colours mean and what
the type floor is, pinned so they cannot drift back without a test saying so.

Nothing here is about a screen. Amber is money and the brand mark; teal is free
and done; coral is an error; chalk is everything else (focus, selection,
progress, where you are). Type a person has to read is at least 12px, and a
label is a word in sentence case, not a 10px uppercase micro-caption. These read
the stylesheet, as the D2 tests do: the arithmetic is the contract.
"""
import pathlib
import re
import unittest

from sweep import app as app_module

CSS = pathlib.Path(app_module.__file__).parent / "static" / "sweep.css"


def rule(css, selector):
    """The body of the first rule whose selector list starts a line with `selector`."""
    m = re.search(r"^" + re.escape(selector) + r"[^{]*\{([^}]*)\}", css, re.M)
    assert m, selector
    return m.group(1)


class TestWhatTheColoursMean(unittest.TestCase):
    css = CSS.read_text()

    def test_the_focus_ring_is_chalk_never_amber(self):
        ring = re.search(r"a:focus-visible, button:focus-visible[^{]*\{([^}]*)\}", self.css).group(1)
        self.assertIn("outline: 2px solid var(--chalk)", ring)
        self.assertNotIn("--paid", ring)

    def test_selection_and_progress_are_neutral(self):
        self.assertIn("accent-color: var(--chalk)", rule(self.css, 'input[type="checkbox"], input[type="radio"]'))
        self.assertNotIn("--paid", rule(self.css, ".choice:has(:checked)"))
        self.assertIn("inset 2px 0 0 var(--chalk)", rule(self.css, ".choice:has(:checked)"))
        for selector in (".stepper button:hover", ".drop:hover, .drop.over", ".activity-fill",
                         ".working-bar span", ".weights .bar > span", ".runbar.live .runbar-dot",
                         ".activity.live .activity-dot", ".stages li.now::before", ".step.current .marker"):
            with self.subTest(selector=selector):
                self.assertNotIn("--paid", rule(self.css, selector), selector)

    def test_a_link_is_chalk_and_underlined_not_teal(self):
        body = rule(self.css, "a ")
        self.assertIn("color: var(--chalk)", body)
        self.assertIn("text-decoration: underline", body)
        self.assertNotIn("--free", body)

    def test_the_primary_hover_comes_from_a_token(self):
        self.assertNotIn("#fff;", self.css)
        self.assertIn("background: var(--chalk-lift)", rule(self.css, "button.primary:hover"))

    def test_amber_does_not_spread(self):
        """15 lines of CSS still name var(--paid). Thirteen are cost or the brand
        (.paid, the meter, the headline figure, .affects, .costs, paid cells and
        their legend, the key balance, the progress ledger's figure); two lines,
        in one rule, are amber that is NOT money and are on the notes' list for the
        later phases (.callout.warn). D5 migrated .cell.running and its legend,
        .numeral-inline b and .banner.warn; D6 migrated the applied tick. The next-steps
        numerals went in D4. The number may fall as the others are migrated. It may not
        rise: a new use has to be argued for here, in a test, not slipped in."""
        lines = [ln for ln in self.css.splitlines()
                 if "var(--paid" in ln and not ln.lstrip().startswith(("/*", "*", "running.html"))]
        self.assertLessEqual(len(lines), 15, "\n".join(lines))

    def test_a_step_is_not_money(self):
        steps = rule(self.css, ".next-steps > li::before")
        self.assertNotIn("--paid", steps)
        self.assertRegex(steps, r"font-size: 1[2-9]px")


class TestTheTypeFloor(unittest.TestCase):
    css = CSS.read_text()

    def test_body_is_fourteen_and_a_label_is_a_word(self):
        self.assertIn("font: 400 14px/1.55", rule(self.css, "body "))
        label = rule(self.css, ".label ")
        self.assertIn("font-size: 12px", label)
        self.assertNotIn("uppercase", label)
        self.assertNotIn("letter-spacing", label)

    def test_what_people_read_is_twelve_or_more(self):
        for selector in (".meta ", ".tag ", ".chip ", ".credit ", ".tracker-at ", ".meter-facts "):
            body = rule(self.css, selector)
            size = re.search(r"font-size: (\d+)px", body)
            with self.subTest(selector=selector):
                self.assertGreaterEqual(int(size.group(1)), 12, selector)
        self.assertRegex(rule(self.css, 'th[scope="col"]'), r"font-size: 12px")

    def test_headings_are_balanced_and_h3_is_not_the_display_face(self):
        self.assertIn("text-wrap: balance", rule(self.css, "h1 "))
        self.assertIn("text-wrap: balance", rule(self.css, "h2 "))
        self.assertNotRegex(self.css, r"h1, h2, h3[^{]*\{[^}]*--display")
        self.assertIn("var(--text)", rule(self.css, "h3 "))


class TestThePreferencesRows(unittest.TestCase):
    """Phase D4: what a settings row and a résumé row promise."""
    css = CSS.read_text()

    def test_what_marks_a_cost_is_twelve_pixels_of_words_and_amber(self):
        body = rule(self.css, ".affects ")
        self.assertIn("font: 600 12px/16px", body)
        self.assertIn("var(--paid)", body)
        self.assertNotIn("uppercase", body)
        self.assertNotIn("letter-spacing", body)

    def test_the_summary_names_are_words_not_captions(self):
        body = rule(self.css, ".summary dt ")
        self.assertIn("font-size: 12px", body)
        self.assertNotIn("uppercase", body)

    def test_a_setting_is_a_ruled_row_with_its_name_beside_it(self):
        self.assertIn("border-top: 1px solid var(--rule)", rule(self.css, ".setting "))
        self.assertNotIn("background", rule(self.css, ".setting "))
        self.assertRegex(self.css, r"@media \(min-width: 48rem\) \{\s*\.setting \{ grid-template-columns: minmax\(11rem, 15rem\)")
        # Advanced is a door between rows and has no box of its own.
        door = rule(self.css, "details.advanced ")
        self.assertNotIn("background", door)
        self.assertNotIn("border:", door.replace("border-top", ""))

    def test_the_drop_zone_is_the_one_dashed_edge_and_compacts(self):
        self.assertIn("1px dashed var(--control)", rule(self.css, ".drop "))
        self.assertIn("flex-direction: row", rule(self.css, ".drop.compact "))
        self.assertNotIn("dashed", rule(self.css, ".picked-row "))

    def test_remove_is_the_error_colour_and_a_word(self):
        body = rule(self.css, "button.tertiary.danger ")
        self.assertIn("var(--over)", body)
        self.assertNotIn("background", body)
        self.assertIn("margin-left: auto", rule(self.css, ".row-actions .a-danger "))

    def test_the_row_actions_fall_into_two_lines_on_a_phone(self):
        phone = self.css[self.css.index("/* A phone: the four groups fall into two lines"):]
        self.assertIn('grid-template-areas: "main state ." "arrange arrange danger";', phone)
        self.assertIn("@media (max-width: 40rem)", phone)


class TestActionsHaveThreeWeights(unittest.TestCase):
    css = CSS.read_text()

    def test_primary_secondary_tertiary_are_distinct(self):
        self.assertIn("background: var(--chalk)", rule(self.css, "button.primary, a.primary"))
        self.assertIn("border: 1px solid var(--control)", rule(self.css, "button.secondary, a.secondary"))
        tertiary = rule(self.css, "button.tertiary, a.tertiary")
        self.assertIn("text-decoration: underline", tertiary)
        self.assertIn("border: 0", tertiary)
        self.assertIn("translateY(1px)", self.css[self.css.index("button.primary:active"):][:200])

    def test_a_touch_target_includes_a_tertiary_action(self):
        touch = self.css[self.css.index("@media (pointer: coarse) {\n  .stepper button"):]
        self.assertRegex(touch, r"button, \.primary, \.secondary, \.tertiary[^{]*\{ min-height: 44px; \}")


class TestMotionAndTheKeyboard(unittest.TestCase):
    css = CSS.read_text()

    def test_reduced_motion_reaches_pseudo_elements(self):
        """`*` does not match ::before, and the status and passes pulses are drawn
        there. The literal `* {...}` line stays (other tests pin it) and the
        pseudo-element rule sits beside it, ahead of the Motion section."""
        blanket = "* { transition: none !important; animation: none !important; }"
        pseudo = "*::before, *::after { transition: none !important; animation: none !important; }"
        self.assertIn(blanket, self.css)
        self.assertIn(pseudo, self.css)
        self.assertLess(self.css.index(pseudo), self.css.index("/* ---- Motion "))

    def test_no_transition_names_all(self):
        self.assertNotRegex(self.css, r"transition:\s*all\b")

    def test_a_sticky_header_cannot_cover_a_focused_control(self):
        self.assertRegex(self.css, r"html \{ scroll-padding-top: [\d.]+rem; \}")
        self.assertIn("touch-action: manipulation", self.css)

    def test_the_page_says_its_colour(self):
        base = (pathlib.Path(app_module.__file__).parent / "templates" / "base.html").read_text()
        self.assertIn('<meta name="theme-color" content="#03161c">', base)
        self.assertIn("--ground: #03161c", self.css)


if __name__ == "__main__":
    unittest.main()
