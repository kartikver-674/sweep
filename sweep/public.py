"""Public beta mode: the profile half of Sweep, safe to put on the internet.

Sweep is a single-operator console. `app.state` is ONE dict for the whole
process, `.env` holds the operator's Apify token, `POST /run` launches a
subprocess that spends real money, and profiles are Python files written
into the repo. Put that on a public URL unchanged and any visitor sees the
last résumé uploaded, spends the operator's balance, or deletes their key.

So public mode does not "harden" the whole app — it exposes a SUBSET:
upload a résumé, read it with the model, review the weights, take the
profile away. Everything else is refused by an allowlist, which fails
closed: a route added later is invisible to the public app until someone
puts it in PUBLIC_ENDPOINTS deliberately.

The three things that make the subset safe:

  isolation  `app.state` becomes a per-session view (SessionState), so the
             50 call sites in app.py keep working and no two visitors can
             see each other's résumé.
  no disk    the PDF is parsed from a temp file that is deleted in the same
             request, and the profile is handed back as a download instead
             of being written into profiles/.
  a budget   every extraction is two GPU calls on the operator's Modal
             account, so a beta code gates the door and a per-IP daily
             limit gates the spend.
"""

import contextlib
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import secrets
import threading
import time
from collections.abc import MutableMapping

from flask import (Response, current_app, has_request_context, redirect,
                   render_template, request, session, url_for)
from werkzeug.exceptions import NotFound

from sweep import worker_client

PUBLIC_ENV = "SWEEP_PUBLIC_MODE"
SECRET_ENV = "SECRET_KEY"
CODE_ENV = "SWEEP_BETA_CODE"
PER_IP_ENV = "SWEEP_BETA_DAILY_PER_IP"
TOTAL_ENV = "SWEEP_BETA_DAILY_TOTAL"
PROXIES_ENV = "SWEEP_TRUSTED_PROXIES"
# Whether a visitor needs the beta code at all (P4-S1B). ONLY an explicit "0"
# opens the door; unset, empty, "1", "false", "off" and anything else keep it
# shut. Opening therefore takes one deliberate operator action, and a deploy
# of this code without the variable is exactly today's locked beta. The code
# itself (CODE_ENV) stays configured while open: it is the emergency re-lock.
ACCESS_ENV = "SWEEP_ACCESS_LOCK"
# Sweeps started per canonical IP, and for everyone, per rolling day. A Sweep
# is one unit whatever it searches — one résumé or three, free or paid: the
# résumés were already counted once each, as derivations.
RUNS_PER_IP_ENV = "SWEEP_DAILY_RUNS_PER_IP"
RUNS_TOTAL_ENV = "SWEEP_DAILY_RUNS_TOTAL"
DEFAULT_RUNS_PER_IP = 5
DEFAULT_RUNS_TOTAL = 150

# How many proxies in front of us write X-Forwarded-For. Render documents
# two: "All inbound traffic to Render web services passes through
# Cloudflare's global network", and then Render's own load balancers.
#
# The count is the whole security property. ProxyFix reads the Nth entry
# from the RIGHT, and every trusted proxy appends the address it received
# from — so with N=2 we read what Cloudflare recorded, which is the real
# visitor. A visitor who sends their own X-Forwarded-For only prepends to
# the LEFT of that, where this never looks.
#
# Too low and every visitor reads as one Cloudflare edge IP and shares a
# single quota; too high and a client-supplied entry becomes the identity.
# Configurable because a different fronting setup is a different count.
DEFAULT_TRUSTED_PROXIES = 2

# What the public app is allowed to reach. Endpoint names, not paths, so a
# renamed URL cannot quietly widen this. Everything else — /key, /run,
# /stop, /results, /export, /rescore, the SSE feed — answers 404.
PUBLIC_ENDPOINTS = frozenset({
    "upload", "resume", "review", "derive_post", "review_post",
    "profile_done", "profile_download", "beta_gate", "healthz", "static",
    # The console's own sweep screens. They are reachable here because in
    # public mode they run against the Oracle worker (sweep/worker_link.py)
    # rather than a local subprocess — same pages, same free_only branches
    # they have always had.
    # configure_post is the preferences form's own submission — the
    # authoritative one. Without it here the gate below answers 404 and the
    # screen silently stops saving anything, which is the exact failure this
    # route was added to end.
    "key", "key_free", "key_post", "configure", "configure_post", "estimate",
    # V2-D1: stop using one of the visitor's OWN connected Apify accounts
    # before their sweep starts. Public-only; the console's key_remove, which
    # edits the operator's .env, stays below.
    "key_forget",
    "confirm", "run", "running", "progress", "stop", "results", "export",
    # The one status endpoint the global activity strip polls, for the
    # résumé half and the sweep half alike. Read-only, and answers only
    # about the caller's own session and their own run.
    "activity",
    # The header's feedback form (sweep/feedback.py): emails the operator
    # and keeps nothing. Behind the beta code like every screen it sits on.
    "feedback",
    # The 1-3 résumé setup's actions (P4-U1): rename, include or leave out,
    # reorder or remove one of this session's own résumés. 404 while the
    # Multi-Track product is off.
    "track_action",
    # P4-S1C: what crawlers may and may not fetch. Outside the door, like
    # /healthz — it says nothing about anyone.
    "robots_txt",
    # What Sweep keeps and for how long. Outside the door and indexable: it
    # is the same page for everyone and launch posts link straight to it.
    "privacy",
})

# Reachable locally, never here. Each one either spends the OPERATOR's
# money, edits their credentials, or reads their disk:
#
#   second_key, key_remove             the operator's Apify keys. POST
#                                      /key is public — it takes the
#                                      VISITOR's key, validates it, and
#                                      hands it to the worker without ever
#                                      writing it down.
#   rescore                            re-scores paid Apify datasets
#   merge                              folds this machine's earlier sweeps
#   applied                            writes an applied-state file
#   events                             SSE; public mode polls /progress
#                                      instead, see running.html
OPERATOR_ONLY = frozenset({"second_key", "key_remove", "rescore", "merge",
                           "applied", "events"})

