"""D4.1: pricing a candidate never touches the saved session.

POST /estimate prices a preferences form the user has not saved. It used to do
that by swapping the candidate into the LIVE session dict, pricing, and
restoring a snapshot taken a moment earlier. Two requests in one session (two
tabs, two quick edits, an edit and a Save) interleave on that dict: the second
snapshot is the first request's candidate, and the last restore writes it back
over whatever the session held, a Save included.

The rule these tests hold: an estimate is a read-only projection. While it
runs, and after it finishes, the session holds exactly what was saved.

Nothing here is left to timing. The pricing call (fetch_plan) and the profile
write a Save makes are stubs that stop on an Event until the test lets them go,
so every interleaving is the one the test names. Every case runs on the
console's one plain dict and on a public visitor's session room; the
Multi-Track approval has its own class at the end. No model, provider or
network beyond the loopback worker the Multi-Track harness already uses.
"""

import copy
import threading
import time
import unittest
from unittest import mock

from sweep import app as app_module
from sweep import worker_client, worker_link
from sweep.tests.test_app import DERIVED, RAW_PLAN
from sweep.tests.test_multi_setup import Setup
from sweep.tests.test_public import public_app, unlocked
from sweep.tests.test_public_guardrails import FakeRun, cookie, free_plan, ready_for_run

WAIT = 10
SAVED = {"max_age_days": 14, "max_results": 10}


class Pricer:
    """A fetch_plan that can be held open. Only calls made from a thread named
    "est..." stop; every other caller (a screen rendering, the setup) is not
    held. `calls` records, in the order they started, what state each call saw
    when it was asked to price."""

    def __init__(self, plan):
        self.plan, self.calls, self.app, self.boom = plan, [], None, None
        self._lock = threading.Lock()

    def __call__(self, profile):
        seen = {"age": self.app.state.get("max_age_days"),
                "results": self.app.state.get("max_results"),
                "in": threading.Event(), "go": threading.Event()}
        if threading.current_thread().name.startswith("est"):
            with self._lock:
                self.calls.append(seen)
            seen["in"].set()
            if not seen["go"].wait(WAIT):
                raise AssertionError("the test never released this pricing call")
        if self.boom:
            raise self.boom
        return self.plan(profile)

    def wait(self, k):
        """Until the k-th held call is inside the pricer."""
        deadline = time.monotonic() + WAIT
        while len(self.calls) <= k:
            if time.monotonic() > deadline:
                raise AssertionError(f"pricing call {k} never started")
            time.sleep(0.002)
        assert self.calls[k]["in"].wait(WAIT)

    def release(self, k):
        self.calls[k]["go"].set()

    def release_all(self):
        for call in self.calls:
            call["go"].set()


def in_thread(fn, name):
    box = {}

    def target():
        try:
            box["r"] = fn()
        except BaseException as exc:          # handed back to the test thread
            box["e"] = exc

    thread = threading.Thread(target=target, name=name, daemon=True)
    thread.start()
    return thread, box


def finish(running):
    thread, box = running
    thread.join(WAIT)
    if thread.is_alive():
        raise AssertionError("a request never finished")
    if "e" in box:
        raise box["e"]
    return box["r"]


