# D7C evidence tooling

What produced `output/design-D7C/`: the final browser flows against the **real** application, in four engines. Nothing here is served by the
application and nothing here is an application dependency. The release candidate it supports is
[../SWEEP_UI_RELEASE_CANDIDATE.md](../SWEEP_UI_RELEASE_CANDIDATE.md); the blockers it closes are in
[../SWEEP_RELEASE_BLOCKERS.md](../SWEEP_RELEASE_BLOCKERS.md).

It reuses the D7B harness (`../motion-d7b/harness/lib.mjs`: engines, `visitor()`, the checker, `D7_OUT`) and adds two servers of its own.

## What it runs against

- `harness/app.py`: the D7B public stack (the real Render app, the real worker app on loopback, the suite's sealed synthetic environment, a
  stubbed model, an engine child the harness releases) plus the states D7C needs: `/__step/incomplete`, `/__step/incomplete_timeout`,
  `/__step/worker_stopped`, `/__step/interrupted`, `/__restart` (the web process forgets every session room, as a redeploy does, while the
  cookie keeps the run id), `/__hostile/<0|1>` (a reading that carries hostile diagnostics), `/__serve_live` (the D6 job set written on the
  tracks of the run a journey just started). `D7C_PLAIN_COOKIE=1` serves the session cookie without `Secure` (see WebKit below).
- `harness/console.py`: the operator console (local mode) with synthetic everything **except** the two things D7C is about, which are real: the
  `profiles/<name>.py` file the console writes and the engine's own `scraper.py --dry-run --json` that reads it. After every write the file's
  modification time is set to one fixed second, so two saves inside one second at the same size is exactly what happens (blocker 1,
  made deterministic). The profile it writes carries a name of its own and is removed when the harness exits.
- No provider, no key, no model call, no paid search, no external network. The only request that leaves the machine is Google Fonts, which the
  pages ask for as they always do.

## Run

    # all flows, one engine (Chromium is the default; --channel chrome runs the installed Google Chrome)
    D7_OUT=output/design-D7C node docs/design/d7c/harness/flows.mjs --engine chromium
    D7_OUT=output/design-D7C node docs/design/d7c/harness/flows.mjs --engine chromium --channel chrome
    D7_OUT=output/design-D7C node docs/design/d7c/harness/flows.mjs --engine firefox
    D7_OUT=output/design-D7C node docs/design/d7c/harness/flows.mjs --engine webkit
    # a subset
    D7_OUT=output/design-D7C node docs/design/d7c/harness/flows.mjs --engine chromium --only W6,W8

| Flow | What it proves |
|---|---|
| W1 | one résumé, free: upload → read → review/save → the free choice → Configure → Running → Results, by pressing the screens' own buttons, 1440 and 390 |
| W2 | three résumés, free: the same through Confirm, ending on Results with a tab for each |
| W3 | paid, fully covered: Configure says nothing is over; Confirm can start |
| W4 | paid, partial coverage: "your connected accounts can run 22 of 120 of these paid searches"; never "$0.00 more" |
| W5 | paid, nothing fits / paid unavailable: said in words, Confirm cannot start a paid search |
| W6 | console: Save then Confirm and Run at once, the profile rewritten inside one second at the same size: the price is the engine's reading of the file just saved, each time |
| W7 | the unsaved-edits guard: nothing asked when clean or put back; Stay/Discard; Escape and backdrop; Save; keyboard; a phone |
| W8 | every ending (paid incomplete, failed, timed out, stopped, the worker's own stop, interrupted, free equivalents, finished), before and after a web restart |
| W9 | no raw diagnostics in anything a visitor can open; the console keeps its notes, escaped |
| W10 | Results: "N jobs found", four tabs, Filter and sort / Export as two outlined buttons, negative score, suggested résumé, export, filter heading |
| H | the operator's header on a free sweep: not amber, nothing about credit |

Each run writes `output/design-D7C/flows.json` (Chromium) or `flows-<chrome|firefox|webkit>.json` (engine, version, pass/total, engine
differences, runtime page and console errors) and the screenshots of the states D7C changed to `output/design-D7C/shots*/`.

## Engine differences, never silent

- **WebKit and `Secure` cookies.** WebKit does not keep a `Secure` cookie that plain http on loopback sets (Chromium and Firefox treat loopback
  as a secure origin). W1 and W2 let the app set the visitor's own session cookie, so for WebKit only the harness serves the same cookie without
  `Secure`. The application is unchanged and production is https. The note is stored with those two results.
- **WebKit and Tab.** Safari/WebKit reach links and buttons with Option+Tab (a plain Tab visits text fields only, a platform setting). W7's
  keyboard steps press Alt+Tab there. The note is stored with the result.
- The browser's own `beforeunload` prompt cannot always be driven under automation; the script's side of it is pinned by
  `sweep/tests/dirty_test.js` and a result says so when an engine raised no dialog.

## At rest, before and after

    git archive 36bc56f | tar -x -C /tmp/d7c-before            # the parent: D7B as accepted, exported (no branch, no worktree)
    D7_OUT=output/design-D7C node docs/design/motion-d7b/harness/regress.mjs --side before --repo /tmp/d7c-before
    D7_OUT=output/design-D7C node docs/design/motion-d7b/harness/regress.mjs --side after
    D7_OUT=output/design-D7C node docs/design/motion-d7b/harness/regress.mjs --compare

The expected differences are only the two D7C changed: Results (the heading and the Filter/Export buttons) and the operator console's
header on a free sweep. Everything else is pixel-identical.

## Proving a flow is not vacuous

W6 on a copy of the tree with only `config.py` and `auto-apply/make_profile.py` put back to `36bc56f`: the price stays at the first save's
(1.87, 1.87, 1.87, 1.87). `D7B_REPO=<that tree> node docs/design/d7c/harness/flows.mjs --only W6` (the harness reads the tree it is pointed at).
