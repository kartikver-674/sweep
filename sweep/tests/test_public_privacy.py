"""D7C blockers 4 and 8: raw internal résumé-reading diagnostics never reach a visitor.

The reading's `notes` are written for whoever checks the derivation (the local engine's are field names, the corrections the
router made, the terms it dropped; the model engine's are free prose) and `skill_scan.widen` appends to them. The review screen used to print them verbatim
on the public page. A visitor is told what was read (`field_summary`: the field, the years, the skills) and gets the lists to
edit; the operator's console keeps the notes.

This is a MARKER sweep: hostile strings that look like exactly what must not appear (an absolute path, a stack trace, an
environment variable, a secret, a module name) are put into every field a reading carries and into every way a read can fail, and
the public HTML of every screen a visitor can reach is searched for them. Escaping is checked the other way round: the one field
a visitor IS shown, injected with markup, comes out as text. No model, provider or network.
"""
import copy
import html
import re
import unittest

from sweep.tests import test_public
from sweep.tests.test_app import DERIVED
from sweep.tests.test_public import PDF, public_app, unlocked, upload

PATH = "/Users/operator/private/job-scraper/profiles/kartik_reachable.py"
SECRET = "apify_api_SECRETSECRET1234567890"
MARKERS = (
    PATH, "/srv/app/auto-apply/make_profile.py", "C:\\Users\\operator\\secret.txt",
    "Traceback (most recent call last)", 'File "/srv/app/sweep/app.py", line 4107, in derive',
    SECRET, "APIFY_TOKEN=", "SWEEP_WORKER_TOKEN", "skill_scan.widen", "local_profile._notes",
    "make_profile.widen_skills", "years_experience COMPUTED", "role_gate_rejected",
    "INTERNAL-DIAGNOSTIC-MARKER",
)
HOSTILE_NOTES = (
    "Generated locally — no API key, no data left this machine. Target field read as 'x'; years_experience COMPUTED from "
    f"the extracted employment dates, not asked for. Source: {PATH}. Traceback (most recent call last): File "
    '"/srv/app/sweep/app.py", line 4107, in derive. APIFY_TOKEN=' + SECRET + " SWEEP_WORKER_TOKEN skill_scan.widen "
    "local_profile._notes make_profile.widen_skills INTERNAL-DIAGNOSTIC-MARKER /srv/app/auto-apply/make_profile.py "
    "C:\\Users\\operator\\secret.txt role_gate_rejected"
)


def hostile(**over):
    """A reading whose every internal field carries a marker. field_summary is the one a visitor sees: it holds only text."""
    d = copy.deepcopy(DERIVED)
    d.update({
        "notes": HOSTILE_NOTES,
        "skills_added": {"react native": f"glued to {PATH}", "soql": "INTERNAL-DIAGNOSTIC-MARKER"},
        "role_signals": {"debug": "Traceback (most recent call last)"},
        "role_evidence": {"path": PATH, "secret": SECRET},
        "role_gate_rejected": [{"title": "INTERNAL-DIAGNOSTIC-MARKER", "why": PATH}],
        "field_summary": "React Native developer — 4 years of relevant experience, 9 skills read from the résumé.",
    })
    d.update(over)
    return d


class Quiet(unittest.TestCase):
    """A page is hundreds of kilobytes: say what was missing, never the haystack."""

    def has(self, needle, hay, msg=""):
        if needle not in hay:
            self.fail(msg or f"missing: {needle!r}")

    def lacks(self, needle, hay, msg=""):
        if needle in hay:
            self.fail(msg or f"found: {needle!r}")

    def clean(self, body, where=""):
        found = leaked(body)
        if found:
            self.fail(f"{where}: internals reached the page: {found}")


def leaked(body):
    """The markers that are in `body`, as text a person would read or a script would hold (unescaped too)."""
    flat = html.unescape(body)
    return sorted({m for m in MARKERS if m in flat or m in body})


