# Visual evidence manifest

The before-redesign screenshots live in git-ignored, local-only directories (synthetic data only,
so they are not committed). This manifest records their SHA-256 so that any later comparison can
prove the "before" side was not overwritten. Verify from the repository root:

    shasum -a 256 -c docs/design/EVIDENCE_MANIFEST.sha256

- `output/design-audit/` — the D1 audit set, captured at `fdb0da0` (desktop 1440, mobile 390). **Never overwrite.**
- `output/a11y-audit/before/` — the D2 baseline set at `fdb0da0` (adds the local operator-mode applied/opened rows, the arrival feed, control-boundary and target-size measurements in `measure.json`). **Never overwrite.**
- `output/a11y-audit/after/`, `compare/`, `contact-sheet.png` — the D2 result; these are comparisons, not baselines.

Every redesign phase writes its screenshots to its own new directory (for example `output/d3-shared-rules/`)
and compares against the two baseline directories above.

D3 (`output/design-D3/`, written by the unified-review phase):

- `output/design-D3/before-075afdf/` — this phase's own "before", captured at `075afdf` before any D3 edit, including review states D1 never reached (reviewed, failed, limited, reading beside a reviewed row). Read-only, and listed in `EVIDENCE_MANIFEST_D3.sha256`; verify the same way:

      shasum -a 256 -c docs/design/EVIDENCE_MANIFEST_D3.sha256

- `after/`, `regression/`, `prototype/`, `compare/`, `contact-sheet*.png`, `a11y.json` — the D3 result; comparisons, not baselines.

D4 (`output/design-D4/`, written by the upload, résumé-management and search-preferences phase):

- `output/design-D4/before-4061b1e/` and `output/design-D4/regression-before/` — this phase's own "before", captured from the D3 commit (`4061b1e`) before any D4 edit: every required Upload, list and Preferences state, and the screens D4 did not redesign but which share the stylesheet. Read-only, and listed in `EVIDENCE_MANIFEST_D4.sha256`; verify the same way:

      shasum -a 256 -c docs/design/EVIDENCE_MANIFEST_D4.sha256

- `after/`, `regression-after/`, `compare/`, `contact-sheet-*.png`, `flows/`, `a11y.json` — the D4 result; comparisons, not baselines. The D1, D2 and D3 sets still verify against their own manifests.

D5 (`output/design-D5/`, written by the Confirm and Progress phase):

- `output/design-D5/before-78702ff/` and `output/design-D5/regression-before/` — this phase's own "before", captured from the D4.2 commit (`78702ff`) before any D5 edit: every Confirm state (free, paid, over credit with partial offered and consented, nothing coverable, paid unavailable, a refused submit; one résumé and three), every Progress state a controlled worker can reach (queued, starting, working, most done, all paid searches done and the free sources running, finished, empty, failed, stopped, timed out, part-run, refused start; free and paid, one résumé and three), the operator-console versions of both, and the screens D5 did not redesign but which share the stylesheet. Read-only, and listed in `EVIDENCE_MANIFEST_D5.sha256`; verify the same way:

      shasum -a 256 -c docs/design/EVIDENCE_MANIFEST_D5.sha256

- `after/`, `regression-after/`, `compare/`, `contact-sheet-*.png`, `flows/`, `a11y.json` — the D5 result; comparisons, not baselines. The D1 to D4 sets still verify against their own manifests.
- The worker behind these captures is the real worker app on loopback with its engine child replaced by one the harness releases (so a state is a real worker state, not a mock of one); its queue position, finished-search ledger, rows and authorization record are files the worker already serves. The harness lives outside the repository.

D5.1 (`output/design-D5.1/`, written by the free-sweep terminal-state correction):

- `output/design-D5.1/before/` — captured from the D5 commit (`38de117`, exported to a scratch tree) before any D5.1 edit: a free sweep that the worker reported as failed, timed out, or that the visitor stopped, one résumé and three, public and operator console, plus the paid and finished states the fix must leave alone. Every free ending is the false "Your jobs are ready". Read-only, and listed in `EVIDENCE_MANIFEST_D5_1.sha256`; verify the same way:

      shasum -a 256 -c docs/design/EVIDENCE_MANIFEST_D5_1.sha256

