"""D5.1: a run's ending is the worker's word, not a count of searches.

A free sweep plans no searches, so `outstanding` is 0 for its whole life, and the
progress screen used to read that as "every search ran": a run the worker reported
as failed, stopped or timed out said "Your jobs are ready". The ending now comes
from the process's own exit (RemoteRun maps the worker's state to it), and a
timeout is named only when the worker's status says `run_timeout`. Rendered
through the same fakes as test_progress_ui; no model, provider or network.
"""

import re
import unittest
from unittest import mock

from deploy import sweep_worker
from sweep import logic, worker_client, worker_link
from sweep.tests.test_progress_ui import sweep_app, text


def app_ended(exit_code, stopped=False, timed_out=False, public=True, worker_stopped=False, **kw):
    """A run that has ended the way the worker reported it (exit code 0 is `done`).

    `stopped` is the visitor's own Stop click, remembered by this session. `worker_stopped` is the WORKER's own
    `stopped` word (RemoteRun.stopped), which survives a web restart that has forgotten the click (D7C)."""
    app = sweep_app(alive=True, public=public, **kw)
    proc = app.state["proc"]
    proc.poll = lambda: exit_code
    proc.timed_out = timed_out
    proc.stopped = worker_stopped
    if stopped:
        app.state["stopped_by_user"] = True
    return app


def progress(app):
    return app.test_client().get("/progress").get_json()


def page_of(app):
    return app.test_client().get("/running").get_data(as_text=True)


def shown_endings(page):
    """Names of the ending banners the page is served showing (not display:none)."""
    out = []
    for tag in re.findall(r'<div class="banner[^"]*"[^>]*>', page):
        name = re.search(r"p\.state === '(\w+)'", tag)
        if name and "display:none" not in tag:
            out.append(name.group(1))
    return out


def visible_banner(page):
    """The markup of the one ending banner the page is served showing."""
    parts = re.split(r'(?=<div class="banner)', page)[1:]
    shown = [b.split('<div class="split', 1)[0].split('<div class="actions"><', 1)[0] for b in parts
             if "display:none" not in b.split(">", 1)[0]]
    return shown[0] if shown else ""


def heading(page):
    return text(re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S).group(1)).strip()


