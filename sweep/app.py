"""Routes. Business logic lives in sweep.plan and sweep.runs."""

import contextlib
import contextvars
import hashlib
import hmac
import math
import os
import re
import secrets
import sys
import tempfile
import threading
from datetime import datetime
from decimal import ROUND_CEILING, Decimal

from flask import (Flask, Response, abort, g, redirect, render_template,
                   request, url_for)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESUME_DIR = os.path.join(REPO_ROOT, "auto-apply", "resume")

# make_profile.render() is used at POST /review time regardless of whether
# extract/derive are injected, so it's imported once here at module load.
# It no longer pulls in google.genai: that import moved inside the two
# functions that reach Gemini, so this app starts without the SDK and the
# local engine needs neither it nor a key.
sys.path.insert(0, os.path.join(REPO_ROOT, "auto-apply"))
# The repo root too, explicitly: `inference` lives there, and relying on
# the cwd being the repo root is how `python -m sweep` from elsewhere
# would fail at import rather than at the model call.
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
import inference  # noqa: E402
import local_profile  # noqa: E402
import make_profile  # noqa: E402
import skill_concepts  # noqa: E402

# Needed by snapshot() below (site free/paid classification) on every SSE
# tick — imported once here, at module load, rather than inside snapshot()
# itself, which would grow sys.path without bound over a 40-minute sweep.
sys.path.insert(0, REPO_ROOT)
import config  # noqa: E402
import scraper  # noqa: E402

# Flask-free logic lives in sweep.logic — form validation, the reachability
# split, the empty-result diagnosis. Re-exported here because these are part
# of this module's surface for its callers and tests, and because the split
# exists to make them reachable WITHOUT a Flask test client, not to hide them.
from sweep import exports, public  # noqa: E402
from sweep.logic import (  # noqa: E402,F401
    SECTIONS, _FormError, _SCOPE, _as_int, _configure_overrides, _parse_int,
    MAX_AVOID_TERMS, SCOPE_KEYS, DEFAULT_SCOPE, allowed_locations,
    DEFAULT_SORT, SECTION_CAP, SORTS, _valid_profile_name, and_list,
    bucket_rows, cheapest_rate, fill_pct, key_pills, mask_token, paid_sites,
    posted_age, remaining_cost, reweighted, location_groups, shortlist,
    experience_parts, experience_text, importance_badges, parse_banner,
    pick_activity, recommendation_pieces, recommendation_words, results_ending,
    run_banner, run_phase, scope_label, site_label, sort_rows, step_states,
    sweep_dates, sweep_state,
    with_experience, worst_filter, applied_path, read_applied, set_applied)

# Step 3 is a fork, not a form: "free sources only" or "connect a key". Its
# label has to be true after either answer — a step chip reading "Connect key"
# with a tick beside it, for someone who declined one, is a lie the tracker
# tells on every screen after it.
STEPS = [("upload", "Upload"), ("review", "Review"), ("key", "Free or paid"),
         ("configure", "Configure"), ("confirm", "Confirm"),
         ("running", "Running"), ("results", "Results")]

# Every state key the Search-preferences screen owns. One list, so "start
# over with another résumé" clears all of them or none — it used to clear the
# avoid-list (which lived inside `derived`) and keep the other six, which is
# the worst of both answers.
#
# `scope` first because it OWNS the six SCOPE_KEYS after it: they are what it
# expands to, and a scope left behind without its expansion (or the reverse)
# is a session whose screen and whose engine disagree.
#
# Deliberately NOT here: cap_usd and the credit readings (a verified key
# belongs to the person, not to the résumé) and anything in the signed
# cookie (session identity, the beta gate, a run already in flight).
PREFERENCE_KEYS = ("scope",) + SCOPE_KEYS + (
    "max_age_days", "max_results", "min_comp_usd", "avoid",
    "sites_enabled", "free_only")

# The 1-3 résumé setup (P4-U1; design §D.2, §N), public mode with the
# Multi-Track product on (worker_link.MULTI_FLAG) and nowhere else. Each
# résumé is one record in state["tracks"], in the visitor's order:
#
#   id           the engine's identity for it: made here, never a name
#   name         its label, and nothing more (1-40 printable characters)
#   renamed      the visitor chose that label, so no default replaces it
#   resume_name  the uploaded file's name, as the review screen shows it
#   resume_text  the text read from it (the PDF itself is never kept)
#   parse        the "reading"/"failed" marker while it is being read
#   derived      its derivation, and after POST /review its reviewed one
#   engine       the engine that derived it (Phase 0b)
#   reviewed     POST /review has accepted it
#   selected     it is in the next Sweep
#
# Preferences stay Sweep-wide, on state as ever. The engine-ready TRACKS are
# never kept here: P4-R1's plan snapshot builds them, at Confirm, and only
# there. One selected résumé is the one-résumé Sweep (schema 1); two or three
# are a Multi-Track Sweep (schema 2).
TRACK_ACTIONS = ("rename", "select", "deselect", "up", "down", "remove", "retry")


def new_track_id():
    """A track's engine identity (design §D.2): random, made on the server
    when the résumé becomes a track, and never a filename, a name or
    anything the visitor typed. make_profile.TRACK_ID accepts it."""
    return secrets.token_hex(8)

# account_usage_usd is a live Apify call. /events polls snapshot() every 2s
# for up to a ~40-minute sweep — read_spend is throttled to once per this
# many seconds and the value cached on app.state in between, or that would
# be ~1200 live requests for a figure that moves slowly.
SPEND_POLL_SECONDS = 15

# How long a screen may reuse the worker's dry run for an unchanged plan
# (P4-S1C, costed). Long enough to cover Configure -> Confirm -> Back without
# a second engine run; short enough that nothing the worker's environment
# decides (paid on or off) is out of date for long. POST /run never reuses.
PLAN_CACHE_SECONDS = 20

# How many arriving listings the running screen keeps on screen. A sample,
# not a ledger: the results screen is where every row is, and this figure is
# also the size of the payload every SSE tick has to carry.
FEED_LEN = 8

# The cap POST /run stamps into the profile is the ESTIMATE times this, not
# the estimate itself. SITE_RATES are measured averages, so a real sweep lands
# near the estimate but not on it — and /confirm says so in as many words. A
# cap equal to the estimate would abort a sweep that came in 10% high, having
# already paid for most of it, which is a worse outcome than the small
# overshoot it prevents.
SPEND_CAP_HEADROOM = 1.25
# Naukri alone is $0.50 per run minimum (config.SITE_RATES), so a cap below
# that would stop the sweep before its first search could finish.
SPEND_CAP_FLOOR_USD = 0.50
# How many of their own Apify accounts a visitor may connect to one sweep
# (V2-D1): the worker's own limit (deploy/sweep_worker.MAX_KEYS), checked here
# first so the refusal is a sentence on the screen rather than a 400.
MAX_PUBLIC_KEYS = 20
_CENT = Decimal("0.01")


def spend_cap_for(plan):
    """The hard stop to write into the profile for a costed plan (plan.cost).

    Sweep generates this; the user never types it — no screen, form field or
    API takes a cap from them — so it may be corrected, and V2-C4 corrects it.
    1.25 x the estimate alone let a reservation-safe engine (V2-C2) authorise
    only 76 of the default plan's 90 searches: an Indeed search is estimated
    at $0.09, capped at $0.1125, and carries a $0.135 provider ceiling. The cap
    is therefore also at least every bounded search's ceiling plus the old
    headroom on whatever is unbounded, rounded UP to the cent, so it can
    never sit below the exposure it has to hold. With no known ceiling (an
    older engine's plan) it is the estimate-based cap it always was.
    """
    cap = round(max(SPEND_CAP_FLOOR_USD, plan["total"] * SPEND_CAP_HEADROOM), 2)
    bounded = Decimal(plan.get("bounded_exposure") or 0)
    if not bounded:
        return cap
    need = bounded + (Decimal(str(plan.get("unbounded_estimate") or 0))
                      * Decimal(str(SPEND_CAP_HEADROOM)))
    return max(cap, float(need.quantize(_CENT, rounding=ROUND_CEILING)))


class ParseInFlight(Exception):
    """This browser already has a résumé being read.

    Not an error the visitor caused and not one they can fix: the answer is
    to show them the reading screen for the parse that IS running, rather
    than start a second one. Raised rather than returned because
    derived_for_state() is reached from four routes and every one of them
    has to stop doing what it was about to do.
    """


class PlanUnavailable(Exception):
    """The engine could not produce a plan for this profile.

    Raised at the subprocess boundary only. plan.fetch() shells out to
    `scraper.py --dry-run --json` and raises CalledProcessError for a profile
    that will not import — which reached Flask uncaught, so /configure and
    /confirm answered a broken profile with a bare 500 and /estimate with an
    HTML error page the fetch could not parse.

    Deliberately NOT wrapped around plan.cost(): a KeyError in the costing
    itself is a bug in this code and should surface as one, not be reported
    to the user as a bad profile.
    """

    def __init__(self, profile):
        super().__init__(f"could not plan profile {profile!r}")
        self.profile = profile


# The state one request sees INSTEAD of the session's own, as (app, dict).
# Set for the length of one POST /estimate pricing call by `priced_as`.
_candidate_state = contextvars.ContextVar("sweep_candidate_state", default=None)


class SweepApp(Flask):
    """Flask, with an `app.state` a single request can shadow for itself.

    Every screen and helper reads `app.state` by name, and pricing a
    candidate needs that candidate to BE `app.state` for the length of the
    call (public mode hands the worker `_prefs(app.state)`, and costed()
    writes its plan, cache and approval back to it). Doing that by swapping
    the candidate into the session's own dict and restoring a snapshot was
    the bug: a second request, a Save included, interleaves on that dict and
    the last restore writes somebody's older copy over the session.

    The shadow lives in a ContextVar, so it belongs to the thread serving
    that request and is invisible to every other. The session's real state is
    never written to while a candidate is being priced, so there is nothing
    to restore and nothing to race.
    """

    @property
    def state(self):
        held = _candidate_state.get()
        return held[1] if held is not None and held[0] is self else self._state

    @state.setter
    def state(self, value):
        self._state = value


@contextlib.contextmanager
def priced_as(app, candidate):
    """`app.state` is `candidate` — for this request only — inside the block.

    Whatever the pricing writes into it (plan, raw_plan, plan_cache, an
    approval, a profile render) lands in the copy and goes with it.
    """
    token = _candidate_state.set((app, candidate))
    try:
        yield candidate
    finally:
        _candidate_state.reset(token)


def next_token_name(env=None):
    """The first unused APIFY_TOKEN_* slot.

    Chosen by NAME, not by counting keys: a slot emptied by hand in .env must
    be filled rather than skipped, and two keys must never land on one name.
    Deliberately reads the raw names instead of scraper.apify_tokens(), whose
    dedupe hides a slot that holds a redundant copy of another key — writing
    over that name would be a silent overwrite.
    """
    env = os.environ if env is None else env
    taken = {n for n in env if n.startswith("APIFY_TOKEN_")}
    slot = 2
    while f"APIFY_TOKEN_{slot}" in taken:
        slot += 1
    return f"APIFY_TOKEN_{slot}"


def sweep_budget(credits):
    """(what one sweep can spend, total across every key) for verified
    per-key credit figures.

    These are two different numbers and conflating them was a money bug.
    scraper._require_token() builds ONE ApifyClient for the whole run from the
    single account with the most headroom, and the credit-exhausted branch
    tells the user to RERUN with another token — so no sweep spends across two
    accounts. Summing the keys therefore told the meter a $6 plan was
    affordable on two $3 accounts that could not fund it between them, and
    every extra key multiplied the error.

    The total is still worth showing: .done_combos means a stopped sweep
    resumes on the next key without re-billing finished searches, so several
    keys really do finish a sweep one account could not — just across runs,
    not within one.
    """
    figures = [max(0.0, c) for c in credits if c is not None]
    if not figures:
        return None, 0.0
    return max(figures), round(sum(figures), 4)


def planned_keys(state):
    """Ledger keys this sweep intends to write, in plan order."""
    from sweep import runs as runs_mod
    return runs_mod.combo_keys(state["raw_plan"], runs_mod.today())


# A .env value with an embedded newline turns one write into two lines —
# the second one an attacker-chosen KEY=VALUE the file's own reader (and
# python-dotenv) will parse as a real entry, silently overwriting whichever
# key it names. So env_key/value are checked here, at the single write
# funnel, rather than trusting every future caller to have checked upstream.
#
# The value is checked with an allowlist, not a blacklist of bad characters
# — a blacklist for \n and \r alone still let a NUL byte through (harmless
# to the file's line structure, but os.environ[...] = value raises on it
# unhandled). Printable, non-space ASCII covers every real Apify token and
# closes newline/CR/NUL/tab/unicode line separators in one rule.
_ENV_KEY_RE = re.compile(r"[A-Z][A-Z0-9_]*")
_ENV_VALUE_RE = re.compile(r"[\x21-\x7E]+")


class NotConfigured(RuntimeError):
    """A setting is missing, and the message names the setting and the fix.

    Composed here from this app's own vocabulary, so — unlike a client
    library's error, which can carry the request URL — it is safe to show
    on screen. It is separate from the model failures because it is not
    one: nothing was asked of any model. Telling someone their PDF might
    be a scan when they simply have no API key sends them to re-export a
    file that was never the problem.
    """