# A session is a browser that uploaded a résumé. Two hours is longer than
# anyone spends on a three-screen flow and short enough that a shared
# laptop does not hand the next person a stranger's parse.
SESSION_TTL = 2 * 60 * 60
# Bounded because this lives in memory: a flood of cookie-less visitors
# must not be able to grow it without limit. Oldest goes first.
MAX_SESSIONS = 500

# Live rooms one canonical IP may hold at once (P4-S1B). A person with three
# tabs and a phone is a handful; a script minting sessions is not.
MAX_ROOMS_PER_IP = 10
# What makes a room somebody's work rather than an empty shell: a résumé, a
# derivation or a setup, a profile, a plan or run it is watching, or keys it
# connected. Rooms holding none of these are the first to go.
MEANINGFUL = ("resume_text", "tracks", "derived", "profile", "raw_plan",
              "proc", "byok_keys")

# One résumé is two qwen3:8b calls on a T4. Conservative on purpose: the
# operator's Modal budget is $25 and a beta is not a product launch.
DEFAULT_PER_IP = 3
DEFAULT_TOTAL = 60
DAY = 24 * 60 * 60
HOUR = 60 * 60

# POST /beta while the door is locked: WRONG attempts per canonical IP per
# window. Reserved before the comparison, handed back when the code is right.
BETA_ATTEMPTS = 10
BETA_WINDOW = 10 * 60
# Résumé PDFs parsed (P4-S1B): each attempt is a child process, so each one
# counts — read, refused as malformed, timed out or killed. Per canonical IP
# per hour and per day, and per session per hour: enough for a person trying
# three résumés and re-exporting one or two.
PARSES_PER_IP_HOUR = 10
PARSES_PER_IP_DAY = 30
PARSES_PER_SESSION_HOUR = 6
# Plans computed for the screens (P4-S1C): each one is an engine dry run on
# the worker. Per session and per canonical IP per minute; a plan served from
# the short cache (sweep/app.py, costed) is not a computation and not counted.
PLANS_PER_SESSION_MINUTE = 10
PLANS_PER_IP_MINUTE = 30
MINUTE = 60
# Polls (P4-S1C): the average interval a session's polling may not beat, per
# route, with a small burst for a second tab or a jittery timer. The running
# screen asks /progress every 4 s. /activity is asked by the status strip
# every 8 s AND, on the "reading your résumé" screen, every 3 s — one request
# per ~2.2 s from a single ordinary tab — so its floor is 2 s, not 3: a
# tighter one would refuse normal browsing.
POLL_INTERVALS = {"progress": 2.0, "activity": 2.0}
POLL_BURST = 3

# What crawlers are asked to leave alone: every route that is somebody's
# session. Advice, not a lock — the door and the allowlist are the locks.
ROBOTS_TXT = "\n".join(["User-agent: *", "Allow: /"] + [f"Disallow: {path}" for path in (
    "/beta", "/resume", "/review", "/derive", "/profile", "/tracks", "/key",
    "/configure", "/estimate", "/confirm", "/run", "/running", "/progress",
    "/activity", "/stop", "/results", "/export", "/feedback", "/healthz")]) + "\n"

AUDIT = logging.getLogger("sweep.audit")
AUDIT.setLevel(logging.INFO)
AUDIT.propagate = False


class BetaLimited(RuntimeError):
    """The visitor may not spend another extraction today."""


class PlanLimited(BetaLimited):
    """This session or network has asked for too many plans this minute."""


class PollLimit:
    """How often one session may poll one route: a token bucket, `burst`
    deep, refilled one token per `interval` seconds. take() is None when the
    poll may go ahead, else the seconds until it could (for Retry-After)."""

    def __init__(self, intervals=None, burst=POLL_BURST, clock=time.monotonic):
        self.intervals = dict(POLL_INTERVALS if intervals is None else intervals)
        self.burst, self._clock = burst, clock
        self._buckets = {}
        self._lock = threading.Lock()

    def take(self, route, key):
        interval = self.intervals[route]
        with self._lock:
            now = self._clock()
            if len(self._buckets) > 4096:
                stale = now - self.burst * max(self.intervals.values()) - 60
                for k in [k for k, (_t, at) in self._buckets.items() if at < stale]:
                    del self._buckets[k]
            tokens, at = self._buckets.get((route, key), (self.burst, now))
            tokens = min(self.burst, tokens + (now - at) / interval)
            if tokens < 1:
                self._buckets[(route, key)] = (tokens, now)
                return (1 - tokens) * interval
            self._buckets[(route, key)] = (tokens - 1, now)
            return None


class RoomsFull(RuntimeError):
    """No room could be made for this browser without dropping somebody's
    work: its network already holds MAX_ROOMS_PER_IP that all carry some."""


class NotConfigured(RuntimeError):
    """Public mode is missing a setting it refuses to start without."""


def enabled(env=None):
    """Public mode is opt-in and explicit. Anything but a clear yes is no,
    because the failure direction matters: a local console that thinks it
    is public loses routes, a public app that thinks it is local exposes
    the operator's money."""
    env = os.environ if env is None else env
    return (env.get(PUBLIC_ENV) or "").strip().lower() in {"1", "true", "yes", "on"}


def access_open(env=None):
    """Whether the public app lets a visitor in without the beta code.

    Fail closed: ONLY "0" (surrounding spaces ignored) opens it. Anything
    else — the variable unset, empty, "1", "false", "off", a typo — is the
    locked beta, so no misconfiguration can open the door by accident.
    """
    env = os.environ if env is None else env
    return (env.get(ACCESS_ENV) or "").strip() == "0"


def session_id():
    """This browser's opaque id, in the SIGNED COOKIE.

    The cookie is the only part of a visitor's session that survives a
    Render restart — `SessionStore` below is process memory and does not.
    So anything that must outlive a redeploy hangs off this.

    Minted permanent: the same two-hour, refreshed-on-every-request cookie a
    beta grant has always made. A visitor to an open door never posts the
    code, and a session that was not permanent would be re-signed only when
    it changed and expire two hours after that, mid-sweep.
    """
    sid = session.get("sid")
    if not sid:
        sid = secrets.token_urlsafe(18)
        session["sid"] = sid
        session.permanent = True
    return sid


