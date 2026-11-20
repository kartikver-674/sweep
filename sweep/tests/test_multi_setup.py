"""Multi-Track Phase 4 (P4-U1): the 1-3 résumé setup, end to end.

Upload up to three résumés, each read (derived) and reviewed on its own, with
a server-made id and a label that is presentation only; include, leave out,
reorder, rename or remove them; one Configure for the Sweep. One selected
résumé is the one-résumé Sweep (schema 1, exactly the legacy requests); two or
three are P4-R1's Multi-Track Sweep, planned at Confirm from one snapshot.
Every change a plan was built from drops that plan's approval; a label, an
unselected résumé or a look at a screen does not.

Everything runs for real except the model and the providers: the Render
public app through its own routes, the actual worker_client over loopback to
the real worker app, the real engine's dry run (sockets refused) for every
plan. Extraction and derivation are the committed persona fixtures; no run
child starts. The environment is sealed and synthetic.
"""
import copy
import io
import json
import os
import re
import unittest
from unittest import mock

from sweep import app as app_module
from sweep import logic, public, worker_client, worker_link
from sweep.tests import test_multi_render as r1
from sweep.tests.test_one_track_goldens import derived_for
from sweep.tests.test_worker_link import render_app

make_profile = r1.make_profile
setUpModule, tearDownModule = r1.setUpModule, r1.tearDownModule

PERSONA = {"ada": "ada-plain", "bhaskar": "bhaskar-plain", "chen": "chen-plain"}
TEXT = {"ada": r1.TEXTS[r1.A], "bhaskar": r1.TEXTS[r1.B], "chen": r1.TEXTS[r1.C]}
LABEL = {"ada": "Backend Engineer", "bhaskar": "Full Stack Web Developer",
         "chen": "Platform Engineer"}
RECORD = {"id", "name", "renamed", "resume_name", "resume_text", "derived", "engine",
          "reviewed", "selected"}
COOKIE = {"sid", "beta_grant", "run_id", "run_tracks", "run_plan_hash", "_permanent"}
ENGINE_WORDS = ("SEARCH", "SCORING", "POSITIONING", "ALIGNMENT", "skill_weights",
                "penalty_terms", "TRACKS")
# A review that edits: one weight moved, one term dropped, experience set.
EDIT = {"term": ["celery", "django"], "weight": ["4", "3"], "drop": ["django"],
        "experience_years": "4", "experience_months": "2"}


def pdf(who, name=None):
    return {"resume": (io.BytesIO(b"%PDF-1.7 " + who.encode()), name or f"{who}-cv.pdf")}


class Setup(r1.Harness):
    """A Render public process with the setup on, and the loopback worker."""

    FLAGS = dict(r1.Harness.FLAGS, **{public.PER_IP_ENV: "50"})

    def render(self):
        self.derived_texts, self.failing, self.while_reading = [], set(), None

        def extract(path):
            with open(path, "rb") as fh:
                who = fh.read()[len(b"%PDF-1.7 "):].decode()
            self.extracted.append(path)
            if self.while_reading:
                self.while_reading()
            return {"blank": "  ", **TEXT}.get(who, who)

        def derive(text, prefs):
            self.derived_texts.append(text)
            if text in self.failing:
                raise RuntimeError("the model did not answer")
            who = next(k for k, v in TEXT.items() if v == text)
            return copy.deepcopy(derived_for(PERSONA[who]))

        self.extracted = []
        return render_app(self.worker.url, check_token=lambda token: (42.0, None),
                          extract=extract, derive=derive)

    # -- the visitor's gestures ------------------------------------------------
    def upload(self, who, **kw):
        return self.client.post("/resume", data=pdf(who, **kw),
                                content_type="multipart/form-data")

    def tracks(self):
        return self.room().get("tracks") or []

    def ids(self):
        return [t["id"] for t in self.tracks()]

    def track(self, tid):
        return next(t for t in self.tracks() if t["id"] == tid)

    def act(self, tid, do, **form):
        return self.client.post("/tracks", data=dict(form, track=tid, do=do))

    def read_and_review(self, tid, **form):
        self.assertEqual(self.client.post(f"/derive?track={tid}").status_code, 302)
        return self.client.post(f"/review?track={tid}", data=form)

    def add(self, who, **form):
        """Upload, read and review one résumé; its id."""
        self.assertEqual(self.upload(who).status_code, 302)
        tid = self.ids()[-1]
        self.assertEqual(self.read_and_review(tid, **form).status_code, 302)
        return tid

    def free(self, *whos, form="india"):
        """A reviewed setup of these résumés on the free path, configured."""
        ids = [self.add(who) for who in whos]
        self.assertEqual(self.client.post("/key/free").status_code, 302)
        self.assertEqual(self.client.post("/configure", data=r1.FORMS[form]).status_code, 303)
        return ids

    def confirm(self):
        """The plan screen: since T2 Configure and Confirm are one public screen, and GET /configure is what plans."""
        answer = self.client.get("/configure")
        self.assertEqual(answer.status_code, 200, answer.get_data(as_text=True)[-600:])
        return answer.get_data(as_text=True)

    def planned(self):
        return self.room().get(worker_link.PLANNED)

    def last_plan(self):
        return self.worker.bodies("/v1/plans")[-1]


