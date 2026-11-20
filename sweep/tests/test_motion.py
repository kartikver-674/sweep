"""D7B: the Quiet Ledger motion system (docs/design/SWEEP_D7_MOTION_DIRECTION.md, docs/design/SWEEP_D7B_MOTION_INTEGRATION.md).

One idea: motion says what changed, and nothing else. Five verbs: PRESS, WRITE IN, DIM and UN-DIM, OPEN, MARK.
What these pin is the contract, so that it cannot drift back without a test saying so: the tokens, the things that
were deleted, what is allowed to move, that every animation waits for `no-preference`, that a money figure is
written and never counted, that the dim is AA-safe, that the two small scripts can only add and remove a class,
and the timing of the Results redirect. What CANNOT be said from markup (a 240-row list is no slower to arrive, a
quick tab is instant, the page never sticks dimmed, Firefox and WebKit degrade) is measured in a real browser by
docs/design/motion-d7b/harness/verify-results.mjs, verify-progress.mjs and verify-forms.mjs, and kept in output/design-D7B/.

Fakes only: no model, provider or network.
"""
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

from sweep import app as app_module
from sweep.tests.test_app import DERIVED, RAW_PLAN
from sweep.tests.test_progress_ui import running
from sweep.tests.test_results_ui import legacy_app, page, row
from sweep.tests.test_upload_configure_ui import configure
import sweep.tests.test_multi_results_view as rv

setUpModule, tearDownModule = rv.setUpModule, rv.tearDownModule

HERE = pathlib.Path(app_module.__file__).parent
CSS = (HERE / "static" / "sweep.css").read_text(encoding="utf-8")
TEMPLATES = {p.name: p.read_text(encoding="utf-8") for p in (HERE / "templates").glob("*.html")}
MOTION = CSS[CSS.index("/* ---- Motion "):CSS.index("/* ---- Attached keys")]


def nc(css):
    """`css` without its comments, which name the very things the tests look for."""
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


class Quiet(unittest.TestCase):
    """The stylesheet and the pages are hundreds of kilobytes: say what was missing, not the haystack."""
    def assertIn(self, needle, hay, msg=None):
        if needle not in hay:
            self.fail(msg or "missing: %r" % (needle,))

    def assertNotIn(self, needle, hay, msg=None):
        if needle in hay:
            self.fail(msg or "found: %r" % (needle,))

    def assertRegex(self, text, pattern, msg=None):
        if not re.search(pattern, text):
            self.fail(msg or "no match for: %r" % (pattern,))

    def assertNotRegex(self, text, pattern, msg=None):
        m = re.search(pattern, text)
        if m:
            self.fail(msg or "matched %r: %r" % (pattern, m.group(0)[:200]))


# ---------------------------------------------------------------------------------------------
def block(css, header):
    """The bodies of every `header { ... }` block in `css` (braces balanced)."""
    out, at = [], 0
    while True:
        i = css.find(header, at)
        if i < 0:
            return out
        j = css.index("{", i)
        depth, k = 1, j + 1
        while depth:
            depth += {"{": 1, "}": -1}.get(css[k], 0)
            k += 1
        out.append(css[j + 1:k - 1])
        at = k


def without(css, header):
    """`css` with every `header { ... }` block removed."""
    for inner in block(css, header):
        css = css.replace(inner, "")
    return css


NO_PREF = "@media (prefers-reduced-motion: no-preference)"
MOT = nc("".join(block(MOTION, NO_PREF)))        # everything that moves, comments stripped


