"""D7C item 8: one sweep across the public app for what must never leave it.

Every public GET route is fetched after a visitor has been through the journey, and its HTML and its headers are searched for:
every secret in this process's environment (by NAME in a failure, never by value: this suite loads the real .env, so a value in a
message would be a leak of its own), absolute paths of this machine, stack-trace text, and the module names of the reading's
internals. Then what ownership means (a second browser gets none of the first one's data), and that rows from an engine and
fields from a visitor are escaped. The deeper suites keep their own ground (test_public_hardening, test_public_guardrails,
test_estimate_isolation, test_worker_link); this is the net across all of it. No model, provider or network.
"""
import copy
import html
import os
import re
import tempfile
import unittest
from unittest import mock

from sweep import app as app_module
from sweep import public
from sweep.tests.test_app import DERIVED
from sweep.tests.test_public import PDF, public_app, unlocked, upload
from sweep.tests.test_results_ui import legacy_app, page, row

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SECRET_NAME = re.compile(r"(TOKEN|SECRET|PASSWORD|API_?KEY|APIKEY|CREDENTIAL|PRIVATE)", re.I)
SYNTHETIC = {"SWEEP_WORKER_TOKEN": "wtok_SYNTHETICSECRET0123456789", "APIFY_TOKEN": "apify_api_SYNTHETICSECRET0123456789",
             "SWEEP_FEEDBACK_API_KEY": "re_SYNTHETICSECRET0123456789"}
INTERNAL_TEXT = ("Traceback (most recent call last)", "site-packages", 'File "/', "skill_scan.widen", "local_profile._notes",
                 "make_profile.widen_skills", "years_experience COMPUTED", "role_gate_rejected")


class Quiet(unittest.TestCase):
    def fail_if(self, cond, msg):
        if cond:
            self.fail(msg)


def secrets_in_environment():
    """name -> value for every environment variable that looks like a credential and is long enough to be one."""
    return {k: v for k, v in os.environ.items() if SECRET_NAME.search(k) and len(v) >= 12}


def paths():
    out = {REPO, tempfile.gettempdir(), "/Users/", "/private/var/", "/srv/", "/opt/sweep-worker"}
    return {p.rstrip("/") + ("/" if p.endswith("/") else "") for p in out if p}


def leaks(blob):
    """What of this blob must not be in it, named without its value."""
    found = [f"env:{k}" for k, v in secrets_in_environment().items() if v in blob]
    found += [f"path:{p}" for p in paths() if p in blob]
    found += [f"text:{t}" for t in INTERNAL_TEXT if t in blob]
    return found


def get_routes(app):
    """Every public GET route that needs no argument."""
    out = []
    for rule in app.url_map.iter_rules():
        if "GET" in rule.methods and not rule.arguments and rule.endpoint in public.PUBLIC_ENDPOINTS | {
                "upload", "review", "key", "configure", "confirm", "running", "results", "profile_done", "profile_download",
                "progress", "activity", "beta_gate", "healthz"}:
            out.append(str(rule.rule))
    return sorted(set(out))


class EveryPublicRoute(Quiet):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, SYNTHETIC)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app = public_app(derive=lambda t, p: {**copy.deepcopy(DERIVED), "field_summary": "React Native developer — 4 years, 9 skills."})
        self.client = unlocked(self.app)
        upload(self.client, name="ada.pdf")
        self.client.post("/derive")
        self.client.post("/review", data={"name": "ada"})

    def test_no_secret_path_or_internal_text_in_any_page_or_header(self):
        self.assertGreaterEqual(len(get_routes(self.app)), 8, "the sweep must actually cover the app")
        for path in get_routes(self.app):
            with self.subTest(path):
                r = self.client.get(path, follow_redirects=True)
                headers = "\n".join(f"{k}: {v}" for k, v in r.headers.items())
                found = leaks(r.get_data(as_text=True)) + [f"header:{f}" for f in leaks(headers)]
                self.fail_if(found, f"{path} carries {found}")
        r = self.client.get("/definitely-not-a-route")
        self.fail_if(leaks(r.get_data(as_text=True)), "the 404 page")

    def test_the_synthetic_secrets_are_really_in_the_process(self):
        for name, value in SYNTHETIC.items():
            self.assertEqual(os.environ.get(name), value)       # the sweep above would be meaningless if they were not

    def test_a_second_browser_gets_nothing_of_the_firsts(self):
        stranger = unlocked(self.app)
        for path in ("/review", "/profile", "/profile.py", "/results", "/progress", "/running", "/export.csv", "/export.xlsx",
                     "/export.json", "/confirm", "/configure"):
            with self.subTest(path):
                r = stranger.get(path, follow_redirects=True)
                body = r.get_data(as_text=True)
                self.fail_if("React Native developer" in body, f"{path} shows the first browser's reading")

    def test_the_visitors_key_is_never_echoed_back(self):
        key = "apify_api_VISITORKEYSYNTHETIC0123456789"
        with mock.patch.object(app_module, "check_token", create=True):
            self.client.post("/key", data={"token": key})
        for path in get_routes(self.app):
            body = self.client.get(path, follow_redirects=True).get_data(as_text=True)
            self.fail_if(key in body, f"{path} echoes a key that was submitted")


class Escaping(Quiet):
    def test_rows_from_an_engine_and_fields_from_a_visitor_come_out_as_text(self):
        hostile = row(1, title='<img src=x onerror=alert(1)>', where='"><script>alert(2)</script>', skills='<b>x</b>,y')
        hostile["company"] = "</td><script>alert(3)</script>"
        body = page(legacy_app([hostile], public=True), '/results?q=%3Cscript%3Ealert(4)%3C/script%3E&source=%22%3E%3Cb%3E')
        for raw in ("<img src=x", "<script>alert(", "<b>x</b>", "</td><script"):
            self.fail_if(raw in body, f"unescaped: {raw}")
        self.assertIn("&lt;", body)

    def test_an_apply_link_that_is_not_http_is_never_a_link(self):
        for bad in ("javascript:alert(1)", "data:text/html,<script>alert(1)</script>", "vbscript:x"):
            body = page(legacy_app([row(1, url=bad)], public=True))
            self.fail_if(re.search(r'href="(javascript|data|vbscript):', body, re.I), f"{bad} became a link")


class UploadsAreNotKept(Quiet):
    def test_the_pdf_leaves_no_trace_on_disk_after_the_read(self):
        before = set(os.listdir(tempfile.gettempdir()))
        app = public_app()
        client = unlocked(app)
        upload(client, name="PRIVATE-NAME-MARKER.pdf", body=PDF + b" private-bytes-marker")
        left = [f for f in set(os.listdir(tempfile.gettempdir())) - before if "PRIVATE-NAME-MARKER" in f]
        self.assertEqual(left, [], "no file named after the upload is left in the temp directory")
        body = client.get("/review", follow_redirects=True).get_data(as_text=True)
        self.fail_if("private-bytes-marker" in body, "the file's bytes are never shown")


if __name__ == "__main__":
    unittest.main()
