"""P4-S1C: the last public-open hardening.

  plans     the screens reuse the worker's dry run for an unchanged plan,
            briefly; a dry run that is not reused is counted (10 a minute
            per session, 30 per network) and refused 429 before it starts;
            POST /run always asks the worker afresh and is never limited here
  polls     /progress and /activity are paced per session (429 +
            Retry-After), and the worker's status and rows are asked at most
            once per STATUS_TTL per owner and run — never across either
  headers   no-store on everything session-bound, noindex on all but the
            front door, nosniff / referrer / framing everywhere, HSTS on
            HTTPS only; a real robots.txt
  recovery  POST /review's fallback derivation gives POST /derive's error
            screens; POST /run after a restart never reaches a KeyError
  wording   no "beta" on a public limit page

The suite runs with the time-based controls at their fastest (see
sweep/tests/__init__.py); every class here that is about one of them puts the
production value back for itself. Fakes only: no model, provider or network.
"""

import io
import json
import logging
import os
import sys
import threading
import time
import unittest
from unittest import mock

from sweep import app as app_module
from sweep import public, safe_pdf, worker_client, worker_link
from sweep.tests import PRODUCTION
from sweep.tests.test_app import DERIVED
from sweep.tests.test_public import CODE, public_app, unlocked, upload
from sweep.tests.test_public_guardrails import (BENCH, LINE, FakeRun, cookie, free_plan,
                                                on_disk, pdf, ready_for_run)

sys.path.insert(0, os.path.join(app_module.REPO_ROOT, "auto-apply"))
import local_profile  # noqa: E402
import make_profile  # noqa: E402
import resume_parser  # noqa: E402

import inference  # noqa: E402

PLANS = mock.patch.object(app_module, "PLAN_CACHE_SECONDS", PRODUCTION["plan_cache_seconds"])
STATUS = mock.patch.object(worker_link, "STATUS_TTL", PRODUCTION["status_ttl"])
POLLS = mock.patch.dict(public.POLL_INTERVALS, PRODUCTION["poll_intervals"])


def audit_lines():
    lines = []

    class Sink(logging.Handler):
        def emit(self, record):
            lines.append(json.loads(record.getMessage()))

    return lines, Sink()


class TestTheProductionValues(unittest.TestCase):
    """The suite relaxes them; what ships is pinned here."""

    def test_they_are_what_the_docs_say(self):
        self.assertEqual(PRODUCTION, {"status_ttl": 2.5, "plan_cache_seconds": 20,
                                      "poll_intervals": {"progress": 2.0, "activity": 2.0}})
        self.assertEqual((public.PLANS_PER_SESSION_MINUTE, public.PLANS_PER_IP_MINUTE,
                          public.POLL_BURST), (10, 30, 3))


# ================================================================ plans
class TestPlanCache(unittest.TestCase):

    def setUp(self):
        PLANS.start()
        self.addCleanup(PLANS.stop)
        self.clock, self.asked = [1000.0], []

    def app(self, **kw):
        def fetch(profile):
            self.asked.append(profile)
            return free_plan(profile)

        kw.setdefault("start_sweep", lambda p: FakeRun())
        return public_app(fetch_plan=fetch, now=lambda: self.clock[0], **kw)

    def ready(self, app):
        client = unlocked(app)
        ready_for_run(client)
        self.asked.clear()
        return client

    def test_normal_plan_screen_works_and_an_identical_one_reuses_the_dry_run(self):
        # T2: the plan screen is /configure; publicly /confirm is its old address (a redirect that plans nothing itself).
        client = self.ready(self.app())
        self.assertEqual(client.get("/configure").status_code, 200)
        self.assertEqual(client.get("/confirm", follow_redirects=True).status_code, 200)
        self.assertEqual(client.get("/configure").status_code, 200)
        self.assertEqual(len(self.asked), 1)
        self.clock[0] += 21
        client.get("/configure")
        self.assertEqual(len(self.asked), 2, "a plan outlived its twenty seconds")

    def test_a_preference_edit_is_a_new_plan(self):
        client = self.ready(self.app())
        client.get("/configure")
        client.post("/configure", data={"max_age_days": "3"})
        client.get("/configure")
        self.assertEqual(len(self.asked), 2)

    def test_a_skill_edit_is_a_new_plan(self):
        app = self.app()
        client = self.ready(app)
        client.get("/configure")
        room = app.session_store._rooms[cookie(app, client)["sid"]]["data"]
        room["derived"] = dict(room["derived"], skill_weights=[{"term": "go", "weight": 5}])
        client.get("/configure")
        self.assertEqual(len(self.asked), 2)

    def test_the_cache_is_this_sessions_alone(self):
        app = self.app()
        first, second = self.ready(app), self.ready(app)
        first.get("/configure")
        second.get("/configure")
        self.assertEqual(len(self.asked), 2)

    def test_run_always_asks_the_worker_afresh(self):
        client = self.ready(self.app())
        client.get("/configure")
        client.get("/configure")
        self.assertEqual(len(self.asked), 1)
        self.assertTrue(client.post("/run").headers["Location"].endswith("/running"))
        self.assertEqual(len(self.asked), 2, "POST /run priced from the cache")

    def test_live_pricing_reuses_an_unchanged_plan_and_prices_a_new_one(self):
        client = self.ready(self.app())
        client.get("/configure")
        self.assertEqual(client.post("/estimate", json={}).status_code, 200)
        self.assertEqual(len(self.asked), 1)
        self.assertEqual(client.post("/estimate", json={"max_age_days": "3"}).status_code, 200)
        self.assertEqual(len(self.asked), 2)