def limiter_key(addr):
    """One visitor as every per-IP limit counts them (P4-S1B).

    `addr` is what ProxyFix left in remote_addr. IPv4 is itself; an
    IPv4-mapped IPv6 address (::ffff:203.0.113.5) is the IPv4 it maps; any
    other IPv6 address is its /64, because a single subscriber is handed a
    whole /64 and could otherwise take a fresh quota from each of 2**64
    addresses. Anything that is not an address at all shares ONE key,
    "invalid" — never a key per garbage string, and never no limit.
    """
    try:
        ip = ipaddress.ip_address((addr or "").strip())
    except ValueError:
        return "invalid"
    if ip.version == 6:
        if ip.ipv4_mapped is not None:
            return str(ip.ipv4_mapped)
        # Built from the integer so a zone id (fe80::1%eth0) is dropped too.
        return str(ipaddress.IPv6Network(((int(ip) >> 64) << 64, 64)))
    return str(ip)


def pseudonym(kind, value):
    """A short, stable stand-in for a session id or an IP key in the audit
    log: an HMAC under SECRET_KEY, so lines about one visitor correlate and
    nobody reading the log can turn them back into the visitor."""
    secret = current_app.secret_key
    secret = secret.encode() if isinstance(secret, str) else (secret or b"")
    return hmac.new(secret, f"sweep-log|{kind}|{value}".encode(),
                    hashlib.sha256).hexdigest()[:12]


def audit(event, **fields):
    """One JSON line for an expensive or security-relevant event (P4-S1B).

    Only what an operator needs to see abuse: the event, the route, an
    outcome, a category, sizes and durations, the run id — plus pseudonyms
    for the session and the canonical IP. Never résumé text, a code, a key,
    a token or a header. Logging can never break the request it describes.
    """
    try:
        record = {"event": event}
        if has_request_context():
            sid = session.get("sid")
            record.update(route=request.endpoint,
                          session=pseudonym("session", sid) if sid else None,
                          ip=pseudonym("ip", client_ip()))
        record.update(fields)
        if not AUDIT.handlers and not current_app.testing:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
            AUDIT.addHandler(handler)
        AUDIT.info(json.dumps(record, sort_keys=True, default=str))
    except Exception:
        pass


def owner_for_session(secret=None):
    """The capability that proves a worker run is this browser's.

    Derived, not stored: HMAC of the cookie's own session id under
    Render's SECRET_KEY. Two consequences, both deliberate —

      * a new Render process re-derives it from the cookie alone, so a
        restart or a redeploy does not orphan somebody's running sweep;
      * Oracle never sees the raw session id, only a value that is
        useless without the key that made it.

    It is a capability, not a secret worth protecting on its own: holding
    it still gets you nowhere without the worker's bearer token, which
    never leaves Render. The Apify token has no business here or anywhere
    near a cookie.
    """
    if secret is None:
        from flask import current_app
        secret = current_app.secret_key
    if isinstance(secret, str):
        secret = secret.encode()
    return hmac.new(secret, b"sweep-run-owner|" + session_id().encode(),
                    hashlib.sha256).hexdigest()


# A Multi-Track run's correlation, beside run_id in the cookie (remember_run).
RUN_MULTI_KEYS = ("run_tracks", "run_plan_hash")


def remember_run(run_id, tracks=None, plan_hash=None):
    """Keep the run id where a restart cannot lose it: the cookie.

    Opaque and not authority on its own — every worker call needs the
    bearer token AND the owner above — which is what makes it safe to
    hand to the browser.

    A Multi-Track run also keeps, beside it (design §N.1, R2), its
    [[track id, label], …] in track order and the plan hash it was started
    with: what its status must match after a restart. Ids, labels and a
    digest — never a track's data. A one-track run writes neither, so its
    cookie is exactly today's.
    """
    session["run_id"] = run_id
    if tracks is not None:
        session["run_tracks"] = [[tid, label] for tid, label in tracks]
        session["run_plan_hash"] = plan_hash
    else:
        for key in [k for k in RUN_MULTI_KEYS if k in session]:
            session.pop(key)
    return run_id


def current_run_id():
    return session.get("run_id")


def current_run_tracks():
    """(track ids, plan hash) of this browser's Multi-Track run, or None for
    a one-track run."""
    tracks = session.get("run_tracks")
    if not tracks:
        return None
    return [tid for tid, _label in tracks], session.get("run_plan_hash")


def run_label(name, n):
    """A track's label as the cookie keeps it (design §N.1): stripped, 1 to
    40 printable characters, else "Résumé <n>"."""
    name = name.strip() if isinstance(name, str) else ""
    return name if 0 < len(name) <= 40 and name.isprintable() else f"Résumé {n}"


def run_track_labels():
    """[(track id, label)] of this browser's Multi-Track run in run order, each
    label re-checked on the way out as it was on the way in; None for a
    one-track run."""
    tracks = session.get("run_tracks")
    if not tracks:
        return None
    return [(tid, run_label(label, n)) for n, (tid, label) in enumerate(tracks, 1)]


def relabel_run_track(tid, label):
    """A rename of one of this run's tracks, after it started: its label in
    run_tracks and nothing else — never an id, the run or its plan hash."""
    tracks = session.get("run_tracks")
    if tracks and any(t == tid for t, _label in tracks):
        session["run_tracks"] = [[t, label if t == tid else old] for t, old in tracks]


def forget_run():
    session.pop("run_id", None)
    for key in RUN_MULTI_KEYS:
        session.pop(key, None)


