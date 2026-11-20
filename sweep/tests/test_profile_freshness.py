"""D7C blocker 1: a profile the console just wrote is the profile the engine reads.

Python trusts profiles/__pycache__/<name>.cpython-XYZ.pyc when the source's modification time (whole seconds) and size
match what the .pyc recorded. The console rewrites profiles/<name>.py on Save, on the review screen, on POST /run
(which stamps the spend cap immediately before the engine starts) and on re-rank, so two writes inside one second
that are the same length (a depth of 20, then 40) left the second looking unchanged and the engine imported the FIRST
write's bytecode. D4.2 stopped an estimate from being priced from another candidate's bytecode (it prices a scratch
profile); it did not touch the saved profile, which is what the engine that spends money starts from.

Nothing here depends on timing. The two writes are made the same length and their modification time is pinned to one
second with os.utime, so the cache's own test calls them the same file on every machine; the .pyc is made explicitly
(py_compile) so the precondition holds whatever PYTHONDONTWRITEBYTECODE says. The first test runs the real engine's
`scraper.py --dry-run --json`, which is the path a dry run and the child POST /run starts share (config.py selects
the profile at import time); the rest go through `config.load_profile_module`, the one loader both use. No model,
provider or network.
"""
import contextlib
import importlib
import importlib.util
import json
import os
import pathlib
import re
import secrets
import subprocess
import sys
import unittest

import config
from sweep import app as app_module
from sweep.tests.test_app import DERIVED

REPO = pathlib.Path(config.__file__).resolve().parent
PROFILES = REPO / "profiles"
SECOND = 1_790_000_000          # one whole second, for every write


def prefs_for(depth):
    # the production builder, so the source is exactly what Save writes
    return app_module._prefs({"max_results": depth, "max_spend_usd": 5.0, "locations": ["Remote"]})


def child(code, *args):
    """Run `code` in a fresh interpreter in the repo: what it prints is what it returns.

    Every write to the real profiles/ directory (the profile itself, its stale bytecode) is made here, not in the test process:
    test_app's setUpModule installs an audit hook that forbids any test from writing the repo's real profiles/, .env or output/
    (a fixture once left a junk key in .env), and that hook stays for the life of a full run. A test that must use the real
    engine has to use the real directory; it does it in a child, under a name of its own (_d7c_fresh_<hex>) that tearDown removes."""
    run = subprocess.run([sys.executable, "-c", code, *map(str, args)], cwd=REPO, capture_output=True, text=True, timeout=180)
    if run.returncode != 0:
        raise AssertionError(run.stderr[-600:])
    return run.stdout.strip()


WRITE = """
import os, sys, tempfile
sys.path.insert(0, "auto-apply")
from sweep import app as A
from sweep.tests.test_app import DERIVED
name, depth, seconds = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
raw = sys.argv[4] if len(sys.argv) > 4 else ""
tmp = tempfile.mkdtemp()
app = A.create_app(state={}, env_path=os.path.join(tmp, ".env"), output_dir=tmp)       # the REAL default writer
source = raw or A.make_profile.render(name, DERIVED, A._prefs({"max_results": depth, "max_spend_usd": 5.0, "locations": ["Remote"]}))
path = app.write_profile(name, source)
os.utime(path, (seconds, seconds))
print(len(source))
"""
PYC = """
import importlib.util, py_compile, sys
path = sys.argv[1]
cached = importlib.util.cache_from_source(path)
py_compile.compile(path, cfile=cached, doraise=True)
print(cached)
"""
ORDINARY = """
import importlib, sys
sys.path.insert(0, ".")
import profiles
print(importlib.import_module("profiles." + sys.argv[1]).SEARCH["max_results"])
"""