class FreeEndings(unittest.TestCase):

    def test_a_free_run_that_succeeded_is_finished(self):
        app = app_ended(0, free=True)
        self.assertEqual(progress(app)["state"], "finished")
        page = page_of(app)
        self.assertEqual(heading(page), "Your jobs are ready")
        self.assertEqual(shown_endings(page), ["finished"])

    def test_a_free_run_that_failed_is_not_shown_as_finished(self):
        # the defect: outstanding is 0 for a free run, so this read "Your jobs are ready"
        app = app_ended(1, free=True)
        p = progress(app)
        self.assertEqual((p["state"], p["finished"], p["interrupted"]), ("halted", False, True))
        page = page_of(app)
        self.assertEqual(heading(page), "Sweep stopped early")
        self.assertEqual(shown_endings(page), ["halted"])
        self.assertNotIn("See the results", visible_banner(page))

    def test_a_free_failure_says_it_did_not_finish_and_names_no_cause(self):
        page = page_of(app_ended(1, free=True))
        self.assertIn(">The sweep did not finish</b>", page)
        # said as a sentence unless the run was a paid one whose plan a restart took (then the money claim is left out: charged_unknown)
        self.assertIn("It stopped before it finished, and the reason is not recorded. ' + (p.charged_unknown ? '' : 'Nothing was charged. ')", page)
        self.assertNotIn("0 of 0", text(page))
        self.assertNotIn(">The sweep ran out of time</b>", page)

    def test_a_free_run_the_user_stopped_is_stopped_not_finished(self):
        app = app_ended(1, stopped=True, free=True)
        self.assertEqual(progress(app)["state"], "stopped")
        page = page_of(app)
        self.assertEqual(heading(page), "You stopped the sweep")
        self.assertEqual(shown_endings(page), ["stopped"])
        self.assertNotIn("0 of 0", text(page))

    def test_a_stop_pressed_after_the_run_finished_does_not_undo_its_success(self):
        self.assertEqual(progress(app_ended(0, stopped=True, free=True))["state"], "finished")

    def test_a_result_the_worker_declared_final_survives_a_crash_after_it(self):
        # V2-B5: results_ready is final; the process's later exit is recorded apart
        app = app_ended(1, free=True, ready=True)
        p = progress(app)
        self.assertEqual((p["state"], p["finished"], p["interrupted"]), ("finished", True, False))
        self.assertEqual(shown_endings(page_of(app)), ["finished"])

    def test_a_free_run_that_fails_after_finding_jobs_keeps_the_way_to_them(self):
        app = app_ended(1, free=True, found=7)
        p = progress(app)
        self.assertEqual((p["state"], p["found"]), ("halted", 7))
        page = page_of(app)
        self.assertEqual(shown_endings(page), ["halted"])
        self.assertIn('<a class="secondary" href="/results">See what it found</a>', page)
        self.assertNotIn('href="/results"', visible_banner(page))

    def test_a_free_run_that_finishes_with_no_jobs_is_still_a_finished_run(self):
        app = app_ended(0, free=True, found=0)
        self.assertEqual(progress(app)["state"], "finished")
        self.assertEqual(shown_endings(page_of(app)), ["finished"])

    def test_a_free_run_still_going_with_nothing_outstanding_is_running(self):
        app = sweep_app(free=True, alive=True)
        p = progress(app)
        self.assertEqual((p["state"], p["outstanding"], p["finished"], p["interrupted"]), ("running", 0, False, False))

    def test_a_timeout_is_named_only_when_the_worker_says_so(self):
        app = app_ended(1, timed_out=True, free=True)
        self.assertEqual(progress(app)["state"], "halted")
        page = page_of(app)
        self.assertIn(">The sweep ran out of time</b>", page)
        self.assertIn("The sweep reached its time limit before it finished. ' + (p.charged_unknown ? '' : 'Nothing was charged. ')", page)
        self.assertNotIn(">The sweep ran out of time</b>", page_of(app_ended(1, free=True)))

    def test_the_failed_ending_is_the_same_in_public_and_the_console(self):
        for free_kwargs in ({}, {"timed_out": True}, {"stopped": True}):
            with self.subTest(**free_kwargs):
                pub = app_ended(1, free=True, public=True, **free_kwargs)
                con = app_ended(1, free=True, public=False, **free_kwargs)
                self.assertEqual(progress(pub)["state"], progress(con)["state"])
                self.assertEqual(shown_endings(page_of(pub)), shown_endings(page_of(con)))
                self.assertNotIn("finished", shown_endings(page_of(con)))

    def test_a_failed_free_run_does_not_keep_animating_or_promise_a_shortlist(self):
        public = page_of(app_ended(1, free=True, public=True))
        self.assertRegex(public, r'<div class="panel gone"[^>]*>\s*<div class="panel-head">\s*<h2>Your shortlist')
        console = page_of(app_ended(1, free=True, public=False))
        self.assertRegex(console, r'<div class="working-bar" x-show="p.state === \'running\'"\s*style="display:none"')
        # nor promise listings "when the pass finishes" once it has not
        self.assertRegex(console, r'<span\s+x-show="p.state === \'running\'" style="display:none"> The listings')
        self.assertRegex(page_of(sweep_app(free=True, public=False)),
                         r'<div class="working-bar" x-show="p.state === \'running\'"\s*><span>')


