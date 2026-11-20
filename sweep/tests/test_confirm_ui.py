"""D5: Confirm in the Quiet Ledger — since T2 (Configure and Confirm are one public screen), the plan ticket.

What these hold, beyond the contracts the older suites pin (the copy, the forms,
the consent): the decision reads in order (what is searched, the cost, whether it
can be covered, then the action), so on a phone the cost and the capacity are above
the button; a free sweep says what it is and shows no figure; an estimate is coral
only when the plan it prices cannot be covered; a full plan is never offered a
Start unless the allocator says it places; partial is a consent nobody has given
(a coupon to pick, then a button of its own), and a refused plan has no enabled
primary; one primary at a time. The stylesheet tests at the end are the console's
Confirm (sweep.css), which T2 did not touch.

Fakes only: the loopback worker the public suites use. No model, provider or network.
"""

import pathlib
import re
import unittest
from unittest import mock

from sweep import app as app_module
from sweep.tests.test_public_sweep import over_sentence, plan_error, shown
from sweep.tests.test_search_v2_d import (CREDIT, KEY_5, KEY_11, PublicSockets, account_reader,
                                          c5_pool_plan, pool_plan, recording_worker, render_app,
                                          reviewed, text, worker_client)

CSS = (pathlib.Path(app_module.__file__).parent / "static" / "sweep.css").read_text()


