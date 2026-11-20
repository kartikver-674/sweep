"""D7C blocker 6: the last copy and UI fixes, pinned.

  A  the over-credit sentence is worded for the real cause (never "That is $0.00 more than your key has.")
  B  All Jobs says "jobs found" (test_results_ui: it holds the negative scores too)
  C  Filter and sort and Export are easier to find and stay two things
  D  the operator's header: a figure of nothing is not amber, an estimate and what was spent stay apart, and a free sweep
     never talks about credit

No model, provider or network.
"""
import html
import json
import os
import re
import shutil
import subprocess
import unittest

import jinja2

from sweep import app as app_module
from sweep.tests import test_search_prefs as sp
from sweep.tests.test_progress_ui import sweep_app
from sweep.tests.test_results_ui import legacy_app, page, row

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "..", "static")
TEMPLATES = os.path.join(HERE, "..", "templates")
NODE = shutil.which("node")
def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


CONFIGURE = read(TEMPLATES, "configure.html")
CSS = read(STATIC, "sweep.css")


class Quiet(unittest.TestCase):
    def has(self, needle, hay, msg=""):
        if needle not in hay:
            self.fail(msg or f"missing: {needle!r}")

    def lacks(self, needle, hay, msg=""):
        if needle in hay:
            self.fail(msg or f"found: {needle!r}")


def sentence_block():
    """The template's own sentence, as it is written."""
    m = re.search(r"<p :class=\"est\.over_cap \? 'over' : 'muted'\" x-show=\"overWhy\".*?</p>", CONFIGURE, re.S)
    assert m, "the over-credit sentence is gone from configure.html"
    return m.group(0)


def server_words(estimate):
    out = jinja2.Environment(autoescape=True).from_string(sentence_block()).render(estimate=estimate)
    shown = "display:none" not in out.split(">", 1)[0]
    return shown, " ".join(html.unescape(re.sub(r"<[^>]+>", "", out)).split())


COV = lambda placeable, total=90, full=False: {"full": full, "placeable_units": placeable, "total_units": total, "accounts": 2}
CASES = [
    # the plan, then what a visitor is told (None: nothing)
    ({"over_cap": False, "shortfall": 0, "total": 3.0}, None),
    ({"over_cap": True, "shortfall": 1.5, "total": 9.9}, "That is $1.50 more than your key has."),
    ({"over_cap": True, "shortfall": 0, "total": 9.9}, "This costs more than your key's credit covers."),
    ({"over_cap": True, "shortfall": 0.004, "total": 9.9}, "This costs more than your key's credit covers."),
    ({"over_cap": True, "shortfall": 0, "coverage": COV(61)}, "Your connected accounts can run 61 of 90 of these paid searches."),
    ({"over_cap": True, "shortfall": 0, "coverage": COV(0)}, "None of these paid searches fit within the credit on your connected accounts."),
    ({"over_cap": False, "shortfall": 0, "coverage": COV(90, full=True)}, None),
    ({"over_cap": False, "shortfall": 0, "paid_unavailable": True, "coverage": None},
     "Paid searches are temporarily unavailable, so none will start. Nothing is charged."),
    ({"over_cap": True, "shortfall": 2, "coverage": COV(90, full=True)}, "That is $2.00 more than your key has."),
    # A board with no provider ceiling stops the plan: credit is not the cause, so the sentence never blames it.
    ({"over_cap": True, "shortfall": 0, "coverage": dict(COV(60, 70), no_ceiling_cut=True, no_ceiling_sites=["Naukri"])},
     "Naukri can't run on connected Apify keys yet, so 10 of these 70 paid searches are left out."),
    ({"over_cap": True, "shortfall": 0, "coverage": dict(COV(0, 10), no_ceiling_cut=True, no_ceiling_sites=["Naukri"])},
     "Naukri can't run on connected Apify keys yet. Untick it to start the sweep."),
]


