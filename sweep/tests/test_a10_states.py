"""A10: the states the design canvas never drew (public only).

Errors as stickers, the active-run strip, the door (beta.html), Confirm's "already done" notes, Results' notice, the feedback
dialog, the plan that could not be made, and a 404 page. The browser half is docs/design/sweep-a/harness/states-a.mjs.

Two kinds of test. Those in `Unchanged` assert what HEAD (ae2d149) answered; they were run against a `git archive` of HEAD with
this file copied in and pass there too, so "the same" is a comparison with the old tree and not with itself. The rest assert what
A10 adds.
"""
import io
import json
import pathlib
import re
import unittest
from unittest import mock

from sweep import app as app_module
from sweep import public, worker_client
from sweep.tests.test_app import DERIVED
from sweep.tests.test_motion import Quiet
from sweep.tests.test_public import CODE, public_app, unlocked

ROOT = pathlib.Path(app_module.__file__).parent
TEMPLATES = ROOT / "templates"
CSS = (ROOT / "static" / "sweep-a.css").read_text(encoding="utf-8")
A10_START = CSS.rindex("/*", 0, CSS.index("==== A10: the other states")) if "==== A10: the other states" in CSS else len(CSS)  # (absent in the HEAD tree this file is also run against)
A10 = re.sub(r"/\*.*?\*/", "", CSS[A10_START:], flags=re.S)

# What Flask answers for an address it has no route for (werkzeug 3), byte for byte.
FLASK_404 = (b"<!doctype html>\n<html lang=en>\n<title>404 Not Found</title>\n<h1>Not Found</h1>\n"
             b"<p>The requested URL was not found on the server. If you entered the URL manually please check your spelling "
             b"and try again.</p>\n")


def template(name):
    return (TEMPLATES / name).read_text(encoding="utf-8")


def with_class(token):
    """The templates that carry `token` as a class."""
    return sorted(p.name for p in TEMPLATES.glob("*.html")
                  if re.search(r'class="[^"]*(?<![\w-])' + re.escape(token) + r'(?![\w-])', p.read_text(encoding="utf-8")))


class Unchanged(unittest.TestCase):
    """What HEAD answered, and A10 must still."""

    def test_the_console_keeps_flasks_own_404(self):
        app = app_module.create_app(state={"resume_text": "x"}, derive=lambda t, p: dict(DERIVED))
        app.config["TESTING"] = True
        r = app.test_client().get("/this-page-does-not-exist")
        self.assertEqual((r.status_code, r.get_data()), (404, FLASK_404))

    def test_an_operator_only_route_still_answers_publicly_with_a_plain_text_404(self):
        client = unlocked(public_app())
        for path, method in (("/events", "get"), ("/rescore", "post"), ("/merge", "post"), ("/applied", "post"),
                             ("/second-key", "post"), ("/key/remove", "post")):
            with self.subTest(path):
                r = getattr(client, method)(path)
                self.assertEqual((r.status_code, r.get_data(), r.mimetype), (404, b"Not found.", "text/plain"))

    def test_a_static_miss_is_still_a_plain_404(self):
        r = unlocked(public_app()).get("/static/not-a-file.css")
        self.assertEqual((r.status_code, r.get_data()), (404, FLASK_404))

    def test_a_view_that_aborts_404_itself_keeps_flasks_answer(self):
        r = unlocked(public_app()).get("/export.zip")
        self.assertEqual((r.status_code, r.get_data()), (404, FLASK_404))

    def test_a_json_endpoint_keeps_its_own_409_body(self):
        client = unlocked(public_app())
        r = client.get("/progress")
        self.assertEqual((r.status_code, r.get_json()), (409, {"error": "No sweep running."}))
        self.assertEqual(client.get("/activity").status_code, 200)

    def test_outside_the_door_an_unknown_address_still_goes_to_the_gate(self):
        r = public_app().test_client().get("/nowhere")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/beta", r.headers["Location"])

    def test_the_gate_keeps_its_words_and_its_form(self):
        client = public_app().test_client()
        body = client.get("/beta").get_data(as_text=True)
        for word in ("Sweep is in private beta", "Enter the code you were given", "Beta code", 'name="code"', 'type="password"',
                     'action="/beta"', ">Enter</button>"):
            self.assertIn(word, body)
        wrong = client.post("/beta", data={"code": "nope"})
        self.assertEqual(wrong.status_code, 403)
        self.assertIn("That code is not right.", wrong.get_data(as_text=True))
        right = client.post("/beta", data={"code": CODE})
        self.assertEqual((right.status_code, right.headers["Location"]), (302, "/"))