def rule(selector):
    """The body of the rule whose selector list ends with `selector`."""
    m = re.search(r"(?:^|\n)" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    return m.group(1) if m else ""


def primaries(page):
    """Every control on the plan screen a visitor can press as the primary action right now: drawn as the primary, not
    inside something the server hid, and not waiting for a coupon to be picked first (x-show="pick === ...")."""
    from sweep.tests.test_a6_key import main_of     # imported here: test_a3_copy (which test_a6_key imports) imports this module
    out = []
    for node in main_of(page).walk():
        if "primary" not in node.classes() or node.tag not in ("button", "a"):
            continue
        chain, hidden = node, False
        while chain is not None:
            hidden = hidden or "display:none" in chain.attrs.get("style", "").replace(" ", "")
            chain = chain.parent
        if not hidden and not node.attrs.get("x-show", "").startswith("pick"):
            out.append(node)
    return out


class ConfirmStates(PublicSockets):

    def visitor(self, url, credit=None, plan=c5_pool_plan, free=False):
        CREDIT.update({KEY_5: 5.0, KEY_11: 11.0})
        self.addCleanup(lambda: [CREDIT.pop(k, None) for k in (KEY_5, KEY_11)])
        app = render_app(url, read_account=account_reader(lambda t: (CREDIT[t], None)),
                         hour_now=lambda: 12)
        client = reviewed(app, "beta_user")
        patch = mock.patch.object(worker_client, "plan", lambda *a, **kw: plan())
        patch.start()
        self.addCleanup(patch.stop)
        if free:
            client.post("/key/free")
        else:
            client.post("/key", data={"token": credit})
        return app, client

    def confirm(self, **kw):
        """The plan screen (GET /configure; /confirm leads to it)."""
        with recording_worker() as (url, store, queue, spawned):
            app, client = self.visitor(url, **kw)
            return client.get("/configure").get_data(as_text=True)

    # ---- free ------------------------------------------------------------
    def test_a_free_sweep_says_what_it_is_and_shows_no_figure(self):
        page = self.confirm(free=True)
        self.assertRegex(text(page), r"\d+ free job boards?")
        self.assertIn("Free — no account needed and nothing to pay.", text(page))
        self.assertNotIn("$0.00", page)
        self.assertNotIn("pticket", page)
        self.assertNotIn('class="numeral', page)
        self.assertNotIn("quoted_total", page)                        # nothing priced to hold it to
        self.assertIn("Start Quick Sweep", page)
        self.assertEqual(len(primaries(page)), 1)

    # ---- paid, covered ---------------------------------------------------
    def test_a_covered_paid_sweep_puts_cost_and_capacity_above_the_action(self):
        page = self.confirm(credit=KEY_11)
        for above in ("Estimated cost", "$10.99 available", 'class="fits"'):
            self.assertLess(page.index(above), page.index("Start the sweep ·"), above)
        # the accounts that pay follow the ticket's stub (they were the Confirm's detail)
        self.assertLess(page.index("Start the sweep ·"), page.index('class="pt-accounts"'))
        self.assertTrue(shown(page, "p", "fits"))
        self.assertEqual(over_sentence(page), "")
        self.assertNotIn("jar over", page)
        self.assertNotIn("is-over", page)
        self.assertEqual([n.text() for n in primaries(page)], ["Start the sweep · $6.97→"])
        self.assertFalse(shown(page, "div", "pt-coupons"))
        self.assertNotIn('type="checkbox" name="over_cap_ack"', page)  # there is no box: consent is a button, and none is offered

    def test_the_ticket_is_a_ledger_before_the_decision(self):
        page = self.confirm(credit=KEY_11)
        self.assertIn('class="pt-lines"', page)
        self.assertLess(page.index('class="pt-lines"'), page.index('class="pt-cost"'))
        self.assertLess(page.index('class="pt-cost"'), page.index('class="pt-stub"'))

    # ---- paid, not covered -----------------------------------------------
    def test_a_short_plan_is_coral_with_a_shape_and_never_says_it_is_covered(self):
        page = self.confirm(credit=KEY_5)
        self.assertIn('<div class="jar over"', page)                 # the jar, drawn over by the server
        self.assertIn(':class="{ over: est.over_cap, updating: stale }" x-text="\'$\' + est.total.toFixed(2)"', page)
        self.assertEqual(over_sentence(page), "Your connected accounts can run 48 of 90 of these paid searches.")
        self.assertFalse(shown(page, "p", "fits"))
        self.assertNotIn("verdict ok", page)
        self.assertIn("$4.99 available", text(page))

    def test_partial_is_a_consent_nobody_has_given_and_no_button_waits_to_start_it(self):
        from sweep.tests.test_a6_key import main_of
        page = self.confirm(credit=KEY_5)
        main = main_of(page)
        # no Start while the plan is over, and nothing pressable that starts anything until a coupon is picked
        self.assertFalse(shown(page, "div", "pt-go"))
        self.assertEqual(primaries(page), [])
        coupons = main.one("div", "pt-coupons")
        picks = coupons.find("button", "coupon")
        self.assertEqual([c.attrs.get("type") for c in picks], ["button", "button"])      # picking never submits
        self.assertEqual([c.one("b").text() for c in picks], ["Add another Apify key", "Run what fits, $3.19"])
        self.assertIn("The first 48 searches; the rest are left out, never charged", picks[1].text())
        # the consent is a submit that names it, shown only once its coupon is the picked one
        fit = [n for n in coupons.find("button") if n.attrs.get("name") == "over_cap_ack"]
        self.assertEqual([(n.attrs["value"], n.attrs.get("x-show"), n.attrs.get("type", "submit")) for n in fit],
                         [("yes", "pick === 'fit' && est.coverage && est.coverage.placeable_units", "submit")])
        self.assertEqual(fit[0].text(), "Start what fits→")
        self.assertEqual(main.find("input", name="over_cap_ack"), [])                  # no pre-ticked or tickable box
        # the remedy is a button of its own: it saves the settings and goes to the key step
        key = [n for n in coupons.find("button") if n.attrs.get("name") == "then"]
        self.assertEqual([(n.attrs["value"], n.attrs.get("formaction"), n.attrs.get("x-show")) for n in key],
                         [("key", "/configure", "pick === 'key'")])

    def test_a_refused_plan_has_a_disabled_primary(self):
        with recording_worker() as (url, store, queue, spawned):
            app, client = self.visitor(url, credit=KEY_11, plan=lambda: pool_plan(None))
            page = client.get("/configure").get_data(as_text=True)
        self.assertEqual(over_sentence(page), "Paid searches are temporarily unavailable, so none will start. Nothing is charged.")
        self.assertIn('<div class="jar off"', page)
        button = re.search(r'<button class="primary[^"]*" type="submit"[^>]*>', page).group(0)
        self.assertIn("disabled", button.replace(":disabled", ""))
        self.assertIn(":disabled=\"sent || busy || est.paid_unavailable\"", page)
        self.assertFalse(shown(page, "div", "pt-coupons"))
        self.assertIn("disabled", primaries(page)[0].attrs)

    def test_an_unavailable_plan_is_not_a_live_figure(self):
        with recording_worker() as (url, store, queue, spawned):
            app, client = self.visitor(url, credit=KEY_11, plan=lambda: pool_plan(None))
            page = client.get("/configure").get_data(as_text=True)
        self.assertIn('<div class="jar off"', page)                  # the jar is the "off" jar: dashed, empty, no credit line
        self.assertRegex(page, r'<div class="jar-lim"[^>]*style="display:none"')
        self.assertNotIn("jar over", page)

    def test_a_plan_nothing_covers_does_not_offer_a_zero_dollar_run(self):
        with recording_worker() as (url, store, queue, spawned):
            CREDIT["apify_api_VISITOR_TINY_0000000000"] = 0.05
            self.addCleanup(CREDIT.pop, "apify_api_VISITOR_TINY_0000000000", None)
            app, client = self.visitor(url, credit="apify_api_VISITOR_TINY_0000000000")
            page = client.get("/configure").get_data(as_text=True)
        self.assertRegex(over_sentence(page), r"None of these paid searches fit within the credit on your connected accounts\.")
        self.assertTrue(shown(page, "div", "pt-coupons"))
        self.assertIn("Add another Apify key", text(page))
        # the "run what fits" coupon exists in the markup but is hidden: nothing fits, so there is nothing to start
        self.assertRegex(page, r'<button type="button" class="coupon"[^>]*x-show="est\.coverage && est\.coverage\.placeable_units"\s+style="display:none"')
        self.assertFalse(shown(page, "div", "pt-go"))
        self.assertEqual(primaries(page), [])

    def test_what_is_searched_for_is_one_line_of_words_and_an_account_can_be_removed_by_name(self):
        page = self.confirm(credit=KEY_11)
        self.assertIn('<dt>Searching for</dt>\n              <dd>React Native Developer, Full Stack Engineer</dd>', page)
        self.assertRegex(page, r'class="tertiary danger"[^>]*aria-label="Stop using Apify account 1"[^>]*>Remove</button>')

    def test_a_refusal_comes_back_on_the_plan_screen_with_a_shape(self):
        with recording_worker() as (url, store, queue, spawned):
            app, client = self.visitor(url, credit=KEY_5)
            client.get("/configure")
            refused = client.post("/run")
            page = refused.get_data(as_text=True)
        self.assertEqual(refused.status_code, 400)
        self.assertIn("can't safely cover the full Sweep", plan_error(page))
        self.assertIn('<h1>Plan your <span class="scrib">sweep</span>.</h1>', page)     # the plan screen, not a screen of its own
        A_CSS = (pathlib.Path(app_module.__file__).parent / "static" / "sweep-a.css").read_text()
        self.assertIn('content: "!"', A_CSS[A_CSS.index(".skin-a .error:not(.confirm.ticket > .decide .error)::before"):][:200])

    def test_a_refusal_is_announced_as_an_alert(self):
        """Confirm's refusal was `<p class="error with-shape" role="alert">`, so a screen reader hears that the start was
        refused. The plan screen's error line is a bare `<p class="error">` (configure.html), so it is not announced."""
        with recording_worker() as (url, store, queue, spawned):
            app, client = self.visitor(url, credit=KEY_5)
            client.get("/configure")
            page = client.post("/run").get_data(as_text=True)
        self.assertRegex(page, r'<p class="error"[^>]*role="alert">')

    # ---- the stylesheet ----------------------------------------------------
    def test_the_decision_is_the_right_column_on_a_wide_screen_and_not_pinned(self):
        self.assertIn("grid-column: 2", rule(".confirm > .decide") + CSS[CSS.index("@media (min-width: 64rem) {\n  .confirm"):][:700])
        self.assertNotIn("position: sticky", rule(".confirm > .decide"))
        self.assertNotIn("position: fixed", rule(".confirm > .decide"))

    def test_the_verdict_shapes_and_colours_follow_the_allocator(self):
        self.assertIn('content: "\\2713"', rule(".verdict.ok::before"))
        self.assertIn("var(--free)", rule(".verdict.ok::before"))
        self.assertIn('content: "!"', rule(".verdict.short::before"))
        self.assertIn("var(--over)", rule(".verdict.short::before"))
        self.assertIn("var(--over)", rule(".decide .headline-figure .numeral.over"))

    def test_a_disabled_primary_is_still_readable(self):
        body = CSS[CSS.index("button.primary[disabled]"):][:260]
        self.assertIn("opacity: 1", body)
        self.assertIn("var(--warm)", body)


if __name__ == "__main__":
    unittest.main()