class SessionStore:
    """Per-session state, in memory, bounded and expiring.

    In memory because the public flow needs nothing to survive a restart:
    a visitor who loses their parse uploads the PDF again. That is also
    why Render's ephemeral disk is not a problem for this subset — and why
    the public app must run ONE worker, since this is not shared between
    processes.

    Allocated lazily (P4-S1B): READING state never creates a room — or a
    session id — so a crawler or a script fetching pages holds no memory
    here. A room is made by the first WRITE, which in practice is a résumé
    being read. Each is tagged with its canonical IP, which may hold at most
    `per_ip` at once, and when anything has to go, rooms with nobody's work
    in them (MEANINGFUL) go before rooms that have some.
    """

    def __init__(self, ttl=SESSION_TTL, cap=MAX_SESSIONS, clock=time.monotonic,
                 per_ip=MAX_ROOMS_PER_IP):
        self._rooms = {}
        self._ttl, self._cap, self._clock, self._per_ip = ttl, cap, clock, per_ip
        self._lock = threading.Lock()

    def _sid(self):
        return session_id()

    def peek(self):
        """This browser's dict, or an empty stand-in when it has none. Never
        allocates: the stand-in is thrown away, and anything written goes
        through room()."""
        sid = session.get("sid")
        room = self._rooms.get(sid) if sid else None
        if room is None:
            return {}
        now = self._clock()
        if now - room["seen"] > self._ttl:
            with self._lock:
                if self._rooms.get(sid) is room:
                    del self._rooms[sid]
            return {}
        room["seen"] = now
        return room["data"]

    def room(self):
        """This browser's own dict, created on first write. RoomsFull when
        its IP already holds `per_ip` rooms that all carry somebody's work."""
        now = self._clock()
        sid = self._sid()
        with self._lock:
            room = self._rooms.get(sid)
            if room is not None and now - room["seen"] > self._ttl:
                del self._rooms[sid]
                room = None
            if room is None:
                self._expire(now)
                ip = client_ip()
                self._make_space_for(ip)
                room = self._rooms[sid] = {"seen": now, "data": {}, "ip": ip}
                # After the insert, never before: evicting first leaves room
                # for one more and the cap is really cap + 1. This room is
                # never the one dropped.
                self._evict(keep=sid)
            room["seen"] = now
        return room["data"]

    @staticmethod
    def _empty(room):
        return not any(room["data"].get(key) for key in MEANINGFUL)

    def _expire(self, now):
        for sid in [s for s, r in self._rooms.items()
                    if now - r["seen"] > self._ttl]:
            del self._rooms[sid]

    def _make_space_for(self, ip):
        """Room under this IP's cap, by dropping its oldest EMPTY room — never
        one holding a résumé, a setup or a run. None to drop: RoomsFull."""
        mine = [s for s, r in self._rooms.items() if r.get("ip") == ip]
        if len(mine) < self._per_ip:
            return
        empty = [s for s in mine if self._empty(self._rooms[s])]
        if not empty:
            raise RoomsFull("this network holds as many sessions as it may")
        del self._rooms[min(empty, key=lambda s: self._rooms[s]["seen"])]

    def _evict(self, keep):
        while len(self._rooms) > self._cap:
            others = [s for s in self._rooms if s != keep]
            empty = [s for s in others if self._empty(self._rooms[s])]
            victim = min(empty or others, key=lambda s: self._rooms[s]["seen"])
            del self._rooms[victim]

    def __len__(self):
        return len(self._rooms)


class SessionState(MutableMapping):
    """`app.state`, per browser.

    A mapping rather than a rewrite of app.py: the routes do
    state.get(...), state[...] = ..., setdefault and pop, and every one of
    those lands in the calling session's own dict. Nothing in app.py has
    to know which mode it is running in.

    Reads go through peek() and never allocate; only a write makes a room
    (MutableMapping's get, pop-with-default and `in` are all reads here).
    """

    def __init__(self, store):
        self._store = store

    def __getitem__(self, key):
        return self._store.peek()[key]

    def __setitem__(self, key, value):
        self._store.room()[key] = value

    def __delitem__(self, key):
        del self._store.peek()[key]

    def __iter__(self):
        return iter(self._store.peek())

    def __len__(self):
        return len(self._store.peek())

    def copy(self):
        """This browser's dict, copied in one step, like a plain dict's own
        copy(). dict(state) would walk it a key at a time, and a Save
        replacing it in the middle of that walk tears the copy."""
        return dict(self._store.peek())

    def update(self, *args, **kwargs):
        """Every key in ONE step, like a plain dict's update(). The inherited
        one sets them a key at a time, and a copy() taken in between sees a
        session that is half of one thing and half of another.

        No lock is taken here or in copy(): each is a single dict operation,
        atomic in CPython (with or without the GIL), and room() has released
        the store's lock before the update runs. Nothing is held while
        another lock is asked for, so there is no order to invert."""
        self._store.room().update(*args, **kwargs)


class DailyLimit:
    """Complete résumé derivations per IP per day, and a ceiling for
    everyone together.

    The UNIT is one derivation, not one model call. A profile is two
    inference calls — fields, then employment — and a quota counted per
    call could let someone through the first and refuse them the second,
    leaving them with a half-read résumé and one call's worth of GPU
    spent for nothing. `metered` wraps the whole derivation, so both
    calls happen inside one reserved slot.

    Reserved, not counted afterwards: check-then-spend is a race, and
    with eight gunicorn threads it is a race that a double-click wins.
    A slot is taken BEFORE the model is asked, so two concurrent requests
    cannot both see the last slot as free. It is NOT given back when the
    derivation fails (P4-S1B): a failure has already spent the GPU time,
    and a refund made the failing résumé a free, endless supply of it.

    The same mechanism, keyed on other things, counts beta-code attempts,
    PDF parses and Sweeps. `messages` are (the everyone-together refusal,
    the per-key one, which may say {n}); `total=None` is no shared ceiling.
    """

    MESSAGES = ("Sweep has read as many résumés as it can today. Nothing "
                "is wrong with your file. Try again tomorrow.",
                "You've reached today's limit of {n} résumé reads from your "
                "network. Nothing is wrong with your file. Try again tomorrow.")

    def __init__(self, per_ip=DEFAULT_PER_IP, total=DEFAULT_TOTAL,
                 clock=time.time, window=DAY, messages=None):
        self.per_ip, self.total = per_ip, total
        self._clock, self._window = clock, window
        self._messages = messages or self.MESSAGES
        self._lock = threading.Lock()
        self._slots = {}

    def _prune(self, now):
        for ip in list(self._slots):
            kept = [at for at in self._slots[ip] if now - at < self._window]
            if kept:
                self._slots[ip] = kept
            else:
                del self._slots[ip]

    def taken(self, ip=None):
        """Slots in use — reserved or completed. For tests and /healthz."""
        with self._lock:
            self._prune(self._clock())
            if ip is None:
                return sum(len(v) for v in self._slots.values())
            return len(self._slots.get(ip, ()))

    def reserve(self, ip):
        """Take one derivation's worth of quota, or raise BetaLimited.

        The whole decision happens under one lock: prune, count, and
        take. Nothing between the count and the take, which is exactly
        where a concurrent request would otherwise slip through.
        """
        with self._lock:
            now = self._clock()
            self._prune(now)
            if (self.total is not None
                    and sum(len(v) for v in self._slots.values()) >= self.total):
                raise BetaLimited(self._messages[0])
            if len(self._slots.get(ip, ())) >= self.per_ip:
                raise BetaLimited(self._messages[1].format(n=self.per_ip))
            self._slots.setdefault(ip, []).append(now)
            return (ip, now)

    def release(self, ticket):
        """Give a reserved slot back, for work that never happened: a Sweep
        the worker did not create, a parse another limit refused. Never for
        a derivation or a parse that ran and failed."""
        ip, at = ticket
        with self._lock:
            held = self._slots.get(ip)
            if held and at in held:
                held.remove(at)
                if not held:
                    del self._slots[ip]


