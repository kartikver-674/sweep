"""A3: the two ways to search are named Quick Sweep and Deep Sweep on PUBLIC screens only.

The names change; the cost facts do not ("paid searches", the "Paid" label, "Nothing to pay"
all stay), and the operator's console keeps its own words. Fakes only: the loopback worker
the public suites use. No model, provider or network.
"""

import io
import os
import re
import shutil
import tempfile
import unittest
from unittest import mock

from sweep import app as app_module
from sweep.tests.test_app import DERIVED
from sweep.tests.test_confirm_ui import KEY_5, KEY_11, CREDIT, PublicSockets
from sweep.tests.test_confirm_ui import (account_reader, c5_pool_plan, recording_worker,
                                         render_app as confirm_app, reviewed, text, worker_client)
from sweep.tests.test_public_copy import CODE, PDF, public_screens, render_app, stack

APIFY_UPLOAD = ("Apify’s free plan includes $5 in monthly credits, with no card required; "
                "actual search usage varies.")
APIFY_KEY = ("Apify’s free plan includes $5 in monthly credits, with no card required. "
             "Actual search usage varies, and you see the estimated cost before anything runs.")


class Quiet(unittest.TestCase):
    """assertIn/assertRegex that name the needle, never print the page."""

    def assertIn(self, needle, hay, msg=None):
        self.assertTrue(needle in hay, msg or f"missing: {needle!r}")

    def assertNotIn(self, needle, hay, msg=None):
        self.assertTrue(needle not in hay, msg or f"unexpected: {needle!r}")

    def assertRegex(self, hay, pattern, msg=None):
        self.assertTrue(re.search(pattern, hay), msg or f"no match: {pattern!r}")


def flat(html):
    return " ".join(html.split())


def free_visitor_pages(paths=("/", "/key", "/configure", "/confirm")):
    with stack() as (url, store):
        app = render_app(url, check_token=lambda t: (4.25, None))
        client = app.test_client()
        client.post("/beta", data={"code": CODE})
        pages = {"/": flat(client.get("/").get_data(as_text=True))}
        client.post("/resume", data={"resume": (io.BytesIO(PDF), "cv.pdf")},
                    content_type="multipart/form-data")
        client.post("/derive")
        client.post("/review", data={"name": "beta_user"})
        pages["/ (after upload)"] = flat(client.get("/").get_data(as_text=True))
        pages["/key"] = flat(client.get("/key").get_data(as_text=True))
        client.post("/key/free")
        for path in ("/configure", "/confirm"):       # T2: "/confirm" leads to the plan screen, which is /configure
            pages[path] = flat(client.get(path, follow_redirects=True).get_data(as_text=True))
        return pages


def console_pages():
    # Rendering /configure and /confirm in local mode stamps profiles/<name>.py, so the app gets a temporary tree:
    # without one this wrote the repository's own profiles/kartik.py every time the module ran (found in A4).
    tmp = tempfile.mkdtemp(prefix="a3-console-")
    os.mkdir(os.path.join(tmp, "profiles"))
    try:
        with mock.patch.object(app_module, "REPO_ROOT", tmp):
            app = app_module.create_app(
                state={"resume_text": "x", "derived": dict(DERIVED), "profile": "kartik",
                       "cap_usd": 4.25, "credit_total_usd": 4.25},
                derive=lambda text, prefs: dict(DERIVED), read_rows=lambda profile: [],
                list_sweeps=lambda profile: [], resume_dir=os.path.join(tmp, "resume"),
                env_path=os.path.join(tmp, "none.env"), output_dir=os.path.join(tmp, "out"))
            app.config["TESTING"] = True
            client = app.test_client()
            return {p: flat(client.get(p).get_data(as_text=True)) for p in ("/", "/key", "/configure", "/confirm")}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class TestPublicNames(Quiet):

    @classmethod
    def setUpClass(cls):
        cls.pages = free_visitor_pages()

    def test_no_public_page_still_says_free_sweep(self):
        for path, html in self.pages.items():
            with self.subTest(path=path):
                self.assertTrue("Free Sweep" not in html and "free sweep" not in html,
                                f"{path} still names the choice 'Free Sweep'")

    def test_the_front_door_names_both_choices_and_carries_the_apify_line(self):
        """A4 moved the two rail blocks ("Quick Sweep", "Deep Sweep, and optional") into the "Is it free?" peek under
        the form: the names and the verified Apify sentence are now the second paragraph of that peek."""
        for path in ("/", "/ (after upload)"):
            html = self.pages[path]
            with self.subTest(path=path):
                self.assertIn("A Quick Sweep is free too. A Deep Sweep adds LinkedIn, Indeed and Naukri "
                              "through your own Apify account, which bills per search. " + APIFY_UPLOAD, html)
                self.assertIn('<span class="peek-label">Is it free?</span>', html)
                # the cost fact stays explicit on the front door (A3's rule: names change, money is never vague)
                self.assertIn("which bills per search", html)
                # the rail blocks are gone from public, and the old names with them
                self.assertNotIn('<h2 class="label free">Quick Sweep</h2>', html)
                self.assertNotIn('<h2 class="label paid">Deep Sweep, and optional</h2>', html)
                self.assertNotIn("Paid, and optional", html)

    def test_key_names_both_choices_and_carries_the_apify_line(self):
        """A6 reshaped /key into two radio cards: the names moved from <h2>s to the cards' names, the "Deep Sweep: add ..."
        disclosure became the sticker and the card's second line, and the "Nothing to pay" tick became "Free, no setup."
        on the Quick card. The Apify line, its order and the cost words ("charges per search") are exactly as they were."""
        html = self.pages["/key"]
        self.assertIn('<span class="nm">Quick Sweep</span>', html)
        self.assertRegex(html, r">Start Quick Sweep<span")
        self.assertIn('<span class="nm">Deep Sweep</span>', html)
        self.assertRegex(html, r'<span class="sticker cit" aria-hidden="true">\+\d+ big boards</span>')       # citrus: peach is money's, and this is not a price
        self.assertNotIn(" too?</h2>", html)
        self.assertIn("<p>" + APIFY_KEY + "</p>", html)
        # directly after the paragraph that says Apify charges per search
        self.assertLess(html.index("charges per search.</p>"), html.index(APIFY_KEY))
        self.assertLess(html.index(APIFY_KEY), html.index("Sweep uses <b>your own</b>"))
        self.assertIn("Company career pages and public job boards. Free, no setup.", html)

    def test_configure_and_confirm_free_say_quick_sweep(self):
        self.assertIn("This is a Quick Sweep, so Sweep searches", self.pages["/configure"])
        self.assertRegex(self.pages["/configure"], r">Start Quick Sweep<span")
        self.assertIn("Free — no account needed and nothing to pay.", self.pages["/configure"])
        self.assertRegex(self.pages["/confirm"], r"Start Quick Sweep<span")
        self.assertRegex(self.pages["/confirm"], r"(\d+ free|<b>Free</b>|Free) job boards?")      # T2: the plan screen's own summary