class Cases:
    """The cases, for any way of holding a session. A subclass says how to
    build the app, how to open another tab on the same session, and where the
    session's dict lives."""

    def setUp(self):
        self.pricer = Pricer(self.plan)
        self.app, self.client = self.build()
        self.pricer.app = self.app
        self.addCleanup(self.pricer.release_all)
        self.save(max_age_days="14", max_results="10")

    # -- gestures --------------------------------------------------------------
    def save(self, tab=None, **form):
        answer = (tab or self.client).post("/configure", data=form)
        self.assertEqual(answer.status_code, 303, answer.get_data(as_text=True)[:300])
        return answer

    def estimate(self, tab=None, **form):
        return (tab or self.tab()).post("/estimate", json=form)

    def estimating(self, name="est", **form):
        """An estimate in flight: a thread that will stop inside the pricer."""
        tab = self.tab()
        return in_thread(lambda: self.estimate(tab, **form), name)

    def saving(self, **form):
        """A Save that will stop while it writes the profile, before it has
        applied anything."""
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
        return gate, in_thread(lambda: self.save(tab, **form), "save")

    def kept(self):
        state = self.state()
        return {key: state.get(key) for key in SAVED}

    def everything(self):
        return copy.deepcopy(dict(self.state()))

    # -- 1 ---------------------------------------------------------------------
    def test_an_ordinary_estimate_leaves_the_saved_session_exactly_as_it_was(self):
        self.client.get("/configure")
        before = self.everything()
        answer = self.estimate(max_age_days="7", max_results="5")
        self.assertEqual(answer.status_code, 200, answer.get_data(as_text=True)[:300])
        self.assertEqual(self.kept(), SAVED)
        self.assertEqual(self.everything(), before)

    def test_while_an_estimate_is_pricing_the_session_still_holds_what_was_saved(self):
        running = self.estimating(max_age_days="7")
        self.pricer.wait(0)
        self.assertEqual(self.pricer.calls[0]["age"], 7, "it did not price the candidate")
        self.assertEqual(self.kept(), SAVED)
        page = self.client.get("/configure").get_data(as_text=True)
        self.assertIn('<option value="14" selected>', page)
        self.assertNotIn('<option value="7" selected>', page)
        self.pricer.release(0)
        self.assertEqual(finish(running).status_code, 200)
        self.assertEqual(self.kept(), SAVED)

    # -- 2, 3 ------------------------------------------------------------------
    def overlapping(self, first_out):
        """A (age 7, depth 5) starts; B (age 3) starts; they finish in the
        order given. Each must have been priced on what was SAVED plus its own
        edits alone: B never sees A's depth."""
        a = self.estimating("est-A", max_age_days="7", max_results="5")
        self.pricer.wait(0)
        b = self.estimating("est-B", max_age_days="3")
        self.pricer.wait(1)
        first, second = (a, b) if first_out == "A" else (b, a)
        order = (0, 1) if first_out == "A" else (1, 0)
        self.pricer.release(order[0])
        done = [finish(first)]
        self.pricer.release(order[1])
        done.append(finish(second))
        self.assertEqual([r.status_code for r in done], [200, 200])
        self.assertEqual([(c["age"], c["results"]) for c in self.pricer.calls],
                         [(7, 5), (3, 10)])
        self.assertEqual(self.kept(), SAVED)

    def test_two_overlapping_estimates_A_finishing_first(self):
        self.overlapping("A")

    def test_two_overlapping_estimates_B_finishing_first(self):
        self.overlapping("B")

    # -- 4, 5 ------------------------------------------------------------------
    def test_an_estimate_that_finishes_after_a_save_cannot_bring_back_older_preferences(self):
        running = self.estimating(max_age_days="7")
        self.pricer.wait(0)
        self.save(max_age_days="21")
        self.assertEqual(self.kept(), {"max_age_days": 21, "max_results": 10})
        self.pricer.release(0)
        self.assertEqual(finish(running).status_code, 200)
        self.assertEqual(self.kept(), {"max_age_days": 21, "max_results": 10})

    def test_a_save_that_starts_while_an_estimate_is_pending_keeps_exactly_what_it_submitted(self):
        running = self.estimating(max_age_days="7")
        self.pricer.wait(0)
        gate, saving = self.saving(max_results="9")          # built from the session as it is now
        assert gate["in"].wait(WAIT)
        self.pricer.release(0)
        self.assertEqual(finish(running).status_code, 200)
        gate["go"].set()
        finish(saving)
        # The estimate's 7 days was never saved, so it is not part of this save.
        self.assertEqual(self.kept(), {"max_age_days": 14, "max_results": 9})

    # -- 6, 7 ------------------------------------------------------------------
    def test_an_estimate_that_fails_leaves_the_session_unchanged(self):
        self.client.get("/configure")
        before = self.everything()
        self.pricer.boom = RuntimeError("the worker did not answer")
        answer = self.estimate(max_age_days="7")
        self.assertEqual(answer.status_code, 400)
        self.assertIn("could not price", answer.get_json()["error"])
        self.assertEqual(self.everything(), before)

    def test_an_estimate_that_raises_outside_the_pricer_leaves_the_session_unchanged(self):
        self.client.get("/configure")
        before = self.everything()
        with mock.patch("sweep.plan.cost", side_effect=ValueError("boom")):
            with self.assertRaises(ValueError):
                self.estimate(max_age_days="7")
        self.assertEqual(self.everything(), before)

    def test_a_refused_candidate_is_never_kept(self):
        self.client.get("/configure")
        before = self.everything()
        for form in ({"max_age_days": "soon"}, {"max_age_days": "0"},
                     {"avoid": "docker; rm -rf /"}, {"scope": "nowhere"}):
            with self.subTest(form=form):
                self.assertEqual(self.estimate(**form).status_code, 400)
                self.assertEqual(self.everything(), before)

    # -- 8 ---------------------------------------------------------------------
    def test_the_estimate_is_the_plan_the_saved_candidate_then_gets(self):
        # The figure a candidate is quoted is the figure Configure shows once
        # that candidate is what was saved: same pricing, same fields.
        quoted = self.estimate(max_age_days="7", max_results="5").get_json()
        self.save(max_age_days="7", max_results="5")
        self.client.get("/configure")
        self.assertEqual(quoted, self.state()["plan"])
        self.assertEqual(self.estimate(max_age_days="7", max_results="5").get_json(), quoted)

    def test_an_empty_form_prices_the_saved_preferences(self):
        quoted = self.estimate().get_json()
        self.client.get("/configure")
        self.assertEqual(quoted, self.state()["plan"])
        self.assertEqual(self.pricer.calls, [], "only estimates are held")

    # -- 10 --------------------------------------------------------------------
    def test_two_tabs_on_one_session_cannot_corrupt_the_saved_configuration(self):
        for first_out in ("A", "B"):
            with self.subTest(first_out=first_out):
                self.pricer.calls.clear()
                tab_a = self.estimating("est-A", max_age_days="7", max_results="5")
                self.pricer.wait(0)
                tab_b = self.estimating("est-B", max_age_days="3")
                self.pricer.wait(1)
                self.save(max_age_days="30")                 # tab B's explicit Save
                order = (0, 1) if first_out == "A" else (1, 0)
                for k in order:
                    self.pricer.release(k)
                    finish((tab_a, tab_b)[k])
                self.assertEqual(self.kept(), {"max_age_days": 30, "max_results": 10})
                self.save(max_age_days="14")


