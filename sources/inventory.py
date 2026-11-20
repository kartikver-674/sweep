"""Fetch once, read many: a SQLite copy of every free board and feed.

Without it every sweep re-fetched all ~130 free sources for every visitor
(2-9 minutes, queued behind paid sweeps), and adding a board made every
visitor's sweep slower. With it a timer refreshes the copy every few hours and
a sweep reads it in well under a second.

    python -m sources.inventory refresh     # fetch everything, update the db
    python -m sources.inventory status      # when, how many, which failed

It is switched on by SWEEP_INVENTORY_DB (a file path). Unset, missing or older
than SWEEP_INVENTORY_MAX_AGE hours (default 12), sources.fetch_free fetches
live exactly as before, so a dead timer degrades to slow, never to empty.

What it stores is the rows the adapters already produce, unfiltered: every
source filters on row["Title"] and row["Location"] as its last step, so
applying a visitor's keep_title / keep_location at read time gives the same
rows a live fetch would. Two things stay live because they are per visitor or
switched off: Himalayas (searched with the visitor's own role keywords) and
Optum / Enterprise.

A board that answered replaces its open set: a job it no longer lists gets
closed_at, because ATS boards only list open jobs. A board that failed this
refresh keeps the rows it had, so one bad fetch never empties a company.
"""
import json
import os
import sqlite3
import sys
import time

from . import ats, feeds

DB_ENV = "SWEEP_INVENTORY_DB"
MAX_AGE_ENV = "SWEEP_INVENTORY_MAX_AGE"
LIVE_FEEDS = {"himalayas"}      # per-visitor queries; fetched live every sweep

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    key        TEXT PRIMARY KEY,
    source     TEXT NOT NULL,
    row        TEXT NOT NULL,
    first_seen REAL NOT NULL,
    last_seen  REAL NOT NULL,
    closed_at  REAL
);
CREATE INDEX IF NOT EXISTS jobs_open ON jobs (source) WHERE closed_at IS NULL;
CREATE TABLE IF NOT EXISTS sources (
    source TEXT PRIMARY KEY,
    ok_at  REAL,
    tried_at REAL NOT NULL,
    count  INTEGER,
    error  TEXT
);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def _connect(path):
    con = sqlite3.connect(path, timeout=30)
    con.execute("PRAGMA journal_mode=WAL")      # readers never wait on a refresh
    con.executescript(_SCHEMA)
    return con


def _key(row):
    url = (row.get("Job URL") or "").strip()
    if url:
        return url
    return "|".join((row.get("Company") or "", row.get("Title") or "",
                     row.get("Location") or ""))


def board_source(platform, token):
    return f"{platform}:{token}"


def feed_source(name):
    return f"feed:{name}"


# ---------------------------------------------------------------- refresh

def _store(con, source, rows, now):
    """One source answered: upsert its rows, close the ones it dropped."""
    seen = set()
    for row in rows:
        key = _key(row)
        seen.add(key)
        con.execute(
            "INSERT INTO jobs (key, source, row, first_seen, last_seen) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET "
            "source=excluded.source, row=excluded.row, "
            "last_seen=excluded.last_seen, closed_at=NULL",
            (key, source, json.dumps(row, ensure_ascii=False), now, now))
    open_keys = [k for (k,) in con.execute(
        "SELECT key FROM jobs WHERE source=? AND closed_at IS NULL", (source,))]
    gone = [k for k in open_keys if k not in seen]
    con.executemany("UPDATE jobs SET closed_at=? WHERE key=?",
                    [(now, k) for k in gone])
    con.execute("INSERT INTO sources (source, ok_at, tried_at, count, error) "
                "VALUES (?, ?, ?, ?, NULL) ON CONFLICT(source) DO UPDATE SET "
                "ok_at=excluded.ok_at, tried_at=excluded.tried_at, "
                "count=excluded.count, error=NULL",
                (source, now, now, len(rows)))
    return len(gone)


def _failed(con, source, exc, now):
    con.execute("INSERT INTO sources (source, tried_at, error) VALUES (?, ?, ?) "
                "ON CONFLICT(source) DO UPDATE SET tried_at=excluded.tried_at, "
                "error=excluded.error", (source, now, str(exc)[:300]))