def fixed_ids(*ids):
    """new_track_id, answering these in turn."""
    return mock.patch.object(app_module, "new_track_id", side_effect=list(ids))


# ===========================================================================
class Dark(Setup):
    """Off, the setup does not exist: no track, no control, no route."""

    FLAGS = dict(r1.RENDER_FLAGS, **{public.PER_IP_ENV: "50"})

    def test_off_nothing_of_the_setup_exists(self):
        page = self.client.get("/").get_data(as_text=True)
        self.upload("ada")
        self.client.post("/derive")
        self.client.post("/review", data={})
        self.client.post("/key/free")
        self.client.get("/configure")
        self.client.post("/run")
        room = self.room()
        self.assertFalse({"tracks", "track_ids_issued"} & set(room))
        self.assertEqual(room["resume_text"], TEXT["ada"])
        for body in (page, self.client.get("/").get_data(as_text=True),
                     self.client.get("/review").get_data(as_text=True)):
            for word in ("track_action", "Your résumés", "name=\"track\"", "?track="):
                self.assertNotIn(word, body)
        self.assertEqual(self.client.post("/tracks", data={"do": "remove"}).status_code, 404)
        self.assertEqual(self.worker.bodies("/v1/runs")[-1].keys(),
                         {"profile", "prefs", "free_only", "owner"})


class Record(Setup):
    """Items 4-10: the canonical record, its id and its label."""

    def test_an_upload_is_one_canonical_record(self):
        with fixed_ids("a1b2c3d4e5f60718"):
            self.assertEqual(self.upload("ada").headers["Location"], "/review?track=a1b2c3d4e5f60718")
        track, = self.tracks()
        self.assertEqual(set(track), RECORD)
        self.assertEqual((track["id"], track["name"], track["renamed"], track["resume_name"],
                          track["resume_text"], track["derived"], track["engine"],
                          track["reviewed"], track["selected"]),
                         ("a1b2c3d4e5f60718", "Résumé 1", False, "ada-cv.pdf", TEXT["ada"],
                          None, None, False, True))
        self.client.post("/derive?track=a1b2c3d4e5f60718")
        self.assertEqual(track["derived"], derived_for("ada-plain"))
        self.assertEqual(track["engine"], r1.skill_concepts.engine_version())
        self.assertNotIn("parse", track)

    def test_ids_are_the_servers_never_the_file_or_the_person(self):
        with fixed_ids("0123456789abcdef", "fedcba9876543210"):
            self.upload("ada", name="Ada_Okonkwo_CV.pdf")
            self.upload("bhaskar", name="Ada_Okonkwo_CV.pdf")       # the same file name
        self.assertEqual(self.ids(), ["0123456789abcdef", "fedcba9876543210"])
        real = [app_module.new_track_id() for _ in range(50)]
        self.assertEqual(len(set(real)), 50)
        for tid in real:
            self.assertRegex(tid, r"\A[0-9a-f]{16}\Z")
            self.assertTrue(make_profile.TRACK_ID.fullmatch(tid))

    def test_a_posted_id_is_never_taken(self):
        self.client.post("/resume", data=dict(pdf("ada"), id="cafecafecafecafe",
                                              track="cafecafecafecafe"),
                         content_type="multipart/form-data")
        self.assertNotIn("cafecafecafecafe", self.ids())

    def test_a_deleted_id_never_comes_back(self):
        with fixed_ids("1111111111111111", "1111111111111111", "2222222222222222"):
            self.upload("ada")
            self.act("1111111111111111", "remove")
            self.upload("bhaskar")
        self.assertEqual(self.ids(), ["2222222222222222"])
        self.assertEqual(self.room()["track_ids_issued"], ["1111111111111111", "2222222222222222"])

    def test_labels_default_to_the_first_title_until_named(self):
        a = self.add("ada")
        self.assertEqual(self.track(a)["name"], LABEL["ada"])
        self.upload("bhaskar")
        b = self.ids()[1]
        self.assertEqual(self.track(b)["name"], "Résumé 2")
        self.act(b, "rename", name="  Mobile  ")
        self.client.post(f"/derive?track={b}")
        self.assertEqual((self.track(b)["name"], self.track(b)["renamed"]), ("Mobile", True))

    def test_a_label_another_resume_has_gets_a_number(self):
        a = self.add("ada")
        self.upload("bhaskar")
        b = self.ids()[1]
        with mock.patch.dict(TEXT, bhaskar=TEXT["bhaskar"]), \
                mock.patch.dict(PERSONA, bhaskar="ada-plain"):
            self.client.post(f"/derive?track={b}")
        self.assertEqual([self.track(a)["name"], self.track(b)["name"]],
                         [LABEL["ada"], LABEL["ada"] + " (2)"])

    def test_rename_is_presentation_only_and_validated(self):
        a, b = self.free("ada", "bhaskar")
        self.confirm()
        approval = self.planned()
        before = copy.deepcopy({k: v for k, v in self.track(b).items() if k != "name"})
        self.assertEqual(self.act(b, "rename", name="My mobile CV").status_code, 303)
        self.assertEqual(self.track(b)["name"], "My mobile CV")
        self.assertEqual({k: v for k, v in self.track(b).items() if k not in ("name", "renamed")},
                         {k: v for k, v in before.items() if k != "renamed"})
        self.assertIs(self.planned(), approval)                  # still approved
        for bad in ("", "   ", "x" * 41, "tab\there", "new\nline"):
            with self.subTest(name=bad):
                self.assertEqual(self.act(b, "rename", name=bad).status_code, 400)
                self.assertEqual(self.track(b)["name"], "My mobile CV")
        self.client.post("/run")
        body, = self.worker.bodies("/v1/runs")
        self.assertEqual([t["id"] for t in body["tracks"]], [a, b])
        self.assertEqual(body["expected_plan_hash"], approval["plan_hash"])
        self.assertNotIn("My mobile CV", json.dumps(self.worker.requests, default=str))
        self.assertEqual(self.cookie()["run_tracks"], [[a, LABEL["ada"]], [b, "My mobile CV"]])


