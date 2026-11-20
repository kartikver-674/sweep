# D7B evidence tooling

What produced `output/design-D7B/`: real-browser checks, real-time recordings, filmstrips and at-rest captures of the **production** application.
Nothing here is served by the application and nothing here is an application dependency. The note is
[../SWEEP_D7B_MOTION_INTEGRATION.md](../SWEEP_D7B_MOTION_INTEGRATION.md).

## What it runs against

- `harness/app.py`: the real Render public app, the real worker app on loopback, the suite's sealed synthetic environment, a stubbed model,
  sockets refused, and an engine child the harness releases (so a Progress state is a real worker state, not a mock of one). No provider, no
  key, no model call, no paid search. It is the D3 to D6 scratch harness (which lived outside the repository) in one file, plus the D7B scenarios.
  Scenarios and the control endpoints (`/__make/<scenario>`, `/__step/<stage>`, `/__ledger/<n>`, `/__rows/<n>`, `/__latency/<path>/<ms>`) are in its docstring.
- `harness/local.py`: the operator console with the suite's own injected fakes, four apps on consecutive ports (Configure at two credit caps, Results, a live Running screen).
- Either can serve another tree (an export of the parent commit): `D7B_REPO=/path/to/export D7B_PORT=5177 .venv/bin/python docs/design/motion-d7b/harness/app.py`.

Playwright is resolved from `PLAYWRIGHT_NODE_MODULES`, else from the Codex runtime already on this machine. Nothing in the repository is installed.

## Run

    .venv/bin/python docs/design/motion-d7b/harness/app.py &      # port 5077 (D7B_PORT)
    .venv/bin/python docs/design/motion-d7b/harness/local.py &    # ports 5078 to 5081
    export D7B_ATTACH=1                                          # the scripts use the servers above instead of starting their own
    node docs/design/motion-d7b/harness/verify-results.mjs       # R1 to R14
    node docs/design/motion-d7b/harness/verify-progress.mjs      # P1 to P9
    node docs/design/motion-d7b/harness/verify-forms.mjs         # F1 to F10
    node docs/design/motion-d7b/harness/record.mjs               # 22 clips, real time (start the servers without D7B_ATTACH)
    node docs/design/motion-d7b/harness/make-sheets.mjs          # filmstrips from the clips
    # at rest, before and after (an export of the parent: git archive 7b1ea25 | tar -x -C /tmp/d7b-before)
    node docs/design/motion-d7b/harness/regress.mjs --side before --repo /tmp/d7b-before
    node docs/design/motion-d7b/harness/regress.mjs --side after
    node docs/design/motion-d7b/harness/regress.mjs --compare
    node docs/design/motion-d7b/harness/make-regression-sheets.mjs

`--channel chrome` runs a script in the installed Google Chrome instead of Playwright's Chromium.

## Firefox, WebKit, and the four-engine pass

Run on Chromium, Chrome, Firefox 153.0 and WebKit 26.5 (the note's section 11). Install the browsers with **the Playwright the harness loads**, so the builds match its protocol (`firefox-1538`, `webkit-2336` for Playwright 1.62.1),
into `~/Library/Caches/ms-playwright`, outside the repository:

    node ~/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/cli.js install chromium firefox webkit

(A bare `npx playwright install` uses whichever Playwright npm resolves, which may be a newer one with other builds, and can remove the builds this one needs.) Then, one engine after another (they share ports 5077 to 5081, and
timing checks should not compete with each other), keeping the machine awake (`caffeinate -i`) and the ports clear, with the arguments written out (zsh does not split a variable into arguments):

    node docs/design/motion-d7b/harness/verify-results.mjs  --engine firefox --suffix engines
    node docs/design/motion-d7b/harness/verify-progress.mjs --engine firefox --suffix engines
    node docs/design/motion-d7b/harness/verify-forms.mjs    --engine firefox --suffix engines     # and webkit; chromium; chromium --channel chrome
    node docs/design/motion-d7b/harness/engine-summary.mjs                                        # the table in the note, from those files

`--suffix NAME` writes `verify-<script>-NAME-<engine>.json` so a pass never overwrites an earlier one. A crashed run leaves its server on the port: `lsof -tiTCP:5077-5081 -sTCP:LISTEN` and kill them before the next.

What the harness does for an engine that differs, never silently: a check that passes through an engine-difference branch says so in the run and in its JSON (`engineDifference`), a skip is listed (`skipped`), and every uncaught script error and console error
is listed with the check it came in (`runtime`). R13 (CPU throttling) is Chromium's CDP emulation and is skipped elsewhere; R11b serves the stylesheet with its `@supports (interpolate-size: ...)` condition made unsatisfiable where the engine could animate height, and where it cannot (Firefox, Safari)
the page itself is the fallback. R6 detects whether the engine keeps painting the outgoing page during a navigation (WebKit does not) rather than assuming it. R11c reads each painted frame of a tool switch, with the click made inside the page.

Recordings: `record.mjs --engine firefox|webkit` writes `recordings-<engine>/` and `traces-<engine>/` (Chrome: `recordings-chrome/`), never over Chromium's. They are recorded without the page trace (it made Firefox paint a page before its stylesheet applied),
and Firefox and WebKit run about a second off wall time: read a timing off the checks, never a clip.

## Files

| File | What |
|---|---|
| `harness/lib.mjs` | launch, servers, a visitor in a scenario, the page trace, the cursor overlay, sync flashes, `checker` |
| `harness/contrast.js` | the contrast of every text node on its real composited backdrop and opacity (a group opacity dims the text and its own background together) |
| `harness/verify-results.mjs`, `verify-progress.mjs`, `verify-forms.mjs` | the checks; one JSON each in `output/design-D7B/` |
| `harness/engine-summary.mjs` | the four-engine table, the engine-difference notes and the runtime errors, from those JSONs |
| `harness/record.mjs`, `make-sheets.mjs`, `filmstrip.mjs` | recordings and the real-frame filmstrips cut from them |
| `harness/regress.mjs`, `make-regression-sheets.mjs`, `png.mjs` | the at-rest before and after, the pixel diff, the contact sheets |