def metered(derive, limit):
    """One derivation ATTEMPT, behind one slot of the daily limit.

    Wrapping the derivation rather than the route: POST /derive is the
    route that means to spend, but POST /review reaches the same function,
    and a limit that a second route walks around is not a limit. Wrapping
    it here also fixes the unit — everything inside, both model calls and
    any retry the inference client makes included, is one usage.

    Admitted means consumed (P4-S1B). Whatever happens inside — a profile,
    an escalation after both model calls, a timeout, a malformed answer —
    the slot stays taken, per IP and in the global total alike, so failing
    on purpose is no cheaper than succeeding. Everything a request can fail
    on BEFORE this (no résumé, an unknown track, a parse in flight) never
    reaches it and costs nothing.
    """
    def guarded(resume_text, prefs):
        try:
            limit.reserve(client_ip())
        except BetaLimited:
            audit("derive", outcome="refused")
            raise
        audit("derive", outcome="admitted")
        try:
            derived = derive(resume_text, prefs)
        except Exception as exc:
            audit("derive", outcome="failed", category=failure_category(exc))
            raise
        audit("derive", outcome="ok")
        return derived
    return guarded


def failure_category(exc):
    """A class name, and the inference category when there is one — never
    the exception's text, which can quote the model or a URL."""
    category = getattr(exc, "category", None)
    name = type(exc).__name__
    return f"{name}:{category}" if isinstance(category, str) else name


def client_ip():
    """The visitor as every per-IP limit counts them: limiter_key() of the
    address the trusted proxies reported.

    ProxyFix has already rewritten remote_addr by the time this runs, and
    it only ever reads entries written by the trusted hops — see
    DEFAULT_TRUSTED_PROXIES. Nothing here reads a raw header. The one
    funnel for the derivation, feedback, beta-attempt, upload and run
    limits and the room cap, so they cannot disagree about who someone is.
    """
    return limiter_key(request.remote_addr)


def reserve_all(pairs):
    """[(limit, key)] taken together or not at all: a refusal by any gives
    back what the ones before it took, then raises BetaLimited."""
    taken = []
    try:
        for limit, key in pairs:
            taken.append((limit, limit.reserve(key)))
    except BetaLimited:
        for limit, ticket in taken:
            limit.release(ticket)
        raise
    return taken


def admit_parse(app):
    """Count one PDF parse against this visitor's upload limits, before the
    reader starts. None when admitted; the refusal's sentence otherwise.
    Never given back: from here a child process does the work."""
    ip_hour, ip_day, per_session = app.upload_limits
    try:
        reserve_all([(ip_hour, client_ip()), (ip_day, client_ip()),
                     (per_session, "session:" + session_id())])
    except BetaLimited as exc:
        audit("parse", outcome="refused")
        return str(exc)
    return None


def trusted_proxies(env=None):
    env = os.environ if env is None else env
    raw = (env.get(PROXIES_ENV) or "").strip()
    if not raw:
        return DEFAULT_TRUSTED_PROXIES
    try:
        return max(1, int(raw))
    except ValueError:
        raise NotConfigured(f"{PROXIES_ENV}={raw!r} is not a whole number") from None


def looks_like_pdf(path):
    """A PDF says so in its first bytes. Cheap, and it keeps the parser
    from being handed whatever a stranger felt like uploading."""
    try:
        with open(path, "rb") as fh:
            return fh.read(5) == b"%PDF-"
    except OSError:
        return False


def secret_key(env=None):
    env = os.environ if env is None else env
    key = (env.get(SECRET_ENV) or "").strip()
    if not key:
        raise NotConfigured(
            f"{SECRET_ENV} is not set. Public mode signs the session cookie "
            f"that keeps one visitor's résumé away from another's, so it "
            f"will not start without a stable one.")
    return key


def beta_code(env=None):
    env = os.environ if env is None else env
    code = (env.get(CODE_ENV) or "").strip()
    if not code:
        raise NotConfigured(
            f"{CODE_ENV} is not set. Every résumé read costs GPU money on "
            f"the operator's account, so public mode will not run without "
            f"a code on the door.")
    return code


def _whole(env, name, fallback):
    raw = (env.get(name) or "").strip()
    if not raw:
        return fallback
    try:
        return max(0, int(raw))
    except ValueError:
        raise NotConfigured(f"{name}={raw!r} is not a whole number") from None


def limit_from_env(env=None):
    """The daily derivation budget, from the environment: ADMITTED attempts
    per canonical IP and for everyone, per rolling day, failures included
    (P4-S1B). Render sets both; the defaults are deliberately small."""
    env = os.environ if env is None else env
    return DailyLimit(_whole(env, PER_IP_ENV, DEFAULT_PER_IP),
                      _whole(env, TOTAL_ENV, DEFAULT_TOTAL))


