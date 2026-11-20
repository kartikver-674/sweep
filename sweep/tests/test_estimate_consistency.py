"""D4.2: what was left after the estimate stopped writing into the session.

  commit    a Save is ONE change to the session: a snapshot taken at any moment
            sees all of it or none of it, and it applies what it changed, not
            the whole session as it looked when the Save began
  profiles  on the console an estimate prices its candidate from a scratch
            profile of its own, so two overlapping estimates cannot price one
            another's candidate, the saved profile file is never touched by one,
            and nothing is left behind when one fails

Deterministic: the pricing call, the profile write a Save makes and the dry run
stop on Events the test releases, and the snapshot test looks at the session
at every step a Save takes rather than hoping a reader lands in the gap. Fakes
only: no model, provider or network.
"""

import os
import re
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock

from sweep import app as app_module
from sweep.tests.test_app import DERIVED, RAW_PLAN
from sweep.tests.test_estimate_isolation import WAIT, Pricer, finish, in_thread
from sweep.tests.test_public import public_app, unlocked
from sweep.tests.test_public_guardrails import FakeRun, cookie, free_plan, ready_for_run

PREFS = ("scope", "locations", "linkedin_locations", "location_hints", "work_scope",
         "remote_scopes", "max_age_days", "max_results", "min_comp_usd", "avoid")
FORM_A = {"scope": "global", "max_age_days": "30", "max_results": "25",
          "min_comp_usd": "40000", "avoid": "php"}
FORM_B = {"scope": "india", "max_age_days": "7", "max_results": "5",
          "min_comp_usd": "", "avoid": ""}


def prefs_of(snapshot):
    return tuple(snapshot.get(key) for key in PREFS)


class Watched(dict):
    """A session dict that calls hook(method, "before" | "after") around every
    way of changing it, so a test can look at the session between the steps a
    commit is made of. Reading it (dict(), .copy()) is never hooked."""

    hook = staticmethod(lambda method, when: None)


def _around(name):
    real = getattr(dict, name)

    def method(self, *args, **kwargs):
        self.hook(name, "before")
        try:
            return real(self, *args, **kwargs)
        finally:
            self.hook(name, "after")
    return method


for _name in ("__setitem__", "__delitem__", "update", "clear", "pop", "popitem", "setdefault"):
    setattr(Watched, _name, _around(_name))


class Commit:
    """Every case runs on the console's plain dict and on a public visitor's room."""

    def setUp(self):
        self.pricer = Pricer(self.plan)
        self.app, self.client = self.build()
        self.pricer.app = self.app
        self.addCleanup(self.pricer.release_all)
        self.save(FORM_B)

    def save(self, form, tab=None):
        answer = (tab or self.client).post("/configure", data=form)
        self.assertEqual(answer.status_code, 303, answer.get_data(as_text=True)[:300])

    def saving(self, **form):
        """A Save that stops while it validates, after it has read the session
        and before it has applied anything."""
        gate = {"in": threading.Event(), "go": threading.Event()}
        real = self.app.write_profile

        def write(name, source):
            if threading.current_thread().name == "save":
                gate["in"].set()
                assert gate["go"].wait(WAIT), "the test never released the save"
            return real(name, source)

        self.app.write_profile = write
        self.addCleanup(gate["go"].set)
        tab = self.tab()
        return gate, in_thread(lambda: self.save(form, tab), "save")

    def test_a_snapshot_at_any_step_of_a_save_is_wholly_before_or_wholly_after(self):
        base, old = set(self.state()), prefs_of(self.state())
        seen, recording = [], []
        self.watch(lambda method, when: recording and seen.append(
            (method, when, self.app.state.copy())))
        recording.append(True)
        self.save(FORM_A)
        recording.clear()
        new = prefs_of(self.state())
        self.assertNotEqual(old, new)
        self.assertTrue(seen, "the watcher saw nothing")
        for method, when, snap in seen:
            with self.subTest(method=method, when=when):
                self.assertLessEqual(base, set(snap), "a key the session had is missing mid-save")
                self.assertIn(prefs_of(snap), (old, new), "preferences half-applied mid-save")
        # and the preferences arrived in one step
        self.assertEqual([m for m, w, _ in seen if m in ("update", "clear", "__delitem__")
                          and w == "before"], ["update"])

    def test_snapshots_hammering_a_run_of_saves_never_see_a_half_applied_one(self):
        self.save(FORM_A)
        a = prefs_of(self.state())
        self.save(FORM_B)
        b = prefs_of(self.state())
        stop, bad = threading.Event(), []

        def reader():
            while not stop.is_set():
                snap = self.app.state.copy()
                if "profile" not in snap or "derived" not in snap or prefs_of(snap) not in (a, b):
                    bad.append(snap)

        readers = [threading.Thread(target=reader, daemon=True) for _ in range(3)]
        was = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)
        try:
            for thread in readers:
                thread.start()
            for i in range(40):
                self.save((FORM_A, FORM_B)[i % 2])
        finally:
            stop.set()
            for thread in readers:
                thread.join(WAIT)
            sys.setswitchinterval(was)
        self.assertEqual(bad, [])

    def test_a_save_applies_what_it_changed_and_not_the_session_it_saw(self):
        gate, saving = self.saving(max_results="9")
        assert gate["in"].wait(WAIT)
        # meanwhile another request saves a different preference and adds a key
        self.state()["max_age_days"] = 21
        self.state()["marker"] = "written by another request"
        gate["go"].set()
        finish(saving)
        state = self.state()
        self.assertEqual((state["max_results"], state["max_age_days"]), (9, 21))
        self.assertEqual(state["marker"], "written by another request")

    def test_a_refused_save_changes_no_preference(self):
        # (the refusal re-renders the screen, which re-prices: the plan it leaves is not a preference)
        before = dict(self.state())
        answer = self.client.post("/configure", data={"max_age_days": "soon", "max_results": "9"})
        self.assertEqual(answer.status_code, 400)
        after = dict(self.state())
        self.assertEqual(prefs_of(after), prefs_of(before))
        self.assertEqual(set(after) - {"plan", "raw_plan", "plan_cache"},
                         set(before) - {"plan", "raw_plan", "plan_cache"})