class TestPlanLimits(unittest.TestCase):
    """A dry run that is not reused is counted — and refused before it runs."""

    def setUp(self):
        self.asked = []

    def app(self):
        def fetch(profile):
            self.asked.append(profile)
            return free_plan(profile)

        return public_app(fetch_plan=fetch, start_sweep=lambda p: FakeRun())

    def test_ten_plans_a_minute_per_session_then_429_and_no_dry_run(self):
        app = self.app()
        client = unlocked(app)
        ready_for_run(client)
        used = app.plan_limits[0].taken()
        for _ in range(public.PLANS_PER_SESSION_MINUTE - used):
            self.assertEqual(client.get("/configure").status_code, 200)
        asked = len(self.asked)
        lines, sink = audit_lines()
        public.AUDIT.addHandler(sink)
        try:
            for path, method in (("/confirm", "get"), ("/configure", "get"),
                                 ("/estimate", "post")):
                with self.subTest(path):
                    # /confirm is the old address of the plan screen (T2): followed, it is refused the same way.
                    r = getattr(client, method)(path, **({"json": {}} if method == "post" else {"follow_redirects": True}))
                    self.assertEqual(r.status_code, 429)
                    body = r.get_data(as_text=True)
                    self.assertIn("search plans for you in the last minute", body)
                    self.assertNotIn("private beta", body)
        finally:
            public.AUDIT.removeHandler(sink)
        self.assertEqual(len(self.asked), asked, "a refused plan reached the worker")
        self.assertEqual({(l["event"], l["outcome"]) for l in lines}, {("plan", "rate_limited")})
        # POST /run is not a screen's plan: its own quota governs it.
        self.assertTrue(client.post("/run").headers["Location"].endswith("/running"))

    def test_thirty_a_minute_per_network(self):
        app = self.app()
        app.plan_limits[1].per_ip = 3
        clients = [unlocked(app) for _ in range(2)]
        for c in clients:
            ready_for_run(c)
        statuses = [clients[n % 2].get("/configure").status_code for n in range(3)]
        self.assertEqual(statuses, [200, 200, 200])
        self.assertEqual(clients[1].get("/configure").status_code, 429)   # the network's 4th
        other = unlocked(app)
        other.environ_base["REMOTE_ADDR"] = "198.51.100.8"
        ready_for_run(other)
        self.assertEqual(other.get("/configure").status_code, 200)

    def test_the_window_is_a_minute(self):
        app = self.app()
        clock = [0.0]
        for limit in app.plan_limits:
            limit._clock = lambda: clock[0]
        client = unlocked(app)
        ready_for_run(client)
        while client.get("/configure").status_code == 200:
            pass
        clock[0] += 61
        self.assertEqual(client.get("/configure").status_code, 200)