def run_limit_from_env(env=None):
    """Sweeps per canonical IP and for everyone, per rolling day."""
    env = os.environ if env is None else env
    return DailyLimit(
        _whole(env, RUNS_PER_IP_ENV, DEFAULT_RUNS_PER_IP),
        _whole(env, RUNS_TOTAL_ENV, DEFAULT_RUNS_TOTAL),
        messages=("Sweep has run as many searches as it can today. Nothing "
                  "has been charged. Try again tomorrow.",
                  "Sweep has started {n} searches from your network today, "
                  "which is the most it runs for one network in a day. "
                  "Nothing has been charged. Try again tomorrow."))


def plan_limits():
    """(per session, per canonical IP) plan computations per minute."""
    wait = "Wait a minute and try again. Nothing has been charged."
    return (
        DailyLimit(PLANS_PER_SESSION_MINUTE, None, window=MINUTE, messages=(
            "", "Sweep has worked out {n} search plans for you in the last "
                "minute. " + wait)),
        DailyLimit(PLANS_PER_IP_MINUTE, None, window=MINUTE, messages=(
            "", "Sweep has worked out {n} search plans for your network in "
                "the last minute. " + wait)))


def admit_plan(app):
    """Count one plan computation — an engine dry run on the worker — or
    raise PlanLimited before it starts. Never given back: once asked, the
    worker does the work."""
    per_session, per_ip = app.plan_limits
    try:
        reserve_all([(per_session, "session:" + session_id()),
                     (per_ip, client_ip())])
    except BetaLimited as exc:
        audit("plan", outcome="rate_limited")
        raise PlanLimited(str(exc)) from None
    audit("plan", outcome="computed")


def upload_limits():
    """(per IP per hour, per IP per day, per session per hour) for PDF parses."""
    return (
        DailyLimit(PARSES_PER_IP_HOUR, None, window=HOUR, messages=(
            "", "Sweep has read {n} résumés from your network in the last "
                "hour. Try again in a little while.")),
        DailyLimit(PARSES_PER_IP_DAY, None, window=DAY, messages=(
            "", "Sweep has read {n} résumés from your network today. Try "
                "again tomorrow.")),
        DailyLimit(PARSES_PER_SESSION_HOUR, None, window=HOUR, messages=(
            "", "You have uploaded {n} résumés in the last hour. Try again "
                "in a little while.")))


def beta_grant(secret, code):
    """What a correct code leaves in the cookie: HMAC(SECRET_KEY, code).

    Tied to the code, so rotating SWEEP_BETA_CODE revokes every grant made
    under the old one — no SECRET_KEY rotation, no session store to clear.
    Keyed, so the value in a (readable, signed) cookie is no help to anyone
    trying to guess the code offline.
    """
    secret = secret.encode() if isinstance(secret, str) else secret
    return hmac.new(secret, b"sweep-beta-grant|" + code.encode(),
                    hashlib.sha256).hexdigest()