class Fresh(unittest.TestCase):
    def setUp(self):
        self.made = []

    def tearDown(self):
        for name in self.made:
            sys.modules.pop(f"profiles.{name}", None)
            with contextlib.suppress(FileNotFoundError):
                os.remove(PROFILES / f"{name}.py")
            cache = PROFILES / "__pycache__"
            if cache.is_dir():
                for leftover in cache.glob(f"{name}.*"):
                    with contextlib.suppress(FileNotFoundError):
                        leftover.unlink()

    def name(self):
        n = f"_d7c_fresh_{secrets.token_hex(5)}"
        self.made.append(n)
        return n

    def source(self, name, depth):
        return app_module.make_profile.render(name, DERIVED, prefs_for(depth))

    def write(self, name, depth, seconds=SECOND, source=None):
        """What the console's own writer does (the real default one, in a child), then the clock pinned."""
        child(WRITE, name, depth, seconds, *([source] if source is not None else []))
        return PROFILES / f"{name}.py"

    def pyc_for(self, path):
        cached = child(PYC, path)
        self.assertTrue(os.path.exists(cached), "the precondition: a .pyc exists")
        return cached

    def depth_read(self, name):
        sys.modules.pop(f"profiles.{name}", None)          # a new process has nothing imported
        module, _stamp = config.load_profile_module(name)
        return module.SEARCH["max_results"]

    def ordinary_import_depth(self, name):
        """What the old loader did: the plain import, which trusts the cache (in a fresh interpreter, as the engine is)."""
        return int(child(ORDINARY, name))