class TheNotFoundPage(unittest.TestCase):
    def setUp(self):
        self.client = unlocked(public_app())

    def test_an_unknown_address_is_the_page_with_status_404(self):
        r = self.client.get("/this-page-does-not-exist")
        body = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 404)
        self.assertIn('<span class="eyebrow">Lost the trail</span>', body)
        self.assertRegex(body, r'<h1>This page isn\'t <span class="scrib">here</span>\.</h1>')
        self.assertIn('<p class="lede">The address may be mistyped or out of date.</p>', body)
        self.assertEqual(re.findall(r'<a class="primary" href="([^"]*)">Back to the start</a>', body), ["/"])
        self.assertIn("<title>Page not found — Sweep</title>", body)
        self.assertIn('<html lang="en" class="skin-a">', body)
        self.assertIn("sweep-a.css", body)

    def test_it_is_the_a_skin_page_with_its_brush_and_one_primary_link(self):
        body = self.client.get("/nope").get_data(as_text=True)
        self.assertIn('<div class="stack nf-a">', body)
        self.assertIn('<span class="nf-brush" aria-hidden="true"><svg', body)
        main = body[body.index("<main>"):body.index("</main>")]
        self.assertEqual(len(re.findall(r'class="primary"', main)), 1)
        self.assertEqual(main.count("<h1>"), 1)

    def test_it_never_says_which_address_was_asked_for(self):
        for path in ("/<script>x</script>", "/secret-path-xyz", '/a"onmouseover=1', "/%3Cb%3Ebold%3C/b%3E", "/nope?next=//evil.example"):
            with self.subTest(path):
                r = self.client.get(path)
                body = r.get_data(as_text=True)
                self.assertEqual(r.status_code, 404)
                self.assertIn("Lost the trail", body)
                for piece in ("x</script>", "script&gt;x", "&lt;script", "secret-path-xyz", "onmouseover", "bold</b>", "%3Cb", "&lt;b&gt;", "evil.example"):
                    self.assertNotIn(piece, body, piece)

    def test_none_of_the_four_steps_is_current(self):
        body = self.client.get("/nope").get_data(as_text=True)
        tracker = body[body.index('<nav class="tracker"'):body.index("</nav>")]
        self.assertNotIn(" current", tracker)
        self.assertNotIn("aria-current", tracker)
        self.assertEqual(len(re.findall(r'<li class="step', tracker)), 4)
        self.assertRegex(tracker, r'<span class="tracker-at">\s*</span>')

    def test_a_post_to_nowhere_is_the_page_too_and_still_404(self):
        r = self.client.post("/nowhere", data={"a": "b"})
        self.assertEqual(r.status_code, 404)
        self.assertIn("Lost the trail", r.get_data(as_text=True))

    def test_the_page_is_not_cached_or_indexed(self):
        r = self.client.get("/nope")
        self.assertEqual(r.headers["Cache-Control"], "no-store")
        self.assertEqual(r.headers["X-Robots-Tag"], "noindex")

    def test_the_other_404s_are_not_this_page(self):
        for path in ("/static/not-a-file.css", "/export.zip", "/events"):
            with self.subTest(path):
                r = self.client.get(path)
                self.assertEqual(r.status_code, 404)
                self.assertNotIn("Lost the trail", r.get_data(as_text=True))

    def test_the_console_has_no_such_page(self):
        app = app_module.create_app(state={"resume_text": "x"}, derive=lambda t, p: dict(DERIVED))
        app.config["TESTING"] = True
        self.assertNotIn(b"Lost the trail", app.test_client().get("/nope").get_data())


