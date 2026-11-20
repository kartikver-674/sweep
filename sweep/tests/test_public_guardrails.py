"""P4-S1B: the guardrails that make an open door safe to have.

Each class pins one requirement of the public-open remediation:

  access      SWEEP_ACCESS_LOCK: only "0" opens, and open skips the code and
              nothing else; a restart with it unset re-locks everyone
  grants      a grant is HMAC(SECRET_KEY, code): a rotated code revokes it,
              an old beta_ok=True is nothing, and guessing is rate-limited
  identity    one canonical limiter key — IPv4, mapped IPv4, IPv6 /64 — used
              by every per-IP limit
  derivation  an admitted attempt is consumed, success or failure
  pdf         the parser runs in a child with a page cap, a text cap, a clock
              and a memory ceiling, one at a time, counted per attempt
  rooms       reading allocates nothing; a network holds at most 10 rooms,
              and empty rooms are evicted before anyone's work
  runs        a Sweep is one unit, reserved before planning, given back when
              no worker run was created (the schema-2 counts are pinned in
              test_multi_render.RunQuota, beside the harness they need)

No model, no provider, no network: derive and the worker are fakes (or the
real worker on loopback), and every PDF is generated here or is one of the
synthetic bench/resumes documents.
"""

import contextlib
import io
import json
import logging
import os
import sys
import tempfile
import threading
import time
import unittest
import zlib
from unittest import mock

from sweep import app as app_module
from sweep import public, safe_pdf, worker_client, worker_link
from sweep.tests.test_app import DERIVED
from sweep.tests.test_public import CODE, public_app, unlocked, upload

REPO = app_module.REPO_ROOT
sys.path.insert(0, os.path.join(REPO, "auto-apply"))
import local_profile  # noqa: E402
import make_profile  # noqa: E402
import resume_parser  # noqa: E402

import inference  # noqa: E402

OPEN = {public.ACCESS_ENV: "0"}
LINE = b"BT /F1 10 Tf 50 700 Td (Senior Python engineer with Django and AWS) Tj ET\n"
# WinAnsi octal escapes: an e-acute, an en dash, curly quotes — the text must
# cross the child's pipe exactly as the in-process parser returns it.
ACCENTS = (b"BT /F1 12 Tf 50 720 Td (R\\351sum\\351 \\226 Caf\\351 \\223quoted\\224) Tj ET\n"
           b"BT /F1 12 Tf 50 700 Td (Second line, same page) Tj ET\n")
BENCH = [os.path.join(REPO, "bench", "resumes", f"{name}.pdf") for name in (
    "ada-plain", "ada-twocol", "bhaskar-tables", "chen-messy", "dmitri-plain",
    "esi-twocol")]


def pdf(content=LINE, pages=1):
    """A minimal valid PDF: `pages` pages sharing ONE Flate content stream —
    the shape of the audit's amplification cases, at whatever size a test
    needs."""
    comp = zlib.compress(content, 9)
    kids = " ".join(f"{3 + i} 0 R" for i in range(pages))
    cs, font = 3 + pages, 4 + pages
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode()]
    objs += [f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources "
             f"<< /Font << /F1 {font} 0 R >> >> /Contents {cs} 0 R >>".encode()
             for _ in range(pages)]
    objs.append(b"<< /Length " + str(len(comp)).encode() + b" /Filter /FlateDecode >>\n"
                b"stream\n" + comp + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                b"/Encoding /WinAnsiEncoding >>")
    out = io.BytesIO()
    out.write(b"%PDF-1.7\n")
    offsets = []
    for n, obj in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(f"{n} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n"
              f"{xref}\n%%EOF\n".encode())
    return out.getvalue()


def encrypted(user_password):
    """RC4 needs no optional crypto package; an empty user password is the
    common permissions-only case, which pypdf opens on its own."""
    from pypdf import PdfReader, PdfWriter
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf(ACCENTS))))
    writer.encrypt(user_password=user_password, owner_password="owner-only",
                   algorithm="RC4-128")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@contextlib.contextmanager
def on_disk(data):
    handle, path = tempfile.mkstemp(suffix=".pdf")
    with os.fdopen(handle, "wb") as fh:
        fh.write(data)
    try:
        yield path
    finally:
        with contextlib.suppress(OSError):
            os.remove(path)


def cookie(app, client):
    jar = client.get_cookie("session")
    return app.session_interface.get_signing_serializer(app).loads(jar.value) if jar else {}


def carried(client, app):
    """The same browser, cookie and all, arriving at another process."""
    other = app.test_client()
    other.set_cookie("session", client.get_cookie("session").value)
    return other


def room_of(app, client):
    return app.session_store._rooms[cookie(app, client)["sid"]]["data"]


def free_plan(profile):
    return {"profile": profile, "sites": {}, "max_results": {}, "free_sources": 3,
            "public_paid": "multi"}


class FakeRun:
    """What start_sweep hands back: a RemoteRun, as far as /run can tell."""

    def __init__(self, finished=True):
        self.run_id, self.finished = os.urandom(8).hex(), finished

    def poll(self):
        return 0 if self.finished else None


def ready_for_run(client):
    """Upload, derive, approve and choose free: one POST /run away."""
    upload(client)
    client.post("/derive")
    client.post("/review", data={})
    client.post("/key/free")


def post_pdf(client, data):
    return client.post("/resume", data={"resume": (io.BytesIO(data), "cv.pdf")},
                       content_type="multipart/form-data")


