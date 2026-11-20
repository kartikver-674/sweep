# Sweep UI — release candidate (D7C)

Branch `design/sweep-ui-overhaul` (local; no upstream). Nothing in it has been pushed, merged or deployed.
`main` and `origin/main` are at `fdb0da0`. D1 to D7B are accepted and this phase did not reopen visual design or motion.

| | |
|---|---|
| **Verdict** | **RC PASS.** All six blockers are resolved and regression-tested; the full release suite has no failure (4,257 of 4,263 pass; the 2 errors are environment-dependent inference health checks that do not touch Sweep, the 4 skips are Linux-only); the eleven browser flows pass 11 of 11 on Chromium, Chrome, Firefox and WebKit; the at-rest regression shows only the intended differences. Not run: Safari.app (a manual checklist is below) and a real Render and worker deploy (a prerequisite, not a blocker) |
| Starting point of D7C | `36bc56f` (D7B and its Firefox/WebKit follow-up) |
| Release candidate | `36bc56f..` the tip of `design/sweep-ui-overhaul`: `106c094` profile freshness, `b88dcf4` run endings and stop recovery, `9fec5e0` public privacy, unsaved-edits guard and copy, then the docs and evidence commit (the tip) |
| Rollback point | `fdb0da0` (`main`, what Render runs today). Within the branch, `36bc56f` is the last commit before D7C |
| Evidence | `output/design-D7C/` (git-ignored; manifest `docs/design/EVIDENCE_MANIFEST_D7C.sha256`), tooling `docs/design/d7c/` |

## 1. Release blockers

Every blocker from `SWEEP_RELEASE_BLOCKERS.md` and the D7C brief, with what was reproduced, the root cause, the fix, where it is
pinned and its status. Details, tests and browser flows are in that file; this table is the summary.

| # | Blocker | Reproduced | Root cause | Fix | Status |
|---|---|---|---|---|---|
| 1 | A saved profile is priced or run from stale bytecode | Console, real browser: Save at depth 20, Save at depth 40 inside the same second; Confirm quoted **$1.87**, the correct figure is **$3.74** | `.pyc` validity is source mtime (whole seconds) plus size; a same-length rewrite in the same second looks unchanged | `config.import_profile`: a source-only loader that never reads or writes a `.pyc`, used by `load_profile_module` (engine, dry run, `--profile`) and `make_profile.load_profile` | **RESOLVED** |
| 2 | Paid run, complete ledger, failed process, read as "finished" | Real worker: every search in `.done_combos`, process fails, no `results_ready`: "Your jobs are ready" | `failed` was applied only to runs with no planned searches | New `incomplete` ending ("every search ran, then the sweep stopped"); `results_ready` still wins; explicit stop stays `stopped`; the worker's `run_timeout` is named; fetched jobs kept | **RESOLVED** |
| 3 | The worker's `stopped` is forgotten after a web restart | `/__restart` after a stop: "did not finish, reason not recorded" | The word was folded into exit code 1 and only the click was remembered; `rehydrate` attached no process to an ended run | `RemoteRun.stopped` (the worker's own `stopped` only, never inferred from a failure); `rehydrate` always attaches a `RemoteRun`; a restarted paid run says nothing about being free (`charged_unknown`) | **RESOLVED** |
| 4 | Raw reading diagnostics in public HTML and in `/profile.py` | Hostile notes, paths, secrets and a stack trace in a reading appeared in the public Review and in the file served | The notes blocks and the generated file carried the derivation's own diagnostics | Notes blocks rendered in operator mode only; `public.keep_profile` stores `make_profile.public_source` (redacted, fail-closed); curated failure sentences | **RESOLVED** |
| 5 | Unsaved résumé edits lost by following a link | Edit years, press another résumé's Review: edit silently discarded | No guard | `sweep/static/dirty.js`: stateless dirty test, native `<dialog>` Stay / Discard, `beforeunload`; Save clears it | **RESOLVED** |
| 6 | Copy and layout: A over-credit wording, B "jobs found", C Filter/Export, D operator header | Seen in the D7B review | A "$0.00 more" when the cause was coverage; B "matched your profile" on a list that holds negative scores; C underlined words easy to read past; D amber `$0.00` and credit talk on a free sweep | A one sentence chosen by real cause; B "N jobs found"; C two outlined secondary buttons; D a zero figure is chalk, free header says "Free sources only" | **RESOLVED** |