class TestEveryPublicScreen(Quiet):

    def test_no_screen_on_either_path_names_a_free_or_paid_sweep(self):
        for free in (True, False):
            with public_screens(free=free) as pages:
                for path, html in pages.items():
                    for old in ("Free Sweep", "free sweep", "Paid sweep", "paid sweep"):
                        with self.subTest(free=free, path=path, old=old):
                            self.assertNotIn(old, html)


class TestDeepSweepConfirm(Quiet, PublicSockets):

    def confirm(self, credit):
        CREDIT.update({KEY_5: 5.0, KEY_11: 11.0})
        self.addCleanup(lambda: [CREDIT.pop(k, None) for k in (KEY_5, KEY_11)])
        with recording_worker() as (url, store, queue, spawned):
            app = confirm_app(url, read_account=account_reader(lambda t: (CREDIT[t], None)))
            client = reviewed(app, "beta_user")
            with mock.patch.object(worker_client, "plan", lambda *a, **kw: c5_pool_plan()):
                client.post("/key", data={"token": credit})
                return client.get("/configure").get_data(as_text=True)      # T2: the plan screen (Configure and Confirm are one)

    def test_a_covered_paid_confirm_starts_a_deep_sweep_and_still_prices_it(self):
        page = self.confirm(KEY_11)
        t = text(page)
        self.assertRegex(t, r"Start the sweep · \$\d")                  # T2: the ticket's Start (it was "Start Deep Sweep · $N")
        self.assertIn("Step 3 · Deep Sweep", t)                          # ...and the screen is still named Deep
        self.assertNotIn("Free Sweep", t)
        self.assertNotIn("Start Sweep", t)
        self.assertRegex(t, r"\d+ paid, plus the free boards")
        self.assertIn("Estimated cost", t)

    def test_a_short_paid_confirm_keeps_its_cost_words(self):
        t = text(self.confirm(KEY_5))
        self.assertIn("Your connected accounts can run 48 of 90 of these paid searches.", t)
        self.assertRegex(t, r"Run what fits, \$\d")
        self.assertNotIn("Free Sweep", t)


class TestTheConsoleIsUntouched(Quiet):

    @classmethod
    def setUpClass(cls):
        cls.pages = console_pages()

    def test_no_new_name_reaches_the_console(self):
        for path, html in self.pages.items():
            with self.subTest(path=path):
                self.assertNotIn("Quick Sweep", html)
                self.assertNotIn("Deep Sweep", html)
                self.assertNotIn("monthly credits", html)

    def test_the_console_keeps_its_old_words(self):
        self.assertIn('<h2 class="label free">Free</h2>', self.pages["/"])
        self.assertIn('<h2 class="label paid">Paid, and optional</h2>', self.pages["/"])
        self.assertIn("a free sweep needs no key", self.pages["/"])
        self.assertIn("Free or paid", self.pages["/key"])
        self.assertIn("Free sources and the paid boards", self.pages["/key"])


if __name__ == "__main__":
    unittest.main()