class MaximumThree(Setup):
    """Item 7."""

    def test_a_fourth_resume_is_refused_and_changes_nothing(self):
        for who in ("ada", "bhaskar", "chen"):
            self.upload(who)
        before = copy.deepcopy(self.room())
        seen = len(self.extracted)
        answer = self.upload("dana")
        self.assertEqual(answer.status_code, 400)
        self.assertIn("Remove one", answer.get_data(as_text=True))
        self.assertEqual(len(self.extracted), seen)              # refused before it was read
        self.assertEqual(self.room(), before)
        page = self.client.get("/").get_data(as_text=True)
        self.assertNotIn('action="/resume"', page)
        self.assertIn("3 of 3", page)

    def test_an_upload_racing_to_the_third_slot_is_refused_after_reading(self):
        self.upload("ada")
        self.upload("bhaskar")
        room = self.room()

        def another_lands():                 # a third upload, finished meanwhile
            room["tracks"].append(dict(copy.deepcopy(room["tracks"][0]),
                                       id="9" * 16, resume_text="another"))
        self.while_reading = another_lands
        answer = self.upload("chen")
        self.assertEqual(answer.status_code, 400)
        self.assertEqual([t["resume_text"] for t in room["tracks"]],
                         [TEXT["ada"], TEXT["bhaskar"], "another"])


class UploadSafety(Setup):
    """Items 8, 11, 12: the one-résumé upload's checks, a track at a time."""

    def test_the_same_checks_refuse_and_the_others_stay(self):
        self.add("ada")
        self.upload("bhaskar")
        before = copy.deepcopy(self.tracks())
        for label, data, status in (
                ("no file", {}, 400),
                ("not a pdf", {"resume": (io.BytesIO(b"hello"), "cv.pdf")}, 400),
                ("a scan", pdf("blank"), 400),
                ("the same résumé again", pdf("ada"), 400)):
            with self.subTest(label):
                answer = self.client.post("/resume", data=data, content_type="multipart/form-data")
                self.assertEqual(answer.status_code, status)
                self.assertEqual(self.tracks(), before)
        self.assertTrue(self.extracted)
        for path in self.extracted:                      # nothing kept on disk
            self.assertFalse(os.path.exists(path))

    def test_a_failed_read_marks_only_its_own_track(self):
        a = self.add("ada")
        self.upload("bhaskar")
        b = self.ids()[1]
        before = copy.deepcopy(self.track(a))
        self.failing.add(TEXT["bhaskar"])
        self.assertEqual(self.client.post(f"/derive?track={b}").status_code, 502)
        self.assertEqual(self.track(b)["parse"]["state"], "failed")
        self.assertIsNone(self.track(b)["derived"])
        self.assertEqual(self.track(a), before)
        # Two résumés share one review page: B's card says it could not be
        # read, and A is still there to review.
        page = self.client.get(f"/review?track={b}")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Couldn't finish reading this résumé.", page.get_data(as_text=True))
        self.assertEqual(self.client.get(f"/review?track={a}").status_code, 200)
        self.failing.clear()
        self.assertEqual(self.client.post(f"/derive?track={b}").status_code, 302)
        self.assertEqual(self.track(b)["derived"], derived_for("bhaskar-plain"))


class OneResume(Setup):
    """Items 9, 13, 33: the setup on, one résumé — exactly the legacy Sweep."""

    def flow(self, paid):
        self.upload("ada")
        self.client.post("/derive")                      # the legacy forms, no id
        self.client.post("/review", data=EDIT)
        if paid:
            self.client.post("/key", data={"token": r1.KEY})
        else:
            self.client.post("/key/free")
        self.client.post("/configure", data=r1.FORMS["india"])
        self.client.get("/confirm")
        self.client.post("/run", data={"over_cap_ack": "1"})
        run_id = self.cookie()["run_id"]
        self.settled(run_id)
        for path in ("/running", "/progress", "/results", "/export.csv"):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        return self.captured()

    def captured(self):
        ids = {}

        def norm(text):
            for tok in re.findall(r"[0-9a-f]{64}|[0-9a-f]{32}|[0-9a-f]{16}", text):
                ids.setdefault(tok, f"<{len(ids)}>")
                text = text.replace(tok, ids[tok])
            return text
        return {"worker": [[q["method"], norm(q["path"]), norm(q["body"].decode())]
                           for q in self.worker.requests],
                "cookie": sorted(self.cookie()),
                "spawned": [sorted(s) for s in self.worker.spawned],
                "dry_runs": ["schema 2" if "TRACKS = [" in p["source"] else "schema 1"
                             for p in self.worker.engine.plans]}

    def golden(self, paid):
        on = self.flow(paid)
        self.assertEqual(len(self.tracks()), 1)
        self.assertNotIn(worker_link.PLANNED, self.room())
        os.environ.pop(worker_link.MULTI_FLAG)             # the same flow, the product off
        self.worker.requests.clear()
        self.worker.spawned.clear()
        self.worker.engine.plans.clear()
        self.app = self.render()
        self.client = self.app.test_client()
        self.client.post("/beta", data={"code": r1.CODE})
        off = self.flow(paid)
        self.assertNotIn("tracks", self.room())
        self.assertEqual(on, off)
        self.assertEqual(set(on["dry_runs"]), {"schema 1"})
        for _method, path, body in on["worker"]:
            self.assertNotIn('"tracks"', body)
            self.assertNotIn("expected_plan_hash", body)

    def test_free_is_the_legacy_sweep_request_for_request(self):
        self.golden(paid=False)

    def test_paid_is_the_legacy_sweep_request_for_request(self):
        self.golden(paid=True)