class TestConsoleCommit(Commit, unittest.TestCase):
    plan = staticmethod(lambda profile: dict(RAW_PLAN))

    def build(self):
        self.room = Watched({"profile": "kabir", "cap_usd": 8.41, "derived": DERIVED})
        app = app_module.create_app(
            state=self.room, extract=lambda p: "x", derive=lambda t, p: DERIVED,
            check_token=lambda t: (8.41, None), fetch_plan=self.pricer)
        app.config.update(TESTING=True)
        app.write_profile = lambda name, source: None
        return app, app.test_client()

    def state(self):
        return self.app.state

    def tab(self):
        return self.app.test_client()

    def watch(self, hook):
        self.room.hook = hook


class TestPublicCommit(Commit, unittest.TestCase):
    plan = staticmethod(free_plan)

    def build(self):
        app = public_app(fetch_plan=self.pricer, start_sweep=lambda p: FakeRun())
        client = unlocked(app)
        ready_for_run(client)
        self.sid = cookie(app, client)["sid"]
        return app, client

    def state(self):
        return self.app.session_store._rooms[self.sid]["data"]

    def tab(self):
        other = self.app.test_client()
        other.set_cookie("session", self.client.get_cookie("session").value)
        return other

    def watch(self, hook):
        room = self.app.session_store._rooms[self.sid]
        room["data"] = Watched(room["data"])
        room["data"].hook = hook


# ============================================================ console profiles
class Files:
    """profiles/ as the console's engine sees it: write_profile puts a file
    there, discard_profile takes it away, and a dry run reads it."""

    def __init__(self):
        self.files, self.written, self.discarded = {}, [], []

    def write(self, name, source):
        self.files[name] = source
        self.written.append(name)

    def discard(self, name):
        self.discarded.append(name)
        self.files.pop(name, None)

    def plan(self, profile):
        """What the dry run answers: the plan of whatever the file says. A
        missing file is a dry run that failed."""
        source = self.files[profile]
        depth = re.search(r'"max_results":\s*(\d+)', source)
        depth = int(depth.group(1)) if depth else 15
        return dict(RAW_PLAN, max_results={"linkedin": depth, "indeed": depth})