# ============================================================ access switch
class TestAccessSwitch(unittest.TestCase):

    def test_A_B_C_every_value_but_an_exact_zero_is_locked(self):
        for value in (None, "", "1", "true", "false", "off", "no", "00", "0 0",
                      "O", "open", "-0", "0.0", "zero"):
            with self.subTest(value=value):
                with mock.patch.dict(os.environ):
                    os.environ.pop(public.ACCESS_ENV, None)
                    app = public_app(env_extra=None if value is None
                                     else {public.ACCESS_ENV: value})
                r = app.test_client().get("/")
                self.assertEqual(r.status_code, 302)
                self.assertIn("/beta", r.headers["Location"])
                self.assertEqual(app.test_client().get("/healthz").get_json()["access"],
                                 "locked")

    def test_D_exactly_zero_opens_spaces_aside(self):
        for value in ("0", " 0 ", "0\n"):
            with self.subTest(value=repr(value)):
                app = public_app(env_extra={public.ACCESS_ENV: value})
                self.assertEqual(app.test_client().get("/").status_code, 200)
                self.assertEqual(app.test_client().get("/healthz").get_json()["access"],
                                 "open")

    def test_the_code_is_still_required_while_open(self):
        with self.assertRaises(public.NotConfigured):
            public_app(env_extra={**OPEN, public.CODE_ENV: ""})

    def test_E_open_the_resume_flow_needs_no_code(self):
        client = public_app(env_extra=OPEN).test_client()
        self.assertEqual(upload(client).status_code, 302)
        self.assertEqual(client.post("/derive").status_code, 302)
        self.assertEqual(client.get("/review").status_code, 200)
        self.assertEqual(client.post("/review", data={}).status_code, 302)

    def test_F_open_a_cross_site_post_is_still_refused(self):
        client = public_app(env_extra=OPEN).test_client()
        upload(client)
        for path in ("/derive", "/resume", "/run", "/key/free", "/tracks", "/beta"):
            with self.subTest(path):
                r = client.post(path, headers={"Origin": "https://evil.example"})
                self.assertEqual(r.status_code, 403)

    def test_G_open_the_allowlist_still_holds(self):
        client = public_app(env_extra=OPEN).test_client()
        self.assertEqual(client.get("/events").status_code, 404)
        for path in ("/key/remove", "/second-key", "/merge", "/applied", "/rescore"):
            with self.subTest(path):
                self.assertEqual(client.post(path).status_code, 404)

    def test_H_open_a_session_is_the_same_permanent_two_hours(self):
        app = public_app(env_extra=OPEN)
        client = app.test_client()
        answer = upload(client)
        self.assertTrue(cookie(app, client).get("_permanent"))
        self.assertIn("Expires=", answer.headers["Set-Cookie"])
        self.assertEqual(app.permanent_session_lifetime.total_seconds(), public.SESSION_TTL)

    def test_I_open_hands_out_no_grant_even_at_the_door(self):
        app = public_app(env_extra=OPEN)
        client = app.test_client()
        upload(client)
        for method in ("get", "post"):
            r = getattr(client, method)("/beta", data={"code": CODE})
            self.assertEqual(r.status_code, 302)
            self.assertTrue(r.headers["Location"].endswith("/"))
        self.assertFalse({"beta_grant", "beta_ok"} & set(cookie(app, client)))

    def test_J_a_restart_without_the_flag_relocks_an_open_visitor(self):
        app = public_app(env_extra=OPEN)
        client = app.test_client()
        upload(client)
        client.post("/derive")
        returning = carried(client, public_app())      # same SECRET_KEY, no flag
        for path in ("/", "/review", "/configure", "/results"):
            with self.subTest(path):
                r = returning.get(path)
                self.assertEqual(r.status_code, 302)
                self.assertIn("/beta", r.headers["Location"])
        self.assertIn("/beta", returning.post("/derive").headers["Location"])
        # The re-lock is a door, not a lock-out: the code still opens it.
        returning.post("/beta", data={"code": CODE})
        self.assertEqual(returning.get("/").status_code, 200)


# ================================================================ grants
class TestBetaGrant(unittest.TestCase):

    def test_K_the_right_code_opens_the_door(self):
        app = public_app()
        client = app.test_client()
        self.assertEqual(client.post("/beta", data={"code": CODE}).status_code, 302)
        self.assertEqual(client.get("/").status_code, 200)
        self.assertRegex(cookie(app, client)["beta_grant"], r"^[0-9a-f]{64}$")
        self.assertNotIn(CODE, client.get_cookie("session").value)

    def test_L_a_wrong_code_is_refused(self):
        client = public_app().test_client()
        self.assertEqual(client.post("/beta", data={"code": "guess"}).status_code, 403)
        self.assertEqual(client.get("/").status_code, 302)

    def test_a_non_ascii_guess_is_a_refusal_not_a_crash(self):
        client = public_app().test_client()
        self.assertEqual(client.post("/beta", data={"code": "cafè-ü"}).status_code, 403)

    def test_M_rotating_the_code_revokes_every_grant(self):
        client = unlocked(public_app())
        self.assertEqual(client.get("/").status_code, 200)
        returning = carried(client, public_app(env_extra={public.CODE_ENV: "a-new-code"}))
        self.assertIn("/beta", returning.get("/").headers["Location"])
        self.assertEqual(returning.post("/beta", data={"code": CODE}).status_code, 403)
        returning.post("/beta", data={"code": "a-new-code"})
        self.assertEqual(returning.get("/").status_code, 200)

    def test_a_grant_survives_a_restart_with_the_same_code(self):
        client = unlocked(public_app())
        self.assertEqual(carried(client, public_app()).get("/").status_code, 200)

    def test_N_an_old_beta_ok_true_opens_nothing(self):
        client = public_app().test_client()
        with client.session_transaction() as sess:
            sess["beta_ok"] = True
            sess["beta_grant"] = "0" * 64
        self.assertIn("/beta", client.get("/").headers["Location"])
        self.assertIn("/beta", client.post("/derive").headers["Location"])

    def test_O_the_eleventh_attempt_is_429_even_when_right(self):
        client = public_app().test_client()
        for _ in range(public.BETA_ATTEMPTS):
            self.assertEqual(client.post("/beta", data={"code": "guess"}).status_code, 403)
        r = client.post("/beta", data={"code": CODE})
        self.assertEqual(r.status_code, 429)
        self.assertNotIn(CODE, r.get_data(as_text=True))
        self.assertEqual(client.get("/").status_code, 302)

    def test_right_codes_do_not_use_up_the_attempts(self):
        """A campus behind one address, all entering the code: only wrong
        guesses count, and a lockout still refuses even the right one."""
        app = public_app()
        for _ in range(3 * public.BETA_ATTEMPTS):
            self.assertEqual(app.test_client().post("/beta", data={"code": CODE}).status_code, 302)
        self.assertEqual(app.beta_attempts.taken(), 0)

    def test_the_window_is_ten_minutes_and_per_network(self):
        self.assertEqual((public.BETA_ATTEMPTS, public.BETA_WINDOW), (10, 600))
        app = public_app()
        clock = [1000.0]
        app.beta_attempts._clock = lambda: clock[0]
        a, b = app.test_client(), app.test_client()
        b.environ_base["REMOTE_ADDR"] = "198.51.100.9"
        for _ in range(10):
            a.post("/beta", data={"code": "guess"})
        self.assertEqual(a.post("/beta", data={"code": CODE}).status_code, 429)
        self.assertEqual(b.post("/beta", data={"code": CODE}).status_code, 302)
        clock[0] += 601
        self.assertEqual(a.post("/beta", data={"code": CODE}).status_code, 302)


