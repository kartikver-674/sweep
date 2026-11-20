"""D4.2: the live price on Configure counts only the newest answer.

The logic is static/price.js and is tested in price_test.js (a network the test
controls, every arrival order, with the cancel honoured and without); this holds
the page to using it. Fakes only: no model, provider or network.
"""

import os
import shutil
import subprocess
import unittest

from sweep import app as app_module
from sweep.tests.test_app import DERIVED, RAW_PLAN


class TestTheLivePriceWiring(unittest.TestCase):
    """price.js holds the logic (price_test.js); the page has to use it."""

    def page(self, **state):
        app = app_module.create_app(
            state=dict({"profile": "kabir", "cap_usd": 8.41, "derived": DERIVED}, **state),
            extract=lambda p: "x", derive=lambda t, p: DERIVED,
            check_token=lambda t: (8.41, None), fetch_plan=lambda profile: dict(RAW_PLAN))
        app.config.update(TESTING=True)
        app.write_profile = lambda name, source: None
        return app.test_client().get("/configure").get_data(as_text=True)

    def test_the_page_loads_price_js_and_hands_it_the_meter_scope(self):
        body = self.page()
        self.assertIn('src="/static/price.js"', body)
        self.assertIn("x-data='sweepPricer({ est:", body)
        # the scope is an ancestor of <main>, so the form inside it reaches price()
        self.assertLess(body.index("x-data='sweepPricer("), body.index("<main>"))
        # a plain script, so it has run before the deferred Alpine calls sweepPricer
        self.assertIn('<script src="/static/price.js"></script>', body)
        self.assertRegex(body, r'<script defer src="/static/alpine-')

    def test_every_change_asks_through_price_and_nothing_else_fetches(self):
        body = self.page()
        self.assertIn('@change="price($el)"', body)
        self.assertNotIn("fetch(", body)

    def test_the_figures_are_dimmed_on_stale_not_just_busy(self):
        body = self.page()
        self.assertEqual(body.count(":class=\"stale && 'updating'\""), 2,
                         "the lines and the headline figure (the meter's is in its own object)")
        self.assertIn(':class="{ over: est.over_cap, updating: stale, zero: est.total === 0 }"', body)
        self.assertIn('x-show="busy"', body)                # the "re-pricing" word is still the request
        self.assertIn('x-show="err"', body)

    def test_price_js_is_the_file_the_suite_tests(self):
        here = os.path.dirname(os.path.abspath(app_module.__file__))
        self.assertTrue(os.path.exists(os.path.join(here, "static", "price.js")))


class TestThePriceLogic(unittest.TestCase):

    def test_only_the_newest_answer_counts(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        script = os.path.join(os.path.dirname(__file__), "price_test.js")
        run = subprocess.run([node, script], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