class TestConsoleProfiles(unittest.TestCase):

    def setUp(self):
        self.disk = Files()
        self.pricer = Pricer(self.disk.plan)
        self.app = app_module.create_app(
            state={"profile": "kabir", "cap_usd": 8.41, "derived": DERIVED},
            extract=lambda p: "x", derive=lambda t, p: DERIVED,
            check_token=lambda t: (8.41, None), fetch_plan=self.pricer)
        self.app.config.update(TESTING=True)
        self.app.write_profile = self.disk.write
        self.app.discard_profile = self.disk.discard
        self.pricer.app = self.app
        self.addCleanup(self.pricer.release_all)
        self.client = self.app.test_client()
        self.assertEqual(self.client.post("/configure", data={
            "max_age_days": "14", "max_results": "10"}).status_code, 303)
        self.committed = self.disk.files["kabir"]
        self.saved_writes = len(self.disk.written)

    def estimate(self, **form):
        return self.app.test_client().post("/estimate", json=form)

    def estimating(self, name, **form):
        tab = self.app.test_client()
        return in_thread(lambda: tab.post("/estimate", json=form), name)

    def scratch(self):
        return [n for n in self.disk.written[self.saved_writes:] if n != "kabir"]

    def test_two_overlapping_estimates_each_price_their_own_candidate(self):
        alone = {d: self.estimate(max_results=str(d)).get_json()["total"] for d in (5, 20)}
        self.assertNotEqual(alone[5], alone[20])
        self.pricer.calls.clear()
        a = self.estimating("est-A", max_results="5")
        self.pricer.wait(0)
        b = self.estimating("est-B", max_results="20")
        self.pricer.wait(1)
        # both candidates exist at once, under different names, beside an untouched saved profile
        on_disk = [n for n in self.disk.files if n != "kabir"]
        self.assertEqual(len(on_disk), 2, on_disk)
        self.assertEqual(self.disk.files["kabir"], self.committed)
        self.pricer.release(0)
        got_a = finish(a).get_json()
        self.pricer.release(1)
        got_b = finish(b).get_json()
        self.assertEqual((got_a["total"], got_b["total"]), (alone[5], alone[20]))
        self.assertEqual(set(self.disk.files), {"kabir"}, "a scratch profile was left behind")

    def test_the_other_order_too(self):
        alone = {d: self.estimate(max_results=str(d)).get_json()["total"] for d in (5, 20)}
        self.pricer.calls.clear()
        a = self.estimating("est-A", max_results="5")
        self.pricer.wait(0)
        b = self.estimating("est-B", max_results="20")
        self.pricer.wait(1)
        self.pricer.release(1)
        got_b = finish(b).get_json()
        self.pricer.release(0)
        got_a = finish(a).get_json()
        self.assertEqual((got_a["total"], got_b["total"]), (alone[5], alone[20]))

    def test_an_estimate_never_writes_the_saved_profile(self):
        self.estimate(max_results="5", max_age_days="3")
        self.assertEqual(self.disk.files["kabir"], self.committed)
        self.assertTrue(self.scratch())
        self.assertNotIn("kabir", self.disk.written[self.saved_writes:])

    def test_the_quote_is_the_plan_the_saved_candidate_then_gets(self):
        quoted = self.estimate(max_results="5").get_json()
        self.assertEqual(quoted["profile"], "kabir", "the scratch name leaked into the quote")
        self.assertEqual(self.client.post("/configure", data={"max_results": "5"}).status_code, 303)
        self.client.get("/configure")
        self.assertEqual(quoted, self.app.state["plan"])
        self.assertIn('"max_results": 5', self.disk.files["kabir"], "a Save writes the saved profile")

    def test_an_empty_form_prices_the_saved_profile_itself(self):
        self.estimate()
        self.assertEqual(self.scratch(), [])
        self.assertEqual(self.pricer.calls, [])

    def test_a_failed_dry_run_leaves_no_scratch_profile(self):
        self.pricer.boom = RuntimeError("the engine would not import that profile")
        answer = self.estimate(max_results="5")
        self.assertEqual(answer.status_code, 400)
        self.assertTrue(self.scratch())
        self.assertEqual(set(self.disk.files), {"kabir"})
        self.assertEqual(sorted(self.disk.discarded), sorted(self.scratch()))

    def test_an_estimate_that_raises_outside_the_dry_run_leaves_none(self):
        with mock.patch("sweep.plan.cost", side_effect=ValueError("boom")):
            with self.assertRaises(ValueError):
                self.estimate(max_results="5")
        self.assertEqual(set(self.disk.files), {"kabir"})
        self.assertEqual(sorted(self.disk.discarded), sorted(self.scratch()))

    def test_a_refused_candidate_writes_no_profile_at_all(self):
        for form in ({"avoid": "docker; rm -rf /"}, {"max_age_days": "soon"}, {"scope": "nowhere"}):
            with self.subTest(form=form):
                self.assertEqual(self.estimate(**form).status_code, 400)
        self.assertEqual(self.scratch(), [])
        self.assertEqual(set(self.disk.files), {"kabir"})

    def test_the_live_sweep_reads_the_saved_profile_not_a_candidate(self):
        # POST /run re-renders the saved profile itself just before it starts
        # the engine; an estimate in flight elsewhere cannot have replaced it.
        a = self.estimating("est-A", max_results="5")
        self.pricer.wait(0)
        self.assertEqual(self.disk.files["kabir"], self.committed)
        self.pricer.release(0)
        finish(a)
        self.assertEqual(self.disk.files["kabir"], self.committed)