# ============================================================== identity
class TestLimiterIdentity(unittest.TestCase):

    def test_the_canonical_key(self):
        key = public.limiter_key
        self.assertEqual(key("203.0.113.5"), "203.0.113.5")
        self.assertEqual(key(" 203.0.113.5 "), "203.0.113.5")
        self.assertEqual(key("::ffff:203.0.113.5"), "203.0.113.5")
        self.assertEqual(key("::FFFF:cb00:7105"), "203.0.113.5")
        same = {key(a) for a in ("2001:db8:1:2::1", "2001:db8:1:2::ffff",
                                 "2001:0db8:0001:0002:0000:0000:0000:0001",
                                 "2001:DB8:1:2:ffff:ffff:ffff:ffff")}
        self.assertEqual(same, {"2001:db8:1:2::/64"})
        self.assertNotEqual(key("2001:db8:1:3::1"), key("2001:db8:1:2::1"))
        self.assertEqual(key("fe80::1%eth0"), "fe80::/64")
        for junk in (None, "", "unknown", "not-an-ip", "999.1.1.1", "1.2.3",
                     "2001:db8::g", "203.0.113.5, 10.0.0.1"):
            with self.subTest(junk=junk):
                self.assertEqual(key(junk), "invalid")

    def test_client_ip_is_the_canonical_key_after_proxyfix(self):
        seen = []

        def derive(text, prefs):
            seen.append(public.client_ip())
            return dict(DERIVED)

        app = public_app(derive=derive)
        for chain, expected in (("2001:db8:1:2::7, 172.16.0.1", "2001:db8:1:2::/64"),
                                ("::ffff:203.0.113.5, 172.16.0.1", "203.0.113.5"),
                                ("9.9.9.9, 203.0.113.5, 172.16.0.1", "203.0.113.5")):
            with self.subTest(chain=chain):
                client = unlocked(app)
                upload(client)
                client.post("/derive", headers={"X-Forwarded-For": chain})
                self.assertEqual(seen[-1], expected)

    @staticmethod
    def one_64(app):
        a, b = unlocked(app), unlocked(app)
        a.environ_base["REMOTE_ADDR"] = "2001:db8:1:2::1"
        b.environ_base["REMOTE_ADDR"] = "2001:db8:1:2::beef"
        return a, b

    def test_every_per_ip_limit_counts_a_64_as_one_visitor(self):
        with self.subTest("derivation"):
            a, b = self.one_64(public_app(env_extra={public.PER_IP_ENV: "1"}))
            upload(a), upload(b)
            self.assertEqual(a.post("/derive").status_code, 302)
            self.assertEqual(b.post("/derive").status_code, 429)
        with self.subTest("upload"):
            app = public_app()
            app.upload_limits[0].per_ip = 1
            a, b = self.one_64(app)
            self.assertEqual(upload(a).status_code, 302)
            self.assertEqual(upload(b).status_code, 429)
        with self.subTest("beta attempts"):
            app = public_app()
            a, b = app.test_client(), app.test_client()
            a.environ_base["REMOTE_ADDR"] = "2001:db8:1:2::1"
            b.environ_base["REMOTE_ADDR"] = "2001:db8:1:2::2"
            for _ in range(10):
                a.post("/beta", data={"code": "guess"})
            self.assertEqual(b.post("/beta", data={"code": CODE}).status_code, 429)
        with self.subTest("run"):
            app = public_app(env_extra={public.RUNS_PER_IP_ENV: "1"},
                             fetch_plan=free_plan, start_sweep=lambda p: FakeRun())
            a, b = self.one_64(app)
            ready_for_run(a), ready_for_run(b)
            self.assertEqual(a.post("/run").status_code, 302)
            self.assertEqual(b.post("/run").status_code, 429)
        with self.subTest("feedback"):
            from sweep.tests.test_feedback import post, ready
            app, client = ready()
            app.feedback_limit.per_ip = 1
            self.assertEqual(post(client, ip="2001:db8:1:2::1").status_code, 200)
            self.assertEqual(post(client, ip="2001:db8:1:2::2").status_code, 429)
            self.assertEqual(post(client, ip="2001:db8:1:3::1").status_code, 200)
        with self.subTest("rooms"):
            store, app = public.SessionStore(per_ip=1), public_app()
            with app.test_request_context(environ_base={"REMOTE_ADDR": "2001:db8:1:2::1"}):
                store.room()["resume_text"] = "one"
            with app.test_request_context(environ_base={"REMOTE_ADDR": "2001:db8:1:2::9"}):
                with self.assertRaises(public.RoomsFull):
                    store.room()


