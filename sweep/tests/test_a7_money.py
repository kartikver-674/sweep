"""Direction A, stage A7 (and T2): the public plan screen. This is the money path.

THE CONTRACT (A7 changed none of it; T2 moved it). Every named control on Configure, in document order, with its name, type and
value; the form's own tag, its scope, `@change="price($el)"` and the Alpine code of the location picker; the estimate request and
response; every over-credit sentence (price.js `overWhy` and its server-rendered twin); `static/price.js` byte for byte.

T2 made Configure and Confirm ONE public screen (GET /configure; public GET /confirm redirects to it), and the Deep Sweep's aside
the plan ticket: what is searched, the credit jar beside the price, and a stub that holds either Start (the plan is covered) or two
coupons (it is not: add a key, or run what fits, picked first and then confirmed by a button of its own). Every public form posts to
POST /run, which holds a paid Sweep to the price its ticket showed (`quoted_total`). What Confirm pinned (every verdict sentence, the
Start / Run labels and their disabled states, the over-cap box) is pinned below in the ticket's terms: the same decisions, said by
the ticket. The Confirm strings in CONFIRM_AT_HEAD were read off HEAD (6e6719d) before A7 touched a template and are kept as the
record of what the console's Confirm still says; the console's Confirm is byte-pinned in TheConsoleIsUntouched.

Around it: the new words and parts (eyebrow, headline, lede; the free-boards chip and the paid boards as toggle chips; the scope
pills; the credit jar, with its fill, its credit line and its over state; the "fits" line; the two peeks; the phone strip; the
ticket's stamp, lines, stub, coupons and accounts), and the operator's console untouched (its rendered bytes pinned, state by state).

The jar's truth is the estimate's and nothing else: its `over` is `est.over_cap` (never computed from the fill), its fill is the
estimate's share of the credit of the accounts the sweep would spend from, its credit line exists only when the estimate carries
coverage. Fakes only: the loopback worker the public suites use. No model, provider, network or real key.
"""
import hashlib
import html
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import unittest
from unittest import mock

from sweep import app as app_module
from sweep import runs as runs_mod
from sweep.tests import test_multi_setup as multi
from sweep.tests.test_a6_key import main_of
from sweep.tests.test_public_sweep import over_sentence, plan_error, quote, shown
from sweep.tests.test_search_v2_d import (CREDIT, KEY_5, KEY_11, SEARCH, PublicSockets, account_reader, c5_pool_plan, pool_plan,
                                          recording_worker, render_app, reviewed, worker_client)

ROOT = pathlib.Path(app_module.__file__).parent
REPO = ROOT.parent
CSS = (ROOT / "static" / "sweep-a.css").read_text()
A7_CSS = re.sub(r"/\*.*?\*/", "", CSS[CSS.rindex("/*", 0, CSS.index("==== A7: Configure and Confirm")):CSS.rindex("/*", 0, CSS.index("==== A8: Progress"))], flags=re.S)   # this stage's section: to where A8's begins
T2_CSS = re.sub(r"/\*.*?\*/", "", CSS[CSS.rindex("/*", 0, CSS.index("==== T2: the plan ticket")):CSS.rindex("/*", 0, CSS.index("==== A6: Search coverage"))], flags=re.S)   # the plan ticket's section
CONFIGURE = (ROOT / "templates" / "configure.html").read_text()
CONFIRM = (ROOT / "templates" / "confirm.html").read_text()
PRICE_JS = (ROOT / "static" / "price.js").read_text()

KEY_9 = "apify_api_VISITOR_NINE_DOLLARS_000"      # $8.99 of room: more than the $6.97 estimate, less than the plan's provider ceilings
KEY_TINY = "apify_api_VISITOR_TINY_0000000000"     # $0.04 of room: nothing fits
KEY_ZERO = "apify_api_VISITOR_ZERO_00000000000"    # $0.00 of room
NO_PAID_LINES = lambda: {"profile": "beta", "sites": {}, "max_results": {}, "free_sources": 5, "public_paid": "multi"}  # noqa: E731

# sha256 of static/price.js. A reskin may not change it: the estimate, the one answer that counts and every over-credit sentence
# live there. If this fails, the money display changed; that is not a reskin. T2 changed it on purpose: the plan ticket's `boards`
# and `paidSearches` getters and `ink(el, value)` (the wash on a line that changed); estimate, overWhy and soon() are as they were
# (sweep/tests/price_test.js pins them, and the new getters, in node). Changed on purpose again: overWhy names a board with no
# provider ceiling (Naukri) as the cut instead of blaming the credit (test_d7c_copy pins those words, server and live).
PRICE_JS_SHA256 = "4a82a8e88f5ead98892c1844372ba9fa5488525cc593f19709c8e9a940011d1e"

# What Configure's form posts, in document order: (tag, name, type, value for hidden / checkbox / radio, else None).
DEEP_CONTROLS = [
    ("input", "sites_present", "hidden", "1"),
    ("input", "site_linkedin", "checkbox", None),
    ("input", "site_indeed", "checkbox", None),
    ("input", "site_naukri", "checkbox", None),
    ("input", "scope", "radio", "india"),
    ("input", "scope", "radio", "remote"),
    ("input", "scope", "radio", "global"),
    ("input", "locations", "hidden", ""),
    ("select", "max_age_days", None, None),
    ("input", "max_results", "number", None),
    ("input", "min_comp_usd", "number", None),
    ("input", "avoid", "text", None),
    ("input", "quoted_total", "hidden", "@total"),      # T2: the ticket's stub posts the price it shows, for /run to hold the Sweep to
]
QUICK_CONTROLS = [c for c in DEEP_CONTROLS if c[1] not in ("sites_present", "site_linkedin", "site_indeed", "site_naukri", "max_results", "quoted_total")]

# What HEAD's Confirm said, state by state: the verdict sentence, the Start / Run label, the button's tag, whether the over-cap box
# was there and whether the add-a-key door was open. The CONSOLE's Confirm still says all of it (it is byte-pinned below); the
# public plan screen says the same decisions through the ticket (ThePlanTicket), whose pins quote these figures.
CONFIRM_AT_HEAD = {
    "full": dict(
        verdict="Your connected Apify accounts can cover the full Sweep.", classes=["verdict ok"],
        label="Start Deep Sweep · $6.97 →", tag='<button class="primary big" type="submit" :disabled="sent">', box=False, door="shut",
        capacity="Available Apify credit $10.99 across 1 account Searches covered 90 of 90 paid searches"),
    "partial5": dict(
        verdict="Your connected Apify accounts don't currently have enough available credit for the estimated cost of the complete "
                "Sweep. Your current accounts can safely cover 48 of 90 paid searches, estimated at $3.19. Add another Apify key for "
                "the full Sweep, or run the covered portion.", classes=["verdict short"],
        label="Run what my credit covers · $3.19 →", tag='<button class="primary big" type="submit" :disabled="sent || !ack">',
        box=True, door="open", capacity="Available Apify credit $4.99 across 1 account Searches covered 48 of 90 paid searches"),
    "partial9": dict(
        verdict="Your current Apify accounts don't have enough available provider capacity to safely run every search in this Sweep. "
                "They can safely cover 78 of 90 paid searches, estimated at $5.89. Add another Apify key for the complete Sweep, or "
                "run the portion your current accounts can cover.", classes=["verdict short"],
        label="Run what my credit covers · $5.89 →", tag='<button class="primary big" type="submit" :disabled="sent || !ack">',
        box=True, door="open", capacity="Available Apify credit $8.99 across 1 account Searches covered 78 of 90 paid searches"),
    "none": dict(
        verdict="Your connected Apify accounts don't currently have enough available credit for the estimated cost of the complete "
                "Sweep. Your current accounts can safely cover 0 of 90 paid searches. Add another Apify key for the full Sweep.",
        classes=["verdict short"], label="Run what my credit covers →",
        tag='<button class="primary big" type="submit" disabled :disabled="sent || !ack">', box=False, door="open",
        capacity="Available Apify credit $0.04 across 1 account Searches covered 0 of 90 paid searches"),
    # A11, owner-approved wording: was "You can search the free sources now from the free or paid step".
    "unavail": dict(
        verdict="Paid searches are temporarily unavailable Sweep can't safely check your Apify credit against this search right now, "
                "so it won't start any paid search. Nothing has been charged. You can run a Quick Sweep now from the Search "
                "coverage step, or come back later.", classes=["verdict short"], label="Paid searches unavailable",
        tag='<button class="primary big" type="submit" disabled :disabled="sent || true">', box=False, door="absent", capacity=None),
    "free": dict(
        verdict=None, classes=[], label="Start Quick Sweep →", tag='<button class="primary big" type="submit" :disabled="sent">',
        box=False, door="absent", capacity=None),
}
DURATION = ("Searching takes a few minutes to a few tens of minutes, depending on how wide your search is. You can close this tab — "
            "Sweep keeps searching.")



def plain(markup):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", markup)).split())


def estimate_of(body):
    """The estimate the page starts Alpine from: the dict price.js is handed, read back out of the page."""
    at = body.index("sweepPricer({ est: ") + len("sweepPricer({ est: ")
    return json.JSONDecoder().raw_decode(body[at:])[0]


def fill_for(est):
    """The jar's fill (percent), by the brief's rule, from the estimate alone."""
    cov = est.get("coverage")
    if not cov:
        return 0.0                                  # no paid lines, or paid searches unavailable
    if cov["available_usd"] > 0:
        return min(100.0, est["total"] / cov["available_usd"] * 88)
    return 100.0 if est["total"] > 0 else 0.0


