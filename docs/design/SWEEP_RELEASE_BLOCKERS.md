# Release blockers found during the UI overhaul

Branch `design/sweep-ui-overhaul`. These are **not** design questions and **not** fixed by the
design phases. Each one has to be resolved, and regression-tested, before the branch is integrated
into production. They are listed here so they cannot be lost between phases; none of them may be
waved off because "users are human-paced" or "it is only the console".

## 1. A saved profile can be priced or run from stale bytecode — RESOLVED in D7C

**Status: fixed and regression-tested in D7C** (resolution at the end of this section; the text below is the
finding as it stood, kept so the history is not lost).


**Found:** D4.2, while reproducing the console profile-file race against the real engine.
**Where:** the console (`profiles/<name>.py`, read by `scraper.py --profile <name>`, imported as the
module `profiles.<name>`). Public mode keeps its profile in the session and is not affected.

**What happens.** Python decides a cached `profiles/__pycache__/<name>.cpython-XYZ.pyc` is still
valid by comparing the source file's modification time **in whole seconds** and its **size** with the
values recorded in the `.pyc`. Two writes of `profiles/<name>.py` inside the same second whose source
is the same length (for example a depth of `20` and then `40`) leave the second write looking
unchanged, and the engine imports the **first** write's bytecode.

**Evidence** (real `scraper.py --dry-run --json`, nothing injected; `d42_console_real.py`, D4.2):
estimating depths 5, 10, 20, 40 one after another on the `b1f8f93` tree quoted `0.576, 0.936, 0.936,
0.936`. With the requests a second apart the same tree quoted `0.576, 0.936, 1.872, 3.744`.

**What D4.2 did and did not fix.** Estimates now write a scratch profile with a unique name, so an
estimate can no longer be priced from another candidate's bytecode, and the saved profile is not
rewritten by an estimate. **The saved profile itself is still written by Save, by the review screen, by
`POST /run` (which re-renders it, stamping the spend cap, immediately before the engine starts), and by
re-rank.** Any two of those within a second that produce a same-length file can leave the engine, or the
next dry run, on the earlier profile. `POST /run` is the one that matters: the engine that spends money
could start from bytecode that predates the cap and preferences the visitor just approved.