No blocker is STILL OPEN.

## 2. Frozen contracts

None of these were changed, and the check is the same for each: the diff touches none of the files that implement them, and the full
suite (including the golden tests that pin them) passes.

| Contract | Evidence |
|---|---|
| Recommendation semantics, caution before suggestion, "Suggested résumé", raw scores, All Jobs and `track_evals` membership, export schemas, mobile Apply target | `scraper.py`, the export writers and the recommendation code are not in the diff; W10 asserts the suggested résumé, a negative score and the export holding every job; the golden tests pass |
| D7B motion, GSAP decision, tile-scale removal, Results stagger, pending dim and slate | `sweep.css` changes are three rules (the Filter/Export button box, a zero figure's colour); no animation, transition or keyframe was touched; `test_motion` passes; the at-rest regression below shows only the intended differences |
| Planning, pricing, AccountPool, quotas, provider execution | `sweep/plan*`, `sweep/runs.py`, `deploy/`, `scraper.py` are not in the diff. The incomplete ending only reads the ledger and the process's exit |
| D4.1 estimate isolation, D4.2 scratch-profile pricing, overlapping Save and estimate | The estimate path still writes a unique scratch profile; the existing tests pass; W6 saves, estimates and runs back to back |

## 3. What changed

Source: `config.py`, `auto-apply/make_profile.py`, `sweep/public.py`, `sweep/logic.py`, `sweep/app.py`, `sweep/worker_link.py`,
`sweep/templates/{base,configure,results,review,running}.html`, `sweep/static/{dirty.js (new),price.js,sweep.css}`.

Regression tests added or changed: `test_profile_freshness.py` (14), `test_public_privacy.py`, `test_security_sweep.py`,
`test_dirty_guard.py` + `dirty_test.js` (46 checks, 12 of 12 mutations caught), `test_d7c_copy.py`, `test_terminal_states.py`,
`test_public_paid.py`, `test_active_run.py`, `test_results_ui.py`, `test_unified_review.py`, `price_test.js`, and pins updated in
`test_app.py`, `test_live_price.py`, `test_motion.py`, `test_multi_results_view.py`, `test_results_ready_early.py`.
`test_results_ready_early.py` also carried a D7B regression found during D7C: its Node harness did not stub Alpine's `$nextTick`, so
the ending-transition test failed with `$nextTick is not defined` (the application was right; the harness was not).

## 4. Full release suite

Credentials emptied (present, so `load_dotenv` leaves them alone: no provider, model or paid call is possible), no proxy, the sealed test
environment, one location after another. Run on the final tree. Log files hold names and totals only.

| Location | Total | Passed | Failed | Skipped | Runtime |
|---|---|---|---|---|---|
| `sweep/tests` (unittest discover; includes the Node-driven `test_motion` and `results_motion_test.js`) | 2,664 | 2,660 | 0 | 4 | 725 s |
| `auto-apply/tests` | 1,226 | 1,224 | 2 (errors) | 0 | 63 s |
| `bench` | 161 | 161 | 0 | 0 | 301 s |
| `deploy` (`test_sweep_worker`, `test_modal_benchmark`) | 65 | 65 | 0 | 0 | 6 s |
| JS, `node sweep/tests/<name>_test.js`: price 69, pick 23, reading 9, dirty 46 checks | 147 | 147 | 0 | 0 | under 1 s each |
| **All** | **4,263** | **4,257** | **2** | **4** | **about 18 min** |

- **The 2 errors** are `test_healthz_needs_no_token` and `test_healthz_answers_while_a_generation_holds_the_slot`
  (`auto-apply/tests/test_inference.py`): the inference server's `/healthz` answers 503 on this machine because no model runtime is reachable.
  Identical on an export of `36bc56f` (before any D7C change) and both pass with that probe stubbed; they do not touch Sweep.
- **The 4 skips** are the Linux-only `RLIMIT_AS` memory-ceiling tests of the PDF reader (`TestSafePdfOnLinux`, `TestSafePdf`). They cannot run on
  macOS. They are unchanged by D7C and remain an owner item for the Linux (Render) side.
- Evidence manifests: all nine earlier manifests (1,110 files) verify; the D7C manifest (378 files) verifies too, 1,488 files in ten manifests.

## 5. Browser matrix

`docs/design/d7c/harness/flows.mjs`, the real application (the Render public app and the worker on loopback; the operator console with its
real profile writes and its real engine dry run), synthetic data, no provider, key or model. 11 flows, each at 1440 and 390 where it has a
viewport.

| Flow | Chromium 151.0.7922.34 | Google Chrome 154.0.8037.58 | Firefox 153.0 | WebKit 26.5 (Playwright 1.62.1) |
|---|---|---|---|---|
| W1 One résumé, free, through the screens | PASS | PASS | PASS | PASS † |
| W2 Three résumés, free, through Confirm to Results | PASS | PASS | PASS | PASS † |
| W3 Paid, fully covered | PASS | PASS | PASS | PASS |
| W4 Paid, partial coverage | PASS | PASS | PASS | PASS |
| W5 Paid, nothing fits / unavailable | PASS | PASS | PASS | PASS |
| W6 Save, then Confirm and Run at once (console, real profile, real dry run) | PASS | PASS | PASS | PASS |
| W7 Unsaved-edits guard (stay, discard, save, revert, keyboard, phone) | PASS | PASS | PASS | PASS † |
| W8 Every ending, before and after a web restart | PASS | PASS | PASS | PASS |
| W9 No raw diagnostics for a visitor; console keeps its notes | PASS | PASS | PASS | PASS |
| W10 Results: tabs, filter, export, negative score, recommendations, "jobs found" | PASS | PASS | PASS | PASS |
| H Operator header on a free sweep | PASS | PASS | PASS | PASS |
| **Checks** | **11/11** | **11/11** | **11/11** | **11/11** |
| Uncaught script errors / console errors | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |

† passed through an engine-difference branch (below).

Engine differences, recorded with the results and never silent: WebKit keeps no `Secure` cookie that plain http on loopback sets, so W1
and W2 run there with the harness serving the session cookie without `Secure` (production is https; the application is unchanged);
Safari/WebKit reach buttons and links with Option+Tab, so W7's keyboard steps press Alt+Tab there. The browser's own `beforeunload` prompt
cannot always be driven under automation; the script's side of it is pinned by `dirty_test.js`.

W6 is proved not vacuous: on a copy of the tree with only `config.py` and `make_profile.py` put back to `36bc56f` it fails (the price stays
at the first save's, 1.87 four times); on the fixed tree it passes (1.87, 3.74, 1.87, 3.74).

## 6. At-rest regression (what else moved)

104 captures (52 states at 1440 and 390) from the parent `36bc56f` (exported) and from this tree, same harness, same hour, animations off both
sides: **38 of 104 identical, the other 66 differing only where D7C changed something (below)**. The differences are exactly the ones D7C made and nothing else:

- Results (every Results state, public and operator): the heading and the two outlined Filter and sort / Export buttons (the page is 7 px
  taller at 1440 and about 52 px at 390), and the empty/no-match headings.
- The operator console's Running header: the figure of $0.00 is chalk, not amber.
- The public Review (three states): the "Technical notes on how this was read" block is gone.
- Everything else, including Upload, Configure, Key, Confirm, Progress, is pixel-identical. One state (`progress-paid-one-some-d`) differed
  in the first capture and not in a recapture of either side (a frame caught mid-transition); both captures are kept in
  `regression-before/` and `regression-before-first-capture/`.

## 7. Security and privacy

- A synthetic-marker search (`test_security_sweep.py`) puts distinct markers into every place a secret or internal could come from (paths,
  tokens, stack traces, the worker token, the key, notes, filenames) and searches every public route's HTML and headers: none appears. A
  second browser gets nothing of the first's; the visitor's key is never echoed; engine rows and visitor fields come out escaped; an Apply
  link that is not http(s) is never a link; an upload leaves nothing on disk after the read. The same markers are searched in the page
  text, markup and served files in a real browser (W9).
- The operator's console keeps its notes, escaped; a hostile string is text there.
- The unsaved-edits dialog is static markup; the script reads no value out of the page that it then writes back as HTML.
- No real provider or model call: tests run with credentials empty; the browser harness has no key, no model and refuses sockets.

## 8. Known limitations

- **Restarted paid run.** After a web restart a paid run's plan is gone with the memory that held it, so its screens are the free ones
  and cannot say "every search ran" (an `incomplete` run reads as "stopped early" after a restart). They no longer claim "Nothing was
  charged". Recovering the plan from the worker is a worker change and is left for the owner.
- **Two environment-dependent errors** in `auto-apply/tests/test_inference.py` (`healthz` returns 503 when no model runtime is reachable).
  They are identical on the parent and pass with the probe stubbed; they are not related to this work.
- WebKit was run through Playwright (26.5); Safari.app 26.6.2 was not automated (see the manual checklist below).
- The `did not run` legend on the Running screen is shown whenever a sweep is not running, including an `incomplete` one where nothing
  did not run. It is existing D5/D7B behaviour (frozen) and harmless.
- Firefox and WebKit replay the tile colour transition when the closed Searches `<details>` opens, and WebKit does not paint the
  slow-answer dim on the page being left (both from the D7B follow-up; owner questions, unchanged).
- Not covered by anything here: a real Render deploy, a real worker with a real engine and a real provider. That is the prerequisite below.

## 9. Safari (the application) — manual smoke checklist

Needs a person at a Mac. Use the **https** origin (staging or a tunnel): Sweep's session cookie is `Secure`, so plain http will not hold a
session in Safari, and that path is the one the WebKit automation could not cover.

1. Upload one résumé, then three. Review opens; "Save and review next résumé" moves on; the key screen; "Start Free Sweep".
2. Dirty editor (Review): change the years, then (a) press another résumé's **Review** (b) press **All your résumés** (c) press the logo:
   each asks "You have unsaved changes" with **Stay and keep editing** focused. Escape stays. **Discard changes and leave** leaves and the
   change is gone. Change it and put it back: nothing is asked. Change something and press Save: nothing is asked.
3. Same page: close the tab, reload and press Back with an edit: Safari's own prompt appears.
4. Keyboard: Safari's default Tab skips buttons and links. Use Option+Tab (or turn on "Press Tab to highlight each item" in Settings →
   Advanced) and confirm the dialog's two buttons are reachable and Enter activates them.
5. Paid (a synthetic key): Configure over credit shows the real cause (dollars; "can run N of M"; "none … fit"; "temporarily
   unavailable"), never "$0.00 more"; Confirm cannot start a paid sweep that nothing can cover.
6. Running: one run each ending in a failure and a stop (use the harness, or Stop). Headings and banners as in
   `output/design-D7C/shots/w8-*`; after redeploying or restarting the web process the stop is still "You stopped the sweep".
7. Results: the heading reads "N jobs found"; **Filter and sort** and **Export…** are outlined buttons, each opens on its own; a
   negative score shows; Export downloads a CSV that opens (Safari's download prompt) and holds every job.
8. Public Review and `/profile.py`: no "Technical notes", no file paths, no stack trace, no key.
9. iPhone Safari (iOS) if one is at hand: the dialog fits the screen, the buttons are at least 44 px, nothing scrolls sideways, Escape is
   not needed (tap the backdrop to stay).
10. Reduced motion on (System Settings → Accessibility → Display): nothing slides; the ending notices still change at once.

## 10. Deployment prerequisites (when the owner decides to ship)

1. The branch merges into `main` as one reviewed change; nothing here has been merged.
2. **The worker is unchanged** (nothing under `deploy/` is in the diff): the web side reads `stopped`, `failed`, `interrupted`,
   `run_timeout`, `results_ready` and `.done_combos` from status the worker already serves, so there is no deploy-order constraint and no
   new field. `render.yaml` still pins derivation limits to 3/60 (live is 6/150 per the operator): unchanged here.
3. `profiles/` on the console host: nothing to migrate. Existing `.pyc` files are simply no longer read for profiles.
4. A staging smoke of the checklist above on https, one free and one paid run on a real worker with an operator-supplied key, and one
   deliberately failed run.
5. Rollback: redeploy `fdb0da0`. The branch changes no stored data and no wire format, so there is nothing to migrate back.

## 11. Evidence

`output/design-D7C/`: `flows*.json` (one per engine), `shots*/`, `regression-before/`, `regression-after/`,
`regression-before-first-capture/`, `regression.json`. Manifest: `shasum -a 256 -c docs/design/EVIDENCE_MANIFEST_D7C.sha256`. The nine
earlier manifests (D1 to D7B and its engines follow-up, 1,110 files) still verify.