def refresh(path, ats_boards, feed_cfg, is_home, log=print):
    """Fetch every board and feed unfiltered and bring the db up to date.
    Returns (sources ok, sources failed, open jobs)."""
    def keep(_value):
        return True
    con = _connect(path)
    ok = failed = 0
    started = time.time()
    # ponytail: serial; ~130 boards take a few minutes, which a timer does not
    # mind. Reuse sources.concurrency if the board list grows past ~500.
    for platform, boards in (ats_boards or {}).items():
        if platform not in ats.ATS:
            continue
        for token, company in boards.items():
            source = board_source(platform, token)
            now = time.time()
            try:
                rows = ats.fetch(platform, token, company, keep, keep, is_home)
            except Exception as exc:
                _failed(con, source, exc, now)
                failed += 1
                log(f"  {source:<40} ! {exc}")
            else:
                closed = _store(con, source, rows, now)
                ok += 1
                log(f"  {source:<40} {len(rows):>5} jobs, {closed} closed")
            con.commit()
    for name, cfg in (feed_cfg or {}).items():
        if name in LIVE_FEEDS or not cfg.get("enabled"):
            continue
        fetcher = getattr(feeds, name, None)
        if fetcher is None:
            continue
        source = feed_source(name)
        now = time.time()
        try:
            rows = fetcher(cfg, keep, keep)
        except Exception as exc:
            _failed(con, source, exc, now)
            failed += 1
            log(f"  {source:<40} ! {exc}")
        else:
            closed = _store(con, source, rows, now)
            ok += 1
            log(f"  {source:<40} {len(rows):>5} jobs, {closed} closed")
        con.commit()
    con.execute("INSERT INTO meta (k, v) VALUES ('refreshed_at', ?) "
                "ON CONFLICT(k) DO UPDATE SET v=excluded.v", (str(time.time()),))
    con.commit()
    open_jobs = con.execute(
        "SELECT COUNT(*) FROM jobs WHERE closed_at IS NULL").fetchone()[0]
    con.close()
    log(f"inventory: {ok} sources ok, {failed} failed, {open_jobs} open jobs, "
        f"{time.time() - started:.0f}s")
    return ok, failed, open_jobs


# ---------------------------------------------------------------- read

def fresh_path(env=None):
    """The db path when the inventory is switched on and recent, else None."""
    env = os.environ if env is None else env
    path = (env.get(DB_ENV) or "").strip()
    if not path or not os.path.exists(path):
        return None
    hours = float(env.get(MAX_AGE_ENV) or 12)
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
        got = con.execute("SELECT v FROM meta WHERE k='refreshed_at'").fetchone()
        con.close()
    except sqlite3.Error:
        return None
    if not got or time.time() - float(got[0]) > hours * 3600:
        return None
    return path


def read(path, ats_boards, feed_cfg, keep_title, keep_location):
    """The open rows of every configured board and enabled stored feed that
    pass the visitor's own title and location gates, in board-list order."""
    wanted = [board_source(p, t) for p, boards in (ats_boards or {}).items()
              for t in boards]
    wanted += [feed_source(n) for n, cfg in (feed_cfg or {}).items()
               if cfg.get("enabled") and n not in LIVE_FEEDS]
    order = {s: i for i, s in enumerate(wanted)}
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    got = con.execute("SELECT source, row FROM jobs WHERE closed_at IS NULL "
                      "ORDER BY first_seen, key").fetchall()
    con.close()
    rows = []
    for source, raw in got:
        if source not in order:
            continue
        row = json.loads(raw)
        if keep_title(row.get("Title") or "") and keep_location(row.get("Location") or ""):
            rows.append((order[source], row))
    rows.sort(key=lambda pair: pair[0])         # stable: first_seen within a source
    return [row for _i, row in rows]


def status(path):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    at = con.execute("SELECT v FROM meta WHERE k='refreshed_at'").fetchone()
    open_jobs = con.execute("SELECT COUNT(*) FROM jobs WHERE closed_at IS NULL").fetchone()[0]
    bad = con.execute("SELECT source, error FROM sources WHERE error IS NOT NULL "
                      "ORDER BY source").fetchall()
    con.close()
    age = (time.time() - float(at[0])) / 3600 if at else None
    print(f"refreshed {age:.1f} h ago" if age is not None else "never refreshed")
    print(f"open jobs: {open_jobs}")
    for source, error in bad:
        print(f"  failing: {source}: {error}")


def main(argv):
    path = os.environ.get(DB_ENV)
    if not path or len(argv) != 1 or argv[0] not in ("refresh", "status"):
        print(f"usage: {DB_ENV}=/path/inventory.sqlite "
              "python -m sources.inventory refresh|status")
        return 2
    if argv[0] == "status":
        status(path)
        return 0
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import config
    import scraper
    ok, _failed_count, _open = refresh(path, config.ATS_BOARDS, config.FEEDS,
                                       scraper.is_home_location)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
