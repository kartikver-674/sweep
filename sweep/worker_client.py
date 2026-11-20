"""Render's side of the link to the Oracle sweep worker.

Server-side only. The browser never learns this URL, never learns the
bearer token, and never talks to Oracle: it polls Render, and Render polls
the worker.

Two credentials, with different lifetimes on purpose:

  the worker token   Render's own, from the environment, the same for
                     every visitor, and never rendered into a page.
  the owner          per visitor, derived from their signed cookie by
                     public.owner_for_session(), so a restarted Render
                     process can still prove a run is theirs.

A visitor's Apify token is neither of those. It is an argument to
create_run and nothing else — not stored here, not logged, not put in a
URL — and the worker is equally careful with it on the far side.
"""

import json
import os
import re
import urllib.error
import urllib.request

from sweep import public

URL_ENV = "SWEEP_WORKER_URL"
TOKEN_ENV = "SWEEP_WORKER_TOKEN"
# deploy/sweep_worker's PLAN_VERSION and PLAN_CHANGED (a test pins them): a
# Multi-Track plan's attestation, and the word for one that went stale.
PLAN_VERSION = 2
PLAN_CHANGED = "plan_changed"
# deploy/sweep_worker's RUN_TIMEOUT (a test pins it): the `error` its status
# carries for a run whose wall clock ran out, told apart from any other failure.
RUN_TIMEOUT = "run_timeout"
PLAN_HASH = re.compile(r"[0-9a-f]{64}")
# deploy/sweep_worker's QUEUE_FULL (a test pins it): the worker's 503 for a
# run its waiting line has no place for, told apart from the paid-off 503.
QUEUE_FULL = "queue_full"

# A sweep is long, but these calls are not: they create, poll or stop.
TIMEOUT = 20


class WorkerError(RuntimeError):
    """The worker could not be reached, or refused. Safe to show: this
    module composes the text, so it never carries urllib's URL."""


class NeedsKey(WorkerError):
    """A paid run was asked for and the worker is holding no key for this
    visitor — spent on an earlier run, or aged out of its memory. It was
    never written down, so the only way back is to ask for it again."""


class PaidUnavailable(WorkerError):
    """The worker has public paid sweeps switched off (SWEEP_PUBLIC_PAID).
    Nothing was started and no key was handed over."""


class QueueFull(WorkerError):
    """The worker has as many runs waiting as it takes (SWEEP_MAX_QUEUED_RUNS).
    No run was created and no held key was spent; trying later is the fix."""


class RunNotFound(WorkerError):
    """No such run — or not this visitor's. The worker does not
    distinguish the two, and neither should anything here."""


class EngineMismatch(WorkerError):
    """The worker priced a profile stamped with a different scoring engine
    than the one that derived this résumé (Phase 0b), or did not say which.
    Nothing may run on that plan: it would score the visitor's jobs with an
    engine their profile was not built for."""


class PlanChanged(WorkerError):
    """A Multi-Track Sweep's approved plan is stale: the worker's 409
    plan_changed, a run whose engine found its plan changed (exit 4), or a
    session edited since the plan was made. Nothing ran on it; the visitor
    must see a new plan. Never a failed search."""


class ProtocolError(WorkerError):
    """The worker answered, but not as the Multi-Track contract promises: a
    plan without plan_version 2 and a plan_hash, a run status that is not the
    planned Sweep's, a result row the engine cannot have written, or a Sweep
    the worker refused as malformed. Fail closed: nothing is shown from it."""


class EngineFailed(WorkerError):
    """The worker's engine could not price a Multi-Track Sweep (its 502)."""


def check_run(status, track_ids, plan_hash):
    """`status`, when it is this Multi-Track run's own — schema 2, exactly
    these track ids in this order, this plan hash — else ProtocolError. A
    one-track run is never checked: its status is exactly what it was."""
    if not (status.get("schema") == 2 and status.get("track_ids") == list(track_ids)
            and status.get("plan_hash") == plan_hash):
        raise ProtocolError("the sweep worker's run is not the planned Sweep")
    return status


def check_engine(raw, engine):
    """`raw`, the worker's dry run, when its profile_engine is `engine`;
    otherwise EngineMismatch. Only for a plan that was asked for with an
    explicit engine — a legacy request is not attested at all."""
    if raw.get("profile_engine") != engine:
        raise EngineMismatch("the sweep worker did not use this résumé's "
                             "scoring engine")
    return raw


def base_url(url=None):
    return (url or os.environ.get(URL_ENV) or "").strip().rstrip("/")


def _token(token=None):
    return (token if token is not None
            else os.environ.get(TOKEN_ENV) or "").strip()


def _refusal(exc):
    """The worker's own error message, or None. Read only to tell
    plan_changed from a missing key; never shown, never logged."""
    try:
        return (json.loads(exc.read() or b"{}").get("error") or {}).get("message")
    except Exception:
        return None


def _call(method, path, body=None, url=None, token=None, owner=None, multi=False):
    root = base_url(url)
    if not root:
        raise WorkerError("the sweep worker is not configured")
    headers = {"Authorization": f"Bearer {_token(token)}",
               # Whose run this is, re-derived from the cookie on every
               # request rather than remembered in this process.
               "X-Sweep-Owner": owner if owner is not None
               else public.owner_for_session()}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(root + path, data=data, headers=headers,
                                     method=method)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RunNotFound("that sweep is not available") from None
        if exc.code == 409:
            # Only a Multi-Track request can meet plan_changed, so a one-track
            # 409 is exactly what it always was.
            if multi and _refusal(exc) == PLAN_CHANGED:
                raise PlanChanged("the planned Sweep changed") from None
            raise NeedsKey("no Apify key is held for this visitor") from None
        if exc.code == 503:
            if _refusal(exc) == QUEUE_FULL:
                raise QueueFull("the sweep worker's queue is full") from None
            raise PaidUnavailable("paid sweeps are temporarily unavailable") from None
        if multi and exc.code == 400:
            raise ProtocolError("the sweep worker refused the Sweep") from None
        if multi and exc.code == 502:
            raise EngineFailed("the sweep worker could not price the Sweep") from None
        raise WorkerError(f"the sweep worker refused the request "
                          f"({exc.code})") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise WorkerError("the sweep worker did not answer") from None