# ================================================================ polls
class TestPollPacing(unittest.TestCase):

    def setUp(self):
        POLLS.start()
        self.addCleanup(POLLS.stop)

    def app(self):
        app = public_app(fetch_plan=free_plan, start_sweep=lambda p: FakeRun(finished=False))
        self.clock = [0.0]
        app.poll_limit = public.PollLimit(clock=lambda: self.clock[0])
        return app

    def at(self, client, path, t):
        self.clock[0] = t
        return client.get(path)

    def test_the_browsers_own_cadence_is_never_refused(self):
        app = self.app()
        client = unlocked(app)
        ready_for_run(client)
        client.post("/run")
        progress = [self.at(client, "/progress", t).status_code for t in range(0, 240, 4)]
        self.assertEqual(set(progress), {200})
        # The reading screen asks /activity every 3 s while the strip asks
        # every 8 s: ~2.2 s apart on average, from one ordinary tab.
        times = sorted({t for t in range(0, 240, 3)} | {t + 0.5 for t in range(0, 240, 8)})
        activity = [self.at(client, "/activity?on=review", t).status_code for t in times]
        self.assertEqual(set(activity), {200})

    def test_too_fast_is_429_with_retry_after_and_nothing_asked_of_the_worker(self):
        app = self.app()
        client = unlocked(app)
        ready_for_run(client)
        client.post("/run")
        lines, sink = audit_lines()
        public.AUDIT.addHandler(sink)
        try:
            self.assertEqual(app.before_request_funcs[None][0].__name__, "poll_pace")
            for path in ("/progress", "/activity"):
                with self.subTest(path), mock.patch.object(worker_link, "rehydrate") as asked:
                    answers = [self.at(client, path, 10.0) for _ in range(public.POLL_BURST)]
                    reached = asked.call_count
                    answers += [self.at(client, path, 10.0) for _ in range(2)]
                    self.assertEqual([a.status_code for a in answers],
                                     [200] * public.POLL_BURST + [429, 429])
                    self.assertEqual((reached, asked.call_count), (public.POLL_BURST,) * 2,
                                     "a refused poll went on towards the worker")
                    self.assertGreaterEqual(int(answers[-1].headers["Retry-After"]), 1)
                    self.assertEqual(answers[-1].get_json(), {"error": "Too many requests. Slow down."})
                    self.assertEqual(self.at(client, path, 12.1).status_code, 200)
        finally:
            public.AUDIT.removeHandler(sink)
        self.assertIn(("poll", "rate_limited"), {(l["event"], l["outcome"]) for l in lines})

    def test_each_session_has_its_own_pace(self):
        app = self.app()
        a, b = unlocked(app), unlocked(app)
        for c in (a, b):
            ready_for_run(c)
        for _ in range(public.POLL_BURST + 1):
            self.at(a, "/progress", 5.0)
        self.assertEqual(self.at(a, "/progress", 5.0).status_code, 429)
        self.assertEqual(self.at(b, "/progress", 5.0).status_code, 409)   # b's own, and no run

    def test_a_browser_with_no_session_is_not_paced_and_costs_nothing(self):
        app = self.app()
        bot = app.test_client(use_cookies=False)
        self.assertEqual({bot.get("/activity").status_code for _ in range(20)}, {302})