class TestConsole(Cases, unittest.TestCase):
    """The operator's console: one plain dict, every tab shares it."""

    plan = staticmethod(lambda profile: dict(RAW_PLAN))

    def build(self):
        app = app_module.create_app(
            state={"profile": "kabir", "cap_usd": 8.41, "derived": DERIVED},
            extract=lambda p: "x", derive=lambda t, p: DERIVED,
            check_token=lambda t: (8.41, None), fetch_plan=self.pricer)
        app.config.update(TESTING=True)
        app.write_profile = lambda name, source: None
        return app, app.test_client()

    def state(self):
        return self.app.state

    def tab(self):
        return self.app.test_client()


class TestPublic(Cases, unittest.TestCase):
    """A public visitor: their own room in the session store, and a second tab
    is another client carrying the same cookie."""

    plan = staticmethod(free_plan)

    def build(self):
        app = public_app(fetch_plan=self.pricer, start_sweep=lambda p: FakeRun())
        client = unlocked(app)
        ready_for_run(client)
        return app, client

    def state(self):
        return self.app.session_store._rooms[cookie(self.app, self.client)["sid"]]["data"]

    def tab(self):
        other = self.app.test_client()
        other.set_cookie("session", self.client.get_cookie("session").value)
        return other

    def test_an_estimate_does_not_replace_the_screens_cached_plan(self):
        self.client.get("/configure")
        cached, plan, raw = (copy.deepcopy(self.state().get(k)) for k in
                             ("plan_cache", "plan", "raw_plan"))
        self.assertIsNotNone(cached)
        asked = len(self.pricer.calls)
        self.assertEqual(self.estimate(max_age_days="3").status_code, 200)
        state = self.state()
        self.assertEqual((state.get("plan_cache"), state.get("plan"), state.get("raw_plan")),
                         (cached, plan, raw))
        self.assertEqual(asked, len(self.pricer.calls))

    def test_an_estimate_does_not_rewrite_the_profile_the_visitor_can_download(self):
        self.client.get("/configure")                        # the committed render
        source = self.state().get("profile_source")
        self.assertTrue(source)
        self.estimate(max_age_days="3")
        self.assertEqual(self.state().get("profile_source"), source)


class TestMultiTrack(Setup):
    """A Multi-Track estimate plans its candidate on a copy. The approval the
    session holds is neither replaced by one for an unsaved candidate nor
    brought back after a Save dropped it."""

    def gate_plans(self):
        real = worker_client.plan_tracks
        self.inside, self.release = threading.Event(), threading.Event()

        def gated(*args, **kw):
            if threading.current_thread().name == "est":
                self.inside.set()
                assert self.release.wait(WAIT), "the test never released the plan"
            return real(*args, **kw)

        patch = mock.patch.object(worker_client, "plan_tracks", gated)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.release.set)

    def test_an_estimate_leaves_the_approval_and_everything_else_as_it_was(self):
        self.free("ada", "bhaskar")
        self.confirm()
        approval, before = self.planned(), copy.deepcopy(self.room())
        answer = self.client.post("/estimate", json={"scope": "remote", "max_age_days": "3"})
        self.assertEqual(answer.status_code, 200, answer.get_data(as_text=True)[:300])
        self.assertIs(self.planned(), approval)
        self.assertEqual(self.room(), before)

    def test_a_late_estimate_cannot_bring_back_an_approval_a_save_dropped(self):
        self.free("ada", "bhaskar")
        self.confirm()
        self.assertIsNotNone(self.planned())
        self.gate_plans()
        tab = self.app.test_client()
        tab.set_cookie("session", self.client.get_cookie("session").value)
        running = in_thread(lambda: tab.post("/estimate", json={"scope": "remote"}), "est")
        self.assertTrue(self.inside.wait(WAIT))
        self.assertEqual(self.client.post("/configure", data={"max_age_days": "21"}).status_code, 303)
        self.assertIsNone(self.planned(), "a changed Save must drop the approval")
        after_save = copy.deepcopy(self.room())
        self.release.set()
        self.assertEqual(finish(running).status_code, 200)
        self.assertIsNone(self.planned(), "the estimate put the old approval back")
        self.assertEqual(self.room(), after_save, "the estimate changed what the Save left")
        self.assertEqual(self.room()["max_age_days"], 21)
        self.assertNotEqual(self.room().get("scope"), "remote")


if __name__ == "__main__":
    unittest.main()