class PaidEndingsAreUnchanged(unittest.TestCase):

    def test_a_paid_run_that_ran_every_search_is_finished(self):
        app = app_ended(0, done=46)
        self.assertEqual(progress(app)["state"], "finished")

    def test_a_paid_ledger_that_is_complete_and_whose_process_succeeded_is_finished(self):
        # D7C: the ledger alone is no longer enough (see PaidEndingAfterTheLastSearch); a clean exit is
        self.assertEqual(progress(app_ended(0, done=46))["state"], "finished")

    def test_a_paid_run_short_of_its_searches_is_still_halted_or_stopped(self):
        self.assertEqual(progress(app_ended(1, done=19))["state"], "halted")
        self.assertEqual(progress(app_ended(1, done=19, stopped=True))["state"], "stopped")

    def test_a_paid_partial_run_is_still_partial(self):
        auth = {"outcome": "partial", "skipped_insufficient_capacity": 27, "skipped_budget": 0,
                "placeable_paid_units": 19, "total_planned_paid_units": 46, "partial_estimate_usd": 1.1}
        self.assertEqual(progress(app_ended(0, done=19, authorization=auth))["state"], "partial")

    def test_a_refused_start_is_still_refused_and_offers_no_continuation_of_work_that_never_began(self):
        app = app_ended(1, done=0, authorization={"outcome": "refused"})
        self.assertEqual(progress(app)["state"], "credit_changed")
        page = page_of(app)
        self.assertEqual(shown_endings(page), ["credit_changed"])
        self.assertRegex(page, r'<div class="split ended"[^>]*display:none')

    def test_a_paid_timeout_keeps_its_count_and_names_the_limit(self):
        page = page_of(app_ended(1, done=19, timed_out=True))
        self.assertIn(">The sweep ran out of time</b>", page)
        self.assertIn("did not run because the sweep reached its time limit", page)
        # without the worker's word it is still the unexplained ending, credit claim and all
        plain = page_of(app_ended(1, done=19))
        self.assertIn(">The reason is not recorded</b>", plain)
        self.assertIn("and the reason is not recorded — the credit is not spent.", plain)