def rule(selector, css=CSS):
    m = re.search(r"(?:^|\n)\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    return m.group(1) if m else ""


def hexrgb(h):
    return [int(h[i:i + 2], 16) for i in (1, 3, 5)]


def lum(rgb):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def token(name):
    m = re.search(r"--" + re.escape(name) + r":\s*(#[0-9a-fA-F]{6})", CSS[:CSS.index("* { box-sizing")])
    return hexrgb(m.group(1))


def after_dimming(fg, bg, alpha):
    """Text and background of a group at `alpha` over the page ground: what the eye gets."""
    ground = token("ground")
    mix = lambda c: [alpha * x + (1 - alpha) * g for x, g in zip(c, ground)]
    hi, lo = sorted((lum(mix(fg)), lum(mix(bg))), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def tokens_of(css):
    return dict(re.findall(r"(--[\w-]+):\s*([^;]+);", nc(css)))


def dimmed_by_the_pending_level(css=CSS):
    """(selector, body) of every rule that sets opacity to --pending-dim, selectors split."""
    out = []
    for group, body in re.findall(r"([^{}]+)\{([^{}]*\bopacity:\s*var\(--pending-dim\)[^{}]*)\}", nc(css)):
        out += [(part.strip(), body) for part in group.split(",") if part.strip() != "from"]
    return out


# ---------------------------------------------------------------------------------------------
class TheTokens(Quiet):
    root = tokens_of(block(MOTION, ":root")[0]) if block(MOTION, ":root") else {}

    def test_they_are_the_approved_ones(self):
        self.assertEqual({k: v for k, v in self.root.items() if not k.startswith("--ease")}, {
            "--ms-1": "120ms", "--ms-2": "160ms", "--ms-3": "200ms",
            "--row-fade": "140ms", "--row-step": "20ms",
            "--tool-in": "var(--ms-3)", "--tool-out": "140ms",
            "--pending-dim": ".85", "--pending-slate": "#aa9885",
        })
        self.assertEqual(self.root["--ease-settle"], "cubic-bezier(.22, .61, .36, 1)")
        self.assertEqual(self.root["--ease-leave"], "cubic-bezier(.4, 0, 1, 1)")

    def test_every_one_is_used_and_none_is_left_over(self):
        for name in self.root:
            with self.subTest(token=name):
                self.assertGreaterEqual(len(re.findall(r"var\(" + re.escape(name) + r"\b", CSS)), 1, name)

    def test_the_dim_is_not_seventy_or_fifty_anywhere(self):
        self.assertEqual(sorted(sel for sel, _ in dimmed_by_the_pending_level()),
                         [".headline-figure.updating", ".lines.updating", ".meter.updating", ".pending .results-body"])
        # and no other rule in the product dims to a literal level on a state that can last
        self.assertNotRegex(nc(CSS), r"\.(updating|pending)[^{]*\{[^}]*opacity:\s*\.[0-9]")


class WhatIsBanned(Quiet):
    def test_nothing_the_brief_rules_out_is_in_the_stylesheet(self):
        for pattern in (r"will-change", r"transition:\s*all\b", r"blur\(", r"backdrop-filter", r"animation-timeline",
                        r"scroll-timeline", r"view-transition", r"perspective", r"cubic-bezier\([^)]*-\d"):
            with self.subTest(pattern=pattern):
                self.assertNotRegex(re.sub(r"/\*.*?\*/", "", CSS, flags=re.S), pattern)

    def test_only_liveness_loops(self):
        loops = set(re.findall(r"animation:\s*([\w-]+)[^;{}]*infinite", CSS))
        self.assertEqual(loops, {"runpulse", "pulse", "slide", "bone-sweep", "cellbreath"},
                         "a new infinite animation has to be argued for here, in a test")

    def test_only_the_indeterminate_bar_moves_anything(self):
        """Opacity and colour say what changed. The indeterminate bar slides (there is no fraction to show, so it is not a
        bar that fills). Nothing else travels, scales or rotates: not even a finished search, which changes colour."""
        moving = {m.group(1) for m in re.finditer(r"@keyframes\s+([\w-]+)\s*\{((?:[^{}]|\{[^{}]*\})*)\}", CSS)
                  if re.search(r"translate|scale|rotate|skew", m.group(2))}
        self.assertEqual(moving, {"slide"})

    def test_no_keyframe_is_dead(self):
        for name in re.findall(r"@keyframes\s+([\w-]+)", CSS):
            with self.subTest(keyframes=name):
                self.assertRegex(CSS, r"animation(?:-name)?:[^;]*\b" + re.escape(name) + r"\b", name)

    def test_what_was_deleted_stays_deleted(self):
        for gone in ("rail-draw", "cap-drop", "cap-cross", "section-in", "first-paint", "@keyframes rise", "@keyframes arrive", "tile-land", "data-was-done",
                     ".reveal", ".search-grid .cell:nth-child(8n", "animation-delay: 10ms", "animation-delay: 70ms",
                     "scaleX(1.04)", "translateX(-3px)", "cap-cross-shake"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, CSS)
        self.assertNotIn("animation: rise", CSS)

    def test_no_template_or_script_keeps_the_old_hooks(self):
        for name, source in TEMPLATES.items():
            for gone in ("first-paint", "sweep.drawn", "sweepCount", "motion.js", " reveal r", "reveal r", "data-was-done", "tile-land"):
                with self.subTest(template=name, gone=gone):
                    self.assertNotIn(gone, source)
        self.assertFalse((HERE / "static" / "motion.js").exists())
        self.assertFalse((HERE / "tests" / "motion_test.js").exists())


class ReducedMotion(Quiet):
    def test_the_blanket_rule_stays_as_the_net_and_comes_first(self):
        blanket = "* { transition: none !important; animation: none !important; }"
        self.assertIn(blanket, CSS)
        self.assertLess(CSS.index(blanket), CSS.index("/* ---- Motion "))

    def test_every_animation_and_transition_this_phase_added_waits_for_no_preference(self):
        outside = without(MOTION, NO_PREF)
        self.assertEqual(len(block(MOTION, NO_PREF)), 1, "one opt-in block, so the rule is easy to audit")
        self.assertNotRegex(outside, r"\b(animation|transition)\s*:")
        self.assertNotIn("@keyframes", outside)
        self.assertNotIn("@starting-style", outside)

    def test_the_states_are_not_motion_so_they_are_outside_it(self):
        # the dim, and the amber-to-coral of a figure over its cap, are the same with reduced motion: instant and complete
        outside = without(MOTION, NO_PREF)
        self.assertIn(".pending .results-body", outside)
        self.assertIn("opacity: var(--pending-dim)", outside)

    def test_the_alpine_hooks_exist_only_inside_no_preference(self):
        # t-from etc. describe the half-open start of a move. Outside no-preference a reader who asked for less would be shown
        # the hidden start state for the frames Alpine waits before it cleans up.
        # (`.t-out { display: none; }` is the one exception, and it is the opposite of a start state: see the next test)
        outside = without(CSS, NO_PREF).replace(".t-out { display: none; }", "")
        for hook in (".t-from", ".t-to", ".t-in", ".t-out", ".m-from", ".m-to", ".m-in"):
            with self.subTest(hook=hook):
                self.assertNotIn(hook, outside)
                self.assertIn(hook, "".join(block(CSS, NO_PREF)))

    def test_a_leaving_panel_is_gone_at_once_unless_its_height_is_animating(self):
        """Switching Filter and sort for Export: Alpine shows the entering panel a frame after it marks the leaving one, and keeps the
        leaving one for a frame or two after that. With nothing animating its height (reduced motion, Firefox, Safari) the list jumped
        a panel lower for one to two painted frames and straight back (Chrome, Firefox and WebKit, measured in D7B's browser pass)."""
        rule = ".t-out { display: none; }"
        self.assertEqual(CSS.count(rule), 1)
        self.assertNotIn(rule, "".join(block(CSS, NO_PREF)), "the reduced-motion reader needs it most")
        self.assertLess(CSS.index(rule), CSS.index(NO_PREF))
        supported = block(MOTION, "@supports (interpolate-size: allow-keywords)")
        self.assertEqual(len(supported), 1)
        self.assertIn(".t-out { display: block; }", supported[0], "the animated close keeps the panel on screen while its height goes")

    def test_reduced_motion_is_not_a_shorter_animation(self):
        """Inside a reduce block every animation or transition declaration is `none` or zero: nothing is shortened, softened or swapped."""
        blocks = block(nc(CSS), "@media (prefers-reduced-motion: reduce)")
        self.assertGreaterEqual(len(blocks), 3, "the blanket rule and the explicit end states")
        for inner in blocks:
            for prop, value in re.findall(r"\b((?:animation|transition)[\w-]*)\s*:\s*([^;}]+)", inner):
                with self.subTest(prop=prop, value=value):
                    self.assertRegex(value.strip(), r"^(none|0s?\b)", "reduced motion removes motion, it does not shorten it")


# ---------------------------------------------------------------------------------------------
class ThePendingDimIsAASafe(Quiet):
    dim = 0.85
    grounds = ("ground", "well", "surface", "surface-low")

    def test_the_level_is_the_token(self):
        self.assertEqual(TheTokens.root["--pending-dim"], ".85")

    def test_the_muted_tone_alone_is_not_enough_on_a_raised_surface(self):
        """Measured, not assumed (D7A's table was on the ground only): --slate on --surface, which is a phone's result card,
        the Configure panel and the console meter, is 5.18:1 at rest and 4.11:1 at .85. That is why a dimmed region lifts it."""
        self.assertGreaterEqual(after_dimming(token("slate"), token("ground"), self.dim), 4.5)
        self.assertLess(after_dimming(token("slate"), token("surface"), self.dim), 4.5)

    def test_every_dimmed_region_lifts_the_muted_tone_and_nothing_else_does(self):
        for selector, body in dimmed_by_the_pending_level():
            with self.subTest(selector=selector):
                self.assertIn("--slate: var(--pending-slate)", body)
        # never at rest: the only places --slate is reassigned are the dimmed regions
        sets = [m.group(0) for m in re.finditer(r"[^{}]*\{[^{}]*--slate:[^{}]*\}", nc(CSS))]
        self.assertEqual(len(sets), 3, "the root token, the Configure regions' one rule and Results' one rule")
        self.assertEqual(sum("var(--pending-slate)" in s_ for s_ in sets), 2)

    def test_text_stays_aa_in_every_dimmed_region_on_every_ground(self):
        lifted = hexrgb(re.search(r"--pending-slate:\s*(#[0-9a-fA-F]{6})", CSS).group(1))
        for bg in self.grounds:
            for name, fg in (("muted (lifted)", lifted), ("chalk", token("chalk")), ("warm", token("warm")), ("free", token("free")),
                             ("paid", token("paid")), ("paid-lift", token("paid-lift")), ("over", token("over"))):
                with self.subTest(fg=name, bg=bg):
                    self.assertGreaterEqual(after_dimming(fg, token(bg), self.dim), 4.5)

    def test_the_lifted_tone_is_still_muted(self):
        lifted = hexrgb(re.search(r"--pending-slate:\s*(#[0-9a-fA-F]{6})", CSS).group(1))
        self.assertGreater(lum(lifted), lum(token("slate")))
        self.assertLess(lum(lifted), lum(token("warm")), "it must not become the secondary text colour: muted stays muted")
        # about a fifth of the way from --slate to --warm, no more
        share = (lum(lifted) - lum(token("slate"))) / (lum(token("warm")) - lum(token("slate")))
        self.assertLess(share, 0.3)

    def test_configure_dims_on_stale_through_the_same_bindings_as_before(self):
        # the price logic is not touched: the class is bound to `stale`, which is "from the change until the newest answer"
        paid = configure(False)[1]
        # T2: the lines table keeps its own binding; the headline figure moved into the plan ticket, where its class is an object
        # (the figure, its jar and the phone strip's copy each carry `updating: stale`).
        self.assertEqual(paid.count(":class=\"stale && 'updating'\""), 1)
        self.assertIn(":class=\"{ over: est.over_cap, updating: stale }\" x-text=\"'$' + est.total.toFixed(2)\"", paid)
        self.assertEqual(paid.count("updating: stale"), 3)


class AFigureIsWrittenNotCounted(Quiet):
    def operator_configure(self):
        app = app_module.create_app(
            state={"profile": "kabir", "cap_usd": 8.41, "derived": DERIVED},
            extract=lambda p: "x", derive=lambda t, p: DERIVED,
            check_token=lambda t: (8.41, None), fetch_plan=lambda profile: dict(RAW_PLAN))
        app.config.update(TESTING=True)
        app.write_profile = lambda name, source: None
        return app.test_client().get("/configure").get_data(as_text=True)

    def test_the_meter_figure_is_bound_by_x_text_to_the_authoritative_estimate(self):
        body = self.operator_configure()
        self.assertRegex(body, r'<span class="numeral[^"]*"\s+x-text="\'\$\' \+ est\.total\.toFixed\(2\)"')
        self.assertNotIn("x-effect", body.split('class="numeral')[1].split(">")[0])

    def test_nothing_in_the_product_writes_an_intermediate_figure(self):
        for path in (HERE / "static").glob("*.js"):
            if "alpine" in path.name:
                continue
            source = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
            with self.subTest(script=path.name):
                self.assertNotRegex(source, r"requestAnimationFrame|cancelAnimationFrame|setInterval\s*\(|ease\s*\(|Math\.pow")
        for name, source in TEMPLATES.items():
            with self.subTest(template=name):
                self.assertNotIn("sweepCount", source)
                # a counter would have to call one of these from inside a template expression
                self.assertNotRegex(source, r"x-(?:text|effect)=\"[^\"]*(?:requestAnimationFrame|toFixed\([^)]*\)\s*\*\s*[a-z]*k\b)")

    def test_the_figure_does_not_reflow_when_it_changes(self):
        self.assertIn("font-variant-numeric: tabular-nums", rule(".meter .numeral"))


class CrossingTheCapIsWordsAndColour(Quiet):
    def test_there_is_no_shake_and_no_overshoot(self):
        self.assertNotRegex(CSS, r"@keyframes\s+cap-")
        self.assertNotRegex(CSS, r"\.meter\.over[^{]*\{[^}]*animation")
        self.assertNotRegex(CSS, r"\.meter-track\s*\{[^}]*animation")

    def test_the_state_is_the_colour_and_the_words(self):
        self.assertIn("background: var(--over)", rule(".meter.over .meter-fill"))
        self.assertIn("color: var(--over)", rule(".numeral.over"))
        self.assertIn("color: var(--over)", rule(".summary-panel .headline-figure .numeral.over"))

    def test_the_colour_change_is_one_hundred_and_sixty_milliseconds(self):
        self.assertIn(".meter-fill { transition: width var(--ms-2) var(--ease-settle), "
                      "background-color var(--ms-2) var(--ease-settle); }", MOT)
        self.assertIn(".headline-figure .numeral, .meter .numeral { transition: color var(--ms-2) var(--ease-settle); }", MOT)
        self.assertIn(".headline-figure { transition: border-color var(--ms-2) var(--ease-settle)", MOT)
        self.assertNotRegex(rule(".meter-fill"), r"transition")
        self.assertNotIn(".35s", nc(CSS))

    def test_nothing_enters_from_zero_on_load(self):
        # the spend rail used to be drawn from zero once a session, before first paint
        self.assertNotIn("sessionStorage", TEMPLATES["base.html"])
        self.assertNotRegex(CSS, r"scaleX\(0\)")


# ---------------------------------------------------------------------------------------------
class TheResultsArrival(Quiet):
    rows = [row(i, where="Pune, India") for i in range(1, 25)]

    def pages(self):
        return {"public": page(legacy_app(self.rows, public=True)), "operator": page(legacy_app(self.rows))}

    def test_the_head_script_is_in_the_head_and_is_one_class(self):
        for mode, body in self.pages().items():
            with self.subTest(mode=mode):
                head = body[:body.index("<header")]
                self.assertEqual(head.count('<script data-motion="arrive">'), 1)
                self.assertLess(head.index('<script data-motion="arrive">'), head.index("</title>") + 4000)
                self.assertIn("document.referrer", head)
                # before the stylesheet-blocking fonts request, so nothing can paint first
                self.assertLess(body.index('data-motion="arrive"'), body.index("fonts.googleapis.com/css2"))

    def test_only_the_results_page_carries_the_scripts(self):
        self.assertNotIn("data-motion", running(done=5))
        self.assertNotIn("data-motion", configure(True)[1])

    def test_the_sections_sit_in_one_wrapper_that_keeps_the_stack_gap(self):
        for mode, body in self.pages().items():
            with self.subTest(mode=mode):
                self.assertEqual(body.count('id="results-body"'), 1)
                self.assertIn('<div id="results-body" class="stack results-body">', body)
                inner = body.split('<div id="results-body"', 1)[1]
                self.assertIn('<section class="jobs-section"', inner)
                self.assertNotIn("reveal", body)
                # wrapper closes before the script, and the heading, tabs and tools are outside it
                self.assertLess(body.index("<h1>"), body.index('id="results-body"'))
                self.assertLess(body.index('class="bar"'), body.index('id="results-body"'))

    def test_a_page_with_no_jobs_draws_no_empty_wrapper(self):
        # an empty flex child still adds a 32 px gap: at rest the empty page must be as tall as it was
        body = page(legacy_app([], public=True))
        self.assertNotIn('id="results-body"', body)

    def test_the_stagger_is_capped_at_eight_and_three(self):
        arrival = block(MOTION, NO_PREF)[0]
        self.assertIn("tr:nth-child(-n + 8)", arrival)
        self.assertNotIn("nth-child(n + 9)", arrival)
        phone = block(arrival, "@media (max-width: 47.99rem)")
        self.assertEqual(len(phone), 1)
        self.assertIn("tr:nth-child(n + 4) { animation: none; }", phone[0])
        steps = re.findall(r"tr:nth-child\((\d+)\)\s*\{\s*--i:\s*(\d+)", arrival)
        self.assertEqual(steps, [(str(n), str(n - 1)) for n in range(1, 9)])
        self.assertIn("animation: write-in var(--row-fade) var(--ease-settle) both", arrival)
        self.assertIn("animation-delay: calc(var(--i) * var(--row-step))", arrival)

    def test_only_the_arrival_class_can_start_it_and_it_is_opacity_only(self):
        arrival = block(MOTION, NO_PREF)[0]
        self.assertIn(".arrive #results-body > .jobs-section:first-child .jobs tbody tr", arrival)
        self.assertRegex(arrival, r"@keyframes write-in\s*\{\s*from\s*\{\s*opacity:\s*0;\s*\}\s*\}")
        self.assertNotRegex(arrival.split("@keyframes write-in")[1].split("}")[0], r"transform|scale|blur|translate")
        # no travel, anywhere on the list
        self.assertNotRegex(re.sub(r"/\*.*?\*/", "", CSS, flags=re.S), r"\.jobs[^{]*\{[^}]*transform\s*:")

    def test_a_slow_answer_dims_and_then_settles(self):
        arrival = block(MOTION, NO_PREF)[0]
        self.assertIn("@keyframes list-in { from { opacity: var(--pending-dim); } }", arrival)
        self.assertIn(".swap .results-body { animation: list-in var(--ms-2) var(--ease-settle) both; }", arrival)
        self.assertIn(".results-body { transition: opacity var(--ms-2) var(--ease-settle); }", arrival)
        # nothing on a quick answer: no rule runs on a plain load
        self.assertNotRegex(MOTION, r"\n\.results-body\s*\{[^}]*animation")

    def test_quick_navigation_has_no_view_transition_or_crossfade(self):
        self.assertNotIn("@view-transition", CSS)
        self.assertNotIn("view-transition", "".join(TEMPLATES.values()))

    def test_the_two_panels_open_in_place_and_nothing_else_does(self):
        body = self.pages()["public"]
        for pid, key in (("tool-filter", "filter"), ("tool-export", "export")):
            with self.subTest(panel=pid):
                tag = re.search(r'<div class="tool-panel" id="%s"[^>]*>' % pid, body).group(0)
                for attr in ('x-transition:enter="t-in"', 'x-transition:enter-start="t-from"', 'x-transition:enter-end="t-to"',
                             'x-transition:leave="t-out"', 'x-transition:leave-start="t-to"', 'x-transition:leave-end="t-from"'):
                    self.assertIn(attr, tag)
        self.assertEqual(body.count("x-transition"), 12, "Apply, Opened and Applied do not animate")
        tools = MOT
        self.assertIn(".t-in { transition: opacity var(--tool-in) var(--ease-settle); }", tools)
        supported = block(tools, "@supports (interpolate-size: allow-keywords)")
        self.assertEqual(len(supported), 1, "height is animated only where the browser can do it")
        self.assertIn("height var(--tool-in) var(--ease-settle)", supported[0])
        self.assertIn("height var(--tool-out) var(--ease-leave)", supported[0])
        self.assertIn("margin-top var(--tool-in)", supported[0])
        # one tool replacing the other: closing and opening on one duration and one curve, or the list between them wobbles
        self.assertIn(".bar:has(.t-in):has(.t-out) .t-out { transition-duration: var(--tool-in); transition-timing-function: var(--ease-settle); }", supported[0])
        # the fallback: opacity on the way in, instantly on the way out
        self.assertNotIn(".t-out", tools.replace(supported[0], ""))
        self.assertNotIn("height", tools.replace(supported[0], ""))
        self.assertNotIn("margin-top", tools.replace(supported[0], ""))

    def test_the_body_script_exists_and_the_row_click_script_is_untouched(self):
        body = self.pages()["operator"]
        self.assertEqual(body.count('<script data-motion="pending">'), 1)
        self.assertIn('var OPENED = "sweep.opened"', body)

    def test_nothing_is_hidden_until_a_script_runs(self):
        # no row, section or table is hidden by markup or by an unconditional rule: the no-JS page is the whole page
        body = self.pages()["public"]
        inner = body.split('id="results-body"', 1)[1]
        markup = inner.split("<script", 1)[0]
        self.assertNotIn('style="display:none"', markup)
        self.assertNotRegex(markup, r"(?<![\w-])hidden(?![\w-])")
        # opacity 0 in the motion layer is only ever the start of a keyframe, of an Alpine move (.t-from, .m-from: they
        # exist for the length of the move and only inside no-preference) or of the dialog's entry: never a rule that a
        # failed script would leave standing
        bare = re.sub(r"@keyframes[^{]*\{(?:[^{}]|\{[^{}]*\})*\}", "", nc(MOTION))
        zeros = {sel.strip() for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", bare) if re.search(r"\bopacity:\s*0\s*;", body)}
        self.assertEqual(zeros, {".t-from", ".m-from", "dialog.feedback[open], dialog.feedback[open]::backdrop"})

    def test_the_scripts_behave(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        script = os.path.join(os.path.dirname(__file__), "results_motion_test.js")
        for mode, body in self.pages().items():
            with self.subTest(mode=mode), tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as fh:
                fh.write(body)
            try:
                run = subprocess.run([node, script, fh.name], capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            finally:
                os.unlink(fh.name)


# ---------------------------------------------------------------------------------------------
class ProgressMarksWhatTheServerSaid(Quiet):
    ENDINGS = ("finished", "stopped", "out_of_credit", "credit_changed", "partial", "halted", "incomplete")

    def test_the_redirect_waits_four_hundred_milliseconds_not_twelve_hundred(self):
        for public in (True, False):
            page_ = running(done=5, public=public)
            with self.subTest(public=public):
                self.assertNotIn("1200", page_)
                self.assertEqual(re.findall(r"setTimeout\(go, (\d+)\)", page_), ["400"])
                # it still needs the server's word: finished, and this visitor was waiting for it
                self.assertEqual(len(re.findall(r"p\.finished &amp;&amp; waiting\) leave\(\)", page_)), 1)

    def test_the_four_hundred_start_when_the_ending_is_on_screen_not_when_the_state_was_set(self):
        """Alpine draws the ending in the next frame, and on a phone with a hundred tiles that was 230 ms late: the ending was
        seen for about 160 ms of the 400 and then cut. So the timer is armed from the second frame after Alpine's draw, with a
        second timer so a tab that draws no frames still goes."""
        for public in (True, False):
            src = running(done=5, public=public)
            with self.subTest(public=public):
                self.assertIn("this.$nextTick(() =&gt; requestAnimationFrame(() =&gt; requestAnimationFrame(arm)));", src)
                self.assertIn("setTimeout(arm, 1000) }", src)
                self.assertIn("if (!armed) { armed = true; setTimeout(go, 400) }", src)

    def test_the_redirect_is_not_reachable_from_a_state_the_server_did_not_send(self):
        for public in (True, False):
            src = running(done=5, public=public)
            head = src[src.index("x-init="):src.index("setInterval")]
            with self.subTest(public=public):
                # the only `location =` is inside leave(), and leave() is called only after p.finished has been checked;
                # p is only ever assigned what the server sent
                self.assertEqual(src.count("location = "), 1)
                self.assertNotIn("location = ", head)
                self.assertEqual(head.count("leave()"), 1)
                self.assertLess(head.index("p.finished"), head.index("leave()"))
                self.assertEqual(len(re.findall(r"\bp = ", head)), 1)

    def test_every_ending_fades_in_only_when_p_state_changes_to_it(self):
        src = running(done=5)
        for state in self.ENDINGS:
            with self.subTest(state=state):
                tag = re.search(r'<div class="banner[^"]*"[^>]*x-show="p\.state === \'%s\'"[^>]*>' % state, src).group(0)
                self.assertIn('x-transition:enter="m-in"', tag)
                self.assertIn('x-transition:enter-start="m-from"', tag)
                self.assertIn('x-transition:enter-end="m-to"', tag)
                self.assertNotIn("x-transition:leave", tag, "an ending is never faded out: a state that stopped being true goes at once")
        self.assertEqual(src.count('x-transition:enter="m-in"'), len(self.ENDINGS))

    def test_the_words_are_bound_to_the_server_state_not_to_the_fade(self):
        src = running(done=5)
        for state in self.ENDINGS:
            with self.subTest(state=state):
                self.assertIn("x-show=\"p.state === '%s'\"" % state, src)
        # the heading is a live region: its words change at once, with no class in between
        self.assertIn("aria-live=\"polite\"", src)
        h1 = src[src.index("<h1"):src.index("</h1>")]
        self.assertNotIn("x-transition", h1)

    def test_the_mark_is_one_hundred_and_sixty_milliseconds_of_opacity(self):
        marks = block(MOTION, NO_PREF)[0]
        self.assertIn(".m-in { transition: opacity var(--ms-2) var(--ease-settle); }", marks)
        self.assertIn(".m-from { opacity: 0; }", marks)
        self.assertIn(".m-to { opacity: 1; }", marks)

    def test_a_finished_search_is_a_colour_not_a_landing(self):
        """It used to scale in, in a column ripple, and again on every load, and a batch of a hundred is a pulse. A transition
        needs a change, so a cell that is done at load is simply done; nothing in the template marks or times a cell."""
        src = running(done=5)
        self.assertNotIn(":nth-child(8n", CSS)
        self.assertNotRegex(nc(CSS), r"\.cell\.done[^{]*\{[^}]*animation")          # the running cell's breath is `.cell.running`
        cell = re.search(r'<div class="cell"[^>]*>', src).group(0)
        self.assertNotIn("x-init", cell)
        # A11 polish (owner): a tile that finishes pops once, a transform and no colour (the colour change above is untouched). The public
        # page's cell carries one effect for it, which marks a cell only if it was NOT done when it was drawn, so a cell done at load is
        # still simply done, never one that finished while its panel was shut, and nothing times a cell: the class comes off when the pop ends. The console's cell carries nothing (test_a8_progress holds that).
        self.assertEqual(re.findall(r'x-effect="([^"]*)"', cell), ["t.state === 'done' &amp;&amp; !was &amp;&amp; !$el._seen &amp;&amp; ($el._seen = true, $el.getClientRects().length &gt; 0 &amp;&amp; $el.classList.add('pop'))"])
        self.assertIn("x-data=\"{ was: t.state === 'done' }\"", cell)
        self.assertNotIn("data-was-done", src)
        self.assertIn(".cell { transition: background-color var(--ms-2) var(--ease-settle), color var(--ms-2) var(--ease-settle), border-color var(--ms-2) var(--ease-settle); }", MOT)

    def test_the_feed_writes_in_only_what_arrived_after_the_page_did(self):
        li = "<li x-init=\"fed &amp;&amp; ($el.classList.add('fresh'), setTimeout(() =&gt; $el.classList.remove('fresh'), 400))\">"
        for label, src in (("paid, beside the tiles", running(done=5)), ("free, the public path", running(free=True))):
            with self.subTest(page=label):
                self.assertEqual(src.count(li), 1)
                self.assertRegex(src, r"fed: false")
                self.assertRegex(src, r"\$nextTick\(\(\) =&gt; fed = true\)")
        self.assertIn(".feed li.fresh > * { animation: write-in var(--ms-2) var(--ease-settle) both; }", MOT)
        self.assertNotIn(".feed li > * { animation", nc(CSS))
        self.assertIn(".feed b { transition: color var(--ms-2) var(--ease-settle); }", MOT)

    def test_the_waiting_screen_has_no_entrance_and_the_bars_stay_honest(self):
        self.assertNotRegex(CSS, r"\.working\s*\{[^}]*animation")
        src = running(done=5)
        self.assertIn('class="activity-track" role="progressbar"', src)              # determinate only with a fraction
        free = running(free=True)
        self.assertNotIn("activity-fill", free)
        self.assertIn('<div class="working-bar"><span><i class="rider" aria-hidden="true"><svg', free)      # A8: the brush rides inside the segment
        self.assertIn(".activity-fill { transition: width var(--ms-2) var(--ease-settle); }", MOT)
        self.assertNotIn("transition", rule(".activity-fill"))
        self.assertNotIn(".45s", nc(CSS))


class UploadAndConfigure(Quiet):
    def test_an_accepted_file_writes_in_and_nothing_else_on_upload_moves(self):
        self.assertIn(".picked-row { animation: write-in var(--ms-2) var(--ease-settle) both; }",
                      "".join(block(MOTION, NO_PREF)))
        self.assertNotIn("x-transition", TEMPLATES["upload.html"])
        # a message that says what is wrong is never faded
        self.assertIn('role="alert"', TEMPLATES["upload.html"])
        self.assertNotRegex(TEMPLATES["upload.html"], r'role="alert"[^>]*x-transition|x-transition[^>]*role="alert"')

    def test_the_dropzone_answers_in_the_press_tier(self):
        self.assertIn(".drop { transition: border-color var(--ms-1) ease, background-color var(--ms-1) ease; }", MOT)
        self.assertIn(".drop .glyph { transition: color var(--ms-1) ease; }", MOT)

    def test_the_press_is_unchanged_in_size(self):
        self.assertIn("transition: background-color var(--ms-1) ease, transform var(--ms-1) ease;", rule("button.primary, a.primary"))
        self.assertIn("translateY(1px)", CSS[CSS.index("button.primary:active"):][:200])

    def test_the_location_menu_fades_in_and_out_instantly(self):
        body = configure(True)[1]
        menu = re.search(r'<div class="picker-menu"[^>]*>', body).group(0)
        self.assertIn('x-transition:enter="menu-in"', menu)
        self.assertIn('x-transition:enter-start="m-from"', menu)
        self.assertIn('x-transition:enter-end="m-to"', menu)
        self.assertNotIn("x-transition:leave", menu)
        self.assertIn(".menu-in { transition: opacity var(--ms-1) var(--ease-settle); }", "".join(block(MOTION, NO_PREF)))

    def test_saving_and_repricing_words_do_not_animate(self):
        for free, needle in ((False, 'x-show="busy"'), (True, 'x-show="sent"')):
            body = configure(free)[1]
            with self.subTest(needle=needle):
                tag = re.search(r"<span[^>]*%s[^>]*>" % re.escape(needle), body).group(0)
                self.assertNotIn("x-transition", tag)


class TheShell(Quiet):
    def test_nothing_in_the_shell_moves_but_the_liveness_pulse(self):
        base = TEMPLATES["base.html"]
        self.assertNotIn("x-transition", base)
        for selector in (".tracker", ".step", ".lockup"):
            with self.subTest(selector=selector):
                self.assertNotRegex(nc(CSS), re.escape(selector) + r"[^{}]*\{[^}]*(animation|transition)")
        runbar = re.findall(r"\.runbar[^{}]*\{[^}]*(?:animation|transition)[^}]*\}", nc(CSS))
        self.assertTrue(runbar and all("runpulse" in r or "animation: none" in r for r in runbar),
                        "the run strip's only motion is the liveness pulse (and its reduced-motion stop)")

    def test_the_activity_strip_repaints_without_a_class_that_could_replay(self):
        base = TEMPLATES["base.html"]
        strip = base[base.index("function paint(b)"):base.index("function tick()")]
        self.assertNotIn("classList", strip)
        self.assertNotIn("animation", strip)

    def test_the_feedback_dialog_fades_in_and_never_out_and_is_not_touched_by_script(self):
        entry = "".join(block(MOTION, NO_PREF))
        self.assertIn("dialog.feedback[open], dialog.feedback[open]::backdrop { opacity: 1; transition: opacity var(--ms-2) var(--ease-settle); }", entry)
        self.assertIn("@starting-style { dialog.feedback[open], dialog.feedback[open]::backdrop { opacity: 0; } }", entry)
        self.assertNotIn("dialog.feedback {", entry)
        script = TEMPLATES["base.html"].split("var dlg = document.getElementById")[1].split("</script>")[0]
        self.assertIn("dlg.showModal()", script)
        self.assertNotRegex(script, r"animat|transition|requestAnimationFrame|setTimeout")


if __name__ == "__main__":
    unittest.main()
