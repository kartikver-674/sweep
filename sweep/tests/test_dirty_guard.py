"""D7C blocker 5: unsaved résumé edits are never lost without a choice.

dirty.js (behaviour: dirty_test.js, run below against a stand-in page; the real browsers run the same flows in
docs/design/motion-d7b/harness) decides when the editor is dirty (a control differs from the value it was served with),
and asks with a native dialog before anything that would take the page away. What these pin is the markup and the contract
around it: the editor form is marked, the dialog is there with its accessible name and its two answers, outside the form
(a dialog form cannot nest in one) and outside <main>, nothing is drawn where there is no editor, and the script does not
move focus or scroll. No model, provider or network.
"""
import os
import re
import shutil
import subprocess
import unittest

from sweep import app as app_module
from sweep.tests import test_app
from sweep.tests.test_public import public_app, unlocked, upload

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "static", "dirty.js")
NODE = shutil.which("node")


def guard_parts(body):
    """(dialog markup or None, whether the editor form is marked, whether dirty.js is loaded)."""
    dialog = re.search(r'<dialog id="leave-guard".*?</dialog>', body, re.S)
    return (dialog.group(0) if dialog else None,
            bool(re.search(r"<form[^>]*\bdata-editor\b", body)),
            "static/dirty.js" in body)


class Quiet(unittest.TestCase):
    def has(self, needle, hay, msg=""):
        if needle not in hay:
            self.fail(msg or f"missing: {needle!r}")

    def lacks(self, needle, hay, msg=""):
        if needle in hay:
            self.fail(msg or f"found: {needle!r}")


class TheScriptBehaves(Quiet):
    @unittest.skipUnless(NODE, "node is not installed")
    def test_the_guard_against_a_stand_in_page(self):
        run = subprocess.run([NODE, os.path.join(HERE, "dirty_test.js")], capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stdout[-1500:] + run.stderr[-500:])
        self.has("all ok", run.stdout)

    def test_it_never_moves_focus_except_to_hand_it_back_and_never_scrolls(self):
        src = open(SCRIPT, encoding="utf-8").read()
        code = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
        for banned in ("scrollTo", "scrollIntoView", "scrollBy", ".blur(", "localStorage", "sessionStorage", "fetch(", "XMLHttpRequest"):
            self.lacks(banned, code, banned)
        self.assertEqual(code.count(".focus("), 1, "one call: to give focus back to what was pressed")
        self.has("p.trigger.focus()", code)

    def test_the_dirty_test_is_the_forms_own_defaults_not_a_snapshot(self):
        code = re.sub(r"/\*.*?\*/", "", open(SCRIPT, encoding="utf-8").read(), flags=re.S)
        for name in ("defaultValue", "defaultChecked", "defaultSelected"):
            self.has(name, code)
        self.lacks("FormData", code, "no snapshot taken at some moment that may be the wrong one")


class TheMarkup(Quiet):
    def public_single(self):
        client = unlocked(public_app())
        upload(client)
        client.post("/derive")
        return client.get("/review").get_data(as_text=True)

    def console_single(self):
        app = app_module.create_app(state={"resume_text": "x", "derived": dict(test_app.DERIVED)}, derive=lambda t, p: test_app.DERIVED)
        app.config["TESTING"] = True
        return app.test_client().get("/review").get_data(as_text=True)

    def test_a_single_résumé_editor_is_guarded_in_public_and_on_the_console(self):
        for who, body in (("public", self.public_single()), ("console", self.console_single())):
            with self.subTest(who):
                dialog, marked, loaded = guard_parts(body)
                self.assertTrue(dialog and marked and loaded, (bool(dialog), marked, loaded))
                self.has('role="alertdialog"', dialog)
                self.has('aria-labelledby="leave-guard-title"', dialog)
                self.has('aria-describedby="leave-guard-text"', dialog)
                self.has('id="leave-guard-title"', dialog)
                self.has('id="leave-guard-text"', dialog)
                self.has('<form method="dialog">', dialog)
                self.has('<button class="primary" value="stay" autofocus>Stay and keep editing</button>', dialog)
                self.has('<button class="secondary" value="leave">Discard changes and leave</button>', dialog)
                self.has("You have unsaved changes", dialog)

    def test_the_dialog_is_outside_the_page_and_outside_the_editors_form(self):
        body = self.public_single()
        self.assertGreater(body.index('<dialog id="leave-guard"'), body.index("</main>"), "after <main>, not in it")
        form = re.search(r"<form[^>]*\bdata-editor\b.*?</form>", body, re.S).group(0)
        self.lacks("leave-guard", form, "a form cannot nest in another")
        self.assertEqual(body.count('id="leave-guard"'), 1)
        self.assertEqual(body.count("static/dirty.js"), 1)

    def test_only_the_editor_form_is_marked_and_there_is_one(self):
        body = self.public_single()
        self.assertEqual(len(re.findall(r"<form[^>]*\bdata-editor\b", body)), 1)

    def test_other_screens_carry_no_guard(self):
        client = unlocked(public_app())
        for path in ("/", "/key", "/beta", "/feedback"):
            body = client.get(path, follow_redirects=True).get_data(as_text=True)
            self.assertEqual(guard_parts(body), (None, False, False), path)

    def test_the_script_is_served(self):
        client = unlocked(public_app())
        r = client.get("/static/dirty.js")
        self.assertEqual(r.status_code, 200)
        self.has("form[data-editor]", r.get_data(as_text=True))
        r.close()


if __name__ == "__main__":
    unittest.main()
