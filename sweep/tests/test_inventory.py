"""sources/inventory.py: fetch once, read many — and read the SAME rows.

No network: ats.fetch and the feed fetchers are replaced by fakes that end
the way the real ones do, filtering on row["Title"] and row["Location"].
"""
import os
import sqlite3
import tempfile
import time
import unittest
from unittest import mock

import sources
from sources import inventory

BOARDS = {"greenhouse": {"acme": "Acme"}, "lever": {"zeta": "Zeta"}}
FEEDS = {"remoteok": {"enabled": True}, "himalayas": {"enabled": True},
         "wwr": {"enabled": False}}


def job(title, location, url, company="Acme"):
    return {"Title": title, "Company": company, "Location": location,
            "Job URL": url, "hires_home": ""}


class Fake:
    """Board contents the tests can change between refreshes."""

    def __init__(self):
        self.boards = {
            "acme": [job("Backend Engineer", "Bengaluru, India", "u/a1"),
                     job("Account Executive", "Bengaluru, India", "u/a2"),
                     job("Backend Engineer", "Berlin", "u/a3")],
            "zeta": [job("Python Developer", "Remote", "u/z1", "Zeta")],
        }
        self.feed = [job("Node Developer", "Worldwide", "u/f1", "Feedco")]
        self.himalayas = [job("Go Engineer", "Anywhere", "u/h1", "Himco")]
        self.down = set()

    def ats_fetch(self, platform, token, company, keep_title, keep_location,
                  is_home=None):
        if token in self.down:
            raise OSError("board down")
        rows = [dict(r) for r in self.boards[token]]
        if is_home is not None:
            home = "yes" if any(is_home(r["Location"]) for r in rows) else "no"
            for r in rows:
                r["hires_home"] = home
        return [r for r in rows if keep_title(r["Title"]) and keep_location(r["Location"])]

    def feed_fetch(self, rows):
        def fetch(_cfg, keep_title, keep_location):
            return [dict(r) for r in rows
                    if keep_title(r["Title"]) and keep_location(r["Location"])]
        return fetch


def keep_title(title):
    return "engineer" in title.lower() or "developer" in title.lower()


def keep_location(location):
    return any(w in location.lower() for w in ("india", "remote", "worldwide", "anywhere"))


def is_home(location):
    return "india" in (location or "").lower()


class InventoryTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "inv.sqlite")
        self.fake = Fake()
        patches = [
            mock.patch.object(sources.ats, "fetch", self.fake.ats_fetch),
            mock.patch.object(inventory.feeds, "remoteok", self.fake.feed_fetch(self.fake.feed)),
            mock.patch.dict(sources.FEED_FETCHERS, {
                "remoteok": self.fake.feed_fetch(self.fake.feed),
                "himalayas": self.fake.feed_fetch(self.fake.himalayas)}),
            mock.patch.object(sources.concurrency, "applies", lambda _p: False),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def refresh(self):
        return inventory.refresh(self.db, BOARDS, FEEDS, is_home, log=lambda *_: None)

    def fetch(self, env):
        with mock.patch.dict(os.environ, env, clear=False):
            if not env:
                os.environ.pop(inventory.DB_ENV, None)
            return sources.fetch_free(BOARDS, FEEDS, keep_title, keep_location,
                                      is_home, log=lambda *_: None)

    @staticmethod
    def urls(rows):
        return sorted(r["Job URL"] for r in rows)

    def test_cached_rows_are_the_live_rows(self):
        live = self.fetch({})
        self.refresh()
        cached = self.fetch({inventory.DB_ENV: self.db})
        self.assertEqual(self.urls(cached), self.urls(live))
        self.assertEqual(self.urls(live), ["u/a1", "u/f1", "u/h1", "u/z1"])
        # hires_home is a board-level fact computed at refresh, as live.
        by_url = {r["Job URL"]: r for r in cached}
        self.assertEqual(by_url["u/a1"]["hires_home"], "yes")
        self.assertEqual(by_url["u/z1"]["hires_home"], "no")

    def test_himalayas_stays_live(self):
        self.refresh()
        con = sqlite3.connect(self.db)
        sources_stored = {s for (s,) in con.execute("SELECT source FROM sources")}
        con.close()
        self.assertNotIn("feed:himalayas", sources_stored)
        self.assertIn("u/h1", self.urls(self.fetch({inventory.DB_ENV: self.db})))

    def test_a_job_the_board_drops_is_closed(self):
        self.refresh()
        self.fake.boards["acme"] = self.fake.boards["acme"][1:]      # u/a1 filled
        self.refresh()
        self.assertNotIn("u/a1", self.urls(self.fetch({inventory.DB_ENV: self.db})))

    def test_a_failed_board_keeps_its_jobs(self):
        self.refresh()
        self.fake.down.add("acme")
        ok, failed, _open = self.refresh()
        self.assertEqual(failed, 1)
        self.assertIn("u/a1", self.urls(self.fetch({inventory.DB_ENV: self.db})))

    def test_a_reopened_job_comes_back(self):
        self.refresh()
        saved = self.fake.boards["acme"]
        self.fake.boards["acme"] = []
        self.refresh()
        self.fake.boards["acme"] = saved
        self.refresh()
        self.assertIn("u/a1", self.urls(self.fetch({inventory.DB_ENV: self.db})))

    def test_a_stale_or_missing_db_means_live(self):
        self.assertIsNone(inventory.fresh_path({inventory.DB_ENV: self.db}))
        self.refresh()
        self.assertEqual(inventory.fresh_path({inventory.DB_ENV: self.db}), self.db)
        con = sqlite3.connect(self.db)
        con.execute("UPDATE meta SET v=? WHERE k='refreshed_at'",
                    (str(time.time() - 13 * 3600),))
        con.commit()
        con.close()
        self.assertIsNone(inventory.fresh_path({inventory.DB_ENV: self.db}))
        # Still answers: everything fetched live.
        self.fake.boards["zeta"].append(job("Rust Developer", "Remote", "u/z2", "Zeta"))
        self.assertIn("u/z2", self.urls(self.fetch({inventory.DB_ENV: self.db})))

    def test_a_board_not_in_this_sweep_is_not_read(self):
        self.refresh()
        only_acme = {"greenhouse": {"acme": "Acme"}}
        with mock.patch.dict(os.environ, {inventory.DB_ENV: self.db}):
            rows = sources.fetch_free(only_acme, {}, keep_title, keep_location,
                                      is_home, log=lambda *_: None)
        self.assertEqual(self.urls(rows), ["u/a1"])


if __name__ == "__main__":
    unittest.main()