class PaidEndingAfterTheLastSearch(unittest.TestCase):
    """D7C blocker 3. A paid run whose every planned search is in the ledger used to read "finished" whatever the
    process did. The ledger proves the searches ran; it does not prove the engine ended well. If the process then failed
    or was interrupted and the worker never declared the result final, the run is "incomplete": every search ran, then it
    stopped. Not "halted" (that says the credit is not spent, which is false here), and not "finished"."""

    def test_a_complete_ledger_with_a_failed_process_is_incomplete_not_finished(self):
        for public in (True, False):
            with self.subTest(public=public):
                p = progress(app_ended(1, done=46, public=public))
                self.assertEqual(p["state"], "incomplete")
                self.assertFalse(p["finished"])
                self.assertTrue(p["interrupted"])
                self.assertEqual(p["remaining_text"], "every search ran, then the sweep stopped")

    def test_it_says_exactly_that_and_never_that_nothing_was_charged(self):
        for public in (True, False):
            with self.subTest(public=public):
                page = page_of(app_ended(1, done=46, public=public))
                self.assertEqual(shown_endings(page), ["incomplete"])
                self.assertEqual(heading(page), "The sweep did not finish")
                banner = text(visible_banner(page))
                self.assertNotIn("0 of 46 searches did not run", page)
                self.assertIn("Every search ran, then the sweep stopped", banner)
                self.assertIn("All 46 searches ran, so their credit is spent.", banner)
                self.assertIn("the reason is not recorded", banner)
                self.assertNotRegex(banner, r"(?i)nothing was charged|credit is not spent|did not run")
                self.assertIn("Everything already fetched is saved", banner)
                self.assertIn("so your results are still there" if public else "The terminal running Sweep will say more", banner)
                # nothing is left to finish, so the screen does not offer to, but the way to the jobs is there
                self.assertRegex(page, r'<div class="split ended"[^>]*display:none')
                self.assertIn('<a class="secondary" href="/results">See what it found</a>', page)

    def test_the_workers_own_timeout_is_named_and_a_plain_failure_is_not_called_one(self):
        timed = text(visible_banner(page_of(app_ended(1, done=46, timed_out=True))))
        self.assertIn("Every search ran, then the sweep ran out of time", timed)
        self.assertIn("reached its time limit", timed)
        self.assertNotIn("the reason is not recorded", timed)
        plain = text(visible_banner(page_of(app_ended(1, done=46))))
        self.assertNotIn("time limit", plain)
        self.assertNotIn("ran out of time", plain)

    def test_an_explicit_stop_is_stopped_whether_it_was_clicked_here_or_said_by_the_worker(self):
        for kw in ({"stopped": True}, {"worker_stopped": True}):
            with self.subTest(**kw):
                app = app_ended(1, done=46, **kw)
                self.assertEqual(progress(app)["state"], "stopped")
                page = page_of(app)
                self.assertEqual(shown_endings(page), ["stopped"])
                self.assertEqual(heading(page), "You stopped the sweep")
                # the banner's words are an expression the page evaluates with the live `p`: the branch for a run with nothing outstanding
                self.assertIn("'Every search had already run. Everything already fetched is saved.'", page)
                self.assertIn("p.outstanding ? p.outstanding + ' of ' + p.planned", page)

    def test_the_result_the_worker_declared_final_stays_final_whatever_the_process_does_after(self):
        for exit_code in (1, 0):
            with self.subTest(exit=exit_code):
                self.assertEqual(progress(app_ended(exit_code, done=46, ready=True))["state"], "finished")
        # ...including after a stop that arrived in the last seconds
        self.assertEqual(progress(app_ended(1, done=46, ready=True, worker_stopped=True))["state"], "finished")

    def test_a_run_that_is_still_going_is_never_ended(self):
        app = sweep_app(done=46, alive=True)
        self.assertEqual(progress(app)["state"], "running")

    def test_a_run_short_of_its_searches_is_unchanged(self):
        self.assertEqual(progress(app_ended(1, done=19))["state"], "halted")
        self.assertEqual(progress(app_ended(1, done=19, worker_stopped=True))["state"], "stopped")
        self.assertEqual(progress(app_ended(1, done=19, timed_out=True))["state"], "halted")

    def test_results_carries_the_same_ending_and_the_jobs_already_fetched_stay(self):
        for public in (True, False):
            with self.subTest(public=public):
                from sweep.tests.test_results_ui import page as results_page
                body = results_page(app_ended(1, done=46, public=public))
                self.assertRegex(body, r'<div class="banner warn" role="note">\s*<div><b>This search did not finish</b>')
                self.assertIn("Every search ran, then the sweep stopped before it finished. These are the jobs it found.", body)
                self.assertIn("found by the searches that ran", body)
                timed = results_page(app_ended(1, done=46, timed_out=True, public=public))
                self.assertIn("<b>This search ran out of time</b>", timed)
                stopped = results_page(app_ended(1, done=46, worker_stopped=True, public=public))
                self.assertIn("<b>You stopped this search</b>", stopped)
                final = results_page(app_ended(1, done=46, ready=True, public=public))
                self.assertNotIn('role="note"', final)