class TheBugIsReal(Fresh):
    def test_two_same_sized_writes_in_one_second_look_unchanged_to_the_ordinary_import(self):
        """The control: the plain import this loader replaced does return the first write's value. If this ever stops
        being true of the interpreter, the other tests still hold (they assert the NEW value), and this says why."""
        name = self.name()
        first = self.write(name, 20)
        self.pyc_for(first)
        second = self.write(name, 40)
        self.assertEqual(len(self.source(name, 20)), len(self.source(name, 40)), "same length")
        self.assertEqual(os.stat(first).st_mtime_ns // 10**9, os.stat(second).st_mtime_ns // 10**9)
        self.assertEqual(self.ordinary_import_depth(name), 20, "the stale bytecode answers: this is the defect")


class SaveThenRun(Fresh):
    def test_the_real_engine_dry_run_reads_the_newest_write(self):
        """Save (depth 20), the engine reads it; Run re-writes it (depth 40) inside the same second: the engine, started as
        scraper.py --profile NAME, must read 40. Real scraper.py, nothing injected."""
        name = self.name()
        seen = []
        for depth in (20, 40, 20, 40):
            self.write(name, depth)
            run = subprocess.run([sys.executable, "scraper.py", "--profile", name, "--dry-run", "--json"],
                                 cwd=REPO, capture_output=True, text=True, timeout=180)
            self.assertEqual(run.returncode, 0, run.stderr[-400:])
            seen.append(json.loads(run.stdout)["max_results"]["linkedin"])
        self.assertEqual(seen, [20, 40, 20, 40])

    def test_a_first_write_that_left_bytecode_beside_it_does_not_matter(self):
        name = self.name()
        first = self.write(name, 20)
        self.assertEqual(self.depth_read(name), 20)
        self.pyc_for(first)
        self.write(name, 40)
        self.assertEqual(self.depth_read(name), 40)


class Matrix(Fresh):
    def test_a_stale_pyc_is_never_read(self):
        name = self.name()
        path = self.write(name, 20)
        cached = self.pyc_for(path)
        before = pathlib.Path(cached).read_bytes()
        self.write(name, 40)
        self.assertEqual(self.depth_read(name), 40)
        self.assertEqual(pathlib.Path(cached).read_bytes(), before, "and the loader does not rewrite it either")

    def test_no_pyc_at_all(self):
        name = self.name()
        path = self.write(name, 40)
        self.assertFalse(os.path.exists(importlib.util.cache_from_source(str(path))))
        self.assertEqual(self.depth_read(name), 40)
        self.assertFalse(os.path.exists(importlib.util.cache_from_source(str(path))),
                         "reading a profile leaves no bytecode behind to go stale")

    def test_two_profiles_and_two_people_never_cross(self):
        a, b = self.name(), self.name()
        pa, pb = self.write(a, 20), self.write(b, 40)
        self.pyc_for(pa)
        self.pyc_for(pb)
        self.write(a, 40)
        self.write(b, 20)
        self.assertEqual((self.depth_read(a), self.depth_read(b)), (40, 20))

    def test_invalid_source_fails_loudly_and_is_never_replaced_by_an_older_valid_one(self):
        name = self.name()
        valid = self.source(name, 20)
        path = self.write(name, 20, source=valid)
        self.pyc_for(path)
        broken = "SEARCH = {" + "#" * (len(valid) - len("SEARCH = {"))       # same length, not Python
        self.assertEqual(len(broken), len(valid))
        self.write(name, 20, source=broken)
        sys.modules.pop(f"profiles.{name}", None)
        with self.assertRaises(SyntaxError):
            config.load_profile_module(name)
        self.assertNotIn(f"profiles.{name}", sys.modules, "a half-loaded module is not left behind")
        self.write(name, 40)                                                  # and the fixed file is read at once
        self.assertEqual(self.depth_read(name), 40)

    def test_running_again_without_saving_reads_the_same_profile(self):
        name = self.name()
        self.write(name, 40)
        self.assertEqual([self.depth_read(name) for _ in range(3)], [40, 40, 40])

    def test_an_unknown_profile_is_still_the_same_loud_exit(self):
        with self.assertRaises(SystemExit) as stopped:
            config.load_profile_module("_d7c_nobody_" + secrets.token_hex(4))
        self.assertIn("Unknown profile", str(stopped.exception))

    def test_a_profile_made_in_the_last_tick_is_found(self):
        # the directory listing is cached by the import system: a file created after it was read must still be seen
        first, second = self.name(), self.name()
        self.write(first, 20)
        self.assertEqual(self.depth_read(first), 20)
        self.write(second, 40)
        self.assertEqual(self.depth_read(second), 40)

    def test_make_profiles_own_loader_reads_the_newest_write_too(self):
        sys.path.insert(0, str(REPO / "auto-apply"))
        try:
            import make_profile
        finally:
            sys.path.pop(0)
        name = self.name()
        self.pyc_for(self.write(name, 20))
        self.write(name, 40)
        sys.modules.pop(f"profiles.{name}", None)
        module, _stamp = make_profile.load_profile(name)
        self.assertEqual(module.SEARCH["max_results"], 40)


class EveryReader(unittest.TestCase):
    """The audit as a test: no production reader imports a profile by name straight through the import cache."""

    def test_no_production_reader_trusts_the_bytecode_cache(self):
        files = [REPO / "config.py", REPO / "auto-apply" / "make_profile.py", REPO / "deploy" / "sweep_worker.py",
                 *sorted((REPO / "sweep").glob("*.py")), REPO / "scraper.py"]
        def code(path):                       # comments name the call without making it
            return re.sub(r"(?m)^\s*#.*$", "", path.read_text(encoding="utf-8"))
        offenders = [str(f.relative_to(REPO)) for f in files
                     if re.search(r'import_module\(\s*f?["\']profiles\.', code(f))]
        self.assertEqual(offenders, [], "read profiles through config.import_profile / load_profile_module")

    def test_every_way_the_console_starts_the_engine_selects_the_profile_through_config(self):
        runs = (REPO / "sweep" / "runs.py").read_text(encoding="utf-8")
        self.assertIn('"scraper.py", "--profile", profile, "--yes"', runs)         # POST /run's child
        self.assertIn("JOB_PROFILE", runs)                                          # re-rank and merge
        plan = (REPO / "sweep" / "plan.py").read_text(encoding="utf-8")
        self.assertIn('"scraper.py", "--profile", profile, "--dry-run", "--json"', plan)   # the dry run
        # ... and config.py is where all of them pick it up, once, through the loader
        text = (REPO / "config.py").read_text(encoding="utf-8")
        self.assertEqual(text.count("load_profile_module(PROFILE)"), 1)
        self.assertIn("class FreshSource", text)
        self.assertIn("def get_code", text)

    def test_the_worker_never_writes_the_same_profile_name_twice(self):
        # public mode: a plan or a run gets its own name, so the cache has nothing to confuse
        worker = (REPO / "deploy" / "sweep_worker.py").read_text(encoding="utf-8")
        self.assertIn('name = f"plan_{secrets.token_hex(8)}"', worker)
        self.assertIn('profile_name = f"beta_{run_id}"', worker)
        self.assertNotIn("default_write_profile", worker)


if __name__ == "__main__":
    unittest.main()