**Required before integration.**
- Make a profile import independent of cached bytecode for the files this app writes: write the profile
  with a fresh modification time, or set `PYTHONDONTWRITEBYTECODE=1` (and clear any existing `.pyc` for that
  name) for the dry run and the engine child, or load the profile by path without the import cache. Choose
  by reading every writer and reader of `profiles/` (see D4.2's audit), not by patching one caller.
- A regression test that writes two same-sized profiles inside one second and proves the second is the
  one the engine reads, for the dry run **and** for the child `POST /run` starts. It must fail on the
  current code.
- Confirm the worker (public mode) is unaffected, or fix it the same way.

**Resolution (D7C).**
- *Root cause, confirmed.* The bytecode cache of `profiles/<name>.py` is valid when the source's mtime (whole seconds) and
  size match the `.pyc`; two saves inside one second at the same length are indistinguishable. Reproduced through the real
  console flow in a browser: Save at depth 20, Save at depth 40 inside the same second, Confirm quoted **$1.87** for
  depth 40 (the first save's price); the correct price is **$3.74**.
- *Fix, at the one place every reader goes through.* `config.import_profile(name)` finds `profiles.<name>` the ordinary way
  and then loads it with a source-only loader whose `get_code` compiles the file's bytes and never reads or writes a `.pyc`.
  `config.load_profile_module` (the engine, the dry run, every `--profile` selection) and `make_profile.load_profile` (the
  console's own reader) both call it. Nothing writes to `profiles/` any differently, and no caller had to change.
  `sweep/public.py` (Render) keeps its profile in the session and the worker writes a unique profile name per run
  (`test_the_worker_never_writes_the_same_profile_name_twice`), so neither was affected.
- *Regression tests* (`sweep/tests/test_profile_freshness.py`, 14 tests, real `profiles/` writes in child processes so the
  suite's own audit hook is honoured): the defect is real under the ordinary import (control); the real engine dry run
  (`scraper.py --dry-run --json`) reads the newest of two same-second same-size writes; a stale `.pyc` beside the source is
  never read; no `.pyc` at all; two profiles and two people never cross; invalid source fails loudly and is never replaced by
  an older valid one; a profile made in the last tick is found; `make_profile`'s loader reads the newest write; a static
  scan that no production reader imports `profiles.<name>` through the cache and that every console path selects the profile
  through `config`. With only `config.py` and `make_profile.py` put back to `36bc56f`, 9 of the 14 fail.
- *Browser:* flow W6 (`docs/design/d7c/harness/flows.mjs`) drives the console with the file's mtime pinned to one second:
  depth 20, 40, 20, 40 quote 1.87, 3.74, 1.87, 3.74 on the fixed tree and 1.87 every time on a copy of the tree with only
  `config.py` and `make_profile.py` put back.

## 2. A free sweep that the worker reports as failed or stopped is shown as finished — RESOLVED in D5.1

**Status: fixed and regression-tested** (`fix(web): respect authoritative free sweep terminal states`,
`sweep/tests/test_terminal_states.py`; 14 of its 22 tests fail on the parent `38de117`). Blocker 1 above is
**still open** and is not touched by this fix.

**Found:** D5, by driving a controlled worker through every state (the original audit had only seen a
finished run).
**Where:** the **public free** progress screen (`/running`) and the free console screen.

**Root cause.** A free sweep plans no searches, so `outstanding == 0` for its whole life, and
`_liveness()` in `sweep/app.py` turned that into `finished = not running and outstanding == 0`,
`sweep_state(..., outstanding=0) == "finished"`. A run the worker reported as **failed**, **stopped** or
**timed out** therefore read "Your jobs are ready", "Every search ran", with a "See the results" button. Zero
outstanding work is proof of nothing when nothing was planned.

**Old-code reproduction** (same fakes, worker says failed / visitor pressed Stop / worker says `run_timeout` /
done): all four gave `state=finished finished=True h1='Your jobs are ready'` with the success banner shown.

**Fix** (presentation-state derivation only; worker, planning, polling, queue and retry untouched):
the process's exit, which `RemoteRun` already maps from the worker's own state (`done` to 0; `failed`,
`stopped`, `interrupted` to 1), is passed to `sweep_state(..., failed=...)` **only for a run with no planned
searches**, and **only when the worker has not declared the result final** (`results_ready`, V2-B5: a crash in the
engine's last seconds never takes finished jobs away; `test_results_ready_early` pins this). The timeout is named
only because the worker **already records** `error: "run_timeout"` in the status it serves (`RemoteRun.timed_out`,
constant `worker_client.RUN_TIMEOUT`, pinned equal to `deploy/sweep_worker.RUN_TIMEOUT`); no worker change.

| Worker says | User pressed Stop | Screen state | Heading | Banner (heading / body) | Action |
|---|---|---|---|---|---|
| done, or `results_ready` | any | `finished` | Your jobs are ready | The search finished / Everything Sweep found is scored, ranked and saved. | **See the results** (primary) |
| failed, no reason recorded | no | `halted` | Sweep stopped early | The sweep did not finish / It stopped before it finished, and the reason is not recorded. Nothing was charged. Anything already fetched is saved. | See what it found (secondary) |
| failed with `run_timeout` | no | `halted` | Sweep stopped early | The sweep ran out of time / The sweep reached its time limit before it finished. Nothing was charged. Anything already fetched is saved. | See what it found (secondary) |
| stopped / failed after Stop | yes | `stopped` | You stopped the sweep | You stopped it / The sweep ended before it finished. Nothing was charged. Anything already fetched is saved. | See what it found (secondary) |
| running | any | `running` | Sweep is searching for you | (none) | Stop the sweep |

Failure and stop are coral "!" and ring shapes with words, never the teal tick. The console (operator) screen
uses the same state and banner; its free panel no longer promises listings "when the pass finishes" after a run
that did not finish. A paid run is unchanged (same state function, `failed` is never passed when searches were
planned); a paid run that hits the worker's timeout now names it in the same banner.

**What this does not do, on purpose, and what to decide:**
- A **paid** run whose every planned search is in the ledger still reads `finished` whatever the process's exit:
  its ledger is its evidence, and the brief for D5.1 said paid completed-run behaviour stays. If the engine can
  fail *after* the last paid search but before its free-source pass ends, that reads as finished. Owner decision
  whether to apply the exit code there too; it needs a new ending ("every search ran, then it failed").
- "You stopped it" is decided from the visitor's own Stop click, recorded in the session. After a server restart
  that memory is gone, so a stopped run then reads "did not finish, reason not recorded": neutral and honest, not
  success. The worker's `stopped` state could be used instead; it is a one-line change left for the owner.
- The free path never reports a jobs-found count (rows arrive at the end), so a free run that fails after
  fetching some jobs cannot say how many; it keeps "See what it found" and Results says what there is.

## 3. A paid run whose ledger is complete but whose process did not exit cleanly reads as finished — RESOLVED in D7C

**Found:** D5.1, recorded again in D6. **Status: fixed and regression-tested in D7C** (resolution below).
**Where:** `sweep_state()` and `_liveness()` in `sweep/app.py`, therefore the Running screen and, since D6, the
Results ending notice (`logic.results_ending`), which reads the same state.

A paid run whose every planned search is in the `.done_combos` ledger is `finished` whatever the process's exit,
because its ledger is its evidence and D5.1 was told to leave the paid path alone. If the engine can fail *after* the
last paid search (the free-source pass, scoring, the export), and the worker has **not** declared the result final
(`results_ready`), that run says "Your jobs are ready" and Results carries no "did not finish" notice. Needs an owner
decision and, if it is a real failure mode, a new ending ("every paid search ran, then it failed") and a test that
drives it through the real worker. To be reviewed before the final production merge.

**Resolution (D7C).** A new ending, `incomplete` ("every search ran, then the sweep stopped"). The process's exit is now
applied to a paid run too (`sweep/app.py` `_liveness`: `failed = code not in (None, 0) and not read_ready()`), and
`logic.sweep_state(..., failed, planned)` returns `incomplete` when nothing is outstanding, the process failed, the result was
never declared final and searches were planned. It is **not** `finished` (no "Your jobs are ready" tick, no "See the results"
as the primary action) and **not** `halted` (halted says the credit may be unspent, which is false when every search ran): the
running screen says every search ran, that their credit is spent, that everything fetched is saved, and offers "See what it
found". A `results_ready` marker still wins (the result is final; `test_results_ready_early`), an explicit Stop is still
`stopped`, the worker's `run_timeout` is still named ("every search ran, then the sweep ran out of time"), and fetched jobs are
kept and shown. A run with searches still outstanding is unchanged. Results carries the same ending notice
(`logic.results_ending`). Planning, pricing, AccountPool, quotas and provider execution are not touched.
Tests: `sweep/tests/test_terminal_states.py` (public and operator, schema 1 and schema 2, every worker word, with the ledger
written the way the engine writes it), `test_public_paid.py` (through the real worker), `test_active_run.py`. Browser: W8.

## 4. The worker's own `stopped` status is not recovered after a web-session restart — RESOLVED in D7C

**Found:** D5.1, recorded again in D6. **Status: fixed and regression-tested in D7C** (resolution below).
**Where:** `app.state["stopped_by_user"]` (set by `POST /stop`, `sweep/app.py`), read by `_liveness()`.

"You stopped the sweep" is decided from the visitor's own Stop click, which lives in the web session's memory. The
worker records `stopped` authoritatively, but the screens do not read that word back (`RemoteRun.poll()` folds it
into exit code 1). After a web restart or a rehydrate, a run the visitor stopped reads "did not finish, the reason is
not recorded" on both Running and Results: neutral and not a success, but less specific than the worker's own record.
The fix is to carry the worker's terminal state on `RemoteRun` (as `timed_out` already is) and let it stand in for
the session flag. To be reviewed before the final production merge.

**Resolution (D7C).** `RemoteRun.stopped` is true only when the worker itself recorded `stopped` (it does so in one place, its
own `stop()`); `_liveness` reads a stop as the visitor's click **or** `proc.stopped is True`. A generic failure, the worker's
`interrupted` (it restarted) and a timeout are never read as a stop, and nothing is inferred from a failure. `rehydrate` now
always attaches a `RemoteRun` (before, a run that had already ended when the web process restarted had no process at all and a
failed or stopped free run read "finished"), so every ending is read from the worker's own word after a restart. A paid run
that is rehydrated has no plan in memory, so its screens are the free ones, but they no longer say "Nothing was charged"
of a run that may have spent money (`charged_unknown`). Tests: `test_terminal_states.py` (`stopped`, `failed`,
`interrupted`, `done`, a rehydrate for each, public paid and free, one résumé and three), `test_public_paid.py`. Browser: W8
(24 endings, before and after a restart, 1440 and 390).

## 5. Raw reading diagnostics reached the public page and the profile file a visitor is handed — RESOLVED in D7C

**Found:** D7B review. **Where:** the public Review screen's "Technical notes" and "Worth knowing" blocks, and
`/profile.py`, which served the profile source with the reading's own comment block (notes, skills added, role evidence,
internal function names, and whatever a failing parser put in a message).

**Fix.** The notes blocks are rendered only in operator (local) mode; in public mode `public.keep_profile` stores
`make_profile.public_source(source)`, the same file with the notes section and the skills-added block redacted (and the whole
docstring replaced rather than guessed at if the layout ever moves). The operator keeps everything, escaped. A failure a
visitor sees is a curated sentence, never the exception text. **Tests:** `test_public_privacy.py` (hostile strings in every
field: paths, stack traces, secrets, markup, internal names; every public screen, the served file, the page's data, escaping,
curated failures, the operator's console unchanged) and `test_security_sweep.py` (a synthetic-marker search over every public
route's HTML and headers, a second browser sees nothing of the first, the key is never echoed, escaping, apply links that are
not http are never links, an upload leaves nothing on disk). Browser: W9.

## 6. Unsaved résumé edits could be lost by following a link — RESOLVED in D7C

**Found:** D7B review. **Fix.** `sweep/static/dirty.js` (about 100 lines, no dependency) on the résumé editor
(`form[data-editor]`, public and console). The editor is dirty when any control differs from the value the server rendered it
with, so editing and putting back is clean; a dirty editor holds links, other forms that navigate and the logo with a native
`<dialog>` ("Stay and keep editing", focused and the answer to Escape and the backdrop; "Discard changes and leave"), and
closing, reloading and Back get the browser's own `beforeunload` prompt. Saving clears it. Without a script the form works
as before. **Tests:** `sweep/tests/dirty_test.js` (Node, 46 checks against a stand-in page), `test_dirty_guard.py` (markup,
one dialog outside `<main>`, one marked form, no guard elsewhere, the script is served, no focus moved, no scroll), and a
12-of-12 mutation check on the script. Browser: W7 (stay, discard, save, revert, keyboard, phone; the browser's own prompt is
asserted where an engine raises it under automation).

## 7. Copy and layout items from the D7B review — RESOLVED in D7C

- **Over-credit sentence** is chosen by the real cause: a shortfall of money names the dollars; "the connected accounts can
  run 22 of 120 of these paid searches" when partial coverage is the cause; "None of these paid searches fit within the credit
  on your connected accounts" when nothing fits; "Paid searches are temporarily unavailable, so none will start. Nothing is
  charged." when the worker cannot authorise. The page and the live script say the same words, and nothing can print a
  "$0.00 more" shortfall (`test_d7c_copy.py`, `price_test.js`). Browser: W3, W4, W5.
- **All Jobs heading** reads "N jobs found" (a filtered view "k of N jobs shown"; a résumé's own view keeps "evaluated for").
  Browser: W10.
- **Filter and sort / Export** are two outlined secondary buttons (`button.secondary.tool-toggle`), separate from each other,
  44px on a phone, in the Quiet Ledger style. Browser: W10.
- **Operator header** on a sweep that costs nothing: a figure of exactly $0.00 is chalk, not amber, and the header says "Free
  sources only" rather than anything about credit. Browser: flow H.

