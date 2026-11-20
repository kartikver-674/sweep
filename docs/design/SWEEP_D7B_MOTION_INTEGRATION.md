# Sweep design, phase D7B: production motion integration

Branch `design/sweep-ui-overhaul`, starting at `7b1ea25` (D7A, approved by the owner). D7A chose the direction and proved it on a
prototype; this phase puts the approved motion into the application. It is not another exploration: no new visual direction, no
animation library, no build step, no framework, no dependency. The principle is the one the owner approved, **"Motion says what
changed and nothing else"**, and the interface stays Quiet Ledger. The direction and its argument are in
[SWEEP_D7_MOTION_DIRECTION.md](SWEEP_D7_MOTION_DIRECTION.md); this note records what was built, what was removed, what differs
from D7A and why, and what was measured. Nothing was pushed, merged or deployed, `main` and `origin/main` are untouched (`fdb0da0`),
and no provider, model or paid-search call was made: every capture is the real application served over loopback with synthetic data.

Evidence is in `output/design-D7B/` (git-ignored; listed and hashed in `EVIDENCE_MANIFEST_D7B.sha256`). The tooling that produced it
is in [`motion-d7b/`](motion-d7b/README.md) and runs against the real Render app and worker (`harness/app.py`) and the operator console
(`harness/local.py`).

**Follow-up pass (Firefox and WebKit).** The owner approved the motion as built and asked for the same checks on Firefox and WebKit. They are in section 11, with one fix (section 7, item 16), the engine differences they showed, and the mistakes in
my own harness they exposed. Nothing in the motion design changed.

## 0. The result in one page