class TestTheStatusCache(unittest.TestCase):
    """What the worker said is reused briefly — per owner and run only."""

    def setUp(self):
        STATUS.start()
        self.addCleanup(STATUS.stop)
        worker_link._ASKED.clear()
        self.app = public_app()

    def ctx(self, sid):
        ctx = self.app.test_request_context()
        ctx.push()
        from flask import session
        session["sid"] = sid
        self.addCleanup(ctx.pop)

    def test_inside_the_window_one_question_per_owner_and_run(self):
        calls = []
        with mock.patch.object(worker_client, "run_status",
                               lambda run_id: calls.append(run_id) or {"state": "running"}):
            self.ctx("session-a")
            for _ in range(5):
                worker_link._status("run1")
            worker_link._status("run2")
        self.assertEqual(calls, ["run1", "run2"])

    def test_never_across_sessions(self):
        answers = iter([{"state": "running", "who": "a"}, {"state": "running", "who": "b"}])
        with mock.patch.object(worker_client, "run_status", lambda run_id: next(answers)):
            self.ctx("session-a")
            self.assertEqual(worker_link._status("same-run")["who"], "a")
            self.ctx("session-b")
            self.assertEqual(worker_link._status("same-run")["who"], "b")

    def test_a_change_shows_as_soon_as_the_window_closes(self):
        states = iter([{"state": "running"}, {"state": "done"}])
        with mock.patch.object(worker_link, "STATUS_TTL", 0.2), \
                mock.patch.object(worker_client, "run_status", lambda run_id: next(states)):
            self.ctx("session-a")
            self.assertEqual(worker_link._status("r")["state"], "running")
            self.assertEqual(worker_link._status("r")["state"], "running")
            time.sleep(0.25)
            self.assertEqual(worker_link._status("r")["state"], "done")

    def test_a_refusal_is_kept_as_briefly_and_a_stop_forgets(self):
        calls = []

        def refuse(run_id):
            calls.append(1)
            raise worker_client.WorkerError("down")

        with mock.patch.object(worker_client, "run_status", refuse):
            self.ctx("session-a")
            for _ in range(3):
                with self.assertRaises(worker_client.WorkerError):
                    worker_link._status("r")
            self.assertEqual(len(calls), 1)
            worker_link.forget("r")
            with self.assertRaises(worker_client.WorkerError):
                worker_link._status("r")
            self.assertEqual(len(calls), 2)

    def test_the_plan_changed_check_still_runs_on_a_kept_status(self):
        from flask import session
        self.ctx("session-a")
        session["run_id"], session["run_tracks"] = "r", [["a" * 16, "A"], ["b" * 16, "B"]]
        session["run_plan_hash"] = "f" * 64
        good = {"schema": 2, "track_ids": ["a" * 16, "b" * 16], "plan_hash": "f" * 64,
                "state": "running"}
        with mock.patch.object(worker_client, "run_status", lambda run_id: dict(good)):
            worker_link._status("r")
            worker_link._ASKED[("status", public.owner_for_session(), "r")][1]["plan_hash"] = "0" * 64
            with self.assertRaises(worker_client.ProtocolError):
                worker_link._status("r")               # checked on every read, cached or not

    def test_rows_are_fetched_once_a_window_and_come_back_whole(self):
        calls, rows = [], [{"title": f"t{i}"} for i in range(1200)]
        with mock.patch.object(worker_client, "all_rows",
                               lambda run_id: calls.append(run_id) or rows):
            self.ctx("session-a")
            first = worker_link._rows("r")
            second = worker_link._rows("r")
        self.assertEqual((len(calls), first, second), (1, rows, rows))
        self.assertIsNot(first, second)


# ============================================================== headers
class TestHeaders(unittest.TestCase):

    def app(self):
        rows = [{"title": "=cmd|' /C calc'!A0", "company": "Acme", "apply_url": "https://x.example",
                 "score": "70", "source_site": "greenhouse:acme"}]
        return public_app(fetch_plan=free_plan, start_sweep=lambda p: FakeRun(),
                          read_rows=lambda profile: [dict(r) for r in rows])

    def session(self):
        app = self.app()
        client = unlocked(app)
        ready_for_run(client)
        client.post("/run")
        return app, client

    PRIVATE = ("/", "/review", "/profile", "/profile.py", "/key", "/configure", "/confirm",
               "/running", "/progress", "/activity", "/results", "/export.csv", "/export.json",
               "/export.xlsx", "/export.html", "/healthz")

    def test_everything_session_bound_is_no_store(self):
        _app, client = self.session()
        for path in self.PRIVATE:
            with self.subTest(path):
                self.assertEqual(client.get(path).headers.get("Cache-Control"), "no-store")
        self.assertEqual(client.get("/nope").headers["Cache-Control"], "no-store")
        self.assertEqual(public_app().test_client().get("/beta").headers["Cache-Control"],
                         "no-store")

    def test_static_files_and_robots_keep_their_own_caching(self):
        client = public_app().test_client()
        for path in ("/static/sweep.css", "/robots.txt"):
            with self.subTest(path):
                r = client.get(path)
                self.assertEqual(r.status_code, 200)
                self.assertNotEqual(r.headers.get("Cache-Control"), "no-store")
                self.assertNotIn("X-Robots-Tag", r.headers)

    def test_only_the_front_door_is_indexable(self):
        _app, client = self.session()
        self.assertNotIn("X-Robots-Tag", client.get("/").headers)
        for path in self.PRIVATE[1:]:
            with self.subTest(path):
                self.assertEqual(client.get(path).headers.get("X-Robots-Tag"), "noindex")

    def test_the_hardening_headers_on_every_page(self):
        _app, client = self.session()
        for path in ("/", "/results", "/export.csv", "/healthz", "/nope"):
            with self.subTest(path):
                h = client.get(path).headers
                self.assertEqual(h["X-Content-Type-Options"], "nosniff")
                self.assertEqual(h["Referrer-Policy"], "strict-origin-when-cross-origin")
                self.assertEqual(h["X-Frame-Options"], "DENY")
                self.assertEqual(h["Content-Security-Policy"], "frame-ancestors 'none'")

    def test_hsts_only_over_https(self):
        client = public_app().test_client()
        self.assertNotIn("Strict-Transport-Security", client.get("/healthz").headers)
        secure = client.get("/healthz", headers={"X-Forwarded-Proto": "https",
                                                "X-Forwarded-For": "203.0.113.7, 172.16.0.1"})
        self.assertEqual(secure.headers["Strict-Transport-Security"], "max-age=31536000")

    def test_the_data_page_needs_no_code_is_indexable_and_linked(self):
        app = public_app()
        r = app.test_client().get("/privacy")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("X-Robots-Tag", r.headers)
        self.assertEqual(r.headers["Cache-Control"], "no-store")
        body = r.get_data(as_text=True)
        for claim in ("two hours", "48 hours", "45 minutes", "never written to disk"):
            self.assertIn(claim, body)
        self.assertIn('href="/privacy"', unlocked(app).get("/").get_data(as_text=True))

    def test_robots_txt_is_real_and_needs_no_code(self):
        r = public_app().test_client().get("/robots.txt")
        self.assertEqual((r.status_code, r.mimetype), (200, "text/plain"))
        body = r.get_data(as_text=True)
        self.assertTrue(body.startswith("User-agent: *\nAllow: /\n"))
        for path in ("/review", "/results", "/export", "/profile", "/running", "/confirm"):
            self.assertIn(f"Disallow: {path}\n", body)
        self.assertNotIn("Disallow: /\n", body)

    def test_exports_name_one_charset_and_stay_defused(self):
        _app, client = self.session()
        self.assertEqual(client.get("/export.csv").headers["Content-Type"], "text/csv; charset=utf-8")
        self.assertEqual(client.get("/export.html").headers["Content-Type"],
                         "text/html; charset=utf-8")
        self.assertEqual(client.get("/export.json").headers["Content-Type"],
                         "application/json; charset=utf-8")
        self.assertIn("'=cmd", client.get("/export.csv").get_data(as_text=True))