class Transitions(Setup):
    """Items 10, 11, 12, 14-16, 35, 36, 40, 41."""

    def one_resume(self, *, deselect=False, remove=False):
        """What a session holding only Ada, reviewed with EDIT, plans: the
        one-résumé reference."""
        other = self.__class__(self._testMethodName)
        other.setUp()
        try:
            other.add("ada", **EDIT)
            other.client.post("/key/free")
            other.client.post("/configure", data=r1.FORMS["india"])
            other.confirm()
            return other.track(other.ids()[0])["derived"], other.last_plan()
        finally:
            other.doCleanups()              # this test's own worker and env again

    def test_one_then_two_keeps_the_first_as_it_was_and_plans_schema_2(self):
        a = self.add("ada", **EDIT)
        self.client.post("/key/free")
        self.client.post("/configure", data=r1.FORMS["india"])
        self.confirm()
        self.assertIn("profile", self.last_plan())
        first = copy.deepcopy(self.track(a))
        b = self.add("bhaskar")
        self.assertNotEqual(a, b)
        self.assertEqual(self.track(a), first)                     # edits, label, selection
        self.assertEqual(self.derived_texts.count(TEXT["ada"]), 1)  # never read again
        self.assertEqual(self.room()["scope"], "india")            # the Sweep's own preferences
        self.confirm()
        plan = self.last_plan()
        self.assertEqual(sorted(plan), ["free_only", "owner", "prefs", "tracks"])
        self.assertEqual([t["id"] for t in plan["tracks"]], [a, b])
        self.assertEqual(self.planned()["snapshot"]["track_ids"], [a, b])

    def check_back_to_one(self, gesture):
        a, b = self.free("ada", "bhaskar")
        self.client.post(f"/review?track={a}", data=EDIT)
        self.confirm()
        self.assertIsNotNone(self.planned())
        gesture(b)
        self.assertIsNone(self.planned())
        derived, reference = self.one_resume()
        self.assertEqual(self.track(a)["derived"], derived)          # its edits kept
        self.confirm()
        plan = self.last_plan()
        self.assertEqual(sorted(plan), ["free_only", "owner", "prefs", "profile"])
        self.assertEqual({k: v for k, v in plan.items() if k != "owner"},
                         {k: v for k, v in reference.items() if k != "owner"})
        self.client.post("/run")
        body, = self.worker.bodies("/v1/runs")
        self.assertEqual(sorted(body), ["free_only", "owner", "prefs", "profile"])
        self.assertEqual(body["profile"], derived)
        self.assertNotIn("run_tracks", self.cookie())
        self.assertFalse(any("tracks" in json.loads(q["body"] or b"{}")
                             for q in self.worker.requests if q["method"] == "POST"
                             and q["path"] in ("/v1/runs",)))

    def test_two_to_one_by_leaving_one_out_is_the_legacy_sweep(self):
        self.check_back_to_one(lambda b: self.act(b, "deselect"))

    def test_two_to_one_by_removing_one_is_the_legacy_sweep(self):
        self.check_back_to_one(lambda b: self.act(b, "remove"))

    def test_three_reordered_and_reselected_plan_in_that_order(self):
        # Ids whose sorted order is none of the orders planned below.
        with fixed_ids("cccccccccccccccc", "aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"):
            a, b, c = self.free("ada", "bhaskar", "chen")
        self.confirm()
        self.assertEqual(self.planned()["snapshot"]["track_ids"], [a, b, c])
        labels = {t["id"]: (t["name"], t["resume_text"]) for t in self.tracks()}
        self.act(c, "up")
        self.assertIsNone(self.planned())                          # reorder: a new Sweep
        self.act(c, "up")
        self.assertEqual(self.ids(), [c, a, b])
        self.assertEqual({t["id"]: (t["name"], t["resume_text"]) for t in self.tracks()}, labels)
        self.act(b, "deselect")
        self.confirm()
        self.assertEqual([t["id"] for t in self.last_plan()["tracks"]], [c, a])
        self.act(b, "select")
        self.assertIsNone(self.planned())
        self.confirm()
        self.assertEqual([t["id"] for t in self.last_plan()["tracks"]], [c, a, b])
        self.client.post("/run")
        body, = self.worker.bodies("/v1/runs")
        self.assertEqual([t["id"] for t in body["tracks"]], [c, a, b])
        self.assertEqual([tid for tid, _ in self.cookie()["run_tracks"]], [c, a, b])

    def test_moving_past_the_ends_changes_nothing(self):
        a, b = self.free("ada", "bhaskar")
        self.act(a, "up")
        self.act(b, "down")
        self.assertEqual(self.ids(), [a, b])

    def test_three_to_two_stays_multi(self):
        a, b, c = self.free("ada", "bhaskar", "chen")
        self.act(b, "remove")
        self.confirm()
        self.assertEqual([t["id"] for t in self.last_plan()["tracks"]], [a, c])
        self.assertNotIn("derived", self.room())                 # no one-résumé profile