| Question | Answer |
|---|---|
| What changed in the application? | `sweep.css` (the Motion section rewritten, and small edits where the old motion lived), `results.html`, `running.html`, `configure.html`, `base.html`; **`motion.js` deleted**. No route, worker, price, score, export or poll was touched. `reading.js`, `price.js` and `pick.js` are unchanged |
| What moves now? | Five verbs: **press** (unchanged), **write in** (Results arrival, an accepted file, a new listing, a finished search), **dim** (a slow Results answer, a pending price), **open** (tool panels, the location menu, the feedback dialog), **mark** (a Progress ending). Everything else is an instant, complete state change |
| What was deleted? | Section 4: the money count-up, the spend-rail draw and cap tick, the cap shake and overshoot, the waiting-screen rise, **the tile scale and its column ripple** (a finished search is now a colour change), the Results section entrance that replayed on every load and the feed's slide; and shortened: the 1.2 s pause (now 400 ms from the ending being painted), the feed's colour step and the determinate bar (500 and 450 ms to 160) |
| Does a large list make the entrance longer? | No. Eight rows animate on 19 jobs and on 240, desktop or phone (three on a phone); the write-in lasts 273 ms against 268 ms (desktop) and 174 ms against 165 ms (phone), and never more than 400 ms at 1x, 4x or 6x CPU slowdown (R2, R13) |
| Is at-rest output unchanged? | **Yes: all 104 captures (52 states at 1440 and 390) are pixel-identical** to the parent commit, public and operator console (section 12) |
| Checks | **38 of 38** browser checks on Chromium 151 and on Google Chrome 154 (the same 38 again after the follow-up fix below); **37 of 37** on Firefox 153.0 and on WebKit 26.5, each with R13 skipped and listed (CPU throttling exists only in Chromium; its unthrottled half is R2); **1,110 focused unit tests** pass; every earlier evidence manifest (717 files) still verifies |
| What was not verified? | **The Safari application.** Safari 26.6.2 is installed here, its automation is off and I did not change that setting. Playwright's WebKit 26.5 is the engine, not the app, and says so wherever it is quoted. Firefox and WebKit were run in a follow-up pass, after the owner approved the motion (section 11) |
| What did Firefox and WebKit change? | **One CSS rule.** Switching Filter and sort for Export showed both panels for one or two painted frames wherever the height is not animated (reduced motion, Firefox, Safari, Chrome with the animation forced off): the list stood a panel lower and then went straight back up. A leaving panel now goes at once there (section 7, item 16). Everything else the two engines found is an engine difference, or a mistake in my harness, and each is listed in section 11 |
| What changed from D7A? | Sixteen things, each measured or reviewed (section 7). The ones that matter most: **the .85 dim is AA on the page ground but not on `--surface`** (D7A's table was computed on the ground only), so a dimmed region also lifts its muted tone; **the 400 ms is now counted from the ending being painted**, not from the state being set; and **a tile or a listing that is already there when a page loads no longer animates**, and a finished search no longer scales |
| What do I need from the owner? | Play the clips in section 13, and answer the questions in section 17 |

## 1. The owner's decisions, and where each one is

| # | Decision | Implemented as | Pinned and measured by |
|---|---|---|---|
| A | The money counter is deleted; the newest price is written directly; the pending treatment stays | `motion.js` and `sweepCount` removed; the meter's figure is `x-text="'$' + est.total.toFixed(2)"`; `.updating` dims at `--pending-dim` | `test_motion`: a figure is written not counted; **F1**, **F3**: every write to the figure equals an `/estimate` answer |
| B | No shake, no overshoot on crossing a cap: the words and a ~160 ms colour | The `cap-cross-*` keyframes are gone; `.meter-fill`, `.numeral` and `.headline-figure` transition colour over `--ms-2` | **F2**, **F4**: every transform is `none` on every frame, only transitions run |
| C | Completion to Results about 400 ms | Both redirect branches in `running.html` use 400 | unit; **P3** (424 ms on a desktop and 427 ms on a phone from the ending being painted to the page leaving; 449 ms in Chrome 154), **F9** (operator console, 425 ms) |
| D | A quick tab, filter, sort, Show all is an instant swap; no view transition, no crossfade | No rule runs on a plain load; no `@view-transition` | **R4**: no animation, no transition on the list, no class on `<html>` |
| E | Tool panels open in place where the browser can; otherwise opacity or an immediate open, same focus and layout | `@supports (interpolate-size: allow-keywords)` carries height and the row gap; the base rules are opacity only | **R11**, **R11b** |
| F | `--pending-dim: .85`, never .7 or .5; muted text stays AA while waiting | The token; Configure's `.updating` moved from .5 to it; `--pending-slate` keeps the muted tone AA (section 7.1) | **R6c**, **F1**, **F3**: every text node AA on its real backdrop, worst 4.57 |
| G | Capped write-in: first 8 rows on a desktop, 3 on a phone, 140 ms, 20 ms apart; only on a genuine arrival | `html.arrive` from the head script; nth-child rules | **R2**, **R3**, **R4** |
| H | Operator: the rail draw and cap tick deleted; the meter's real value transition at about 160 ms | Both deleted with the `first-paint` script; `.meter-fill` width and colour at `--ms-2` | **F9** (no rail, no tick at load), **F1**, **F2** |
| I | No Review status mark | `reading.js` and `reading_test.js` untouched | `git diff --stat` |
| J | No GSAP, no WAAPI, no dependency | CSS, existing Alpine `x-transition`, two class-toggling scripts | no new file in `static/`, one deleted |
| K | A real reduced-motion alternative | Every animation and transition this phase added is inside `no-preference`; states are outside it | **R5**, **F7**, **P6** |

## 2. The motion that ships

Every effect is one of the five verbs. `Reduced` is what a reader with `prefers-reduced-motion: reduce` gets.

### Upload

| Effect | Verb | Mechanism and timing | Reduced | Checks |
|---|---|---|---|---|
| An accepted file | write in | `.picked-row`, `write-in` (opacity) 160 ms. The list is keyed, so only the new row is new; the single-file path animates as the row is shown | none; the row is there | F6 |
| A file held over the drop zone | press | `.drop` border and background 120 ms; the glyph colour 120 ms | instant | F6 |
| Removing a file, an error message | none | answers the press; `role="alert"` is never faded | same | F6 |

### Configure and Confirm

| Effect | Verb | Mechanism and timing | Reduced | Checks |
|---|---|---|---|---|
| A price being re-checked | dim | `.updating` on the headline figure, the cost table and the console meter: opacity `.85`, transitioned 160 ms; bound to `stale`, so from the change to the newest answer | `.85` at once | F1, F3 |
| The new price | none | written once, when the answer arrives; it equals the answer | same | F1, F3 |
| The meter's fill | mark of a real value | width and colour 160 ms (was 350 ms) | instant | F1, F2 |
| Crossing the credit or cap | state | colour of the figure, the box and the fill 160 ms, plus the words that were already there; no shake, no scale | instant | F2, F4 |
| The location menu | open | `x-transition` opacity 120 ms in, instant out | instant | F5 |
| Saving, re-pricing words | none | the existing liveness pulse only | same | unit |
| Confirm on load | none | nothing is drawn or counted; the over-cap state is simply shown | same | F8 |

### Progress

| Effect | Verb | Mechanism and timing | Reduced | Checks |
|---|---|---|---|---|
| Running (liveness) | existing | the pulse, the indeterminate bar, the determinate bar only where the server gave a fraction | existing end states | P7 |
| An ending | mark | `x-transition:enter` opacity 160 ms on the six ending banners, only when `p.state` changes to it; never faded out; a page opened in an ended state shows it as it is | full strength at once | P3, P4, P5, P6 |
| A finished search | mark | the cell changes colour (amber or teal) over 160 ms, all together, no column delay, no scale. A colour transition needs a change, so a cell already done when the page loads is simply done, and a panel opened later shows what is there | instant | P1, P2, P2b |
| A new listing | write in | `.feed li.fresh` children, 160 ms opacity, no slide; only a listing that arrived after the page did | none | P2 |
| The determinate bar | real value | width 160 ms (was 450 ms) | instant | P7 |
| The wait for Results | none | 400 ms (was 1,200), **counted from the ending being painted** (Alpine's draw, then the second frame), with a one-second fallback for a tab that draws no frames; no state is shown complete before `p.state` says so | same | P3, F9 |

### Results

| Effect | Verb | Mechanism and timing | Reduced | Checks |
|---|---|---|---|---|
| Arriving from another stage | write in | `html.arrive`, set before first paint by a head script and removed 500 ms after the first frame; the first 8 rows of the first section (3 on a phone), `write-in` 140 ms, 20 ms apart | rows are simply there | R2, R3, R12 |
| A quick tab, filter, sort, Show all, Clear, reload, back | none | an instant swap: no class, no rule, no transition | same | R4 |
| A slow answer | dim | after 160 ms of waiting `html.pending` dims the list (not the heading, tabs or tools) to `.85`; the new page starts at `.85` and settles in 160 ms | the dim at once, no settle | R5, R6, R6c, R7, R8 |
| Filter and sort, Export | open | height, the row gap and opacity together, 200 ms in and 140 ms out, where `interpolate-size` exists; opacity in and instant out elsewhere. When one tool replaces the other, both move on the opening curve and duration, so the list under them moves one way | at once, complete | R11, R11b, R11c, R5 |
| Apply, Opened, Applied | none | the reader is in another tab | same | R3 |

### Shell

| Effect | Verb | Mechanism and timing | Reduced | Checks |
|---|---|---|---|---|
| The feedback dialog | open | `dialog.feedback[open]` and its backdrop fade in together over 160 ms with `@starting-style`; native `showModal`, focus and Escape are untouched; closing is not animated | at once | R14 |
| The tracker, step changes, the run strip repaint | none | navigations and polls never animate | same | unit |

## 3. Prototype to production

| D7A prototype | Production |
|---|---|
| `motion-proposed.css`, 36 lines, loaded after `sweep.css` | The Motion section of `sweep.css`, which replaces the old one (97 lines). The layer's tokens, `write-in` (was `row-in`), `list-in`, `.swap`, `.pending`, `.t-*` and the arrival rules are carried over; `@supports` now gates the height rules |
| A 15-line head script in the fixture's `<head>` | `{% block head %}` in `base.html`, filled by `results.html`; `data-motion="arrive"` |
| A 22-line script at the end of the fixture | the end of `results.html`; `data-motion="pending"` |
| A wrapper `<div id="results-body" class="stack results-body">` | the same, in the template, and not drawn when a run has no jobs |
| `x-transition` on the two panels | the same six attributes, after `x-show` and its `style` |
| `harness/verify.mjs` (T1 to T15) | `motion-d7b/harness/verify-results.mjs` (R1 to R14), now against the real pages |
| `motion-gsap-spike`, `motion-vt-alt` | not carried over; D7A's evidence keeps them |

## 4. What was removed

| Effect | Where it was | What replaced it | Pinned absent by |
|---|---|---|---|
| The money count-up | `motion.js` (75 lines), `x-effect="sweepCount"` in `configure.html`, its `<script>` in `base.html`, `motion_test.js` | `x-text` on the authoritative estimate | `test_motion` (no `sweepCount`; no `requestAnimationFrame` in any file under `static/`; the file is gone) |
| Spend rail drawn from zero, cap tick | `.first-paint`, `rail-draw`, `cap-drop`, a `sessionStorage` script in `base.html` | nothing | `test_nothing_enters_from_zero_on_load`, F9 |
| Cap overshoot and 500 ms shake | `cap-cross-fill`, `cap-cross-shake` on `.meter.over` | colour transition and the words | `test_there_is_no_shake_and_no_overshoot`, F2 |
| Waiting-screen rise | `@keyframes rise`, `.working { animation }` | nothing | `test_the_waiting_screen_has_no_entrance…` |
| Tile scale and column ripple | `tile-land` (scale .82 to 1), seven `nth-child(8n + k)` delays, and it replayed on every load | the cell's colour change, 160 ms | `test_a_finished_search_is_a_colour_not_a_landing`, `test_only_the_indeterminate_bar_moves_anything`, P1, P2, P2b |
| Results section entrance on every load | `.reveal`, `.reveal.r2/.r3`, `section-in`, `class="… reveal r1"` | the capped arrival | `test_what_was_deleted_stays_deleted`, R4 |
| The feed's 8 px slide and 500 ms | `arrive`, `.feed li > * { animation }` | `write-in` 160 ms, only when new | `test_the_feed_writes_in_only_what_arrived…`, P2 |
| Feed colour step-down at 500 ms, determinate bar at 450 ms | `.feed b`, `.activity-fill` transitions | 160 ms | unit |
| A price dim at `.5` and 120 ms | `.updating { opacity: .5 }` | `--pending-dim` | `test_the_dim_is_not_seventy_or_fifty_anywhere` |
| 1,200 ms before Results | two `setTimeout`s in `running.html` | `leave()`: 400 from the ending being painted | unit, P3, F9 |

Obsolete names were searched for after the change (`rail-draw`, `cap-drop`, `cap-cross`, `section-in`, `first-paint`, `sweep.drawn`,
`sweepCount`, `motion.js`, `@keyframes rise`, `@keyframes arrive`, `.reveal`): none remains in `sweep/`; the tests above keep it so. They
appear only in the D1 to D7A documents, which record history.

## 5. Tokens

| Layer | Token | Value | Used by |
|---|---|---|---|
| Primitive | `--ms-1` | 120 ms | press tier: buttons, the drop zone, the location menu |
| Primitive | `--ms-2` | 160 ms | a dim, a mark, a figure's colour, a finished search, the meter, the feed, an accepted file, the dialog |
| Primitive | `--ms-3` | 200 ms | a panel opening (`--tool-in`) |
| Primitive | `--ease-settle` | `cubic-bezier(.22, .61, .36, 1)` | every arrival |
| Primitive | `--ease-leave` | `cubic-bezier(.4, 0, 1, 1)` | a panel closing |
| Meaning | `--row-fade`, `--row-step` | 140 ms, 20 ms | one row, and the step; eight rows is 140 + 7 x 20 = 280 ms |
| Meaning | `--tool-in`, `--tool-out` | `var(--ms-3)`, 140 ms | a panel opening, and leaving |
| Meaning | `--pending-dim` | `.85` | the wait, everywhere |
| Meaning | `--pending-slate` | `#aa9885` | the muted tone inside a dimmed region only (7.1) |

`--ms-1` is new (D7A had a literal 120 ms); the button press now uses it. Every token is used, and a test says so.

## 6. How it behaves

- **Results arrival.** From the Running screen, a step, a link: the heading, tabs and tools are there on the first frame; the first eight rows
  (three on a phone) write in over 280 ms designed, 273 measured on 19 jobs and 268 on 240 (desktop), 174 and 165 on a phone. A first section
  with fewer rows animates fewer (a run with five jobs animates five); nothing else is invented. A typed address, a bookmark, a reload and
  back or forward are not arrivals.
- **Quick navigation.** An instant swap: time to readable is 14 ms after the first painted frame on a desktop and 15 ms on a phone (R12).
- **Slow navigation.** At 60 ms nothing has happened; from about 160 ms the list is dimmed (at 200 ms the transition is part-way, at 320 ms it
  is `.85`); the heading, tabs and tools stay at 1. The new page starts at `.85` and settles in 160 ms, plays no row entrance, and is clean.
  A second press while it is dimmed keeps it dimmed, with the give-up clock restarted.
- **Configure price.** The old figure stays, at `.85`, with every text node AA, until the newest answer; then the new figure is written once.
  A fast answer is a hint of a dip (the lowest opacity seen was .975 to .98).
- **Progress ending.** Nothing is visible or fading before the server says so; the ending fades in over 160 ms with its words already in
  place; the page leaves for Results 400 ms after the ending is first painted (424 to 449 ms measured: the timer plus the navigation starting);
  Results arrives with the capped write-in. A finished search is the cell changing colour over 160 ms, all together; one that is done when the page
  loads is simply done.
- **Reduced motion.** No class is added, no animation or transition runs on any frame (R5, F7, P6), a panel opens at once and complete, the dim
  is drawn at once, and the ending is at full strength the moment it is shown.

## 7. What differs from D7A, and why

1. **The AA claim was true only on the ground (7.1).** D7A's table computed muted text on `#03161c`. The same tone on `--surface` (a phone's
   result cards, the Configure panel, the console meter) is 5.18:1 at rest and **4.11:1 at .85**, below AA. The first production run
   measured 74 failing text nodes on a phone. Fix: every dimmed region also sets `--slate: var(--pending-slate)`, a tone a fifth of the way
   to `--warm`, which is 4.61:1 on `--surface` and 5.10:1 on the ground, both dimmed. At rest nothing changes. My first attempt, dimming
   only the figures, was dropped: it left stale rates and counts at full strength, which is the wrong trade.
2. **An arrival needs a same-origin referrer.** The prototype also animated a typed address and a bookmark. The brief says "from another
   product stage", so those are quiet now.
3. **The un-dim flag carries a time.** `sessionStorage` holds `Date.now()`, and the head script honours it for 10 s and only right after
   Results. Otherwise an abandoned dim could turn a real arrival into a settle a minute later.
4. **A second press while dimmed stays dimmed.** The prototype un-dimmed and re-dimmed, a blink the wait did not deserve.
5. **Height is gated by `@supports (interpolate-size: allow-keywords)`.** The prototype set `height: 0` and `margin-top` on the start state
   unconditionally. In a browser without the property that would have animated only the margin (a 12 px slide) while the height snapped.
6. **A tile or a listing that is already there does not animate.** D7A did not look at a reload. Every done tile used to pop at load (with a
   column ripple), and every feed line faded in. Now a listing is marked `.fresh` (for 400 ms) only if it arrived after the page did (the `fed` flag), and a
   tile is a colour transition, which needs a change: only what happens while you watch is shown, and a panel opened later shows what is there.
7. **`motion.js` is deleted outright**, not reduced to a function that only writes the figure. Nothing needed it.
8. **The blanket reduced-motion rule stays.** D7A's plan item D7B-4 proposed replacing it. It is a net under the press and the chevrons, and
   four tests pin it; everything this phase added is opt-in under `no-preference` regardless.
9. **The determinate bar and the feed's colour step were shortened to 160 ms** (were 450 and 500 ms), so the bar is not still moving when the
   page leaves for Results 400 ms after the ending.
10. **The feedback dialog fades in.** Optional in D7A; included, because it is an Open, costs one rule, and focus is on the first field from the
    first frame (R14).
11. **The Running screen's test data changed.** The harness's listings are reachable from India, so Results opens its first section; D5's
    were "Remote" and landed in the collapsed "abroad" group, where nothing is visible to animate.
12. **A finished search no longer scales.** D7A kept the tile landing "as today" (`scale(.82)` to 1). The reviewer's frames showed 106 cells scaling
    at once at the last poll, stacked with the banner fade, the bar and the layout step: a pulse, and the only transform in the product. It is now the
    cell's colour change over 160 ms, which also deleted the JavaScript that marked cells (`data-was-done`, an `x-init`, an `x-effect`, a timer) and the
    replay on opening the "Searches" panel. **This is a deviation from the owner's list, which names the landing as kept; question 2 in section 17.**
13. **The 400 ms is counted from the ending being painted.** The first version started it when the state was set. The reviewer's frames showed the ending
    on screen for about 160 ms of the 400 in the phone clip. **That turned out to be mostly the recorder**: measured on the page's own frame clock, the ending was
    painted 11 to 17 ms after the state was set (30 ms in Chrome 154), so the old timer was nearly right, and the recorder's frames lag the page by up to a few hundred
    milliseconds when a page has just redrawn about 120 tiles. The change is still worth having and cannot make the pause shorter: `leave()` arms the timer from the second
    frame after Alpine's draw, so a device that really does paint late still shows the ending for 400 ms, and a second timer, one second after the state, covers a tab that
    draws no frames. P3, F9 and P6 now measure from a painted-frame probe. What a viewer of the clips sees is in the note in section 13.
14. **One tool replacing the other moves the list one way.** Closing in 140 ms on an ease-in while the other opened in 200 ms on an ease-out made the
    list drop and then rise (measured: up 24 px, then down 78 px, with a 20 px step near the end). Both now use the opening duration and curve while
    both are moving (`.bar:has(.t-in):has(.t-out)`): one direction, at most 4 px back. An 8 px step remains at each end, which is one row gap: a flex
    line cannot be shorter than nothing, so `margin-top: -gap` cancels the gap only once the panel is a gap tall. D7A's comment that there is "no pop" was
    not exact, and is corrected in the stylesheet.
15. **The dialog's backdrop fades with it.** The page used to darken at once under a panel that was still arriving.

16. **A leaving tool panel is gone at once where its height is not animating** (found by Firefox and WebKit, in the follow-up pass). When one tool replaces the other, Alpine marks the leaving panel at once, shows the entering one a frame later and keeps the leaving one a frame or two after that. Where the height is animated that overlap is the smooth move. Everywhere else (reduced motion, Firefox, Safari, a browser without `interpolate-size`) the list stood 72 px lower for one or two painted frames and then rose by 128: two frames in Chrome and Firefox, one in WebKit. One rule, `.t-out { display: none; }`, outside `no-preference` (the reader who asked for less needs it most), and `.t-out { display: block; }` inside the `@supports` block that animates the height. Chrome's animated path is unchanged (the same nine and eleven layout shifts, with the same values, before and after). R11c fails on the old tree and passes on the new one in all three engines (section 11.2). A first reading with a `requestAnimationFrame` sampler and a second with `layout-shift` entries both over-counted it (the first sampled before Alpine's callback ran in the same frame, the second was woken by Playwright's mouse events hit-testing a page no frame ever painted); the figures here are from the state read after each frame's rendering, with the click made inside the page.

### 7.1 The numbers behind item 1

| Text | On the ground, at rest | dimmed to .85 | On `--surface`, at rest | dimmed to .85 | With `--pending-slate`, dimmed |
|---|---|---|---|---|---|
| Muted `#9f8e7b` | 5.84 | 4.54 | 5.18 | **4.11** | ground 5.10, well 5.30, surface **4.61**, surface-low 4.78 |
| Warm, chalk, teal, amber, coral | 8.7 to 14.4 | 6.5 to 10.6 | 7.8 to 12.7 | 5.9 to 9.6 | unchanged, all above 5.9 |

Measured in the browser rather than computed (R6c, F1, F3): worst text while waiting is **5.10** (Results, 1440), **4.61** (Results, 390),
**4.57** (Configure, public, both widths) and **4.57** (console meter).

## 8. If something fails

| Failure | Result | Checked by |
|---|---|---|
| JavaScript is off | every row, the heading and the list are fully visible; nothing carries a class; the ending the server rendered is at full strength | R1, P8 |
| The head or body script throws, or `sessionStorage` is blocked | caught; the page is simply there; the dim still works without carrying over | Node test (67 assertions on each of two pages) |
| Alpine does not load | no class hides anything; the panels' `display:none` is server-rendered; an ending is as rendered | R1, P8, unit |
| A number field refuses its input, or a navigation is stopped with Esc, or the network drops | the list is never left dimmed: armed only by a valid `submit` or a same-page link click, given up after 10 s | R7 |
| Back or forward restores a dimmed page from the cache | `pageshow` with `persisted` clears the class and the flag | R6b, Node test |
| An export, Apply, download, fragment, another page or another site | never arms the dim | R7, Node test |
| Focus and scroll | no script of ours calls `focus()` or scrolls; focus stays on the control that was used | R10, Node test, R14 |
| The first section is the collapsed "abroad" group | nothing animates, nothing is invented | R2 |

## 9. Accessibility

Contrast while waiting is in 7.1. Keyboard: Tab reaches Filter and sort with a solid 2 px chalk ring, Enter opens it, Space closes it, focus stays
on the button, and the page's scripts call `focus()` zero times (R10). An alert (`role="alert"`) is fully there on its first frame (F6), the
feedback dialog's first field has focus on the first frame (R14), a heading's words change at once (`aria-live`, P4), and no content is gated on motion
(R1, P8). Nothing overflows horizontally on any frame of any Results view or Progress screen at 1440 or 390 (R9, P9), and the worst layout shift
is 0.0014.

## 10. Performance

No `will-change`, no `transition: all`, no blur, no parallax, no scroll-linked effect, no uncapped stagger; the only loops are the existing
liveness ones. CPU throttling is a Chromium emulation, so it was run in Chromium only. Median of three (R13):

| CPU | List | Animated rows | Write-in (ms) | Worst frame (ms) | Frames over 50 ms |
|---|---|---|---|---|---|
| 1x | 19 | 8 | 273 | 196 | 1 |
| 1x | 240 | 8 | 281 | 180 | 2 |
| 4x | 19 | 8 | 286 | 179 | 2 |
| 4x | 240 | 8 | 390 | 167 | 5 |
| 6x | 19 | 8 | 269 | 188 | 4 |
| 6x | 240 | 8 | 341 | 199 | 7 |

The entrance is 280 ms by design; a throttled engine delivers `animationstart` late and sometimes together, so the bound is the design plus
120 ms, for both lists. The long frames are layout of the list, which is the same with or without the motion.

## 11. Browsers

D7B first ran on Chromium and Chrome only. After the owner approved the motion, Firefox and WebKit were installed outside the repository and the same checks were run on all four engines
after the one fix below. Every figure in this section is read from `output/design-D7B/verify-*-engines-<engine>.json` by `motion-d7b/harness/engine-summary.mjs`
(the table is also `output/design-D7B/engines-summary.md`).

| Engine | Version | Results | Progress | Forms | Checks run | Skipped | Engine-difference branches | Script errors | Console errors |
|---|---|---|---|---|---|---|---|---|---|
| Chromium (Playwright headless shell, `chromium-1234`) | 151.0.7922.34 | 18/18 | 10/10 | 10/10 | **38/38** | none | 0 | 0 | 0 |
| Google Chrome (`channel: chrome`) | 154.0.8037.58 | 18/18 | 10/10 | 10/10 | **38/38** | none | 0 | 0 | 0 |
| Firefox (Playwright `firefox-1538`) | 153.0 | 17/17 | 10/10 | 10/10 | **37/37** | R13 | 3 | 0 | 0 |
| WebKit (Playwright `webkit-2336`, macOS 26 arm64) | 26.5 | 17/17 | 10/10 | 10/10 | **37/37** | R13 | 6 | 0 | 3 (all in R11b, all the harness's) |

Playwright 1.62.1, Node 26.3.0, Darwin 25.6.0 arm64. **Safari.app 26.6.2 is installed and was not run**: Playwright's WebKit is the WebKit engine, not Safari the application (its UI, its
settings, its networking and its release schedule differ), and a headed Playwright WebKit behaved the same as the headless one in the one place they were compared (11.3).
Installation was `node <codex runtime>/playwright/cli.js install firefox webkit` with the Playwright the harness loads (1.62.1), so the builds match its protocol; about 270 MiB in
`~/Library/Caches/ms-playwright` in all, none of it in the repository. (An earlier install from a newer Playwright had left `firefox-1543` and `webkit-2359` there, built for a
different protocol, and had removed the Chromium build; those two are untouched and unused, and `chromium-1234` was reinstalled.)

"Engine-difference branch" is a check that passed through code written for what an engine does differently. It is printed in the run, written into the JSON with its reason and counted here,
so a pass is never a quiet pass. R13 is the only skip: CPU throttling is a Chromium (CDP) emulation, so Firefox and WebKit cannot be slowed; its unthrottled half (eight rows animate on 19 and
on 240 jobs, the same length, under 400 ms) is R2, which ran on both (Firefox 285 and 254 ms, WebKit 164 and 140 ms for 19 and 240 jobs on a desktop).

### 11.1 What the owner asked to see

| Asked | Where | Result in Firefox and WebKit |
|---|---|---|
| Results arrival content remains visible | R1 (no JavaScript), R2, R3, R12 | Every row is fully visible with scripts off; eight rows animate (three on a phone) and the rest are simply there. Firefox: first readable frame to full in 108 ms (desktop); WebKit: see 11.3 |
| Rapid tabs do not stick or lose the final state | R8 | Three presses 30 to 120 ms apart, ten runs, fast and 700 ms slow, in both engines: every run ends on a real view, nothing stuck, dimmed or animating, the last press shown 10 of 10 |
| Filter and Export function | R10, R11, R11c | Open, close, switch, five presses 60 ms apart consistent with `aria-expanded`; keyboard Enter and Space; focus never moves to another control |
| Unsupported height interpolation degrades correctly | R11, R11b, R11c | Neither engine has `interpolate-size`, so the page itself is the fallback (no stand-in): natural height from the first frame, opacity in, instant out, same panel and list position as the forced fallback in Chromium. **R11c found a defect here; fixed** (11.2) |
| Slow-answer dim and un-dim clear | R6, R6b, R6c, R7 | Firefox: dims from about 160 ms, settles at .85, clears; AA at 5.10 and 4.61. **WebKit does not paint the dim on the old page** (11.3), and it clears |
| Reduced motion gives immediate, complete states | R5, P6, F7, R11c | No animation or transition on any frame in either engine; **the tool switch now swaps in one frame in reduced motion too** |
| No horizontal overflow | R9, P9 | 0 px on every view and every Progress screen, at 1440 and 390, panel open too |
| No hidden or stuck content | R1, R7, R8, P5, P8 | None; a stopped navigation clears within 10 s; the no-JavaScript pages show everything |
| No new console or runtime errors | every script | 0 uncaught script errors in all four engines. Console errors: 0 in Chromium, Chrome and Firefox; WebKit logs three, all in R11b, and none comes from the product: two are failed preconnects to the font hosts (the harness has no network) and one is its message for the stylesheet request that the forced-fallback arm re-routes |
| Progress ending and redirect remain correct | P3 to P6 | The ending fades in over 160 ms after the server says so; the page leaves for Results 472 ms (Firefox) and 465 ms (WebKit) on a desktop after the ending is painted (426 and 433 on a phone), against 485 and 493 (434 and 445) in Chromium and Chrome. The 400 ms is the design; the rest is the next page committing from the harness's Python server, which is in the figure (the first pass read 424 in Chromium on a quieter machine; no redirect code changed). All are inside the check's 395 to 540 ms |
| Configure pending state remains readable | F1, F3 | The old figure stays at .85, every text node AA (worst 4.57), the new figure is written once and equals the `/estimate` answer, in both engines |

### 11.2 The defect, and the proof

Switching Filter and sort for Export (or back) showed **both panels for one or two painted frames** whenever the height is not animated, so the list stood 72 px lower and then rose 128 px.
The painted frames, read after each frame's rendering with the click made inside the page, before and after the fix (`FE` both panels, `F-` Filter only, `-E` Export only, `list@` the list's top):