class VisitorNeverSeesTheReadingsInternals(Quiet):

    def visitor(self, derived):
        app = public_app(derive=lambda text, prefs: copy.deepcopy(derived))
        client = unlocked(app)
        self.assertEqual(upload(client).status_code, 302)
        client.post("/derive")
        return app, client

    def saved(self, derived):
        """A visitor who has read their résumé and saved the review: /profile now has a file to show."""
        app, client = self.visitor(derived)
        self.assertEqual(client.post("/review", data={"name": "ada"}).status_code, 302)
        return app, client

    def test_the_review_screen_carries_none_of_them(self):
        _app, client = self.visitor(hostile())
        body = client.get("/review").get_data(as_text=True)
        self.has("React Native developer", body, "what the visitor IS told stands")
        self.clean(body, "/review")
        for gone in ("Technical notes on how this was read", "Worth knowing", 'class="notes"'):
            self.lacks(gone, body)

    def test_every_screen_a_visitor_can_reach_after_a_reading_is_clean(self):
        _app, client = self.saved(hostile())
        for path in ("/", "/review", "/key", "/configure", "/confirm", "/running", "/results", "/profile", "/profile.py",
                     "/feedback", "/beta"):
            with self.subTest(path):
                r = client.get(path, follow_redirects=True)
                self.clean(r.get_data(as_text=True), path)

    def test_the_file_a_visitor_is_handed_is_the_profile_without_the_diagnostics(self):
        _app, client = self.saved(hostile())
        shown = client.get("/profile").get_data(as_text=True)
        served = client.get("/profile.py").get_data(as_text=True)
        self.assertEqual(client.get("/profile.py").status_code, 200)
        for where, text in (("/profile", shown), ("/profile.py", served)):
            self.clean(text, where)
            self.has("SEARCH", text)                                   # it is still a profile
            self.has("PROFILE_SCHEMA", text)
        self.has("They are not part of the file it hands you.", served)
        self.lacks("Each line says why it counted as a claim", served)

    def test_the_internal_fields_are_not_in_the_page_as_data_either(self):
        _app, client = self.visitor(hostile())
        body = client.get("/review").get_data(as_text=True)
        for name in ("skills_added", "role_signals", "role_evidence", "role_gate_rejected", '"notes"', "glued to"):
            self.lacks(name, body, name)

    def test_the_one_field_a_visitor_is_shown_is_escaped(self):
        _app, client = self.visitor(hostile(field_summary='<script>alert("x")</script><b onmouseover=1>Dev</b>'))
        body = client.get("/review").get_data(as_text=True)
        self.lacks('<script>alert("x")</script>', body)
        self.lacks("<b onmouseover=1>", body)
        self.has("&lt;script&gt;", body)

    def test_a_reading_with_no_notes_is_the_same_page_to_a_visitor(self):
        _a, with_notes = self.visitor(hostile())
        _b, without = self.visitor(hostile(notes="", skills_added={}))
        a = with_notes.get("/review").get_data(as_text=True)
        b = without.get("/review").get_data(as_text=True)
        scrub = lambda t: re.sub(r'name="csrf[^>]*>', "", t)
        self.assertEqual(len(scrub(a)), len(scrub(b)), "the notes change nothing a visitor sees")


class ThePublicCopyOfTheProfile(Quiet):
    """make_profile.public_source: the redaction is pinned to render()'s own layout, and fails closed."""

    @staticmethod
    def source(**over):
        from sweep import app as app_module
        return app_module.make_profile.render("ada", hostile(**over), app_module._prefs({"locations": ["Remote"]}))

    def test_render_still_lays_the_file_out_the_way_the_redaction_expects(self):
        from sweep import app as app_module
        mp = app_module.make_profile
        src = self.source()
        self.has(mp.READING_HEADING, src)
        self.assertRegex(src, r"(?s)" + re.escape(mp.READING_HEADING) + r"\n.*\n\nSkill weights are by DISCRIMINATIVE POWER")
        self.has("# Found in the résumé and named by the market, added to what\n    # the model reported. Each line says why it counted as a claim.\n", src)
        # ...so the markers really are in the whole file, and the redaction really is what removes them
        self.assertTrue(leaked(src))
        self.assertEqual(leaked(mp.public_source(src)), [])

    def test_it_changes_nothing_else_in_the_file(self):
        from sweep import app as app_module
        mp = app_module.make_profile
        src = self.source()
        pub = mp.public_source(src)
        strip = lambda t: re.sub(r"(?s)HOW THE MODEL READ THIS RÉSUMÉ\n.*?\n\nSkill weights", "SW", t)
        added = re.compile(r"(?m)^    # Found in the résumé.*?\n(?:    #   .*\n)*", re.S)
        self.assertEqual(re.sub(r"(?m)^    # Found in the résumé and named by the market.*\n    # the model reported.*\n(?:    #   .*\n)*", "", strip(src)),
                         strip(pub))
        # a valid generated module: the same check the engine applies runs on it
        mp.check_module(pub)
        self.assertEqual(mp.public_source(pub), pub, "idempotent")

    def test_if_the_layout_ever_moves_the_whole_docstring_goes_rather_than_a_guess(self):
        from sweep import app as app_module
        mp = app_module.make_profile
        src = self.source().replace("HOW THE MODEL READ THIS RÉSUMÉ", "HOW IT WAS READ")
        self.assertTrue(leaked(src))
        pub = mp.public_source(src)
        self.assertEqual(leaked(pub), [])
        self.has('"""A profile generated from a résumé by Sweep."""', pub)

    def test_a_file_with_nothing_to_redact_is_unchanged(self):
        from sweep import app as app_module
        mp = app_module.make_profile
        src = self.source(notes="", skills_added={})
        self.assertEqual(leaked(mp.public_source(src)), [])