def create_app(state=None, extract=None, resume_dir=None,
               max_upload_bytes=15 * 1024 * 1024, derive=None,
               check_token=None, env_path=None, fetch_plan=None,
               start_sweep=None, read_spend=None, output_dir=None,
               read_done=None, now=None, read_rows=None, read_live=None,
               start_rescore=None, hour_now=None, profile_exists=None,
               wall_now=None, list_sweeps=None, start_merge=None,
               read_queue=None, read_ready=None, read_account=None,
               read_authorization=None):
    app = SweepApp(__name__)
    app.config["MAX_CONTENT_LENGTH"] = max_upload_bytes
    app.state = state if state is not None else {}
    resume_dir = resume_dir if resume_dir is not None else RESUME_DIR
    env_path = env_path if env_path is not None else os.path.join(REPO_ROOT, ".env")
    # Same shape as resume_dir/env_path: a real run writes under
    # REPO_ROOT/output/<profile>, but a test must never be able to reach a
    # real profile's output dir just because it picked a name that collides
    # with one — output/ holds real paid-sweep results with no git history
    # to fall back on.
    output_dir = output_dir if output_dir is not None else os.path.join(REPO_ROOT, "output")
    # Stashed so public mode can report WHICH market answered its skill
    # weights without re-deriving where output/ is.
    app.config["OUTPUT_DIR"] = output_dir
    # Injected so a test can advance the spend-poll throttle (SPEND_POLL_SECONDS
    # below) without a real sleep — a sleeping test is a slow test forever.
    import time as _time_mod
    now = now if now is not None else _time_mod.monotonic

    if extract is None:
        if public.enabled():
            # P4-S1B: never pypdf in this process for a stranger's file — a
            # child with a memory ceiling, a page cap and a clock, running
            # the same resume_parser.extract_text (sweep/safe_pdf.py).
            from sweep import safe_pdf
            extract = safe_pdf.extract
        else:
            import resume_parser
            extract = resume_parser.extract_text

    if derive is None:
        import apply_config as cfg

        def derive(resume_text, prefs):
            engine = make_profile.engine_name()
            api_key = os.environ.get("GEMINI_API_KEY")
            # Only the engines that can reach Gemini need the key. The
            # local engine exists so that a user without one can still
            # get a profile, so asking for it here would defeat it.
            if not api_key and engine != "local":
                # The hint used to be suppressed when the engine was
                # "gemini", which is exactly the person who needs it: the
                # default engine plus no key is what a first run without
                # a key looks like, and the screen said nothing about the
                # local engine existing.
                raise NotConfigured(
                    f"Sweep is set to read résumés with Gemini "
                    f"(engine {engine!r}), and GEMINI_API_KEY is not set. "
                    f"To run with no API key at all, start Sweep with "
                    f"{make_profile.ENGINE_ENV}=local — it reads the "
                    f"résumé with a model on this machine. Note that .env "
                    f"is not read for this setting; it has to be set in "
                    f"the environment.")
            client = None
            # A key AND an engine that can use one. `tailor` pulls in
            # google.genai, so building a client for a leftover key would
            # crash a local-only install that never needed the SDK.
            if api_key and engine != "local":
                import tailor
                client = tailor.get_client(api_key)
            # The ladder, not the pin: RPD is counted per model on the free
            # tier, so an exhausted primary is a reason to ask the next model,
            # not to fail the upload.
            return make_profile.generate(
                client, cfg.MODELS, resume_text, prefs, engine=engine)

    # Public mode runs the console's OWN screens against the Oracle
    # worker: same Configure, Confirm, Running and Results, which have
    # carried a free_only branch since long before any of this. Only what
    # they reach for changes. An explicitly injected one always wins, so
    # a test still decides for itself.
    if public.enabled():
        from sweep import worker_link
        remote = worker_link.injections(app)
        fetch_plan = fetch_plan or remote["fetch_plan"]
        start_sweep = start_sweep or remote["start_sweep"]
        read_live = read_live or remote["read_live"]
        read_rows = read_rows or remote["read_rows"]
        read_done = read_done or remote["read_done"]
        read_spend = read_spend or remote["read_spend"]
        list_sweeps = list_sweeps or remote["list_sweeps"]
        read_queue = read_queue or remote["read_queue"]
        read_ready = read_ready or remote["read_ready"]
        read_authorization = read_authorization or remote["read_authorization"]

    # Public mode: every extraction is two GPU calls on the operator's
    # Modal account, so the daily limit wraps the CALL, not the route —
    # POST /derive means to spend, but POST /review reaches the same
    # function, and a limit a second route walks around is not a limit.
    if public.enabled():
        app.beta_limit = public.limit_from_env()
        derive = public.metered(derive, app.beta_limit)

    if read_queue is None:
        # A local sweep is a subprocess started directly by POST /run: there
        # is nothing in front of it and nothing to wait behind, so "no queue"
        # is a fact here rather than a missing reading.
        def read_queue():
            return None

    if read_ready is None:
        # Nor anything to say a local result is final early: it is final
        # when its child exits, exactly as before.
        def read_ready():
            return False

    if read_authorization is None:
        # The console reads its own terminal; only a public run reports the
        # engine's paid authorization (V2-D1) back to a screen.
        def read_authorization():
            return None

    if read_account is None:
        def read_account(token):
            """(account, error) for a visitor's key (V2-D1): WHICH account it
            is and what that account can hold — users/me and users/me/limits,
            the same two free reads and the same arithmetic the engine's pool
            uses (scraper._account_reading), so a screen and the engine never
            disagree about a balance. `id` is the provider's account id; the
            caller keeps only a keyed digest of it."""
            from apify_client import ApifyClient
            try:
                client = ApifyClient(token)
                me = client.user().get()
                reading = scraper._account_reading(
                    me, client.user().limits().model_dump())
                ident = getattr(me, "id", None)
            except Exception:
                return None, "That token was rejected by Apify. Check and retry."
            if not ident:
                return None, ("Apify did not say which account this key belongs "
                              "to, so Sweep cannot count its credit safely.")
            return dict(reading, id=ident), None

    if profile_exists is None:
        def profile_exists(name):
            return os.path.exists(
                os.path.join(REPO_ROOT, "profiles", f"{name}.py"))

    def default_write_profile(name, source):
        if not _valid_profile_name(name):
            raise ValueError(f"not a valid profile name: {name!r}")
        path = os.path.join(REPO_ROOT, "profiles", f"{name}.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(source)
        return path

    app.write_profile = default_write_profile

    def default_discard_profile(name):
        """Take a SCRATCH profile off disk again, and the bytecode the dry
        run's import left beside it. Only a scratch one (POST /estimate's
        `_est_<12 hex>` candidates): never a profile anyone named.
        """
        if not (_valid_profile_name(name) and re.search(r"_est_[0-9a-f]{12}$", name)):
            return
        base = os.path.join(REPO_ROOT, "profiles")
        with contextlib.suppress(FileNotFoundError):
            os.remove(os.path.join(base, f"{name}.py"))
        cache = os.path.join(base, "__pycache__")
        with contextlib.suppress(FileNotFoundError):
            for leftover in os.listdir(cache):
                if leftover.startswith(name + ".") and leftover.endswith(".pyc"):
                    with contextlib.suppress(FileNotFoundError):
                        os.remove(os.path.join(cache, leftover))

    app.discard_profile = default_discard_profile

    if check_token is None:
        def check_token(token):
            """Return (available_usd, error). Available credit is the account's
            monthly limit minus month-to-date usage, both from the same call
            scraper.py trusts for its spend cap."""
            from apify_client import ApifyClient
            try:
                limits = ApifyClient(token).user().limits().model_dump()
                current = (limits.get("current") or {}).get("monthly_usage_usd") or 0
                allowed = (limits.get("limits") or {}).get("max_monthly_usage_usd")
                if allowed is None:
                    return None, (
                        "Apify did not report a monthly limit for this "
                        "account, so Sweep cannot work out your remaining "
                        "credit and will not guess at it. Set a monthly "
                        "limit on the account, or run from the command line, "
                        "where the profile's own cap is the only guard.")
                return float(allowed) - float(current), None
            except Exception:
                return None, "That token was rejected by Apify. Check and retry."

    def default_write_env(env_key, value):
        """Upsert one key in .env, leaving every other line untouched. Lines
        are normalised to end with '\\n' before appending — the real .env
        does not end with one, and writelines() glues text together with no
        separator otherwise, corrupting whichever key happened to be last."""
        if not _ENV_KEY_RE.fullmatch(env_key):
            raise ValueError(f"not a valid env key: {env_key!r}")
        if not isinstance(value, str) or not _ENV_VALUE_RE.fullmatch(value):
            raise ValueError("env value must be printable, non-space ASCII")
        lines = []
        if os.path.exists(env_path):
            with open(env_path) as fh:
                lines = [ln if ln.endswith("\n") else ln + "\n"
                         for ln in fh if not ln.startswith(f"{env_key}=")]
        lines.append(f"{env_key}={value}\n")
        with open(env_path, "w") as fh:
            fh.writelines(lines)

    def default_remove_env(env_key):
        """Drop one key from .env. Every other line is left byte for byte.

        The counterpart to default_write_env and validated the same way: the
        name reaches a file the process re-reads as configuration, so it is
        checked here at the single funnel rather than at each caller.
        """
        if not _ENV_KEY_RE.fullmatch(env_key):
            raise ValueError(f"not a valid env key: {env_key!r}")
        if not os.path.exists(env_path):
            return
        with open(env_path) as fh:
            lines = [ln if ln.endswith("\n") else ln + "\n"
                     for ln in fh if not ln.startswith(f"{env_key}=")]
        with open(env_path, "w") as fh:
            fh.writelines(lines)

    app.write_env = default_write_env
    app.remove_env = default_remove_env
    app.jinja_env.globals["and_list"] = and_list
    from sweep.logic import short_places
    app.jinja_env.filters["short_places"] = short_places

    def read_env_tokens():
        """(name, token) for every Apify key in .env ON DISK, and reconcile the
        process environment with it.

        The process environment is not the record. os.environ is loaded once
        at start-up and load_dotenv() does not override what is already there,
        so a key deleted from .env by hand stays visible to this process for
        as long as the server runs — which is why the duplicate check kept
        rejecting a key that had just been removed. It also stays visible to
        the ENGINE, which inherits this environment (runs.start), so a sweep
        would go on spending from an account the user thought they had
        detached.

        Reading the file is therefore not enough: the stale names are dropped
        from os.environ too, so the file is the single answer to "which keys
        are configured" for the UI and for every child it launches.

        Slot ordering and same-key dedupe stay in scraper.apify_tokens(),
        called on the file's contents, rather than being reimplemented here.

        Empty in public mode: this file is the operator's, and no screen a
        visitor can open may read, count or spend what is in it.
        """
        if app.config.get("PUBLIC_MODE"):
            return []
        from_file = {}
        if os.path.exists(env_path):
            with open(env_path) as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    name, _, value = line.partition("=")
                    name = name.strip()
                    if name == "APIFY_TOKEN" or name.startswith("APIFY_TOKEN_"):
                        # .env may quote a value; load_dotenv strips those, so
                        # a reader that does not would compare a quoted string
                        # against a bare one and call the same key different.
                        from_file[name] = value.strip().strip("\"'")
        for name in [n for n in os.environ
                     if n == "APIFY_TOKEN" or n.startswith("APIFY_TOKEN_")]:
            if name not in from_file:
                del os.environ[name]
        for name, value in from_file.items():
            os.environ[name] = value
        return scraper.apify_tokens(env=from_file)

    def read_env_tokens_as_env():
        """{name: token} from .env, for next_token_name's slot search.

        It picks a slot by NAME rather than by counting keys, precisely so a
        slot emptied by hand gets refilled — which only works if it is looking
        at the file the hand edited.
        """
        return {name: token for name, token in read_env_tokens()}

    def refresh_credits():
        """Re-verify every key in .env and rewrite the credit figures.

        Replaces the incremental bookkeeping this used to do. Adding a key's
        credit to a running total is how the same key pasted twice inflated
        the cap twice — and reading the limits endpoint costs nothing, so
        there is no reason to carry arithmetic that can drift instead of
        asking.

        A key that cannot be read is recorded as None rather than zero:
        sweep_budget() skips it, so one unreachable account cannot make the
        other three look spent.

        Does nothing in public mode, and that is load-bearing. .env holds
        the OPERATOR's keys; re-reading them for a visitor overwrites the
        credit their own key reported with a stranger's — which is both the
        wrong number and the operator's balance on a public page. A
        visitor's cap comes from the one check_token call their own key got
        at POST /key, and nothing else may touch it.
        """
        if app.config.get("PUBLIC_MODE"):
            return
        known = app.state.get("key_credit") or {}
        credits = {}
        for name, token in read_env_tokens():
            available, error = check_token(token)
            # A read that FAILED must not discard a figure already verified.
            # The limits endpoint is a live call; on a blip every key would
            # come back unknown, sweep_budget would skip them all, cap_usd
            # would go None — and needs_key() reads exactly that, so a
            # network hiccup would bounce someone back to step 3 mid-flow.
            # A key deleted from .env is different: it is not in this loop at
            # all, so it drops, which is the user's own instruction.
            credits[name] = known.get(name) if error else available
        app.state["key_credit"] = credits
        app.state["cap_usd"], app.state["credit_total_usd"] = sweep_budget(
            credits.values())
        return credits

    if fetch_plan is None:
        from sweep import plan as plan_mod
        fetch_plan = plan_mod.fetch

    if start_sweep is None:
        from sweep import runs as runs_mod
        start_sweep = runs_mod.start

    if read_spend is None:
        def read_spend():
            """Month-to-date account spend, the authoritative figure. Actor
            self-reports undercount roughly 3x (scraper.py:912).

            Returns None — never a fabricated 0.0 — when the figure isn't
            available: no token set, or the call itself failed (network,
            Apify outage). /run persists whatever this returns as
            baseline_usd; None there means "unknown", and Task 8 must show
            the raw current spend with a caveat rather than treat it as a
            zero baseline, which would report the account's entire
            month-to-date spend as this one sweep's cost."""
            import scraper
            from apify_client import ApifyClient
            token = os.environ.get("APIFY_TOKEN")
            if not token:
                return None
            try:
                return scraper.account_usage_usd(ApifyClient(token))
            except Exception:
                return None

    if read_done is None:
        def read_done(profile, day):
            """Keys finished today, straight from output/<profile>/.done_combos
            — never parsed from stdout, which is a formatting detail the
            engine itself doesn't trust to resume a capped sweep. Reads
            through the injected output_dir, same as _write_run_json, so a
            test can never reach a real profile's real (paid, unrecoverable)
            output directory just by picking a colliding profile name."""
            from sweep import runs as runs_mod
            out_dir = os.path.join(output_dir, profile)
            return runs_mod.done_keys(runs_mod.done_path_for(out_dir), day)

    # Wall clock, injected like the rest. `now` is monotonic and says nothing
    # about the time of day, but this one is compared against FILE mtimes and
    # is shown to the user as an elapsed time, so it has to be the real clock.
    wall_now = wall_now if wall_now is not None else _time_mod.time

    if read_live is None:
        def read_live(profile, since):
            """Rows from the file THIS sweep is writing, or [].

            The newest jobs_<stamp>.csv, and deliberately NOT
            jobs_combined.csv: that file is merge_jobs.py's output and spans
            every earlier sweep, so a live feed built on it would open by
            presenting last month's listings as things that just arrived.

            `since` is the same guard one step further: at the moment a sweep
            launches, the newest stamped file is still the PREVIOUS sweep's,
            so a file untouched since before this run started is not this
            run's and is ignored entirely.

            Read through the injected output_dir, same as read_done and
            _write_run_json, so a test can never reach a real profile's real
            (paid, unrecoverable) output directory.
            """
            import csv
            import glob
            files = [f for f in glob.glob(
                        os.path.join(output_dir, profile, "jobs_2*.csv"))
                     if since is None or os.path.getmtime(f) >= since]
            if not files:
                return []
            with open(max(files, key=os.path.getmtime),
                      newline="", encoding="utf-8") as fh:
                return list(csv.DictReader(fh))

    if list_sweeps is None:
        def list_sweeps(profile):
            """The dates of the files a merge would fold in, newest first.

            EXACTLY what merge_jobs.py itself globs — jobs_*.json minus the
            combined and jobs_all outputs — so the offer on screen cannot
            claim more or fewer sweeps than the merge will actually read.

            Ordered by mtime, matching read_rows' own "newest first", so the
            first entry is the sweep currently on display. The date comes
            from the filename stamp where there is one and the mtime where
            there is not: output directories hold hand-named files too
            (jobs_chandigarh.json), and the merge reads those as well.
            """
            import glob
            from datetime import date as _date
            out = []
            paths = glob.glob(os.path.join(output_dir, profile, "jobs_*.json"))
            for path in sorted(paths, key=os.path.getmtime, reverse=True):
                base = os.path.basename(path)
                if "combined" in base or "jobs_all" in base:
                    continue
                stamp = re.match(r"jobs_(\d{4}-\d{2}-\d{2})", base)
                out.append(stamp.group(1) if stamp else
                           _date.fromtimestamp(os.path.getmtime(path)).isoformat())
            return out

    if start_merge is None:
        from sweep import runs as runs_mod
        start_merge = runs_mod.start_merge

    if read_rows is None:
        def read_rows(profile):
            """This profile's shortlist, newest first, or [] if none yet.

            Prefers jobs_combined*.csv, which merge_jobs.py and
            rescore_from_apify.py write and which spans every sweep. Falls
            back to the newest jobs_<date>_<time>.csv, because **scraper.py
            never writes a combined file** — only merge_jobs.py and a
            re-score do. Without the fallback a UI-driven sweep finishes, is
            billed, and the results screen says nothing was found: 8 of the 16
            profile directories in this repo today have stamped sweep output
            and no combined file at all.

            The fallback is safe to show whole: scraper.py's emit() writes the
            cumulative row set at every checkpoint (scraper.py:1686-1697), so
            a stamped file is the full sweep so far, not a fragment of it.

            Reads through the injected output_dir, same as read_done, so a
            test can never reach a real profile's real (paid, unrecoverable)
            output directory by picking a colliding profile name.
            """
            import csv
            import glob
            base = os.path.join(output_dir, profile)
            merged = sorted(glob.glob(os.path.join(base, "jobs_combined*.csv")),
                            key=os.path.getmtime, reverse=True)
            stamped = sorted(glob.glob(os.path.join(base, "jobs_2*.csv")),
                             key=os.path.getmtime, reverse=True)
            files = merged or stamped
            if not files:
                return []
            with open(files[0], newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            for row in rows:
                # Which file this came from, so the screen can say whether it
                # is showing every sweep or only the most recent one.
                row.setdefault("_merged", "1" if merged else "")
            return rows

    def _applied_file():
        return applied_path(output_dir, app.state["profile"])

    def rows_with_applied(profile):
        """This profile's shortlist, each row flagged with whether it has been
        ticked as applied.

        One place, called by both the screen and the export, because a row
        shown as applied and exported as not would make the tick worthless.
        The ledger is read once per request rather than per row — it is a set
        of a few hundred keys, and the file is small enough that caching it
        would only add a way for it to go stale.
        """
        # Copied, not flagged in place: read_rows is injectable and a test's
        # fixture list is shared between cases, so writing into the caller's
        # dicts leaks one case's ticks into the next.
        rows = [dict(row) for row in read_rows(profile)]
        done = read_applied(applied_path(output_dir, profile))
        for row in rows:
            # The engine's own identity rule, the same one the live feed
            # above uses — never a second one that could disagree with it.
            row["_key"] = scraper._seen_key(row)
            row["applied"] = bool(row["_key"]) and row["_key"] in done
        return rows

    if start_rescore is None:
        from sweep import runs as runs_mod
        start_rescore = runs_mod.start_rescore

    def live_feed(p):
        """Listings this sweep has produced: how many, and a sample of the
        ones that appeared since the last reading.

        scraper.py rewrites its output file WHOLE after every search
        (finalize() re-ranks every row), so what is new cannot be found by
        tailing the file — it is the difference between two readings, which
        is why the keys already reported are kept on state.

        Free-only sweeps get nothing here, and deliberately: fetch_free()
        returns everything in one pass at the end, so a feed would sit empty
        for the whole run and then flash the lot. That path shows the
        indeterminate bar instead, which is the honest signal for work with
        no reportable progress.
        """
        p["found"] = app.state.get("live_found", 0)
        p["latest"] = app.state.get("live_items", [])
        p["since"] = None
        if free_only():
            return
        rows = read_live(app.state["profile"], app.state.get("run_started_at"))
        if len(rows) < p["found"]:
            # A reading can land mid-write and come back short. During a
            # sweep this file only ever grows, so a shorter one is a torn
            # read rather than news, and reporting it would walk the count
            # backwards on a screen someone is watching for reassurance.
            return
        seen = app.state.setdefault("live_seen", set())
        fresh = []
        for row in rows:
            # The engine's own identity rule, not a second one that could
            # disagree with it. A row it cannot key on is counted but never
            # shown: without an identity, every re-read would report it as
            # having just arrived, over and over.
            key = scraper._seen_key(row)
            if not key or key in seen:
                continue
            seen.add(key)
            item = {"key": key,
                    "title": (row.get("title") or "").strip(),
                    "company": (row.get("company") or "").strip(),
                    "site": (row.get("source_site") or "").strip(),
                    "score": _as_int(row.get("score"))}
            if app.config.get("PUBLIC_MODE"):
                # A8: why a match matched. Split exactly as results.html does
                # (`split(',')`, trim, drop the empty ones); six is what a
                # chip row holds. Public only: the console's /running embeds
                # `progress|tojson`, and its bytes do not move. A Multi-Track
                # row's column already holds the best track's skills
                # (scraper.py), so this is right for one résumé and for several.
                item["skills"] = [
                    t for t in (s.strip() for s in
                                (row.get("matched_skills") or "").split(","))
                    if t][:6]
            fresh.append(item)
        app.state["live_found"] = p["found"] = len(rows)
        if fresh:
            # Newest batch on top. Within a batch the engine's own order is
            # kept, which is by score — so what shows is the best of what
            # just arrived, not an arbitrary slice of it.
            app.state["live_items"] = (
                fresh + app.state.get("live_items", []))[:FEED_LEN]
            app.state["live_at"] = wall_now()
        p["latest"] = app.state.get("live_items", [])
        last_at = app.state.get("live_at")
        if last_at is not None:
            p["since"] = int(max(0, wall_now() - last_at))

    def snapshot():
        """One progress reading. Spend is a delta from the recorded baseline,
        because account_usage_usd is month-to-date, not per-run."""
        from sweep import runs as runs_mod

        planned = planned_keys(app.state)
        done = read_done(app.state["profile"], runs_mod.today())
        p = runs_mod.progress(planned, done)

        # Where this run is in the worker's queue, if it is in one at all.
        # MAX_ACTIVE is 1 on the worker, so waiting behind somebody else is
        # the NORMAL state for a public beta with more than one visitor —
        # and until now it was indistinguishable from a hang: the screen
        # showed an indeterminate bar and said nothing.
        waiting = read_queue()
        p["queued"] = bool(waiting)
        p["queue_position"] = waiting or 0

        for tile in p["tiles"]:
            # Same rule plan.cost() already uses (a site listed at a $0.00
            # rate is free either way) rather than a second implementation
            # of "is this site free" that could disagree with it.
            tile["free"] = config.SITE_RATES.get(tile["site"], 0.0) == 0.0

        # No account to poll on the free path, and nothing that reading it
        # could report: skipped rather than called every 15s for a figure
        # that is zero by construction.
        live_feed(p)
        started = app.state.get("run_started_at")
        # None until POST /run records it, and after a server restart. Shown
        # as nothing rather than as zero: a clock reading 0s beside a sweep
        # that is minutes old is worse than no clock.
        p["elapsed"] = None if started is None else int(wall_now() - started)

        if free_only():
            p["spend"] = 0.0
            p["spend_known"] = p["baseline_known"] = True
            return _liveness(p)

        last_at = app.state.get("spend_read_at")
        if last_at is None or (now() - last_at) >= SPEND_POLL_SECONDS:
            app.state["spend_read_val"] = read_spend()
            app.state["spend_read_at"] = now()
        spend_now = app.state["spend_read_val"]

        baseline = app.state.get("baseline_usd")
        p["baseline_known"] = baseline is not None
        p["spend_known"] = spend_now is not None
        if spend_now is None:
            # No reading at all. Don't invent a figure for a money display.
            p["spend"] = None
        elif baseline is None:
            # Month-to-date with no baseline to subtract. Report it as what
            # it is, not as this sweep's cost.
            p["spend"] = round(spend_now, 4)
        else:
            p["spend"] = spend_delta()

        return _liveness(p)

    def _liveness(p):
        """Is the child still alive, and what does that make of the counts.

        Shared with the free path above: two readings of "finished" is how a
        screen ends up offering results for a sweep still running.
        """
        proc = app.state.get("proc")
        # What the USER is waiting for, which is the process — until the
        # worker says the result is final while the engine is still busy with
        # work that cannot change it (V2-B5). From here the screen reads
        # exactly as it will once the process exits, so the page moves on by
        # its usual route. _sweep_in_flight() still asks the process, so
        # nothing new can start meanwhile.
        running_now = (proc is not None and proc.poll() is None
                       and not read_ready())
        # A run with no planned searches (the free path) has nothing
        # outstanding for its whole life, so "outstanding == 0" says nothing
        # about whether it succeeded there. The process does: its exit is the
        # worker's own word (RemoteRun maps done to 0 and failed, stopped or
        # interrupted to 1). A result the worker has declared final
        # (results_ready, V2-B5) stays final whatever the process does after
        # it: a crash in the engine's last seconds is recorded apart and does
        # not take the jobs away.
        code = None if running_now or proc is None else proc.poll()
        # D7C: the same for a PAID run. Its ledger proves the searches ran, not
        # that the engine ended well: a process that failed or was interrupted
        # after the last search, with the result never declared final, is not
        # "finished" (sweep_state names it "incomplete"). With searches still
        # outstanding nothing changes: that run was never finished.
        failed = code not in (None, 0) and not read_ready()
        p["finished"] = (not running_now) and p["outstanding"] == 0 and not failed
        p["interrupted"] = (not running_now) and (p["outstanding"] > 0 or failed)
        # A paid run the server was restarted under (rehydrate): no plan, so no searches to count, and no right to say that nothing
        # was charged. The words on the screen leave that sentence out when this is set.
        p["charged_unknown"] = bool(app.state.get("unplanned_paid")) and not p["planned"]
        # Only when the worker's own status said so; a local child has none.
        p["timed_out"] = p["interrupted"] and bool(getattr(proc, "timed_out", False))
        # The engine works through the free sources AFTER the paid searches,
        # and they have no ledger and no tiles: at this point the grid is
        # full, "still to run" reads zero, and listings go on arriving for
        # minutes. Without saying so the screen looks stuck on a sweep that
        # is busy — which is exactly how it read on a real run.
        p["free_running"] = running_now and p["outstanding"] == 0

        # What the searches that never ran would cost, at the same effective
        # rates the plan was priced at. It is the figure the decision to
        # resume turns on, and it was nowhere on the screen.
        rates = {line["site"]: line["rate"]
                 for line in (app.state.get("plan") or {}).get("lines") or ()}
        p["remaining_cost"] = remaining_cost(p["tiles"], rates)

        # One live re-read at the moment it stops, not on every SSE tick:
        # saying the credit ran out is a claim about a balance, so it has to
        # be made against a balance read after the spending stopped.
        if (p["interrupted"] and p["outstanding"] > 0 and not free_only()
                and not app.state.get("interrupt_credit_read")
                and app.state.get("credit_total_usd") is not None):
            app.state["interrupt_credit_read"] = True
            refresh_credits()

        # The refreshed total already has this sweep's spend taken out of it
        # — the accounts really were charged — so nothing is subtracted here.
        # A stop is the visitor's own click (recorded in this session) or, where
        # the session no longer remembers it, the WORKER's own `stopped`
        # (RemoteRun.stopped): never inferred from a failure.
        p["state"] = sweep_state(
            running_now, p["outstanding"],
            stopped_by_user=bool(app.state.get("stopped_by_user"))
                            or getattr(proc, "stopped", False) is True,
            planned=p["planned"],
            # key_credit empty means no key is on file at all, and
            # sweep_budget() reports a 0.00 TOTAL for that — which is "we
            # know of nothing", not "there is nothing". Claiming the credit
            # ran out needs a key that is actually spent.
            credit_left=(None if free_only() or not app.state.get("key_credit")
                         else app.state.get("credit_total_usd")),
            cheapest_search=cheapest_rate(p["tiles"], rates),
            authorization=None if free_only() else read_authorization(),
            failed=failed)
        p["authorization"] = None if free_only() else read_authorization()

        # A free sweep has no per-search progress to count: the free sources
        # are one pass inside the engine, so "0 searches left" — literally
        # true, since none are planned — reads as a finished sweep for the
        # whole run.
        p["remaining_text"] = (
            ("fetching the free sources" if free_only()
             else f"{p['outstanding']} searches left") if running_now else
            {"finished": "finished",
             "stopped": "stopped by you",
             "out_of_credit": "out of credit",
             "halted": "stopped early",
             "incomplete": "every search ran, then the sweep stopped",
             "credit_changed": "not started — your Apify credit changed",
             "partial": "finished the part your credit covers"}[p["state"]])

        # The persistent status strip, built by the SAME function the server
        # render uses (logic.run_banner) and carried in the poll payload —
        # so the strip a page was served with and the strip its first poll
        # replaces cannot word the same run differently.
        p["banner"] = run_banner(
            run_phase(p["state"], queued=p.get("queued")),
            queue_position=p.get("queue_position") or 0,
            found=p.get("found") or None)

        return p

    def ending_of_this_run():
        """How the run behind Results ended when it was not whole, or None.

        The Running screen's own reading of the run (progress from the
        ledger, then _liveness), so the two screens use ONE state and cannot
        disagree — without snapshot()'s paging of every row. None without a
        run this process knows, and on any failure to read it: Results must
        render either way."""
        if app.state.get("proc") is None or not app.state.get("raw_plan"):
            return None
        from sweep import runs as runs_mod
        try:
            p = runs_mod.progress(planned_keys(app.state),
                                  read_done(app.state["profile"], runs_mod.today()))
            p = _liveness(p)
        except Exception:
            return None
        return results_ending(p["state"], timed_out=p.get("timed_out", False))

    def current_scope():
        """Which of the three scopes this session is actually on.

        Unset until something commits one, which ensure_scope() does before
        the first profile is written — so in practice this falls back only
        on a session that has not reached the review screen yet. The radio
        was once hardcoded `checked` on one answer while _prefs() produced
        another, and the summary duly printed the wrong one.

        DEFAULT_SCOPE lives in sweep.logic so the radio order, the
        materialisation and the form validator all read one name.
        """
        return app.state.get("scope") or DEFAULT_SCOPE

    def ensure_scope():
        """Write the default scope into state, so it is a choice and not a
        gap the engine fills differently from the screen.

        Unset, `_prefs` produced locations=["Remote"] and nothing else, so
        make_profile omitted the SITES block entirely and LinkedIn inherited
        config's own ["India", "Remote"] — two searches per keyword, half of
        them India-onsite, under a screen whose radio said "Remote, from
        anywhere". Touching any control then posted the real scope and the
        quoted price halved for no reason the user had caused.

        Called wherever a profile is about to be rendered, priced or run.
        """
        if not app.state.get("scope"):
            # One update, so a snapshot never sees the scope without what it
            # expands to.
            app.state.update({"scope": DEFAULT_SCOPE, **_SCOPE[DEFAULT_SCOPE]})

    def sync_profile():
        """Re-render the profile file from state.

        The profile is a DERIVED artifact: state is what the user chose, the
        file is what the engine reads, and every screen that prices or runs
        re-derives it. That is what lets POST /estimate price a candidate
        the user has not committed to — the next read puts the committed one
        back — and it is why a priced-but-unsubmitted form can never become
        the sweep.
        """
        name = app.state.get("profile")
        if not name or not app.state.get("derived"):
            return
        ensure_scope()
        try:
            app.write_profile(
                name, make_profile.render(name, app.state["derived"],
                                          _prefs(app.state)))
        except KeyError as exc:
            # Only reachable from state that validation should have refused.
            # Logged rather than raised: the file on disk is then simply the
            # previous good render, which is what the screen was showing
            # anyway, and a 500 here would be on a GET.
            if app.config.get("PUBLIC_MODE"):
                # Never the profile name publicly: it is the visitor's name.
                app.logger.warning("could not re-render the profile from "
                                   "state: %s", type(exc).__name__)
            else:
                app.logger.warning("could not re-render %r from state: %s",
                                   name, exc)

    def commit_prefs(form):
        """Validate a posted preferences form and APPLY it. Error string or None.

        The one writer. POST /configure and the free path's POST /run both
        come through here, so "what the browser submitted" is what the
        session holds — no screen depends on a fetch() having fired, and a
        live-pricing request that never finished cannot cost anyone their
        last edit.

        Atomic in the same way POST /estimate always was: built on a COPY,
        and applied only once make_profile.render() — the validator shared
        with the CLI path — has actually succeeded on it.

        What is applied is what this Save CHANGES, in one update() — not the
        session as it looked when the Save began. A snapshot taken by
        anything else at any moment sees all of it or none of it (the old
        clear() then update() showed a session with nothing in it in
        between), and a preference another request saved while this one was
        validating is not put back to what this one saw.
        """
        try:
            overrides = _configure_overrides(form, current_scope())
        except _FormError as exc:
            return str(exc)
        if not overrides:
            return None
        # The paid toggles belong to the free/paid choice while it stands.
        # Configure renders no source checkboxes in free mode, so this is a
        # forged or stale form rather than a control the user saw.
        if free_only():
            overrides.pop("sites_enabled", None)
        changed = dict(overrides)
        new_state = app.state.copy()
        new_state.update(changed)
        if not new_state.get("scope"):
            changed["scope"] = DEFAULT_SCOPE
            changed.update(_SCOPE[DEFAULT_SCOPE])
            new_state.update(changed)
        try:
            write_sweep_profile(new_state)
        except KeyError as exc:
            return str(exc)
        app.state.update(changed)
        settle_tracks()
        return None

    def write_sweep_profile(state, profile=None):
        """make_profile.render, the validator every preference change goes
        through (shared with the CLI path), over the Sweep `state` describes.
        `profile` names the file to write when it is not the session's own
        (an estimate's scratch profile).

        One résumé: its profile, rendered and written as it always was. A
        Multi-Track Sweep (P4-R1): each selected résumé checked the same way
        against the same preferences, and nothing written — that Sweep's
        profile is its plan snapshot, built at Confirm and nowhere else.
        KeyError, as ever, for what the validator refuses.
        """
        from sweep import worker_link
        name = profile or state["profile"]
        if worker_link.multi_active(state):
            for track in worker_link.selected(state):
                make_profile.render(name, track["derived"], _prefs(state))
            return
        app.write_profile(name, make_profile.render(
            name, state["derived"], _prefs(state)))

    def search_facts():
        """Roles, scope, locations and sources — what the sweep will DO.

        Read from the same state the engine is handed, never recomputed: the
        roles are the derivation's own keywords, the locations are what the
        Configure form posted, and the sources come off the costed plan. A
        second opinion about any of them would be a summary that disagrees
        with the sweep it is summarising.
        """
        derived = app.state.get("derived") or {}
        roles = derived.get("role_keywords") or []
        from sweep import worker_link
        if worker_link.multi_active(app.state):
            # A Multi-Track Sweep searches for each selected résumé, and what
            # the engine searches for each is its own (P4-R1's snapshot, never
            # shown). So the row names the résumés, by label, in their order.
            roles = [track["name"] for track in worker_link.selected(app.state)]
        plan_now = app.state.get("plan") or {}
        # See current_scope(): the form and the summary must not disagree
        # about a choice nobody has made yet.
        paid_on = [site_label(line["site"]) for line in plan_now.get("lines") or ()
                   if not line.get("free")]
        scope = current_scope()
        # Only an explicit pick. The scope's own expansion is six city names
        # the user never chose, and listing them as "Where" would read as six
        # decisions rather than one. Detected by comparing against the scope's
        # own list rather than by a separate flag, so the summary cannot claim
        # a narrowing that is not in state.
        #
        # This is also what stops the old free-mode lie: under "Remote, from
        # anywhere" the picker is not offered and locations are dropped, so
        # `locations` equals the scope's and the summary says "Remote,
        # anywhere" — it can no longer print "Where: Bengaluru" for a sweep
        # that searches everywhere.
        picked = app.state.get("locations")
        narrowed = picked if picked and picked != _SCOPE[scope]["locations"] else None
        return {
            "roles": roles,
            "scope_label": scope_label(scope),
            "locations": narrowed,
            "paid_labels": paid_on,
            "free_sources": (app.state.get("raw_plan") or {}).get("free_sources"),
            # Retrieval depth is a PAID concept: a free sweep runs no
            # per-query searches at all, it enumerates whole boards, so
            # quoting a depth there would describe something that does not
            # happen. None means "do not show it".
            "depth": (None if free_only() else
                      app.state.get("max_results") or config.SEARCH["max_results"]),
        }

    def plan_identity(profile):
        """Everything the worker's dry run is made from, as one digest — or
        None where no earlier plan may stand in for a new one (P4-S1C).

        One résumé: the derivation, the preferences it is sent (_prefs, the
        spend stamps included), free or paid, the engine it is rendered
        with, and the profile name, serialised in their own key order. A
        Multi-Track Sweep: its approval, which only exists unused and
        un-invalidated, bound to the snapshot inputs it was planned from and
        the worker's hash for it — any edit worker_link.inputs sees is a new
        plan, exactly as before. Console mode: never (no cache there).
        """
        if not app.config.get("PUBLIC_MODE"):
            return None
        import json

        from sweep import worker_link
        if worker_link.multi_active(app.state):
            planned = app.state.get(worker_link.PLANNED)
            if (not planned or "run_id" in planned or app.state.get(worker_link.REPLAN)
                    or planned["snapshot"]["inputs"] != worker_link.inputs(app.state)):
                return None
            parts = ["multi", profile, planned["plan_hash"], planned["snapshot"]["inputs"]]
        else:
            parts = ["one", profile, app.state.get("derived"), _prefs(app.state),
                     free_only(), worker_link.engine_for(app.state)]
        return hashlib.sha256(json.dumps(parts, ensure_ascii=False, default=str)
                              .encode("utf-8")).hexdigest()

    def costed(profile, fresh=False, plan_profile=None):
        """Cost the plan and say whether it exceeds the key's credit. The
        over-cap flag is advisory: SETTINGS["max_spend_usd"] is the real guard.

        `plan_profile` is the profile the dry run READS when that is not
        `profile` itself: the console's estimate prices a candidate from a
        scratch profile of its own. Everything else — the plan's name, what
        is already done today — is `profile`'s.

        Priced on what is LEFT to run, not on the whole plan: the engine
        skips today's finished combos and will not re-bill them, so quoting
        the full sweep to resume a fraction of it overstates the spend on the
        one screen that exists to state it correctly.

        Public mode (P4-S1C): the screens' plans — Configure, Confirm, live
        pricing — reuse the worker's dry run for PLAN_CACHE_SECONDS while
        plan_identity() is unchanged, and a dry run that is not reused counts
        against the plan limit first (public.admit_plan, PlanLimited). Only
        the worker's answer is reused: what is left to run and what the
        connected accounts can hold are worked out again every time.
        `fresh` (POST /run) always asks the worker and is never limited here:
        a Sweep's own quota was taken before it got this far.
        """
        import copy

        from sweep import plan as plan_mod
        from sweep import runs as runs_mod

        key = None if fresh else plan_identity(profile)
        hit = app.state.get("plan_cache")
        if key is not None and hit and hit["key"] == key and (
                now() - hit["at"] < PLAN_CACHE_SECONDS):
            raw = copy.deepcopy(hit["raw"])
        else:
            if app.config.get("PUBLIC_MODE") and not fresh:
                public.admit_plan(app)
            try:
                raw = fetch_plan(plan_profile or profile)
            except Exception as exc:
                # Logged, not rendered: the detail is useful in the terminal the
                # user is already running this from, and engine stderr is
                # unbounded output that has no business being echoed into a page
                # on the same screen where a key gets pasted. Publicly, neither
                # the profile name (the visitor's own name) nor the text.
                if app.config.get("PUBLIC_MODE"):
                    app.logger.warning("plan failed: %s", public.failure_category(exc))
                else:
                    app.logger.warning("plan failed for %r: %s", profile, exc)
                raise PlanUnavailable(profile) from exc
            if plan_profile:
                raw = dict(raw, profile=profile)
            stored = plan_identity(profile)
            if stored is not None:
                app.state["plan_cache"] = {"key": stored, "at": now(),
                                           "raw": copy.deepcopy(raw)}
        # The FULL plan stays in state: the progress grid counts against it,
        # and a resumed sweep still shows 28 of 56 rather than restarting the
        # count at nought. Only the PRICE is of what is left.
        app.state["raw_plan"] = raw
        day = runs_mod.today()
        priced, already_done = runs_mod.remaining_plan(
            raw, set(read_done(profile, day)), day)
        out = plan_mod.cost(priced, config.SITE_RATES, config.SITE_RATE_BASIS)
        # The board's own spelling, added here rather than in plan.cost():
        # that function is the pricing contract and knows nothing about
        # screens, but every consumer of a line — /confirm server-side and
        # /configure's live JSON — is showing it to a person.
        for line in out.get("lines") or ():
            line["label"] = site_label(line["site"])
        out["already_done"] = already_done
        cap = app.state.get("cap_usd")
        out["over_cap"] = bool(cap is not None and out["total"] > cap)
        out["shortfall"] = (round(max(0.0, out["total"] - cap), 4)
                             if cap is not None else 0.0)
        # The hard stop POST /run will write into the profile. Computed here,
        # once, so the figure /confirm promises the user and the figure the
        # engine enforces cannot be two different numbers.
        out["spend_cap"] = (0.0 if free_only()
                            else spend_cap_for(out))
        # V2-D1: a public paid sweep is authorised by EXACT PLACEMENT of every
        # search's provider ceiling on the visitor's connected accounts —
        # never by the estimate against a balance, never by balances summed.
        # Advisory here: the engine re-reads every account just before its
        # first start and decides again on what it finds. V2-D closeout: the
        # worker's dry run names the mode (scraper.public_paid_mode) — "multi",
        # every account; "single", the one with the most capacity — and there
        # is no third, credit-unaware one: anything else (off, or an engine
        # older than this) means paid searches are unavailable, never the
        # console's estimate-over-credit gate.
        out["coverage"], out["paid_unavailable"] = None, False
        if (app.config.get("PUBLIC_MODE") and not free_only()
                and any(not line["free"] for line in out["lines"] or ())):
            mode = raw.get("public_paid")
            # The console's estimate-over-credit flag means nothing here; only
            # placement below may set it.
            out["over_cap"] = False
            if mode not in ("multi", "single"):
                out["paid_unavailable"] = True
            else:
                keys = _funding_keys(mode)
                cov = plan_mod.coverage(
                    priced, [Decimal(k["capacity_usd"]) for k in keys], out["spend_cap"])
                part = plan_mod.cost(cov.pop("prefix"), config.SITE_RATES,
                                     config.SITE_RATE_BASIS)
                cov["no_ceiling_sites"] = [site_label(s) for s in cov["no_ceiling_sites"]]
                out["coverage"] = dict(cov, partial_estimate=part["total"],
                                       single_account=mode == "single",
                                       funding_ids=[k["id"] for k in keys])
                out["over_cap"] = not cov["full"]
        app.state["plan"] = out
        return out

    def _funding_keys(mode):
        """The connected accounts a public sweep would spend from: all of them
        ("multi"), or the ONE with the most usable capacity, the first added on
        a tie ("single") — the rule the engine applies to its own fresh
        readings (AccountPool.open(single=True))."""
        keys = list(app.state.get("byok_keys") or ())
        if mode == "single" and len(keys) > 1:
            keys = [max(keys, key=lambda k: (Decimal(k["capacity_usd"]), -keys.index(k)))]
        return keys

    def no_key_yet():
        """No verified key on file, so no credit figure to be honest against.

        cap_usd is the flag with a reader: costed()'s over_cap is
        `cap is not None and total > cap`, which is False for ANY total while
        it is None — so every money screen downstream of here would show an
        advisory cap that can never trip, and the engine would run on
        whatever APIFY_TOKEN happens to already be in .env. Every route that
        prices or launches a sweep fails closed on this, not just one.
        """
        return app.state.get("cap_usd") is None

    def free_only():
        """The user chose to search only the sources that cost nothing.

        Recorded on state by POST /key/free, never inferred from a missing
        key: "hasn't connected one yet" and "declined one" need opposite
        answers from every guard below, and cap_usd cannot tell them apart.
        """
        return bool(app.state.get("free_only"))

    def needs_key():
        """Nothing may be priced or launched: no verified key, and no free
        choice either.

        The free path is safe HERE, at the flow guards, only because it is
        unsafe to be wrong further down — POST /run re-checks the priced plan
        itself, so a free-only session that somehow arrives with a paid site
        enabled is refused rather than trusted to have chosen well.
        """
        return no_key_yet() and not free_only()

    def owned_run_banner(step, live=False):
        """The persistent status strip, or None.

        Public mode only, and only for a browser whose SIGNED COOKIE holds a
        run id — so a visitor without one costs no worker call at all, and a
        visitor with somebody else's id gets nothing, because the worker
        checks the owner capability and answers 404 to a stranger exactly as
        it does for /running.

        Deliberately the CHEAP reading: the worker's own status, which
        worker_link caches on `g` and which the rehydrate hook has usually
        already fetched this request. snapshot() is the fuller picture and it
        pages every row the run has produced — fine for /running and for the
        poll, far too much to pay on /review just to draw a strip.

        `found` therefore comes from whatever the last live reading left on
        state, and is absent rather than invented on a fresh process. The
        poll fills it in.
        """
        if not app.config.get("PUBLIC_MODE"):
            return None
        from sweep import worker_link
        if not public.current_run_id():
            return None
        # The POLL may pay for the fuller reading — it is the same call
        # /running makes, and it is where the jobs-found count comes from.
        # A page RENDER may not: snapshot() pages every row the run has
        # produced, which is far too much to draw one line on /review.
        if live and app.state.get("raw_plan"):
            try:
                said = snapshot()["banner"]
            except Exception:
                said = None
            if said:
                # on_results is the render's business, not snapshot's.
                if step == "results" and said["to"] == "results":
                    return None
                return said
        try:
            status = worker_link.owned_status()
        except Exception:
            # Unreachable, expired, or not this visitor's. All three mean
            # the same thing to the strip: nothing to show. They are never
            # distinguished here — that is the ownership boundary.
            return None
        if not status:
            return None
        state = status.get("state")
        if state == "running" and status.get("results_ready") is True:
            # Same reading _liveness makes: the result is final, and the
            # engine's last seconds are not the visitor's to wait through.
            state = "done"
        return run_banner(
            run_phase(state, queued=bool(status.get("queue_position"))),
            queue_position=status.get("queue_position") or 0,
            found=app.state.get("live_found") or None,
            # A "Sweep complete" strip above the jobs it is pointing at is
            # one line of chrome telling the reader to go where they are.
            on_results=(step == "results"))

    def owned_activity(step, live=False):
        """The ONE strip: whichever of the two things Sweep can be doing for
        this browser is the one worth saying.

        Public only, like the sweep half — the console operator is watching
        their own terminal and a strip telling them a model is running would
        be repeating it.
        """
        if not app.config.get("PUBLIC_MODE"):
            return None
        said = parse_banner(
            parse_phase(),
            # Same stand-down rule the sweep half has: "ready" says nothing
            # on the screen it points at — and nothing at all once the
            # visitor has been there. An approved profile is exactly that
            # record: POST /review is the only thing that sets it, and a new
            # résumé pops it again, so it cannot outlive the parse it
            # describes. Without the second half, "Your profile is ready —
            # review profile" reappears over Search preferences and again
            # over the free/paid choice, on the forward path where the
            # profile screen is the page the visitor just left.
            reviewed=(step == "review" or bool(app.state.get("profile"))))
        # ...and it is behind you entirely once a sweep exists. Checked on
        # the run id rather than on the sweep banner, because that banner has
        # already stood itself down on /results — and "Your profile is ready"
        # sliding into the gap it left is how the jobs screen ended up
        # pointing back at the profile.
        if said and said["phase"] == "ready" and public.current_run_id():
            said = None
        return pick_activity(owned_run_banner(step, live=live), said)

    def shell(step, spend=0.0, spend_is_this_sweep=True,
              spend_is_estimate=False, **kw):
        """Every screen gets the meter reflecting ITS OWN state, never a
        figure carried over from another step.

        `spend` is an ARGUMENT, not a lookup: it used to be read from
        app.state["spend"], which /configure set to the estimate and no later
        screen overwrote — so /results showed the estimate under the label
        "Spent" with nothing spent at all. A shared mutable figure cannot
        satisfy the rule in the line above, so there isn't one.

        None means "not known" and renders as that, never as $0.00: a
        fabricated zero on a money display is the same defect pointing the
        other way.

        `spend_is_estimate` is True on the two screens where `spend` is a
        PRICE, not a payment — /configure and /confirm. Nothing has left the
        account there, so nothing may be taken off the remaining credit.

        `spend_is_this_sweep` is False when the figure is the account's
        month-to-date total with no baseline to subtract. The meter then
        must not label it "spent so far", must not paint it the over-cap
        red, and must not fill the bar against the cap — R74 gated the
        Alpine layer of exactly this and left the server-rendered layer,
        so the first paint was the dishonest state it removed.
        """
        cap = app.state.get("cap_usd")
        total = app.state.get("credit_total_usd")
        # Read from the FILE, which also reconciles os.environ with it — so
        # every render leaves this process (and any engine it launches)
        # agreeing with what is actually configured. keys_attached used to
        # count os.environ while this list came from disk: two answers to
        # one question.
        # Public mode never opens .env. The pills carry the operator's own
        # key state — masked, but still their last four and their credit —
        # and no visitor has any business seeing it.
        public_mode = bool(app.config.get("PUBLIC_MODE"))
        pills = ([] if public_mode
                 else key_pills(read_env_tokens(), app.state.get("key_credit")))
        # "Credit left" means every account's credit added up, which is what
        # the header used to LABEL while showing cap_usd — the best single
        # key's balance. On four keys holding $8.33 it read $5.00.
        #
        # Minus this sweep's own spend where that is known, so the figure
        # keeps up with a run instead of standing still at what it was when
        # the last key was verified. Two guards, because `spend` means a
        # different thing on different screens: spend_is_estimate stops a
        # PRICE being subtracted as if it had been paid, and
        # spend_is_this_sweep stops a month-to-date total being subtracted
        # as if this sweep had spent it.
        left = None
        if total is not None:
            left = total
            if spend and spend_is_this_sweep and not spend_is_estimate:
                left = round(max(0.0, total - spend), 2)
        banner = owned_activity(step)
        # The résumé setup (P4-U1) keeps each résumé's text in its track, so
        # "has a résumé" is "has a track" there — the same fact, for the step
        # that opens on it.
        setup = tracks_on()
        facts = ({**app.state, "resume_text": bool(app.state.get("tracks"))}
                 if setup else app.state)
        current = g.get("track")
        return dict(steps=step_states(app.config.get("STEPS", STEPS),
                                      facts, step,
                                      # While a sweep is live, the Search
                                      # stage is that sweep — not the form
                                      # that configures a new one.
                                      links={"key": "running"}
                                      if banner and banner["to"] == "running"
                                      else None),
                    public_mode=public_mode,
                    # Every screen that names a board names it the way the
                    # board spells it. Here rather than per-render because
                    # five templates print a site key and they were not
                    # agreeing: /configure and /confirm showed "linkedin"
                    # while the prose beside them said "LinkedIn".
                    site_label=site_label,
                    apify_guide=app.config.get("APIFY_GUIDE") or {},
                    # Experience is a total number of months on state and a
                    # "N years M months" on screen, and four templates were
                    # each about to do that division themselves.
                    experience_parts=experience_parts,
                    experience_text=experience_text,
                    # The sweep this browser owns, on every screen it has.
                    # A run that outlives the page it was started from is
                    # the promise "you can close this tab" makes, and the
                    # UI had no way to keep it.
                    active_run=banner,
                    step=step, spend=spend, cap_usd=cap,
                    credit_left=left,
                    free_only=free_only(),
                    spend_is_this_sweep=spend_is_this_sweep,
                    fill_pct=fill_pct(spend, cap) if spend_is_this_sweep else 0,
                    # Counted from the environment, not from state: that is
                    # what the engine will actually discover, so a key left in
                    # .env by an earlier session is included rather than the
                    # screen claiming fewer keys than the sweep will see.
                    keys_attached=len(pills),
                    key_pills=pills,
                    # One-shot: popped as it is handed over, so a refusal
                    # shows on the screen it happened on and not again on
                    # the next one.
                    key_notice=app.state.pop("key_notice", None),
                    # Whether a child is alive right now. The detach control
                    # is disabled while one is, because the engine is
                    # holding a client built from one of these keys and
                    # which one is its business, not this screen's.
                    sweep_running=_sweep_in_flight(),
                    # Which résumé this session is working from. A session
                    # fact, so it belongs here rather than in one render:
                    # five routes render the review screen, and the four
                    # error paths would each have to remember it. The name
                    # only — the path is this machine's filesystem and says
                    # nothing the reader needs.
                    resume_name=os.path.basename(
                        (current or {}).get("resume_name")
                        or app.state.get("resume_path") or ""),
                    # The résumé setup (P4-U1), only while it is on: the
                    # résumé this screen is about (its id is what its forms
                    # post back), and every résumé as a page may see it.
                    track_id=current["id"] if current else None,
                    track=track_view(current) if current else None,
                    tracks=track_views() if setup else None,
                    max_tracks=make_profile.MAX_TRACKS,
                    multi_sweep=setup and is_multi(),
                    credit_total_usd=app.state.get("credit_total_usd"),
                    # V2-D1: the visitor's connected accounts, as figures and
                    # worker ids — never a token, never an account's name.
                    byok_keys=(app.state.get("byok_keys") or []) if public_mode else [],
                    **kw)

    # The public sweep screens (sweep/public_sweep.py) render the same
    # chrome, and shell() is where "the same chrome" is defined.
    app.shell = shell

    def spend_delta():
        """This sweep's own spend, or None when it cannot be known.

        account_usage_usd is month-to-date, so a baseline is subtracted; a
        None baseline means "unknown" and must never be subtracted as zero,
        which would report the account's whole month as this sweep's cost.
        Shared with snapshot() so the two screens cannot disagree about a
        KNOWN figure. They do differ deliberately when the baseline is
        unknown: snapshot() branches before this and shows month-to-date with
        a caveat, because a running sweep is better served by a real number
        it can qualify than by nothing, while /results shows "not known"
        rather than attribute a whole month to one sweep.
        """
        # A free sweep launches no paid actor, so zero is a KNOWN figure
        # here, not an unreadable one: there is no token to read the account
        # with, and "not known" over a run that cannot spend is a worse
        # answer than the truth.
        if free_only():
            return 0.0
        spend_now = app.state.get("spend_read_val")
        baseline = app.state.get("baseline_usd")
        if spend_now is None or baseline is None:
            return None
        return round(max(0.0, spend_now - baseline), 4)

    # Which steps of the "where do I find my key" guide have a picture.
    # Read ONCE at start-up, not per render: it is a directory listing, and
    # the answer only changes when somebody adds a file and redeploys.
    #
    # The guide works without any of them — the steps are the instruction and
    # the screenshots only confirm it — so a missing file is a quieter guide
    # rather than a broken image on the screen where a stranger is deciding
    # whether to trust us with an API key.
    def _guide_shots():
        folder = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "static", "apify")
        try:
            have = set(os.listdir(folder))
        except OSError:
            return {}
        return {step: f"apify/{step}.png" for step in
                ("1-signup", "2-console", "3-token")
                if f"{step}.png" in have}

    app.config["APIFY_GUIDE"] = _guide_shots()

    limit_mb = max_upload_bytes / (1024 * 1024)

    # ---- The 1-3 résumé setup (P4-U1; see TRACK_ACTIONS) --------------------
    def tracks_on():
        """The multi-résumé setup is on: public mode and the Multi-Track
        product. Off, nothing reads or writes state["tracks"], and every
        screen, request and session is the one-résumé product's own."""
        from sweep import worker_link
        return bool(app.config.get("PUBLIC_MODE")) and worker_link.multi_enabled()

    def is_multi():
        from sweep import worker_link
        return worker_link.multi_active(app.state)

    def track_ready(track):
        """Everything P4-R1's snapshot will build this résumé's engine-ready
        entry from — its id, text, derivation and engine — approved on the
        review screen, which sets `reviewed` only once make_profile.render
        has accepted the derivation."""
        return bool(track.get("reviewed") and all(
            track.get(key) for key in ("id", "resume_text", "derived", "engine")))

    def setup_ready():
        """1-3 résumés selected and every one of them ready: the only setup
        a key choice, Configure, Confirm or a run is reached from. An
        unselected résumé does not count, ready or not."""
        from sweep import worker_link
        chosen = worker_link.selected(app.state)
        return (1 <= len(chosen) <= make_profile.MAX_TRACKS
                and all(map(track_ready, chosen)))

    def not_ready():
        """Where a setup that cannot search yet goes instead: the review
        screen, which opens on the first selected résumé still to review. None
        when the setup is off, or ready."""
        if not tracks_on() or setup_ready():
            return None
        return redirect(url_for("review"))

    def the_track(default=False):
        """The track this request names (?track= or a form field), found
        among this session's own and never made from the id: None for an id
        that names none of them — a stale page, a forgery, another session's
        — and the caller refuses rather than act on some other track. With
        no id, the one track when there is only one; `default` (a GET of the
        review screen) also takes the first selected résumé still to review.
        """
        tracks = app.state.get("tracks") or []
        tid = request.values.get("track")
        if tid is not None:
            found = next((t for t in tracks if t["id"] == tid), None)
        elif len(tracks) == 1:
            found = tracks[0]
        elif default and tracks:
            found = next((t for t in tracks
                          if t.get("selected", True) and not track_ready(t)), tracks[0])
        else:
            found = None
        g.track = found
        return found

    def track_id():
        """The id of the track this request is about, for the URLs it hands
        on; None (so no parameter at all) with the setup off."""
        current = g.get("track")
        return current["id"] if current else None

    def no_such_track():
        return upload_screen(error="That résumé is not in this search any "
                                   "more. Here are the ones that are."), 404

    def track_view(track):
        """One résumé as a page may see it: the id its buttons post back, its
        label and place, whether it is in the search, how ready it is, and
        the file name the review screen has always shown. Never its text,
        its derivation, a profile, or anything built for the engine."""
        tracks = app.state.get("tracks") or []
        phase = parse_phase(track)
        return {"id": track["id"], "label": track["name"],
                "n": tracks.index(track) + 1 if track in tracks else None,
                "selected": track.get("selected", True),
                "file": os.path.basename(track.get("resume_name") or ""),
                "status": ("ready" if track_ready(track)
                           else "review" if track.get("derived") is not None
                           else phase or "unread")}

    def track_views():
        return [track_view(t) for t in app.state.get("tracks") or ()]

    def settle_tracks():
        """After any change to the résumés or the Sweep's preferences, with
        the setup on.

        The one-résumé Sweep reads `derived` and `derived_engine` off state,
        so while exactly one résumé is selected they are ITS (the same
        objects, not copies); otherwise they are absent, and nothing can run
        one résumé's profile for two. And a planned Multi-Track Sweep whose
        inputs (worker_link.inputs: the selected résumés in order, the plan's
        preferences, free or paid) moved is no longer approved. A label, an
        unselected résumé or a look at a screen moves none of them.
        """
        if not tracks_on() or "tracks" not in app.state:
            return
        from sweep import worker_link
        chosen = worker_link.selected(app.state)
        one = chosen[0] if len(chosen) == 1 else {}
        for key, field in (("derived", "derived"), ("derived_engine", "engine")):
            if one.get(field) is not None:
                app.state[key] = one[field]
            else:
                app.state.pop(key, None)
        planned = app.state.get(worker_link.PLANNED)
        if (planned and "run_id" not in planned
                and planned["snapshot"]["inputs"] != worker_link.inputs(app.state)):
            del app.state[worker_link.PLANNED]

    def label_taken(label, track=None):
        """Another of this session's résumés already has `label`, compared
        stripped and casefolded ("Frontend", "frontend", " Frontend " are
        one): its view and every sentence naming it could not be told apart.
        Only the setup as it stands — a run's frozen labels are its own."""
        want = label.strip().casefold()
        return any(t["name"].strip().casefold() == want
                   for t in app.state.get("tracks") or () if t is not track)

    def default_label(track):
        """A label until the visitor names one (design §D.2): the résumé's
        first search title, each lower-case word capitalised, " (2)" after
        a label another résumé already has. None without a usable title."""
        roles = (track.get("derived") or {}).get("role_keywords") or []
        if not roles or not isinstance(roles[0], str):
            return None
        base = " ".join(w[:1].upper() + w[1:] if w.islower() else w
                        for w in roles[0].split())[:40]
        label, n = base, 2
        while label_taken(label, track):
            label = f"{base[:40 - len(f' ({n})')]} ({n})"
            n += 1
        return label if label and public.run_label(label, 0) == label else None

    FULL = (f"You have {make_profile.MAX_TRACKS} résumés here, which is the "
            f"most one search takes. Remove one to add another.")

    def add_track(filename, text):
        """The upload became a track: a new id, a placeholder label, selected.
        (its id, None), or (None, the sentence refusing it).

        Checked and added under one lock, so two uploads racing cannot make a
        fourth; a refusal changes nothing. The session's FIRST résumé is a
        new search, exactly as a one-résumé upload always was (see the
        legacy path below); a second or third joins the one in progress.
        """
        refusal = None
        with _tracks_lock:
            tracks = app.state.get("tracks") or []
            if len(tracks) >= make_profile.MAX_TRACKS:
                refusal = FULL
            elif any(t["resume_text"] == text for t in tracks):
                # A second copy of a résumé already here: a resubmitted form,
                # or the same file twice. It could only search twice for the
                # same jobs.
                refusal = "That résumé is already here."
            else:
                if not tracks:
                    for stale in PREFERENCE_KEYS + (
                            "derived", "derived_engine", "profile",
                            "profile_source", "plan", "raw_plan"):
                        app.state.pop(stale, None)
                issued = app.state.setdefault("track_ids_issued", [])
                tid = new_track_id()
                # Never an id this session has already had: a deleted
                # track's id must not come back as another résumé's.
                while tid in issued:
                    tid = new_track_id()
                issued.append(tid)
                # Its place in the list, or the next number no other label has.
                n = len(tracks) + 1
                while label_taken(f"Résumé {n}"):
                    n += 1
                tracks.append({
                    "id": tid, "name": f"Résumé {n}", "renamed": False,
                    "resume_name": filename, "resume_text": text,
                    "derived": None, "engine": None, "reviewed": False,
                    "selected": True})
                app.state["tracks"] = tracks
        if refusal:
            return None, refusal
        settle_tracks()
        return tid, None

    @app.post("/tracks")
    def track_action():
        """One action on one of this session's résumés: rename it, put it in
        or take it out of the search, move it up or down, or remove it.

        The target is found among this session's own tracks by id
        (the_track) — an id it does not hold is refused, and never read as
        some other track. A label is presentation only: it changes nothing
        a plan was built from, so a rename keeps an approved plan.
        """
        if not tracks_on():
            abort(404)
        track = the_track()
        if track is None or request.values.get("track") is None:
            return no_such_track()
        action = request.form.get("do")
        if action not in TRACK_ACTIONS:
            return upload_screen(error="Sweep did not recognise that."), 400
        tracks = app.state["tracks"]
        if action == "rename":
            name = (request.form.get("name") or "").strip()
            # public.run_label is the cookie's own rule for a label (design
            # §N.1): 1-40 printable characters.
            if public.run_label(name, 0) != name or not name:
                return upload_screen(error="A résumé's name is 1 to 40 "
                                           "letters, numbers or symbols."), 400
            if label_taken(name, track):
                # Refused before anything changes: the label, the id, a plan
                # and a run's labels are all as they were.
                return upload_screen(error="Another résumé already has that "
                                           "name. Choose a different one."), 400
            track["name"], track["renamed"] = name, True
            # A track of the run in progress, or of the one whose Results
            # these are, keeps its new name after a restart too (P4-R2).
            public.relabel_run_track(track["id"], name)
            return redirect(url_for("review") if request.form.get("back") == "review"
                            else url_for("upload"), code=303)
        if action in ("select", "deselect"):
            track["selected"] = action == "select"
        elif action == "remove":
            tracks.remove(track)
            g.track = None
        elif action == "retry":
            # A read that failed goes back in the queue, and only by this
            # deliberate click: nothing retries on its own, and the read it
            # queues is one more attempt against the quota when it runs.
            with _parse_lock:
                if track.get("derived") is None and parse_phase(track) == "failed":
                    track.pop("parse", None)
        else:
            at = tracks.index(track)
            to = at - 1 if action == "up" else at + 1
            if 0 <= to < len(tracks):
                tracks[at], tracks[to] = tracks[to], tracks[at]
        settle_tracks()
        # The review page's own buttons come back to it.
        return redirect(url_for("review") if request.form.get("back") == "review"
                        else url_for("upload"), code=303)

    def upload_screen(**kw):
        """The front door, from all four ways it is reached: a fresh visit,
        the two rejected-file paths, and the 413 handler.

        The size limit is injected, so the copy and the client-side check both
        read it from here — a template that names 15 MB beside an app
        configured for 1 MB tells the user the wrong number.

        `read` is the CACHED derivation and never a fresh model call: coming
        back to step 1 with a résumé already read should show what the model
        found, not claim nothing has been read, and this screen must not be
        able to spend anything.
        """
        # A batch upload that added some and not all of its files says which
        # here, once, after its redirect (add_resumes).
        kw.setdefault("problems", app.state.pop("upload_report", None))
        return render_template("upload.html", **shell(
            # The setup lists every résumé instead of the one read last.
            "upload", max_mb=limit_mb,
            read=None if tracks_on() else app.state.get("derived"),
            setup_ready=tracks_on() and setup_ready(),
            paid=[site_label(s) for s in paid_sites()], **kw))

    # public.harden's refusal of a new session room lands on this screen.
    app.upload_screen = upload_screen

    @app.errorhandler(413)
    def too_large(e):
        # The limit is on the whole request, so with the setup's several
        # files it is their total (the page says so too).
        return upload_screen(
            error=(f"That upload is larger than {limit_mb:g} MB. Add fewer "
                   "résumés at a time, or export a smaller PDF."
                   if tracks_on() else
                   f"That file is larger than {limit_mb:g} MB. "
                   "Export a smaller PDF and try again.")), 413

    @app.get("/")
    def upload():
        return upload_screen()

    @contextlib.contextmanager
    def saved(upload_file):
        """The upload on disk for as long as it is being read.

        A public visitor's résumé is parsed from a temp file and deleted in
        this same request, whatever happens. RESUME_DIR is ONE fixed path:
        on a shared box every visitor would overwrite the last one's PDF and
        leave their own sitting there afterwards.
        """
        public_mode = app.config.get("PUBLIC_MODE")
        if public_mode:
            handle, path = tempfile.mkstemp(prefix="sweep-", suffix=".pdf")
            os.close(handle)
        else:
            os.makedirs(resume_dir, exist_ok=True)
            path = os.path.join(resume_dir, "resume.pdf")
        try:
            upload_file.save(path)
            yield path
        finally:
            if public_mode:
                with contextlib.suppress(OSError):
                    os.unlink(path)

    def read_upload(path):
        """(text, None) for the PDF at `path`, or (None, (sentence, status)):
        every check and count one uploaded résumé has — a batch reads each of
        its files through here, so each is exactly a lone upload."""
        # Checked in every mode: the parser should be handed a PDF
        # because the form said PDF, not because the browser was
        # honest about it.
        if not public.looks_like_pdf(path):
            return None, ("That file is not a PDF. Export your résumé as a "
                          "PDF and try again.", 400)
        if app.config.get("PUBLIC_MODE"):
            # P4-S1B: reading is the expensive part, so it is counted
            # before it starts, and counted whatever it turns out to be.
            refused = public.admit_parse(app)
            if refused:
                return None, (refused, 429)
            from sweep import safe_pdf
            began = _time_mod.monotonic()
            size = os.path.getsize(path)
            try:
                text = extract(path)
            except safe_pdf.Unreadable as exc:
                public.audit("parse", outcome=exc.category, bytes=size,
                             ms=int((_time_mod.monotonic() - began) * 1000))
                return None, (exc.message, exc.status)
            public.audit("parse", outcome="ok" if text.strip() else "empty",
                         bytes=size,
                         ms=int((_time_mod.monotonic() - began) * 1000))
        else:
            text = extract(path)
        if not text.strip():
            return None, ("That PDF has no text in it — it is probably a "
                          "scan. Export a text PDF and try again.", 400)
        return text, None

    def add_resume(upload_file):
        """One uploaded PDF, read and made a track of its own: (its id, None),
        or (None, (sentence, status)) with nothing added."""
        if len(app.state.get("tracks") or ()) >= make_profile.MAX_TRACKS:
            # Refused before the file is read (add_track checks again).
            text = None
        else:
            with saved(upload_file) as path:
                text, refused = read_upload(path)
            if refused:
                return None, refused
        tid, refusal = add_track(upload_file.filename, text)
        return tid, refusal and (refusal, 400)

    def add_resumes():
        """POST /resume with the setup on: one to three PDFs in one upload,
        each a track of its own, appended in the order they were chosen.

        One file at a time, start to finish (add_resume: the same checks,
        the same parse count and the same one-child reader as a lone
        upload), so no two are ever parsed at once. Nothing is derived here:
        each résumé is read by the model later, on its own, through /derive
        — the review screen goes on to the next one still to read. A file
        refused is named, and leaves the others as they are.
        """
        files = [f for f in request.files.getlist("resume") if f.filename]
        if not files:
            return upload_screen(error="Choose a PDF to upload."), 400
        room = make_profile.MAX_TRACKS - len(app.state.get("tracks") or ())
        if len(files) > 1 and len(files) > room:
            # Refused before any is read: which of them were meant is the
            # visitor's to say, not a guess by the order they came in.
            return upload_screen(error=FULL if room <= 0 else (
                f"This search has room for {room} more "
                f"résumé{'s' * (room > 1)}, and you chose {len(files)}. "
                f"Choose {'one' if room == 1 else f'up to {room}'} and try "
                f"again.")), 400
        added, refused = [], []
        for upload_file in files:
            tid, why = add_resume(upload_file)
            if tid:
                added.append(tid)
            else:
                refused.append((os.path.basename(upload_file.filename), why))
        if not refused:
            return redirect(url_for("review", track=added[0]))
        if len(files) == 1:
            # The one-file upload's own answer, exactly as it always was.
            (_name, (sentence, status)), = refused
            return upload_screen(error=sentence), status
        report = [f"Could not add {name}. {sentence}"
                  for name, (sentence, _status) in refused]
        if not added:
            return upload_screen(problems=report), refused[0][1][1]
        report.append(f"Added {len(added)} of {len(files)} résumés. Review "
                      f"{'it' if len(added) == 1 else 'each one'} below.")
        # Redirected, so a refresh does not send the files again.
        app.state["upload_report"] = report
        return redirect(url_for("upload"), code=303)

    @app.post("/resume")
    def resume():
        if tracks_on():
            return add_resumes()
        upload_file = request.files.get("resume")
        if upload_file is None or not upload_file.filename:
            return upload_screen(error="Choose a PDF to upload."), 400
        with saved(upload_file) as path:
            text, refused = read_upload(path)
        if refused:
            return upload_screen(error=refused[0]), refused[1]
        # The NAME in public mode, never a path: the file is already gone,
        # and the review screen only ever shows its basename.
        app.state["resume_path"] = (upload_file.filename
                                    if app.config.get("PUBLIC_MODE") else path)
        app.state["resume_text"] = text
        # The previous résumé's parse belongs to the previous résumé.
        # Without this, uploading a second CV shows the FIRST one's skills
        # and titles — derived_for_state() caches on state and only ever
        # asks the model when there is nothing there.
        #
        # And so do the previous résumé's SEARCH PREFERENCES. Clearing only
        # the parse left the next candidate with the last one's scope,
        # cities, pay floor and depth, while their avoid-list — which lived
        # inside `derived` — was reset with it. Half kept and half discarded,
        # with nothing on screen saying which. A new résumé is a new search.
        for stale in PREFERENCE_KEYS + ("derived", "derived_engine", "profile",
                                        "profile_source", "plan", "raw_plan"):
            app.state.pop(stale, None)
        return redirect(url_for("review"))

    COMMODITY_WEIGHT = 2

    # How long a "reading" marker is believed. The parse is two model calls
    # and gunicorn kills the worker at MAX_TIMEOUT+60, so anything older than
    # this is a request that died without reaching its own `finally` — and a
    # strip still claiming to be reading a résumé nobody is reading is the
    # exact dishonesty this whole component exists to remove.
    PARSE_STALE_SECONDS = 20 * 60

    def parse_phase(rec=None):
        """reading / ready / failed / None, for THIS browser.

        Read from the session room, which is where the parse already writes
        its result — so the marker and the thing it describes cannot drift,
        and both die together if the process does. That last part is the
        honest half: a Render restart loses the résumé text as well, so
        there is nothing to resume and the strip correctly says nothing.

        `rec` is the résumé asked about: one track of the résumé setup, or
        (the default) state itself, the one résumé. With the setup on, the
        default asks about all of them — the strip is the browser's, and
        says the most pressing of theirs.
        """
        if rec is None and tracks_on():
            phases = {parse_phase(t) for t in app.state.get("tracks") or ()}
            return next((p for p in ("reading", "failed", "ready") if p in phases), None)
        rec = app.state if rec is None else rec
        if rec.get("derived") is not None:
            return "ready"
        mark = rec.get("parse")
        if not mark:
            return None
        if mark.get("state") == "reading":
            if wall_now() - mark.get("at", 0) > PARSE_STALE_SECONDS:
                return "failed"
            return "reading"
        return mark.get("state")

    def parse_in_flight(rec=None):
        return parse_phase(rec) == "reading"

    def derived_for_state(rec=None):
        """The model call is made once per résumé and cached on state — a
        cost, so never repeated just because the review screen reloads.

        The cache was the only guard, and it is only set AFTER the call
        returns: during the twenty-to-a-hundred-and-fifty seconds the model
        takes, `derived` is still None, so a refresh — which deriving.html
        auto-submits — started a SECOND parse. Measured: two model calls,
        four GPU calls, and two of a visitor's three daily slots for one
        résumé. The marker closes that window.

        `rec` as for parse_phase: a track keeps its own derivation, engine
        and marker, so one résumé's parse — or its failure — never touches
        another's.
        """
        rec = app.state if rec is None else rec
        derived = rec.get("derived")
        if derived is not None:
            return derived
        with _parse_lock:
            # Re-read under the lock: two requests that both saw None above
            # would otherwise both spend.
            if rec.get("derived") is not None:
                return rec["derived"]
            # And one résumé at a time per browser, whichever route asks: a
            # second tab, or an old page's form, waits for the one reading.
            others = () if rec is app.state else app.state.get("tracks") or ()
            if parse_in_flight(rec) or any(map(parse_in_flight, others)):
                raise ParseInFlight
            rec["parse"] = {"state": "reading", "at": wall_now()}
        return read_claimed(rec)

    def read_claimed(rec):
        """The model call for a résumé already marked reading under
        _parse_lock, by derived_for_state or read_next.

        What it learns is written into that résumé's own record, field by
        field, never a copy of the session written back: a review saved
        while this runs is left exactly as it was. A track removed meanwhile
        gets its result in a record nothing holds any more, so it does not
        come back.
        """
        try:
            # Phase 0b: the engine this derivation runs under, recorded WITH
            # it and never re-read — the worker must stamp what derived the
            # résumé, not what this process happens to say later.
            engine = skill_concepts.engine_version()
            derived = derive(rec["resume_text"], _prefs(app.state))
        except Exception:
            # Marked, not cleared: "we tried and it did not work" is a state
            # the visitor can act on, and an absent marker would send them
            # round the auto-submitting screen again.
            rec["parse"] = {"state": "failed", "at": wall_now()}
            raise
        rec["derived"] = derived
        rec["derived_engine" if rec is app.state else "engine"] = engine
        rec.pop("parse", None)
        if rec is not app.state:
            if derived and not rec.get("renamed"):
                rec["name"] = default_label(rec) or rec["name"]
            settle_tracks()
        return derived

    def the_record(default=False):
        """The résumé this request is about: one of the setup's tracks, found
        by the_track (None: refuse), or — the setup off — state itself, the
        one résumé every route here has always read."""
        return the_track(default) if tracks_on() else app.state

    # ---- Two or three résumés: one review page (the unified review) -------
    def unified():
        """The setup holds two or three résumés, so their review is ONE page:
        it reads them one after another (read_next) while the visitor
        reviews each as soon as it is read. One résumé keeps its own reading
        screen and review, exactly as before."""
        return tracks_on() and len(app.state.get("tracks") or ()) > 1

    CARD_STATES = {"ready": "reviewed", "review": "ready", "reading": "reading",
                   "failed": "failed"}

    def resume_cards(open_track=None):
        """The unified page as a page may see it: a card per résumé in the
        setup's order (track_view, its state, and counts the review screen
        already shows), which one is open for editing, and the sentences for
        the banner and the button. Never a derivation's engine fields, a
        profile or anything built for the engine."""
        from sweep import worker_link
        cards = []
        for t in app.state.get("tracks") or ():
            view = track_view(t)
            mark, derived = t.get("parse") or {}, t.get("derived") or {}
            state = CARD_STATES.get(view["status"], "queued")
            cards.append(dict(
                view, state=state, open=t is open_track,
                roles=len(derived.get("role_keywords") or ()),
                skills=len(derived.get("skill_weights") or ()),
                why=mark.get("why") if state == "failed" else None,
                limited=state == "failed" and bool(mark.get("limited"))))
        chosen = {t["id"] for t in worker_link.selected(app.state)}
        inc = [c for c in cards if c["id"] in chosen]
        reading, queued, ready, reviewed, failed = (
            [c for c in inc if c["state"] == s]
            for s in ("reading", "queued", "ready", "reviewed", "failed"))
        # The order they will be read in: the one reading, then the rest.
        line = reading + queued
        for before, c in zip(line, line[1:]):
            c["after"] = before["n"]

        def some(n):
            return f"{n} résumé{'s' * (n != 1)}"
        done = len(ready) + len(reviewed)
        if line:
            title = "Reading your résumés"
            status = f"{done} of {len(inc)} ready · " + (
                f"Reading résumé {reading[0]['n']}" if reading
                else f"Résumé {queued[0]['n']} is next")
        elif inc and len(reviewed) == len(inc):
            title, status = "All résumés reviewed", "Every résumé in this search is ready."
        elif not inc:
            title, status = "Your résumés", "Include at least one résumé to search."
        else:
            title = "Review your résumés"
            status = " ".join(filter(None, (
                ready and (f"{some(len(ready))} ready to review." if failed else
                           f"All résumés are read — review the remaining "
                           f"{some(len(ready))} to continue."),
                failed and (f"Résumé {failed[0]['n']} wasn't read: today's limit "
                            f"is reached." if failed[0]["limited"] else
                            f"Résumé {failed[0]['n']} couldn't be read.")
                + " Try again, or leave it out to continue.")))
        blocker = (None if setup_ready()
                   else f"Reading {some(len(line))}…" if line
                   else f"Review {some(len(ready))} to continue" if ready
                   else f"Try again or leave out résumé {failed[0]['n']} to continue"
                   if failed else "Include at least one résumé to continue")
        return {"cards": cards, "title": title, "status": status,
                "reading": bool(line), "blocker": blocker}

    def profile_context(derived):
        """What the review screen shows for one derivation."""
        # The model already read the résumé, so the person's own name is
        # right there — typing it again was busywork. A profile chosen
        # earlier in the session still wins: that is the name the rest of the
        # flow is already using.
        suggested = (app.state.get("profile")
                     or make_profile.profile_name_for(derived))
        return dict(
            derived=derived,
            commodity=[w["term"] for w in derived["skill_weights"]
                       if w["weight"] <= COMMODITY_WEIGHT],
            importance=importance_badges(derived),
            suggested_name=suggested,
            # Surfaced on arrival, not after a rejected submit: a suggested
            # name is very often one the user already has a profile for, and
            # autofilling straight into a guaranteed 409 would just trade one
            # piece of friction for another.
            clash=(suggested if suggested and profile_exists(suggested)
                   else None))

    def review_screen(**kw):
        """review.html: one résumé's profile — and, with two or three, the
        page they share, with that one open (g.track) or none."""
        if unified():
            kw["resumes"] = resume_cards(g.get("track"))
        return render_template("review.html", **shell("review", **kw))

    def unified_review():
        """GET /review with two or three résumés. No model call, ever: the
        page's script asks for each read (read_next). Open for editing: the
        résumé named, once it is read; with none named, the first in the
        search read and not yet reviewed; else none, and every card is
        compact."""
        from sweep import worker_link
        named = request.args.get("track") is not None
        track = the_track() if named else None
        if named and track is None:
            return no_such_track()
        if not named:
            track = next((t for t in worker_link.selected(app.state)
                          if t.get("derived") is not None and not t.get("reviewed")),
                         None)
        g.track = track if track and track.get("derived") is not None else None
        if g.track is None:
            return review_screen()
        return review_screen(**profile_context(g.track["derived"]))

    def read_next():
        """POST /derive from the unified page's script, as JSON: read the
        next résumé and say what happened; the page asks again for the one
        after. So they are read one after another, in the setup's order,
        while the visitor reviews what is already read — and only while a
        page is open: nothing here runs in the background.

        Chosen and claimed in one step under _parse_lock: the first résumé
        in the search not read, not being read and not failed. Nothing
        starts while any of this browser's résumés is being read (`busy`: a
        second tab, or a page reopened mid-read), and nothing left out,
        removed, read or failed is read — a failure waits for Try again. The
        read is the one every route makes (read_claimed, metered): one
        attempt against the quota each, and none for asking.
        """
        from flask import jsonify

        from sweep import worker_link
        with _parse_lock:
            busy = next((t for t in app.state.get("tracks") or ()
                         if parse_in_flight(t)), None)
            rec = None if busy else next(
                (t for t in worker_link.selected(app.state)
                 if t.get("derived") is None and parse_phase(t) is None), None)
            if rec is not None:
                rec["parse"] = {"state": "reading", "at": wall_now()}
        if busy is not None:
            return jsonify(state="busy", track=busy["id"])
        if rec is None:
            return jsonify(state="idle")
        try:
            derived = read_claimed(rec)
        except public.BetaLimited as exc:
            # Nothing was spent. The limit's own neutral sentence stays on
            # the card, and the page stops asking.
            rec["parse"] = {"state": "failed", "at": wall_now(),
                            "why": str(exc), "limited": True}
            return jsonify(state="limited", track=rec["id"]), 429
        except Exception as exc:
            rec["parse"] = {"state": "failed", "at": wall_now(),
                            "why": derive_failure(exc)[0]}
            return jsonify(state="failed", track=rec["id"])
        if not derived:
            app.logger.warning("derive returned %r for the résumé", derived)
            rec["derived"] = None
            rec["parse"] = {"state": "failed", "at": wall_now(), "why": NOTHING_RETURNED}
            return jsonify(state="failed", track=rec["id"])
        return jsonify(state="read", track=rec["id"])

    @app.get("/review")
    def review():
        if unified():
            return unified_review()
        rec = the_record(default=True)
        if rec is None:
            return (no_such_track() if request.args.get("track") is not None
                    else redirect(url_for("upload")))
        if not rec.get("resume_text"):
            return redirect(url_for("upload"))
        # The model call takes seconds, so it deliberately does NOT happen in
        # this render. It used to, which meant the browser sat on the PREVIOUS
        # page for the whole wait with nothing the server could show — there
        # was no response to put a loading state in. Hand back the working
        # screen instead and let POST /derive make the call: a form POST keeps
        # that screen on display until the redirect lands.
        if rec.get("derived") is None:
            phase = parse_phase(rec)
            if phase == "failed":
                return render_template("deriving.html", **shell(
                    "review",
                    error="Sweep could not read that résumé. Nothing was "
                          "charged. Try uploading it again — a text-based "
                          "PDF rather than a scan works best.")), 502
            # `waiting` is the whole fix for the duplicate: the screen starts
            # a parse only when there is not one already running, and watches
            # instead when there is.
            return render_template("deriving.html", **shell(
                "review", waiting=(phase == "reading")))
        return review_screen(**profile_context(derived_for_state(rec)))

    @app.post("/derive")
    def derive_post():
        """Make the one model call, then send the user to the real screen.

        A POST, not a GET, because it is not idempotent — it spends a model
        call. derived_for_state() caches on state, so a reload after this
        lands on the review screen rather than paying twice.
        """
        # The unified page's script asks for JSON: the next résumé, chosen
        # by the server (read_next). A form post is the reading screen's.
        if unified() and request.accept_mimetypes.best == "application/json":
            return read_next()
        rec = the_record()
        if rec is None:
            return no_such_track()
        if not rec.get("resume_text"):
            return redirect(url_for("upload"))
        failed = derive_screen(rec)
        if failed is not None:
            return failed
        return redirect(url_for("review", track=track_id()))

    def derive_screen(rec):
        """Derive `rec` (derived_for_state), or the screen that says why it
        did not work — None when it did. The one answer POST /derive and POST
        /review's fallback both give (P4-S1C): the fallback used to let these
        failures out as a bare 500. A failure still spends its slot."""
        try:
            derived = derived_for_state(rec)
        except ParseInFlight:
            # A refresh, a second tab, or a double-submit. The parse that is
            # already running is the one to watch.
            return redirect(url_for("review", track=track_id()))
        except public.BetaLimited:
            # Not a model failure and not this app's error page: the beta
            # budget has its own 429 handler, and the catch-all below would
            # turn "you have had your three for today" into "the model did
            # not answer".
            raise
        except Exception as exc:
            error, status = derive_failure(exc)
            return render_template("deriving.html", **shell(
                "review", error=error)), status
        # A falsy derivation is indistinguishable from "not derived yet" on
        # state, so GET /review would hand back the working screen — which
        # submits ITSELF, calling the model again, once per lap, forever.
        # Reported rather than redirected: the error screen carries no
        # auto-submit, which is what breaks the loop.
        if not derived:
            app.logger.warning("derive returned %r for the résumé", derived)
            return render_template("deriving.html", **shell(
                "review", error=NOTHING_RETURNED)), 502
        return None

    NOTHING_RETURNED = ("The model returned nothing for that résumé. Try a "
                        "text-based PDF export.")

    def derive_failure(exc):
        """(sentence, status) for a derivation that raised `exc`: the fixed
        or self-composed sentence a screen may show, for derive_screen and
        the review page's reader (read_next) alike."""
        if isinstance(exc, local_profile.Escalated):
            # The local engine read the résumé and then REJECTED its own
            # answer — dates it could not reconcile, or, far more often
            # here, no job title that survived validation.
            #
            # It is a plain RuntimeError rather than an InferenceError, so
            # it fell past the branch below into the catch-all and came out
            # as "export your résumé as a text-based PDF rather than a
            # scan". That advice is wrong twice: the PDF is fine, and
            # re-uploading it fails identically every time.
            #
            # Public mode has no output/ corpus (docs/public-beta.md), so
            # `fields_for` has only the résumé's own job titles to work
            # from — and a résumé whose every role reads "(Intern)" or
            # "Student Lead" yields none of them. That is a real limit of
            # this deployment and the screen says so, rather than blaming
            # the file.
            app.logger.warning("derive escalated: %s", "; ".join(exc.reasons))
            no_titles = any("role_keywords" in r for r in exc.reasons)
            return ((
                "Sweep read your résumé but could not work out which job "
                "titles to search for. That usually happens when the "
                "roles on it are internships or study positions rather "
                "than the job you are looking for now. Nothing was "
                "charged. Try a résumé that names the role you want, or "
                "add it as your most recent title."
                if no_titles else
                "Sweep read your résumé but was not confident enough in "
                "what it found to build a profile from it. Nothing was "
                "charged. A résumé with clearer dates and role titles "
                "usually works.")
                if app.config.get("PUBLIC_MODE") else
                f"The local engine rejected its own parse: {exc}"), 422
        if isinstance(exc, make_profile.ModelAnswerError):
            # The one exception whose text this app composed itself, from the
            # response's own finish_reason enum. Everything else stays behind
            # the fixed message below, because a client library's error can
            # carry the request URL.
            app.logger.warning("derive failed: %s", exc)
            return (f"The model did not answer: {exc}. Your résumé is "
                    "fine — this is the model call, not the PDF."), 502
        if isinstance(exc, inference.InferenceError):
            # Safe to show in full: inference.py composes these itself and
            # they never carry urllib's text. They are also the only
            # errors the catch-all below actively MISDIRECTS — "an
            # exhausted API quota or a scanned PDF" is the wrong advice
            # for "the model service is not running".
            app.logger.warning("derive failed: %s", exc)
            return ("Sweep could not reach the service that reads résumés. "
                    "Nothing was charged. Try again in a minute."
                    if app.config.get("PUBLIC_MODE") else
                    f"The local model could not be reached: {exc}"), 502
        if isinstance(exc, NotConfigured):
            # Safe to show in full: this app composed it. A 500, not a 502
            # — nothing upstream was reached, and nothing upstream is at
            # fault.
            app.logger.warning("derive not configured: %s", exc)
            return str(exc), 500
        # The message is fixed, not str(exc): a client library's error can
        # carry the request URL, and this app's whole job is to be careful
        # with the credentials in .env.
        #
        # It no longer blames the PDF outright. A quota, an expired key and
        # a network failure all land here too, and telling someone their
        # résumé is a scan when the API refused the call sends them to
        # re-export a file that was never the problem.
        app.logger.warning("derive failed: %s", exc)
        # Two audiences, two true sentences. The operator can read
        # their own terminal; a beta visitor has none, no key of
        # their own in this call, and nothing to fix but the PDF.
        return ("Sweep could not read your résumé just now. Nothing "
                "was charged. Try again in a minute — or, if it keeps "
                "failing, export your résumé as a text-based PDF "
                "rather than a scan and upload it again."
                if app.config.get("PUBLIC_MODE") else
                "The model call failed. The reason is in the terminal "
                "running Sweep — an exhausted API quota, a key that no "
                "longer works, or a scanned PDF with no text layer are "
                "the usual causes."), 502

    def auto_profile_name(derived):
        """A name nobody had to type.

        Public mode writes no file — `public.harden` replaces write_profile
        with one that keeps the source in memory — so the name only labels
        the exports at the end. Asking a job seeker to invent one, in a
        required field, beside a sentence about Python filenames, was a step
        with nothing on the other side of it.

        `profile_name_for` returns "" for a résumé whose name does not
        transliterate, which locally means "type one yourself" and here has
        to mean something. "sweep" is what worker_link.rehydrate already
        falls back to for the same reason.
        """
        return make_profile.profile_name_for(derived) or "sweep"

    @app.post("/review")
    def review_post():
        # The résumé this form reviews: with the setup on, the track its id
        # names in THIS session — never another because that one is gone.
        rec = the_record()
        if rec is None:
            return no_such_track()
        if not rec.get("resume_text"):
            return redirect(url_for("upload"))
        # Approving a profile that is still being read would reach
        # derived_for_state() and start a second parse — the same window the
        # marker closes for GET, through the other door.
        if parse_in_flight(rec):
            return redirect(url_for("review", track=track_id()))
        derived_now = rec.get("derived")
        if app.config.get("PUBLIC_MODE"):
            # No field to read: the public screen does not render one.
            name = (app.state.get("profile")
                    or auto_profile_name(derived_now or {}))
        else:
            name = (request.form.get("name") or "").strip()
        # Nothing derived yet means this reaches the model: the same answers
        # as POST /derive for everything that can go wrong (P4-S1C).
        failed = derive_screen(rec)
        if failed is not None:
            return failed
        derived = rec["derived"]
        commodity = [w["term"] for w in derived["skill_weights"]
                     if w["weight"] <= COMMODITY_WEIGHT]
        importance = importance_badges(derived)
        if not name:
            return review_screen(
                derived=derived, commodity=commodity,
                importance=importance,
                suggested_name="",
                error="Give the profile a name."), 400
        if not _valid_profile_name(name):
            return review_screen(
                derived=derived, commodity=commodity,
                importance=importance,
                suggested_name=name,
                error="Use letters, numbers, dashes and underscores only "
                      "— this becomes a filename."), 400

        try:
            kept = reweighted(derived, request.form.getlist("term"),
                              request.form.getlist("weight"),
                              request.form.getlist("drop"),
                              request.form.get("add_skills") or "",
                              request.form.get("add_weight") or "")
            kept = with_experience(kept,
                                   request.form.get("experience_years"),
                                   request.form.get("experience_months"))
        except _FormError as exc:
            return review_screen(
                derived=derived, commodity=commodity,
                importance=importance,
                suggested_name=name, error=str(exc)), 400
        # Refuse to overwrite an existing profile unless the user says so.
        # This screen writes profiles/<name>.py, /estimate rewrites the same
        # file on every configure change, and a profile can carry weeks of
        # hand-tuning — profiles/kartik_reachable.py exists precisely because
        # someone tuned it against a real sweep.
        # Public mode never writes into profiles/, so there is nothing of the
        # visitor's to protect — and the directory it would be consulting is
        # the OPERATOR's, checked into the repo. A visitor called Kartik
        # would otherwise collide with profiles/kartik_reachable.py and be
        # shown a clash they cannot understand or resolve.
        if (not app.config.get("PUBLIC_MODE")
                and profile_exists(name) and not request.form.get("overwrite")):
            return review_screen(
                derived=derived, suggested_name=name,
                clash=name,
                error=f"A profile named {name} already exists. Pick another "
                      f"name, or confirm you want to replace it."), 409

        # The default scope becomes a real choice here, before the first
        # profile is written. Left unset, `locations` defaulted to ["Remote"]
        # and nothing overrode SITES, so LinkedIn silently inherited
        # config.py's ["India", "Remote"] while the next screen's radio said
        # "Remote, from anywhere" — the plan and the screen disagreed until
        # something was touched.
        ensure_scope()
        source = make_profile.render(name, kept, _prefs(app.state))
        app.write_profile(name, source)
        # The reviewed list becomes the state, not just the file. /estimate
        # re-renders this same profile from state["derived"] on every
        # Configure change, so leaving the model's original here put every
        # dropped term and every un-edited weight straight back — a skill
        # pruned on this screen was silently restored by the first click on
        # the next one, with the profile then scoring against it.
        #
        # Only the fields above reach it (reweighted, with_experience): a
        # posted SEARCH, SCORING or anything else the engine reads is never
        # read from a form.
        rec["derived"] = kept
        app.state["profile"] = name
        if rec is not app.state:
            rec["reviewed"] = True
            settle_tracks()
            # On to the next résumé in the search still to review, if any.
            from sweep import worker_link
            waiting = next((t for t in worker_link.selected(app.state)
                            if not track_ready(t)), None)
            if waiting is not None:
                # The review page: open on the next one read, or waiting
                # calmly for the one still being read (unified_review).
                return redirect(url_for("review"))
        return redirect(url_for(app.config.get("AFTER_REVIEW_ENDPOINT", "key")))

    @app.get("/profile")
    def profile_done():
        """Public mode's last step. The profile is handed over here rather
        than written into profiles/: that is a shared namespace on an
        ephemeral disk, so one visitor's name could replace another's."""
        source = app.state.get("profile_source")
        if not source:
            return redirect(url_for("upload"))
        return render_template("profile_done.html", **shell(
            "profile_done", name=app.state.get("profile"), source=source))

    @app.get("/profile.py")
    def profile_download():
        source = app.state.get("profile_source")
        if not source:
            return redirect(url_for("upload"))
        name = app.state.get("profile") or "profile"
        return Response(
            source, mimetype="text/x-python",
            headers={"Content-Disposition": f'attachment; filename="{name}.py"'})

    def key_screen(**kw):
        """Step 3, from all four ways it is reached. The paid boards are named
        in its copy AND are what the free choice switches off, so both come
        from paid_sites() rather than a list typed into the template."""
        return render_template("key.html", **shell(
            "key", paid=[site_label(s) for s in paid_sites()], **kw))

    # public.harden's plan-limit refusal lands on this screen (P4-S1C).
    app.key_screen = key_screen

    @app.get("/key")
    def key():
        # K2: a key just checked on this screen comes back to it once, to show what the check found (the newest
        # account's own figure) before the plan. Only while a key is held: an old ?checked link is the plain screen.
        keys = app.state.get("byok_keys") or []
        if app.config.get("PUBLIC_MODE") and request.args.get("checked") and keys:
            return key_screen(checked={"credit_usd": float(keys[-1]["headroom_usd"])})
        # T2: the plan's "Add another Apify key" opens the setup on its paste step.
        return key_screen(adding=bool(app.config.get("PUBLIC_MODE") and request.args.get("add")))

    def _apply_choice(free):
        """Record the free/paid choice and re-render the profile it implies.

        The paid toggles belong to this choice: taking the free path switches
        every metered site off, and coming back with a key restores config's
        own set rather than leaving a sweep silently all-off. Without the
        rewrite the choice would be state-only — /configure prices the
        profile FILE, so a free-only session would be quoted the paid plan it
        just declined.

        Returns an error string, or None. render() is the same validator the
        CLI path uses; nothing here is user input, so a failure is a bug
        rather than a bad field, but it must not reach the user as a 500 on
        the screen that was about to price a sweep.
        """
        if free:
            app.state["free_only"] = True
            app.state["sites_enabled"] = {s: False for s in paid_sites()}
        elif not app.state.pop("free_only", None):
            # A key pasted on the paid path switches nothing on or off, so
            # the profile on disk is already the one to price. Rewriting it
            # anyway would rebuild a profile from a session that may not
            # carry a derivation at all.
            return None
        else:
            # Undo the free path's own side effect, and only that: popping
            # unconditionally would discard a deliberate per-site choice
            # made later on Configure.
            app.state.pop("sites_enabled", None)
        # Free or paid is part of what a Multi-Track plan was made from.
        settle_tracks()
        if not app.state.get("profile") or (tracks_on() and not setup_ready()):
            # Nothing ready to render yet. Every screen that prices a Sweep is
            # behind the same readiness, and renders it from state first.
            return None
        try:
            write_sweep_profile(app.state)
        except KeyError as exc:
            return f"That profile could not be rewritten: {exc}"
        return None

    @app.post("/key/free")
    def key_free():
        """Skip Apify entirely and search only what costs nothing.

        No token is asked for, none is verified, and cap_usd stays None —
        there is no credit figure to be honest against, and a 0.0 cap would
        render as an account with nothing left on it.
        """
        # The derivation as well as the profile: this path rewrites the
        # profile from it, and a session that cannot be rewritten would be
        # quoted the paid plan it just declined. With the résumé setup on,
        # every selected résumé ready is the same fact.
        if tracks_on():
            if not setup_ready():
                return redirect(url_for("review"))
        elif not (app.state.get("profile") and app.state.get("derived")):
            return redirect(url_for("review"))
        error = _apply_choice(free=True)
        if error:
            return key_screen(error=error), 500
        return redirect(url_for("configure"))

    # Where adding a key may return to (V2-D1): the key step itself sends a
    # visitor on to Configure; Confirm's "Add another Apify key" comes back.
    KEY_ADD_RETURN = {"configure", "confirm"}

    def _account_digest(ident):
        """A visitor's Apify account, as this session knows it: a keyed
        digest of the provider's id — enough to see that two keys are one
        account, useless for naming it, and never shown."""
        secret = app.secret_key
        secret = secret.encode() if isinstance(secret, str) else secret
        return hmac.new(secret or b"", b"sweep-apify-account|" + str(ident).encode(),
                        hashlib.sha256).hexdigest()

    def _byok_totals():
        """cap_usd and credit_total_usd from the visitor's connected accounts:
        the best single one and all of them together, as the console's
        sweep_budget() reports its keys — display figures. Whether a plan
        fits is the allocator's question (plan.coverage), never this sum."""
        heads = [float(k["headroom_usd"]) for k in app.state.get("byok_keys") or ()]
        app.state["cap_usd"] = max(heads) if heads else None
        app.state["credit_total_usd"] = round(sum(heads), 4) if heads else None

    def _public_key(token, back):
        """POST /key in public mode: one more of the visitor's own accounts.

        The key funds their own sweep and nothing else. It is not written to
        .env, not put in os.environ, not kept on this session and not
        returned to the browser: it goes to the worker, which holds it in
        memory until their run starts, and this request forgets it. What
        stays here is its id at the worker, a keyed digest of its ACCOUNT
        (so a second key to the same account is refused rather than counted
        twice), and the figures the screens show — numbers, not credentials.
        """
        def refuse(message, status=400):
            if back == "confirm" and app.state.get("plan"):
                return _confirm_page(error=message, status=status)
            return key_screen(error=message), status

        account, error = read_account(token)
        if error:
            # Never render the token back into the page.
            return refuse(error)
        keys = list(app.state.get("byok_keys") or ())
        digest = _account_digest(account["id"])
        if any(k["account"] == digest for k in keys):
            return refuse("This key belongs to an Apify account already added.")
        if len(keys) >= MAX_PUBLIC_KEYS:
            return refuse(f"Sweep can use up to {MAX_PUBLIC_KEYS} Apify accounts "
                          f"for one search.")
        from sweep import worker_client
        try:
            key_id = worker_client.hold_token(token)
        except worker_client.WorkerError as exc:
            return refuse(f"That key is fine, but the sweep service could not "
                          f"take it just now: {exc}.", 502)
        del token
        entry = {"id": key_id, "account": digest,
                 "headroom_usd": str(account["headroom_usd"]),
                 "capacity_usd": str(scraper.usable_capacity(account["headroom_usd"]))}
        # A worker older than V2-D1 holds ONE key per visitor and names none:
        # the newest replaces the rest, as it always did there.
        app.state["byok_keys"] = keys + [entry] if key_id else [entry]
        _byok_totals()
        error = _apply_choice(free=False)
        if error:
            return key_screen(error=error), 500
        if back == "configure":
            # The key step itself (K2): back to it, to show the check, with the way on to the plan.
            return redirect(url_for("key", checked=1))
        return redirect(url_for(back))

    @app.post("/key")
    def key_post():
        token = (request.form.get("token") or "").strip()
        back = request.form.get("back") or "configure"
        if back not in KEY_ADD_RETURN:
            back = "configure"
        public_confirm = (app.config.get("PUBLIC_MODE") and back == "confirm"
                          and app.state.get("plan"))
        if not token:
            if public_confirm:
                return _confirm_page(error="Paste your Apify token.", status=400)
            return key_screen(error="Paste your Apify token."), 400
        if not _ENV_VALUE_RE.fullmatch(token):
            # Never echo the token back — say what's wrong, not what it was.
            message = ("That doesn't look like a token — remove any extra "
                       "characters and paste it again.")
            if public_confirm:
                return _confirm_page(error=message, status=400)
            return key_screen(error=message), 400

        if app.config.get("PUBLIC_MODE"):
            return _public_key(token, back)

        available, error = check_token(token)
        if error:
            # Never render the token back into the page.
            return key_screen(error=error), 400

        app.write_env("APIFY_TOKEN", token)
        os.environ["APIFY_TOKEN"] = token
        # Re-verified from the FILE rather than recorded from this one call:
        # .env may already hold other keys (an earlier session, or a hand
        # edit), and the credit figures have to describe what is configured
        # now, not what this request happened to paste.
        refresh_credits()
        error = _apply_choice(free=False)
        if error:
            return key_screen(error=error), 500
        return redirect(url_for("configure"))

    @app.post("/key/forget")
    def key_forget():
        """V2-D1, public only: stop using one of the visitor's accounts before
        the sweep starts. Dropped here and released at the worker; a run
        already started keeps the keys it was given, which the worker froze
        when it created the run. Idempotent, like the console's key_remove."""
        if not app.config.get("PUBLIC_MODE"):
            abort(404)
        key_id = request.form.get("key") or ""
        back = request.form.get("back") or "confirm"
        if back not in KEY_ADD_RETURN:
            back = "confirm"
        keys = app.state.get("byok_keys") or []
        if any(k["id"] == key_id for k in keys):
            from sweep import worker_client
            # A release the worker misses is harmless: a run names the keys
            # it may use (key_ids), and this one is no longer among them.
            with contextlib.suppress(worker_client.WorkerError):
                worker_client.release_token(key_id)
            app.state["byok_keys"] = [k for k in keys if k["id"] != key_id]
            _byok_totals()
        return redirect(url_for(back if app.state.get("cap_usd") is not None
                                else "key"))

    @app.errorhandler(PlanUnavailable)
    def plan_unavailable(exc):
        """One handler for every screen that prices a plan.

        Registered rather than caught per route so a route added later gets
        this instead of a bare 500 — /configure and /confirm both reached
        Flask uncaught before, and /run reads the plan they store.
        """
        return render_template("plan_error.html", **shell(
            None, profile=exc.profile)), 500

    def _configure_page(error=None, plan=None):
        """The preferences screen. Shared by GET and by a rejected POST, so a
        bad field comes back on the screen it was typed on rather than as a
        bare 400. `plan`: a refused Start (T2) shows the plan it was refused
        on rather than pricing again — a refusal costs the worker no dry run."""
        # State is authoritative; the profile file is derived from it. Doing
        # this before costing is what makes the price on this screen the
        # price of the sweep the screen is describing — an untouched visit
        # used to quote config.py's own LinkedIn geographies, and a candidate
        # priced through /estimate but never submitted used to linger.
        sync_profile()
        estimate = plan or costed(app.state["profile"])
        chosen = app.state.get("sites_enabled") or {}
        return render_template("configure.html", **shell(
            "configure", spend=estimate["total"], spend_is_estimate=True,
            estimate=estimate,
            # Unset means "inherit config.py's SITES", so the box has to show
            # what config actually says — read live, never hardcoded.
            # Rendering a state the profile does not have is how the first
            # change to any other field posts that lie back as an instruction.
            sites=[{"name": site,
                    # `name` stays the engine's key — it is the form field
                    # name POST /estimate and POST /run parse. `label` is the
                    # only thing a person reads.
                    "label": site_label(site),
                    "on": chosen.get(site, config.SITES[site].get("enabled", True)),
                    # A site bills per run when config.py pins its depth —
                    # the reason the depth control cannot move naukri.
                    "per_run": bool(config.SITES[site].get("results_per_run"))}
                   for site in paid_sites()],
            paid=[site_label(s) for s in paid_sites()],
            # Read live from config.LINKEDIN_GEO_IDS: a geoId verified (or
            # removed) there appears (or stops appearing) here, and the form
            # is validated against the same table.
            # EVERY group, each tagged with the scopes it belongs to. The
            # picker renders the menu itself so that changing the scope radio
            # changes the options with no round trip; one table drives that
            # and the server's own validation, so they cannot disagree.
            location_groups=location_groups(),
            # The no-JS text for the all-locations row and the empty picker.
            # Alpine re-computes it from the live scope; this is what the
            # server renders before it boots, and what a visitor without it
            # keeps.
            all_locations_label=("Anywhere in India"
                                 if current_scope() == "india" else "Everywhere"),
            # Only what the user picked — never the scope's own list, which
            # would render as an explicit choice they did not make and post
            # itself back as one.
            picked_locations=_picked_locations(),
            scope=current_scope(),
            # Every remaining control, rendered from what is actually stored
            # rather than from a placeholder or a hardcoded `selected`. Four
            # of them used to show a fixed state and then post it back as an
            # instruction, so coming back to this screen silently reset the
            # freshness window and erased the pay floor.
            max_age_days=app.state.get("max_age_days")
            or config.SETTINGS["max_age_days"],
            max_results=app.state.get("max_results")
            or config.SEARCH["max_results"],
            min_comp_usd=app.state.get("min_comp_usd"),
            avoid_terms=", ".join(app.state.get("avoid") or []),
            max_avoid_terms=MAX_AVOID_TERMS,
            advanced_custom=_advanced_is_custom(),
            error=error,
            # T2: the plan ticket carries Confirm's late-night warning (a Sweep past midnight re-bills).
            spans_midnight=_spans_midnight(),
            facts=search_facts()))

    @app.get("/configure")
    def configure():
        blocked = not_ready()
        if blocked:
            return blocked
        if not app.state.get("profile"):
            return redirect(url_for("review"))
        if needs_key():
            return redirect(url_for("key"))
        return _configure_page()

    def _picked_locations():
        """The cities/countries the user actually chose, for the picker.

        Never the scope's own expansion: rendering six city names the user
        did not pick would show as six explicit choices and post itself back
        as one. Under "Remote roles" this is always empty — the picker is not
        offered there, because a place cannot narrow "anywhere" and a city
        used to strip LinkedIn's remote filter.

        Filtered to what THIS scope offers, so a pick left over from a wider
        one cannot come back as a chip. It cannot normally be in state at all
        — the validator drops it on the way in — but the render must not be
        the thing that depends on that.
        """
        scope = current_scope()
        picked = app.state.get("locations")
        if scope == "remote" or not picked:
            return []
        if picked == _SCOPE[scope]["locations"]:
            return []
        offered = allowed_locations(scope)
        return [p for p in picked if p in offered]

    def _advanced_is_custom():
        """Whether anything behind the Advanced disclosure differs from its
        default. The badge used to read "using defaults" unconditionally."""
        return bool(
            (app.state.get("max_age_days") or config.SETTINGS["max_age_days"])
            != config.SETTINGS["max_age_days"]
            or (app.state.get("max_results") or config.SEARCH["max_results"])
            != config.SEARCH["max_results"]
            or app.state.get("min_comp_usd") is not None
            or app.state.get("avoid"))

    @app.post("/configure")
    def configure_post():
        """The preferences form's own submission — the authoritative one.

        The screen used to have no submit path at all: the form carried no
        method and no action, "Review and start" was a link, and the only
        thing that ever persisted a preference was the live-cost fetch()
        firing on a change event. With JavaScript unavailable every control
        was inert, and a last edit followed straight away by clicking through
        could be lost to the navigation aborting that request.
        """
        blocked = not_ready()
        if blocked:
            return blocked
        if not app.state.get("profile"):
            return redirect(url_for("review"))
        if needs_key():
            return redirect(url_for("key"))
        error = commit_prefs(request.form)
        if error:
            return _configure_page(error=error), 400
        if app.config.get("PUBLIC_MODE"):
            # T2: the plan screen starts the sweep itself (POST /run), so a save here is the ticket's "Add another Apify
            # key": the settings kept, then the key step, whose "Continue to your plan" comes back.
            if request.form.get("then") == "key":
                return redirect(url_for("key", add=1), code=303)
            return redirect(url_for("configure"), code=303)
        # 303, so the browser re-GETs rather than offering to re-POST the
        # form if the user then uses Back.
        return redirect(url_for("confirm"), code=303)

    @app.post("/estimate")
    def estimate():
        from flask import jsonify
        if not app.state.get("profile"):
            return jsonify({"error": "No profile yet — approve the review first."}), 409
        if needs_key():
            return jsonify({"error": "Connect your Apify key first."}), 409
        if tracks_on() and not setup_ready():
            return jsonify({"error": "Review every résumé in this search "
                                     "first."}), 409

        form = request.get_json(silent=True) or {}
        try:
            overrides = _configure_overrides(form, current_scope())
        except _FormError as exc:
            return jsonify({"error": str(exc)}), 400

        # PRICING ONLY. This route no longer commits anything to the session:
        # POST /configure does that, from the form the browser actually
        # submitted. What happens here is that a CANDIDATE profile is
        # rendered and priced — the local dry run reads the file, so the file
        # has to exist — and state is left alone. Every screen that reads the
        # profile re-renders it from state first (sync_profile), so a
        # candidate the user never submitted cannot become the sweep.
        #
        # A partial form only patches the keys it named. Built on a COPY, and
        # written only once make_profile.render() has succeeded — render() is
        # where an unverified LinkedIn geography or an unknown config key
        # gets caught, shared with the CLI path.
        #
        # The paid toggles are the free choice's to own while it stands.
        # Configure does not render them in free mode, so this is a forged or
        # stale form rather than a control the user saw — dropped quietly,
        # and /run refuses a priced plan regardless.
        if free_only():
            overrides.pop("sites_enabled", None)
        name = app.state["profile"]
        candidate = app.state.copy()
        if overrides:
            candidate.update(overrides)
            if not candidate.get("scope"):
                candidate["scope"] = DEFAULT_SCOPE
                candidate.update(_SCOPE[DEFAULT_SCOPE])

        # Priced AS the candidate, on a private copy of the session. Public
        # mode's plan comes from the worker, which is handed
        # _prefs(app.state) rather than the profile file, so pricing a
        # candidate means the candidate has to be what `app.state` says — but
        # only to THIS request. The session's own dict is never written, so a
        # second estimate or a Save running at the same moment cannot be
        # overwritten by this one finishing late (this route used to swap the
        # candidate into the live dict and restore a snapshot, which is
        # exactly that). The plan, cache and approval that costed() leaves in
        # state, and the profile render public mode keeps there, go with the
        # copy.
        #
        # The console's dry run reads a profile FILE, and the file is shared
        # by everything that runs the engine (the dry run, POST /run's child,
        # a re-rank). A candidate is therefore written to a scratch profile
        # of its own and discarded afterwards: two estimates cannot price one
        # another's candidate, and the saved profile is never a candidate.
        # Public mode keeps its profile in the session, which the copy above
        # already isolates.
        scratch = None
        if overrides and not app.config.get("PUBLIC_MODE"):
            scratch = f"{name[:60]}_est_{secrets.token_hex(6)}"
        with priced_as(app, candidate):
            try:
                if overrides:
                    try:
                        write_sweep_profile(candidate, scratch)
                    except KeyError as exc:
                        return jsonify({"error": str(exc)}), 400
                # The caller is a fetch() doing r.json(), so this cannot fall
                # through to the HTML handler below: an error page would fail
                # to parse and read as "the network is down" on the screen
                # whose whole job is a live cost.
                try:
                    return jsonify(costed(name, plan_profile=scratch))
                except PlanUnavailable:
                    return jsonify({"error": "The engine could not price that "
                                             "combination. Nothing was charged."}), 400
                except public.PlanLimited as exc:
                    # P4-S1C: the meter's own words, before any dry run started.
                    return jsonify({"error": str(exc)}), 429
            finally:
                if scratch:
                    app.discard_profile(scratch)

    @app.get("/confirm")
    def confirm():
        if app.config.get("PUBLIC_MODE"):
            # T2: one plan screen. Every way that used to land here (a key added, one removed, a stale Multi-Track
            # approval) lands on it instead, re-priced from the session as it stands.
            return redirect(url_for("configure"))
        # One selected résumé is planned as ever; two or three are planned by
        # the Multi-Track path (costed -> worker_link.plan_multi). Either way
        # only once every selected résumé is ready.
        blocked = not_ready()
        if blocked:
            return blocked
        if not app.state.get("profile"):
            return redirect(url_for("configure"))
        if needs_key():
            return redirect(url_for("key"))
        if not free_only():
            # Re-verified on arrival, like the plan beside it. Reading the
            # limits endpoint costs nothing, and this is the one screen where
            # a stale balance changes a decision — the figures here decide
            # whether the plan is affordable at all.
            refresh_credits()
        # Re-costed on every visit, like /configure — the meter shows this
        # screen's own state, never a figure carried over from an earlier one.
        # Re-rendered from state first, for the same reason /configure is: a
        # candidate that POST /estimate priced but the user never submitted
        # must not be what this screen quotes or what /run then launches.
        sync_profile()
        plan = costed(app.state["profile"])
        return render_template("confirm.html", **shell(
            "confirm", spend=plan["total"], spend_is_estimate=True, plan=plan,
            facts=search_facts(), spans_midnight=_spans_midnight()))

    @app.post("/run")
    def run():
        """Start a Sweep. Public mode counts it first (P4-S1B).

        One Sweep is one unit of SWEEP_DAILY_RUNS_* whatever it searches —
        one résumé or three, free or paid. It is reserved after the cheap
        checks and BEFORE anything is priced or sent to the worker, and it is
        given back unless the worker actually created a run: a plan that
        failed, a worker that did not answer or had no room, a form that did
        not validate all cost nothing. A run the worker accepted stays
        counted, however it later ends.
        """
        blocked = not_ready()
        if blocked:
            return blocked
        if not app.config.get("PUBLIC_MODE"):
            return start_run()
        if _sweep_in_flight():
            # A second click, or a refresh: the existing run wins (as the
            # check inside start_run says), and it costs nothing.
            return redirect(url_for("running"))
        try:
            ticket = app.run_limit.reserve(public.client_ip())
        except public.BetaLimited as exc:
            # Refused before any planning: the plan already on state is the
            # one this screen shows, and nothing is priced to say so.
            public.audit("run", outcome="refused")
            if app.state.get("plan"):
                return _confirm_page(error=str(exc), status=429)
            return key_screen(error=str(exc)), 429
        public.audit("run", outcome="admitted")
        g.run_created, g.run_error = None, None
        try:
            return start_run()
        except Exception as exc:
            g.run_error = public.failure_category(exc)
            raise
        finally:
            if g.run_created is None:
                app.run_limit.release(ticket)
                public.audit("run", outcome="not_started", category=g.run_error)
            else:
                public.audit("run", outcome="accepted", run=g.run_created)

    def start_run():
        # The free public path has no /confirm screen: its Start button IS
        # the preferences form's submit, so this is where that form lands and
        # this is where it has to be applied — before anything is priced or
        # launched. A POST from /confirm carries only over_cap_ack, so
        # _configure_overrides sees no recognised field and this is a no-op
        # there.
        from sweep import worker_link
        if app.state.get("profile") and app.state.get("derived"):
            error = commit_prefs(request.form)
            if error:
                if app.config.get("PUBLIC_MODE") and free_only():
                    return _configure_page(error=error), 400
                return _confirm_page(error=error, status=400)
            # Re-priced against what was just committed. The guards below
            # read app.state["plan"], and quoting the previous form's plan is
            # exactly the kind of drift this screen exists to prevent. Fresh:
            # never the screens' short-lived cache (P4-S1C).
            costed(app.state["profile"], fresh=True)
        elif app.state.get("profile") and worker_link.multi_active(app.state):
            # A Multi-Track Sweep runs only a plan made from exactly what the session holds. On the console that is
            # Confirm's: a form that carries preferences outdates it and is refused below, back to Confirm, with nothing
            # started. Publicly (T2) the plan screen's Start carries the preferences, so a form that moved them is planned
            # again here, fresh, and then held to the price the screen showed (below); one that moved nothing runs the
            # plan the screen was priced with.
            error = commit_prefs(request.form)
            if error:
                return _confirm_page(error=error, status=400)
            planned = app.state.get(worker_link.PLANNED)
            if app.config.get("PUBLIC_MODE") and (
                    not planned or "run_id" in planned
                    or planned["snapshot"]["inputs"] != worker_link.inputs(app.state)):
                costed(app.state["profile"], fresh=True)
        elif app.config.get("PUBLIC_MODE") and app.state.get("plan"):
            # P4-S1C: a plan with no résumé behind it — what a Render restart
            # leaves when the cookie brought a finished run back (rehydrate)
            # but the résumé, its derivation and its priced plan were memory.
            # There is nothing to search for, so nothing is started and
            # nothing is made up: the visitor begins again from the résumé.
            return upload_screen(
                error="Your résumé is no longer here — Sweep keeps it for a "
                      "short while only. Upload it again to start a new "
                      "search."), 409
        # Fail closed: no plan at all (a /run hit that never went through
        # /confirm) must refuse exactly like an over-cap plan does, not
        # launch an uncapped subprocess because an empty dict's .get()
        # reads as falsy the same as a real "under cap" plan would.
        plan_now = app.state.get("plan")
        if not plan_now:
            return "No plan to run — start from Configure.", 400
        if needs_key():
            return "No key connected — connect one before running.", 400
        quoted = request.form.get("quoted_total")
        if app.config.get("PUBLIC_MODE") and not free_only() and quoted is not None:
            # T2: the plan screen's Start carries the price its ticket showed (quoted_total), and the Sweep is held to it:
            # priced again just above from the same settings, and if that came out higher (credit, a busy moment, an answer
            # that had not landed yet) nothing starts and the screen shows the new figure. Lower is fine. A quote that is
            # not a finite number is refused the same way. A form without one is not from that screen (a page from before
            # it): it showed its own price, so it is let through to the guards below as it always was.
            try:
                quoted = float(quoted)
            except ValueError:
                quoted = math.nan
            if not math.isfinite(quoted) or plan_now["total"] > quoted + 0.005:
                return _confirm_page(
                    error=(f"The price is now ${plan_now['total']:.2f}"
                           + (f", not the ${quoted:.2f} this page showed" if math.isfinite(quoted) else "")
                           + ". Nothing has started. Check the ticket and start again."),
                    status=409)
        # The free path's real guard. free_only() opened /configure, /confirm
        # and this route without a verified key, so this is where that choice
        # is checked against what the plan actually says: a priced plan means
        # a paid actor is about to run on whatever APIFY_TOKEN happens to be
        # in .env, for someone who asked to spend nothing.
        if free_only() and plan_now.get("total"):
            return _confirm_page(
                error="This sweep is set to free sources only, but the plan "
                      "now prices paid searches. Connect a key, or switch "
                      "the paid boards back off.", status=400)
        if plan_now.get("paid_unavailable"):
            # V2-D closeout: the worker's engine cannot safely authorise a
            # visitor's paid sweep right now (switched off, or older than
            # this). Refused — never started on an estimate instead.
            return _confirm_page(
                error="Paid searches are temporarily unavailable. Nothing has been "
                      "charged. You can search the free sources now, or come back "
                      "later.", status=503)
        if (plan_now.get("coverage") is not None
                and not plan_now["coverage"].get("funding_ids")):
            # No account connected any more — the keys were spent on the last
            # run, or removed. The worker's own answer, without asking it.
            from sweep import worker_client
            raise worker_client.NeedsKey("no Apify key is connected")
        if (plan_now.get("over_cap") and plan_now.get("coverage")
                and not request.form.get("over_cap_ack")):
            # V2-D1: the connected accounts cannot safely hold the whole
            # plan. A full sweep never quietly becomes a smaller one: nothing
            # starts until the visitor adds a key or chooses the part their
            # credit covers, with the same box the console has always used.
            return _confirm_page(
                error="Your connected Apify accounts can't safely cover the "
                      "full Sweep. Add another Apify key, or choose \"Run what "
                      "fits\" to start the part they can cover.", status=400)
        if plan_now.get("over_cap") and not request.form.get("over_cap_ack"):
            # No longer a refusal: it is the user's account and the sweep is
            # recoverable — the engine stops when the account is spent, and
            # .done_combos means the finished searches are not re-billed when
            # it resumes on another key. What is NOT acceptable is starting
            # one by mis-click, so the over-cap button carries its own
            # acknowledgement and this fails closed without it.
            return _confirm_page(
                error="This plan costs more than one key can fund. Tick the "
                      "box to start it anyway, or narrow the search first.",
                status=400)

        # Stamp the real cap into the profile BEFORE the child starts.
        # SETTINGS["max_spend_usd"] is the only guard that can actually stop
        # an overspend — scraper.py:1748 re-reads the account after every
        # search — and make_profile.render() omitting the key means "inherit
        # config.py's None", i.e. no cap at all. So this is what makes the
        # README's "a wrong estimate cannot cause an overspend" true.
        # Written through render(), never an f-string: it is also what
        # validates every key against the live config.
        # Checked and set under one lock, the same shape /rescore uses. The
        # dev server is threaded, this route makes a live Apify call before it
        # redirects, and /second-key sends the user back to /confirm with a
        # live Run button while the first sweep is still going — so a second
        # launch is a double-click or a documented gesture away, and it spends
        # real money. The profile rewrite is inside too: a request refused
        # with 409 should leave no trace, and it must still land before the
        # child starts.
        with _run_lock:
            if _sweep_in_flight():
                # The existing run wins. It is the one the worker is
                # actually executing and the one whose rows exist, and
                # replacing it would orphan a sweep this process can no
                # longer stop — POST /stop signals the child it can see.
                #
                # Publicly that refusal cannot be the confirm screen: the
                # free path never visits /confirm, so a second click on
                # "Start Free Sweep" would land on a page the visitor has
                # never seen, explaining a state the strip already shows.
                # Send them to their sweep instead.
                if app.config.get("PUBLIC_MODE"):
                    return redirect(url_for("running"))
                return _confirm_page(
                    error="A sweep is already running. Watch it on the "
                          "running screen, or stop it before starting "
                          "another.", status=409)
            app.state["max_spend_usd"] = plan_now["spend_cap"]
            # V2-D1: the ONE place a partial paid sweep is authorised — the
            # ticked box on an over-cap plan, written into the profile the
            # engine reads (SETTINGS["allow_partial_paid_sweep"]). Reset on
            # every run, so an earlier yes never carries into a later sweep;
            # unset means config's False: the whole plan or none of it.
            app.state["allow_partial_paid_sweep"] = (
                True if plan_now.get("over_cap") and request.form.get("over_cap_ack")
                else None)
            # Which of a visitor's held keys fund this run: exactly the ones
            # Confirm placed the plan on (every account, or the one "single"
            # mode uses). Never chosen here by any other rule.
            cov = plan_now.get("coverage") or {}
            app.state["run_key_ids"] = [k for k in cov.get("funding_ids") or () if k] or None
            from sweep import worker_link
            if not worker_link.multi_active(app.state):
                # A Multi-Track Sweep runs its planned snapshot, rendered on
                # the worker; there is no one-résumé profile to write.
                app.write_profile(app.state["profile"], make_profile.render(
                    app.state["profile"], app.state["derived"], _prefs(app.state)))
            # baseline_usd may be None (see read_spend's docstring) —
            # recorded as-is, never coerced to 0.0, so the meter can tell
            # "unknown" from "no spend yet".
            #
            # Not read at all on the free path: no paid actor will run, so
            # spend_delta() answers a known 0.0 without a baseline, and this
            # would be a live Apify call whose only possible answer — a
            # month-to-date total from a token this sweep never uses — is a
            # figure nothing here may attribute to it.
            app.state["baseline_usd"] = None if free_only() else read_spend()
            # Both the elapsed clock and the live feed hang off this: the
            # feed ignores any output file untouched since before it, which
            # is what stops the previous sweep's rows opening the feed.
            app.state["run_started_at"] = wall_now()
            # Both belong to the run that just ended. Carried into this one,
            # a resumed sweep that later dies on its own would report "you
            # stopped it", and the credit reading behind "out of credit"
            # would be the one taken before this sweep spent anything.
            app.state.pop("stopped_by_user", None)
            app.state.pop("interrupt_credit_read", None)
            app.state["proc"] = start_sweep(app.state["profile"])
            # The worker created it: from here the Sweep is counted (P4-S1B).
            g.run_created = getattr(app.state["proc"], "run_id", None) or "local"
            # V2-D1: the worker spent every held key on this run (they are
            # used once), so the accounts listed here are gone too — kept, a
            # re-pasted key would be refused as "already added" to nothing.
            if app.config.get("PUBLIC_MODE"):
                app.state.pop("byok_keys", None)
                app.state.pop("run_key_ids", None)
            # The console's own crash-recovery note, for a child on THIS
            # machine. A public run is recorded on the worker instead, and
            # writing it here would put one visitor's state on a shared
            # disk under a profile name another visitor can pick too.
            if not app.config.get("PUBLIC_MODE"):
                _write_run_json(app.state, output_dir)
        return redirect(url_for("running"))

    # Where a removal may return to. An endpoint name off a form field
    # reaches url_for, so it is checked against a list rather than trusted —
    # and Referer is not usable for this, being both absent and forgeable.
    KEY_RETURN = {"confirm", "running"}

    @app.post("/key/remove")
    def key_remove():
        """Detach one key. It stops funding sweeps and stops being counted.

        Removed from the FILE and from os.environ together: the engine
        inherits this process's environment, so a key dropped from only one
        of the two would go on paying for searches the user thought they had
        detached.
        """
        name = (request.form.get("name") or "").strip()
        back = request.form.get("back") or "confirm"
        if back not in KEY_RETURN:
            back = "confirm"
        on_file = read_env_tokens_as_env()
        if name not in on_file:
            # Already gone — a double submit, or a hand edit in between.
            # Not an error: the state the user asked for is the state.
            return redirect(url_for(back))
        # A sweep in flight is holding a client built from one of these, and
        # which one is the engine's business, not this screen's.
        if _sweep_in_flight():
            return _key_error(back, "A sweep is running. Stop it before "
                                    "detaching a key.")
        app.remove_env(name)
        # One call does the rest, and both halves matter: read_env_tokens()
        # inside it drops every APIFY_TOKEN* that is no longer in the file
        # from os.environ — which is what stops the engine, that inherits
        # this environment, spending from an account the user detached — and
        # it rebuilds key_credit keyed only on what the file holds, so the
        # removed key's last known balance goes with it.
        #
        # Popping either by hand here first was dead code, and a mutation
        # said so: both lines could be deleted with nothing failing.
        refresh_credits()
        return redirect(url_for(back))

    def _key_error(back, message):
        """The refusal, on the screen it came from."""
        if back == "running":
            app.state["key_notice"] = message
            return redirect(url_for("running"))
        return _confirm_page(error=message, status=409)

    @app.post("/second-key")
    def second_key():
        token = (request.form.get("token") or "").strip()
        # No plan at all (a /second-key hit that never went through
        # /confirm) can't be rendered back into confirm.html — plan.lines
        # etc. would be undefined — so this fails the same simple way /run
        # does for the same precondition, rather than a 500 on a missing key.
        plan_now = app.state.get("plan")
        if not plan_now:
            return "No plan to attach a key to — start from Configure.", 400

        # Read from .env on disk, not from this process's environment: a key
        # deleted from the file by hand is still in os.environ for the life of
        # the server, and this check was rejecting keys that had just been
        # removed.
        #
        # The check itself stays because re-pasting a key that IS on file adds
        # no credit while looking like it did — but the figures no longer
        # depend on it being right, since refresh_credits() re-reads every key
        # rather than adding this one's balance to a running total.
        if token and token in {tok for _, tok in read_env_tokens()}:
            return _confirm_page(error="That's the same key already on file — it adds no "
                      "new credit.", status=400)

        if not token:
            return _confirm_page(error="Paste your Apify token.", status=400)
        if not _ENV_VALUE_RE.fullmatch(token):
            return _confirm_page(
                error="That doesn't look like an Apify token — printable "
                      "characters, no spaces.", status=400)
        available, error = check_token(token)
        if error:
            return _confirm_page(error=error, status=400)
        if available <= 0:
            return _confirm_page(error="That key verified, but it has no credit "
                      "available.", status=400)

        slot = next_token_name(read_env_tokens_as_env())
        app.write_env(slot, token)
        os.environ[slot] = token
        # Every key re-verified, not this one's balance added to a total. The
        # cap is still max-not-sum (see sweep_budget): another key lifts what
        # ONE sweep can spend only if that key alone covers the plan.
        refresh_credits()
        # over_cap is not patched here — GET /confirm re-costs the whole
        # plan via costed() on the redirect below, so any value written
        # here would be discarded before ever being read.
        return redirect(url_for("confirm"))

    @app.get("/running")
    def running():
        from sweep import worker_link
        if app.state.get(worker_link.REPLAN):
            # A Multi-Track Sweep whose plan went stale: plan it again.
            return redirect(url_for("confirm"))
        if not app.state.get("raw_plan"):
            return redirect(url_for("configure"))
        progress_now = snapshot()
        return render_template("running.html", **shell(
            "running", spend=progress_now["spend"],
            spend_is_this_sweep=progress_now["baseline_known"],
            progress=progress_now, plan=app.state["plan"]))

    @app.get("/activity")
    def activity():
        """What Sweep is doing for this browser, as the strip says it.

        ONE endpoint for the one component, so the résumé half and the sweep
        half cannot drift into two poll loops with two opinions. It answers
        the same function the page was rendered from, so a poll can only ever
        replace the strip with a newer version of itself.

        No run and no parse is `{"banner": null}` and a 200: "nothing is
        happening" is an answer, not an error, and the script hides the strip
        on it.
        """
        from flask import jsonify
        return jsonify({"banner": owned_activity(
            request.args.get("on") or "", live=True)})

    @app.get("/progress")
    def progress():
        from flask import jsonify
        # Reachable without going through /run, same as /running — a
        # bookmark, a stale tab after a reset, curl during manual testing.
        # snapshot() reaches state["raw_plan"]/["profile"] by bracket
        # access, so this must not fall through to it on empty state.
        if not app.state.get("raw_plan"):
            return jsonify({"error": "No sweep running."}), 409
        return jsonify(snapshot())

    @app.get("/events")
    def events():
        import json
        import time
        from flask import Response

        # Same guard as /progress. A 302 here is what /running redirects
        # with, but EventSource treats a redirect response as HTML to load,
        # not a stream to read — so this closes the connection with a plain
        # error status instead of redirecting into it.
        if not app.state.get("raw_plan"):
            return Response('{"error": "No sweep running."}', status=409,
                            mimetype="application/json")

        def stream():
            while True:
                p = snapshot()
                yield f"data: {json.dumps(p)}\n\n"
                if p["finished"] or p["interrupted"]:
                    return
                time.sleep(2)

        return Response(stream(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache"})

    @app.post("/stop")
    def stop():
        from sweep import runs as runs_mod
        proc = app.state.get("proc")
        if proc is not None:
            runs_mod.stop(proc)
        # Recorded, not inferred. A stopped sweep and one that ran out of
        # credit both end as a dead child with searches left, and the screen
        # used to report the same "stopped early" for either — so the one
        # case the user caused looked like the one that costs them money.
        app.state["stopped_by_user"] = True
        return redirect(url_for("running"))

    def _shortlist_args():
        """The filter and the sort in the query string, validated.

        Read in one place because two screens now depend on them agreeing:
        a file offered as "Export CSV (128)" has to hold the same 128 rows
        the page is showing, and it is reached by a separate request that
        carries the filters along in its own query string.
        """
        sort = request.args.get("sort") or DEFAULT_SORT
        return (request.args.get("min", type=int) or 0,
                request.args.get("source") or "",
                (request.args.get("q") or "").strip(),
                # Validated against the table rather than trusted: it
                # arrives in a query string and picks a sort key by name.
                sort if sort in SORTS else DEFAULT_SORT)

    def _results_page(error=None, notice=None):
        """Shared by GET /results and a failed POST /rescore, so an
        out-of-range hours value re-renders the same screen with an error
        instead of a bare 400."""
        # A finished sweep is exactly when the balances have moved, and this
        # is the screen the running screen sends you to. Re-read once here
        # rather than on every SSE tick, which would be N live calls every
        # two seconds for forty minutes.
        if not free_only() and app.state.get("credit_total_usd") is not None:
            refresh_credits()
        profile = app.state["profile"]
        all_rows = rows_with_applied(profile)
        sweeps = list_sweeps(profile)
        # A single sweep's file is complete for that sweep but does not span
        # earlier ones, and merge_jobs.py is what combines them.
        merged = bool(all_rows) and all_rows[0].get("_merged") == "1"

        min_score, source, q, sort = _shortlist_args()
        view = results_view(all_rows)
        export_total = None
        if view:
            # No floor unless one is asked for: every one of these rows is one
            # the engine kept, a negative score included.
            min_score = request.args.get("min", type=int)
            # The export is All Jobs whichever view is open (P4-E1), so its
            # label counts what ITS file holds, filtered as it will be.
            export_total = len(shortlist(all_rows, min_score, source, q, sort))
            all_rows = view["rows"]

        rows = shortlist(all_rows, min_score, source, q, sort)

        # One option per PLATFORM, not per company board: the free adapters
        # write `platform:company`, so this used to offer "greenhouse:stripe"
        # and "greenhouse:sumup" as separate, differently-named sources. The
        # filter matches on the same prefix (logic.shortlist).
        sources = sorted({(r.get("source_site") or "").split(":")[0]
                          for r in all_rows if r.get("source_site")})

        return render_template("results.html", **shell(
            # What this sweep actually cost, or None when no run recorded a
            # baseline to subtract from. Never the estimate.
            "results", spend=spend_delta(),
            buckets=bucket_rows(rows), sections=SECTIONS,
            total=len(rows), all_total=len(all_rows),
            min_score=min_score, source=source, q=q, sources=sources,
            sort=sort, sorts=SORTS,
            # Same rule plan.cost() and snapshot() use — a site listed at a
            # $0.00 rate is free either way, never a second "is this site
            # free" rule that could disagree with them.
            rates=config.SITE_RATES, merged=merged,
            # Each section shows its best N until asked for the rest: a real
            # sweep is 1600 rows, and three sections of everything is a page
            # nobody reaches the bottom of.
            section_cap=SECTION_CAP,
            full=bool(request.args.get("full")),
            posted_age=posted_age,
            # Only consumed when nothing survived the filters, and it makes
            # one pass over every unfiltered row per active filter — three
            # passes over up to 1607 rows, thrown away, on every page load.
            worst=(worst_filter(all_rows, min_score, source, q)
                   if not rows else None),
            rescoring=_rescore_in_flight(), merging=_merge_in_flight(),
            # The offer to merge, and the honest count behind it: [0] is the
            # sweep on display, so anything after it is what folding in would
            # add. The old copy told the user to run merge_jobs.py whenever
            # this screen was showing an unmerged file — including when there
            # was only one sweep and nothing to fold in.
            earlier=max(0, len(sweeps) - 1),
            earlier_dates=sweep_dates(sweeps[1:]),
            # The re-rank panel edits these in place, so it needs the same
            # list the review screen wrote — not the profile file, which it
            # cannot read back into weights.
            derived=app.state.get("derived"), profile=profile,
            notice=notice, error=error,
            export_total=len(rows) if export_total is None else export_total,
            # The minimum every link carries on: today's default 0 is no
            # parameter at all; a Multi-Track minimum only when one was set,
            # an explicit 0 included.
            min_arg=min_score if view else (min_score or None),
            ending=ending_of_this_run(),
            views=view and view["views"], view_track=view and view["track"],
            view_label=view and view["label"], view_file=view and view["file"],
            # A column nobody in this list fills is not drawn (the facts are
            # still in every row's data and in the exports).
            # A run that made no recommendation has no suggestion to head a column
            # or caption with; a run with nothing at all has no tabs or tools to draw.
            has_recs=any(r.get("_pieces") for r in rows),
            run_empty=(not (min_score or source or q)
                       and (view["views"][0]["count"] == 0 if view else not all_rows)),
            show_pay=any((r.get("salary") or "").strip() for r in rows),
            show_exp=any((r.get("experience_required") or "").strip() for r in rows)))

    def run_labels():
        """(track ids, {id: label}) of this browser's Multi-Track run, in run
        order, or None: the product off, or a one-track run. The RUN's ids —
        its cookie's, which its status has just been checked against — never
        the setup's. One answer for Results and the exports.

        Each résumé is called by the file it was uploaded as, found by id in
        this browser's own setup: a title read off it would only guess at the
        role the visitor is after, and a file name is never put in the cookie.
        A run whose setup is gone (a restart, a removed résumé) says "Résumé
        n"; a name two of them share says "Résumé n · name". Past 40
        characters, a name is shortened."""
        pairs = public.run_track_labels()
        if not tracks_on() or not pairs:
            return None
        files = {t["id"]: os.path.basename(t.get("resume_name") or "").strip()
                 for t in app.state.get("tracks") or ()}
        names = [files.get(tid, "") for tid, _label in pairs]
        folded = [name.casefold() for name in names]
        labels = {}
        for n, ((tid, _label), name) in enumerate(zip(pairs, names), 1):
            if name and folded.count(name.casefold()) > 1:
                name = f"Résumé {n} · {name}"
            short = name if len(name) <= 40 else name[:39] + "…"
            labels[tid] = public.run_label(short, n)
        return [tid for tid, _label in pairs], labels

    def run_identities():
        """What the Results screen calls each résumé of this browser's
        Multi-Track run: (track ids, {id: label}, {id: file name}), or None
        like run_labels().

        The LABEL is the résumé's editable name (design decision 4): the
        setup's current one for the same id, so a rename after the run started
        is followed; else the one the cookie froze when the run began; else
        "Résumé n" in run order. The FILE it was uploaded as is the secondary
        line, "" once the setup is gone. Ids still decide everything; two
        labels that read alike are told apart by their place in the run.

        Only the screen. The exports keep run_labels() (their label cells are
        unchanged by this phase); the two are one line apart if the owner wants
        them to agree."""
        pairs = public.run_track_labels()
        if not tracks_on() or not pairs:
            return None
        setup = {t["id"]: t for t in app.state.get("tracks") or ()}
        labels, files = {}, {}
        for n, (tid, frozen) in enumerate(pairs, 1):
            track = setup.get(tid) or {}
            labels[tid] = public.run_label(track.get("name") or frozen, n)
            files[tid] = os.path.basename(track.get("resume_name") or "").strip()
        folded = [label.casefold() for label in labels.values()]
        for n, tid in enumerate(list(labels), 1):
            if folded.count(labels[tid].casefold()) > 1:
                labels[tid] = f"{labels[tid][:40 - len(f' · {n}')]} · {n}"
        return [tid for tid, _label in pairs], labels, files

    def results_view(rows):
        """A Multi-Track run's Results (P4-R2; design §P.1), or None: the
        product off, or a one-track run — whose Results are today's, untouched.

        The views are the RUN's tracks — the ids its cookie names and its
        status has just been checked against (worker_link._checked) — never
        the setup as it stands now: a résumé added, left out or removed since
        changes no view. Labels are presentation only: the setup's current
        name for the same id (a rename after the run started), else the
        cookie's, else "Résumé n" in run order.

        `rows` are read_rows' strictly checked rows, each read again only
        through worker_link.multi_row; nothing here judges, scores or
        recommends. All Jobs is every row, in the engine's order. A résumé's
        view is the rows its track has an evaluation for (track_evals, never
        best_track or found_by), each with that track's own score and matched
        skills, ranked by that score; the recommendation stays the job's.
        ?track= names a view only as one of this run's ids; else All Jobs.
        """
        from sweep import worker_link
        run = run_identities()
        if run is None:
            return None
        ids, labels, files = run
        chosen = request.args.get("track")
        chosen = chosen if chosen in ids else None
        counts, shown = dict.fromkeys(ids, 0), []
        for row in rows:
            typed = worker_link.multi_row(row, ids)
            evals = typed["track_evals"]
            for tid in evals:
                counts[tid] += 1
            # The same sentences twice: as text (what the row's tests and the
            # exports read) and in pieces (what the screen draws).
            words = recommendation_words(typed, labels)
            pieces = recommendation_pieces(typed, labels)
            if chosen is None:
                shown.append(dict(row, _words=words, _pieces=pieces,
                                  _for=labels[typed["best_track"]]))
            elif chosen in evals:
                shown.append(dict(row, score=evals[chosen]["s"],
                                  matched_skills=evals[chosen]["m"],
                                  _words=words, _pieces=pieces, _for=labels[chosen]))
        views = [{"id": None, "label": "All Jobs", "file": "", "count": len(rows),
                  "current": chosen is None}]
        views += [{"id": tid, "label": labels[tid], "file": files[tid],
                   "count": counts[tid], "current": tid == chosen} for tid in ids]
        return {"rows": shown, "views": views, "track": chosen,
                "label": labels.get(chosen), "file": files.get(chosen, "")}

    # Wall-clock hour, injectable so the midnight re-bill warning is
    # testable. Separate from `now`, which is a monotonic clock for the
    # spend-poll throttle and says nothing about the time of day.
    if hour_now is None:
        def hour_now():
            return datetime.now().hour

    def _spans_midnight():
        """A sweep started this late will still be running after midnight,
        and .done_combos is scoped to a single day — so every search it had
        already finished gets re-run and re-billed."""
        return hour_now() >= 22

    def _confirm_page(error=None, status=200):
        """confirm.html with the live plan. Four routes rendered this inline
        with spans_midnight hardcoded False, so any error after 22:00 threw
        away the one warning that prevents a real double bill."""
        if app.config.get("PUBLIC_MODE"):
            # T2: a refused Start comes back to the screen it was pressed on, with the reason above the settings, showing
            # the plan it was refused on (priced moments ago, or the screen's own): nothing is priced to say so.
            return _configure_page(error=error, plan=app.state.get("plan")), status
        plan_now = app.state.get("plan")
        return render_template("confirm.html", **shell(
            "confirm", spend=plan_now["total"], spend_is_estimate=True,
            plan=plan_now, facts=search_facts(),
            spans_midnight=_spans_midnight(), error=error)), status

    _run_lock = threading.Lock()
    # Held only across the check-and-mark, never across the model call: two
    # concurrent requests must not both decide to spend, but one visitor's
    # parse must not block anybody else's.
    _parse_lock = threading.Lock()
    # add_track's check-and-add: a résumé setup never holds a fourth.
    _tracks_lock = threading.Lock()
    _rescore_lock = threading.Lock()
    _merge_lock = threading.Lock()

    def _sweep_in_flight():
        """Whether a sweep child is still running.

        Two sweeps on one profile append to the same .done_combos and
        truncate the same jobs_*.json, so the second re-bills searches the
        first already paid for and the output interleaves. Worse,
        app.state["proc"] holds one child, so a second launch orphans the
        first: POST /stop can only signal the one it can see.
        """
        proc = app.state.get("proc")
        return proc is not None and proc.poll() is None

    # ponytail: in-memory and single-process, like the re-score flag. run.json
    # carries no pid, so restarting the server mid-sweep reports idle and the
    # next POST /run launches a second paid child over a live one — the
    # original defect, through a narrower door. Persist the pid alongside
    # run.json if the server is ever restarted mid-sweep in practice.

    def _results_url():
        """/results carrying whatever filters the request arrived with, so a
        redirect does not silently clear them. The error paths were fixed for
        this and the success path was left bare, which is the same
        one-instance-only fix this branch keeps making."""
        chosen = request.args.get("sort")
        return url_for("results",
                       min=request.args.get("min", type=int) or None,
                       source=request.args.get("source") or None,
                       q=(request.args.get("q") or "").strip() or None,
                       # The order is a filter as far as a redirect is
                       # concerned: coming back from a re-rank into a
                       # different order is the same surprise as coming back
                       # with the filters cleared.
                       sort=(chosen if chosen in SORTS
                             and chosen != DEFAULT_SORT else None))

    def _rescore_in_flight():
        """Whether a re-score child is still running.

        rescore_from_apify.py truncates jobs_combined.csv and .json in place
        with no lock of its own, so two overlapping children interleave writes
        to the same two files.

        ponytail: in-memory and single-process. Restarting the server while a
        child runs loses this and orphans it, and there is no way to cancel a
        running re-score from the UI — POST /stop signals app.state["proc"]
        only. Both are acceptable for one local user driving one button by
        hand; persist it alongside run.json if a second entry point ever
        starts a re-score.
        """
        proc = app.state.get("rescore_proc")
        return proc is not None and proc.poll() is None

    def _merge_in_flight():
        """Whether a merge child is still running.

        merge_jobs.py truncates jobs_combined.csv and .json in place, the same
        two files a re-score writes, so two children — of either kind —
        interleave writes to them. Same ponytail caveat as
        _rescore_in_flight(): in-memory, single-process, lost on a restart.
        """
        proc = app.state.get("merge_proc")
        return proc is not None and proc.poll() is None

    def _rewriter_busy():
        """Which child is rewriting the shortlist, or None.

        merge_jobs.py and rescore_from_apify.py write the same two files
        (jobs_combined.csv/.json), so neither may start while either runs —
        and the refusal has to name the one that is actually running rather
        than guess.
        """
        if _merge_in_flight():
            return "merge"
        return "re-score" if _rescore_in_flight() else None

    @app.post("/merge")
    def merge():
        """Fold this profile's earlier sweeps into one shortlist.

        Free and local — no key, no account, no actor — so this is offered on
        the free path too.
        """
        if not app.state.get("profile"):
            return redirect(url_for("upload"))
        with _merge_lock:
            busy = _rewriter_busy()
            if busy:
                return _results_page(
                    notice=f"A {busy} is already running. Reload in a moment "
                           "to see the new shortlist."), 409
            app.state["merge_proc"] = start_merge(app.state["profile"])
        return redirect(_results_url())

    @app.post("/applied")
    def applied():
        """Tick or untick one listing. Answers 204, never a page.

        Posted by the checkbox itself so a tick does not reload the results
        screen — which would lose the scroll position on a 1,600-row page,
        and with it the row the user was looking at when they ticked it.

        The key arrives from the browser, so it is checked against the keys
        THIS profile's shortlist actually contains rather than written
        straight to the ledger: the ledger outlives the output files, and a
        junk key in it would never be cleaned up by anything.
        """
        if not app.state.get("profile"):
            return redirect(url_for("upload"))
        key = (request.form.get("key") or "").strip()
        on = request.form.get("on") == "1"
        known = {row["_key"]: row
                 for row in rows_with_applied(app.state["profile"])
                 if row.get("_key")}
        if key not in known:
            # Not an error the user can act on — it means the shortlist was
            # rewritten under them (a merge, a re-score) since the page
            # loaded. Say so plainly rather than writing a key nothing owns.
            return {"error": "That listing is no longer in this shortlist — "
                             "reload the results screen."}, 409
        row = known[key]
        set_applied(_applied_file(), key, on,
                    row.get("title", ""), row.get("company", ""))
        return "", 204

    @app.get("/results")
    def results():
        from sweep import worker_link
        if app.state.get(worker_link.REPLAN):
            return redirect(url_for("confirm"))
        if not app.state.get("profile"):
            return redirect(url_for("upload"))
        return _results_page()

    # (mimetype, builder) by extension. The extension in the path IS the
    # format, so an unknown one is a 404 — a file that is not what its name
    # says is worse than no file at all.
    EXPORTS = {
        "csv": ("text/csv; charset=utf-8", exports.as_csv),
        "json": ("application/json; charset=utf-8", exports.as_json),
        "xlsx": ("application/vnd.openxmlformats-officedocument"
                 ".spreadsheetml.sheet", exports.as_xlsx),
        # The shortlist to read rather than to process: one self-contained
        # page, styled, grouped as the screen groups it, and asking the
        # internet for nothing when it is opened later.
        "html": ("text/html; charset=utf-8", exports.as_html),
    }
    # Formats that describe the sweep as well as listing it.
    EXPORTS_WITH_ABOUT = ("xlsx", "html")

    @app.get("/export.<fmt>")
    def export(fmt):
        """The listings on screen, as a file.

        Costs nothing and fetches nothing: it re-reads the shortlist already
        on disk and applies the filters from the query string, which is why
        the buttons carry the current filters with them.
        """
        if fmt not in EXPORTS:
            abort(404)
        if not app.state.get("profile"):
            return redirect(url_for("upload"))

        profile = app.state["profile"]
        min_score, source, q, sort = _shortlist_args()
        all_rows = rows_with_applied(profile)
        run = run_labels()
        multi = {}
        if run:
            # A Multi-Track run's export is its All Jobs (P4-E1; design §Q.1),
            # whichever résumé's view the visitor had open: every row the
            # strict reader passed, once, no floor unless one was asked for —
            # exactly what the page counted — each with the engine's own
            # fields, read again only through worker_link.multi_row, and the
            # run's labels beside them.
            from sweep import worker_link
            ids, labels = run
            min_score = request.args.get("min", type=int)
            typed = [(row, worker_link.multi_row(row, ids)) for row in all_rows]
            all_rows = [dict(row, _multi=exports.multi_fields(t, labels),
                             _words=recommendation_words(t, labels)) for row, t in typed]
            multi = {"multi": True}
        rows = shortlist(all_rows, min_score, source, q, sort)
        # Tagged from the SAME buckets the screen renders, so a row cannot be
        # filed under one heading on the page and another in the file.
        tagged = exports.rows_for_export(bucket_rows(rows), SECTIONS)

        mimetype, build = EXPORTS[fmt]
        if fmt in EXPORTS_WITH_ABOUT:
            about = [
                ("Profile", profile),
                ("Exported", datetime.now().strftime("%Y-%m-%d %H:%M")),
                ("Listings", len(tagged)),
                ("Minimum score", min_score or "no minimum"),
                ("Source", source or "All sources"),
                ("Search text", q or "none"),
                ("Sorted by", SORTS[sort][0])]
            if run:
                about[3] = ("Minimum score",
                            "no minimum" if min_score is None else min_score)
                about.insert(1, ("Résumés", " · ".join(run[1].values())))
            try:
                body = build(tagged, about=about, **multi)
            except ImportError:
                # A fresh clone that has not reinstalled. Say what to run
                # rather than 500 — CSV and JSON still work meanwhile.
                return _results_page(
                    error=("Excel export is not available right now. Your "
                           "jobs are all still here — use CSV, JSON or the "
                           "web page instead."
                           if app.config.get("PUBLIC_MODE") else
                           "Excel export needs the openpyxl package. Run "
                           "pip install -r requirements.txt and try again — "
                           "CSV and JSON work without it.")), 503
        else:
            body = build(tagged, **multi)

        # Stripped, not quoted: the profile name reaches a response header
        # here, and a quote or a newline in one would end the header early.
        safe = re.sub(r"[^A-Za-z0-9_-]", "", profile) or "sweep"
        name = f"sweep-{safe}-{datetime.now():%Y-%m-%d}.{fmt}"
        # content_type, not mimetype: the value already names its charset,
        # and mimetype= appended a second one (P4-S1C).
        return Response(body, content_type=mimetype, headers={
            "Content-Disposition": f'attachment; filename="{name}"'})

    @app.post("/rescore")
    def rescore():
        if not app.state.get("profile"):
            return redirect(url_for("upload"))
        if free_only():
            # A free sweep produces no Apify runs, so there is nothing to
            # re-read. Worse than useless: rescore_from_apify.py writes
            # jobs_combined.csv, which read_rows PREFERS, so a re-rank that
            # happened to find another profile's paid runs on a shared key
            # would replace THIS shortlist with them. The screen does not
            # offer it here; a posted form still has to be refused.
            #
            # A status, not a failure — so it goes through `notice`, not the
            # red reserved for over-cap.
            return _results_page(
                notice="Re-ranking re-reads what an Apify actor already "
                       "returned, and this sweep ran the free sources. There "
                       "is nothing to re-read, so nothing was changed."), 409
        try:
            # Label matches the field's own visible text, so the error names
            # the control the user is looking at.
            hours = _parse_int(request.form.get("hours") or "6", 1, 168,
                                "Hours to look back")
        except _FormError as exc:
            return _results_page(error=str(exc)), 400

        # The weights the panel posted, validated before anything is written
        # or launched. rescore_from_apify.py scores against
        # profiles/<name>.py, so an edit left only on state would re-rank
        # against the OLD numbers and read as an edit that did nothing.
        #
        derived = app.state.get("derived")
        source, kept = None, None
        if derived:
            try:
                kept = reweighted(derived, request.form.getlist("term"),
                                  request.form.getlist("weight"),
                                  request.form.getlist("drop"),
                                  request.form.get("add_skills") or "",
                                  request.form.get("add_weight") or "")
            except _FormError as exc:
                return _results_page(error=str(exc)), 400
            if kept == derived:
                kept = None          # nothing to write
            else:
                try:
                    source = make_profile.render(
                        app.state["profile"], kept, _prefs(app.state))
                except KeyError as exc:
                    # Same rule as /estimate: render() is the validator, and
                    # a failure must leave nothing applied.
                    return _results_page(error=str(exc)), 400

        # Checked and set under one lock. The dev server runs threaded, so
        # without it two clicks a few milliseconds apart both read "nothing
        # running" and both spawn a child truncating the same file. The
        # profile rewrite is inside too, for the reason POST /run's is: a
        # request refused with 409 must leave no trace, and the write still
        # has to land before the child reads the file.
        with _rescore_lock:
            busy = _rewriter_busy()
            if busy:
                # A status, not a failure — so it must not go through `error`,
                # which is painted the red reserved for over-cap.
                return _results_page(
                    notice=f"A {busy} is already running. Reload in a moment "
                           "to see the new ranking."), 409
            if source is not None:
                app.write_profile(app.state["profile"], source)
                app.state["derived"] = kept
            app.state["rescore_proc"] = start_rescore(
                app.state["profile"], hours)
        return redirect(_results_url())

    from sweep import feedback
    feedback.register(app)

    # Last, so it overrides what create_app just built: the allowlist,
    # per-session state, the beta door and the profile hand-off.
    if public.enabled():
        public.harden(app)

    return app


def _write_run_json(state, output_dir):
    """Persist what a reload needs: which profile, and the spend baseline.

    baseline_usd may be None (json.dump writes it as null) — that means
    read_spend() couldn't get a figure, not that the account has spent
    nothing. Task 8 must treat a None baseline as "show the raw current
    spend with a caveat", never subtract it as if it were 0 — that would
    report the account's whole month-to-date spend as this sweep's cost.
    """
    import json
    out_dir = os.path.join(output_dir, state["profile"])
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "run.json"), "w") as fh:
        json.dump({"profile": state["profile"],
                   "baseline_usd": state["baseline_usd"],
                   "planned": state["plan"]["total_searches"]}, fh)


def _prefs(state):
    return {
        "locations": state.get("locations") or ["Remote"],
        # None lets make_profile.render() set the cut from the résumé's
        # years (levels_for); nothing on the public screens sets it today.
        "exclude_levels": state.get("exclude_levels") or None,
        "avoid": state.get("avoid") or [],
        "min_comp_usd": state.get("min_comp_usd"),
        # Set by POST /run only (see spend_cap_for). Unset means the profile
        # inherits config.py's None, i.e. no cap — so /run must always set it.
        "max_spend_usd": state.get("max_spend_usd"),
        # Unset (None) means "not touched by the Configure screen yet" —
        # make_profile.render() omits the key entirely in that case, so
        # config.py's own default silently applies instead of being reset.
        "remote_scopes": state.get("remote_scopes"),
        # The other two thirds of the scope choice. work_scope is the
        # onsite/hybrid filter the "india" and "global" answers need — without
        # it they were the same sweep. location_hints is the free sources'
        # only location filter: they have no location parameter to query, so
        # the picker narrows them by matching each posting's own location
        # text. Both follow the "unset means inherit config" rule.
        "work_scope": state.get("work_scope"),
        "location_hints": state.get("location_hints"),
        "max_age_days": state.get("max_age_days"),
        "max_results": state.get("max_results"),
        "linkedin_locations": state.get("linkedin_locations"),
        "linkedin_remote_only": state.get("linkedin_remote_only"),
        # Unset means "inherit config.py's SITES", the same rule as every
        # other optional key here — never {} , which would render an overlay
        # switching every paid site off.
        "sites_enabled": state.get("sites_enabled"),
        # Set by POST /run only (V2-D1): True when the user ticked "run with
        # my available credit anyway"; unset inherits config's False.
        "allow_partial_paid_sweep": state.get("allow_partial_paid_sweep"),
    }