| Path | Before (`b9fc6c0`) | After |
|---|---|---|
| Chrome 154, height animation forced off | `F-@442` then `FE@514` x2 then `-E@388` | `F-@442` then `-E@388` |
| Chrome 154, reduced motion | `F-@442` then `FE@514` x2 then `-E@388` | `F-@442` then `-E@388` |
| Firefox 153.0 (its own fallback, and reduced motion) | `F-@444` then `FE@516` x2 then `-E@388` | `F-@444` then `-E@388` |
| WebKit 26.5 (its own fallback, and reduced motion) | `F-@443` then `FE@515` x1 then `-E@388` | `F-@443` then `-E@388` |
| Chrome 154, animated | the list moves one way over 13 frames | identical (the same layout-shift values) |

R11c now measures this (the old version sampled with a callback that runs before Alpine's in the same frame and saw a gap that was never painted). It **fails on the old tree in Chrome, Firefox and WebKit and passes on the new one**
(`output/design-D7B/engines-prefix-proof/`, one file per engine), and `test_motion.py` pins the two rules (removing either was caught by a mutation). The fix touches nothing at rest (`.t-out` exists only while Alpine is moving a panel),
so the 104 at-rest captures stand; the reduced-motion Results clips are the only Chromium evidence it affects, and they were recaptured in Chrome 154 (`recordings-chrome/`, section 13).

### 11.3 Engine differences (not defects), and what each costs a visitor

- **WebKit stops painting the outgoing page the moment a navigation is pending.** Measured, not assumed: after a press that starts a navigation, the old document gets no `requestAnimationFrame` frames (0 in 500 ms against about 30 in Chromium and Firefox),
  however the navigation starts (a click, a key, `location.href`), headless or headed, and an opacity transition sits at its start. So on a slow answer the old page is **not dimmed**; the class and the handoff flag are set and cleared as designed
  (R6, R6b, R7 pass), and the new page then starts at .85 and settles in 160 ms with no dim before it. It is a faint fade-in of the new list, never a stuck or hidden state. R6 and R6c state this and measure the dimmed state the same rule gives with no
  navigation pending (worst contrast 5.10 and 4.61). This is the Safari habit of freezing a page that is being left; I could not confirm it in the Safari app. Question 5 in section 17.
- **Firefox and WebKit replay the tiles' 160 ms colour change when the closed "Searches" panel is opened**, for the tiles that finished while it was shut (Firefox 51 and WebKit 24 property transitions, colour only: no scale, no ripple, no animation). They keep a closed
  `<details>` content's last rendered style and transition from it on opening; Chromium does not. P2b states this and bounds it. No CSS-only rule I tried could tell the engine the old style is stale, and a script for it is more than this is worth.
- **Neither engine has `layout-shift` entries**, so R9's layout-shift figure is 0 because nothing was measured; the overflow half is measured. (Chromium's worst is 0.0016.)
- **macOS WebKit's Tab key stops at form fields and summaries, not buttons or links** (Safari's "Press Tab to highlight each item" is off by default); Option-Tab reaches every control in the same order. R10 uses it there and says so. And **WebKit does not focus a clicked button**,
  so after a click the focus is on the page, never on another control (R11b).
