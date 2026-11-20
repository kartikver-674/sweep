"""Public mode's sweep backend: the console's own screens, run on Oracle.

The local console already knows how to run a free sweep. Its Configure,
Confirm, Running and Results screens have carried `free_only` branches
since long before any of this — "Free sources only", a zero meter, no key
pills — and those screens have had far more iteration than anything a
beta would grow in a week.

So public mode does not get its own pages. It gets the same routes, with
the four things they reach for replaced:

    fetch_plan   a free-only plan, costed locally, no subprocess
    start_sweep  a run created on the Oracle worker
    read_live    what that run has found so far
    read_rows    what it found, for Results and the exports
    read_done    nothing: a free sweep bills no combos

`app.state["proc"]` normally holds a Popen. Here it holds a RemoteRun,
which answers poll() and terminate() from the worker instead — so
_sweep_in_flight(), the running screen and POST /stop keep working
without knowing the sweep is on another machine.

State is memory, and Render's memory does not survive a redeploy. The run
id does, in the signed cookie, so `rehydrate` puts back the few facts the
screens need to show a sweep this process never started.
"""

import ast
import copy
import hashlib
import json
import os
import threading
import time

from sweep import public, worker_client

# Phase 0b's activation switch, and the ONLY one. Render has recorded the
# engine that derived each résumé (state["derived_engine"]) since Phase 0b-A,
# but tells the worker only when this is on. Off — the default, and what
# every deploy before sign-off runs — every plan and run request is byte for
# byte what it was before Phase 0b, and the worker stamps its own default
# (v1). On, the worker stamps the derivation's engine (v2 on Render), which
# changes public scoring from v1 to v2: so this is switched on only after the
# offline v1-vs-v2 comparison is signed off, and switching it off again is
# the rollback.
ENGINE_FLAG = "SWEEP_SEND_PROFILE_ENGINE"