class Readiness(Setup):
    """Items 17, 18, 22, 23, 27."""

    # T2: publicly /confirm is only the plan screen's old address (it redirects, planning nothing), so the screens that plan
    # and start are /configure and /run.
    GUARDED = (("get", "/configure"), ("post", "/configure"), ("get", "/confirm"),
               ("post", "/run"), ("post", "/key/free"))

    def test_an_incomplete_selected_resume_reaches_nothing(self):
        self.add("ada")
        self.upload("bhaskar")                               # selected, never reviewed
        plans = len(self.worker.bodies("/v1/plans"))
        for method, path in self.GUARDED:
            with self.subTest(path=path, method=method):
                answer = getattr(self.client, method)(path, data=r1.FORMS["india"])
                self.assertEqual((answer.status_code, answer.headers.get("Location")),
                                 (302, "/configure" if path == "/confirm" else "/review"))
        # ...and the old address leads on to a guarded screen, so it too ends at the review.
        answer = self.client.get("/confirm", follow_redirects=True)
        self.assertEqual(answer.request.path, "/review")
        self.assertEqual(self.client.post("/estimate", json={"scope": "india"}).status_code, 409)
        self.assertEqual(len(self.worker.bodies("/v1/plans")), plans)
        self.nothing_started()
        # The review screen opens on the résumé that is waiting.
        self.assertIn(f"track={self.ids()[1]}", self.client.get("/review").get_data(as_text=True))

    def test_an_incomplete_unselected_resume_blocks_nothing(self):
        a = self.add("ada")
        self.upload("bhaskar")
        self.act(self.ids()[1], "deselect")
        self.client.post("/key/free")
        self.assertEqual(self.client.post("/configure", data=r1.FORMS["india"]).status_code, 303)
        self.confirm()
        self.assertEqual(self.last_plan()["profile"], self.track(a)["derived"])

    def test_nothing_selected_reaches_nothing(self):
        a = self.add("ada")
        self.act(a, "deselect")
        for method, path in self.GUARDED:
            with self.subTest(path=path):
                self.assertEqual(getattr(self.client, method)(path).status_code, 302)
        self.nothing_started()

    def test_a_review_goes_on_to_the_next_resume_waiting(self):
        self.upload("ada")
        self.upload("bhaskar")
        a, b = self.ids()
        self.client.post(f"/derive?track={a}")
        answer = self.client.post(f"/review?track={a}", data={})
        # The unified review page: open on the next one read, or waiting.
        self.assertEqual(answer.headers["Location"], "/review")
        self.client.post(f"/derive?track={b}")
        self.assertEqual(self.client.post(f"/review?track={b}", data={}).headers["Location"],
                         "/key")