- **WebKit's R12 is not informative:** rAF does not run while WebKit loads a page, so the first sample is already at full strength (449 ms, span 0) and the check passes without showing the fade. The recorded clip does (`frames-webkit/01b-arrival-wide-desktop.png`: rows fade in over about 150 ms from the first paint).
- **R2 failed once in twelve attempts on Firefox and I cannot explain it.** In that run the 240-job desktop arrival animated one row (writeIn 1, motionMs 140) instead of eight; it passed on the first pass, six times in a row afterwards, and four times with the CPU
  saturated (ten busy loops on eight cores). The failing result is kept (`output/design-D7B/engines-first-attempts/`). It happened while the machine was busy (a stale browser process, an editor at 86% CPU). The designed failure is benign (rows are visible and the arrival
  is skipped) and the same check passed under 6x throttling in Chromium, but it is an unexplained intermittent, not a pass for the unexplained.

### 11.4 What was my harness's fault

Eight things were wrong in the harness, not the product, and each was fixed in the harness (`motion-d7b/harness/`) and re-run: R11b required an animated arm that an engine without `interpolate-size` cannot have; R10 used a key that WebKit does not use for buttons; R11b required focus on a button WebKit does
not focus; **F6** left the pointer over the drop zone (already its hover colour in WebKit, so a drag changed nothing) **and rewrote the files between picks** (a new modification time makes the picker treat a file as a different one, and WebKit keeps whole seconds where Firefox keeps milliseconds, so the same sequence read differently in each);
R11c sampled before Alpine's callback and, in a second attempt, counted layout shifts that a Playwright mouse event had forced and no frame ever painted; the page trace made Firefox paint a page before its stylesheet had applied, putting a white frame into the Firefox recordings at some navigations that a visitor never sees
(measured: none with the trace off, on this tree or on the parent; the trace is now off for Firefox and WebKit takes); the recorder's output folder was shared between engines (it would have overwritten the Chromium clips; each engine now has its own); and two runs died on `net::ERR_NETWORK_IO_SUSPENDED` (macOS suspending the network)
and left a server on the port that failed the five runs after it (the runs now keep the machine awake and clear the ports first). The first-attempt files that showed these are kept in `output/design-D7B/engines-first-pass/` and `engines-first-attempts/`.