class TheDoor(unittest.TestCase):
    def test_it_wears_the_a_skin_by_hand_and_has_no_tracker(self):
        body = public_app().test_client().get("/beta").get_data(as_text=True)
        self.assertIn('<html lang="en" class="skin-a">', body)
        self.assertIn("/static/sweep-a.css", body)
        self.assertIn("/static/theme.js", body)
        self.assertIn("Instrument+Sans", body)
        self.assertIn('<meta name="theme-color" content="#FFF6EE" media="(prefers-color-scheme: light)">', body)
        self.assertIn('<main class="door-a">', body)
        self.assertIn('<svg class="mark"', body)
        for gone in ('class="tracker"', "<header", "style=", "working"):
            self.assertNotIn(gone, body)

    def test_the_refusal_is_an_alert(self):
        client = public_app().test_client()
        body = client.post("/beta", data={"code": "nope"}).get_data(as_text=True)
        self.assertIn('<p class="error" role="alert">That code is not right.</p>', body)
        limited = public_app()
        limited.beta_attempts.reserve = lambda ip: (_ for _ in ()).throw(public.BetaLimited("x"))
        r = limited.test_client().post("/beta", data={"code": "nope"})
        self.assertEqual(r.status_code, 429)
        self.assertIn("Too many attempts.", r.get_data(as_text=True))


class TheWorkerTroubleOnKey(unittest.TestCase):
    """public.sweep_service_trouble: each refusal's status and words on /key. Two of them named the choices in the old voice
    ("take the free sources"); they now say Quick Sweep / Deep Sweep. Nothing pinned the old words."""

    CASES = [
        (worker_client.NeedsKey, 400, "Paste it again for a Deep Sweep, or run a Quick Sweep."),
        (worker_client.RunNotFound, 502, "That sweep is no longer available"),
        (worker_client.QueueFull, 503, "there is no room in the queue for yours"),
        (worker_client.PaidUnavailable, 503, "You can run a Quick Sweep now, or come back later."),
        (worker_client.WorkerError, 502, "search service is not responding just now"),
    ]

    def test_each_one_lands_on_key_with_its_status_and_its_words(self):
        app = public_app()
        state = {"exc": None}

        def boom():
            raise state["exc"]("harness")
        app.add_url_rule("/t-trouble", "t_trouble", boom)
        client = unlocked(app)
        with mock.patch.object(public, "PUBLIC_ENDPOINTS", public.PUBLIC_ENDPOINTS | {"t_trouble"}):
            for exc, status, words in self.CASES:
                with self.subTest(exc.__name__):
                    state["exc"] = exc
                    r = client.get("/t-trouble")
                    body = r.get_data(as_text=True)
                    self.assertEqual(r.status_code, status)
                    self.assertIn(words, body)
                    self.assertIn('<p class="error" role="alert">', body)
                    self.assertNotIn("free sources", body.split("<main>")[1].split("</main>")[0].replace("133 free", ""))


