"""D5: Progress in the Quiet Ledger.

The count of jobs is not amber; the money lines say "estimate" and never "charged";
a part-run is not shown as success; an ending that needs attention is coral with a
shape; the side panels are one door; a bar is determinate only where the backend
gave a fraction. Rendered through the console's own injected fakes (TestRunningScreen's
build), with the engine's authorization record injected to reach the partial and
refused endings. No model, provider or network.
"""

import os
import pathlib
import re
import tempfile
import unittest

from sweep import app as app_module
from sweep.tests.test_app import DERIVED, RUNNING_PLAN, FakeProc

CSS = (pathlib.Path(app_module.__file__).parent / "static" / "sweep.css").read_text()


def rule(selector):
    """The body of the rule whose selector list ends with `selector`."""
    m = re.search(r"(?:^|\n)" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    return m.group(1) if m else ""


def text(page):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page))


def sweep_app(done=0, alive=True, free=False, public=True, authorization=None, found=0, spend=2.42, elapsed=700, ready=False):
    """A running screen (TestRunningScreen's own build) with the knobs D5 needs."""
    import time
    from sweep import runs as runs_mod
    proc = FakeProc()
    if not alive:
        proc.poll = lambda: 0
    raw = {"profile": "kabir", "sites": {} if free else RUNNING_PLAN["sites"], "max_results": {}, "free_sources": 134}
    lines = [] if free else [{"site": "linkedin", "label": "LinkedIn", "searches": 32, "rate": 0.045,
                              "results": 25, "subtotal": 1.44, "free": False},
                             {"site": "indeed", "label": "Indeed", "searches": 14, "rate": 0.09,
                              "results": 15, "subtotal": 1.26, "free": False}]
    state = {"profile": "kabir", "cap_usd": 8.41, "proc": proc, "baseline_usd": 1.0, "raw_plan": raw,
             "run_started_at": time.time() - elapsed, "live_found": found, "live_items": [],
             "plan": {"total": 0.0 if free else 2.70, "total_searches": 0 if free else 46, "over_cap": False,
                      "lines": lines, "spend_cap": 0.0, "free_sources": 134}}
    if free:
        state["free_only"] = True
    keys = [] if free else runs_mod.combo_keys(raw, runs_mod.today())
    env = os.path.join(tempfile.mkdtemp(), ".env")
    pathlib.Path(env).write_text("APIFY_TOKEN=tok\n")
    app = app_module.create_app(
        state=state, extract=lambda p: "x", derive=lambda t, p: DERIVED, check_token=lambda t: (8.41, None),
        fetch_plan=lambda p: raw, start_sweep=lambda p: proc, read_spend=lambda: spend,
        read_done=lambda p, d: set(keys[:done]), read_rows=lambda p: [], env_path=env,
        read_authorization=(lambda: authorization), read_ready=(lambda: ready), output_dir=tempfile.mkdtemp())
    app.config.update(TESTING=True, PUBLIC_MODE=public)
    return app


def running(**kw):
    return sweep_app(**kw).test_client().get("/running").get_data(as_text=True)