## 12. At rest

Every state the D6 regression set covered (Upload, Review, Configure, Key, Confirm, Progress, Results; one résumé and three; public and console),
plus the states D7 adds (a 19-job and a 240-job Results, a one-résumé Results, an over-credit Configure): **52 states, each at 1440 and 390 (104 full-page captures)**, from an export of the parent commit
and from this tree by the same harness, on the same night (D6 captured both sides within the hour because a Confirm screen adds an evening clock warning; every Confirm state here is identical, so it did not change), with CSS animations and transitions taken off both so the comparison is of composition.
**All 104 captures are pixel-identical.** (A first capture showed one or two levels of difference on glyph edges in every state the old page animated: the old page's
entrance leaves text on a compositor layer. Taking animations off both trees, which is also what a settled page looks like, removed it; one console state
needed a longer settle after the old tile animation. The difference was anti-aliasing, never position, size or colour, and every page height was identical.)

The parent's tree differs from this one only in the files this phase names (`diff -rq` of the two exports: the stylesheet, four templates, `motion.js`, three test files).
The approved D6 screenshots were used as anchors by name: of the 80 screens both sets hold, 28 are byte-identical to D6's; the rest differ for reasons the D6
notes already give (the "Nd ago" ages and the evening clock warning depend on the hour; the console's rows and the harness's listings are not D6's), so they are not a fair comparison, and the same-hour
pair above is the evidence. `regression-anchors.json` has the list.

Contact sheets: `contact-sheet-regression-desktop.png`, `contact-sheet-regression-mobile.png` (every state, green when identical) and
`contact-sheet-before-after-desktop.png`, `contact-sheet-before-after-mobile.png` (before | after | difference, one screen per stage).

## 13. Recordings

Real browser (Chromium 151), real time, one continuous take per clip, 25 fps VP8 WebM, 1440 x 900 and 390 x 844 (touch). Fonts are the real ones, cached before the take. **Not slowed.** A cursor and a press ring are drawn into the recording. Each
clip starts and ends with a 160 ms white flash that aligns its trace with the video (drift 74 ms at most). Paths are relative to the repository root.

The ten recordings the brief asks for, and the files:

| # | The brief's clip | Files |
|---|---|---|
| 1 | Desktop complete Results interaction | `results-desktop` |
| 2 | Mobile complete Results interaction | `results-mobile` |
| 3 | Slow Results response, dim and un-dim | `results-slow-desktop`, `results-slow-mobile` |
| 4 | Reduced-motion Results | `results-reduced-desktop`, `results-reduced-mobile` |
| 5 | Progress running, success, about 400 ms, Results | `progress-success-desktop`, `progress-success-mobile` (and `console-progress-desktop`) |
| 6 | Progress failure ending | `progress-failure-desktop`, `progress-failure-mobile` |
| 7 | Configure price update: pending .85, then the authoritative price | `configure-price-desktop`, `configure-price-mobile` (and `console-configure-desktop`) |
| 8 | Over-cap transition with no shake | `configure-overcap-desktop`, `configure-overcap-mobile`, `console-overcap-desktop`, `console-overcap-mobile` |
| 9 | Upload file acceptance | `upload-desktop`, `upload-mobile` |
| 10 | Long Results list | `results-long-desktop`, `results-long-mobile` |

**Firefox, WebKit and the recaptured Chrome clips (follow-up pass).** Same scenarios, same harness, real time, one engine per folder. Firefox and WebKit are recorded **without the page trace** (section 11.4) and run about a second off wall time, a roughly constant offset rather than a proportion; every trace
keeps its measured drift, and a timing is never to be read off a clip. Each has exactly the two sync flashes. Paths are relative to the repository root; filmstrips are in `output/design-D7B/frames-firefox/`, `frames-webkit/` and `frames-chrome/`.

| Clip | Length | Size | What it shows |
|---|---|---|---|
| `output/design-D7B/recordings-firefox/results-desktop.webm` | 0:28 | 2.5 MB | The complete Results interaction in Firefox 153.0: tabs, interruption, Filter and sort, Export replacing it (the fixed switch), Apply, Back |
| `output/design-D7B/recordings-firefox/results-slow-desktop.webm` | 0:16 | 1.3 MB | A slow answer in Firefox: the list dims after 160 ms and settles on arrival |
| `output/design-D7B/recordings-firefox/results-reduced-desktop.webm` | 0:28 | 2.5 MB | Reduced motion in Firefox |
| `output/design-D7B/recordings-firefox/progress-success-desktop.webm` | 0:18 | 1.1 MB | Progress: tiles, a listing, the ending, about 400 ms, Results |
| `output/design-D7B/recordings-firefox/configure-price-desktop.webm` | 0:19 | 1.2 MB | A slow price answer: the old figure at .85, then the new one written |
| `output/design-D7B/recordings-webkit/results-desktop.webm` | 0:30 | 3.0 MB | The complete Results interaction in WebKit 26.5. **Look at the arrival:** the old page is held until the new one paints, then the rows write in |
| `output/design-D7B/recordings-webkit/results-mobile.webm` | 0:24 | 1.2 MB | The same at 390 (WebKit's mobile emulation, by touch) |
| `output/design-D7B/recordings-webkit/results-slow-desktop.webm` | 0:17 | 1.5 MB | **A slow answer in WebKit: the old page is not dimmed** (section 11.3), then the new one arrives at .85 and settles |
| `output/design-D7B/recordings-webkit/results-slow-mobile.webm` | 0:14 | 0.6 MB | The same at 390 |
| `output/design-D7B/recordings-webkit/results-reduced-desktop.webm` | 0:29 | 2.9 MB | Reduced motion in WebKit |
| `output/design-D7B/recordings-webkit/progress-success-desktop.webm` | 0:19 | 1.1 MB | Progress ending and redirect in WebKit |
| `output/design-D7B/recordings-webkit/configure-price-desktop.webm` | 0:20 | 1.5 MB | The pending price in WebKit |
| `output/design-D7B/recordings-chrome/results-reduced-desktop.webm` | 0:28 | 2.7 MB | **Recaptured after the fix** (Chrome 154): reduced motion, with Filter replaced by Export in one step. Supersedes `recordings/results-reduced-desktop.webm` for that interaction |
| `output/design-D7B/recordings-chrome/results-reduced-mobile.webm` | 0:24 | 0.9 MB | The same at 390 |

The Chromium clips above (`recordings/`) stand: the animated path they show is unchanged by the fix.

| Clip | Length | Size | What it is |
|---|---|---|---|
| `output/design-D7B/recordings/results-desktop.webm` | 0:29.3 | 3.1 MB | **The complete Results interaction (1440).** Arrive from the Running screen, four tabs, three tabs pressed 70 ms apart, Filter and sort, Export (Filter closes), Export closes, Apply filters, Back |
| `output/design-D7B/recordings/results-mobile.webm` | 0:24.0 | 1.0 MB | The same at 390, by touch |
| `output/design-D7B/recordings/results-slow-desktop.webm` | 0:16.3 | 1.5 MB | **A slow answer.** Every Results answer held 700 ms: the list dims after 160 ms and settles on arrival; then a quick tab (instant) |
| `output/design-D7B/recordings/results-slow-mobile.webm` | 0:14.2 | 0.5 MB | The same at 390 |
| `output/design-D7B/recordings/results-reduced-desktop.webm` | 0:29.1 | 2.7 MB | **Reduced motion.** The complete sequence with `prefers-reduced-motion: reduce` |
| `output/design-D7B/recordings/results-reduced-mobile.webm` | 0:23.3 | 1.0 MB | The same at 390 |
| `output/design-D7B/recordings/results-long-desktop.webm` | 0:17.2 | 2.0 MB | **A long list.** 240 jobs: the arrival, Show all, scroll down and up, a tab |
| `output/design-D7B/recordings/results-long-mobile.webm` | 0:15.6 | 1.0 MB | The same at 390 |
| `output/design-D7B/recordings/progress-success-desktop.webm` | 0:18.7 | 1.1 MB | **Running to Results.** A worker run part-way: the Searches panel opened, searches finish and a listing arrives, the worker ends the run, the ending fades in, about 400 ms, Results arrives |
| `output/design-D7B/recordings/progress-success-mobile.webm` | 0:14.6 | 0.4 MB | The same at 390 |
| `output/design-D7B/recordings/progress-failure-desktop.webm` | 0:11.8 | 0.5 MB | **A failure.** The engine exits with an error: the ending fades in and the page goes nowhere |
| `output/design-D7B/recordings/progress-failure-mobile.webm` | 0:11.4 | 0.2 MB | The same at 390 |
| `output/design-D7B/recordings/configure-price-desktop.webm` | 0:19.6 | 1.2 MB | **A price update.** A slow answer (1.1 s): the old figure stays at .85 and the new one is written at once; then quick answers |
| `output/design-D7B/recordings/configure-price-mobile.webm` | 0:22.2 | 0.6 MB | The same at 390 (2.6 s; the stepper is operated from the keyboard so the figure is in view) |
| `output/design-D7B/recordings/configure-overcap-desktop.webm` | 0:18.4 | 1.3 MB | **Over the credit.** The estimate crosses the key's credit and comes back: colour and words, no shake |
| `output/design-D7B/recordings/configure-overcap-mobile.webm` | 0:17.5 | 0.5 MB | The same at 390 |
| `output/design-D7B/recordings/upload-desktop.webm` | 0:17.5 | 0.8 MB | **An accepted file.** A file held over the drop zone, two files accepted, a third, one removed, a file that is not a PDF |
| `output/design-D7B/recordings/upload-mobile.webm` | 0:13.7 | 0.4 MB | The same at 390, without the hover |
| `output/design-D7B/recordings/console-configure-desktop.webm` | 0:18.6 | 1.3 MB | The operator console's meter: the figure written, the fill following, slow and quick answers |
| `output/design-D7B/recordings/console-overcap-desktop.webm` | 0:18.6 | 1.3 MB | The console meter crossing a $2.00 cap, both ways: no shake, no overshoot |
| `output/design-D7B/recordings/console-overcap-mobile.webm` | 0:16.7 | 0.4 MB | The same at 390 |
| `output/design-D7B/recordings/console-progress-desktop.webm` | 0:14.8 | 0.9 MB | The console's Running screen (streamed): tiles, a listing, the ending, Results |

**Where to look in `results-desktop.webm`** (each step begins when the cursor starts to move; the press lands about 0.4 s later):

| Video time | What happens | What to watch |
|---|---|---|
| 0:03.9 | arrive on Results | The heading, tabs and tools are already there; the first eight rows write in top-down |
| 0:06.6 | tab: Backend | An instant swap: only the list changes |
| 0:08.8 | tab: MERN | Same |
| 0:10.9 | tab: Applied | Same |
| 0:13.0 | tab: All Jobs | Same |
| 0:14.4 | interruption | Three tabs in 140 ms: the page settles on one; nothing flickers or sticks |
| 0:17.1 | Filter and sort: open | The panel grows in place, pushing the list down |
| 0:19.0 | Export: open | **Filter closes and Export opens together: the list moves one way** (this was the wobble the review found) |
| 0:21.0 | Export: close | Closes in 140 ms |
| 0:22.6 | Filter and sort: open, Apply | Opens; Apply filters reloads: an instant swap |
| 0:25.6 | Back | Back to the previous view: instant |

Slow server (`results-slow-*`): watch the old list dim about 160 ms after each press and the new list arrive 700 ms later already dimmed and settle (faint at .85: look at the text, not the page); the page has no other cue. `progress-success-desktop.webm`: the tiles change colour together at **0:09.5** (the new listing writes in); the worker ends the run, and the ending is first drawn at about **0:13.5** (the recorder's frames lag the page by up to a few hundred milliseconds here, see the note below); Results arrives about **0:13.9** with its first rows writing in.

**A note on the recorder.** Playwright's screen recorder delivers frames late when the page has just redrawn a great deal (here, about 120 tiles and a banner in one frame on a phone): in `progress-success-mobile.webm` the ending is on screen for about 250 ms of video although the page's own frame clock puts 400 ms between the ending being painted and the page leaving (P3: 424 ms on a desktop, 427 ms on a phone). The page is right and the clip is late. Do not time the pause from the clip.

Filmstrips (`output/design-D7B/frames/`, 34 sheets of real frames with their real times) are the nearest thing to the video that a reviewer who cannot play it can
read. Two limits of the footage: 25 fps cannot resolve a 20 ms row step, and a headless browser does not show the jank of a real device.

## 14. Independent critique

**Who and how.** A fresh `general-purpose` subagent that had no part in building this, read-only, given the brief's criteria, the owner's decisions and the evidence
paths. It cannot play video; it read the diff, the stylesheet, both inline scripts, the Alpine hooks, the tests and 25 of the filmstrips, and it decoded eight of the WebMs itself
with the machine's ffmpeg (brightness and layout series over about 1,400 frames, twelve full-resolution frames). It made 88 tool calls over 16 minutes and did not run the tests.
Its rule was to look for motion to delete. Ratings and what followed:

| Criterion | Rating | Its reason, and what I did |
|---|---|---|
| Responsiveness | Strong | A quick tab is one frame; the dim waits 160 ms |
| Restraint | Adequate | "The ending cluster, the tile scale and the 160 ms fades that carry no information". **The tile scale and the ending cluster were fixed (below); the fades were kept (below)** |
| The 20 ms stagger | "Weak value" | "Not fussy: imperceptible, and it can go." **Kept: the owner's decision G.** Question 3 |
| Waiting-state clarity | Adequate on Configure, weak on Results | The Results dim measures about .88 ink. **Kept: the owner chose .85 and said it may stay subtle.** The only lever is the level, and it costs AA (7.1) |
| Panel movement | Adequate | Open and close are clean; **the switch wobbled: fixed** |
| Reduced motion | Strong | Every cue traced; state complete |
| Mobile feel | Adequate | Three rows, an instant tab swap; the ending's paint latency was the risk: **the timer now starts from the painted frame** (defect 2) |
| Browser fallback | Adequate | Unverified in real engines, as stated |
| Performance | Adequate | Unmeasured: a 240-row dim on a phone; 106 cell transitions at once (**removed with the scale**) |
| Consistency with Quiet Ledger | Adequate | "The tile scale and the stacked ending break the restraint": **fixed** |

**Its five findings, and what was done.**

| # | Defect | Disposition |
|---|---|---|
| 1 | Switching Filter to Export made the list wobble (the first table rule went 559, 572, 576, 549, 503: down 17 px, then up 73), with both panels half visible | **Fixed** (item 14 of section 7). Before: up 24 px, then down 78 px with a 20 px late step; after: one direction, at most 4 px back. R11c is new and fails without the fix |
| 2 | The ending can be on screen for much less than 400 ms: about 160 ms of it in the phone clip, which the reviewer took to be Alpine drawing the ending a frame or more after the state was set (75 ms on a desktop, 230 ms on a phone with about 106 tiles changing at once). P3 and F9 had measured the DOM flip, not the paint | **Partly right, changed anyway** (item 13). On the page's own frame clock the ending was painted 11 to 17 ms after the flip, so most of the gap is the recorder's lag, not the page's. The timer is now armed from the second frame after Alpine's draw, which is correct wherever paint really is slow, and P3, F9 and P6 measure from a painted-frame probe |
| 3 | A batch of tiles landing is a pulse, stacked with the banner fade, the bar moving from 12% to 100% and an instant layout step: five things in the last 400 ms | **Fixed** (item 12): the scale and its JavaScript are gone; the colour change remains. The layout step is the ending's box appearing, which is how the screen already worked |
| 4 | The first painted frame of an arrival is an empty ledger: all eight rows at opacity 0, heading and rules visible, for one recorded frame | **Not changed.** It is one frame at 60 Hz, the heading, tabs and tools are readable in it, and starting a row at .3 would change a parameter the owner approved (140 ms from opacity 0). It is also what the write-in is |
| 5 | Wording and evidence: the note said "no `requestAnimationFrame` in any script" but the test scans `static/` and the head script uses one; the feedback dialog faded but its backdrop did not; the over-credit sentence reads "$0.00 more than your key has" | The wording is corrected (the claim is "in any file under `static/`"); the **backdrop now fades with the dialog** (R14 measures both); the sentence is an existing copy problem and is recorded for D7C (section 17) |

**Deletions it recommended, and what I did.**

| Recommendation | Done | Why |
|---|---|---|
| The 20 ms stagger (taste) | No | Owner's decision G; flagged as question 3 |
| The tile scale and its marker JavaScript (mostly objective) | **Yes** | Item 12 |
| The MARK fade on `finished` (objective, from defect 2) | No | The owner's decision H/"Progress ending ~160 ms". The cause was the timing, which is fixed |
| The feed's colour step-down; the location menu fade (taste) | No | Existing and owner-listed respectively, both one line and 160 and 120 ms |
| The dialog fade, or fade the backdrop too (taste) | The backdrop now fades | The owner allowed a dialog fade |
| The un-dim half of DIM: `swap`, the `sessionStorage` handoff, `list-in` (taste, "worst complexity to visibility") | No | Owner's decision F ("start at .85 and settle to full over ~160 ms"). It is a few rules of CSS and the two inline scripts, tested by 67 assertions on each of two pages. |
| Arrival write-in, panel height, `@supports`, press, Configure dim, upload and feed write-in, meter width | Kept | |

**Not judged from frames:** playback feel and 60 Hz pacing; whether a 20 ms step reads as a sequence, or .85 is perceptible to a person; the dialog (no recording; R14 measures it);
drag-over glow (faint in every frame); Firefox and Safari (opacity on `tr` under `border-collapse` in WebKit is untested); screen-reader output with `aria-live` and a write-in; real-device jank;
the dim of a 240-row container on a phone. **Everything the review changed was recaptured**: all 22 clips, the filmstrips and the at-rest states come from the final code.

## 15. Tests

- **`sweep/tests/test_motion.py`** (new, 57 tests, one added in the follow-up for the leaving panel): the tokens and that each is used; nothing banned (`will-change`, `transition: all`, blur, view transitions, parallax); only the indeterminate bar moves anything;
  no dead keyframe; what was deleted stays deleted; every animation and transition this phase added is inside `no-preference`; reduced motion is not a shorter animation (every declaration in a reduce block is `none` or zero);
  the dim is AA on every ground (computed from the tokens) and every dimmed region lifts the muted tone; the figure is written not counted; no shake; the head script, wrapper, stagger cap, arrival and slow-answer rules;
  the panels' attributes, the `@supports` split and the one-curve switch; the redirect is 400, counted from the painted ending, with a fallback, and reachable only from `p.finished`; every ending fades in on `p.state` only;
  a finished search is a colour, and the feed marker; upload, menu and dialog (backdrop included); nothing in the shell moves. Each test was shown to fail against the old code (67 failures and 7 errors on the first run).
- **`sweep/tests/results_motion_test.js`** (new, 67 assertions on each of the public and operator pages, run by `test_the_scripts_behave`): referrer, navigation type, reduced motion, stale flag, blocked storage; which links and forms
  arm the dim; interruption; bfcache; that neither script can hide, scroll, move focus or navigate. Seven mutations of the scripts were each caught.
- Updated on purpose: `test_app.py` (`TestMotion` reduced to the three things still true; the working screen no longer rises; the finished sweep's redirect is now `leave()`), `test_results_ui.py` (no `reveal`).
- **Focused run:** 1,110 tests (1,109 and the new pin) across the UI, Results, Progress, Configure, Confirm, Upload, terminal-state, public-copy and Multi-Track Results suites, **OK** (3 skipped, as before), in 223 s after the fix (211 s before). `price_test.js`, `pick_test.js` and
  `reading_test.js` pass untouched. The full release suite was not run, as instructed.
- **Mutation check of the Python tests** (each change made in a sandbox copy, never in the tree): twenty-three regressions, **all caught**: the dim back to .7; a `will-change`; `transition: all`; the muted tone not lifted on Results; a loop outside
  `no-preference`; the money counter back; an ending without its mark; a shake; a wrapper without `stack`; a stagger cap of 12; a view transition; a shorter fade for reduced motion (this one survived the first round and the test was tightened);
  the referrer check removed; the first-paint script back; the redirect back to 1,200; a column ripple; the tile scale; the redirect timer started at the state again; a tab that draws no frames never leaving; the tool switch on two curves;
  the dialog backdrop popping; a tile marker in the template; the feed marker never cleared.
- **Browser checks:** `motion-d7b/harness/verify-results.mjs` (R1 to R14 and R6b, R6c, R11b, R11c: 18 checks), `verify-progress.mjs` (P1 to P9 and P2b: 10), `verify-forms.mjs` (F1 to F10: 10), kept in `output/design-D7B/verify-*.json`.
  After the follow-up pass the browser checks are run on four engines (section 11): 38 + 38 + 37 + 37, written to `verify-*-engines-<engine>.json`; R11c, R11b, R6, R6c, R9, R10, P2b and F6 are the checks that changed (11.4).
  R11c, the one-curve switch, was shown to fail without the fix (the list went up 24 px and down 78 px with a 20 px late step; with it, 12 up and 66 down, one direction apart from the gap step at each end).

## 16. Evidence

| What | Where |
|---|---|
| Recordings (22 clips, 23 MB), traces | `output/design-D7B/recordings/`, `traces/` |
| Filmstrips (34) | `output/design-D7B/frames/` |
| At-rest captures, before and after (104 + 104 PNGs), verdicts, anchors | `output/design-D7B/regression-before/`, `regression-after/`, `regression.json`, `regression-anchors.json` |
| Contact sheets | `output/design-D7B/contact-sheet-*.png` |
| Browser checks, first pass (Chromium, Chrome; before the follow-up fix) | `output/design-D7B/verify-results.json`, `verify-progress.json`, `verify-forms.json` and the `-chrome` variants |
| Firefox, WebKit and Chrome follow-up: browser checks on four engines | `output/design-D7B/verify-{results,progress,forms}-engines-{chromium,chrome,firefox,webkit}.json`, `engines-summary.md` |
| What the first attempts showed (kept, not replaced) | `output/design-D7B/engines-first-pass/` (the first Firefox and WebKit runs, before the harness was corrected), `engines-first-attempts/` (the Firefox R2 failure; the first forms runs), `engines-prefix-proof/` (R11c failing on the old tree in three engines) |
| Follow-up recordings and filmstrips | `output/design-D7B/recordings-{firefox,webkit,chrome}/`, `traces-*`, `frames-{firefox,webkit,chrome}/` |
| Manifests | `docs/design/EVIDENCE_MANIFEST_D7B.sha256` (the first pass, unchanged and still verifying) and `docs/design/EVIDENCE_MANIFEST_D7B_ENGINES.sha256` (the follow-up), each `shasum -a 256 -c` |
| Tooling | `docs/design/motion-d7b/` |

The D1 to D7A sets and manifests are untouched and still verify (717 files).

## 17. Left for D7C, and questions

Still open, deliberately untouched here: the saved-profile same-second bytecode caching; the complete paid ledger and an unsuccessful process ending; the worker's own stopped state after a restart;
raw internal résumé-reading diagnostics in the public UI; unsaved expanded résumé-editor state on navigation; operator-header consistency. The two D6 polish candidates (Filter/Export discoverability, "jobs found"
against "jobs matched your profile") are also left.

Seen while recording, not fixed, not motion: Configure's over-credit sentence can read **"That is $0.00 more than your key has."** when the plan's hard cap, not the estimate, is what exceeds the credit; and on
a phone the stepper and the estimate are never on one screen, so a price change there is seen only by scrolling.

Questions for you (2 to 4 were put before the motion was approved, and the owner's approval of it as built answers them; they stay here for the record):
1. **The Safari application.** Firefox 153.0 and WebKit 26.5 are done (section 11). Safari 26.6.2 itself is not: it needs "Allow remote automation" (Develop menu, or `sudo safaridriver --enable`), which changes a security setting on your machine. The one thing it would settle is question 5.
2. **The tile landing.** You listed "completed search tile landing" as kept. I kept the landing as the cell's colour change and **removed the scale** (item 12 of section 7), on the reviewer's evidence. If you want the scale back, it is one keyframe
   and the marker script; say so and I will restore it with a cap on how many tiles may land together.
3. **The stagger.** Still the most distinctive part of the arrival and the part 25 fps cannot judge, and the reviewer found it imperceptible. If it reads as noise in the clip, drop the stagger, not the arrival.
4. **`--pending-slate`.** It is a lifted muted tone while a region waits. The alternative is to accept 4.11:1 for muted words on a card while it waits. I would not.
5. **WebKit does not paint the slow-answer dim on the page being left** (11.3), so a Safari visitor sees the old list at full strength and then the new one arrive at .85 and settle. It never sticks or hides anything. Two ways forward: accept it (my recommendation: it is a faint fade-in, and the cost of the alternative is in the approved head script), or set the handoff flag only once a frame has been painted since the dim began (a few lines in the pending script, and the 67 assertions on each page to extend). Which?
6. **Firefox and WebKit replay the tile colour change when the closed Searches panel is opened** (11.3). Accept, or have me find a way to keep a tile's colour change from running when the panel was not showing it? I would accept.