def over_why(est):
    """price.js's own sentence for this estimate: the real file, run by node."""
    script = ("global.window = {}; require(process.argv[1]); "
              "const p = window.sweepPricer({ est: JSON.parse(process.argv[2]), cap: 0, url: '/' }); process.stdout.write(p.overWhy);")
    done = subprocess.run(["node", "-e", script, str(ROOT / "static" / "price.js"), json.dumps(est)],
                          capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    return done.stdout


HAS_NODE = shutil.which("node") is not None


class Sessions(PublicSockets):
    """Real renders of the public plan screen, one per state, built once per class and kept as strings."""

    CACHE = {}

    def visit(self, url, credit=None, plan=c5_pool_plan, free=False, hour=12, more=(), done=0):
        CREDIT.update({KEY_5: 5.0, KEY_11: 11.0, KEY_9: 9.0, KEY_TINY: 0.05, KEY_ZERO: 0.01})
        self.addCleanup(lambda: [CREDIT.pop(k, None) for k in (KEY_5, KEY_11, KEY_9, KEY_TINY, KEY_ZERO)])
        # The hour is the app's wall clock: the late-night warning on the ticket (a sweep past midnight re-bills) shows from 22:00,
        # so a state is rendered at noon unless it is about that.
        extra = {}
        if done:       # the first `done` LinkedIn searches already finished today
            extra["read_done"] = lambda profile, day: {runs_mod.combo_key(day, "linkedin", s)
                                                       for s in plan()["sites"]["linkedin"][:done]}
        app = render_app(url, read_account=account_reader(lambda t: (CREDIT[t], None)), hour_now=lambda: hour, **extra)
        client = reviewed(app, "beta_user")
        patch = mock.patch.object(worker_client, "plan", lambda *a, **kw: plan())
        patch.start()
        self.addCleanup(patch.stop)
        if free:
            client.post("/key/free")
        else:
            answer = client.post("/key", data={"token": credit})
            assert answer.status_code in (302, 303), (credit, answer.status_code)
            for token in more:                      # more accounts, added the way the plan's accounts list does
                answer = client.post("/key", data={"token": token, "back": "confirm"})
                assert answer.status_code in (302, 303), (token, answer.status_code)
        return client

    def state(self, label):
        if not Sessions.CACHE:
            recipes = {
                "full": dict(credit=KEY_11), "partial5": dict(credit=KEY_5), "partial9": dict(credit=KEY_9),
                "none": dict(credit=KEY_TINY), "unavail": dict(credit=KEY_11, plan=lambda: pool_plan(None)),
                "nolines": dict(credit=KEY_11, plan=NO_PAID_LINES), "free": dict(free=True),
                "late": dict(credit=KEY_11, hour=23), "two": dict(credit=KEY_11, more=(KEY_9,)),
                "done": dict(credit=KEY_11, done=5),
            }
            for name, kw in recipes.items():
                with recording_worker() as (url, store, queue, spawned):
                    client = self.visit(url, **kw)
                    Sessions.CACHE[name] = {"configure": client.get("/configure").get_data(as_text=True)}
        return Sessions.CACHE[label]

    def configure(self, label):
        body = self.state(label)["configure"]
        return body, main_of(body)


def named_controls(main):
    form = main.one("form", "split")
    out = []
    for n in form.walk():
        if n.tag in ("input", "select", "textarea") and n.attrs.get("name"):
            kind = n.attrs.get("type")
            out.append((n.tag, n.attrs["name"], kind, n.attrs.get("value", "") if kind in ("hidden", "checkbox", "radio") and "value" in n.attrs
                        else (None if kind in ("checkbox", "radio") else ("" if kind == "hidden" else None))))
    return out


# =====================================================================================================================
class TheTopOfTheScreen(Sessions):
    def test_deep_and_quick_open_with_the_eyebrow_the_headline_and_the_lede(self):
        # T2: one screen to plan and start, so it says "Plan your sweep" (it said "Where should we look?"), and the lede names
        # the ticket that reprints when a setting changes; a free Sweep has no ticket, so it says "or start".
        for label, eyebrow, lede in (
                ("full", "Step 3 · Deep Sweep", "Already set from your résumé. Change anything and the ticket reprints."),
                ("free", "Step 3 · Quick Sweep", "Already set from your résumé. Change anything, or start.")):
            body, main = self.configure(label)
            top = main.find(cls="stack-tight")[0]
            with self.subTest(label=label):
                self.assertEqual(top.one(cls="eyebrow").text(), eyebrow)
                self.assertEqual(main.one("h1").text(), "Plan your sweep.")
                self.assertIn('<h1>Plan your <span class="scrib">sweep</span>.</h1>', body)
                self.assertEqual(top.one(cls="lede").text(), lede)
                self.assertLess(body.index('class="eyebrow"'), body.index("<h1>"))
                self.assertEqual(body.count('class="eyebrow"'), 1)
                for gone in ("Search preferences", "go straight to searching", "Change anything you like",
                             "Where should we", "Ready when", "Here’s your sweep, on one ticket"):
                    self.assertNotIn(gone, body)

    def test_the_lede_says_resumes_when_there_are_several(self):
        self.assertIn("{{ 'résumés' if multi_sweep else 'résumé' }}", CONFIGURE)

    def test_only_deep_has_a_cost_heading_to_link_to(self):
        for label, want in (("full", 1), ("partial5", 1), ("unavail", 1), ("nolines", 1), ("free", 0)):
            body, _ = self.configure(label)
            with self.subTest(label=label):
                self.assertEqual(body.count('id="cost-h"'), want)
                self.assertEqual(body.count('id="ticket-h"'), want)
        body, main = self.configure("full")
        heading = main.one("h3", id="cost-h")
        self.assertEqual(heading.text(), "Estimated cost re-pricing")          # the second word is the busy note (hidden until a price is out)
        self.assertEqual(heading.one(cls="sending").attrs.get("x-show"), "busy")
        self.assertEqual(main.one("section", "pt-cost").attrs.get("aria-labelledby"), "cost-h")


class TheForm(Sessions):
    def test_the_named_controls_in_document_order_are_the_pinned_list(self):
        for label, want in (("full", DEEP_CONTROLS), ("partial5", DEEP_CONTROLS), ("free", QUICK_CONTROLS)):
            body, main = self.configure(label)
            if want is DEEP_CONTROLS:       # the quote is the estimate's own total, whatever the state
                want = [(t, n, k, "%.2f" % estimate_of(body)["total"] if v == "@total" else v) for t, n, k, v in want]
            with self.subTest(label=label):
                self.assertEqual(named_controls(main), want)

    def test_the_submits_are_the_forms_own_and_a_ticket_has_exactly_the_ones_it_names(self):
        """Quick: one submit, the Start. Deep (T2): the ticket's stub holds Start, and, over the credit, the two buttons its coupons
        reveal; each Remove in the accounts list submits its own hidden forget form (form="forget-N"), never this one."""
        _, main = self.configure("free")
        form = main.one("form", "split")
        submits = [n for n in form.walk() if (n.tag == "button" and n.attrs.get("type", "submit") == "submit")
                   or (n.tag == "input" and n.attrs.get("type") == "submit")]
        self.assertEqual(len(submits), 1, [n.attrs for n in submits])
        self.assertIn("primary", submits[0].classes())
        self.assertEqual(len([n for n in main.walk() if n.tag == "button" and n.attrs.get("type") == "submit"]), 1)
        for label in ("full", "partial5", "none", "unavail", "nolines", "two"):
            _, main = self.configure(label)
            form = main.one("form", "split")
            submits = [n for n in form.walk() if (n.tag == "button" and n.attrs.get("type", "submit") == "submit")
                       or (n.tag == "input" and n.attrs.get("type") == "submit")]
            own = [n for n in submits if "form" not in n.attrs]
            removes = [n for n in submits if "form" in n.attrs]
            with self.subTest(label=label):
                self.assertEqual([(n.attrs.get("name"), n.attrs.get("value"), n.attrs.get("formaction")) for n in own],
                                 [(None, None, None), ("then", "key", "/configure"), ("over_cap_ack", "yes", None)])
                self.assertTrue(all("primary" in n.classes() for n in own))
                self.assertEqual([n.within("div").classes() for n in own], [["pt-go"], ["pt-coupons"], ["pt-coupons"]])
                self.assertTrue(all(n.text() == "Remove" and re.fullmatch(r"forget-\d", n.attrs["form"]) for n in removes))
                self.assertEqual(len(removes), 2 if label == "two" else 1 if label != "unavail" else 0, [n.attrs for n in removes])

    def test_the_form_the_scope_and_the_price_check_are_the_same(self):
        for label in ("full", "free"):
            body, _ = self.configure(label)
            tag = re.search(r'<form class="split"[^>]*>', body, re.S).group(0)
            with self.subTest(label=label):
                # T2: both post straight to /run (a paid Sweep is held there to the price its ticket showed)
                self.assertRegex(tag, r'^<form class="split" method="post"\s+action="/run"')
                self.assertIn("x-data='{ scope:", tag)
                self.assertEqual(len(re.findall(r"\bpicked:", tag)), 1)
                self.assertIn('@change="price($el)"', tag)
                self.assertIn('@submit="sent = true"', tag)
                self.assertIn("x-init=\"$watch('scope', () =&gt; narrow())\"", tag)
                self.assertEqual(body.count('class="panel summary-panel"'), 1 if label == "free" else 0)   # Deep's is the ticket
                self.assertEqual(body.count('class="pticket"'), 0 if label == "free" else 1)
                self.assertIn('<details class="advanced">', body)
                self.assertRegex(body, r'<section class="setting" aria-labelledby="locations-h" x-show="scope !== \'remote\'"')

    def test_the_scope_radios_are_still_radios_with_one_name_and_x_model(self):
        _, main = self.configure("full")
        radios = [n for n in main.walk() if n.tag == "input" and n.attrs.get("name") == "scope"]
        self.assertEqual([r.attrs["value"] for r in radios], ["india", "remote", "global"])
        for r in radios:
            self.assertEqual(r.attrs.get("type"), "radio")
            self.assertEqual(r.attrs.get("x-model"), "scope")
        self.assertEqual(len([r for r in radios if "checked" in r.attrs]), 1)
        group = radios[0].within(cls="stack-tight")
        self.assertEqual(group.attrs.get("role"), "radiogroup")
        for choice in group.find("label", "choice"):
            self.assertEqual(len(choice.find(cls="why")), 1)       # the explanation stays in the markup; CSS shows it under the chosen one

    def test_the_paid_boards_are_toggle_chips_the_same_labels_the_same_inputs(self):
        _, main = self.configure("full")
        boards = main.one(cls="boards")
        self.assertIn("stack-tight", boards.classes())
        chip = boards.one(cls="free-chip")
        self.assertEqual(chip.text(), "✓ 5 free job boards always on")
        self.assertEqual([c.text() for c in boards.find("label", "choice")], ["LinkedIn", "Indeed", "Naukri"])
        for c in boards.find("label", "choice"):
            box = c.find("input")[0]
            self.assertEqual(box.attrs.get("type"), "checkbox")
            self.assertTrue(box.attrs["name"].startswith("site_"))
        self.assertLess(boards.kids.index(chip), boards.kids.index(boards.find("label", "choice")[0]))   # before the paid boards
        quick, _ = self.configure("free")
        self.assertNotIn("free-chip", quick)
        self.assertNotIn('class="stack-tight boards"', quick)

    def test_the_free_chip_counts_the_boards_the_plan_has(self):
        self.assertIn("' free job board' ~ ('' if facts.free_sources == 1 else 's') if facts.free_sources else 'Free job boards'", CONFIGURE)


class TheAside(Sessions):
    def test_the_ticket_says_what_is_searched_in_five_lines_and_has_no_summary_peek(self):
        """T2: Deep's "What Sweep will search" peek is gone: the first half of the ticket says it, always open."""
        body, main = self.configure("full")
        ticket = main.one("aside", "cf-ticket")
        lines = ticket.one("dl", "pt-lines")
        self.assertEqual([(r.one("dt").text(), r.one("dd").text()) for r in lines.find(cls="pt-line")], [
            ("Searching for", "React Native Developer, Full Stack Engineer"), ("Jobs", "In India, or remote open to India"),
            ("Where", "Anywhere in India"), ("Boards", "LinkedIn, Indeed, and the free boards"),
            ("Searches", "90 paid, plus the free boards")])
        # the four that follow the settings are written in again when they change (price.js ink); the roles are the résumé's, not a setting
        self.assertEqual([r.attrs.get("x-effect") for r in lines.find(cls="pt-line")],
                         [None, "ink($el, scopeText())", "ink($el, whereText())", "ink($el, boards)", "ink($el, paidSearches)"])
        self.assertEqual([p.one(cls="peek-label").text() for p in ticket.find("details", "peek")],
                         ["How is this worked out?", "Your Apify accounts (1)"])
        self.assertEqual(ticket.find("dl", "summary"), [])
        self.assertIn("{{ 'Résumés' if multi_sweep else 'Searching for' }}", CONFIGURE)       # several résumés: the first line names them
        self.assertEqual(ticket.one(cls="stamp").text(), "Not started")
        self.assertEqual(ticket.one("h2", id="ticket-h").text(), "Your sweep")

    def test_quick_keeps_its_summary_visible_and_has_no_peek(self):
        body, main = self.configure("free")
        panel = main.one(cls="summary-panel")
        self.assertEqual(panel.find("h2")[0].text(), "What Sweep will search")
        self.assertEqual(len(panel.find("dl", "summary")), 1)
        self.assertEqual(panel.find("dl", "summary")[0].within("details"), None)
        self.assertEqual(panel.find("details"), [])
        self.assertIn("Free — no account needed and nothing to pay.", panel.text())
        self.assertIn("aside cf-quick", body)
        self.assertEqual(main.find(cls="jar"), [])
        self.assertEqual(main.find(cls="cf-strip"), [])
        self.assertNotIn("Estimated cost", panel.text())
        self.assertEqual(len(panel.find("button", type="submit")), 1)
        self.assertEqual(panel.find("button", type="submit")[0].text(), "Start Quick Sweep→")

    def test_the_lines_table_is_in_its_own_peek_under_the_figure(self):
        _, main = self.configure("full")
        figure = main.one(cls="pt-figure")
        table = figure.one("table", "lines")
        peek = table.within("details", "peek")
        self.assertEqual(peek.one(cls="peek-label").text(), "How is this worked out?")
        self.assertIs(peek.parent, figure)
        self.assertIn(':class="stale && \'updating\'"', html.unescape(re.search(r'<table class="lines"[^>]*>', self.state("full")["configure"], re.S).group(0)))
        self.assertEqual(table.attrs.get("x-show"), "est.lines.length")
        self.assertEqual(len(figure.find("template", **{"x-for": "line in est.lines"})), 1)
        # the figure's own order: its heading, the number, the error line, the "fits" line, the over sentence, the
        # single-account note, the peek
        names = [(n.tag, " ".join(n.classes())) for n in figure.kids if not isinstance(n, str)]
        self.assertEqual(names, [("h3", "label"), ("p", "numeral"), ("p", "error"), ("p", "fits"), ("p", "over"), ("p", "meta"),
                                 ("details", "peek")])
        # no paid board on: the ticket says "Free boards only" and prices $0.00, and the table is hidden (there is nothing to list)
        body, nolines = self.configure("nolines")
        self.assertEqual(nolines.one("dd", **{"x-text": "boards"}).text(), "Free boards only")
        self.assertEqual(nolines.one("table", "lines").attrs.get("style"), "display:none")
        self.assertEqual(estimate_of(body)["lines"], [])

    def test_the_money_figure_keeps_every_binding_the_suites_and_the_flows_read(self):
        body, main = self.configure("full")
        self.assertIn(""":class="stale && 'updating'\"""", body)
        self.assertIn(""":class="{ over: est.over_cap, updating: stale }" x-text="'$' + est.total.toFixed(2)\"""", body)
        self.assertEqual(main.one("p", "numeral").attrs.get("aria-live"), "polite")
        why = main.one("p", **{"x-show": "overWhy"})
        self.assertEqual(why.attrs.get("x-text"), "overWhy")
        self.assertEqual(len(main.find("p", **{"x-show": "overWhy"})), 1)
        self.assertEqual(main.one("span", cls="sending", **{"x-show": "busy"}).text(), "re-pricing")
        self.assertEqual(main.one("p", "error", **{"x-show": "err"}).attrs.get("x-text"), "err")

    def test_the_positive_line_is_there_only_when_the_engine_says_the_whole_plan_fits(self):
        for label, shown in (("full", True), ("partial9", False), ("partial5", False), ("none", False), ("unavail", False),
                             ("nolines", False)):
            body, main = self.configure(label)
            fits = main.one("p", "fits")
            est = estimate_of(body)
            with self.subTest(label=label):
                self.assertEqual(fits.text(), "Your connected Apify accounts can cover the full Sweep.")
                self.assertEqual(fits.attrs.get("x-show"), "est.coverage && est.coverage.full && !est.over_cap")
                self.assertEqual("style" not in fits.attrs, shown)
                if "style" in fits.attrs:
                    self.assertEqual(fits.attrs["style"], "display:none")
                self.assertEqual(shown, bool(est.get("coverage") and est["coverage"]["full"] and not est["over_cap"]))
                # it is not the overWhy sentence, which says nothing when the plan is covered
                self.assertNotEqual(fits.attrs.get("x-show"), "overWhy")
                self.assertIsNone(fits.within(cls="panel-head"))
            self.assertEqual(len(main.find("p", **{"x-show": "overWhy"})), 1)


class TheJar(Sessions):
    JAR_CLASS_BINDING = "{ off: est.paid_unavailable, over: est.over_cap, wobble: wob, updating: stale }"
    FILL_BINDING = ("'height: ' + (est.coverage ? (est.coverage.available_usd > 0 ? Math.min(100, est.total / "
                    "est.coverage.available_usd * 88) : (est.total > 0 ? 100 : 0)) : 0) + '%'")

    def jar(self, label):
        body, main = self.configure(label)
        return body, main, main.one(cls="jar"), estimate_of(body)

    def height(self, jar):
        return float(re.fullmatch(r"height: ([\d.]+)%", jar.one(cls="jar-fill").attrs["style"]).group(1))

    def test_it_is_decoration_with_the_pinned_bindings(self):
        for label in ("full", "partial9", "none", "unavail", "nolines"):
            _, _, jar, _ = self.jar(label)
            with self.subTest(label=label):
                self.assertEqual(jar.attrs.get("aria-hidden"), "true")
                self.assertEqual(jar.attrs.get("x-data"), "{ wob: false }")
                self.assertEqual(jar.attrs.get(":class"), self.JAR_CLASS_BINDING)
                self.assertEqual(jar.attrs.get("@animationend"), "wob = false")
                init = jar.attrs.get("x-init")
                self.assertIn("$watch('est.over_cap', (v, was) =>", init)
                self.assertIn("if (v && !was) { wob = false; $nextTick(() => { wob = true }) }", init)
                self.assertEqual(jar.one(cls="jar-fill").attrs.get(":style"), self.FILL_BINDING)
                self.assertEqual(jar.find(cls="jar-fill")[0].text(), "")
                # the fill sits in the jar's inside, which clips it to the curve (a sliver of a fill used to poke out)
                self.assertEqual(jar.one(cls="jar-fill").parent.classes(), ["jar-in"])
                self.assertIs(jar.one(cls="jar-in").parent, jar)
                self.assertEqual(len(jar.find("button")) + len(jar.find("input")) + len(jar.find("a")), 0)   # nothing to press
                self.assertIn("pt-cost", jar.parent.classes())          # T2: the jar is the first half of the ticket's cost section

    def test_over_is_the_estimates_over_cap_and_never_the_fill(self):
        for label in ("full", "partial9", "partial5", "none", "unavail", "nolines"):
            body, _, jar, est = self.jar(label)
            binding = jar.attrs[":class"]
            with self.subTest(label=label):
                self.assertRegex(binding, r"\bover:\s*est\.over_cap\b")
                self.assertNotIn("fill", binding)
                self.assertNotRegex(binding, r"\b88\b|>=|<=|\d")
                self.assertNotIn("fill", jar.attrs.get("x-init", ""))
                self.assertEqual("over" in jar.classes(), bool(est["over_cap"]))
                self.assertEqual("off" in jar.classes(), bool(est.get("paid_unavailable")))

    def test_the_server_rendered_fill_follows_the_rule_for_every_state(self):
        for label in ("full", "partial9", "partial5", "none", "unavail", "nolines"):
            _, _, jar, est = self.jar(label)
            with self.subTest(label=label):
                self.assertAlmostEqual(self.height(jar), fill_for(est), delta=0.06)

    def test_fully_covered_the_fill_is_under_the_line_and_not_over(self):
        _, _, jar, est = self.jar("full")
        self.assertTrue(est["coverage"]["full"])
        self.assertFalse(est["over_cap"])
        self.assertAlmostEqual(est["total"] / est["coverage"]["available_usd"] * 88, 55.8, delta=0.1)
        self.assertAlmostEqual(self.height(jar), 55.8, delta=0.1)
        self.assertNotIn("over", jar.classes())

    def test_partly_covered_can_be_over_with_the_fill_under_the_line(self):
        """Placement, not the estimate, decides in public mode: $8.99 is more than the $6.97 estimate, but the plan's provider
        ceilings do not all fit, so the plan is over (the sentence says why) while the fill is honest about the estimate."""
        _, _, jar, est = self.jar("partial9")
        self.assertGreater(est["coverage"]["available_usd"], est["total"])
        self.assertFalse(est["coverage"]["full"])
        self.assertTrue(est["over_cap"])
        self.assertLess(self.height(jar), 88)
        self.assertAlmostEqual(self.height(jar), est["total"] / est["coverage"]["available_usd"] * 88, delta=0.06)
        self.assertIn("over", jar.classes())

    def test_a_fill_is_never_drawn_past_the_top(self):
        for label in ("partial5", "none"):
            _, _, jar, est = self.jar(label)
            with self.subTest(label=label):
                self.assertGreater(est["total"] / est["coverage"]["available_usd"] * 88, 100)
                self.assertEqual(self.height(jar), 100.0)
                self.assertIn("over", jar.classes())

    def test_no_room_at_all_with_a_total_is_a_full_jar(self):
        """available_usd == 0 with a total above zero: the rule's third branch, run through the template."""
        with recording_worker() as (url, store, queue, spawned):
            CREDIT.update({KEY_ZERO: 0.01})
            self.addCleanup(CREDIT.pop, KEY_ZERO, None)
            app = render_app(url, read_account=account_reader(lambda t: (CREDIT[t], None)))
            client = reviewed(app, "beta_user")
            with mock.patch.object(worker_client, "plan", lambda *a, **kw: c5_pool_plan()):
                answer = client.post("/key", data={"token": KEY_ZERO})
                if answer.status_code not in (302, 303):
                    self.skipTest("a key with nothing left is refused before Configure")
                body = client.get("/configure").get_data(as_text=True)
        est = estimate_of(body)
        self.assertEqual(est["coverage"]["available_usd"], 0)
        self.assertGreater(est["total"], 0)
        self.assertEqual(self.height(main_of(body).one(cls="jar")), 100.0)

    def test_paid_unavailable_is_an_empty_jar_with_the_off_look_and_no_credit_line(self):
        body, _, jar, est = self.jar("unavail")
        self.assertIsNone(est["coverage"])
        self.assertTrue(est["paid_unavailable"])
        self.assertIn("off", jar.classes())
        self.assertNotIn("over", jar.classes())
        self.assertEqual(self.height(jar), 0.0)
        lim = jar.one(cls="jar-lim")
        self.assertEqual(lim.attrs.get("style"), "display:none")
        self.assertEqual(lim.text(), "")

    def test_no_paid_lines_is_an_empty_jar_that_is_not_off(self):
        _, _, jar, est = self.jar("nolines")
        self.assertEqual(est["lines"], [])
        self.assertIsNone(est["coverage"])
        self.assertFalse(est["paid_unavailable"])
        self.assertEqual(self.height(jar), 0.0)
        self.assertNotIn("off", jar.classes())
        self.assertNotIn("over", jar.classes())
        self.assertEqual(jar.one(cls="jar-lim").attrs.get("style"), "display:none")

    def test_the_credit_line_exists_only_with_coverage_and_says_the_credit_the_accounts_list_shows(self):
        for label in ("full", "partial9", "partial5", "none"):
            body, main, jar, est = self.jar(label)
            lim = jar.one(cls="jar-lim")
            word = "$%.2f available" % est["coverage"]["available_usd"]
            with self.subTest(label=label):
                self.assertEqual(lim.attrs.get("x-show"), "est.coverage")
                self.assertNotIn("style", lim.attrs)
                self.assertEqual(lim.text(), word)
                label_binding = lim.one("span").attrs.get("x-text")
                self.assertEqual(label_binding, "est.coverage ? '$' + est.coverage.available_usd.toFixed(2) + ' available' : ''")
                # the figure Confirm called "Available Apify credit" (CONFIRM_AT_HEAD), and the accounts list under the ticket
                at_head = re.match(r"Available Apify credit (\$[\d.]+) across 1 account", CONFIRM_AT_HEAD[label]["capacity"]).group(1)
                self.assertEqual(lim.text(), at_head + " available")
                self.assertEqual(main.one("ul", "accounts").find("li")[0].text()[:len("Apify account 1 — " + word)],
                                 "Apify account 1 — " + word)
        for label in ("unavail", "nolines"):
            _, _, jar, _ = self.jar(label)
            self.assertEqual(jar.one(cls="jar-lim").attrs.get("style"), "display:none")

    def test_it_sits_before_the_figure_in_the_cost_section(self):
        _, main = self.configure("full")
        cost = main.one("section", "pt-cost")
        names = [(n.tag, " ".join(n.classes())) for n in cost.kids if not isinstance(n, str)]
        self.assertEqual(names, [("div", "jar"), ("div", "pt-figure")])                 # beside the price: the price is what the jar is filled to
        # ...and the section sits between what is searched and the stub that starts it
        ticket = main.one(cls="pticket")
        self.assertEqual([k.classes()[0] for k in ticket.kids if not isinstance(k, str)], ["pt-main", "pt-cost", "pt-stub"])


class TheOverSentence(Sessions):
    """Every over-credit sentence is price.js's, byte for byte, on the server too (the page is right before Alpine boots)."""

    def server_sentence(self, label):
        _, main = self.configure(label)
        return main.one("p", **{"x-show": "overWhy"}).text()

    def test_the_server_twin_equals_overWhy_for_each_cause(self):
        for label in ("full", "partial9", "partial5", "none", "unavail", "nolines"):
            body, _ = self.configure(label)
            est = estimate_of(body)
            want = {"full": "", "nolines": "", "unavail": "Paid searches are temporarily unavailable, so none will start. Nothing is charged.",
                    "partial9": "Your connected accounts can run %d of %d of these paid searches." % (
                        est["coverage"]["placeable_units"], est["coverage"]["total_units"]) if est.get("coverage") else "",
                    "partial5": "Your connected accounts can run %d of %d of these paid searches." % (
                        est["coverage"]["placeable_units"], est["coverage"]["total_units"]) if est.get("coverage") else "",
                    "none": "None of these paid searches fit within the credit on your connected accounts."}[label]
            with self.subTest(label=label):
                self.assertEqual(self.server_sentence(label), want)
                if HAS_NODE:
                    self.assertEqual(self.server_sentence(label), over_why(est))      # the real price.js, run

    def test_the_sentences_are_in_both_sources_verbatim(self):
        for literal in ("Paid searches are temporarily unavailable, so none will start. Nothing is charged.",
                        "None of these paid searches fit within the credit on your connected accounts.",
                        "Your connected accounts can run ",
                        " of these paid searches.",
                        " more than your key has.",
                        "This costs more than your key's credit covers."):
            with self.subTest(literal=literal):
                self.assertIn(literal, PRICE_JS)
                self.assertIn(literal, CONFIGURE)

    def test_price_js_is_byte_for_byte_what_it_was(self):
        self.assertEqual(hashlib.sha256(PRICE_JS.encode()).hexdigest(), PRICE_JS_SHA256)


class ThePhoneStrip(Sessions):
    def test_deep_has_a_link_to_the_cost_never_a_button(self):
        for label in ("full", "partial9", "unavail", "nolines"):
            body, main = self.configure(label)
            strip = main.one("a", "cf-strip")
            est = estimate_of(body)
            with self.subTest(label=label):
                self.assertEqual(strip.attrs.get("href"), "#cost-h")
                self.assertEqual(strip.one(cls="cf-strip-t").text(), "Estimated cost")
                figure = strip.one(cls="cf-strip-v")
                self.assertEqual(figure.attrs.get("x-text"), "'$' + est.total.toFixed(2)")
                self.assertEqual(figure.attrs.get(":class"), "{ updating: stale, over: est.over_cap }")
                self.assertEqual(figure.text(), "$%.2f" % est["total"])           # right without a script
                self.assertEqual(strip.one(cls="cf-strip-go").attrs.get("aria-hidden"), "true")
                self.assertEqual(strip.find("button"), [])
                self.assertEqual(len(main.find(cls="cf-strip")), 1)
                # in the form, immediately before the aside
                form = main.one("form", "split")
                kids = [n for n in form.kids if not isinstance(n, str)]
                self.assertEqual(kids[kids.index(strip) + 1].tag, "aside")
                self.assertIs(strip.parent, form)
        _, main = self.configure("free")
        self.assertEqual(main.find(cls="cf-strip"), [])

    def test_it_shows_only_on_phones_and_sticks_to_the_bottom(self):
        base = re.search(r"\.skin-a \.cf-strip \{([^}]*)\}", A7_CSS).group(1)
        for want in ("position: sticky", "bottom: 0", "env(safe-area-inset-bottom)", "background: var(--ground)"):
            self.assertIn(want, base)
        hide = re.search(r"@media \(min-width: 40\.01rem\) \{\s*([^{}]*)\{\s*display: none;\s*\}", A7_CSS)
        self.assertIsNotNone(hide)
        self.assertEqual(sorted(p.strip() for p in hide.group(1).split(",")), [".skin-a.js .cf-strip", ".skin-a:not(.js) .cf-strip"])


class TheTemplatesStayHonest(unittest.TestCase):
    def test_nothing_new_is_hidden_with_x_cloak(self):
        """x-cloak hides without a script too. Configure had five (the busy note, the error line, the picker's count and menu, the
        sending note) and Confirm one (the sending note) at HEAD; A7's parts are shown or hidden by `style` set from the estimate.
        T2 repeats two of the five in the plan ticket (its busy note and its error line, the ones the summary panel has), so the
        template has seven and the ticket's two are exactly those; every other part of the ticket is `style`-hidden."""
        ticket = CONFIGURE[CONFIGURE.index("{%- if public_mode and not free_only %}"):CONFIGURE.index("{%- else %}\n    <aside class=\"aside{% if public_mode %} cf-quick")]
        self.assertEqual(re.findall(r'<(\w+) class="([^"]*)"[^>]*x-cloak', ticket), [("span", "meta sending"), ("p", "error")])
        self.assertEqual(CONFIGURE.count("x-cloak"), 7)
        self.assertEqual(CONFIRM.count("x-cloak"), 1)

    def test_the_jar_is_not_given_a_second_opinion(self):
        # one place computes the fill (the :style binding) and one the server rule; neither reads over_cap
        jar = CONFIGURE[CONFIGURE.index('<div class="jar'):CONFIGURE.index('<div class="pt-figure">')]
        self.assertNotIn("over_cap ?", jar)
        self.assertEqual(jar.count("est.over_cap"), 2)       # the :class binding and the x-init watch: nothing else


class TheConsolesConfirmKeepsTheLogicThatDecidesItsButtons(unittest.TestCase):
    """confirm.html is the console's screen alone since T2 (publicly /confirm only redirects to the plan screen), and its bytes are
    pinned in TheConsoleIsUntouched. These are the literals of the logic that decides its Start / Run label, its disabled states and
    its over-cap box, kept because that logic is still what the console runs."""

    def test_the_template_keeps_the_logic_that_decides_them(self):
        for literal in (':disabled="sent{% if plan.paid_unavailable %} || true{% elif plan.over_cap %} || !ack{% endif %}"',
                        "{% if plan.paid_unavailable or (plan.coverage and plan.over_cap\n                      and not plan.coverage.placeable_units) %}disabled{% endif %}",
                        '<input type="checkbox" name="over_cap_ack" value="yes"',
                        "{% if plan.coverage and plan.over_cap %}", "{% if plan.coverage.placeable_units %}",
                        '{%- elif public_mode and not plan.over_cap %}Start Deep Sweep ·',
                        "{%- elif plan.coverage and plan.over_cap %}Run what my credit covers",
                        # pre-merge polish: a public BUTTON label has no em-dash (a middle dot before the figure); the console keeps its dash
                        "{%- if plan.coverage.placeable_units %} {{ '·' if public_mode else '—' }} ${{ '%.2f'|format(plan.coverage.partial_estimate) }}{% endif %}",
                        "{%- else %}Run the sweep — ${{ '%.2f'|format(plan.total) }}{% endif %}</button>",
                        "{%- elif plan.paid_unavailable %}Paid searches unavailable",
                        "{% if public_mode and sweep_running %}", "{% if spans_midnight and not zero %}",
                        '<details class="add-key"{% if not cov.full %} open{% endif %}>'):
            with self.subTest(literal=literal[:50]):
                self.assertIn(literal, CONFIRM)


# =====================================================================================================================
class ThePlanTicket(Sessions):
    """T2: the public Deep Sweep's aside is a plan ticket (Configure and Confirm are one screen). It says what Confirm said, in the
    ticket's parts: the figure, the credit on the jar, how many searches the accounts can run, then Start or, over the credit, two
    coupons. CONFIRM_AT_HEAD (what HEAD's Confirm said, state by state) is the record its figures are held to."""

    def test_the_old_address_leads_to_the_one_screen_and_plans_nothing_itself(self):
        planned = []
        with recording_worker() as (url, store, queue, spawned):
            client = self.visit(url, credit=KEY_11)
            client.get("/configure")
            with mock.patch.object(worker_client, "plan", lambda *a, **kw: planned.append(1) or c5_pool_plan()):
                answer = client.get("/confirm")
        self.assertEqual((answer.status_code, answer.headers["Location"]), (302, "/configure"))
        self.assertEqual(planned, [])                                   # it is an address, not a screen: nothing is priced for it
        with recording_worker() as (url, store, queue, spawned):
            free = self.visit(url, free=True).get("/confirm")
        self.assertEqual((free.status_code, free.headers["Location"]), (302, "/configure"))

    def parts(self, label):
        body, main = self.configure(label)
        ticket = main.one("aside", "cf-ticket")
        stub = ticket.one("section", "pt-stub")
        return body, main, ticket, stub

    def test_when_the_plan_is_covered_the_stub_offers_start_at_the_price_on_the_ticket(self):
        body, main, ticket, stub = self.parts("full")
        est = estimate_of(body)
        self.assertEqual(ticket.classes(), ["aside", "cf-deep", "cf-ticket"])
        self.assertEqual(ticket.attrs.get("aria-labelledby"), "ticket-h")
        self.assertEqual([k.classes()[0] for k in ticket.one(cls="pticket").kids if not isinstance(k, str)], ["pt-main", "pt-cost", "pt-stub"])
        self.assertEqual(stub.attrs.get("aria-label"), "Start")
        # the price the ticket shows is posted with the Start, for /run to hold the Sweep to
        quoted = stub.one("input", name="quoted_total")
        self.assertEqual((quoted.attrs.get("type"), quoted.attrs.get("value"), quoted.attrs.get(":value")),
                         ("hidden", "%.2f" % est["total"], "est.total.toFixed(2)"))
        self.assertEqual(quoted.attrs["value"], CONFIRM_AT_HEAD["full"]["label"].split("$")[1].split(" ")[0])      # the $6.97 Confirm's button said
        # Start, shown; the coupons, there but hidden by the server
        go = stub.one("div", "pt-go")
        self.assertEqual((go.attrs.get("x-show"), "style" in go.attrs), ("!est.over_cap", False))
        start = go.one("button")
        self.assertEqual((start.text(), start.attrs.get("type"), start.attrs.get(":disabled"), "disabled" in start.attrs),
                         ("Start the sweep · $6.97→", "submit", "sent || busy || est.paid_unavailable", False))
        self.assertEqual(start.one("span", **{"x-text": "est.paid_unavailable ? 'Paid searches unavailable' : 'Start the sweep · $' + est.total.toFixed(2)"}).text(),
                         "Start the sweep · $%.2f" % est["total"])
        coupons = stub.one("div", "pt-coupons")
        self.assertEqual((coupons.attrs.get("x-show"), coupons.attrs.get("style")), ("est.over_cap && est.coverage", "display:none"))
        self.assertTrue(shown(body, "p", "fits"))
        self.assertEqual(over_sentence(body), "")
        # the notes shown (the unavailable state's way to a Quick Sweep is there, hidden by the server)
        self.assertEqual([p.text() for p in stub.find("p", "meta") if "style" not in p.attrs],
                         ["Nothing is charged until you start.", DURATION])
        self.assertEqual(plain(body).count(DURATION), 1)
        self.assertEqual(stub.find("p", "error"), [])                                   # noon: no late-night warning
        # the stamp is the ticket's own: "Not started" until the form it is part of is sent (it reads that form's `sent`, and only reads it)
        stamp = ticket.one(cls="stamp")
        self.assertEqual((stamp.text(), stamp.attrs.get(":class"), stamp.attrs.get("x-text")),
                         ("Not started", "{ sent: sent }", "sent ? 'Sweeping…' : 'Not started'"))
        self.assertEqual({k for k in stamp.attrs if k.startswith("@") or k.startswith("x-on")}, set())   # it listens to nothing: it cannot hold a submit back

    def test_over_the_credit_the_stub_hides_start_and_offers_two_coupons(self):
        for label in ("partial5", "partial9"):
            body, main, ticket, stub = self.parts(label)
            est = estimate_of(body)
            at_head = CONFIRM_AT_HEAD[label]
            placeable, total = re.search(r"covered (\d+) of (\d+) paid searches", at_head["capacity"]).groups()
            fit_price = re.search(r"· (\$[\d.]+) →", at_head["label"]).group(1)
            with self.subTest(label=label):
                go, coupons = stub.one("div", "pt-go"), stub.one("div", "pt-coupons")
                self.assertEqual(go.attrs.get("style"), "display:none")                   # no Start while the plan is over
                self.assertNotIn("style", coupons.attrs)                                  # the coupons are shown
                # the quote is the whole plan's price (what Start would have said), never the part's
                self.assertEqual(stub.one("input", name="quoted_total").attrs["value"], "%.2f" % est["total"])
                self.assertNotEqual(fit_price, "$%.2f" % est["total"])
                picks = coupons.find("button", "coupon")
                self.assertEqual([c.attrs.get("type") for c in picks], ["button", "button"])         # picking submits nothing
                self.assertEqual([(c.one("b").text(), c.one("span").text()) for c in picks], [
                    ("Add another Apify key", "Run all %s paid searches" % total),
                    ("Run what fits, " + fit_price, "The first %s searches; the rest are left out, never charged" % placeable)])
                self.assertEqual([c.attrs.get("aria-pressed") for c in picks], ["false", "false"])
                self.assertEqual([c.attrs.get(":aria-pressed") for c in picks], ["pick === 'key' ? 'true' : 'false'", "pick === 'fit' ? 'true' : 'false'"])
                self.assertEqual(over_sentence(body), "Your connected accounts can run %s of %s of these paid searches." % (placeable, total))
                self.assertFalse(shown(body, "p", "fits"))
                self.assertIn("over", main.one(cls="jar").classes())
                # what a coupon reveals: its own button, hidden until it is the one picked
                key, fit = [n for n in coupons.find("button") if n.attrs.get("type") != "button"]
                self.assertEqual((key.attrs.get("name"), key.attrs.get("value"), key.attrs.get("formaction"), key.attrs.get("x-show"), key.text()),
                                 ("then", "key", "/configure", "pick === 'key'", "Save and add a key→"))
                self.assertEqual((fit.attrs.get("name"), fit.attrs.get("value"), fit.attrs.get("formaction"), fit.attrs.get("x-show"), fit.text()),
                                 ("over_cap_ack", "yes", None, "pick === 'fit' && est.coverage && est.coverage.placeable_units", "Start what fits→"))
                self.assertEqual(coupons.attrs.get("x-data"), "{ pick: '' }")                      # nothing is picked when the page opens
                self.assertEqual(main.find("input", name="over_cap_ack"), [])                      # there is no box to tick or to pre-tick

    def test_with_nothing_that_fits_only_the_key_coupon_is_offered(self):
        body, main, ticket, stub = self.parts("none")
        coupons = stub.one("div", "pt-coupons")
        self.assertNotIn("style", coupons.attrs)
        fit_coupon = coupons.find("button", "coupon")[1]
        self.assertEqual((fit_coupon.attrs.get("x-show"), fit_coupon.attrs.get("style")), ("est.coverage && est.coverage.placeable_units", "display:none"))
        self.assertEqual(stub.one("div", "pt-go").attrs.get("style"), "display:none")
        self.assertEqual(over_sentence(body), "None of these paid searches fit within the credit on your connected accounts.")

    def test_when_paid_searches_are_unavailable_start_is_there_and_cannot_be_pressed(self):
        body, main, ticket, stub = self.parts("unavail")
        start = stub.one("div", "pt-go").one("button")
        self.assertIn("disabled", start.attrs)
        self.assertEqual(start.attrs.get(":disabled"), "sent || busy || est.paid_unavailable")
        self.assertEqual(stub.one("div", "pt-coupons").attrs.get("style"), "display:none")
        self.assertEqual(over_sentence(body), "Paid searches are temporarily unavailable, so none will start. Nothing is charged.")
        self.assertIn("off", main.one(cls="jar").classes())
        self.assertEqual(main.find(cls="pt-accounts"), [])                             # nothing to pay with, nothing to remove
        self.assertEqual([b for b in main.find("button") if b.text() == "Remove"], [])

    def test_with_no_paid_board_on_the_ticket_prices_nothing_and_still_starts(self):
        body, main, ticket, stub = self.parts("nolines")
        start = stub.one("div", "pt-go").one("button")
        self.assertEqual((start.text(), "disabled" in start.attrs), ("Start the sweep · $0.00→", False))
        self.assertEqual(stub.one("input", name="quoted_total").attrs["value"], "0.00")

    def test_the_late_night_warning_is_in_the_stub_from_ten_at_night(self):
        warning = ("It is late in the day. A sweep that runs past midnight starts its ledger over and re-bills searches it already paid "
                   "for. Consider starting tomorrow.")
        _, _, _, late = self.parts("late")
        self.assertEqual([p.text() for p in late.find("p", "error")], [warning])
        for label in ("full", "partial5", "free"):
            self.assertNotIn(warning, plain(self.state(label)["configure"]), label)
        self.assertIn("{%- if spans_midnight and estimate.lines %}", CONFIGURE)

    def test_what_pays_for_it_is_an_accounts_peek_whose_removes_are_forms_of_their_own(self):
        for label, n in (("full", 1), ("two", 2)):
            body, main, ticket, stub = self.parts(label)
            with self.subTest(label=label):
                peek = main.one("div", "pt-accounts").one("details", "peek")
                self.assertEqual(peek.one(cls="peek-label").text(), "Your Apify accounts (%d)" % n)
                self.assertIs(main.one("div", "pt-accounts").parent, ticket)
                rows = peek.one("ul", "accounts").find("li")
                self.assertEqual(len(rows), n)
                for i, row in enumerate(rows, 1):
                    btn = row.one("button")
                    self.assertEqual((btn.text(), btn.attrs.get("form"), btn.attrs.get("aria-label"), btn.attrs.get("type")),
                                     ("Remove", "forget-%d" % i, "Stop using Apify account %d" % i, "submit"))
                    self.assertIn("danger", btn.classes())
                    # its form is written after the plan's own, never inside it (a form cannot nest), posting to the same route as before
                    forget = main.one("form", id="forget-%d" % i)
                    self.assertIsNone(forget.within("form"))
                    self.assertEqual((forget.attrs.get("action"), forget.attrs.get("method"), "hidden" in forget.attrs),
                                     ("/key/forget", "post", True))
                    self.assertEqual([(x.attrs["name"], x.attrs.get("type")) for x in forget.find("input")], [("key", "hidden"), ("back", "hidden")])
                    self.assertEqual(forget.find("input")[1].attrs["value"], "confirm")
                    self.assertTrue(forget.find("input")[0].attrs["value"])
                # no key, no part of one, anywhere on the page
                for token in (KEY_5, KEY_9, KEY_11):
                    self.assertNotIn(token, body)
                    self.assertNotIn(token[10:], body)
        _, main = self.configure("free")
        self.assertEqual(main.find(cls="pt-accounts") + main.find("form", id="forget-1"), [])

    def test_a_search_finished_today_is_said_above_the_form_because_the_ticket_prices_what_is_left(self):
        body, main = self.configure("done")
        callout = main.one(cls="callout")
        self.assertEqual(callout.text(), "5 searches from today's run are already done They are recorded, so they will not run again and "
                                         "will not be billed again. The ticket is the cost of finishing the rest.")
        self.assertLess(body.index('class="callout"'), body.index('<form class="split"'))
        self.assertLess(estimate_of(body)["total"], estimate_of(self.state("full")["configure"])["total"])
        self.assertEqual(main.one(cls="pt-stub").one("input", name="quoted_total").attrs["value"], "%.2f" % estimate_of(body)["total"])
        for label in ("full", "free", "partial5"):
            self.assertEqual(main_of(self.state(label)["configure"]).find(cls="callout"), [], label)


class TheStartHoldsTheSweepToTheTicket(Sessions):
    """POST /run, public and paid: the Start carries the price its ticket showed (`quoted_total`), the Sweep is priced again from the
    same settings, and one that now costs MORE than the ticket said starts nothing. Less is fine. A form with no quote is not from
    the ticket (a page from before it) and is let through to the guards it always met."""

    def started(self, *, form, plan=c5_pool_plan, credit=KEY_11):
        """(response, the quote on the page the visitor saw, the worker's store, the keys it spawned) for one press."""
        with recording_worker() as (url, store, queue, spawned):
            client = self.visit(url, credit=credit)
            page = client.get("/configure").get_data(as_text=True)
            data = {k: (quote(page) if v is None else v) for k, v in form.items()}
            answer = client.post("/run", data=data)
            return answer, quote(page), list(store.all()), list(spawned)

    def test_a_ticket_whose_price_still_holds_starts_the_sweep(self):
        answer, shown_quote, runs, spawned = self.started(form={"quoted_total": None})
        self.assertEqual(shown_quote, "6.97")
        self.assertEqual((answer.status_code, answer.headers["Location"]), (302, "/running"))
        self.assertEqual((len(runs), spawned), (1, [[KEY_11]]))

    def test_a_ticket_that_said_more_than_it_costs_now_starts_too(self):
        for quoted in ("7.50", "6.97", "6.9660"):
            with self.subTest(quoted=quoted):
                answer, _, runs, _ = self.started(form={"quoted_total": quoted})
                self.assertEqual((answer.status_code, len(runs)), (302, 1))

    def test_a_ticket_that_said_less_than_it_costs_now_starts_nothing(self):
        answer, shown_quote, runs, spawned = self.started(form={"quoted_total": "6.00"})
        self.assertEqual(answer.status_code, 409)
        body = answer.get_data(as_text=True)
        self.assertEqual(plan_error(body), "The price is now $6.97, not the $6.00 this page showed. Nothing has started. "
                                           "Check the ticket and start again.")
        self.assertIn('<h1>Plan your <span class="scrib">sweep</span>.</h1>', body)       # the refusal is on the plan screen, above the settings
        self.assertEqual(quote(body), "6.97")                                              # the ticket it comes back with says the new price
        self.assertEqual((runs, spawned), ([], []))

    def test_a_price_that_rose_after_the_page_was_drawn_is_caught(self):
        """The ticket said $6.97; the plan the worker now gives is longer. /run prices it again from the same settings, so the
        higher price is what it checks, whatever the page said."""
        pricier = c5_pool_plan()
        pricier["sites"]["linkedin"] += [dict(SEARCH, location=f"X{i}") for i in range(6)]
        with recording_worker() as (url, store, queue, spawned):
            client = self.visit(url, credit=KEY_11)
            page = client.get("/configure").get_data(as_text=True)
            with mock.patch.object(worker_client, "plan", lambda *a, **kw: pricier):
                answer = client.post("/run", data={"quoted_total": quote(page)})
                body = answer.get_data(as_text=True)
                self.assertEqual(answer.status_code, 409)
                now = re.fullmatch(r"The price is now \$(\d+\.\d\d), not the \$6\.97 this page showed\. Nothing has started\. "
                                   r"Check the ticket and start again\.", plan_error(body)).group(1)
                self.assertGreater(float(now), 6.97)
                self.assertEqual((store.all(), spawned), ([], []))
                # the page it comes back with quotes the new price, and pressing that starts it
                self.assertEqual(quote(body), now)
                self.assertEqual(client.post("/run", data={"quoted_total": quote(body)}).status_code, 302)
            self.assertEqual(len(store.all()), 1)

    def test_a_quote_that_is_not_a_number_starts_nothing(self):
        for quoted in ("nan", "inf", "-inf", "abc", "", "6,97"):
            with self.subTest(quoted=quoted):
                answer, _, runs, spawned = self.started(form={"quoted_total": quoted})
                self.assertEqual(answer.status_code, 409)
                self.assertEqual(plan_error(answer.get_data(as_text=True)),
                                 "The price is now $6.97. Nothing has started. Check the ticket and start again.")
                self.assertEqual((runs, spawned), ([], []))

    def test_a_form_with_no_quote_is_let_through_as_before(self):
        answer, _, runs, _ = self.started(form={})
        self.assertEqual((answer.status_code, len(runs)), (302, 1))

    def test_a_good_quote_is_not_consent_to_a_part_of_the_plan(self):
        """Over the credit the quote alone starts nothing: the consent is over_cap_ack=yes, which only the ticket's "Start what fits"
        button sends. With it, the Sweep runs the part that fits and the profile says so."""
        for form in ({"quoted_total": None}, {"quoted_total": None, "over_cap_ack": ""}):
            answer, _, runs, spawned = self.started(form=form, credit=KEY_5)
            with self.subTest(form=form):
                self.assertEqual(answer.status_code, 400)
                self.assertIn("can't safely cover the full Sweep", plan_error(answer.get_data(as_text=True)))
                self.assertEqual((runs, spawned), ([], []))
        with recording_worker() as (url, store, queue, spawned):
            client = self.visit(url, credit=KEY_5)
            page = client.get("/configure").get_data(as_text=True)
            got = client.post("/run", data={"quoted_total": quote(page), "over_cap_ack": "yes"})
            self.assertEqual((got.status_code, got.headers["Location"]), (302, "/running"))
            with open(os.path.join(store.dir(store.all()[-1]["run_id"]), "profile.py"), encoding="utf-8") as fh:
                self.assertIn('"allow_partial_paid_sweep": True', fh.read())
            self.assertEqual(spawned, [[KEY_5]])

    def test_a_sweep_already_going_is_viewed_not_started_again(self):
        with recording_worker() as (url, store, queue, spawned):
            client = self.visit(url, credit=KEY_11)
            page = client.get("/configure").get_data(as_text=True)
            self.assertEqual(client.post("/run", data={"quoted_total": quote(page)}).headers["Location"], "/running")
            stub = main_of(client.get("/configure").get_data(as_text=True)).one("section", "pt-stub")
            link = stub.one("a", "primary")
            self.assertEqual((link.text(), link.attrs.get("href")), ("View my Sweep→", "/running"))
            self.assertEqual(stub.find("input") + stub.find("button"), [])                  # no price to quote, nothing to press
            again = client.post("/run", data={"quoted_total": quote(page)})
            self.assertEqual((again.status_code, again.headers["Location"], len(store.all())), (302, "/running", 1))

    def test_a_free_sweep_has_no_price_to_hold_it_to(self):
        with recording_worker() as (url, store, queue, spawned):
            client = self.visit(url, free=True, plan=NO_PAID_LINES)
            page = client.get("/configure").get_data(as_text=True)
            self.assertNotIn("quoted_total", page)
            self.assertEqual(client.post("/run").status_code, 302)
            self.assertEqual(len(store.all()), 1)


class ThePlanScreenSavesOnTheWayToAKey(Sessions):
    """The ticket's "Save and add a key" is the one public submit that is not a Start: it posts to /configure (formaction) with
    then=key, which saves the settings and goes to the key step opened on its paste step; the key step's way back is the plan."""

    def test_saving_with_then_key_goes_to_the_key_step_and_keeps_the_settings(self):
        with recording_worker() as (url, store, queue, spawned):
            client = self.visit(url, credit=KEY_5)
            app = client.application
            client.get("/configure")
            answer = client.post("/configure", data={"scope": "india", "max_age_days": "7", "then": "key"})
            self.assertEqual((answer.status_code, answer.headers["Location"]), (303, "/key?add=1"))
            self.assertEqual(next(iter(app.session_store._rooms.values()))["data"]["max_age_days"], 7)     # saved on the way
            self.assertEqual(store.all(), [])                                                              # and nothing started
            opened = client.get("/key?add=1").get_data(as_text=True)
            self.assertRegex(opened, r"x-data=\"\{ mode: 'deep', setup: true, step: 3 \}\"")            # the Deep setup, on its paste step
            plain_key = client.get("/key").get_data(as_text=True)
            self.assertNotRegex(plain_key, r"mode: 'deep', setup: true")

    def test_saving_without_it_comes_back_to_the_plan_and_a_bad_field_comes_back_refused(self):
        with recording_worker() as (url, store, queue, spawned):
            client = self.visit(url, credit=KEY_5)
            answer = client.post("/configure", data={"scope": "india", "max_age_days": "7"})
            self.assertEqual((answer.status_code, answer.headers["Location"]), (303, "/configure"))
            for extra in ({}, {"then": "key"}):          # a refused save is the screen it was typed on, with nothing kept, key step or not
                bad = client.post("/configure", data={"scope": "india", "max_age_days": "0", **extra})
                self.assertEqual(bad.status_code, 400)
                self.assertIn('<h1>Plan your <span class="scrib">sweep</span>.</h1>', bad.get_data(as_text=True))
            self.assertEqual(client.post("/configure", data={"scope": "india", "then": "elsewhere"}).headers["Location"], "/configure")

    def test_the_old_addresses_a_key_came_back_to_lead_to_the_plan(self):
        """A key added from the plan comes back through the key step's own "checked" page; one pasted with back=confirm (an old form)
        and a removal both end at /confirm, which is the plan screen."""
        with recording_worker() as (url, store, queue, spawned):
            client = self.visit(url, credit=KEY_5)
            client.get("/configure")
            added = client.post("/key", data={"token": KEY_9, "back": "confirm"}, follow_redirects=True)
            self.assertEqual((added.status_code, added.request.path), (200, "/configure"))
            self.assertIn("Apify accounts (2)", plain(added.get_data(as_text=True)))
            ids = [k["id"] for k in next(iter(client.application.session_store._rooms.values()))["data"]["byok_keys"]]
            gone = client.post("/key/forget", data={"key": ids[1], "back": "confirm"}, follow_redirects=True)
            self.assertEqual((gone.status_code, gone.request.path), (200, "/configure"))
            self.assertIn("Apify account 1", plain(gone.get_data(as_text=True)))


class TheFreeMultiTrackConfigure(multi.Setup):
    """A free Multi-Track (2-3 résumé) Sweep's Configure is the one form too (it used to say "Save and review" and go on to
    Confirm): it posts to /run, and its button starts it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        multi.r1.setUpModule()                               # the committed market corpus and loopback-only sockets, as test_multi_setup's
        cls.addClassCleanup(multi.r1.tearDownModule)

    def test_it_posts_to_run_and_the_button_says_start_quick_sweep(self):
        self.free("ada", "bhaskar")
        body = self.client.get("/configure").get_data(as_text=True)
        self.assertRegex(body, r'<form class="split" method="post"\s+action="/run"')
        main = main_of(body)
        buttons = [n for n in main.one("form", "split").walk() if n.tag == "button" and n.attrs.get("type", "submit") == "submit"]
        self.assertEqual([b.text() for b in buttons], ["Start Quick Sweep→"])
        self.assertNotIn("Save and review", body)
        self.assertIn("Already set from your résumés.", plain(body))                # several résumés: the lede says so
        self.assertEqual(self.client.get("/confirm").headers["Location"], "/configure")
        run = self.client.post("/run", data=multi.r1.FORMS["india"])
        self.assertEqual((run.status_code, run.headers["Location"]), (302, "/running"))      # the one press plans and starts it
        self.assertEqual(len(self.worker.bodies("/v1/runs")), 1)


# =====================================================================================================================
class TheConsoleIsUntouched(Sessions):
    NEW = ('class="jar', "cf-strip", 'class="free-chip"', "cost-h", 'class="peek"', "confirm ticket", 'class="stamp"', 'class="tlink"',
           'class="eyebrow"', 'class="fits"', "stack-tight boards", "cf-deep", "cf-quick", "accts-h", "Ready when", "Where should we",
           "How is this worked out", "Change something", 'class="scrib"', "skin-a", "jar-fill", "ticket-free", "cf-row", "cf-next", "What happens next", "Sweeping…",
           # T2: the plan ticket
           "pticket", "pt-lines", "pt-stub", "pt-coupons", "quoted_total", "ticket-h", "Plan your", 'class="coupon"', "Start the sweep")

    @classmethod
    def console(cls, path):
        sys.path.insert(0, str(REPO))
        out = subprocess.run([sys.executable, str(REPO / "docs/design/sweep-a/harness/configure-hash.py"), str(REPO)],
                             capture_output=True, text=True, timeout=120, env={**os.environ, "SWEEP_PUBLIC_MODE": ""}, cwd=str(REPO))
        assert out.returncode == 0, out.stderr[-600:]
        return {re.sub(r"\s+", " ", line[len("console "):-17]).strip(): line.split()[-1] for line in out.stdout.splitlines() if line.startswith("console ")}

    def test_every_console_state_renders_the_bytes_it_rendered_at_head(self):
        """sha256 (first 16 hex) of the console's /configure and /confirm, GET only, in local mode over a temporary tree, with the
        suite's own fakes (docs/design/sweep-a/harness/configure-hash.py). Taken from 6e6719d before A7 edited a template.
        The two Configure states with the depth stepper moved once since, on purpose: 0feccd7 made the stepper ask for
        the price through price.js soon() (one dry run per burst of clicks), in the console as on public pages. All three
        Configure states moved again on 2026-11-20: the India radio's label became "In India, or remote open to India"."""
        got = self.console(None)
        self.assertEqual(got, {
            "configure cap $8.41": "302383d26077a750",
            "configure over the cap": "1dc9e5c001136f35",
            "configure free-only": "bd2eb8cceb0233b0",
            "confirm cap $8.41": "53fde9f310198a04",
            "confirm over the cap": "8786d80fe5620ec6",
            "confirm free-only": "f92a1befa6d85d18",
            "confirm late (23:00)": "8329ca7f8ddd86c8",
            "confirm over, late": "11201e7bead5a285",
            "confirm over, 2 keys": "a92a0a98f02b1367",
            "confirm already done": "0db32a8ffaad81f1",
        })

    def test_none_of_the_new_markup_is_in_a_console_page(self):
        tmp_pages = {}
        import tempfile
        tmp = tempfile.mkdtemp(prefix="a7-console-")
        os.mkdir(os.path.join(tmp, "profiles"))
        try:
            from sweep.tests import test_app as T
            import copy
            with mock.patch.object(app_module, "REPO_ROOT", tmp):
                app = app_module.create_app(
                    state={"profile": "kabir", "derived": copy.deepcopy(T.DERIVED), "cap_usd": 8.41, "credit_total_usd": 8.41},
                    extract=lambda p: "x", derive=lambda t, p: copy.deepcopy(T.DERIVED), check_token=lambda t: (8.41, None),
                    fetch_plan=lambda name: dict(copy.deepcopy(T.RAW_PLAN), profile=name), read_rows=lambda profile: [],
                    list_sweeps=lambda profile: [], hour_now=lambda: 12, resume_dir=os.path.join(tmp, "resume"),
                    env_path=os.path.join(tmp, "stub.env"), output_dir=os.path.join(tmp, "out"))
                app.config["TESTING"] = True
                app.write_profile = lambda n, src: None
                app.discard_profile = lambda n: None
                client = app.test_client()
                for path in ("/configure", "/confirm"):
                    tmp_pages[path] = client.get(path).get_data(as_text=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        for path, page in tmp_pages.items():
            for needle in self.NEW:
                with self.subTest(path=path, needle=needle):
                    self.assertTrue(needle not in page, "the console's %s carries %r" % (path, needle))
        self.assertIn("<h1>Configure the sweep</h1>", tmp_pages["/configure"])
        self.assertIn("<h1>Confirm the spend</h1>", tmp_pages["/confirm"])
        self.assertIn('<div class="meter', tmp_pages["/configure"])

    def test_the_public_pages_do_wear_it(self):
        for label in ("full", "free"):
            self.assertIn("skin-a", self.state(label)["configure"])


# =====================================================================================================================
class TheStylesheet(unittest.TestCase):
    def rule(self, selector):
        for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", A7_CSS):
            if " ".join(sel.split()) == selector:
                return body
        self.fail("no rule for " + selector)

    def test_the_depth_stepper_rules_reach_only_configure(self):
        """Review's experience and weight steppers and the Results editor's are A5's: the first A7 build restyled every
        .stepper on the public pages, which moved them. Configure's is the one inside a .setting-body."""
        sels = [" ".join(sel.split()) for sel, _ in re.findall(r"([^{}]+)\{([^{}]*)\}", A7_CSS) if ".stepper" in sel]
        self.assertTrue(sels)
        for sel in sels:
            for part in sel.split(","):
                self.assertIn(".setting-body .stepper", part, part)

    def test_no_raw_colour_and_no_reduce_block(self):
        self.assertNotRegex(A7_CSS, r"#[0-9A-Fa-f]{3,8}\b")
        self.assertNotRegex(A7_CSS, r"rgba?\(")
        self.assertNotIn("@media (prefers-reduced-motion: reduce)", A7_CSS)

    def test_every_rule_that_hides_something_is_under_js_or_not_js(self):
        hiders = [" ".join(sel.split()) for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", A7_CSS) if re.search(r"display:\s*none", body)]
        self.assertGreaterEqual(len(hiders), 3)
        for sel in hiders:
            for part in (p.strip() for p in sel.split(",")):
                with self.subTest(selector=part):
                    self.assertTrue(part.startswith((".skin-a.js ", ".skin-a:not(.js) ")), part)

    def test_the_scope_reveal_is_has_checked_so_a_browser_without_has_shows_everything(self):
        self.assertIn(".skin-a.js .setting-body > [role=\"radiogroup\"] .choice:not(:has(:checked)) .why", A7_CSS)
        self.assertIn(".skin-a:not(.js) .setting-body > [role=\"radiogroup\"] .choice:not(:has(:checked)) .why", A7_CSS)

    def test_motion_is_only_in_no_preference_and_the_jar_pours_and_wobbles_once(self):
        at = A7_CSS.index("@media (prefers-reduced-motion: no-preference)")
        self.assertNotRegex(A7_CSS[:at], r"(animation|transition)\s*:")
        block = A7_CSS[at:]
        self.assertIn("transition: height .6s cubic-bezier(.3, 1.4, .5, 1);", block)
        self.assertIn(".skin-a .jar.wobble { animation: a-wobble .6s ease-in-out; }", block)
        self.assertNotIn("infinite", block)                                         # once
        self.assertEqual(sorted(re.findall(r"@keyframes\s+([\w-]+)", A7_CSS)), ["a-stamp", "a-wobble"])      # A11 polish added the stamp press
        self.assertNotRegex(A7_CSS, r"\.skin-a \.jar\.over \{[^}]*animation")        # never on first paint: `over` alone does not move it

    def test_the_rail_is_wide_screens_only_and_lights_up_only_with_motion(self):
        self.assertRegex(A7_CSS, r"@media \(min-width: 75rem\) \{\s*\.skin-a \.cf-row \{ display: grid; grid-template-columns: minmax\(0, 62rem\) minmax\(14rem, 17rem\);")
        self.assertRegex(A7_CSS, r"@media \(max-width: 74\.99rem\) \{\s*\.skin-a\.js \.cf-next, \.skin-a:not\(\.js\) \.cf-next \{ display: none; \}")
        at = A7_CSS.index("@media (prefers-reduced-motion: no-preference)")
        before, block = A7_CSS[:at], A7_CSS[at:]
        self.assertNotRegex(before, r"\.cf-next:(hover|focus-within)")                      # reduced motion: the steps are shown plainly and stay so
        self.assertIn(".skin-a .cf-next:hover li, .skin-a .cf-next:focus-within li { background: color-mix(in srgb, var(--a-cit) 28%, var(--surface)); }", block)
        self.assertIn(".skin-a .cf-next:hover li::after, .skin-a .cf-next:focus-within li::after { opacity: 1; }", block)       # the tick
        self.assertIn("transition-delay: calc(var(--n) * .45s);", block)                      # in turn, one after the other
        for k, n in ((1, 0), (2, 1), (3, 2)):
            self.assertIn(f".skin-a .cf-next li:nth-child({k}) {{ --n: {n}; }}", A7_CSS)
        self.assertNotIn("animation", self.rule(".skin-a .cf-next li"))                       # a transition, so no keyframes of its own

    def test_the_stamp_is_pressed_when_sent_in_no_preference_only(self):
        at = A7_CSS.index("@media (prefers-reduced-motion: no-preference)")
        self.assertNotIn("a-stamp", A7_CSS[:at])
        self.assertIn(".skin-a .confirm.ticket > .what > .stamp.sent { animation: a-stamp .42s cubic-bezier(.3, 1.5, .5, 1) both; }", A7_CSS[at:])
        kf = re.search(r"@keyframes a-stamp \{(.*?)\n  \}", A7_CSS, re.S).group(1)
        self.assertEqual(sorted(set(re.findall(r"([a-z-]+)\s*:", re.sub(r"[\d.%]+ \{", "{", kf)))), ["opacity", "transform"])
        self.assertEqual(kf.count("rotate(-7deg)"), 3)                                         # it keeps the stamp's own tilt all the way

    def test_the_jar_is_a_dashed_limit_a_striped_peach_fill_and_a_coral_over(self):
        self.assertIn("var(--a-pch)", self.rule(".skin-a .jar-fill"))
        inside = self.rule(".skin-a .jar-in")
        self.assertIn("overflow: hidden", inside)
        self.assertIn("border-radius: 0 0 37px 37px", inside)      # the jar's 40px corners less its 3px wall
        self.assertNotIn("border-radius", self.rule(".skin-a .jar-fill"))
        self.assertIn("repeating-linear-gradient(-45deg", self.rule(".skin-a .jar-fill"))
        self.assertIn("bottom: 88%", self.rule(".skin-a .jar-lim"))
        self.assertIn("2px dashed var(--a-line)", self.rule(".skin-a .jar-lim"))
        self.assertIn("var(--over)", self.rule(".skin-a .jar.over .jar-fill"))
        self.assertIn("dashed", self.rule(".skin-a .jar.off"))
        self.assertIn("opacity: var(--pending-dim)", self.rule(".skin-a .jar.updating"))

    def test_the_plan_ticket_is_tokens_only_and_its_one_motion_waits_for_no_preference(self):
        """T2: the ticket's section of the stylesheet. A line that changed is written in again with a citrus wash (the a-ink
        keyframe), and only where motion is welcome."""
        self.assertTrue(T2_CSS.strip())
        self.assertNotRegex(T2_CSS, r"#[0-9A-Fa-f]{3,8}\b")
        self.assertNotRegex(T2_CSS, r"rgba?\(")
        self.assertNotIn("@media (prefers-reduced-motion: reduce)", T2_CSS)
        at = T2_CSS.index("@media (prefers-reduced-motion: no-preference)")
        self.assertNotRegex(T2_CSS[:at], r"(animation|transition)\s*:")
        self.assertIn(".skin-a .pt-line.inked { animation: a-ink 1.1s ease-out; }", T2_CSS[at:])
        self.assertEqual(re.findall(r"@keyframes\s+([\w-]+)", T2_CSS), ["a-ink"])
        self.assertNotIn("infinite", T2_CSS)

    def test_the_stub_is_peach_for_money_and_citrus_when_free_in_ink(self):
        base = self.rule(".skin-a .cf-quick .summary-panel, .skin-a .confirm.ticket > .decide")
        for want in ("--fill: var(--a-pch)", "--chalk: var(--a-ink)", "--over: var(--a-ink)", "background: var(--fill)"):
            self.assertIn(want, base)
        self.assertIn("--fill: var(--a-cit)", self.rule(".skin-a .cf-quick .summary-panel, .skin-a .confirm.ticket-free > .decide"))
        self.assertIn("border-top: 3px dashed var(--a-ink)", self.rule(".skin-a .confirm.ticket > .decide"))

    def test_the_ticket_is_two_halves_wide_and_stacked_on_a_phone(self):
        wide = A7_CSS[A7_CSS.index("@media (min-width: 48rem)"):]
        wide = wide[:wide.index("\n}\n")]
        self.assertIn("grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr)", wide)
        self.assertIn("grid-column: 1 / -1", self.rule(".skin-a .confirm.ticket > .detail"))
        self.assertIn("grid-column: 2; grid-row: 1", wide)
        self.assertIn("grid-column: 1; grid-row: 1", wide)
        self.assertIn("border-left: 3px dashed var(--a-ink)", wide)
        self.assertNotIn("grid-template-columns", self.rule(".skin-a .confirm.ticket"))   # one column until 48rem: the stub follows the summary
        self.assertNotIn("position: sticky", self.rule(".skin-a .confirm.ticket > .decide"))   # the stub is not pinned

    def test_the_stub_button_passes_aa_in_both_themes(self):
        """The fill is --a-primary under --a-on-primary (A2 pins that pair); the stub only changes its edge and shadow to ink."""
        body = self.rule(".skin-a .cf-quick .summary-panel .primary, .skin-a .confirm.ticket > .decide .primary")
        self.assertIn("border-color: var(--a-ink)", body)
        self.assertIn("box-shadow: 4px 4px 0 var(--a-ink)", body)
        from sweep.tests.test_visual_rules_a import THEMES, contrast, rgb
        for theme, v in THEMES.items():
            with self.subTest(theme=theme):
                self.assertGreaterEqual(contrast(rgb(v["--a-on-primary"]), rgb(v["--a-primary"])), 4.5)
                for fill in ("--a-pch", "--a-cit"):                               # ink on the stub's fills, and the slate-ish mix on them
                    self.assertGreaterEqual(contrast(rgb(v["--a-ink"]), rgb(v[fill])), 4.5)


if __name__ == "__main__":
    unittest.main()