class AFreeRunIsStillSaidToBeFreeAndAPaidOneAfterARestartIsNot(unittest.TestCase):
    """D7C. After a web restart a paid run is shown through its free screens (its plan went with the memory that held it). Those
    screens say "Nothing was charged"; of a run the worker records as paid that is not theirs to say."""

    def test_the_flag_is_the_workers_word_and_is_set_only_for_a_paid_run_with_no_plan(self):
        app = app_ended(1, free=True)
        self.assertFalse(progress(app)["charged_unknown"])
        app.state["unplanned_paid"] = True
        self.assertTrue(progress(app)["charged_unknown"])
        # a run with its plan (the normal case) can count its searches and never needs it
        paid = app_ended(1, done=19)
        paid.state["unplanned_paid"] = True
        self.assertFalse(progress(paid)["charged_unknown"], "with a plan the searches are counted: no claim to withhold")

    def test_rehydrate_records_whether_the_worker_says_the_run_was_paid(self):
        from sweep import public
        for status_free, want in ((True, False), (False, True), (None, False)):
            app = sweep_app(free=True, alive=True, public=True)
            app.state.pop("raw_plan")
            with app.test_request_context("/"), mock.patch.object(public, "current_run_id", return_value="r1"), \
                    mock.patch.object(worker_link, "_asked", side_effect=lambda kind, rid, ask: {"state": "failed", "profile_name": "x", "free_only": status_free}), \
                    mock.patch.object(worker_link, "_checked", return_value=None):
                worker_link.rehydrate(app)
            self.assertIs(app.state["unplanned_paid"], want, status_free)


class TheWorkersStopIsTheStop(unittest.TestCase):
    """D7C blocker 4. The visitor's Stop click lives in the web session's memory; the worker records `stopped`
    authoritatively. After a web restart the click is gone and the worker's word is what is left, so that is what
    stands in for it, and ONLY that: a generic failure, a timeout and an interrupted run are never read as a stop."""

    def test_the_worker_saying_stopped_is_a_stop_for_a_free_run_with_no_click_on_record(self):
        for public in (True, False):
            with self.subTest(public=public):
                app = app_ended(1, free=True, worker_stopped=True, public=public)
                self.assertNotIn("stopped_by_user", app.state)
                self.assertEqual(progress(app)["state"], "stopped")
                page = page_of(app)
                # the public screen has its own heading for a stop; the console's reads "Sweep stopped early" for every ending
                self.assertEqual(heading(page), "You stopped the sweep" if public else "Sweep stopped early")
                self.assertEqual(shown_endings(page), ["stopped"])

    def test_nothing_else_the_worker_says_is_a_stop(self):
        self.assertEqual(progress(app_ended(1, free=True))["state"], "halted")                   # failed, no reason
        self.assertEqual(progress(app_ended(1, free=True, timed_out=True))["state"], "halted")   # run_timeout
        # a click that was never made and a process that is still going
        self.assertEqual(progress(sweep_app(free=True, alive=True))["state"], "running")

    def test_a_stop_after_a_finished_run_does_not_undo_its_success(self):
        self.assertEqual(progress(app_ended(0, free=True, worker_stopped=True))["state"], "finished")
        self.assertEqual(progress(app_ended(0, free=True, stopped=True))["state"], "finished")

    def test_the_stop_survives_the_session_forgetting_the_click(self):
        app = app_ended(1, free=True, stopped=True)                     # the visitor's click, then...
        self.assertEqual(progress(app)["state"], "stopped")
        app.state.pop("stopped_by_user")                               # ...a restart forgets it
        self.assertEqual(progress(app)["state"], "halted")             # (without the worker's word that is all there is)
        app.state["proc"].stopped = True                                # the worker's word is read back from its status
        self.assertEqual(progress(app)["state"], "stopped")

    def test_only_a_real_true_counts(self):
        # a stand-in process that answers every attribute (a mock) must not turn into a stop
        app = app_ended(1, free=True)
        app.state["proc"].stopped = mock.MagicMock()
        self.assertEqual(progress(app)["state"], "halted")