# ============================================================ derivation
class TestDerivationAttempts(unittest.TestCase):
    """One admitted attempt, one slot — whatever the attempt turns into."""

    @staticmethod
    def raising(exc, calls=None):
        def derive(text, prefs):
            if calls is not None:
                calls.append(1)
            raise exc
        return derive

    def test_every_outcome_consumes_exactly_one(self):
        outcomes = {
            "success": (lambda t, p: dict(DERIVED), 302),
            "escalated": (self.raising(local_profile.Escalated(["role_keywords: none"])), 422),
            "inference failure": (self.raising(inference.ModelUnavailable("no model")), 502),
            "malformed answer": (self.raising(make_profile.ModelAnswerError("truncated")), 502),
            "anything else": (self.raising(RuntimeError("boom")), 502),
        }
        for label, (derive, status) in outcomes.items():
            with self.subTest(label):
                app = public_app(derive=derive)
                client = unlocked(app)
                upload(client)
                self.assertEqual(client.post("/derive").status_code, status)
                self.assertEqual((app.beta_limit.taken("127.0.0.1"), app.beta_limit.taken()),
                                 (1, 1))

    def test_an_internal_retry_is_still_one(self):
        calls = []

        def retrying(text, prefs):
            calls.extend(["fields", "fields-retry", "employment"])
            return dict(DERIVED)

        app = public_app(derive=retrying)
        client = unlocked(app)
        upload(client)
        client.post("/derive")
        self.assertEqual((len(calls), app.beta_limit.taken()), (3, 1))

    def test_failures_exhaust_the_per_ip_limit(self):
        calls = []
        app = public_app(derive=self.raising(local_profile.Escalated(["dates"]), calls),
                         env_extra={public.PER_IP_ENV: "2"})
        client = unlocked(app)
        upload(client)
        self.assertEqual([client.post("/derive").status_code for _ in range(3)],
                         [422, 422, 429])
        self.assertEqual(len(calls), 2, "the refused attempt reached the model")

    def test_failures_from_many_networks_exhaust_the_global_limit(self):
        calls = []
        app = public_app(derive=self.raising(inference.ModelUnavailable("down"), calls),
                         env_extra={public.TOTAL_ENV: "3"})
        statuses = []
        for n in range(5):
            client = unlocked(app)
            client.environ_base["REMOTE_ADDR"] = f"198.51.100.{n + 1}"
            upload(client)
            statuses.append(client.post("/derive").status_code)
        self.assertEqual(statuses, [502, 502, 502, 429, 429])
        self.assertEqual((len(calls), app.beta_limit.taken()), (3, 3))

    def test_the_review_fallback_shares_the_same_quota(self):
        calls = []

        def derive(text, prefs):
            calls.append(1)
            return dict(DERIVED)

        app = public_app(derive=derive, env_extra={public.PER_IP_ENV: "1"})
        client = unlocked(app)
        upload(client)
        self.assertEqual(client.post("/review", data={}).status_code, 302)  # it derives
        self.assertEqual(app.beta_limit.taken(), 1)
        other = unlocked(app)
        upload(other)
        self.assertEqual(other.post("/derive").status_code, 429)
        self.assertEqual(other.post("/review", data={}).status_code, 429)
        self.assertEqual(len(calls), 1)

    def test_a_failed_review_fallback_is_consumed_too(self):
        # P4-S1C gave the fallback POST /derive's own error screens; the
        # attempt stays counted all the same.
        app = public_app(derive=self.raising(local_profile.Escalated(["dates"])))
        client = unlocked(app)
        upload(client)
        self.assertEqual(client.post("/review", data={}).status_code, 422)
        self.assertEqual(app.beta_limit.taken(), 1)

    def test_what_fails_before_derive_consumes_nothing(self):
        app = public_app()
        client = unlocked(app)
        self.assertEqual(client.post("/derive").status_code, 302)        # no résumé
        self.assertEqual(client.post("/review", data={}).status_code, 302)
        self.assertEqual(app.beta_limit.taken(), 0)
        with mock.patch.dict(os.environ, {worker_link.MULTI_FLAG: "1"}):
            multi = public_app()
            client = unlocked(multi)
            upload(client)
            r = client.post("/derive", data={"track": "0123456789abcdef"})
        self.assertEqual(r.status_code, 404)                              # not this session's
        self.assertEqual(multi.beta_limit.taken(), 0)

    def test_a_parse_already_in_flight_is_not_a_second_attempt(self):
        started, finish = threading.Event(), threading.Event()

        def slow(text, prefs):
            started.set()
            finish.wait(5)
            return dict(DERIVED)

        app = public_app(derive=slow)
        client = unlocked(app)
        upload(client)
        worker = threading.Thread(target=lambda: client.post("/derive"))
        worker.start()
        self.assertTrue(started.wait(5))
        self.assertEqual(carried(client, app).post("/derive").status_code, 302)
        finish.set()
        worker.join(5)
        self.assertEqual(app.beta_limit.taken(), 1)