def harden(app, env=None, store=None, limit=None):
    """Turn a local console into the public profile app.

    Called from create_app only when `enabled()`. Everything here either
    narrows what is reachable or isolates what is stored; nothing changes
    how a résumé is read, which is the whole point of the Modal work this
    sits on top of.
    """
    env = os.environ if env is None else env
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.secret_key = secret_key(env)
    # Required locked or open: while open it is the emergency re-lock.
    code = beta_code(env)
    grant = beta_grant(app.secret_key, code)
    app.config["PUBLIC_MODE"] = True
    # Read once, at start-up: re-locking is setting SWEEP_ACCESS_LOCK back
    # (or removing it) and restarting, and nothing else.
    app.config["ACCESS_OPEN"] = access_open(env)
    # Without this the app sees Render's proxy instead of the visitor and
    # http:// instead of https://.
    #
    # x_for counts the hops that WRITE the header (Cloudflare, then
    # Render's load balancer): read the entry Cloudflare wrote, not the
    # one a client can prepend. x_proto is 1 because the scheme header
    # carries one value written by the nearest proxy.
    #
    # x_host is 0 deliberately: X-Forwarded-Host would let a client
    # rewrite request.host, and request.host is what the cross-site check
    # below compares an Origin against — trusting it would hand an
    # attacker the means to match it. Render passes the real Host through.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=trusted_proxies(env),
                            x_proto=1, x_host=0, x_port=0, x_prefix=0)
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=True,
        # Strict, with the CSRF check below as the belt to its braces: the
        # public flow is three same-origin POSTs and never a cross-site
        # landing, so nothing legitimate is lost.
        SESSION_COOKIE_SAMESITE="Strict",
        PERMANENT_SESSION_LIFETIME=SESSION_TTL,
    )

    # Which market decides skill weights here, read ONCE at start-up: on
    # a fresh clone or Render there is no output/, so the shipped table
    # answers, and a health check should be able to say so. Reading it per
    # request would rescan every CSV a real corpus holds.
    import corpus_signal
    app.config["MARKET_SIGNAL_SOURCE"] = corpus_signal.market_signal(
        app.config.get("OUTPUT_DIR"))[1]
    # The same question for TITLES, which had no frozen fallback until a
    # real upload proved it needed one: no output/ meant no role_keywords
    # for anyone whose own titles are filtered out, and that is every
    # internship-only résumé. Read once here for the same reason as above —
    # market_rows() walks every CSV a live corpus holds.
    #
    # The row COUNT as well as the source: "frozen" alone cannot tell a
    # shipped corpus from a shipped empty one, and this is the diagnostic
    # that says whether the artifact actually made it into the build.
    import local_search
    _title_rows, _title_source = local_search.market_rows(
        app.config.get("OUTPUT_DIR"))
    app.config["TITLE_CORPUS_SOURCE"] = _title_source
    app.config["TITLE_CORPUS_ROWS"] = len(_title_rows)

    store = store if store is not None else SessionStore()
    app.session_store = store
    app.state = SessionState(store)
    # create_app already built one and wrapped `derive` in it — replacing
    # it here would meter a limit nothing consults.
    if limit is not None:
        app.beta_limit = limit
    elif not hasattr(app, "beta_limit"):
        app.beta_limit = limit_from_env(env)
    app.run_limit = run_limit_from_env(env)
    app.upload_limits = upload_limits()
    app.plan_limits = plan_limits()
    app.poll_limit = PollLimit()
    app.beta_attempts = DailyLimit(BETA_ATTEMPTS, None, window=BETA_WINDOW)

    def admitted():
        """Past the door: it is open, or this cookie holds the grant for the
        CURRENT code. A bare beta_ok=True from before grants existed is not
        a grant, and a grant for a rotated code no longer matches."""
        if app.config["ACCESS_OPEN"]:
            return True
        given = session.get("beta_grant")
        return (isinstance(given, str) and given.isascii()
                and hmac.compare_digest(given, grant))

    # A profile is handed back, never written into profiles/: that
    # directory is a shared namespace on an ephemeral disk, so one
    # visitor's name could replace another's and neither would survive a
    # restart.
    def keep_profile(name, source):
        # The visitor's copy never carries the reading's own notes or the scanner's reasons (D7C):
        # /profile prints this and /profile.py serves it.
        from sweep.app import make_profile
        app.state["profile_source"] = make_profile.public_source(source)
        return None

    app.write_profile = keep_profile
    # "Continue to job search" leads to the console's own source-choice
    # screen, which is where a visitor picks the free sweep.
    app.config["AFTER_REVIEW_ENDPOINT"] = "key"
    # The journey a VISITOR is walking, which is not the one the routes
    # describe. Seven numbered steps is the operator's decomposition —
    # "Free or paid", "Configure", "Confirm" and "Running" are four
    # announcements of a single thing a job seeker calls "searching". The
    # routes are untouched; only what the header says about them changes.
    from sweep.logic import PUBLIC_STAGES
    app.config["STEPS"] = PUBLIC_STAGES

    @app.before_request
    def poll_pace():
        """P4-S1C: a session polling faster than its screens ever do is told
        to wait (429, Retry-After) BEFORE anything below can ask the worker.
        Keyed on the signed cookie's session id; a browser with none has no
        run to ask about, and its poll costs nothing."""
        route, sid = request.endpoint, session.get("sid")
        if route not in POLL_INTERVALS or not sid:
            return None
        wait = app.poll_limit.take(route, sid)
        if wait is None:
            return None
        audit("poll", outcome="rate_limited")
        refused = Response(json.dumps({"error": "Too many requests. Slow down."}),
                           status=429, mimetype="application/json")
        refused.headers["Retry-After"] = str(max(1, int(wait + 0.999)))
        return refused

    @app.before_request
    def resume_a_running_sweep():
        """Oracle keeps sweeping while Render redeploys; the cookie keeps
        the run id. Put back what the screens need before they render."""
        if request.endpoint in PUBLIC_ENDPOINTS and admitted():
            from sweep import worker_link
            with contextlib.suppress(Exception):
                worker_link.rehydrate(app)
        return None

    @app.before_request
    def gate():
        # 1. Only the public subset exists. Unknown endpoint (404 already)
        #    falls through to Flask's own handler.
        if request.endpoint is not None and request.endpoint not in PUBLIC_ENDPOINTS:
            return Response("Not found.", status=404, mimetype="text/plain")
        # 2. Same-origin for anything that changes state. Origin is sent by
        #    every browser on a cross-site POST, and a forged one cannot be
        #    set by a page — which is exactly the attack this stops.
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("Origin")
            if origin and origin.split("//")[-1] != request.host:
                return Response("Cross-site request refused.", status=403,
                                mimetype="text/plain")
        # 3. The door — the ONLY step an open door (SWEEP_ACCESS_LOCK=0)
        #    skips. Steps 1 and 2 hold either way.
        if request.endpoint in {"beta_gate", "healthz", "static", "robots_txt", "privacy"}:
            return None
        if not admitted():
            return redirect(url_for("beta_gate"))
        return None

    @app.after_request
    def private_by_default(response):
        """P4-S1C. Every answer here but the static files and robots.txt is
        about one browser's session — a résumé, a plan, a run, its jobs — so
        no cache anywhere may keep it (no-store), and none but the front door
        belongs in a search index (noindex). The rest harden every page:
        no sniffing, no framing (one policy, said the old way and the new),
        no full URL in a Referer to a job site, and HSTS where the request
        really arrived over HTTPS."""
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
        if request.is_secure:
            headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        if request.endpoint not in ("static", "robots_txt"):
            headers["Cache-Control"] = "no-store"
            if request.endpoint not in ("upload", "privacy"):
                headers["X-Robots-Tag"] = "noindex"
        return response

    @app.get("/robots.txt")
    def robots_txt():
        return Response(ROBOTS_TXT, mimetype="text/plain")

    @app.get("/privacy")
    def privacy():
        return render_template("privacy.html", **app.shell(None))

    @app.get("/beta")
    @app.post("/beta")
    def beta_gate():
        if app.config["ACCESS_OPEN"]:
            # Nothing to enter, and no grant is handed out for nothing: an
            # open door must not leave cookies that outlive a re-lock.
            return redirect(url_for("upload"))
        if request.method == "POST":
            # Reserved BEFORE the code is looked at, so a network that has
            # used its attempts cannot test even one more guess. A right code
            # hands its attempt back — only wrong ones count, so a campus of
            # people entering it is never locked out — and a refusal says
            # nothing about how close a guess was.
            try:
                attempt = app.beta_attempts.reserve(client_ip())
            except BetaLimited:
                audit("beta", outcome="rate_limited")
                return render_template(
                    "beta.html", error="Too many attempts. Wait a few "
                                       "minutes and try again."), 429
            given = (request.form.get("code") or "").strip()
            # Constant time, and as bytes: compare_digest refuses a non-ASCII
            # str with a TypeError, which a pasted "é" would have made a 500.
            if hmac.compare_digest(given.encode(), code.encode()):
                app.beta_attempts.release(attempt)
                session["beta_grant"] = grant
                session.pop("beta_ok", None)
                session.permanent = True
                audit("beta", outcome="granted")
                return redirect(url_for("upload"))
            audit("beta", outcome="refused")
            return render_template("beta.html",
                                   error="That code is not right."), 403
        if admitted():
            return redirect(url_for("upload"))
        return render_template("beta.html")

    @app.get("/healthz")
    def healthz():
        """Render's health check. Cheap on purpose: it touches no model,
        no session and no disk, so a health probe can never wake the GPU
        or cost anything.

        The engine block is here so a rollback can be CONFIRMED rather
        than assumed. It reports what this process would derive with —
        the worker reports its own, and a profile's own stamp still beats
        both. No secret, no path, no user data.
        """
        import make_profile
        import skill_concepts

        from sweep import safe_pdf, worker_link
        effective = skill_concepts.effective()
        return {"status": "ok", "mode": "public-beta",
                "sessions": len(store),
                # P4-S1B: aggregates only — never a per-IP or per-session
                # figure, a grant, or anything about the code.
                "access": "open" if app.config["ACCESS_OPEN"] else "locked",
                "session_rooms": len(store),
                "derivations_today": app.beta_limit.taken(),
                "runs_today": app.run_limit.taken(),
                "parses_in_flight": safe_pdf.in_flight(),
                "market_signal_source": app.config["MARKET_SIGNAL_SOURCE"],
                "title_corpus_source": app.config["TITLE_CORPUS_SOURCE"],
                "title_corpus_rows": app.config["TITLE_CORPUS_ROWS"],
                "derivation_engine": effective["version"],
                "engine_source": effective["source"],
                "role_families": effective["roles"],
                # Phase 0b: whether the worker is told that engine (on) or
                # stamps its own default (off) — so activating or rolling back
                # the v1 -> v2 switch can be confirmed, not assumed.
                "engine_propagation": worker_link.sends_engine(),
                "profile_schema": make_profile.PROFILE_SCHEMA}

    @app.errorhandler(worker_client.WorkerError)
    def sweep_service_trouble(exc):
        """The worker refused or could not be reached.

        Almost always one thing: the visitor's Apify key is no longer held
        — spent on a run, or aged out of the worker's memory — because it
        was deliberately never written down. So this lands them back on the
        screen where they choose free or paid, with the reason, rather than
        on a 500 that tells them nothing.
        """
        from flask import render_template

        from sweep.logic import paid_sites, site_label
        needs_key = isinstance(exc, worker_client.NeedsKey)
        gone = isinstance(exc, worker_client.RunNotFound)
        busy = isinstance(exc, worker_client.QueueFull)
        if busy:
            # P4-S1B: the worker's line is full, so no run exists. The keys
            # the visitor connected are still held there, so they are kept
            # here too: trying again later needs nothing pasted again.
            message = ("Sweep is running as many searches as it can right now, "
                       "and there is no room in the queue for yours. Nothing "
                       "has been charged. Try again in a few minutes.")
        elif isinstance(exc, worker_client.PaidUnavailable):
            message = ("Paid searches are temporarily unavailable. Nothing has "
                       "been charged. You can run a Quick Sweep now, or "
                       "come back later.")
        elif needs_key:
            # V2-D1: nothing the worker still holds for them; the accounts this
            # session lists must go with it, or pasting a key again would be
            # refused as a duplicate of one that no longer exists.
            app.state.pop("byok_keys", None)
            app.state.pop("run_key_ids", None)
            message = (
                "Your Apify key is not held any more — it is used for one "
                "sweep and never saved. Paste it again for a Deep Sweep, or "
                "run a Quick Sweep.")
        elif gone:
            # The worker deliberately does not distinguish "expired" from
            # "not yours" (worker_client.RunNotFound), so this must cover
            # both without claiming either. The TTL is the honest reason to
            # name, because it is the one a visitor can act on.
            message = (
                "That sweep is no longer available — sweeps are kept for "
                "48 hours. Nothing has been charged. Start a new one below.")
        else:
            # Never str(exc) here: the client's messages name "the sweep
            # worker", which is our infrastructure and not a visitor's
            # concern.
            message = ("Sweep's search service is not responding just now. "
                       "Nothing has been charged. Try again in a minute.")
        return render_template("key.html", **app.shell(
            "key", paid=[site_label(s) for s in paid_sites()],
            error=message)), (400 if needs_key else
                              503 if busy or isinstance(exc, worker_client.PaidUnavailable)
                              else 502)

    @app.errorhandler(RoomsFull)
    def no_room(exc):
        """This network already holds its share of sessions, every one with
        somebody's work in it — none is dropped to make an empty one."""
        audit("room", outcome="refused")
        return app.upload_screen(
            error="Too many Sweep sessions are open from your network right "
                  "now. Finish or close one, or try again later."), 429

    @app.errorhandler(NotFound)
    def not_found(exc):
        """An address that matches no route, on the A-skin's own page (A10).

        Only the router's NotFound: a view that aborts 404 itself and a
        /static miss keep the answer they always had, and the operator-only
        routes never get this far — gate() has already given them their
        plain-text 404. The page never names the address that was asked for."""
        if exc is not request.routing_exception or request.path.startswith("/static/"):
            return exc
        return render_template("not_found.html", **app.shell(None)), 404

    @app.errorhandler(worker_client.PlanChanged)
    def plan_changed(exc):
        """A Multi-Track Sweep's approved plan went stale before it could
        run. Nothing ran; the approval is dropped and Confirm plans the Sweep
        again, from the session as it now stands."""
        from sweep import worker_link
        worker_link.invalidate(app.state)
        return redirect(url_for("confirm"))

    @app.errorhandler(BetaLimited)
    def beta_limited(exc):
        """A daily limit, on the screen a visitor starts from, in words that
        are true whether the door is open or locked (P4-S1C)."""
        return app.upload_screen(error=str(exc)), 429

    @app.errorhandler(PlanLimited)
    def plan_limited(exc):
        """Too many plans this minute: back on the search step, told to wait.
        Nothing was priced, so nothing on that screen is stale."""
        return app.key_screen(error=str(exc)), 429

    return app
