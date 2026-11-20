"""The résumé setup's batch upload: one to three PDFs chosen together.

POST /resume takes up to as many files as the setup has room for and makes
each a track of its own, in the order chosen, one file at a time through the
same checks, parse count and one-child reader as a lone upload. Nothing is
derived by the upload: each résumé is then read by the model on its own,
through /derive, and the review screen goes on to the next. A file refused
is named and leaves the others as they are; more files than there is room
for is refused before any is read.

The P4-U1 harness throughout (sealed env, the real worker on loopback, the
real engine dry run at Confirm); the model and the parser are the persona
fixtures, except in RealReader, which runs public mode's own child reader
over PDFs made here. No model, provider or external network.
"""
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest import mock

from sweep import app as app_module
from sweep import public, safe_pdf, worker_link
from sweep.tests import test_multi_render as r1
from sweep.tests import test_multi_setup as u1
from sweep.tests.test_public_guardrails import LINE, OPEN, pdf as real_pdf

COOKIE, LABEL, RECORD, TEXT, fixed_ids = u1.COOKIE, u1.LABEL, u1.RECORD, u1.TEXT, u1.fixed_ids
# Found before any test seals the environment's PATH.
NODE = shutil.which("node")

make_profile = r1.make_profile
setUpModule, tearDownModule = r1.setUpModule, r1.tearDownModule

NAMES = {"ada": "Default.pdf", "bhaskar": "MERN.pdf", "chen": "AI.pdf"}


def part(who, name=None):
    """One file of the upload: a persona's PDF (the harness's extract reads
    the persona back out of it), or raw bytes."""
    body = who if isinstance(who, bytes) else b"%PDF-1.7 " + who.encode()
    return (io.BytesIO(body), name or NAMES.get(who, f"{who}.pdf"))


class Batch(u1.Setup):
    """The setup on, with a parser that can also refuse a file as malformed."""

    def setUp(self):
        super().setUp()

        def reading():
            with open(self.extracted[-1], "rb") as fh:
                if fh.read().endswith(b"broken"):
                    raise safe_pdf.Unreadable("malformed")
        self.while_reading = reading

    def send(self, *parts, client=None):
        return (client or self.client).post(
            "/resume", data={"resume": [part(*p) if isinstance(p, tuple) else part(p)
                                        for p in parts]},
            content_type="multipart/form-data")

    def page(self, client=None):
        return (client or self.client).get("/").get_data(as_text=True)

    def taken(self):
        return [limit.taken() for limit in self.app.upload_limits]

    def report(self, body):
        box = re.search(r'<div class="error" role="alert">(.*?)</div>', body, re.S)
        return re.findall(r"<li>(.*?)</li>", box.group(1)) if box else []

    def browser(self):
        other = self.app.test_client()
        other.post("/beta", data={"code": r1.CODE})
        return other

    @contextlib.contextmanager
    def as_browser(self, client):
        mine, self.client = self.client, client
        try:
            yield
        finally:
            self.client = mine