# ============================================================= recovery
class TestReviewFallbackNeverFails500(unittest.TestCase):

    def test_expected_failures_through_the_fallback(self):
        for exc, status in ((local_profile.Escalated(["role_keywords: none"]), 422),
                            (inference.ModelUnavailable("down"), 502),
                            (make_profile.ModelAnswerError("truncated"), 502),
                            (RuntimeError("anything"), 502)):
            with self.subTest(type(exc).__name__):
                def derive(text, prefs, exc=exc):
                    raise exc
                app = public_app(derive=derive)
                client = unlocked(app)
                upload(client)
                r = client.post("/review", data={})
                self.assertEqual(r.status_code, status)
                self.assertNotIn("Traceback", r.get_data(as_text=True))
                self.assertEqual(app.beta_limit.taken(), 1, "the failure was refunded")

    def test_one_tracks_failure_leaves_the_other_alone(self):
        with mock.patch.dict(os.environ, {worker_link.MULTI_FLAG: "1"}):
            texts = ["first résumé", "second résumé"]
            calls = []

            def derive(text, prefs):
                calls.append(text)
                if text == "second résumé":
                    raise local_profile.Escalated(["dates"])
                return dict(DERIVED)

            app = public_app(extract=lambda p: texts.pop(0), derive=derive)
            client = unlocked(app)
            upload(client)
            upload(client)
            room = app.session_store._rooms[cookie(app, client)["sid"]]["data"]
            first, second = room["tracks"]
            self.assertEqual(client.post("/review", data={"track": first["id"]}).status_code, 302)
            r = client.post("/review", data={"track": second["id"]})
        self.assertEqual(r.status_code, 422)
        self.assertTrue(first["reviewed"] and first["derived"])
        self.assertEqual((second["derived"], second["parse"]["state"]), (None, "failed"))