class PerTrack(Setup):
    """Items 20, 21, 36 (K, L, M, V)."""

    def test_each_resume_is_read_and_reviewed_on_its_own(self):
        a = self.add("ada")
        before = copy.deepcopy(self.track(a))
        b = self.add("bhaskar", term=["css"], weight=["5"])
        self.assertEqual(self.track(a), before)
        self.assertEqual(self.track(b)["derived"]["skill_weights"][0], {"term": "css", "weight": 5})
        self.assertEqual(self.track(a)["derived"], derived_for("ada-plain"))

    def test_a_review_edits_only_the_resume_it_names(self):
        a, b = self.free("ada", "bhaskar")
        before = copy.deepcopy(self.track(a))
        self.client.post(f"/review?track={b}", data={"term": ["css"], "weight": ["1"]})
        self.assertEqual(self.track(a), before)
        self.assertEqual(self.track(b)["derived"]["skill_weights"][0]["weight"], 1)

    def test_the_browser_cannot_post_what_the_engine_reads(self):
        a, b = self.free("ada", "bhaskar")
        self.client.post(f"/review?track={b}", data=EDIT)
        plain = copy.deepcopy(self.track(b)["derived"])
        forged = dict(EDIT, SEARCH='{"role_keywords": ["cto"]}', SCORING="{}",
                      POSITIONING="{}", ALIGNMENT="{}", tracks="[]", derived="{}",
                      role_keywords="cto", engine="v9", id="f" * 16, selected="0")
        self.client.post(f"/review?track={b}", data=forged)
        self.assertEqual(self.track(b)["derived"], plain)
        self.assertEqual((self.track(b)["id"], self.track(b)["engine"], self.track(b)["selected"]),
                         (b, self.track(a)["engine"], True))

    def test_an_id_this_session_does_not_hold_is_refused(self):
        a, b = self.free("ada", "bhaskar")
        stranger = self.app.test_client()
        stranger.post("/beta", data={"code": r1.CODE})
        stranger.post("/resume", data=pdf("chen"), content_type="multipart/form-data")
        theirs = self.room(client=stranger)["tracks"][0]["id"]
        before, calls = copy.deepcopy(self.room()), len(self.derived_texts)
        for tid in ("0" * 16, theirs, a[:-1], "", "../" + a):
            with self.subTest(tid=tid):
                for method, path, data in (
                        ("post", "/tracks", {"track": tid, "do": "remove"}),
                        ("post", "/tracks", {"track": tid, "do": "rename", "name": "x"}),
                        ("post", "/derive", {"track": tid}),
                        ("post", "/review", {"track": tid, **EDIT}),
                        ("get", f"/review?track={tid}", None)):
                    answer = getattr(self.client, method)(path, data=data)
                    self.assertEqual(answer.status_code, 404, (method, path))
        self.assertEqual(self.client.post("/tracks", data={"do": "remove"}).status_code, 404)
        self.assertEqual(self.client.post("/tracks", data={"track": a, "do": "sort"}).status_code,
                         400)
        self.assertEqual(self.room(), before)
        self.assertEqual(len(self.derived_texts), calls)
        self.assertEqual(len(self.room(client=stranger)["tracks"]), 1)

    def test_a_stale_page_never_acts_on_another_resume(self):
        a, b = self.free("ada", "bhaskar")
        self.act(a, "remove")
        before = copy.deepcopy(self.room())
        self.assertEqual(self.act(a, "deselect").status_code, 404)    # the page before it
        self.assertEqual(self.client.post(f"/review?track={a}", data=EDIT).status_code, 404)
        # One résumé left, and a change that names none: still not "that one".
        for do in ("remove", "deselect", "up"):
            self.assertEqual(self.client.post("/tracks", data={"do": do}).status_code, 404)
        self.assertEqual(self.room(), before)


class Preferences(Setup):
    """Items 20, 21, 25, 26 (N, O)."""

    def test_configure_takes_a_multi_sweep_with_the_one_form(self):
        a, b = self.free("ada", "bhaskar")
        page = self.client.get("/configure")
        self.assertEqual(page.status_code, 200)
        text = page.get_data(as_text=True)
        # T2: a Multi-Track Sweep's Configure is the plan screen like any other: its one form starts the Sweep (POST /run).
        self.assertRegex(text, r'<form class="split" method="post"\s+action="/run"')
        self.assertIn("Start Quick Sweep", text)
        self.assertNotIn("Save and review", text)
        answer = self.client.post("/configure", data=r1.FORMS["global_custom"])
        self.assertEqual((answer.status_code, answer.headers["Location"]), (303, "/configure"))
        room = self.room()
        self.assertEqual((room["max_age_days"], room["avoid"]), (7, ["php", "salesforce"]))
        for track in self.tracks():                                   # never per résumé
            self.assertEqual(set(track), RECORD)
        self.confirm()
        self.assertEqual(self.last_plan()["prefs"], worker_link._plan_prefs(room))
        bad = self.client.post("/configure", data={"scope": "india", "max_age_days": "0"})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.room()["max_age_days"], 7)

    def test_estimate_prices_a_multi_candidate_and_commits_nothing(self):
        self.free("ada", "bhaskar")
        self.confirm()
        approval, prefs = self.planned(), worker_link._plan_prefs(self.room())
        answer = self.client.post("/estimate", json={"scope": "remote"})
        self.assertEqual(answer.status_code, 200, answer.get_data(as_text=True))
        self.assertEqual(self.last_plan()["prefs"]["work_scope"], logic._SCOPE["remote"]["work_scope"])
        self.assertIs(self.planned(), approval)
        self.assertEqual(worker_link._plan_prefs(self.room()), prefs)

    def test_confirm_names_the_resumes_being_planned_and_nothing_else(self):
        a, b = self.free("ada", "bhaskar")
        self.act(b, "rename", name="Mobile CV")
        page = self.confirm()
        self.assertLess(page.index(LABEL["ada"]), page.index("Mobile CV"))
        tracks = self.planned()["snapshot"]["tracks"]
        for word in ENGINE_WORDS + ("no job titles", TEXT["ada"][:30], "celery", "bazel"):
            self.assertNotIn(word, page)
        for entry in tracks:
            self.assertNotIn(json.dumps(entry)[:40], page)
        self.assertIn("Start Quick Sweep", page)