class TheStateFunction(unittest.TestCase):

    def test_zero_outstanding_is_not_proof_of_success(self):
        self.assertEqual(logic.sweep_state(False, 0), "finished")
        self.assertEqual(logic.sweep_state(False, 0, failed=True), "halted")
        self.assertEqual(logic.sweep_state(False, 0, failed=True, stopped_by_user=True), "stopped")
        self.assertEqual(logic.sweep_state(True, 0, failed=True), "running")

    def test_a_partial_record_never_turns_a_failed_empty_plan_into_a_partial_run(self):
        self.assertEqual(logic.sweep_state(False, 0, failed=True, authorization={"outcome": "partial"}), "halted")

    def test_planned_searches_all_done_and_a_failed_process_is_incomplete(self):
        self.assertEqual(logic.sweep_state(False, 0, failed=True, planned=46), "incomplete")
        self.assertEqual(logic.sweep_state(False, 0, failed=False, planned=46), "finished")
        self.assertEqual(logic.sweep_state(False, 0, failed=True, planned=46, stopped_by_user=True), "stopped")
        self.assertEqual(logic.sweep_state(True, 0, failed=True, planned=46), "running")
        # nothing planned (the free path) is still halted, and searches outstanding are still halted
        self.assertEqual(logic.sweep_state(False, 0, failed=True, planned=0), "halted")
        self.assertEqual(logic.sweep_state(False, 3, failed=True, planned=46), "halted")
        # a refused start and a partial run keep their own words
        self.assertEqual(logic.sweep_state(False, 0, failed=True, planned=46, authorization={"outcome": "refused"}), "credit_changed")
        self.assertEqual(logic.sweep_state(False, 5, failed=True, planned=46,
                                           authorization={"outcome": "partial", "skipped_insufficient_capacity": 5}), "partial")

    def test_the_new_state_is_in_the_vocabulary_and_every_consumer_knows_it(self):
        self.assertIn("incomplete", logic.SWEEP_STATES)
        self.assertEqual(logic.run_phase("incomplete"), "failed")
        self.assertIsNotNone(logic.results_ending("incomplete"))


class WhatTheWorkerSaid(unittest.TestCase):
    """RemoteRun is the public app's process: the worker's state becomes its exit,
    and `run_timeout` (which the worker already records) becomes `timed_out`."""

    def poll(self, status):
        run = worker_link.RemoteRun("r1")
        with mock.patch.object(worker_link, "_status", return_value=status):
            return run.poll(), run.timed_out

    def stopped(self, status):
        run = worker_link.RemoteRun("r1")
        with mock.patch.object(worker_link, "_status", return_value=status):
            run.poll()
        return run.stopped

    def test_only_the_workers_own_stopped_is_a_stop(self):
        for state, error, want in (("stopped", None, True), ("failed", None, False), ("interrupted", None, False),
                                   ("failed", sweep_worker.RUN_TIMEOUT, False), ("done", None, False),
                                   ("running", None, False), ("queued", None, False)):
            with self.subTest(state=state, error=error):
                self.assertIs(self.stopped({"state": state, "error": error}), want)

    def test_a_stop_is_remembered_once_seen_like_the_exit_it_goes_with(self):
        run = worker_link.RemoteRun("r1")
        with mock.patch.object(worker_link, "_status", return_value={"state": "stopped"}):
            self.assertEqual(run.poll(), 1)
        with mock.patch.object(worker_link, "_status", side_effect=worker_client.WorkerError("down")):
            self.assertEqual(run.poll(), 1)
        self.assertTrue(run.stopped)

    def test_each_worker_state_maps_to_an_exit_and_only_the_timeout_is_a_timeout(self):
        self.assertEqual(self.poll({"state": "done"}), (0, False))
        self.assertEqual(self.poll({"state": "running"}), (None, False))
        self.assertEqual(self.poll({"state": "failed", "error": None}), (1, False))
        self.assertEqual(self.poll({"state": "stopped"}), (1, False))
        self.assertEqual(self.poll({"state": "interrupted"}), (1, False))
        self.assertEqual(self.poll({"state": "failed", "error": sweep_worker.RUN_TIMEOUT}), (1, True))
        self.assertEqual(self.poll({"state": "failed", "error": "plan_changed"}), (1, False))

    def test_the_name_is_the_workers(self):
        self.assertEqual(worker_client.RUN_TIMEOUT, sweep_worker.RUN_TIMEOUT)


if __name__ == "__main__":
    unittest.main()