- `after/`, `compare/`, `contact-sheet-*.png`, `flows/`, `flows.log` — the D5.1 result; comparisons, not baselines. `flows.log` is a live smoke of a free sweep the page is watching, ending four ways, schema 1 and schema 2, 1440 and 390 (84 checks, all pass). Unchanged states differ from `before/` only by capture noise (a 1px entrance-animation offset with identical text) and, deliberately, the paid timeout banner. The D1 to D5 sets still verify against their own manifests.

D6 (`output/design-D6/`, written by the live Results phase):

- `output/design-D6/before-75130e0/` — this phase's own "before", captured from the D5.1 commit (`75130e0`, exported to a scratch tree) before any D6 edit: the live Results for one résumé and for three (All Jobs, each résumé's view), with filters open, with Export open (then inside Filter and sort), with long labels and titles, with no pay or experience stated, with no recommendation, empty, a résumé with no jobs, a filter that matches nothing, a search that failed part-way, and the operator console's versions including Applied and Opened rows. Read-only, and listed in `EVIDENCE_MANIFEST_D6.sha256`; verify the same way:

      shasum -a 256 -c docs/design/EVIDENCE_MANIFEST_D6.sha256

- `after/`, `flows/`, `flows.log`, `a11y.json`, `contact-sheet-*.png`, `recommendation-states-*.png`, `compare-prototype-*.png`, `prototype/` — the D6 result; comparisons, not baselines. `prototype/` is the approved D3 static Results page as it rendered at `75130e0`, for comparing the live page with what was approved.
- `regression-before/` and `regression-after/` — Upload, Review, Configure, Key, Confirm and Progress states that share the stylesheet, before and after. Every one is pixel-identical at 1440 and 390 except two animation frames (an indeterminate bar and an activity dot). Capture both sides at the same hour: a paid Confirm screen adds a clock warning ("It is late in the day…") in the evening, which once read as a difference.
- Data: synthetic, engine-shaped rows served through the real Render app and the real worker on loopback (and the operator console's injected fakes); Apply links are intercepted, so nothing leaves the machine. The harness lives outside the repository.

D7A (`output/design-D7A/`, written by the motion-direction phase; the application is unchanged, so this phase has no "before" of its own):

- `recordings/` (12 real-time WebM clips: the proposal, the shipped page as the comparison, reduced motion, a slow server, the view-transition alternative and the GSAP spike, at 1440 and 390), `frames/` (23 filmstrips of real frames cut from those clips at 25 fps), `traces/` (each clip's steps, click times and the measured clock offset between trace and video), `verify.json`, `verify-gsap.json`, `perf-throttle.json` and `disclosure-lab.json`. These are the evidence the note reviewed, fixed as reviewed:

      shasum -a 256 -c docs/design/EVIDENCE_MANIFEST_D7A.sha256

- `scratch/` (logs and working frames) is not part of the evidence. Data: synthetic, engine-shaped rows rendered by the real `results.html` through the worker-backed test harness on loopback; Apply links are intercepted; the only external request is to Google Fonts, cached before each take. The D1 to D6 sets and manifests are untouched and still verify.

D7B (`output/design-D7B/`, written by the motion-integration phase; "before" is an export of the parent commit `7b1ea25`, which is the D6 application):

- `recordings/` (22 real-time WebM clips of the **production** application at 1440 and 390: Results, a slow server, reduced motion, a 240-job list, Progress success and failure, the price, over the credit, Upload, and the operator console), `frames/` (34 filmstrips of real frames cut from them at 25 fps), `traces/` (each clip's steps, presses, the harness's own calls and the moments the page was seen to land tiles or show an ending, with the clock offset between trace and video), `verify-results.json`, `verify-progress.json`, `verify-forms.json` and their `-chrome` variants (38 browser checks each, Chromium 151 and Chrome 154), `regression-before/` and `regression-after/` (52 states at 1440 and 390, 104 captures each, from the parent commit and from this tree, same harness, animations taken off both), `regression.json` (104 of 104 identical), `regression-anchors.json` (the same screens against D6's approved images, by name), and `contact-sheet-regression-*.png` and `contact-sheet-before-after-*.png`:

      shasum -a 256 -c docs/design/EVIDENCE_MANIFEST_D7B.sha256

- Data: synthetic, engine-shaped rows served through the real Render app and the real worker on loopback (and the operator console's injected fakes), by `docs/design/motion-d7b/harness/` (in the repository this time). No provider, model or paid call; Apply links are intercepted; the only external request is to Google Fonts, cached before each take. Firefox and Safari/WebKit were not run (no engine installed). The D1 to D7A sets and manifests are untouched and still verify.

D7B follow-up (Firefox and WebKit; `output/design-D7B/`, written after the owner approved the motion):

- `verify-{results,progress,forms}-engines-{chromium,chrome,firefox,webkit}.json` (the same checks on Chromium 151.0.7922.34, Chrome 154.0.8037.58, **Firefox 153.0** and **WebKit 26.5**, Playwright 1.62.1; each JSON carries its engine-difference reasons, skips, environment and the runtime errors it saw), `engines-summary.md` (the table, from those files),
  `recordings-{firefox,webkit,chrome}/` with `traces-*` and `frames-*` (Firefox and WebKit clips of the owner's checklist, and the Chrome reduced-motion clips recaptured after the fix), and three folders that keep what the first attempts showed instead of replacing it: `engines-first-pass/` (the first Firefox and WebKit runs, before the harness was corrected),
  `engines-first-attempts/` (a Firefox R2 failure that did not reproduce; the first forms runs) and `engines-prefix-proof/` (R11c failing on the old tree in three engines). Safari.app 26.6.2 was not run.

      shasum -a 256 -c docs/design/EVIDENCE_MANIFEST_D7B_ENGINES.sha256

- Same data and harness as D7B. The first-pass D7B evidence above is untouched.

D7C (`output/design-D7C/`, written by the final release-hardening phase; "before" is an export of the parent commit `36bc56f`, which is D7B as accepted):

- `flows.json`, `flows-chrome.json`, `flows-firefox.json`, `flows-webkit.json` (the eleven browser flows W1 to W10 and H on Chromium 151.0.7922.34, Google Chrome 154.0.8037.58, **Firefox 153.0** and **WebKit 26.5**, Playwright 1.62.1; 11 of 11 in each, with the WebKit engine-difference notes stored in the file), `shots/`, `shots-chrome/`, `shots-firefox/`, `shots-webkit/` (the states D7C changed: the unsaved-edits dialog at 1440 and 390, the corrected over-credit Configure and Confirm copy, the public Review with no technical notes and the console's with them, "N jobs found" and the outlined Filter and sort / Export buttons, a paid run whose every search ran and then failed, the worker's own stop and a failure after a web restart, the operator's header on a free sweep),
  `regression-before/` and `regression-after/` (52 states at 1440 and 390, 104 captures each, from `36bc56f` and from this tree, same harness, animations off both), `regression.json` (38 of 104 identical; the other 66 differ only in Results, the console's Running header and the public Review's removed notes block) and `regression-before-first-capture/` (the one "before" frame, `progress-paid-one-some-d`, that differed in the first capture and not in a recapture of either side; both kept):

      shasum -a 256 -c docs/design/EVIDENCE_MANIFEST_D7C.sha256

- Data: synthetic, engine-shaped rows served through the real Render app and the real worker on loopback, and the operator console with its real profile writes and real engine dry run, by `docs/design/d7c/harness/` (see its README). No provider, model or paid call. The D1 to D7B sets and manifests are untouched and still verify (1,110 files).