class Invalidation(Setup):
    """Items 19, 23-25, 29 (D, E, F, G, U): the matrix, exactly."""

    def planned_three(self, free=True):
        ids = self.free("ada", "bhaskar", "chen")
        self.act(ids[2], "deselect")                   # C: unselected, reviewed
        self.confirm()
        self.assertIsNotNone(self.planned())
        return ids

    def test_what_changes_the_sweep_drops_its_approval(self):
        cases = {
            "add a résumé": lambda a, b, c: (self.act(c, "remove"), self.upload("chen2")),
            "remove a selected résumé": lambda a, b, c: self.act(b, "remove"),
            "leave one out": lambda a, b, c: self.act(b, "deselect"),
            "put one in": lambda a, b, c: self.act(c, "select"),
            "reorder": lambda a, b, c: self.act(b, "up"),
            "a selected résumé's review": lambda a, b, c: self.client.post(
                f"/review?track={a}", data=EDIT),
            "a selected résumé replaced": lambda a, b, c: (
                self.act(b, "remove"), self.upload("chen2")),
            "a preference": lambda a, b, c: self.client.post(
                "/configure", data=r1.FORMS["remote"]),
            "free or paid": lambda a, b, c: self.client.post("/key", data={"token": r1.KEY}),
        }
        TEXT["chen2"] = TEXT["chen"] + "\nAlso: Go."
        PERSONA["chen2"] = "chen-plain"
        self.addCleanup(TEXT.pop, "chen2")
        self.addCleanup(PERSONA.pop, "chen2")
        for label, gesture in cases.items():
            with self.subTest(label):
                self.setUp()
                a, b, c = self.planned_three()
                gesture(a, b, c)
                self.assertIsNone(self.planned(), label)

    def test_what_does_not_change_the_sweep_keeps_its_approval(self):
        cases = {
            "rename": lambda a, b, c: self.act(b, "rename", name="Mobile"),
            "an unselected résumé's review": lambda a, b, c: self.client.post(
                f"/review?track={c}", data=EDIT),
            "rename the unselected": lambda a, b, c: self.act(c, "rename", name="Spare"),
            "look at a review": lambda a, b, c: self.client.get(f"/review?track={b}"),
            "look around": lambda a, b, c: [self.client.get(p) for p in ("/", "/key", "/review")],
            "move the unselected between them": lambda a, b, c: self.act(c, "up"),
            "the same preferences again": lambda a, b, c: self.client.post(
                "/configure", data=r1.FORMS["india"]),
        }
        for label, gesture in cases.items():
            with self.subTest(label):
                self.setUp()
                a, b, c = self.planned_three()
                approval = self.planned()
                gesture(a, b, c)
                self.assertIs(self.planned(), approval, label)
                plans = len(self.worker.bodies("/v1/plans"))
                self.client.post("/run")
                self.assertEqual(len(self.worker.bodies("/v1/runs")), 1, label)
                # T2: the approval it kept is the plan that runs, not planned again.
                self.assertEqual(len(self.worker.bodies("/v1/plans")), plans, label)
                self.assertEqual(self.worker.bodies("/v1/runs")[0]["expected_plan_hash"], approval["plan_hash"], label)

    def test_a_dropped_approval_never_runs(self):
        """T2: a run whose approval was dropped is planned again from what the session holds now (fresh, before any guard),
        and it is THAT plan the worker is told to run — never the dropped one, which is gone."""
        a, b, c = self.planned_three()
        dropped = self.planned()
        self.act(a, "deselect")
        self.act(a, "select")                                  # back as it was
        self.assertIsNone(self.planned())
        plans = len(self.worker.bodies("/v1/plans"))
        answer = self.client.post("/run")
        self.assertEqual(answer.headers["Location"], "/running")
        self.assertEqual(len(self.worker.bodies("/v1/plans")), plans + 1)        # planned again, not run from memory
        body, = self.worker.bodies("/v1/runs")
        fresh = self.planned()
        self.assertIsNot(fresh, dropped)
        self.assertEqual(body["expected_plan_hash"], fresh["plan_hash"])
        self.assertEqual([t["id"] for t in body["tracks"]], [a, b])

    def test_a_form_that_moved_a_preference_is_planned_again_and_runs_that_plan(self):
        """T2: the plan screen's Start carries the preferences. What they changed is committed and priced again, and the
        run is that new plan (the old Confirm refused this form back to itself with nothing started)."""
        a, b, c = self.planned_three()
        approval = self.planned()
        plans = len(self.worker.bodies("/v1/plans"))
        answer = self.client.post("/run", data=r1.FORMS["remote"])
        self.assertEqual(answer.headers["Location"], "/running")
        self.assertEqual(len(self.worker.bodies("/v1/plans")), plans + 1)
        self.assertEqual(self.room()["scope"], "remote")
        body, = self.worker.bodies("/v1/runs")
        fresh = self.planned()
        self.assertIsNot(fresh, approval)
        self.assertNotEqual(fresh["snapshot"]["inputs"], approval["snapshot"]["inputs"])
        self.assertEqual(body["expected_plan_hash"], fresh["plan_hash"])
        self.assertEqual(body["prefs"]["work_scope"], logic._SCOPE["remote"]["work_scope"])

    def test_a_form_that_moved_nothing_runs_the_plan_the_screen_was_priced_with(self):
        a, b, c = self.planned_three()
        approval = self.planned()
        plans = len(self.worker.bodies("/v1/plans"))
        self.assertEqual(self.client.post("/run", data=r1.FORMS["india"]).headers["Location"], "/running")
        self.assertEqual(len(self.worker.bodies("/v1/plans")), plans)             # not planned again
        body, = self.worker.bodies("/v1/runs")
        self.assertEqual(body["expected_plan_hash"], approval["plan_hash"])

    def test_a_failed_replan_leaves_no_approval_to_run(self):
        for edited in (True, False):
            with self.subTest(edited=edited):
                self.setUp()
                a, b, c = self.planned_three()
                if edited:
                    self.client.post(f"/review?track={a}", data=EDIT)
                else:
                    self.client.post("/configure", data=r1.FORMS["remote"])
                with mock.patch.object(worker_client, "plan_tracks",
                                       side_effect=worker_client.EngineFailed("no")):
                    # costed(): a plan that fails is PlanUnavailable, the plan
                    # error page. T2: the plan screen is /configure, and a run
                    # plans again itself, so it meets the same failure.
                    self.assertEqual(self.client.get("/configure").status_code, 500)
                    self.assertIsNone(self.planned())
                    self.assertEqual(self.client.post("/run").status_code, 500)
                self.assertIsNone(self.planned())
                self.nothing_started()