# ===========================================================================
class Contract(Batch):
    """Items 1-3, 13, 16-18: what one batch makes."""

    def test_three_at_once_are_three_tracks_in_the_order_chosen(self):
        # Ids whose sorted order is not the upload order.
        ids = ["cccccccccccccccc", "aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"]
        with fixed_ids(*ids):
            r = self.send("ada", "bhaskar", "chen")
        self.assertEqual((r.status_code, r.headers["Location"]), (302, f"/review?track={ids[0]}"))
        tracks = self.tracks()
        self.assertEqual(self.ids(), ids)
        self.assertEqual([t["resume_name"] for t in tracks], ["Default.pdf", "MERN.pdf", "AI.pdf"])
        self.assertEqual([t["resume_text"] for t in tracks],
                         [TEXT["ada"], TEXT["bhaskar"], TEXT["chen"]])
        self.assertEqual([t["name"] for t in tracks], ["Résumé 1", "Résumé 2", "Résumé 3"])
        for t in tracks:
            self.assertEqual(set(t), RECORD)
            self.assertEqual((t["selected"], t["reviewed"], t["renamed"], t["derived"],
                              t["engine"]), (True, False, False, None, None))
        self.assertEqual(self.room()["track_ids_issued"], ids)
        # Read one at a time in that order; nothing derived, no derivation
        # counted, one parse counted per file exactly as three lone uploads.
        self.assertEqual(len(self.extracted), 3)
        self.assertEqual(self.derived_texts, [])
        self.assertEqual(self.app.beta_limit.taken(), 0)
        self.assertEqual(self.taken(), [3, 3, 3])

    def test_every_id_is_fresh_and_a_deleted_one_never_returns(self):
        self.send("ada", "bhaskar")
        real = self.ids()
        self.assertEqual(len(set(real)), 2)
        for tid in real:
            self.assertTrue(make_profile.TRACK_ID.fullmatch(tid))
        self.act(real[0], "remove")
        with fixed_ids("1111111111111111", "1111111111111111", "2222222222222222"):
            self.send("chen", "ada")
            self.act("1111111111111111", "remove")
            self.send(("ada", "again.pdf"))
        self.assertEqual(self.ids(), [real[1], "2222222222222222"])
        self.assertEqual(self.room()["track_ids_issued"],
                         real + ["1111111111111111", "2222222222222222"])

    def test_one_file_is_exactly_a_lone_upload(self):
        other = self.browser()
        with fixed_ids("a1b2c3d4e5f60718", "a1b2c3d4e5f60718"):
            lone = self.upload("ada", name="Default.pdf")
            batch = self.send("ada", client=other)
        self.assertEqual((lone.status_code, lone.headers["Location"]),
                         (batch.status_code, batch.headers["Location"]))
        self.assertEqual(self.room()["tracks"], self.room(client=other)["tracks"])
        # And its refusals are the lone upload's own sentences and statuses.
        for parts, status, sentence in (
                (((b"GIF89a", "a.pdf"),), 400, "That file is not a PDF. Export your résumé as a PDF and try again."),
                ((("blank", "a.pdf"),), 400, "That PDF has no text in it — it is probably a scan. Export a text PDF and try again."),
                ((("broken", "a.pdf"),), 400, safe_pdf.MESSAGES.get("malformed", safe_pdf._UNREADABLE)),
                ((("ada", "again.pdf"),), 400, "That résumé is already here.")):
            with self.subTest(sentence):
                r = self.send(*parts)
                self.assertEqual(r.status_code, status)
                body = r.get_data(as_text=True)
                self.assertIn(f'<p class="error">{sentence}</p>', body)
                self.assertEqual(self.report(body), [])
        self.assertEqual(len(self.tracks()), 1)

    def test_an_empty_upload_is_refused(self):
        r = self.client.post("/resume", data={"resume": [(io.BytesIO(b""), "")]},
                             content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Choose a PDF to upload.", r.get_data(as_text=True))

    def test_the_uploaded_bytes_are_never_kept(self):
        self.send("ada", "bhaskar", "chen")
        room, jar = self.room(), self.cookie()
        blob = json.dumps(room, default=repr)
        self.assertNotIn("%PDF", blob)

        def walk(value):
            self.assertNotIsInstance(value, (bytes, bytearray, io.IOBase))
            for item in (value.values() if isinstance(value, dict)
                         else value if isinstance(value, (list, tuple)) else ()):
                walk(item)
        walk(room)
        self.assertLessEqual(set(jar), COOKIE)
        self.assertNotIn("%PDF", json.dumps(jar, default=repr))
        self.assertNotIn("Default.pdf", json.dumps(jar, default=repr))


class Room(Batch):
    """Items 4-6, 15: never more than three, existing ones included."""

    def test_more_than_the_room_left_is_refused_before_any_is_read(self):
        for existing, chosen, sentence in (
                (0, 4, "This search has room for 3 more résumés, and you chose 4. Choose up to 3 and try again."),
                (1, 3, "This search has room for 2 more résumés, and you chose 3. Choose up to 2 and try again."),
                (2, 2, "This search has room for 1 more résumé, and you chose 2. Choose one and try again."),
                (3, 2, "You have 3 résumés here, which is the most one search takes. Remove one to add another."),
                (3, 1, "You have 3 résumés here, which is the most one search takes. Remove one to add another.")):
            with self.subTest(existing=existing, chosen=chosen):
                client = self.browser()
                with self.as_browser(client):
                    if existing:
                        self.assertEqual(self.send(*["ada", "bhaskar", "chen"][:existing]).status_code, 302)
                    before, read, counted = self.ids(), len(self.extracted), self.taken()
                    r = self.send(*[f"extra{i}" for i in range(chosen)])
                    self.assertEqual(r.status_code, 400)
                    self.assertIn(sentence, r.get_data(as_text=True))
                    self.assertEqual(self.ids(), before)
                    self.assertEqual(len(self.extracted), read, "a file was read")
                    self.assertEqual(self.taken(), counted, "a parse was counted")

    def test_the_room_left_takes_that_many(self):
        a = self.add("ada")
        self.send("bhaskar", "chen")
        self.assertEqual(len(self.ids()), 3)
        self.assertEqual(self.ids()[0], a)
        self.assertEqual([t["resume_text"] for t in self.tracks()],
                         [TEXT["ada"], TEXT["bhaskar"], TEXT["chen"]])
        other = self.browser()
        with self.as_browser(other):
            self.send("ada", "bhaskar")
            self.assertEqual(self.send("chen").status_code, 302)
            self.assertEqual(len(self.ids()), 3)

    def test_a_double_submit_makes_no_second_copy(self):
        self.assertEqual(self.send("ada", "bhaskar", "chen").status_code, 302)
        read = len(self.extracted)
        again = self.send("ada", "bhaskar", "chen")                 # refresh, or Back and resend
        self.assertEqual(again.status_code, 400)
        self.assertEqual(len(self.extracted), read)                 # refused before reading
        self.assertEqual(len(self.ids()), 3)
        # Two copies of one batch at the same moment, from one browser.
        other = self.browser()
        self.room(client=other)                     # its session made, then shared
        twin = self.app.test_client()
        twin.set_cookie("session", other.get_cookie("session").value)
        gate = threading.Barrier(2)
        answers = []

        def post(client):
            gate.wait()
            answers.append(self.send("ada", "bhaskar", "chen", client=client).status_code)
        threads = [threading.Thread(target=post, args=(c,)) for c in (other, twin)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        tracks = self.room(client=other)["tracks"]
        self.assertEqual(sorted(t["resume_text"] for t in tracks),
                         sorted([TEXT["ada"], TEXT["bhaskar"], TEXT["chen"]]))
        self.assertEqual(len(self.room(client=other)["track_ids_issued"]), 3)
        self.assertEqual(len(answers), 2)


class Partial(Batch):
    """Items 7-11: a refused file is named; the others are kept."""

    def check_report(self, r, lines, tracks):
        self.assertEqual((r.status_code, r.headers["Location"]), (303, "/"))
        body = self.page()
        self.assertEqual(self.report(body), lines)
        self.assertEqual(self.report(self.page()), [], "the report is shown once")
        self.assertEqual([t["resume_text"] for t in self.tracks()], [TEXT[w] for w in tracks])
        # No phantom: every id issued is a track, and every track is whole.
        self.assertEqual(self.room()["track_ids_issued"], self.ids())
        for t in self.tracks():
            self.assertEqual(set(t), RECORD)

    def test_a_duplicate_inside_the_batch(self):
        r = self.send("ada", ("ada", "copy-of-Default.pdf"), "bhaskar")
        self.check_report(r, ["Could not add copy-of-Default.pdf. That résumé is already here.",
                              "Added 2 of 3 résumés. Review each one below."],
                          ["ada", "bhaskar"])

    def test_a_duplicate_of_one_already_here(self):
        self.upload("ada")
        r = self.send(("ada", "Ada-final.pdf"), "chen")
        self.check_report(r, ["Could not add Ada-final.pdf. That résumé is already here.",
                              "Added 1 of 2 résumés. Review it below."], ["ada", "chen"])

    def test_valid_malformed_valid(self):
        r = self.send("ada", ("broken", "MERN.pdf"), "chen")
        self.check_report(r, [f"Could not add MERN.pdf. {safe_pdf._UNREADABLE}",
                              "Added 2 of 3 résumés. Review each one below."],
                          ["ada", "chen"])

    def test_not_a_pdf_and_no_text_are_named_too(self):
        r = self.send((b"GIF89a", "photo.pdf"), "bhaskar", ("blank", "scan.pdf"))
        self.check_report(r, [
            "Could not add photo.pdf. That file is not a PDF. Export your résumé as a PDF and try again.",
            "Could not add scan.pdf. That PDF has no text in it — it is probably a scan. Export a text PDF and try again.",
            "Added 1 of 3 résumés. Review it below."], ["bhaskar"])
        # A non-PDF is never parsed and never counted, as alone.
        self.assertEqual(self.taken(), [2, 2, 2])

    def test_a_quota_refusal_partway_keeps_what_came_before(self):
        self.app.upload_limits[2].per_ip = 2            # this session: two an hour
        r = self.send("ada", "bhaskar", "chen")
        self.check_report(r, [
            "Could not add AI.pdf. You have uploaded 2 résumés in the last hour. Try again in a little while.",
            "Added 2 of 3 résumés. Review each one below."], ["ada", "bhaskar"])
        self.assertEqual(len(self.extracted), 2)        # the third was never read
        self.assertEqual(self.taken(), [2, 2, 2])       # and its refusal gave the IP slots back

    def test_all_refused_is_one_answer_and_nothing_added(self):
        r = self.send((b"GIF89a", "a.pdf"), ("broken", "b.pdf"))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.report(r.get_data(as_text=True)), [
            "Could not add a.pdf. That file is not a PDF. Export your résumé as a PDF and try again.",
            f"Could not add b.pdf. {safe_pdf._UNREADABLE}"])
        self.assertEqual(self.tracks(), [])
        self.assertNotIn("track_ids_issued", self.room())

    def test_a_refusal_leaves_the_successful_ones_selection_alone(self):
        a = self.add("ada")
        self.act(a, "deselect")
        self.send("bhaskar", ("broken", "b.pdf"))
        self.assertEqual([t["selected"] for t in self.tracks()], [False, True])

    def test_file_names_are_escaped(self):
        evil = '<img src=x onerror=alert(1)>.pdf'
        self.send(("ada", evil), (b"GIF89a", "<b>bold<b>.pdf"))
        body = self.page()
        self.assertNotIn("<img src=x", body)
        self.assertNotIn("<b>bold", body)
        self.assertIn("Could not add &lt;b&gt;bold&lt;b&gt;.pdf.", body)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;.pdf", body)


class Planning(Batch):
    """Item 12: the batch changes a plan exactly as adding one by one does."""

    def planned_one(self, client):
        with self.as_browser(client):
            self.add("ada")
            self.client.post("/key/free")
            self.client.post("/configure", data=r1.FORMS["india"])
            self.confirm()

    def test_the_same_as_adding_them_one_by_one(self):
        one_by_one, batch = self.browser(), self.browser()
        for client in (one_by_one, batch):
            self.planned_one(client)
        before = json.dumps(self.room(client=batch), sort_keys=True, default=repr)
        # Refused outright (too many, or none readable): nothing changes.
        self.send("bhaskar", "chen", "extra", client=batch)
        self.send((b"GIF89a", "x.pdf"), ("broken", "y.pdf"), client=batch)
        self.assertEqual(json.dumps(self.room(client=batch), sort_keys=True, default=repr), before)
        with fixed_ids("1111111111111111", "2222222222222222",
                       "1111111111111111", "2222222222222222"):
            with self.as_browser(one_by_one):
                self.upload("bhaskar", name="MERN.pdf")
                self.upload("chen", name="AI.pdf")
            self.send("bhaskar", "chen", client=batch)

        def seen(client):
            room = dict(self.room(client=client))
            room["plan_cache"] = dict(room["plan_cache"], at="<when it was cached>")
            first = room["tracks"][0]["id"]
            text = json.dumps(room, sort_keys=True, default=repr)
            return text.replace(first, "<first>")
        self.assertEqual(seen(batch), seen(one_by_one))
        self.assertIsNone(self.room(client=batch).get(worker_link.PLANNED))


class Screens(Batch):
    """Items 7-11, 29, 31: what each state of the front door offers."""

    def front(self):
        body = self.page()
        picker = re.search(r'<input type="file"[^>]*>', body).group(0)
        heading = re.search(r"<h2>(Add [^<]*)</h2>", body)
        return body, picker, heading and heading.group(1).split()

    def test_A_to_G(self):
        for n, whos, heading, room in (
                ("A", (), "Add up to 3 résumés", 3),
                ("E", ("ada",), "Add up to 2 more résumés", 2),
                ("F", ("ada", "bhaskar"), "Add another résumé", 1),
                ("G", ("ada", "bhaskar", "chen"), None, 0)):
            with self.subTest(n), self.as_browser(self.browser()):
                if whos:
                    self.send(*whos)
                body = self.page()
                if room == 0:
                    self.assertNotIn('<input type="file"', body)
                    self.assertIn("A search takes up to 3 résumés. Remove", " ".join(body.split()))
                    continue
                _, picker, words = self.front()
                self.assertEqual(" ".join(words), heading)
                if room > 1:
                    self.assertIn(" multiple", picker)
                    self.assertIn(f'x-data="sweepPicker({room}, 15)"', body)
                    self.assertIn(f"Drop up to {room} résumés here, or click to choose PDFs", body)
                    self.assertIn("PDFs only, up to 15 MB in total.", body)
                    self.assertIn('<script src="/static/pick.js"></script>', body)
                    self.assertIn("'Read ' + files.length + ' résumés' : 'Read my résumé'", body)
                    self.assertIn(":aria-label=\"'Remove ' + f.name\"", body)
                    self.assertNotIn("Replace file", body)
                else:
                    # One place left: the one-file picker, Replace file and all.
                    self.assertNotIn("multiple", picker)
                    self.assertNotIn("pick.js", body)
                    self.assertIn("Drop your résumé here, or click to choose a PDF", body)
                    self.assertIn("Replace file", body)
                # The server-rendered button is right before any script runs.
                self.assertIn(">Read my résumé</button>", body)
                for t in self.tracks():
                    for control in (f'value="{t["id"]}"', "Leave out", ">Remove<span", "Rename"):
                        self.assertIn(control, body)

    def test_the_picker_script_is_served_and_its_tests_pass(self):
        self.assertEqual(self.client.get("/static/pick.js").status_code, 200)
        if not NODE:
            self.skipTest("node not installed")
        script = os.path.join(os.path.dirname(__file__), "pick_test.js")
        run = subprocess.run([NODE, script], capture_output=True, text=True,
                             env={"PATH": os.path.dirname(NODE)})
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_a_413_names_the_total(self):
        app = self.app
        app.config["MAX_CONTENT_LENGTH"] = 1024
        r = self.send(("ada", "a.pdf"), (b"%PDF-1.7 " + b"x" * 4096, "b.pdf"))
        self.assertEqual(r.status_code, 413)
        self.assertIn("That upload is larger than 15 MB. Add fewer résumés at a time",
                      r.get_data(as_text=True))


class GateOff(Batch):
    """Items 14, 27: with the setup off, nothing of this exists."""

    FLAGS = u1.Dark.FLAGS

    def test_one_file_and_no_multiple(self):
        body = self.client.get("/").get_data(as_text=True)
        self.assertNotIn("multiple", re.search(r'<input type="file"[^>]*>', body).group(0))
        self.assertNotIn("pick.js", body)
        self.assertIn("Replace file", body)
        self.assertIn("Drop your résumé here, or click to choose a PDF", body)
        # Two files posted anyway: the first is the résumé, as it always was.
        r = self.client.post("/resume", data={"resume": [part("ada"), part("bhaskar")]},
                             content_type="multipart/form-data")
        self.assertEqual((r.status_code, r.headers["Location"]), (302, "/review"))
        room = self.room()
        self.assertEqual(room["resume_text"], TEXT["ada"])
        self.assertNotIn("tracks", room)
        self.assertEqual(self.extracted[-1:], self.extracted)    # read once


class Flow(Batch):
    """Items 11-12, 32: select A/B/C together, then read and review each in
    turn without uploading again, and plan them in that order."""

    def test_a_b_c(self):
        ids = ["cccccccccccccccc", "aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"]
        with fixed_ids(*ids):
            first = self.send("ada", "bhaskar", "chen").headers["Location"]
        a, b, c = ids
        self.assertEqual(first, f"/review?track={a}")
        listed = self.page()
        for n, label in enumerate(["Résumé 1", "Résumé 2", "Résumé 3"], 1):
            # A row: its place, the name that can be changed (here the
            # placeholder, so the file stands in for it in the heading), its
            # state. The rename field still carries the name.
            self.assertIn(f'<span class="rank" aria-hidden="true">{n:02d}</span>', listed)
            self.assertIn(f'<h2 id="resume-{n}"', listed)
            self.assertIn(f'<input name="name" value="{label}"', listed)
        self.assertEqual(listed.count("Not read yet"), 3)
        uploads = self.taken()
        for tid, who, then in ((a, "ada", "/review"),
                               (b, "bhaskar", "/review"),
                               (c, "chen", "/key")):
            with self.subTest(who):
                # The unified page, next in line (its no-script form reads it).
                reading = self.client.get(f"/review?track={tid}").get_data(as_text=True)
                self.assertIn(f'action="/derive?track={tid}"', reading)
                self.assertEqual(self.client.post(f"/derive?track={tid}").status_code, 302)
                self.assertEqual(self.derived_texts[-1], TEXT[who])
                page = self.client.get(f"/review?track={tid}").get_data(as_text=True)
                # The next one is not read yet, so this saves; the last goes on.
                self.assertIn(("Save and continue to job search" if tid == c
                               else f"Save résumé {ids.index(tid) + 1}"), page)
                r = self.client.post(f"/review?track={tid}", data={})
                self.assertEqual(r.headers["Location"], then)
        # One derivation each, one at a time, in upload order; no upload again.
        self.assertEqual(self.derived_texts, [TEXT["ada"], TEXT["bhaskar"], TEXT["chen"]])
        self.assertEqual(self.app.beta_limit.taken(), 3)
        self.assertEqual(self.taken(), uploads)
        self.assertEqual([t["name"] for t in self.tracks()],
                         [LABEL["ada"], LABEL["bhaskar"], LABEL["chen"]])
        self.assertEqual(self.client.post("/key/free").status_code, 302)
        self.assertEqual(self.client.post("/configure", data=r1.FORMS["india"]).status_code, 303)
        self.confirm()
        plan = self.last_plan()
        self.assertEqual(sorted(plan), ["free_only", "owner", "prefs", "tracks"])
        self.assertEqual([t["id"] for t in plan["tracks"]], ids)
        self.assertEqual(self.planned()["snapshot"]["track_ids"], ids)


# ===========================================================================
class RealReader(unittest.TestCase):
    """Public mode's own reader over a batch: its child, one at a time,
    counted per file, every temp file gone."""

    def app(self):
        home = tempfile.mkdtemp(prefix="batch-")
        env = mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin", "HOME": home,
                                           worker_link.MULTI_FLAG: "1"}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(shutil.rmtree, home, ignore_errors=True)
        from sweep.tests.test_public import public_app
        return public_app(env_extra=OPEN, extract=None)

    def test_one_child_at_a_time_counted_each_and_nothing_left(self):
        app = self.app()
        client = app.test_client()
        made, real_mkstemp = [], tempfile.mkstemp
        live, peak, real_run = [0], [0], safe_pdf._run_child

        def mkstemp(*a, **kw):
            made.append(real_mkstemp(*a, **kw))
            return made[-1]

        def run_child(*a):
            live[0] += 1
            peak[0] = max(peak[0], live[0])
            try:
                return real_run(*a)
            finally:
                live[0] -= 1

        bodies = [real_pdf(b"BT /F1 10 Tf 50 700 Td (" + who + b" engineer) Tj ET\n")
                  for who in (b"Alpha", b"Bravo", b"Charlie")]
        cut = real_pdf(LINE)[:200]                          # malformed: read, refused
        with mock.patch.object(app_module.tempfile, "mkstemp", mkstemp), \
                mock.patch.object(safe_pdf, "_run_child", run_child):
            r = client.post("/resume", data={"resume": [
                (io.BytesIO(body), f"{n}.pdf") for n, body in enumerate(
                    [bodies[0], cut, bodies[1]])]}, content_type="multipart/form-data")
            self.assertEqual(r.status_code, 303)
            r = client.post("/resume", data={"resume": [(io.BytesIO(bodies[2]), "c.pdf")]},
                            content_type="multipart/form-data")
            self.assertEqual(r.status_code, 302)
        room = app.session_store._rooms[
            app.session_interface.get_signing_serializer(app).loads(
                client.get_cookie("session").value)["sid"]]["data"]
        self.assertEqual([t["resume_text"].split()[0] for t in room["tracks"]],
                         ["Alpha", "Bravo", "Charlie"])
        self.assertEqual(peak[0], 1)
        self.assertEqual(safe_pdf.in_flight(), 0)
        self.assertEqual([lim.taken() for lim in app.upload_limits], [4, 4, 4])
        self.assertEqual(len(made), 4)
        for _handle, path in made:
            self.assertFalse(os.path.exists(path), path)


if __name__ == "__main__":
    unittest.main()