class OverCreditWording(Quiet):
    def test_the_page_says_the_real_cause_before_any_script_runs(self):
        for plan, want in CASES:
            with self.subTest(plan=plan):
                shown, text = server_words(plan)
                self.assertEqual(shown, want is not None)
                self.assertEqual(text, want or "")
                self.lacks("$0.00", text)

    @unittest.skipUnless(NODE, "node is not installed")
    def test_the_live_wording_is_the_same_words(self):
        script = ("global.window = {}; eval(require('fs').readFileSync(process.argv[1], 'utf8'));"
                  "const plans = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
                  "process.stdout.write(JSON.stringify(plans.map(p => window.sweepPricer({est: Object.assign({total: 1, lines: []}, p), cap: 8, url: '/e'}).overWhy)));")
        run = subprocess.run([NODE, "-e", script, os.path.join(STATIC, "price.js")], input=json.dumps([p for p, _w in CASES]),
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr[-500:])
        live = json.loads(run.stdout)
        for (plan, want), got in zip(CASES, live):
            with self.subTest(plan=plan):
                self.assertEqual(got, want or "")
                self.assertEqual(got, server_words(plan)[1], "first paint and live update say the same thing")

    def test_the_console_page_with_a_key_that_cannot_cover_the_plan_names_the_dollars(self):
        app = sp.make_app(free=False, cap_usd=0.05)
        app.config["PUBLIC_MODE"] = False
        body = app.test_client().get("/configure").get_data(as_text=True)
        block = re.search(r"<p :class=\"est\.over_cap[^>]*>(.*?)</p>", body, re.S)
        said = " ".join(html.unescape(block.group(1)).split())
        self.assertRegex(said, r"^That is \$0\.\d\d more than your key has\.$")
        self.assertNotEqual(said, "That is $0.00 more than your key has.")

    def test_a_plan_that_fits_has_the_sentence_hidden(self):
        app = sp.make_app(free=False, cap_usd=25.0)
        app.config["PUBLIC_MODE"] = False
        body = app.test_client().get("/configure").get_data(as_text=True)
        self.has('x-show="overWhy"', body)
        self.assertRegex(body, r'x-show="overWhy"[^>]*style="display:none"></p>')

    def test_nothing_in_the_product_can_still_print_a_zero_shortfall(self):
        for name in ("configure.html", "confirm.html"):
            src = read(TEMPLATES, name)
            self.lacks("' more than your key has.'", src.replace("overWhy", ""), name)
        self.lacks("est.shortfall.toFixed(2) + ' more than", CONFIGURE, "the old sentence is in price.js now, behind its cause")


class FilterAndExport(Quiet):
    def results(self):
        return page(legacy_app([row(i, score=str(40 - i)) for i in range(1, 6)], public=True))

    def test_they_are_two_outlined_buttons_not_underlined_words(self):
        body = self.results()
        buttons = re.findall(r'<button type="button" class="(secondary tool-toggle)" aria-controls="(tool-\w+)"[^>]*>(.*?)</button>', body, re.S)
        self.assertEqual([(b[1], " ".join(b[2].split())) for b in buttons], [("tool-filter", "Filter and sort"), ("tool-export", "Export…")])
        self.lacks('class="tertiary tool-toggle"', body)

    def test_export_stays_apart_from_the_filter(self):
        body = self.results()
        filt = body[body.index('id="tool-filter"'):body.index('id="tool-export"')]
        export = body[body.index('id="tool-export"'):]
        self.lacks("Export", filt.split("</form>")[0], "Export is not a control of the filter's form")
        self.has("export.csv", export)
        self.assertEqual(body.count('id="tool-export"'), 1)

    def test_the_style_is_the_products_own_and_quiet(self):
        self.has("button.secondary.tool-toggle { padding:", CSS)
        rule = re.search(r"button\.secondary\.tool-toggle \{[^}]*\}", CSS).group(0)
        self.assertNotRegex(rule, r"background:\s*var\(--(paid|chalk)\b", "no fill: it is an outline")
        self.assertNotRegex(rule, r"will-change|transition: all|box-shadow|filter:")