class TheMarkup(unittest.TestCase):
    """The hooks the sheet hangs on, and that the console never carries them."""

    def test_the_new_root_classes_are_public_only_and_one_place(self):
        self.assertEqual(with_class("cf-a"), ["confirm.html"])
        self.assertEqual(with_class("pe-a"), ["plan_error.html"])
        self.assertEqual(with_class("nf-a"), ["not_found.html"])
        self.assertEqual(with_class("door-a"), ["beta.html"])
        self.assertIn('<div class="stack{% if public_mode %} cf-a{% endif %}">', template("confirm.html"))
        self.assertIn('<div class="stack{% if public_mode %} pe-a{% endif %}">', template("plan_error.html"))
        self.assertIn('<p class="muted{% if public_mode %} notice{% endif %}">{{ notice }}</p>', template("results.html"))

    def test_the_console_renders_none_of_them(self):
        app = app_module.create_app(state={"resume_text": "x"}, derive=lambda t, p: dict(DERIVED))
        app.config["TESTING"] = True
        for path in ("/", "/key", "/results"):
            body = app.test_client().get(path, follow_redirects=True).get_data(as_text=True)
            for token in ("cf-a", "pe-a", "nf-a", "door-a", "skin-a"):
                self.assertNotIn(token, body, (path, token))

    def test_the_templates_that_carry_an_error_are_the_ones_the_sheet_means(self):
        self.assertEqual(with_class("error"), ["base.html", "beta.html", "configure.html", "confirm.html", "deriving.html",
                                               "key.html", "results.html", "review.html", "running.html", "upload.html"])


def parts(css):
    """Every selector part of every rule in `css` (comments gone), at-rule preludes skipped."""
    out = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        sel = m.group(1).strip()
        if sel.startswith("@"):
            sel = sel.split("{")[-1].strip()
            if sel.startswith("@"):
                continue
        out.extend(p.strip() for p in re.split(r",(?![^(]*\))", sel) if p.strip())
    return out


def enclosing(css, pos):
    stack, start = [], 0
    for i, ch in enumerate(css[:pos]):
        if ch == "{":
            stack.append(css[start:i].strip())
            start = i + 1
        elif ch == "}":
            stack.pop()
            start = i + 1
        elif ch == ";":
            start = i + 1
    return stack


# Every selector of the section names one of these anchors: a class that exists in one place, or a screen's error / the dialog.
ANCHORS = {
    ".runbar": ["_active_run.html"], ".door-a": ["beta.html"], ".cf-a": ["confirm.html"], ".pe-a": ["plan_error.html"],
    ".nf-a": ["not_found.html"], ".res-a": ["results.html"], ".data-a": ["privacy.html"], ".site-foot": ["base.html"],
}
SHARED = (".skin-a .error:not(.confirm.ticket > .decide .error)", ".skin-a dialog.feedback", ".skin-a .tracker-at:empty")