def sends_engine(env=None):
    """Is engine propagation on? Anything but a clear yes is no."""
    raw = ((os.environ if env is None else env).get(ENGINE_FLAG) or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def engine_for(state, env=None):
    """The engine this visitor's plan and run must be rendered with: the one
    recorded when their résumé was derived, while propagation is on. None
    otherwise — including a derivation with no recorded engine, which is
    then rendered exactly as before Phase 0b."""
    if not sends_engine(env):
        return None
    return state.get("derived_engine")


# --------------------------------------------------------------------------
# A Multi-Track Sweep (P4-R1; design §M, amended 2026-09-28)
# --------------------------------------------------------------------------
# Render derives each selected track's engine-ready TRACKS entry and the worker
# only runs it. The entries are résumé-derived and ORDERED (key order is data),
# so they live in this session's server-side room and nowhere else: never a
# page, a cookie or a JSON answer.
#
# The product gate (design §T Phase 5). Off, the default, nothing reaches this
# path: every screen, request and cookie is today's.
MULTI_FLAG = "SWEEP_MULTI_TRACK"
# Stamped by POST /run from the confirmed plan, never chosen with it: spend cap
# and partial approval are authorization, outside the plan hash (design §G.1)
# and no track's input. A planned snapshot carries neither; its run adds them.
AUTHORIZATION = ("max_spend_usd", "allow_partial_paid_sweep")
# In the room: the one planned Sweep ({"snapshot", "plan_hash"}, set only by a
# plan that succeeded; "run_id" once it started), and the flag that sends a
# stale one back to Confirm.
PLANNED = "multi_planned"
REPLAN = "multi_replan"
# track_recommendation's kinds and scraper.CAUTIONS (a test pins both).
KINDS = ("clear", "close", "tied", "split")
CAUTIONS = ("", "no_focus_evidence")


class MultiTrackUnavailable(worker_client.WorkerError):
    """No Multi-Track Sweep can be built here: not 2-3 selected résumés, or a
    derivation flag it needs is off. Fail closed — never one résumé instead."""


def multi_enabled(env=None):
    """Is the Multi-Track product on? Anything but a clear yes is no."""
    raw = ((os.environ if env is None else env).get(MULTI_FLAG) or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def selected(state):
    """The tracks this Sweep searches, in the user's order."""
    return [t for t in state.get("tracks") or () if t.get("selected", True)]


def multi_active(state, env=None):
    """Whether this session's Sweep is a Multi-Track one: public mode, the
    product on, and two or more selected résumés. One résumé never is."""
    from flask import current_app, has_app_context
    return (multi_enabled(env) and has_app_context()
            and bool(current_app.config.get("PUBLIC_MODE"))
            and len(selected(state)) >= 2)


_MARKET = []


def _market():
    """The corpus the derivations read (local_profile.generate's own
    local_search.Market()), indexed once per process.
    ponytail: a live corpus that grows mid-process is not re-read; public
    mode has none (Render ships the frozen one)."""
    if not _MARKET:
        import local_search
        _MARKET.append(local_search.Market())
    return _MARKET[0]


def _plan_prefs(state):
    """The Sweep's preferences as a plan is made from them: _prefs, less the
    two values POST /run stamps afterwards."""
    return dict(_prefs_of(state), **dict.fromkeys(AUTHORIZATION))


def inputs(state):
    """What a planned Sweep was built from, as one digest: each selected
    track's id, engine, derivation and résumé text in order, the plan's
    preferences and free_only. ANY change is a new Sweep to plan — nothing here
    judges whether an edit would have mattered. Internal: never sent."""
    tracks = [[t.get("id"), t.get("engine"), t.get("derived"), t.get("resume_text")]
              for t in selected(state)]
    body = json.dumps([tracks, _plan_prefs(state), bool(state.get("free_only"))],
                      ensure_ascii=False, default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _tracks_of(source):
    """TRACKS as render_sweep wrote it, key order and all."""
    return next(ast.literal_eval(node.value) for node in ast.parse(source).body
                if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "TRACKS")


def build_snapshot(state, market=None):
    """The immutable input of one Multi-Track plan and its run, from ONE
    capture of the session: tracks and preferences can never come from two
    different moments (each track's penalty_terms already carry the avoid and
    exclude lists).

    Derived exactly as every accepted schema-2 render is — with_track_search,
    with_track_scoring, render_sweep — and the entries are render_sweep's own
    TRACKS, so what the worker is sent is the profile Render would write.
    Carries no résumé text: that stays in the room, beside its track."""
    import make_profile
    captured = copy.deepcopy({k: v for k, v in state.copy().items() if k != "proc"})
    tracks = selected(captured)
    if not 2 <= len(tracks) <= make_profile.MAX_TRACKS:
        raise MultiTrackUnavailable("a Multi-Track Sweep has 2 or 3 résumés")
    if not (make_profile.track_search_enabled() and make_profile.track_scoring_enabled()
            and make_profile.track_alignment_enabled()):
        raise MultiTrackUnavailable("Multi-Track derivation is not configured")
    prefs = _plan_prefs(captured)
    texts = [t["resume_text"] for t in tracks]
    market = market if market is not None else _market()
    attached = make_profile.with_track_scoring(make_profile.with_track_search(
        [{"id": t["id"], "engine": t["engine"], "derived": t["derived"]} for t in tracks],
        texts, market), texts, market)
    source = make_profile.render_sweep(captured.get("profile") or "sweep", attached, prefs)
    return {"schema": 2, "tracks": _tracks_of(source), "prefs": prefs,
            "free_only": bool(captured.get("free_only")),
            "track_ids": [t["id"] for t in tracks], "inputs": inputs(captured)}


def invalidate(state):
    """Drop the planned Sweep's approval: the next Confirm plans it again."""
    state.pop(PLANNED, None)
    state[REPLAN] = True


def plan_multi(state):
    """/v1/plans for this session's Multi-Track Sweep: a new snapshot, priced
    by the worker, and stored with the worker's plan_hash — the only hash a
    run may carry. The approval it replaces is dropped first, so a plan that
    fails leaves none behind."""
    state.pop(PLANNED, None)
    state.pop(REPLAN, None)
    snapshot = build_snapshot(state)
    raw = worker_client.plan_tracks(snapshot["tracks"], snapshot["prefs"],
                                    free_only=snapshot["free_only"])
    state[PLANNED] = {"snapshot": snapshot, "plan_hash": raw["plan_hash"]}
    return raw


def start_multi(state):
    """Start the planned Sweep, exactly as planned: the stored tracks, prefs
    and free_only, POST /run's authorization stamps, and the stored plan hash —
    for a free Sweep too. A session changed since the plan, or an approval
    already used, is PlanChanged: back to Confirm, nothing started."""
    planned = state.get(PLANNED)
    if not planned or "run_id" in planned or inputs(state) != planned["snapshot"]["inputs"]:
        invalidate(state)
        raise worker_client.PlanChanged("the planned Sweep changed since it was priced")
    snapshot = planned["snapshot"]
    free_only = snapshot["free_only"]
    try:
        run_id = worker_client.create_tracks_run(
            snapshot["tracks"], dict(snapshot["prefs"], **{k: state.get(k) for k in AUTHORIZATION}),
            planned["plan_hash"], free_only=free_only,
            key_ids=None if free_only else state.get("run_key_ids"))
    except worker_client.PlanChanged:
        invalidate(state)
        raise
    planned["run_id"] = run_id
    public.remember_run(run_id, tracks=[
        [t["id"], public.run_label(t.get("name"), n)] for n, t in enumerate(selected(state), 1)],
        plan_hash=planned["plan_hash"])
    return RemoteRun(run_id)


def multi_row(row, track_ids):
    """One Multi-Track result row's engine fields, parsed strictly. The row
    itself stays exactly as the worker served it; this is its typed reading,
    for the screens to come. Nothing is recomputed: a recommendation, a kind or
    a caution is the engine's or the row is refused (ProtocolError).

    recommendation_caution keeps its three meanings: absent (not computed),
    "" (no caution), "no_focus_evidence"."""
    ids = set(track_ids)
    try:
        out = {"best_track": row["best_track"], "track_evals": json.loads(row["track_evals"]),
               "found_by": row["found_by"].split(";")}
        evals = out["track_evals"]
        ok = (out["best_track"] in evals and isinstance(evals, dict) and set(evals) <= ids
              and all(set(e) == {"s", "m"} and type(e["s"]) is int and isinstance(e["m"], str)
                      for e in evals.values())
              and len(set(out["found_by"])) == len(out["found_by"])
              and set(out["found_by"]) <= ids | {"free"})
        if "recommended_tracks" in row or "recommendation" in row:
            out["recommended_tracks"] = row["recommended_tracks"].split(";")
            out["recommendation"] = row["recommendation"]
            ok = ok and (out["recommended_tracks"][0] == out["best_track"]
                         and set(out["recommended_tracks"]) <= set(evals)
                         and len(set(out["recommended_tracks"])) == len(out["recommended_tracks"])
                         and out["recommendation"] in KINDS)
        if "recommendation_caution" in row:
            out["recommendation_caution"] = row["recommendation_caution"]
            ok = ok and "recommendation" in out and out["recommendation_caution"] in CAUTIONS
    except (KeyError, TypeError, ValueError, AttributeError):
        ok = False
    if not ok:
        raise worker_client.ProtocolError("the sweep worker served a row the engine "
                                          "cannot have written")
    return out


def _expected(run_id):
    """(track ids, plan hash) this browser's Multi-Track run must report, or
    None: a one-track run, or a run that is not the one in the cookie."""
    if run_id != public.current_run_id():
        return None
    return public.current_run_tracks()


def _checked(run_id, status):
    """A Multi-Track run's status, correlated: its schema, track ids (in
    order) and plan hash are the planned Sweep's, or ProtocolError. One whose
    engine found the plan changed (exit 4) sends the session back to
    Confirm. A one-track status passes untouched."""
    expected = _expected(run_id)
    if expected is None:
        return status
    worker_client.check_run(status, *expected)
    if status.get("state") == "failed" and status.get("error") == worker_client.PLAN_CHANGED:
        from flask import current_app
        planned = current_app.state.get(PLANNED)
        # Only this run's own approval: the activity strip keeps reading the
        # old run, and a Sweep planned again since must not be dropped by it.
        if planned is None or planned.get("run_id") == run_id:
            invalidate(current_app.state)
    return status


# What a free sweep's plan looks like: no paid searches at all. The shape
# is plan.fetch()'s, so plan.cost() prices it the same way it prices a
# real one — at zero, because there is nothing billable in it.
def free_plan(profile, free_sources=0):
    return {"profile": profile, "sites": {}, "max_results": {},
            "free_sources": free_sources}


class RemoteRun:
    """A Popen, as far as the console's screens are concerned.

    They ask a sweep two things — are you still going, and stop — and a
    run on another machine can answer both. Nothing else about the local
    subprocess is relied on.
    """

    FINISHED = {"done", "failed", "stopped", "interrupted"}

    def __init__(self, run_id):
        self.run_id = run_id
        self._code = None
        # True only when the worker itself said the wall clock ran out.
        self.timed_out = False
        # True only when the worker itself recorded `stopped`, which it does in
        # one place only: its own stop() (a visitor's Stop, asked for). A
        # generic failure, a timeout and a restart (`interrupted`) are never
        # read as a stop. This is what lets a run the visitor stopped still say
        # so after a web restart has forgotten their click (D7C).
        self.stopped = False

    def poll(self):
        """None while the sweep is alive, an exit code once it is not."""
        if self._code is not None:
            return self._code
        try:
            status = _status(self.run_id)
        except (worker_client.RunNotFound, worker_client.ProtocolError):
            # Not found, or (Multi-Track) not the planned Sweep: either way
            # this screen has no run to wait for.
            self._code = 1
            return self._code
        except worker_client.WorkerError:
            # Unreachable for a moment is not finished: saying otherwise
            # would send the watcher to a results screen mid-sweep.
            return None
        if status.get("state") in self.FINISHED:
            self._code = 0 if status.get("state") == "done" else 1
            self.timed_out = status.get("error") == worker_client.RUN_TIMEOUT
            self.stopped = status.get("state") == "stopped"
        return self._code

    def terminate(self):
        try:
            worker_client.stop_run(self.run_id)
        except worker_client.WorkerError:
            pass
        forget(self.run_id)

    def send_signal(self, _sig):
        """runs.stop() interrupts the engine with SIGINT. There is no
        local process to signal, so the worker is asked to stop the run —
        the same outcome by the only means available across a wire."""
        self.terminate()

    # The console calls this on a child it has already terminated.
    def wait(self, timeout=None):
        return self.poll()


# What the worker said about a run, kept for STATUS_TTL seconds (P4-S1C):
# (kind, owner, run id) -> (when, answer, error). Keyed on the owner — the
# worker's own authority for a run — so an answer is only ever reused for a
# request that would have been given the very same one, never across
# sessions or runs. A refusal is kept as briefly, so a worker that is down is
# not asked again by every poll. The multi-track correlation (_checked) is
# not cached: it runs on every read.
STATUS_TTL = 2.5
_ASKED = {}
_ASKED_LOCK = threading.Lock()


def _asked(kind, run_id, ask):
    from flask import has_request_context
    if not has_request_context():
        return ask()
    key = (kind, public.owner_for_session(), run_id)
    now = time.monotonic()
    with _ASKED_LOCK:
        held = _ASKED.get(key)
    if held and now - held[0] < STATUS_TTL:
        if held[2] is not None:
            raise held[2]
        return held[1]
    try:
        answer, error = ask(), None
    except worker_client.WorkerError as exc:
        answer, error = None, exc
    with _ASKED_LOCK:
        for stale in [k for k, (at, _a, _e) in _ASKED.items() if now - at >= STATUS_TTL]:
            del _ASKED[stale]
        _ASKED[key] = (now, answer, error)
    if error is not None:
        raise error
    return answer


def forget(run_id):
    """Drop what was kept about this run — after a stop, its next reading
    must be the worker's, not the one from before."""
    with _ASKED_LOCK:
        for key in [k for k in _ASKED if k[2] == run_id]:
            del _ASKED[key]


def _status(run_id):
    """This run's status, at most once per STATUS_TTL per owner and run.

    The running screen polls, and one poll asks three questions — is it
    alive, what has finished, what has arrived — and the strip asks again.
    Without this they would be round trips to Oracle every few seconds per
    watcher, each one as many as a script cared to send.
    """
    return _checked(run_id, _asked("status", run_id,
                                   lambda: worker_client.run_status(run_id)))


def _rows(run_id, strict=False):
    """The run's rows. A Multi-Track run's only once its status is the planned
    Sweep's and every row reads as the engine wrote it; `strict` (Results and
    the exports) lets a mismatch through as ProtocolError rather than an empty
    list, so it is never shown as a search that found nothing."""
    if not run_id:
        return []
    expected = _expected(run_id)
    try:
        if expected is not None:
            _status(run_id)
        # Every page of rows, fetched at most once per STATUS_TTL per owner
        # and run (P4-S1C): a poll, the strip and Results in one window share
        # it. The rows themselves are exactly the worker's, in its order.
        rows = list(_asked("rows", run_id, lambda: worker_client.all_rows(run_id)))
        if expected is not None:
            for row in rows:
                multi_row(row, expected[0])
        return rows
    except worker_client.ProtocolError:
        if strict:
            raise
        return []
    except worker_client.WorkerError:
        return []


def injections(app):
    """The functions create_app would otherwise resolve locally.

    Takes the app and reads `app.state` per call, never capturing it:
    public mode swaps that attribute for a per-session view after these
    are built, and a closure over the old object would serve one
    visitor's sweep to everybody.
    """

    def fetch_plan(profile):
        # A free sweep has nothing to price, and Render has neither the
        # engine's corpus nor the CPU to spend on a dry run that can only
        # ever answer zero. A PAID one is different: that number is what a
        # visitor approves before spending their own money, so it comes
        # from the engine's own dry run, on the machine that has it.
        if multi_active(app.state):
            # A Multi-Track Sweep is priced for free runs too: its run is
            # bound to the plan's hash, and there is no hash without a plan.
            raw = plan_multi(app.state)
            raw["profile"] = profile
            return raw
        if not app.state.get("derived"):
            return free_plan(profile)
        free_only = bool(app.state.get("free_only"))
        engine = engine_for(app.state)
        try:
            raw = worker_client.plan(app.state["derived"], _prefs_of(app.state),
                                     free_only=free_only,
                                     **({"engine": engine} if engine is not None else {}))
        except worker_client.WorkerError:
            # A free sweep can still be configured and started while the
            # plan service is unreachable: there is nothing to price. A paid
            # one cannot — see /run, which refuses a plan it never got.
            if free_only:
                return free_plan(profile)
            raise
        if engine is not None:
            # Outside the fallback on purpose. An unreachable worker may still
            # start a free sweep; a worker that ANSWERED with a profile stamped
            # for another engine (or no attestation at all) starts nothing,
            # free or paid — never a silent run on the old engine. /run re-
            # prices through here immediately before every start.
            worker_client.check_engine(raw, engine)
        # The worker names the plan after its own throwaway profile; the
        # screens read this one back as the profile they are configuring.
        raw["profile"] = profile
        return raw


    def start_sweep(profile):
        if multi_active(app.state):
            return start_multi(app.state)
        # The visitor's key, if they chose to use one, is already held by
        # the worker — it never came back to Render to be kept.
        free_only = bool(app.state.get("free_only"))
        # V2-D1: exactly the held keys POST /run chose — the accounts the
        # visitor confirmed — and the worker freezes them for this run.
        # Phase 0b: the same recorded engine the plan was attested with.
        engine = engine_for(app.state)
        run_id = worker_client.create_run(
            app.state.get("derived") or {}, _prefs_of(app.state),
            free_only=free_only,
            key_ids=None if free_only else app.state.get("run_key_ids"),
            **({"engine": engine} if engine is not None else {}))
        public.remember_run(run_id)
        return RemoteRun(run_id)

    def read_live(profile, since):
        return _rows(public.current_run_id())

    def read_rows(profile):
        return _rows(public.current_run_id(), strict=True)

    def read_done(profile, day):
        """Which searches have finished, from the run's own ledger.

        A free sweep runs no billable combos, so this is empty and the
        grid stays empty with it — the same as locally. A PAID sweep's
        grid is exactly this, which is why it comes over the wire rather
        than being assumed empty.
        """
        run_id = public.current_run_id()
        if not run_id:
            return set()
        try:
            done = _status(run_id).get("done") or []
        except worker_client.WorkerError:
            return set()
        # Today's only, the same filter runs.done_keys applies: the engine
        # re-runs and re-bills yesterday's, so they are not progress.
        return {line for line in done if line.startswith(day)}

    def read_queue():
        """This run's place in the worker's queue, or None when it is not
        waiting.

        The worker has reported `queue_position` since it was written
        (sweep_worker.py, `public()`), and nothing on this side read it —
        so with MAX_ACTIVE=1 a visitor waiting behind another sweep saw
        exactly what a hung sweep looks like. Read from the SAME cached
        status the rest of the screen polls, so it costs no extra call.
        """
        run_id = public.current_run_id()
        if not run_id:
            return None
        try:
            status = _status(run_id)
        except worker_client.WorkerError:
            return None
        # 0 means "not waiting" on the worker's side — running, finished, or
        # never queued. Reported as None so the screen does not have to know
        # which of the two zeroes it is looking at.
        return status.get("queue_position") or None

    def read_ready():
        """Whether the worker says this run's result is final although its
        engine is still running (V2-B5).

        False — wait for the process, as before — whenever the field is
        absent: a worker or an engine older than this, the flag off, or the
        worker not answering. Strictly `True`, so no other value in a status
        body can move a visitor to their results. From the same cached
        status the rest of the poll reads, so it costs no extra call.
        """
        run_id = public.current_run_id()
        if not run_id:
            return False
        try:
            return _status(run_id).get("results_ready") is True
        except worker_client.WorkerError:
            return False

    def read_authorization():
        """The engine's own record of how much of the paid plan it could
        authorise when it came to start (V2-D1), or None: no run, the worker
        not answering, or a run that has not got that far. From the cached
        status the poll already reads, so it costs no extra call."""
        run_id = public.current_run_id()
        if not run_id:
            return None
        try:
            return _status(run_id).get("paid_authorization")
        except worker_client.WorkerError:
            return None

    def read_spend():
        # Never called on the free path (snapshot() returns early), and
        # there is no account to poll if it were.
        return None

    def list_sweeps(profile):
        return []

    return {"fetch_plan": fetch_plan, "start_sweep": start_sweep,
            "read_live": read_live, "read_rows": read_rows,
            "read_done": read_done, "read_spend": read_spend,
            "read_queue": read_queue, "read_ready": read_ready,
            "read_authorization": read_authorization,
            "list_sweeps": list_sweeps}


def owned_status():
    """This browser's run, as the worker sees it — or None.

    The one call the persistent status strip is allowed to make. Cheap by
    construction: `_status` caches on `g`, so the rehydrate hook that runs
    before every public request has usually already paid for it and this is
    free.

    None for every reason a strip should stay silent, and deliberately
    without distinguishing them: no run in the cookie, the worker refusing
    a run that is not this owner's (RunNotFound, which is what a stranger
    holding a real id gets), a run aged past its TTL, or the worker simply
    not answering. Telling those apart on screen is how an ownership
    boundary leaks.
    """
    run_id = public.current_run_id()
    if not run_id:
        return None
    try:
        return _status(run_id)
    except worker_client.WorkerError:
        return None


def _prefs_of(state):
    from sweep.app import _prefs
    return _prefs(state)


def rehydrate(app):
    """Put back what a returning visitor's screens need after a redeploy.

    Oracle keeps sweeping while Render restarts, and the cookie keeps the
    run id — but state is memory, so /running would bounce a visitor all
    the way back to the upload screen for a sweep that is still going.

    Only the facts the screens read, and only from the worker: the
    profile name it is running, when it started, and an empty free plan.
    The derived résumé is gone for good, which is why this does not try to
    make Configure work — starting a NEW sweep needs the résumé again.
    """
    run_id = public.current_run_id()
    if not run_id or app.state.get("raw_plan"):
        return None
    try:
        status = _asked("status", run_id, lambda: worker_client.run_status(run_id))
        # A Multi-Track run is put back only if it is still the planned Sweep
        # the cookie names; one whose plan changed sends the visitor to
        # Confirm (the before_request hook runs inside the request).
        _checked(run_id, status)
    except worker_client.WorkerError:
        return None

    profile = status.get("profile_name") or "sweep"
    app.state["profile"] = profile
    app.state["free_only"] = True
    app.state["raw_plan"] = free_plan(profile)
    app.state["plan"] = _costed(app.state["raw_plan"])
    # What the worker says the run was. The plan of a paid run is gone with the memory that held it, so its screens are the free
    # ones (an empty plan), but they must not say "nothing was charged" of a run that may have spent money (D7C).
    app.state["unplanned_paid"] = status.get("free_only") is False
    app.state["run_started_at"] = status.get("started_at") or time.time()
    # Always, finished or not (D7C). A run that ended while the tab was shut, or
    # that the visitor stopped before a restart, is read from the worker's own
    # word (its exit, `stopped`, `run_timeout`), not from a process this
    # server never had: without it a failed or stopped free run read
    # "finished" here, because there was no process to say otherwise.
    # _sweep_in_flight() asks proc.poll(), which is an exit code once it is over.
    app.state["proc"] = RemoteRun(run_id)
    return status


def _costed(raw):
    import config

    from sweep import plan as plan_mod
    return plan_mod.cost(raw, config.SITE_RATES, config.SITE_RATE_BASIS)