class OperatorHeader(Quiet):
    def meter(self, body):
        m = re.search(r'<div class="meter ?([^"]*)"[^>]*>', body)
        return m and m.group(1).split()

    def test_a_figure_that_is_exactly_nothing_is_not_amber(self):
        self.lacks("var(--paid)", re.search(r"\.meter\.zero \.numeral \{[^}]*\}", CSS).group(0))
        self.has("var(--chalk)", re.search(r"\.meter\.zero \.numeral \{[^}]*\}", CSS).group(0))
        # ...and the same figure with money in it is, with the base rule that has always made it so
        self.assertRegex(CSS, r"\.numeral \{[^}]*color: var\(--paid\)")

    def test_it_is_set_on_the_free_screens_and_not_when_there_is_money(self):
        free = app_module.create_app(state={"profile": "kabir", "cap_usd": 8.41, "free_only": True},
                                     extract=lambda p: "x", derive=lambda t, p: {}, check_token=lambda t: (8.41, None),
                                     read_rows=lambda profile: [], start_rescore=lambda profile, hours: None)
        free.config.update(TESTING=True, PUBLIC_MODE=False)
        self.assertIn("zero", self.meter(free.test_client().get("/results").get_data(as_text=True)) or [])
        for kw in ({"free": True}, {"free": False}):
            running = sweep_app(public=False, spend=0.0, **kw).test_client().get("/running").get_data(as_text=True)
            self.assertIn("zero", self.meter(running), kw)
        spent = sweep_app(public=False, spend=2.42).test_client().get("/running").get_data(as_text=True)
        self.assertNotIn("zero", self.meter(spent))
        none = sweep_app(public=False, spend=None).test_client().get("/running").get_data(as_text=True)
        self.assertNotIn("zero", self.meter(none), "an unknown figure is not a zero")

    def test_configure_follows_the_estimate_live(self):
        app = sp.make_app(free=True)
        app.config["PUBLIC_MODE"] = False
        body = app.test_client().get("/configure").get_data(as_text=True)
        self.has("zero: est.total === 0", body)
        self.assertIn("zero", self.meter(body))
        paid = sp.make_app(free=False, cap_usd=25.0)
        paid.config["PUBLIC_MODE"] = False
        self.assertNotIn("zero", self.meter(paid.test_client().get("/configure").get_data(as_text=True)))

    def test_a_free_sweep_never_talks_about_credit_and_a_paid_one_still_does(self):
        for public in (False, True):
            free = sweep_app(public=public, free=True, spend=0.0).test_client().get("/running").get_data(as_text=True)
            facts = free.split('class="meter-facts"', 1)
            if public:
                continue                                  # the meter is the operator's; the public screen has none
            self.has("Free sources only", facts[1][:400])
            self.lacks("credit left", facts[1].split("</div>", 1)[0])
        app = sweep_app(public=False, spend=2.42)
        app.state["credit_total_usd"] = 8.41
        paid = app.test_client().get("/running").get_data(as_text=True)
        self.has("credit left", paid.split('class="meter-facts"', 1)[1].split("</div>", 1)[0])
        app = sweep_app(public=False, free=True, spend=0.0)
        app.state["credit_total_usd"] = 8.41             # a key is on file, and the sweep is free
        freekey = app.test_client().get("/running").get_data(as_text=True)
        self.lacks("credit left", freekey.split('class="meter-facts"', 1)[1].split("</div>", 1)[0])

    def test_an_estimate_and_what_was_spent_keep_their_own_words(self):
        configure = sp.make_app(free=False, cap_usd=25.0)
        configure.config["PUBLIC_MODE"] = False
        label = lambda body: " ".join(re.sub(r"<[^>]+>", " ", re.search(r'<span class="label">(.*?)</span>', body.split('class="meter', 1)[1], re.S).group(1)).split())
        self.assertEqual(label(configure.test_client().get("/configure").get_data(as_text=True)), "Estimated cost")
        confirm = label(configure.test_client().get("/confirm").get_data(as_text=True))
        self.assertIn(confirm, ("About to spend",), "the amount to be authorised, said as an intention, not a payment")
        running = label(sweep_app(public=False, spend=2.42).test_client().get("/running").get_data(as_text=True))
        self.assertIn(running, ("Spent so far", "Account spend this month"))
        results = label(page(legacy_app([row(1)], public=False)))
        self.assertEqual(results, "Spent")
        for said in (running, results):
            self.assertNotIn("stimate", said)
        for said in ("Estimated cost", confirm):
            self.assertNotIn("Spent", said)


if __name__ == "__main__":
    unittest.main()