class TheStylesheet(Quiet):
    def test_the_section_exists_and_is_the_last_one(self):
        self.assertIn("==== A10: the other states", CSS)
        self.assertGreater(len(parts(A10)), 30)
        self.assertNotIn("==== A", CSS[A10_START + 10:])

    def test_every_selector_hangs_on_the_skin_and_on_markup_that_is_only_where_it_means(self):
        for p in parts(A10):
            with self.subTest(selector=p):
                self.assertTrue(p.startswith(".skin-a"), p)
                self.assertTrue(any(a in p for a in ANCHORS) or p.startswith(SHARED), p)

    def test_the_anchors_exist_in_exactly_the_templates_meant(self):
        for token, where in ANCHORS.items():
            if token == ".runbar":
                self.assertEqual(with_class("runbar"), where)
            else:
                self.assertEqual(with_class(token[1:]), where, token)

    def test_every_class_a_selector_names_exists_in_a_template(self):
        dynamic = {"live", "done", "warn", "wait"}                     # the strip's tone, set by logic.run_banner / parse_banner
        for p in parts(A10):
            for token in re.findall(r"\.([A-Za-z][\w-]*)", p):
                if token in dynamic or token == "skin-a":
                    continue
                with self.subTest(selector=p, token=token):
                    self.assertTrue(with_class(token) or token in ("mark",), f"no template carries .{token}")
        logic = (ROOT / "logic.py").read_text(encoding="utf-8")
        for tone in dynamic:
            self.assertRegex(logic, rf'"tone": "{tone}"|tone="{tone}"|\'{tone}\'|"{tone}"')

    def test_the_stub_s_own_error_is_left_to_a7_and_the_dialog_is_covered(self):
        self.assertIn(":not(.confirm.ticket > .decide .error)", A10)
        self.assertIn(".skin-a .confirm.ticket > .decide .error", CSS[:A10_START])      # A7's rule, which the :not() leaves alone

    def test_nothing_in_the_section_moves(self):
        self.assertNotRegex(A10, r"(?<![\w-])(animation|transition)(?:-[\w-]+)?\s*:")
        self.assertNotIn("@keyframes", A10)
        self.assertNotIn("prefers-reduced-motion", A10)

    def test_no_raw_colour(self):
        self.assertNotRegex(A10, r"#[0-9A-Fa-f]{3,8}\b")
        self.assertNotRegex(A10, r"rgba?\(|hsla?\(")
        self.assertNotRegex(A10, r"[:\s](white|black|red|green|blue|orange|yellow|purple|pink)\s*[;}]")

    def test_peach_is_money_only_and_there_is_none_here(self):
        self.assertNotRegex(A10, r"var\(--(paid|paid-lift|a-pch)\)")

    def test_an_error_is_not_colour_alone(self):
        rule = re.search(r"\.skin-a \.error:not\([^)]*\)::before[^{]*\{([^}]*)\}", A10).group(1)
        self.assertIn('content: "!"', rule)
        self.assertIn("border: 2px solid var(--over)", rule)
        box = re.search(r"\.skin-a \.error:not\([^)]*\) \{([^}]*)\}", A10).group(1)
        self.assertIn("border: 2px solid var(--a-line)", box)
        self.assertIn("box-shadow: 4px 4px 0 var(--a-shadow)", box)

    def test_the_strip_is_centred_on_its_own_button_and_stays_in_the_gutters(self):
        rule = re.search(r"\.skin-a \.runbar \{([^}]*)\}", A10).group(1)
        self.assertIn("align-items: center", rule)
        self.assertIn("border: 2px solid var(--a-line)", rule)
        self.assertRegex(A10, r"@media \(min-width: 64rem\) \{\s*\.skin-a \.runbar \{[^}]*max-width: 85rem")

    def test_sweep_css_and_the_other_sheets_are_not_edited_by_this_stage(self):
        sweep = (ROOT / "static" / "sweep.css").read_text(encoding="utf-8")
        for name in ("door-a", "door-card", "cf-a", "pe-a", "nf-a", "nf-brush"):
            self.assertNotIn(name, sweep)


class TheServerChangeIsNarrow(unittest.TestCase):
    """The handler is registered for the router's NotFound only, in public.py, and renders the page without the requested path."""

    def test_it_is_the_routers_not_found_and_nothing_else(self):
        src = (ROOT / "public.py").read_text(encoding="utf-8")
        handler = src[src.index("@app.errorhandler(NotFound)"):src.index("@app.errorhandler(worker_client.PlanChanged)")]
        self.assertIn("exc is not request.routing_exception", handler)
        self.assertIn('request.path.startswith("/static/")', handler)
        self.assertIn("return exc", handler)
        self.assertIn('render_template("not_found.html", **app.shell(None)), 404', handler)
        self.assertNotIn("request.path", handler.replace('request.path.startswith("/static/")', ""))
        self.assertNotIn("request.url", handler)
        self.assertNotIn("request.full_path", handler)
        self.assertEqual(src.count("errorhandler(NotFound)"), 1)
        self.assertNotIn("errorhandler(NotFound)", (ROOT / "app.py").read_text(encoding="utf-8"))

    def test_the_template_does_not_print_anything_the_visitor_sent(self):
        t = re.sub(r"\{#.*?#\}", "", template("not_found.html"), flags=re.S)
        for forbidden in ("request", "path", "url_for('static'", "|safe"):
            self.assertNotIn(forbidden, t)
        self.assertEqual(re.findall(r"\{\{[^}]*\}\}", t), ["{{ brush(40) }}", "{{ url_for('upload') }}"])


if __name__ == "__main__":
    unittest.main()