class Privacy(Setup):
    """Items 27, 28, 31-33 (R, S): content stays in the room."""

    def test_pages_cookies_and_urls_carry_no_resume_content(self):
        a, b = self.free("ada", "bhaskar")
        self.act(b, "rename", name="Mobile CV")
        self.confirm()
        pages = [self.client.get(p).get_data(as_text=True)
                 for p in ("/", f"/review?track={a}", "/configure", "/confirm", "/key")]
        self.client.post("/run")
        self.settled(self.cookie()["run_id"])
        pages += [self.client.get(p).get_data(as_text=True)
                  for p in ("/running", "/progress", "/activity", "/results")]
        snapshot = self.planned()["snapshot"]
        for page in pages:
            for word in ("TRACKS", "POSITIONING", "ALIGNMENT", "resume_text", "derived_engine"):
                self.assertNotIn(word, page)
            for text in TEXT.values():
                self.assertNotIn(text[:40], page)
            self.assertNotIn(json.dumps(snapshot["tracks"][0]["SCORING"])[:60], page)
        cookie = self.cookie()
        self.assertLessEqual(set(cookie), COOKIE)
        raw = json.dumps(cookie, ensure_ascii=False)
        for text in TEXT.values():
            self.assertNotIn(text[:20], raw)
        for word in ("celery", "django", "bazel", "css", "backend engineer", "ada-cv"):
            self.assertNotIn(word, raw)
        self.assertEqual(cookie["run_tracks"], [[a, LABEL["ada"]], [b, "Mobile CV"]])
        for path in re.findall(r'(?:href|action)="([^"]+)"', "".join(pages)):
            self.assertNotRegex(path, r"Mobile|Backend|ada|bhaskar|\.pdf")

    def test_the_page_sees_one_projection(self):
        a, b = self.free("ada", "bhaskar")
        views = []
        with mock.patch.object(app_module, "render_template",
                               side_effect=lambda name, **kw: views.append(kw) or ""):
            self.client.get("/")
            self.client.get(f"/review?track={b}")
        for kw in views:
            for view in kw["tracks"] + [kw["track"]] * bool(kw["track"]):
                self.assertEqual(set(view), {"id", "label", "n", "selected", "status", "file"})
        self.assertEqual(views[1]["track"], {"id": b, "label": LABEL["bhaskar"], "n": 2,
                                             "selected": True, "status": "ready",
                                             "file": "bhaskar-cv.pdf"})


class Navigation(Setup):
    """Items 29, 30, 34, 35, 43."""

    def test_reloads_and_resubmits_never_copy_a_resume(self):
        first = self.upload("ada")
        self.assertEqual(first.status_code, 302)                     # POST-redirect-GET
        a = self.ids()[0]
        for _ in range(3):
            self.client.get(first.headers["Location"])
            self.client.get("/")
        self.assertEqual(self.upload("ada").status_code, 400)        # the form sent again
        self.assertEqual(self.ids(), [a])
        self.client.post(f"/derive?track={a}")
        self.client.post(f"/derive?track={a}")                        # a second submit
        self.assertEqual(self.derived_texts, [TEXT["ada"]])

    def test_a_restart_loses_the_setup_as_it_loses_a_resume_today(self):
        self.free("ada", "bhaskar")
        again = self.render().test_client()
        again.set_cookie("session", r1.cookie_of(self.client), domain="localhost")
        self.assertIn("Add up to 3", again.get("/").get_data(as_text=True))
        self.assertEqual(again.get("/configure").headers["Location"], "/review")
        self.assertEqual(again.get("/confirm").headers["Location"], "/configure")       # T2: the old address of the plan screen

    def test_every_control_is_a_labelled_button_or_link(self):
        self.free("ada", "bhaskar")
        page = self.client.get("/").get_data(as_text=True)
        for button in re.findall(r"<button\b[^>]*>(.*?)</button>", page, re.S):
            self.assertTrue(re.sub(r"<[^>]+>", "", button).strip(), button)
        for field in re.findall(r'<input name="name"[^>]*>', page):
            self.assertIn("Name for résumé", page[page.rindex("<label", 0, page.index(field)):
                                                   page.index(field)])
        # State is a shape and a word on each row (the review screen's own),
        # never colour alone; a résumé in the search carries no extra label.
        self.assertEqual(page.count('class="status reviewed">Reviewed<'), 2)
        self.assertNotIn("Left out", page)
        self.assertNotIn("draggable", page)


if __name__ == "__main__":
    unittest.main()