def create_run(profile, prefs, free_only=True, apify_token=None, key_ids=None,
               engine=None, **kw):
    """Start a sweep. Returns the opaque run id.

    `apify_token` passes straight through to the worker and is not held
    here — not in a variable that outlives this call, not in a log line.
    `key_ids` (V2-D1) names which of the visitor's held keys fund it: the
    accounts they confirmed, and no others. `engine` (Phase 0b) is the
    engine that derived the résumé; omitted, the body is exactly what it
    was before the field existed.
    """
    body = {"profile": profile, "prefs": prefs, "free_only": free_only,
            "owner": kw.pop("owner", None) or public.owner_for_session()}
    if apify_token:
        body["apify_token"] = apify_token
    if key_ids:
        body["key_ids"] = list(key_ids)
    if engine is not None:
        body["engine"] = engine
    answer = _call("POST", "/v1/runs", body, **kw)
    return answer["run_id"]


def hold_token(apify_token, **kw):
    """Hand a visitor's Apify key to the worker, for their next run only.

    Render must not keep it between requests, so this is where it goes and
    this call is the only place it exists here. The worker holds it in
    memory against the same owner these calls already carry.
    """
    answer = _call("POST", "/v1/tokens",
                   {"owner": kw.pop("owner", None) or public.owner_for_session(),
                    "apify_token": apify_token}, **kw)
    # The worker's name for this key: all Render ever keeps of it. None from
    # a worker older than V2-D1, which holds one key per visitor.
    return answer.get("key_id")


def release_token(key_id, **kw):
    """Tell the worker to forget one held key (the visitor removed it)."""
    return _call("DELETE", f"/v1/tokens/{key_id}", **kw)


def plan(profile, prefs, free_only=True, engine=None, **kw):
    """What this profile would search, priced by the engine's own dry run.

    Costs nothing and runs nothing; it is the number a visitor approves
    before spending their own money, so it comes from the engine rather
    than from arithmetic repeated here. With `engine`, the worker renders
    with that stamp and its dry run reports profile_engine (check_engine);
    without it, the request is exactly what it always was.
    """
    body = {"profile": profile, "prefs": prefs, "free_only": free_only,
            "owner": kw.pop("owner", None) or public.owner_for_session()}
    if engine is not None:
        body["engine"] = engine
    return _call("POST", "/v1/plans", body, **kw)


def plan_tracks(tracks, prefs, free_only=True, **kw):
    """A Multi-Track Sweep's plan: the worker's dry run of `tracks`, the
    engine-ready TRACKS entries Render built, with the Sweep's `prefs`.

    Sent through _call's json.dumps, which keeps every mapping in the order
    Render built it — an entry's key order is data (ScoringContext.key reads
    skill_weights in order), so this body is never key-sorted. The answer
    must attest plan_version 2 and a plan_hash, or it is no plan at all."""
    body = {"tracks": tracks, "prefs": prefs, "free_only": free_only,
            "owner": kw.pop("owner", None) or public.owner_for_session()}
    raw = _call("POST", "/v1/plans", body, multi=True, **kw)
    if not (isinstance(raw, dict) and raw.get("plan_version") == PLAN_VERSION
            and isinstance(raw.get("plan_hash"), str) and PLAN_HASH.fullmatch(raw["plan_hash"])):
        raise ProtocolError("the sweep worker did not attest a Multi-Track plan")
    return raw


def create_tracks_run(tracks, prefs, expected_plan_hash, free_only=True,
                      apify_token=None, key_ids=None, **kw):
    """Start a planned Multi-Track Sweep: exactly the tracks and prefs its plan
    was made from, bound to that plan's hash. Required, free or paid — the
    worker would take a free Sweep without one, but then nothing would stop it
    running a plan nobody saw. Returns the opaque run id."""
    body = {"tracks": tracks, "prefs": prefs, "free_only": free_only,
            "owner": kw.pop("owner", None) or public.owner_for_session(),
            "expected_plan_hash": expected_plan_hash}
    if apify_token:
        body["apify_token"] = apify_token
    if key_ids:
        body["key_ids"] = list(key_ids)
    answer = _call("POST", "/v1/runs", body, multi=True, **kw)
    return answer["run_id"]


def run_status(run_id, **kw):
    return _call("GET", f"/v1/runs/{run_id}", **kw)


def run_rows(run_id, since=0, **kw):
    return _call("GET", f"/v1/runs/{run_id}/rows?since={int(since)}", **kw)


def all_rows(run_id, cap=5000, **kw):
    """Every row the run has produced, paged.

    The worker serves a window at a time so one request cannot be asked
    for a whole sweep at once; the results screen wants the lot, so it
    walks them. `cap` is the backstop against a pathological sweep.
    """
    out, since = [], 0
    while len(out) < cap:
        page = run_rows(run_id, since=since, **kw)
        rows = page.get("rows") or []
        out.extend(rows)
        since += len(rows)
        if not rows or since >= (page.get("total") or 0):
            break
    return out


def stop_run(run_id, **kw):
    return _call("POST", f"/v1/runs/{run_id}/stop", **kw)