class ProgressStates(unittest.TestCase):

    def test_the_count_of_jobs_is_not_money(self):
        page = running(found=4, done=5)
        self.assertIn('class="headline-figure found"', page)
        self.assertIn("var(--chalk)", rule(".headline-figure.found .numeral"))
        self.assertNotIn("--paid", rule(".headline-figure.found .numeral"))
        self.assertNotIn("--paid", rule(".numeral-inline b"))

    def test_the_estimate_is_money_and_is_never_called_a_charge(self):
        page = text(running(done=5))
        self.assertIn("Estimated cost $2.70", page)
        self.assertNotRegex(page, r"(?i)charged \$|you were charged")
        self.assertIn('<b class="paid">$2.70</b>', running(done=5))

    def test_a_visitors_sweep_shows_no_spend_it_does_not_have(self):
        page = running(done=5, public=True)
        self.assertIn('class="figures"', page)
        self.assertNotIn("Spent so far", page.split('class="figures"', 1)[1].split("</dl>", 1)[0])
        self.assertNotIn("not known", page.split('class="figures"', 1)[1].split("</dl>", 1)[0])

    def test_the_console_ledger_keeps_estimate_and_spend_apart(self):
        page = running(done=5, public=False)
        ledger = page.split('class="figures"', 1)[1].split("</dl>", 1)[0]
        self.assertIn("Estimated cost", ledger)
        self.assertIn("Spent so far", ledger)
        self.assertLess(ledger.index("Estimated cost"), ledger.index("Spent so far"))
        self.assertIn('<b class="paid">$2.70</b>', ledger)
        # the spend is an account reading: delta from the baseline, never the estimate
        self.assertRegex(ledger, r'<b :class="p.spend === null[^"]*"\s+class="paid"[^>]*>\$1\.42')

    def test_a_determinate_bar_exists_only_where_the_backend_gave_a_fraction(self):
        paid = running(done=5)
        self.assertIn("activity-track", paid)
        self.assertIn('role="progressbar"', paid)
        free = running(free=True)
        self.assertNotIn("activity-fill", free)
        self.assertNotIn('role="progressbar"', free)
        # A8: the free pass's own bar carries the brush inside its moving segment (public-only markup): it rides with the bar
        self.assertIn('<div class="working-bar"><span><i class="rider" aria-hidden="true"><svg', free)

    def test_the_free_page_has_one_door_not_three_panels_beside_the_work(self):
        page = running(free=True)
        self.assertIn('<details class="about">', page)
        self.assertEqual(page.count('<aside class="aside stack">'), 0)
        inside = page.split('<details class="about">', 1)[1].split("</details>", 1)[0]
        for heading in ("Where Sweep is searching", "How jobs are ranked", "What to expect"):
            self.assertIn(heading, inside)

    def test_the_paid_page_is_one_sound_structure(self):
        # the Searches section used to open a <div> and close a <details>, which left the
        # Latest matches panel inside it
        page = running(done=5)
        self.assertIn('<details class="pane searches" open>', page)   # A11 polish: the Searches peek is open by default (it still closes)
        self.assertIn("<summary class=\"panel-head\">", page)
        for tag in ("details", "summary", "div", "dl"):
            opened = len(re.findall(rf"<{tag}[\s>]", page))
            closed = page.count(f"</{tag}>")
            self.assertEqual(opened, closed, tag)

    def test_the_operators_searches_are_still_a_panel_not_a_door(self):
        page = running(done=5, public=False)
        self.assertNotIn('<details class="pane searches">', page)
        self.assertIn("search-grid", page)

    def test_a_part_run_is_not_dressed_as_a_success(self):
        auth = {"outcome": "partial", "total_planned_paid_units": 46, "placeable_paid_units": 43,
                "skipped_insufficient_capacity": 3, "skipped_budget": 0, "partial_estimate_usd": 2.1}
        page = running(done=43, alive=False, authorization=auth)
        self.assertIn('<div class="banner part"', page)
        self.assertNotIn('<div class="banner ok" x-show="p.state === \'partial\'"', page)
        self.assertIn("Part of your search ran", page)
        body = rule(".banner.part b::before")
        self.assertIn("linear-gradient", body)            # a half-filled shape, not a tick

    def test_a_refused_start_says_nothing_ran_and_nothing_was_charged(self):
        auth = {"outcome": "refused", "total_planned_paid_units": 46, "placeable_paid_units": 0,
                "skipped_insufficient_capacity": 46, "executed_paid_units": 0}
        page = running(done=0, alive=False, authorization=auth)
        self.assertIn("Your search did not start", page)
        self.assertIn("Nothing was searched and nothing was charged.", page)

    def test_one_primary_action_at_a_time_when_a_sweep_has_ended(self):
        # the banner's action wins: the block's Continue is an outline for these endings
        for state, auth, done in (("partial", {"outcome": "partial", "total_planned_paid_units": 46,
                                               "placeable_paid_units": 43, "skipped_insufficient_capacity": 3,
                                               "skipped_budget": 0, "partial_estimate_usd": 2.1}, 43),
                                  ("refused", {"outcome": "refused", "total_planned_paid_units": 46,
                                               "placeable_paid_units": 0, "skipped_insufficient_capacity": 46}, 0)):
            with self.subTest(state):
                page = running(done=done, alive=False, authorization=auth)
                self.assertRegex(page, r'<a class="secondary"\s+:class="\[\'partial\', \'credit_changed\'\]')
        halted = running(done=5, alive=False)
        self.assertRegex(halted, r'<a class="primary"\s+:class="\[\'partial\', \'credit_changed\'\]')

    def test_endings_that_need_attention_are_coral_with_a_shape_not_amber(self):
        self.assertIn("var(--over)", rule(".banner.warn"))
        self.assertIn("var(--over)", rule(".banner.warn b"))
        self.assertIn('content: "!"', rule(".banner.warn b::before"))
        self.assertIn('content: "\\2713"', rule(".banner.ok b::before"))
        self.assertNotIn("--paid", rule(".banner.warn"))

    def test_a_stopped_row_is_a_ring_and_a_word(self):
        self.assertIn("transparent", rule(".activity.off .activity-dot"))
        self.assertIn("Search stopped", running(done=5, alive=False))

    def test_the_shortlist_placeholder_goes_when_the_run_is_over(self):
        page = running(free=True, alive=False)
        # any ending, not only a success: a failed free run is never going to fill it
        self.assertIn(":class=\"p.state !== 'running' && 'gone'\"", page)
        self.assertIn("display: none", rule(".gone"))

    def test_the_state_is_announced_once_by_the_heading(self):
        for public in (True, False):
            with self.subTest(public=public):
                page = running(done=5, public=public)
                self.assertRegex(page, r'<h1 x-text="[^"]*"\s+aria-live="polite">')
                # and the count that moves every poll is NOT a live region
                self.assertNotRegex(page, r'class="activity-count"[^>]*aria-live')

    def test_an_ending_says_only_what_it_can_stand_behind(self):
        page = running(done=5, alive=False)
        # no per-search count for a run that had no searches; "so far" only while it runs
        free = running(free=True, alive=False)
        self.assertIn("p.planned ? 'All ' + p.planned + ' of them.", free)
        self.assertIn("(p.state === 'running' ? ' so far' : '')", page)
        # a visitor's own Stop is named as theirs
        self.assertIn("'You stopped the sweep'", page)
        # the last pass of a finished run is done, not a dot that says still going
        self.assertIn('return at === i && i < 3 ? "now" : (at >= i && at >= 0 ? "done" : "next")', page)
        self.assertIn('return at === i && i < 3 ? ", in progress" : (at >= i && at >= 0 ? ", done"', page)

    def test_a_run_that_found_nothing_does_not_say_the_first_search_has_to_finish(self):
        page = running(done=46, alive=False)
        self.assertIn("!p.latest.length && p.state === 'running'", page)
        self.assertIn("'Nothing matched'", page)
        self.assertIn("'Nothing was fetched'", page)

    def test_a_refused_start_offers_only_the_way_back_to_confirm(self):
        auth = {"outcome": "refused", "total_planned_paid_units": 46, "placeable_paid_units": 0,
                "skipped_insufficient_capacity": 46, "executed_paid_units": 0}
        page = running(done=0, alive=False, authorization=auth)
        block = page.split('<div class="split ended"', 1)[1][:260]
        self.assertIn("display:none", block)                      # nothing to finish, nothing kept
        self.assertIn(">Back to Confirm</a>", page)

    def test_nothing_animates_under_reduced_motion(self):
        block = CSS[CSS.index("@media (prefers-reduced-motion: reduce) {\n  * { transition"):][:500]
        self.assertIn("*::before, *::after { transition: none !important; animation: none !important; }", block)

    def test_the_queued_page_is_honest_about_waiting(self):
        page = running(free=True)
        self.assertIn("You are in the queue", page)
        self.assertIn("Nothing is lost while you wait", text(page))


if __name__ == "__main__":
    unittest.main()