# ================================================================== pdf
class TestSafePdf(unittest.TestCase):
    """The child: the same text, bounded, and every failure a fixed sentence."""

    def test_ordinary_resumes_read_exactly_as_the_in_process_parser(self):
        documents = [p for p in BENCH if os.path.exists(p)]
        self.assertGreaterEqual(len(documents), 4)
        for path in documents:
            with self.subTest(os.path.basename(path)):
                self.assertEqual(safe_pdf.extract(path), resume_parser.extract_text(path))
        for label, data in (("accents", pdf(ACCENTS)), ("three pages", pdf(LINE * 40, 3)),
                            ("permissions-only encryption", encrypted(""))):
            with self.subTest(label), on_disk(data) as path:
                self.assertEqual(safe_pdf.extract(path), resume_parser.extract_text(path))

    def test_non_ascii_crosses_the_pipe_unchanged(self):
        with on_disk(pdf(ACCENTS)) as path:
            text = safe_pdf.extract(path)
        self.assertIn("Résumé – Café", text)
        self.assertIn("“quoted”", text)

    def refused(self, data, category, **limits):
        with on_disk(data) as path:
            with self.assertRaises(safe_pdf.Unreadable) as caught:
                safe_pdf.extract(path, **limits)
        exc = caught.exception
        self.assertEqual((exc.category, exc.status), (category, 503 if category == "busy" else 400))
        for leak in ("pypdf", "Traceback", "/tmp", "/var", ".pdf", "Error"):
            self.assertNotIn(leak, exc.message)
        return exc

    def test_ten_pages_read_and_eleven_are_refused(self):
        with on_disk(pdf(LINE, pages=10)) as path:
            self.assertTrue(safe_pdf.extract(path))
        self.refused(pdf(LINE, pages=11), "pages")

    def test_more_than_100_kib_of_text_is_refused(self):
        self.assertEqual(safe_pdf.MAX_TEXT_BYTES, 100 * 1024)
        self.refused(pdf(LINE * 3000), "too_long")
        with on_disk(pdf(LINE * 20)) as path:
            size = len(safe_pdf.extract(path).encode())
        self.refused(pdf(LINE * 20), "too_long", max_text=size - 1)

    def test_malformed_and_encrypted_are_controlled_refusals(self):
        self.refused(pdf(LINE)[:200], "malformed")
        self.refused(b"%PDF-1.7\n" + bytes(range(256)) * 8, "malformed")
        self.refused(encrypted("a-real-password"), "encrypted")

    def test_a_child_past_its_clock_is_killed_and_refused(self):
        procs, real = [], safe_pdf.subprocess.Popen

        def keep(*a, **kw):
            procs.append(real(*a, **kw))
            return procs[-1]

        began = time.monotonic()
        with mock.patch.object(safe_pdf.subprocess, "Popen", keep):
            self.refused(pdf(LINE * 200_000), "timeout", timeout=0.5)
        self.assertLess(time.monotonic() - began, 10)
        self.assertEqual(len(procs), 1)
        self.assertIsNotNone(procs[0].poll(), "the child outlived its refusal")

    def test_a_child_killed_by_the_kernel_is_a_controlled_refusal(self):
        dies = [sys.executable, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGKILL)"]
        with mock.patch.object(safe_pdf, "_child_argv", lambda path: dies):
            self.refused(pdf(), "resource")

    def test_the_ceilings_are_set_on_the_child(self):
        calls = []

        class Resource:
            RLIMIT_AS, RLIMIT_CPU = "AS", "CPU"

            @staticmethod
            def setrlimit(which, limits):
                calls.append((which, limits))

        safe_pdf._apply_limits(safe_pdf.MEMORY_BYTES, 20, Resource, "linux")
        self.assertEqual(calls, [("AS", (safe_pdf.MEMORY_BYTES,) * 2), ("CPU", (20, 20))])
        self.assertTrue(256 * 2**20 <= safe_pdf.MEMORY_BYTES <= 320 * 2**20)
        self.assertEqual((safe_pdf.MAX_PAGES, safe_pdf.TIMEOUT_SECONDS), (10, 15))

    def test_on_linux_a_ceiling_that_cannot_be_set_refuses_to_parse(self):
        class Refusing:
            RLIMIT_AS, RLIMIT_CPU = "AS", "CPU"

            @staticmethod
            def setrlimit(which, limits):
                raise ValueError("not allowed")

        with self.assertRaises(ValueError):
            safe_pdf._apply_limits(1, 1, Refusing, "linux")
        safe_pdf._apply_limits(1, 1, Refusing, "darwin")      # best effort off Linux
        out = io.BytesIO()
        with mock.patch.object(safe_pdf, "_apply_limits", side_effect=ValueError), \
                mock.patch.object(sys, "stdout", mock.Mock(buffer=out)):
            safe_pdf._child("/nonexistent.pdf", {"SWEEP_PDF_MEMORY": "1", "SWEEP_PDF_CPU": "1",
                                                 "SWEEP_PDF_MAX_PAGES": "10",
                                                 "SWEEP_PDF_MAX_TEXT": "10"})
        self.assertEqual(out.getvalue(), b"ERR\nresource")

    @unittest.skipUnless(sys.platform.startswith("linux"), "RLIMIT_AS is enforced on Linux")
    def test_on_linux_the_memory_ceiling_stops_a_greedy_parse(self):
        self.refused(pdf(LINE * (16 * 2**20 // len(LINE))), "resource", memory=96 * 2**20)

    def test_the_child_inherits_no_secret(self):
        seen, real = {}, safe_pdf.subprocess.Popen

        def keep(*a, **kw):
            seen.update(kw["env"])
            return real(*a, **kw)

        with mock.patch.dict(os.environ, {"SECRET_KEY": "s3cret", "SWEEP_WORKER_TOKEN": "wt"}), \
                mock.patch.object(safe_pdf.subprocess, "Popen", keep), on_disk(pdf()) as path:
            safe_pdf.extract(path)
        self.assertFalse({"SECRET_KEY", "SWEEP_WORKER_TOKEN"} & set(seen))

    def test_one_reader_at_a_time_and_no_queue(self):
        self.assertTrue(safe_pdf._SLOT.acquire(timeout=1))
        try:
            began = time.monotonic()
            self.refused(pdf(), "busy", slot_wait=0.1)
            self.assertLess(time.monotonic() - began, 2)
        finally:
            safe_pdf._SLOT.release()
        with on_disk(pdf()) as path:
            self.assertTrue(safe_pdf.extract(path))
        self.assertEqual(safe_pdf.in_flight(), 0)


class TestTheUploadRoute(unittest.TestCase):
    """The real reader behind POST /resume: counted, bounded, cleaned up."""

    def app(self, **kw):
        return public_app(extract=None, **kw)      # public mode's own: the child

    def test_a_real_upload_reads_through_the_child(self):
        app = self.app()
        client = unlocked(app)
        self.assertEqual(post_pdf(client, pdf(ACCENTS)).status_code, 302)
        self.assertIn("Résumé – Café", room_of(app, client)["resume_text"])

    def test_every_refusal_is_a_4xx_with_a_fixed_sentence(self):
        app = self.app()
        for data, phrase in ((pdf(LINE, pages=11), "more than 10 pages"),
                             (pdf(LINE)[:200], "could not read that PDF"),
                             (encrypted("pw"), "password-protected"),
                             (b"PK\x03\x04 zip", "not a PDF")):
            with self.subTest(phrase):
                r = post_pdf(unlocked(app), data)
                self.assertEqual(r.status_code, 400)
                body = r.get_data(as_text=True)
                self.assertIn(phrase, body)
                self.assertNotIn("Traceback", body)
        self.assertEqual(len(app.session_store), 0, "a refused file made a room")

    def test_every_parse_attempt_counts_and_a_non_pdf_does_not(self):
        app = self.app()
        client = unlocked(app)
        post_pdf(client, b"GIF89a not a pdf")
        self.assertEqual(app.upload_limits[0].taken(), 0)
        post_pdf(client, pdf(LINE)[:200])              # malformed: counted
        post_pdf(client, pdf(LINE, pages=11))          # too many pages: counted
        post_pdf(client, pdf())                        # read: counted
        self.assertEqual([lim.taken() for lim in app.upload_limits], [3, 3, 3])

    def test_the_quotas_refuse_before_any_child_starts(self):
        self.assertEqual((public.PARSES_PER_IP_HOUR, public.PARSES_PER_IP_DAY,
                          public.PARSES_PER_SESSION_HOUR), (10, 30, 6))
        for which in (0, 1, 2):
            with self.subTest(limit=which):
                app = self.app()
                app.upload_limits[which].per_ip = 2
                one = unlocked(app)
                clients = [one] * 3 if which == 2 else [unlocked(app) for _ in range(3)]
                for c in clients[:2]:
                    self.assertEqual(post_pdf(c, pdf()).status_code, 302)
                with mock.patch.object(safe_pdf.subprocess, "Popen",
                                       side_effect=AssertionError("a child started")):
                    r = post_pdf(clients[2], pdf())
                self.assertEqual(r.status_code, 429)
                # A refusal by a later limit gives the earlier ones back.
                self.assertEqual(app.upload_limits[0].taken(), 2)

    def test_a_busy_reader_is_a_503(self):
        client = unlocked(self.app())
        self.assertTrue(safe_pdf._SLOT.acquire(timeout=1))
        try:
            with mock.patch.object(safe_pdf, "SLOT_WAIT_SECONDS", 0.05):
                r = post_pdf(client, pdf())
        finally:
            safe_pdf._SLOT.release()
        self.assertEqual(r.status_code, 503)
        self.assertIn("reading another résumé", r.get_data(as_text=True))

    def test_the_temp_file_is_gone_on_every_path(self):
        made, real = [], tempfile.mkstemp

        def mkstemp(*a, **kw):
            made.append(real(*a, **kw))
            return made[-1]

        app = self.app()
        sleeper = [sys.executable, "-c", "import time; time.sleep(30)"]
        with mock.patch.object(app_module.tempfile, "mkstemp", mkstemp):
            for data in (pdf(), pdf(LINE)[:200], pdf(LINE, pages=11), b"not a pdf"):
                post_pdf(unlocked(app), data)
            with mock.patch.object(safe_pdf, "_child_argv", lambda p: sleeper), \
                    mock.patch.object(safe_pdf, "TIMEOUT_SECONDS", 0.3):
                self.assertEqual(post_pdf(unlocked(app), pdf()).status_code, 400)
            app.upload_limits[0].per_ip = 0
            self.assertEqual(post_pdf(unlocked(app), pdf()).status_code, 429)
        self.assertEqual(len(made), 6)
        for _handle, path in made:
            self.assertFalse(os.path.exists(path), path)


# ================================================================ rooms
class TestLazyRooms(unittest.TestCase):

    def test_cookie_less_reading_allocates_nothing(self):
        for env in (None, OPEN):
            with self.subTest(open=bool(env)):
                app = public_app(env_extra=env)
                bot = app.test_client(use_cookies=False)
                for _ in range(20):
                    for path in ("/", "/review", "/key", "/configure", "/confirm",
                                 "/results", "/activity", "/progress", "/healthz",
                                 "/beta", "/profile"):
                        bot.get(path)
                self.assertEqual(len(app.session_store), 0)

    def test_an_open_bot_flood_leaves_a_real_visitor_alone(self):
        app = public_app(env_extra=OPEN)
        victim = app.test_client()
        upload(victim)
        victim.post("/derive")
        bot = app.test_client(use_cookies=False)
        for _ in range(600):
            bot.get("/")
        self.assertEqual(len(app.session_store), 1)
        self.assertEqual(victim.get("/review").status_code, 200)
        self.assertIn("react native", victim.get("/review").get_data(as_text=True))

    def test_the_first_write_makes_one_room_and_navigation_no_more(self):
        app = public_app(env_extra=OPEN)
        client = app.test_client()
        client.get("/")
        self.assertEqual(len(app.session_store), 0)
        upload(client)
        self.assertEqual(len(app.session_store), 1)
        for path in ("/", "/review", "/key", "/review", "/"):
            client.get(path)
        client.post("/derive")
        self.assertEqual(len(app.session_store), 1)

    def ctx(self, ip):
        return public_app().test_request_context(environ_base={"REMOTE_ADDR": ip})

    def test_ten_rooms_per_network_then_its_oldest_empty_one_goes(self):
        self.assertEqual(public.MAX_ROOMS_PER_IP, 10)
        store = public.SessionStore()
        for n in range(10):
            with self.ctx("203.0.113.7"):
                store.room()["resume_text" if n else "key_notice"] = f"r{n}"
        empty = [s for s, r in store._rooms.items() if "key_notice" in r["data"]]
        with self.ctx("203.0.113.7"):
            store.room()["resume_text"] = "eleventh"
        self.assertEqual(len(store), 10)
        self.assertNotIn(empty[0], store._rooms, "the empty room was not the one to go")
        with self.ctx("203.0.113.7"), self.assertRaises(public.RoomsFull):
            store.room()
        self.assertEqual(len(store), 10, "a refusal dropped somebody's work")
        with self.ctx("198.51.100.1"):
            store.room()["resume_text"] = "another network"
        self.assertEqual(len(store), 11)

    def test_a_network_at_its_cap_is_refused_on_screen_and_nobody_is_dropped(self):
        app = public_app()
        app.upload_limits[0].per_ip = app.upload_limits[1].per_ip = 99
        clients = [unlocked(app) for _ in range(11)]
        for c in clients[:10]:
            self.assertEqual(upload(c).status_code, 302)
        r = upload(clients[10])
        self.assertEqual(r.status_code, 429)
        self.assertIn("Too many Sweep sessions", r.get_data(as_text=True))
        self.assertEqual(len(app.session_store), 10)
        for c in clients[:10]:
            self.assertEqual(c.get("/review").status_code, 200)

    def test_at_the_global_cap_empty_rooms_go_before_anyones_work(self):
        store = public.SessionStore(cap=5)
        with self.ctx("203.0.113.7"):
            store.room()["resume_text"] = "victim"
            victim = public.session_id()
        for n in range(40):
            with self.ctx(f"198.51.100.{n}"):
                store.room()["key_notice"] = "empty"
        self.assertIn(victim, store._rooms)
        self.assertEqual(len(store), 5)

    def test_reading_an_expired_room_forgets_it(self):
        clock = [0.0]
        store = public.SessionStore(ttl=100, clock=lambda: clock[0])
        with self.ctx("203.0.113.7"):
            store.room()["resume_text"] = "x"
            clock[0] += 101
            self.assertEqual(store.peek(), {})
        self.assertEqual(len(store), 0)

    def test_open_visitors_are_isolated_from_each_other(self):
        texts = ["ADA-ONLY", "BEN-ONLY"]
        app = public_app(env_extra=OPEN, extract=lambda p: texts.pop(0),
                         derive=lambda t, p: {**DERIVED, "field_summary": t})
        ada, ben = app.test_client(), app.test_client()
        upload(ada), upload(ben)
        ada.post("/derive"), ben.post("/derive")
        self.assertIn("ADA-ONLY", ada.get("/review").get_data(as_text=True))
        self.assertNotIn("ADA-ONLY", ben.get("/review").get_data(as_text=True))

    def test_a_multi_resume_setup_room_works_open(self):
        texts = ["first résumé", "second résumé"]
        with mock.patch.dict(os.environ, {worker_link.MULTI_FLAG: "1"}):
            app = public_app(env_extra=OPEN, extract=lambda p: texts.pop(0))
            client = app.test_client()
            upload(client)
            upload(client)
        self.assertEqual(len(room_of(app, client)["tracks"]), 2)
        self.assertEqual(len(app.session_store), 1)


# ================================================================= runs
class TestRunQuota(unittest.TestCase):
    """Schema 1 through the injected seam: counted before planning, given
    back unless the worker created a run."""

    def app(self, start=None, plan=free_plan, **env):
        planned = []

        def fetch(profile):
            planned.append(profile)
            return plan(profile)

        app = public_app(env_extra=env or None, fetch_plan=fetch,
                         start_sweep=start or (lambda p: FakeRun()))
        app.planned = planned
        return app

    def test_a_free_sweep_counts_one_and_stays_counted(self):
        app = self.app()
        client = unlocked(app)
        ready_for_run(client)
        self.assertTrue(client.post("/run").headers["Location"].endswith("/running"))
        self.assertEqual((app.run_limit.taken("127.0.0.1"), app.run_limit.taken()), (1, 1))

    def test_a_second_click_while_it_runs_costs_nothing(self):
        app = self.app(start=lambda p: FakeRun(finished=False))
        client = unlocked(app)
        ready_for_run(client)
        client.post("/run")
        planned = len(app.planned)
        self.assertTrue(client.post("/run").headers["Location"].endswith("/running"))
        self.assertEqual(app.run_limit.taken(), 1)
        self.assertEqual(len(app.planned), planned, "a refresh re-planned")

    def test_the_per_ip_limit_refuses_before_planning(self):
        app = self.app(**{public.RUNS_PER_IP_ENV: "2"})
        client = unlocked(app)
        ready_for_run(client)
        for _ in range(2):
            self.assertEqual(client.post("/run").status_code, 302)
        planned = len(app.planned)
        r = client.post("/run")
        self.assertEqual(r.status_code, 429)
        body = r.get_data(as_text=True)
        self.assertIn("searches from your network today", body)
        self.assertNotIn("private beta", body)
        self.assertEqual(len(app.planned), planned, "a refused run was planned")
        self.assertEqual(app.run_limit.taken(), 2)

    def test_the_refusal_is_the_plan_screen_and_reuses_the_plan_it_just_priced(self):
        """T2: a refused run (429) comes back on the plan screen, which prices itself as any visit does. Within the screens' plan
        cache (20 seconds in production; the suite relaxes it to nothing, which is why the test above sees the screen plan) the
        refusal costs the worker no dry run, and the page says why."""
        with mock.patch.object(app_module, "PLAN_CACHE_SECONDS", 20):
            app = self.app(**{public.RUNS_PER_IP_ENV: "2"})
            client = unlocked(app)
            ready_for_run(client)
            for _ in range(2):
                self.assertEqual(client.post("/run").status_code, 302)
            planned = len(app.planned)
            r = client.post("/run")
            self.assertEqual(r.status_code, 429)
            body = r.get_data(as_text=True)
            self.assertIn("searches from your network today", body)
            self.assertIn('<h1>Plan your <span class="scrib">sweep</span>.</h1>', body)
            self.assertEqual(len(app.planned), planned, "a refused run was planned inside the plan cache")
            self.assertEqual(app.run_limit.taken(), 2)

    def test_the_global_limit_holds_across_networks(self):
        app = self.app(**{public.RUNS_TOTAL_ENV: "2"})
        statuses = []
        for n in range(3):
            client = unlocked(app)
            client.environ_base["REMOTE_ADDR"] = f"198.51.100.{n + 1}"
            ready_for_run(client)
            statuses.append(client.post("/run").status_code)
        self.assertEqual(statuses, [302, 302, 429])

    def test_a_run_refused_before_the_worker_is_given_back(self):
        def priced(profile):
            return dict(free_plan(profile), max_results={"linkedin": 15}, sites={
                "linkedin": [{"keywords": "x", "location": "Remote", "company": ""}]})

        app = self.app(plan=priced)
        client = unlocked(app)
        ready_for_run(client)
        self.assertEqual(client.post("/run").status_code, 400)    # free, yet priced
        self.assertEqual(app.run_limit.taken(), 0)

    def test_a_worker_that_fails_or_is_full_gives_it_back(self):
        for exc, status, phrase in (
                (worker_client.WorkerError("down"), 502, "not responding"),
                (worker_client.QueueFull("full"), 503, "no room in the queue")):
            with self.subTest(type(exc).__name__):
                def start(profile, exc=exc):
                    raise exc
                app = self.app(start=start)
                client = unlocked(app)
                ready_for_run(client)
                r = client.post("/run")
                self.assertEqual(r.status_code, status)
                self.assertIn(phrase, r.get_data(as_text=True))
                self.assertEqual(app.run_limit.taken(), 0)

    def test_a_plan_that_fails_gives_it_back(self):
        def broken(profile):
            raise RuntimeError("no plan today")

        app = self.app(plan=broken)
        client = unlocked(app)
        ready_for_run(client)
        self.assertEqual(client.post("/run").status_code, 500)
        self.assertEqual(app.run_limit.taken(), 0)

    def test_a_run_that_later_fails_still_counts(self):
        runs = []

        def start(profile):
            runs.append(FakeRun(finished=False))
            return runs[-1]

        app = self.app(start=start)
        client = unlocked(app)
        ready_for_run(client)
        client.post("/run")
        runs[-1].finished = True                   # the worker says it failed
        client.get("/running")
        self.assertEqual(app.run_limit.taken(), 1)

    def test_the_defaults_and_a_malformed_value(self):
        app = self.app()
        self.assertEqual((app.run_limit.per_ip, app.run_limit.total), (5, 150))
        with self.assertRaises(public.NotConfigured):
            public_app(env_extra={public.RUNS_PER_IP_ENV: "five"})


class TestQueueFullEndToEnd(unittest.TestCase):
    """The real worker on loopback with no waiting place: the second visitor
    is told the service is busy, nothing is counted, and no run exists."""

    def test_a_full_worker_is_busy_not_paid_off_and_not_a_run(self):
        from sweep.tests.test_worker_link import (CODE as LINK_CODE, WORKER_TOKEN,
                                                  render_app, worker_on_a_socket)
        with mock.patch.dict(os.environ, {"SWEEP_MAX_QUEUED_RUNS": "0"}), \
                worker_on_a_socket() as (url, store):
            app = render_app(url, fetch_plan=free_plan)
            with mock.patch.dict(os.environ, {worker_client.URL_ENV: url,
                                              worker_client.TOKEN_ENV: WORKER_TOKEN}):
                first, second = app.test_client(), app.test_client()
                for c in (first, second):
                    c.post("/beta", data={"code": LINK_CODE})
                    ready_for_run(c)
                self.assertTrue(first.post("/run").headers["Location"].endswith("/running"))
                r = second.post("/run")
            body = r.get_data(as_text=True)
            self.assertEqual(r.status_code, 503)
            self.assertIn("no room in the queue", body)
            self.assertNotIn("Paid searches are temporarily unavailable", body)
            self.assertEqual(len(store.all()), 1)
            self.assertEqual(app.run_limit.taken(), 1)
            self.assertIsNone(cookie(app, second).get("run_id"))


class TestWorkerClientQueueFull(unittest.TestCase):
    """The worker's two 503s, told apart by its message, with no new field."""

    def call_with(self, body):
        import urllib.error

        def urlopen(request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 503, "busy", {}, io.BytesIO(body))

        with mock.patch.object(worker_client.urllib.request, "urlopen", urlopen), \
                public_app().test_request_context():
            worker_client.create_run({}, {}, owner="o", url="http://worker.test", token="t")

    def test_queue_full_is_busy_and_anything_else_is_paid_off(self):
        from deploy import sweep_worker
        self.assertEqual(worker_client.QUEUE_FULL, sweep_worker.QUEUE_FULL)
        with self.assertRaises(worker_client.QueueFull):
            self.call_with(b'{"error": {"message": "queue_full"}}')
        for other in (b'{"error": {"message": "paid sweeps are temporarily unavailable"}}',
                      b"", b"not json"):
            with self.subTest(other), self.assertRaises(worker_client.PaidUnavailable):
                self.call_with(other)
        self.assertFalse(issubclass(worker_client.QueueFull, worker_client.PaidUnavailable))


# ============================================================== privacy
class TestPrivacy(unittest.TestCase):
    """What the audit log and the health check may never carry."""

    RESUME = "RESUME-SECRET-TEXT Ada Okonkwo, 12 Quiet Lane"
    GUESS = "not-the-code-SECRET-GUESS"

    def test_audit_lines_and_health_carry_no_secret_and_no_resume(self):
        lines = []

        class Sink(logging.Handler):
            def emit(self, record):
                lines.append(record.getMessage())

        sink = Sink()
        public.AUDIT.addHandler(sink)
        try:
            with mock.patch.dict(os.environ, {"SWEEP_WORKER_TOKEN": "WORKER-TOKEN-SECRET"}):
                failing = public_app(extract=lambda p: self.RESUME, derive=lambda t, p: (
                    _ for _ in ()).throw(local_profile.Escalated(["role_keywords: none"])))
                client = failing.test_client()
                client.post("/beta", data={"code": self.GUESS})
                client.post("/beta", data={"code": CODE})
                upload(client)
                client.post("/derive")
                reader = public_app(extract=None)
                rc = unlocked(reader)
                post_pdf(rc, pdf(ACCENTS))
                post_pdf(rc, pdf()[:200])
                runner = public_app(fetch_plan=free_plan, start_sweep=lambda p: FakeRun())
                sc = unlocked(runner)
                ready_for_run(sc)
                sc.post("/run")
                health = json.dumps([a.test_client().get("/healthz").get_json()
                                     for a in (failing, reader, runner)])
        finally:
            public.AUDIT.removeHandler(sink)
        text = "\n".join(lines)
        for event in ("beta", "parse", "derive", "run"):
            self.assertIn(f'"event": "{event}"', text)
        records = [json.loads(line) for line in lines]
        self.assertTrue(all(set(r) <= {"event", "route", "session", "ip", "outcome",
                                       "category", "bytes", "ms", "run"} for r in records))
        sids = [cookie(failing, client)["sid"], cookie(runner, sc)["sid"]]
        for secret in (self.RESUME, "Okonkwo", "Quiet Lane", "Résumé", "Café",
                       self.GUESS, CODE, "WORKER-TOKEN-SECRET", "test-secret",
                       "Authorization", "Bearer", "apify", "127.0.0.1", "TRACKS",
                       "skill_weights", "beta_grant", *sids):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, text)
                self.assertNotIn(secret, health)

    def test_the_same_visitor_correlates_and_different_ones_do_not(self):
        app = public_app()
        with app.test_request_context():
            a, b = public.pseudonym("ip", "203.0.113.5"), public.pseudonym("ip", "203.0.113.6")
            self.assertEqual(a, public.pseudonym("ip", "203.0.113.5"))
        self.assertNotEqual(a, b)
        self.assertRegex(a, r"^[0-9a-f]{12}$")


class TestHealth(unittest.TestCase):

    def test_aggregates_only(self):
        app = public_app(fetch_plan=free_plan, start_sweep=lambda p: FakeRun())
        client = unlocked(app)
        ready_for_run(client)
        client.post("/run")
        body = app.test_client().get("/healthz").get_json()
        self.assertEqual({k: body[k] for k in ("access", "session_rooms", "derivations_today",
                                               "runs_today", "parses_in_flight")},
                         {"access": "locked", "session_rooms": 1, "derivations_today": 1,
                          "runs_today": 1, "parses_in_flight": 0})
        self.assertFalse(any(isinstance(v, (dict, list)) for v in body.values()))


if __name__ == "__main__":
    unittest.main()