class TestTheProfilesDirectory(unittest.TestCase):
    """The real writer and the real discard, in a directory of their own."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="d42-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.profiles = os.path.join(self.root, "profiles")
        os.makedirs(os.path.join(self.profiles, "__pycache__"))

        def dry_run(profile):
            # a dry run is a subprocess that imports the profile: it reads the file and
            # leaves bytecode beside it
            with open(os.path.join(self.profiles, f"{profile}.py"), encoding="utf-8") as fh:
                fh.read()
            with open(os.path.join(self.profiles, "__pycache__", f"{profile}.cpython-314.pyc"), "wb") as fh:
                fh.write(b"\0")
            return dict(RAW_PLAN)

        self.app = app_module.create_app(
            state={"profile": "kabir", "cap_usd": 8.41, "derived": DERIVED},
            extract=lambda p: "x", derive=lambda t, p: DERIVED,
            check_token=lambda t: (8.41, None), fetch_plan=dry_run)
        self.app.config.update(TESTING=True)
        patch = mock.patch.object(app_module, "REPO_ROOT", self.root)
        patch.start()
        self.addCleanup(patch.stop)
        self.client = self.app.test_client()
        self.assertEqual(self.client.post("/configure", data={"max_age_days": "14"}).status_code, 303)

    def listing(self):
        return sorted(os.listdir(self.profiles)), sorted(os.listdir(os.path.join(self.profiles, "__pycache__")))

    def test_an_estimate_leaves_the_directory_as_it_found_it(self):
        before = self.listing()
        with open(os.path.join(self.profiles, "kabir.py"), encoding="utf-8") as fh:
            saved = fh.read()
        self.assertEqual(self.client.post("/estimate", json={"max_age_days": "3"}).status_code, 200)
        self.assertEqual(self.listing(), before)
        with open(os.path.join(self.profiles, "kabir.py"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), saved)

    def test_a_failed_one_does_too(self):
        before = self.listing()
        with mock.patch("sweep.plan.cost", side_effect=ValueError("boom")):
            with self.assertRaises(ValueError):
                self.client.post("/estimate", json={"max_age_days": "3"})
        self.assertEqual(self.listing(), before)

    def test_discard_only_ever_removes_a_scratch_profile(self):
        for name in ("kabir", "bigtech", "kabir_est_", "x_est_nothex0000000"):
            with open(os.path.join(self.profiles, f"{name}.py"), "w", encoding="utf-8") as fh:
                fh.write("SETTINGS = {}\n")
            self.app.discard_profile(name)
            self.assertTrue(os.path.exists(os.path.join(self.profiles, f"{name}.py")), name)
        self.app.discard_profile("../../etc/passwd")          # not a name at all: nothing happens


class TestPublicIsUnaffected(unittest.TestCase):

    def test_a_public_estimate_writes_and_discards_no_profile(self):
        pricer = Pricer(free_plan)
        app = public_app(fetch_plan=pricer, start_sweep=lambda p: FakeRun())
        pricer.app = app
        client = unlocked(app)
        ready_for_run(client)
        with mock.patch.object(app, "discard_profile") as discard:
            self.assertEqual(client.post("/estimate", json={"max_age_days": "3"}).status_code, 200)
        discard.assert_not_called()


if __name__ == "__main__":
    unittest.main()