class FailuresAreCuratedNotCopied(Quiet):
    """A read or a parse that fails with an exception full of internals says one fixed sentence."""

    BOOM = (f"{PATH}: Traceback (most recent call last): File \"/srv/app/sweep/app.py\", line 4107 {SECRET} "
            "APIFY_TOKEN= SWEEP_WORKER_TOKEN INTERNAL-DIAGNOSTIC-MARKER C:\\Users\\operator\\secret.txt")

    def failing(self, derive=None, extract=None):
        kw = {}
        if derive:
            kw["derive"] = derive
        if extract:
            kw["extract"] = extract
        app = public_app(**kw)
        # as production runs it: an unexpected exception is the generic 500 page, not a re-raise into the test
        app.config.update(TESTING=False, PROPAGATE_EXCEPTIONS=False)
        client = unlocked(app)
        return client

    def raise_(self, exc):
        def boom(*_a, **_k):
            raise exc
        return boom

    def test_a_model_that_fails_with_internals_in_its_message(self):
        for exc in (RuntimeError(self.BOOM), ValueError(self.BOOM), OSError(self.BOOM), KeyError(self.BOOM),
                    Exception(self.BOOM)):
            with self.subTest(type(exc).__name__):
                client = self.failing(derive=self.raise_(exc))
                upload(client)
                r = client.post("/derive", follow_redirects=True)
                self.clean(r.get_data(as_text=True), "POST /derive")
                after = client.get("/review", follow_redirects=True).get_data(as_text=True)
                self.clean(after, "GET /review")

    def test_a_pdf_the_parser_chokes_on(self):
        for exc in (RuntimeError(self.BOOM), ValueError(self.BOOM), Exception(self.BOOM)):
            with self.subTest(type(exc).__name__):
                client = self.failing(extract=self.raise_(exc))
                r = upload(client)
                body = r.get_data(as_text=True)
                follow = client.get(r.headers.get("Location", "/"), follow_redirects=True).get_data(as_text=True)
                self.clean(body, "POST /resume")
                self.clean(follow, "after the upload")

    def test_a_filename_carrying_markup_or_a_path_is_never_trusted(self):
        client = unlocked(public_app())
        r = upload(client, name="../../etc/passwd<script>alert(1)</script>.pdf")
        body = client.get("/review", follow_redirects=True).get_data(as_text=True) + r.get_data(as_text=True)
        self.lacks("<script>alert(1)</script>", body)


class TheOperatorKeepsTheirNotes(Quiet):
    """Operator diagnostics may remain where they are appropriate: the console shows the notes, escaped."""

    def test_the_console_review_still_shows_the_notes_behind_their_door(self):
        from sweep import app as app_module
        app = app_module.create_app(state={"resume_text": "x", "derived": hostile(notes="Source: <b>p</b> read as 'x'")},
                                    derive=lambda t, p: hostile())
        app.config["TESTING"] = True
        body = app.test_client().get("/review").get_data(as_text=True)
        self.has("Worth knowing", body)
        self.has("&lt;b&gt;p&lt;/b&gt;", body)                      # escaped
        self.lacks("<b>p</b>", body)


if __name__ == "__main__":
    unittest.main()