class TestRunAfterARestart(unittest.TestCase):
    """The real worker on loopback: a finished run, a restarted Render, the
    cookie alone — and POST /run starts nothing and never 500s."""

    def test_one_resume_goes_back_to_the_upload_screen(self):
        from sweep.tests.test_worker_link import (CODE as LINK_CODE, WORKER_TOKEN,
                                                  render_app, worker_on_a_socket)
        with worker_on_a_socket() as (url, store):
            env = {worker_client.URL_ENV: url, worker_client.TOKEN_ENV: WORKER_TOKEN}
            with mock.patch.dict(os.environ, env):
                first = render_app(url, fetch_plan=free_plan)
                client = first.test_client()
                client.post("/beta", data={"code": LINK_CODE})
                ready_for_run(client)
                client.post("/run")
                client.post("/stop")
                restarted = render_app(url)
                again = restarted.test_client()
                again.set_cookie("session", client.get_cookie("session").value)
                self.assertEqual(again.get("/running").status_code, 200)   # rehydrated
                r = again.post("/run")
                body = r.get_data(as_text=True)
            self.assertEqual(r.status_code, 409)
            self.assertIn("Upload it again", body)
            self.assertEqual(len(store.all()), 1, "a run was started from nothing")
            self.assertEqual(restarted.run_limit.taken(), 0)

    def test_the_resume_setup_goes_back_to_review(self):
        from sweep.tests.test_worker_link import render_app
        with mock.patch.dict(os.environ, {worker_link.MULTI_FLAG: "1"}):
            app = render_app("http://127.0.0.1:9")
            client = app.test_client()
            client.post("/beta", data={"code": "let-me-in"})
            with client.session_transaction() as sess:
                sess["sid"], sess["run_id"] = "restarted", "0" * 32
            r = client.post("/run")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/review", r.headers["Location"])


# ============================================================== wording
class TestNeutralWording(unittest.TestCase):

    def test_no_limit_page_says_beta_open_or_locked(self):
        for env in (None, {public.ACCESS_ENV: "0"}):
            with self.subTest(open=bool(env)):
                app = public_app(env_extra=env)
                app.beta_limit.per_ip = 0
                client = app.test_client() if env else unlocked(app)
                upload(client)
                body = client.post("/derive").get_data(as_text=True)
                self.assertIn("résumé reads from your network", body)
                self.assertNotIn("beta", body.lower().replace("data-beta", ""))

    def test_the_public_404_and_the_feedback_dialog(self):
        client = unlocked(public_app())
        self.assertEqual(client.get("/events").get_data(as_text=True), "Not found.")
        page = client.get("/").get_data(as_text=True)
        self.assertIn("I read every message.", page)
        self.assertNotIn("during the beta", page)


# ============================================================ linux hook
@unittest.skipUnless(sys.platform.startswith("linux"), "RLIMIT_AS is enforced on Linux only")
class TestSafePdfOnLinux(unittest.TestCase):
    """THE pre-opening check (docs/public-beta.md): on Linux, at the shipped
    288 MiB ceiling, an ordinary résumé reads exactly as before and the
    audit's PDF is refused while this process lives on. Must report 3 tests
    run, 0 skipped, before the door is opened."""

    def test_ordinary_resumes_read_under_the_real_ceiling(self):
        for path in [p for p in BENCH if os.path.exists(p)][:3]:
            with self.subTest(os.path.basename(path)):
                self.assertEqual(safe_pdf.extract(path), resume_parser.extract_text(path))

    def test_the_audit_pdf_is_refused_and_this_process_survives(self):
        began = time.monotonic()
        with on_disk(pdf(LINE * (16 * 2**20 // len(LINE)))) as path:
            with self.assertRaises(safe_pdf.Unreadable) as caught:
                safe_pdf.extract(path)
        self.assertIn(caught.exception.category, ("resource", "timeout"))
        self.assertLess(time.monotonic() - began, safe_pdf.TIMEOUT_SECONDS + 5)
        self.assertEqual(safe_pdf.in_flight(), 0)

    def test_the_child_really_runs_under_the_ceiling(self):
        import subprocess
        probe = ("import resource, sys; sys.path.insert(0, %r); from sweep import safe_pdf; "
                 "safe_pdf._apply_limits(safe_pdf.MEMORY_BYTES, 20); "
                 "print(resource.getrlimit(resource.RLIMIT_AS)[0])") % app_module.REPO_ROOT
        out = subprocess.run([sys.executable, "-I", "-c", probe], capture_output=True, text=True,
                             timeout=30, env={"PATH": os.defpath})
        self.assertEqual(out.stdout.strip(), str(safe_pdf.MEMORY_BYTES))


if __name__ == "__main__":
    unittest.main()
