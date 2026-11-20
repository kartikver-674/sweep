# Sweep design, phase D7A: motion direction, tooling audit and a working prototype

Branch `design/sweep-ui-overhaul`, starting at `7487f3d` (D6 accepted by the owner). This phase is **research, direction
and one isolated prototype**. The application is unchanged: nothing under `sweep/` was edited, no route serves the
prototype, no dependency was added, and nothing was pushed, merged or deployed. Evidence is in `output/design-D7A/`
(git-ignored, synthetic data only, no model, provider or paid call); the prototype is in
[`prototype/motion/`](prototype/motion/README.md). The visual direction is still
[SWEEP_DESIGN_DIRECTION.md](SWEEP_DESIGN_DIRECTION.md); motion extends it and does not add to it.

**Implemented in D7B:** the approved direction was put into the application in [SWEEP_D7B_MOTION_INTEGRATION.md](SWEEP_D7B_MOTION_INTEGRATION.md), which also lists where production differs from this note (section 7 there). This note is otherwise unchanged and still describes D7A as it was approved.

**The owner's gate.** Recordings at normal speed are in `output/design-D7A/recordings/` (section 10). Neither I nor the
independent reviewer can *watch* a video. What was judged is frames cut from those same recordings at their native 25 fps,
plus in-page measurements (sections 12 and 13). Approval of how the motion *feels* is yours and needs the clips played.

## 0. The decision in one page

| Question | Answer |
|---|---|
| What is the motion idea? | **Motion says what changed and nothing else.** The heading, the tabs and the tools are readable at t = 0 and never move. The list moves in three cases only: it is *written in* when you arrive, it *dims and then un-dims* when an answer is slow, and a tool panel *opens in place*. **A quick tab, filter or sort is an instant swap with no motion.** Nothing travels; everything is opacity, height and the row gap. No slide, scale, bounce or blur |
| How much is that? | Three effects on Results, one fade on each Progress ending, a few small fades elsewhere, and **six things deleted** (section 14). Most of the work is removal |
| CSS, WAAPI or GSAP? | **CSS**, plus a 15-line head script and a 22-line body script that only toggle classes. **No GSAP, no WAAPI.** The interactions are not sequences: the hard cases are page navigations, where nothing persists for a timeline to manage. A GSAP spike reproduced the arrival and was no better on timing, added 28 KB, and made the page wait or hide its list whenever its script was slow or missing (section 7) |
| What changed the design? | Four measured or reviewed results, all kept in the evidence. (1) A cross-document **view transition swallows clicks**: the last of three rapid presses was shown in 0 or 1 of 10 runs against 7 to 10 of 10 on the shipped page, so the crossfade I built first is now an alternative, not the proposal. (2) **Height animation of a tool panel added at most a small cost** (the worst cell, 240 rows at 6x CPU: a mean frame of 9.1 ms against 7.7 ms against an opacity fade), so my own rule "opacity only, height is expensive" was wrong and was removed. (3) On review, an **un-dim on every tab change created a dip** on a fast server, so it now happens only after a dim, as the end of a wait. (4) Dimming to .7 leaves the muted captions at **3.45:1**, below AA, so the level is **.85** (4.54:1) |
| What already breaks the new rules? | `motion.js` counts the **money figure** up between values (forbidden by the brief), the section entrance replays on every tab, filter and reload, and there is a 500 ms shake when a cap is crossed. All three are recommended for deletion or simplification |
| What do I need from you? | Watch the clips and answer section 15. The important ones: the money counter, the cap shake, the 1.2 s pause before Results, whether a quick tab change should be instant, the dim level, and GSAP's licence |

## 1. Skill audit and selection

The inventory was audited by reading each candidate's instructions, not its name. The triage read the motion-relevant
parts of every design skill; the ones chosen were then read in full. **Not every skill was loaded into one context**:
`high-end-visual-design`, `gpt-taste`, `brandkit` and the video skills were checked and closed.

| Candidate | What it actually says about motion | Role |
|---|---|---|
| **`frontend-design`** (official plugin, 9.4 KB, read in full) | "Use non-user-triggered motion sparingly and deliberately... A single orchestrated moment... fade-and-slide-up entrances on each section and hover transitions on every card are the generic default and read as AI-generated. Motion that answers a person's action (opening, expanding, confirming) is welcome when it shows what changed." Defers to the brief ("the brief's own words always win"); quality floor includes "reduced motion respected"; closes with "remove one accessory" | **Primary creative direction.** It is the only candidate whose motion paragraph matches Quiet Ledger, and it is also the method used: plan, review the plan against the brief, build, critique |
| `minimalist-ui` (7.9 KB, read in full) | §7 opens "Motion should feel invisible", then prescribes a 600 ms scroll entry on *every* major block (§8.5), an uncapped `calc(var(--index) * 80ms)` stagger, and card hover lifts with shadows. Its palette is white or bone | **Lens, one sentence.** "Invisible" and its transform/opacity rule are kept. Its prescriptions are not: they would animate every block, and Quiet Ledger has no shadows |
| `design-taste-frontend-v1` (21 KB: dials and §4 to §6 read, the rest searched) | `MOTION_INTENSITY` dial, default 6; 1 to 3 is "no automatic animations, hover and active only"; 4 to 7 is `transition: all 0.3s`; "perpetual micro-interactions", spring physics and Framer Motion (React) above that | **Lens, the dial.** D1 ran it at 2. Motion here is event-driven, so it is run at **3**. Its "animate only transform and opacity" rule is adopted (with one measured exception, the tool panel's height); Framer and springs are not applicable (no React) |
| `high-end-visual-design` (10.5 KB, motion sections read) | Bans `linear` and `ease-in-out`, requires custom beziers and "spring physics... real-world mass", 700 ms durations, and a checklist line "Scroll entry animations are present, no element appears statically" | **Set aside**, as in D1. It contradicts the brief on three counts |
| `gpt-taste` (7.9 KB, §5 read) | "Static interfaces are strictly forbidden", ScrollTrigger pinning and scrubbing, card stacking, a 700 ms hover scale, Python-driven layout randomisation | **Set aside.** Landing-page tooling for a workspace |
| `redesign-existing-projects` (15 KB, interaction sections searched) | "Instant transitions with zero duration: add 200 to 300 ms to all interactive elements", spring physics "on all interactive elements" | **Not re-run.** It ran in D1. Sweep already has press and hover states and no zero-duration flashes; adding motion to everything is the opposite of the brief |
| `ui-ux-pro-max` 2.6.2, `motion.csv` | 16 rows, each with a GSAP snippet, a duration, an easing, Do, Don't and performance notes. Every row is written for GSAP | **Supporting cross-check.** Used for ranges only: stagger "0.02 to 0.04 s per item for lists longer than 10, never more than 0.1 s"; page transitions "cap exit at about 250 ms... exit faster than entrance"; hover displacement under 2 px. The GSAP bias is noted, and the rows for hover lift with shadow, parallax and scroll scrub are not used |
| `ui-ux-pro-max:design-system` (6.9 KB, read) | Three-layer tokens: primitive, semantic, component | **Supporting.** The structure of the motion tokens in section 4. Its slide system is irrelevant |
| `superpowers:brainstorming` (17.5 KB, opening and hard gate read) | The gate is on *implementation of product code*; three paths (spike, bounded, architectural); "when the request already supplies the purpose and constraints, reflect that understanding instead of asking the same questions again" | **Used as discipline.** This brief is an owner-approved spike, so there was no question loop; the written-back understanding is section 0 and the comparison of approaches is sections 7 and 9 |
| `superpowers:verification-before-completion` (3.6 KB, read) | Evidence before claims; "red-green" for a regression test | **Final gate.** Every number below was produced by a command in this session, and each new check was shown to fail against the defect it guards (T14, T15, the GSAP dip detector) |
| `webapp-testing` (3.9 KB, read) | Playwright scripts; reconnaissance then action; wait for `networkidle` | **Supporting, adapted.** Python Playwright is not installed here, so Node Playwright 1.62.1 from the Codex runtime was used (nothing installed). Its `with_server.py` was not used (D1 found it could not start the harness); `serve.py` is 100 lines |
| `ponytail` (6.6 KB, read; its hook was already active) | The ladder: does it need to exist, native platform feature, installed dependency, "never add a new one for what a few lines can do" | **Decision lens for GSAP.** It is exactly the order section 7 is argued in. Its terse-output rule does not apply to a note the brief asks for |
| `writing-plans`, `test-driven-development` | Govern production code | **Deferred to D7B.** The prototype is not production code; section 14 is the input to that plan |
| `brandkit`, Stitch and image tools | Image generation | Not relevant |
| BRAG 0.4.0, Remotion 4.0.531, `motion-graphics` | Launch-film tooling | **Kept out** of the app and of this phase. Only their descriptions were inspected, by design |

**Independent critic.** A fresh `general-purpose` subagent with no part in building the prototype (section 12), given the
brief's ten criteria and the Vercel Web Interface Guidelines' animation rules (fetched live: honour reduced motion;
animate transform and opacity only; never `transition: all`; animations interruptible; decorative loops stop under
reduced motion). **No skill was installed.** The one missing capability (a browser that records video) was already on the
machine.

## 2. What moves today

Read from `sweep.css` (2,604 lines), the five scripts and the templates, at `7487f3d`. Lines are in `sweep.css` unless
stated.

| # | What | Where | Trigger and timing | Reduced motion | Finding |
|---|---|---|---|---|---|
| 1 | Button background and press | 473, 482, 486 | hover and `:active`, 120 ms, `ease`, 1 px press | blanket rule | Keep. The right size |
| 2 | Disclosure chevrons | 602 to 604, 1652 to 1654 | `details` and `.tool-toggle`, 150 ms | blanket rule | Keep |
| 3 | The "alive" pulse | 761 to 764, 1146 to 1148, 1335, 1456, 1963 | infinite, 1 to 2 s, opacity | `.runbar` has its own (763); the rest by the blanket rule | Keep: the one vocabulary for "a run is live" |
| 4 | Stale price dim | 1137 | `.updating`, opacity .5, 120 ms | blanket rule | Keep the idea. **.5 fails AA for every text colour but the lightest** (muted 2.34:1, warm 3.51:1, body 4.35:1, computed on the ground colour) |
| 5 | Activity feed arrival | 1233 to 1239 | `arrive` 500 ms, 8 px slide, on each new row; colour 500 ms | blanket rule | Simplify: 500 ms and a slide are long for a feed that updates every few seconds. Keyed `x-for`, so only new rows animate (no replay on poll) |
| 6 | Waiting screen entrance | 1279 to 1280 | `.working` rises 8 px over 400 ms on load | blanket rule | **Delete.** An entrance on a screen whose job is to wait |
| 7 | Indeterminate bar | 1295 to 1305 | `slide` 1.15 s, infinite | **explicit**: static bar at half opacity | Keep. Honest: no percentage is invented |
| 8 | Determinate bar | 1347, 1359 to 1361 | width .45 s, only when a real fraction exists | explicit: no transition | Keep |
| 9 | Reading skeleton | 1404 to 1416 | `bone-sweep` 2.4 s infinite | explicit: static at half opacity | Keep. The Review reader replaces card nodes, so these restart on each refresh; harmless because they loop |
| 10 | Spend rail draw and cap tick | 2055 to 2062, `base.html` head script | `.first-paint`: 600 ms rail, 240 ms tick, **once per session** via `sessionStorage` | blanket rule | **Delete.** A decorative entrance that draws the *spend* bar from zero; operator console only (the public app has no meter) |
| 11 | Cap crossed: overshoot and shake | 2073 to 2090 | `.meter.over`: fill `scaleX(1.04)`, track shakes 3 px left and right, 500 ms; also plays on Confirm load | blanket rule | **Simplify.** A sideways shake reads as a wrong password. The state already has colour and words |
| 12 | Search tile landing | 2105 to 2118 | `.cell.done`: `scale(.82)` to 1, 200 ms, **10 to 70 ms delay by column** | blanket rule | Keep the landing, **delete the column delays**: the ripple is invented order, not the order searches finished |
| 13 | Running search cell breath | 2099 to 2100 | `cellbreath` 2 s infinite on the border | blanket rule | Keep, but note each running cell breathes out of phase with the others |
| 14 | Results sections entrance | 2123 to 2126 | `.reveal`: 320 ms, 6 px, r2 at 80 ms and r3 at 160 ms, **on every load of Results** | blanket rule | **Replace.** A tab, a filter, a sort and a reload each replay it (measured: 3 section animations every time), so every same-screen move blinks |
| 15 | **Money counter** | `motion.js`, `configure.html:12` | `sweepCount`: rAF, 350 ms ease-out cubic, **writes every intermediate dollar figure** to the page | `REDUCED` read once at load | **Delete the tween.** This is an invented intermediate number on a cost estimate, which the brief forbids. The first call already sets the text outright, which is the behaviour to keep |
| 16 | Meter fill width | 297 | `transition: width .35s` | blanket rule | Shorten to 160 ms. Console only |
| 17 | Everything else | | `x-show` and `details` swap instantly; no `x-transition` anywhere; no `will-change`; no `transition: all` | | The baseline is restrained. Good |

**Reduced motion today** is one blanket rule (`* , *::before, *::after { transition: none !important; animation: none
!important }`, lines 875 to 880) plus four explicit end states (763, 1303, 1359, 1416) and `motion.js` reading the query
once. It works, and it is why nothing in the list above is unsafe for a reader who asked for less. What it is not is an
*alternative*: it removes the motion and keeps everything else as it was. Section 11 says what the alternative is.

**Tests that pin the current motion** and will have to change, on purpose, in D7B: `test_app.py` around 5040 to 5141
(`first-paint`, `rail-draw`, `cap-cross-shake`, `sweepCount`, `tile-land`, `.reveal.r2/.r3` delays, and an assertion that the
motion section has *no* reduced-motion block), `test_results_ui.py:303` (`reveal r1`), `test_progress_ui.py:213`, and
`motion_test.js` (the fake-clock counter).

## 3. Motion vocabulary

Five verbs. Every effect in this note is one of them, and an effect that is none of them is not proposed.

| Verb | Means | Looks like | Used for |
|---|---|---|---|
| **Press** | "I heard you" | 120 ms colour and a 1 px press. Already exists | Buttons, links |
| **Write in** | "this is new" | Opacity 0 to 1, rows top-down, 140 ms each, 20 ms apart, capped at eight | The first rows of Results on arrival; a new line in a list |
| **Dim**, and **un-dim** | "still waiting, the old answer is the best there is"; and "the wait ended" | Dim to .85 after 160 ms of waiting, never blanked; the new page starts at .85 and settles in 160 ms. The un-dim exists **only after a dim**, so a quick answer has no cue at all | A slow answer (a tab, a filter, a sort); a figure being re-priced |
| **Open** | "a thing appeared where you pressed" | Height, the gap above it and opacity together, 200 ms in and 140 ms out, in place | Filter and sort, Export, menus |
| **Mark** | "an authoritative state changed" | Opacity 0 to 1 in 160 ms on the element that names the new state, only after the server said so | A Progress ending; a résumé finishing reading |

What is deliberately absent: **travel** (no element slides, rises or flies in; the only distance anything moves is the
height of a panel opening), **scale**, **blur**, **spring or overshoot**, **stagger beyond eight items**, **parallax and
scroll-linked motion**, **a cue on a quick navigation**, and any loop other than the existing "alive" pulse.

## 4. Timing and easing tokens

Three layers, as the design-system skill lays them out. They live at the top of
[`motion-proposed.css`](prototype/motion/motion-proposed.css). Every one is used (the first draft had twelve tokens for
four effects, two of them unused and one an alias; the review said so and they were removed).

| Layer | Token | Value | Notes |
|---|---|---|---|
| Primitive | `--ms-2`, `--ms-3` | 160, 200 ms | Two durations carry everything; the other two sizes (120 ms press, 140 ms leaving) are a literal and a meaning token |
| Primitive | `--ease-settle` | `cubic-bezier(.22,.61,.36,1)` | **Already in `sweep.css`** (the activity fill, the rail): decelerating, no overshoot. Arrivals and settles |
| Primitive | `--ease-leave` | `cubic-bezier(.4,0,1,1)` | Accelerating. Departures only |
| Meaning | `--row-fade`, `--row-step` | 140 ms, 20 ms | One row writing in; eight rows is 140 + 7 x 20 = **280 ms** designed |
| Meaning | `--tool-in`, `--tool-out` | 200 ms, 140 ms | Leaving is quicker than arriving |
| Meaning | `--pending-dim` | **.85** | The lowest level at which every text colour stays AA on the ground colour (table below) |
| Component | the rules that use them | | `.arrive ... tr:nth-child(-n+8)`, `.swap .results-body`, `.t-in`, `.t-out` |

Contrast of the real text colours on the ground (`#03161c`) at each level, computed from the tokens:

| Text | Full | .85 | .7 | .5 (today's `.updating`) |
|---|---|---|---|---|
| Body `#d2e6ee` | 14.35:1 | 10.55 | 7.47 | 4.35 |
| Warm `#d7c3af` | 10.85:1 | 8.06 | 5.79 | 3.51 |
| Muted `#9f8e7b` (captions, "via", post age, file names) | 5.84:1 | **4.54** | **3.45** | 2.34 |
| Teal `#7ed6cd` | 10.91:1 | 8.12 | 5.84 | 3.58 |

D1's direction (section 4.5, A3) set .7 as the floor for any dimmed text, and D2 then *removed* the persistent dimming from
the feed and from applied and opened rows rather than use it. This layer dims a whole list, so it is held to a stricter
standard than the floor: .85, where the muted captions are still 4.54:1. The cost is a fainter cue, and .7 is an owner option
(section 15.6). It is a transient state, not a persistent marker, which is the difference from what D2 removed.

The brief's timing hypotheses, against what the screens supported:

| Interaction | Hypothesis | Chosen | Why |
|---|---|---|---|
| Control feedback | 100 to 160 ms | **120 ms** (existing) | Unchanged |
| Small state change | 140 to 200 ms | **160 ms** | The dim and the un-dim are the same size of event |
| Disclosure | 180 to 260 ms | **200 ms in, 140 ms out** | The panel is about 118 px tall; 200 ms reads as a reveal and is still cheap to interrupt |
| Page entrance | 200 to 280 ms | **280 ms designed**; measured 321 ms on 19 rows, 357 ms on 240 rows, 8 animated rows in both between the first and last running frame | Frame quantisation and the first frame's delay add 41 to 77 ms; the 240-row page adds layout |
| Initial Results reveal | subtle, capped | **8 rows on a desktop, 3 on a phone** | About six rows are above the fold at 1440 x 900 and about a card and a half at 390 x 844; animating rows nobody can see is pure cost |

Distances: **zero**. The rows change opacity only (a transform on a table row is not reliable in every engine, and nothing
needs to travel). This is the main way the proposal differs from the `arrive`, `rise` and `section-in` effects it
replaces, which move 6 to 8 px.

## 5. Page by page

Verdicts: **implement**, **simplify** (smaller than first imagined), **delete** (remove motion that exists), **omit** (leave
as it is, instant). The **Tool** column answers the brief's CSS, WAAPI or GSAP question: **no effect needs WAAPI or GSAP**.
Reduced motion is "none" unless stated, and state changes are instant and complete. Layout risk is low unless stated.

### A. Upload

| Effect | Purpose | Trigger and element | Duration, easing | Tool | Reduced | Risk | Verdict |
|---|---|---|---|---|---|---|---|
| A1 A file is accepted | Shows the list took it | Alpine `x-for` adds a `.picked-row` (keyed, so only the new row) | 160 ms opacity, settle | CSS | none | The row would replay if the list were replaced wholesale; it is not | **Implement** |
| A2 A file is removed | | `Remove` pressed | none | none | | Motion here delays feedback for the action just taken | **Omit** |
| A3 Dropzone hover and drag-over | Shows it is a target | `.drop.over` | 120 ms colour (press tier) | CSS | none | none | **Implement** |
| A4 Reading starts | Shows the long wait began | `sending` note (existing pulse) | existing | exists | existing | none | **Omit** (exists) |
| A5 Validation message | | `role="alert"`, `x-show="bad"` | none | none | | A fade would delay an alert | **Omit** |

### B. Unified Review

| Effect | Purpose | Trigger and element | Duration, easing | Tool | Reduced | Risk | Verdict |
|---|---|---|---|---|---|---|---|
| B1 Reading to ready | Notice that one résumé finished while reviewing another | `reading.js` `refresh()` replaces each non-open card with `importNode`; a status differs from the last | 160 ms opacity **on the status word and marker only** | CSS, plus `reading.js` (one class) | none | **The replace kills any CSS transition and would replay an entrance on every refresh**, so it cannot be a rule on `.resume`. It needs `refresh()` to note which card's status changed and set a one-shot class | **Simplify**: status marker only, flagged by the diff, or omit. Touches `reading.js` and `reading_test.js` |
| B2 Résumé expansion and collapse | | The open résumé is chosen by `?track=`, a **navigation**, not a toggle | | none | | Nothing in-page to animate | **Omit** |
| B3 Moving between résumé sections | | Same navigation | | none | | | **Omit** |
| B4 `Adjust what Sweep looks for` | | Native `<details>` | | none | | Height on `details` needs `::details-content`, Chromium only | **Omit** |
| B5 Validation feedback | | `role="alert"` banner | none | none | | | **Omit** |
| B6 Reading skeleton | Honest "working" | `bone-sweep` | existing, reduced handled | exists | | Restarts on refresh; it loops, so harmless | **Keep** |

### C. Configure

| Effect | Purpose | Trigger and element | Duration, easing | Tool | Reduced | Risk | Verdict |
|---|---|---|---|---|---|---|---|
| C1 The live price | Show the figure is in flight and then final | `est` changes (`x-effect="sweepCount"`) | **No tween.** The new figure is written at once; `.updating` dims it while a question is out | delete the `motion.js` tween; CSS | dim is state, same | **A stale figure must never look current**: the dim is on from the change until the newest answer, as `price.js` already guarantees | **Delete** the counter; **simplify** the dim to `--pending-dim` (.85) |
| C2 Meter fill | | `.meter-fill` width | 160 ms (from 350) | CSS | none | Console only | **Simplify** |
| C3 Cap crossed | The one cost-safety cue | `.meter.over` is added | **No shake, no overshoot**: a 160 ms colour change and the existing words | CSS | none | Also plays on Confirm load today | **Simplify** |
| C4 Location picker menu | | `x-show="open"` | 120 ms opacity in, instant out | Alpine `x-transition` (CSS) | none | | **Implement** (small) |
| C5 `Advanced` | | Native `<details>` | | none | | as B4 | **Omit** |
| C6 `re-pricing` text, `Saving...` | | `x-show` | none | none | | A fade on transient text is flicker | **Omit** |
| C7 Disabled to available | | `:disabled` | existing 120 ms | exists | | | **Omit** (exists) |

### D. Confirm

| Effect | Purpose | Trigger and element | Duration, easing | Tool | Reduced | Risk | Verdict |
|---|---|---|---|---|---|---|---|
| D1 Initial presentation | | none today except the rail draw | | delete | | The rail draws the spend bar from zero on the first page of a session | **Delete** the rail and the tick |
| D2 Over-cap on load | The moment of discovery | server renders `.over` | as C3 | CSS | none | | **Simplify** |
| D3 Consent and capacity changes | | form state | none | none | | State changes are instant and complete | **Omit** |

### E. Progress

| Effect | Purpose | Trigger and element | Duration, easing | Tool | Reduced | Risk | Verdict |
|---|---|---|---|---|---|---|---|
| E1 Running | Liveness | existing pulse, indeterminate bar, determinate fill | existing | exists | existing end states | none | **Keep** |
| E2 An ending (finished, partial, stopped, failed) | The authoritative state changed | `p.state` flips (`x-show` on the ending blocks) | 160 ms opacity, **only after the state flips, never before** | Alpine `x-transition` (CSS) | none | Must not make a run look complete early: the animation is a consequence of the server's state, not a cause | **Implement** |
| E3 Tiles landing | A search really finished | `.cell.done` | 200 ms as today, **without** the column delays | CSS | none | The delay ramp is invented order | **Simplify** |
| E4 Feed arrival | A job really arrived | keyed `x-for` | 160 ms opacity, **no slide** | CSS | none | Only new rows animate, so a poll does not replay it | **Simplify** |
| E5 Waiting-screen entrance | | `.working` on load | none | delete | | | **Delete** |
| E6 The 1.2 s pause before Results | Lets the ending be seen | `setTimeout(..., 1200)` in `running.html` | | none (a decision) | | It delays a navigation the brief says not to delay without need | **Owner decision** (section 15) |

### F. Results (the prototype)

| Effect | Purpose | Trigger and element | Duration, easing | Tool | Reduced | Risk | Verdict |
|---|---|---|---|---|---|---|---|
| F1 Arrival | The list is new | `html.arrive` (reached from another page), first 8 rows (3 on a phone) | 140 ms opacity, 20 ms apart, settle | CSS + 15-line head script | none: rows are simply there | Hidden if the script fails? No: without the class nothing is hidden. Never replays (the class is removed 500 ms after the first frame). If the first section has fewer than 8 rows the later sections are static | **Implement** |
| F2 A quick tab, filter, sort, "Show all" | The list was replaced | a navigation answered within 160 ms | **none: an instant swap** | none | same | A cue here would be a dip (section 12). The crossfade that would soften it swallows a second press (section 9) | **Omit** (deliberately) |
| F3 A slow answer | Acknowledge the press, then end the wait | a same-page link or a valid GET form submit, 160 ms of waiting; on the next page `html.swap` | dim to .85 over 160 ms; the new page starts at .85 and settles in 160 ms | CSS + 22-line body script | dim kept, no transition | Armed on `submit` (after the browser's own validation), gives up after 10 s, cleared on a bfcache restore; all tested (T6, T15). **No `aria-busy`**: untested with a screen reader | **Implement** |
| F4 Filter and sort, Export | Something opened where you pressed | Alpine `x-transition` | 200 ms in, 140 ms out; height, gap, opacity | Alpine `x-transition` + CSS | none | Height is a layout property: measured, a small cost at worst (section 13). Chromium only; the classes exist only during the move | **Implement** |
| F5 Apply, Opened | | Row click opens a new tab | | none | | The reader has left the page; the motion would be unseen | **Omit** |
| F6 Applied tick (console) | | checkbox | | none | | | **Omit** |
| F7 Ending notice | | rendered with the page | | none | | | **Omit** |

### G. Shell

| Effect | Verdict |
|---|---|
| Tracker and step changes (navigation) | **Omit** |
| Run strip repaint (`/activity` polls every 8 s) | **Omit. It must never animate on a poll** |
| Feedback `<dialog>` open and close | **Simplify, optional**: a 160 ms fade with `@starting-style`; native focus handling is untouched |

## 6. What must not animate

- **A money figure.** It is written, never counted. (The counter is deleted.)
- **Anything on a poll.** The run strip, the Progress numbers, the feed's existing rows, the Results page (which does not poll). Motion attaches to a *state change* and a class that removes itself, never to a node that can be recreated.
- **A result row individually, beyond the first eight**, and never a row's position.
- **A quick navigation.** A tab, filter or sort that is answered at once has no cue.
- **Removing something you pressed**, and validation or error text (`role="alert"` must not wait for a fade).
- **Focus.** The prototype's scripts call `focus()` zero times and move no scroll position (checked, T9). The application's own code calls it in three places (the feedback dialog and the Configure picker), which this phase does not touch.
- **Loading percentages.** The indeterminate bar stays indeterminate; a determinate bar only when a real fraction exists.
- **Completion before the server says so.** An ending fades in after `p.state` changes, not as a flourish.
- **Tabs, steps and résumé cards** as if they were in-page toggles. They are navigations.
- **Anything while `prefers-reduced-motion: reduce` is set**, other than a state that is not motion (the dim).
- **Opened and Applied** (the reader is in another tab).
- **`will-change`** on a collection, `transition: all`, blur, parallax, scroll-linked effects, any new loop.

## 7. CSS, WAAPI or GSAP

Argued in ponytail's order: does it need to exist, what does the platform do, what is already installed, what must be
added.

| | CSS | Web Animations API | GSAP 3.15.0 |
|---|---|---|---|
| Arrival (rows written in) | 12 lines of rules. No script after the first paint | Possible; starts after the script runs, so it has the same pre-hide problem | 24 lines of script and 5 of CSS: a pre-hide rule, a failsafe timer, a reduced-motion branch and a cleanup (the spike) |
| Dim, un-dim | A keyframe, a transition and a class (3 lines) | Same result, more code | Same result |
| Tool panel | `interpolate-size` plus Alpine's class transition: 6 lines | Possible, and a bug magnet around `display: none` | Would fight Alpine, which owns `display` |
| Interruption | A CSS transition retargets from wherever it is, natively. Measured: five presses 60 ms apart leave the panel consistent | `reverse()` and `cancel()` work | `overwrite` works |
| Works if the script fails | **Yes: there is no animation script** (the head script only adds a class, and nothing is hidden without it) | No | **Only with a failsafe** |
| Added assets | 0 | 0 | **{"raw": 72927, "gzip": 28302, "brotli": 25706} bytes** |
| Sequences, scrubbing, timelines across elements | Not needed here | | What it is for |

**The genuine reason to test GSAP** was the one the brief names: coordinated choreography with interruption safety. The
hard cases in this app are **page navigations** (a tab, a filter, a sort, a résumé card). A navigation destroys the
document, so there is no timeline to keep, cancel or reverse: whatever moves lives in the new page for half a second and then
the class is gone. That is what CSS is for, and it is what the prototype uses.

So a GSAP spike was built for the one interaction that *could* have needed it, the arrival, and was run against the same
fixture with fault injection (`harness/verify-gsap.mjs`). **The first spike blinked**: rows appeared in order, vanished top
to bottom, then all popped in, because `clearProps` handed each row back to the pre-hide rule the moment its own tween ended.
The reviewer saw it in a filmstrip; the test had checked only the end state. It is fixed, and the test now counts frames on
which a row that had appeared gets *less* visible (7 with the bug, 0 after). Time until the first eight rows are
fully visible, from navigation start:

| Condition | CSS (proposal) | GSAP, written carefully (sync in `<head>`, pre-hide only if present, failsafe) | GSAP as tutorials show it (`defer` and a CSS pre-hide) |
|---|---|---|---|
| Nothing wrong | 332 ms | 312 ms | 440 ms |
| Script 1.5 s late | 463 ms (no script involved) | **1825 ms** (the sync script blocks the first paint) | **1808 ms** (rows hidden until it arrives) |
| Script blocked | 459 ms (no script involved) | 253 ms (no animation, content at once) | **never** (rows stay hidden) |

CSS figures vary between 332 and 463 ms from run to run (page load and fonts, no script involved), so read the
GSAP rows against that range: healthy and blocked are not meaningfully different from CSS; **late is +1.4 s**. Evaluating the
library is not the cost (median 0.2 ms at 1x and 2.6 ms at 6x to parse and run). The costs are 28 KB on every page that uses it, and a
choice between **blocking first paint** and **hiding content until a script arrives**, neither of which CSS has.

**Decision: no GSAP, no WAAPI, in D7B.** It would not improve choreography (nothing here is a sequence), maintainability
(the CSS is shorter than the GSAP), or interruption handling (a navigation cannot be interrupted from script, and the CSS
transitions retarget natively). **What would change this:** a screen that keeps state across many in-place updates and
needs a real timeline (a live, animated job-search map; an onboarding tour; a scroll-driven launch page). That is a
different product surface, and it is where a library would earn its bytes.

If GSAP is ever adopted, these are the answers the brief asks for:

| Question | Answer |
|---|---|
| Exact interactions | None today |
| Asset cost | 72,927 B raw, 28,302 gzip, 25,706 brotli, core only; zero dependencies; no `eval` or `new Function` (searched) |
| Version pinning | Vendored like `alpine-3.14.1.min.js`: the version in the file name, served from `/static`, never from a CDN (the same reasoning as `base.html`'s comment about Alpine on the credential page). **The prototype does not commit it**: `vendor/` is git-ignored and `harness/lib.mjs` fetches exactly `gsap@3.15.0` from npm on demand |
| Offline and CSP | Vendored, so offline. The app sends only `frame-ancestors 'none'` today; GSAP needs nothing more. Alpine's standard build needs `unsafe-eval` if a script-src is ever added, which is a separate issue |
| Reduced motion | `gsap.matchMedia()`, as in the spike |
| Cleanup on navigation | Each page is a fresh document, so there is nothing to clean; `matchMedia` cleanup if the preference flips |
| Alpine | Alpine owns `display` and classes (`x-show`, `x-transition`); GSAP must never animate the same property on the same element |
| Fallback | A failsafe timer that removes the pre-hide, and only pre-hiding when `window.gsap` exists (both in the spike) |
| **Licence** | GSAP's page says "free for everyone", but its own plain-English summary still says the no-charge licence applies "as long as end users are not charged a fee of any kind to use your product", and otherwise a Business membership. **This is an owner and legal question** if Sweep ever charges for access (section 15) |

## 8. Architecture and dependency implications

- **No build step, no React, no dependency.** Everything is `sweep.css` rules, Alpine attributes that already exist
  (`x-transition` is part of the vendored Alpine 3.14.1), and two small inline scripts.
- **Two scripts, both additive, 37 lines between them.** The head script (15 lines) adds `arrive` or `swap` to `<html>` and
  removes it 500 ms after the first frame. The body script (22 lines) marks the list pending if an answer takes over 160 ms.
  If neither runs, nothing is hidden and nothing is missing (tested with JavaScript off).
- **`motion-proposed.css` (36 lines) is the layer that D7B folds into `sweep.css`**, replacing the `Motion` block at 2038 to
  2133. It is inside `@media (prefers-reduced-motion: no-preference)`, the opt-in pattern: a browser that does not
  understand the query gets no motion, rather than the motion that the blanket rule has to remember to cancel.
- **Templates:** `results.html` gains a wrapper around the sections (it must keep the `.stack` layout, or the 32 px gap
  between sections is lost: a bug the first prototype had, caught by the pixel check T14) and two `x-transition` attributes;
  `base.html` gains the head script and loses the `first-paint` script. **Tests** change where section 2 lists.
- **Not touched:** the worker, polling, `reading.js` (unless B1 is accepted), `price.js`, `pick.js`, the routes.

## 9. The prototype

**What it is.** The real Results page, rendered by the application's own template through the same worker-backed harness the
Results tests use, with invented rows (19 jobs in three sections, every recommendation state, pay and experience on some
rows, a negative score; and a 240-job page with "Show all"). It is served by a 100-line standard-library server that keeps
production's URL shape (`/results?track=<id>`), so moving between views is a same-path navigation exactly as in the app. The
proposal is one 36-line stylesheet, a 15-line head script, a 22-line script at the end of the page, a wrapper `<div>` and two
Alpine attributes. `sweep.css` is untouched: the layer loads after it. At rest the proposal is **byte-identical to the
shipped page** in all six full-page screenshots (two widths, three views, check T14; the check was shown to fail, on all six,
when the wrapper lost its layout class).

**What it demonstrates**, against the brief:

| Brief | Where to see it |
|---|---|
| Page hierarchy appearing smoothly; heading and navigation readable at once | The heading, tabs, tools line, section heading and table header are on the first painted frame and never change. Sheet `01-arrival-*` |
| A restrained entrance for the initial visible rows | The first 8 rows write in top-down over 280 ms designed. Fully readable at 263 ms against 333 ms shipped (desktop). Sheet `01-arrival-proposed-*` |
| A responsive tab interaction | A quick tab is an instant swap; a slow one dims after 160 ms and un-dims on arrival. Sheets `02-tab-change-*` and `04-slow-server-*`. **At .85 the dim is faint enough to be hard to see in a still frame**; it needs the clip |
| An interruption-safe experience | Three tabs pressed 70 ms apart; five presses 60 ms apart on a tool panel; a stopped navigation; an invalid field. Sheet `07-interruption-*`, checks T7, T12, T15 |
| No repeated animation caused by unrelated state changes | Filter and Export toggles, a row click, a re-render of the rows, a resize and a visibility change start no entrance (T3); a reload starts none (T4) |

**How the design got here.** Four results changed it; all are kept in the evidence:

1. *The crossfade was wrong.* The first build moved between views with a cross-document view transition: the old list stays
   on screen and the two cross over. It is the smoother picture. Measured with three tabs pressed 30 to 120 ms apart, the last
   press was the one shown in **0 or 1 of 10 runs** (0/10 in the final run), against 7 to 10 of 10 on the shipped page
   (10/10 in the final run) and 9 or 10 of 10 on the proposal (10/10 in the final run). While a view transition plays the real page is not
   hit-testable (a press lands on `<html>`; `pointer-events: none` on the overlay does not change it). It does not exist in
   Firefox. It is kept as `motion-vt-alt.css` and recorded (`proposed-vt-desktop-normal.webm`).
2. *The height rule was wrong.* The first tool panel faded in place and I had written into the CSS that height was expensive
   because it "re-lays-out every row on every frame". Measured (median of five runs per cell, section 13), a 200 ms height
   animation on the 19-row and the 240-row pages at 1x and 6x CPU slowdown differed from an opacity fade by at most 9.1 ms per frame against 7.7 ms (the worst cell: 240 rows at 6x CPU), with worst frames of 17.4 against 16.7 ms. The
   comment was removed, and the panel now opens with height, the row gap and opacity together.
3. *An un-dim on every swap was wrong.* The second design made every new list arrive at .7 and settle. The reviewer pointed
   out that on a fast server that is a dip the effect itself creates. It now happens only when the old page had dimmed, so
   it ends a wait instead of starting a flicker, and a quick tab change has no motion at all.
4. *.7 was the wrong level.* Section 4's contrast table: at .7 the muted captions fall to 3.45:1. The level is .85.

**What it is not.** It does not filter; Apply filters reloads the same rows, which is what is needed to see a same-screen
navigation. It covers Results only. It has been run in Chromium 151 only: not in Safari or Firefox (see 15.5). It is not
wired to any route.

## 10. Recordings

Real browser (headless Chromium 151 via Playwright 1.62.1), real time, one continuous take per clip, 25 fps VP8 WebM,
1440 x 900 and 390 x 844 (touch). Fonts are the real ones, already cached before the take, so no clip shows a font swap a
second visit would not have. **Not slowed.** A cursor and a press ring are drawn into the recording so you can see what is
pressed; each clip starts and ends with a 160 ms white sync flash, which is how the trace's clock was aligned with the
video's (which runs 47 to 95 ms short of wall time over a 10 to 24 s clip, corrected in every timestamp below).
All paths are relative to the repository root and the files are git-ignored.

| Clip | Length | Size | What it is |
|---|---|---|---|
| `output/design-D7A/recordings/proposed-desktop-normal.webm` | 00:24.08 | 2.3 MB | **The proposal**, the complete sequence |
| `output/design-D7A/recordings/baseline-desktop-normal.webm` | 00:24.04 | 2.3 MB | The page **as it ships today**, same sequence (the comparison) |
| `output/design-D7A/recordings/proposed-desktop-reduced.webm` | 00:24.00 | 2.3 MB | The proposal with **reduced motion** on |
| `output/design-D7A/recordings/baseline-desktop-reduced.webm` | 00:24.00 | 2.4 MB | The shipped page with reduced motion on |
| `output/design-D7A/recordings/proposed-mobile-normal.webm` | 00:19.40 | 0.8 MB | The proposal at 390 px, touch |
| `output/design-D7A/recordings/baseline-mobile-normal.webm` | 00:19.36 | 1.2 MB | Shipped, 390 px, touch |
| `output/design-D7A/recordings/proposed-mobile-reduced.webm` | 00:19.44 | 0.7 MB | The proposal at 390 px with reduced motion |
| `output/design-D7A/recordings/proposed-desktop-slow-server.webm` | 00:10.68 | 0.9 MB | Every answer held 700 ms: the list dims, then un-dims on the new page |
| `output/design-D7A/recordings/baseline-desktop-slow-server.webm` | 00:10.80 | 0.9 MB | Shipped, same slow server |
| `output/design-D7A/recordings/proposed-mobile-slow-server.webm` | 00:09.68 | 0.3 MB | Slow server at 390 px |
| `output/design-D7A/recordings/proposed-vt-desktop-normal.webm` | 00:24.00 | 2.6 MB | **Alternative, not proposed**: a view-transition crossfade on every move (watch the interruption step: presses are lost) |
| `output/design-D7A/recordings/gsap-desktop-normal.webm` | 00:24.04 | 2.2 MB | **GSAP spike**: arrival only (its tab changes are instant) |

**Where to look in `proposed-desktop-normal.webm`** (each step begins when the cursor starts to move; the press lands about
0.4 s later). The other desktop clips run the same sequence to within about 0.3 s.

| Video time | What happens | What to watch |
|---|---|---|
| 0:00.7 | arrive from the Running screen | The list writes in top-down; the heading, tabs and tools are already there |
| 0:02.7 | tab: Backend Engineer | An instant swap: nothing moves but the list changing |
| 0:04.6 | tab: Full Stack Web Developer | Same |
| 0:06.5 | tab: Platform Engineer | Same |
| 0:08.4 | tab: All Jobs | Same |
| 0:10.4 | interruption: three tabs pressed 70 ms apart | Three tabs in 140 ms: the page settles on one of them (the last, in 9 of 10 runs); nothing flickers or sticks |
| 0:12.3 | Filter and sort: open | The panel grows in place, pushing the list down; the cursor ring marks the press |
| 0:14.0 | Export: open (Filter closes) | Filter closes (140 ms), Export opens (200 ms) |
| 0:15.7 | Export: close | Closes in 140 ms |
| 0:17.1 | Filter and sort: open, Apply filters | The panel opens; then Apply filters reloads the page: an instant swap |
| 0:20.4 | Back | Back to the previous view: instant |

Mobile (`proposed-mobile-normal.webm`, taps do not glide so the steps are closer together): 0:00.7 arrive from the Running screen; 0:02.7 tab; 0:04.1 tab; 0:05.4 tab; 0:06.8 tab; 0:08.2 interruption: three tabs pressed 70 ms apart; 0:10.1 Filter and sort: open; 0:11.4 Export: open (Filter closes); 0:12.6 Export: close; 0:13.5 Filter and sort: open, Apply filters; 0:15.7 Back.
Slow server (`*-slow-server.webm`): 0:00.7 arrive from the Running screen; 0:03.4 tab (slow server): Backend Engineer; 0:06.0 tab (slow server): Platform Engineer. Watch the old list dim about 160 ms after each press, and the new list arrive 700 ms later
already dimmed and settle (faint at .85: look at the text, not the page); the shipped page shows nothing for the whole 700 ms.

**Representative frames** are in `output/design-D7A/frames/` (23 sheets, real frames with their real times, 40 ms apart): `01`
arrival, `02` tab change, `03` reduced motion, `04` slow server, `05` tool panels, `06` the view-transition alternative,
`07` interruption, `08` the GSAP spike. Filmstrips are the nearest thing to the video that I and the reviewer can read; they
are not a substitute for playing it. **Two limits of the footage:** 25 fps cannot resolve a 20 ms row step (it is under one
frame), and a headless browser does not show the jank of a real device.

## 11. Normal against reduced motion

Reduced motion is an alternative, not a subtraction: each cue that motion carried is carried by something that is not motion.

| Moment | Normal | Reduced | What still says it |
|---|---|---|---|
| Arrival on Results | First 8 rows write in over 280 ms | Rows are simply there at once. **Nothing is animating on any frame** (T5) | The heading count, the table |
| A quick tab, filter or sort | An instant swap | The same instant swap | The heading's words change ("4 jobs evaluated for Backend Engineer"), the current tab is underlined and has `aria-current` |
| A slow answer | The list dims to .85 after 160 ms; the new page un-dims over 160 ms | **The same dim**, without the 160 ms transition; the new page appears at full strength | The dim is a state, not motion, so it stays |
| A tool panel | Opens over 200 ms (height, gap, opacity) | Opens at once, complete; across 20 frames there is no half-open or hidden-but-present frame (T12c) | `aria-expanded`, the panel itself |
| Pressing a button | 120 ms colour, 1 px press | Instant | The colour |
| A running search | The one pulse; the indeterminate bar | Static shapes (today's explicit end states, kept) | The words "Sweep is searching" |

What is deliberately not done in reduced mode: no fade as a consolation, no shortened animation, no smaller distance. Every
animation rule in the layer sits inside `@media (prefers-reduced-motion: no-preference)`, so a browser that does not
understand the query gets no motion at all. The recordings `proposed-desktop-reduced.webm` and `proposed-mobile-reduced.webm`
run the full sequence with the preference on; the sheets `03-reduced-*` show the same moments as `01` and `02`.

## 12. Independent critique

**Who and how.** A fresh `general-purpose` subagent that had no part in building the prototype, read-only, given the brief's
ten criteria, the Vercel animation rules and the evidence paths. It could not play video and said so; it read the filmstrips
(real frames from the recordings), the traces and measurements, the CSS and scripts, and it was asked to audit the draft note
for claims the evidence does not support, and to recommend deletions. It made 78 tool calls over 13
minutes. Its findings and what was done:

| Criterion | Reviewer's rating | Its evidence and what followed |
|---|---|---|
| Perceived responsiveness | Adequate | Tab change readable at 144 ms against 328 ms; but the dim level was never shown at the level proposed. **Then:** level changed to .85 for AA and the clips re-recorded at it |
| Restraint | Adequate | Twelve tokens for four effects, two unused and one an alias. **Then:** pruned to the ones used |
| Timing | Adequate | Every duration inside the brief's ranges |
| Quiet Ledger consistency | Adequate | D2 had *removed* opacity dimming as an AA failure; this layer puts dimming back on a whole list. **Then:** held to a stricter standard than D2's floor (.85, AA for every text colour, section 4), and labelled as transient, not a persistent marker |
| Visual hierarchy | **Strong** | Tabs, tools and headings bright at t = 0; the shipped page fades the section heading and notes with the list |
| Interruption | Adequate | T7 last-press counts are noise (baseline 10/10 in one run, 7/10 in the next); a stuck pending state was untested. **Then:** T7 reported as ranges over runs, and T15 added |
| Accessibility | Adequate | No-JS, keyboard and reduced motion pass; `aria-busy` on a plain `div` has no tested effect; muted text at .7 is 3.45:1. **Then:** `aria-busy` dropped; level .85 |
| Mobile | Adequate | The mobile arrival animates 3 rows; one first frame at 390 px shows `Export...` wrapped. **Then:** traced to the page's own font swap, not the layer (below); in the re-recorded sheet, with the fonts cached, the first frame is already in its final layout |
| Performance | Weak to adequate | Animating-frame counts 31/9/5 against 55/49/42; "row opacity looks main-thread bound". **Then:** tested directly (below); not supported |
| GSAP against CSS | CSS wins | The decision is right but the comparison is not evidence while the spike blinks. **Then:** spike fixed, dip detector added and shown to catch the bug |

**Deletions it recommended, and what I did:**

| Recommendation | Done | Why |
|---|---|---|
| Delete SWAP (the un-dim on every tab change) | **Accepted in part** | On a fast server it is a dip the effect creates. It now exists only after a dim (continuity, not a cue), so a quick tab change is an instant swap |
| Collapse the arrival stagger to one fade | **Not accepted; flagged for the video** | The brief asks for a capped stagger, and it is the only distinctive part of the entrance. Two of the reviewer's reasons did not hold (next paragraph). One did, and is stated: if the first section has fewer than 8 rows the later sections are static |
| Drop unused tokens; drop `aria-busy` | **Accepted** | |
| Keep the tool panels | **Kept** | The `margin-top` does hard-wire `.bar`'s row gap (`--s3`); now commented |
| Keep pending but fix it | **Accepted** | Armed on `submit`, 10 s give-up, same-page links covered, tested red and green |
| Drop the GSAP vendor file, the spike and the view-transition alternative from the commit | **Accepted for the vendor file; kept for the other two** | The 73 KB library is fetched on demand instead of committed. The spike (29 lines) and the alternative (15 lines) are what the numbers in sections 7 and 9 were measured with |

**Defects it found, all objectively demonstrable, and their resolution:**

| Defect | Resolution |
|---|---|
| Evidence older than the code: fixtures rebuilt and CSS edited after the recordings; the note and `verify.json` disagreed on .7 and .85; the first wrapper had no `.stack` | All evidence regenerated from the final prototype in one pass (one comment in `motion-proposed.css` was reworded afterwards; no rule changed); the wrapper fixed, and T14 (pixel identity at rest, 6 of 6) added and shown to fail against the old wrapper |
| The dim could stick: an invalid number field in the filter form fired the click handler but never navigated, leaving the list dimmed until reload; so could Esc during a slow answer | Armed on `submit` (fired only after validation), a 10 s give-up, and the un-dim flag cleared with it. T15 covers the field, the stopped navigation and which links count, and **fails against the old script** (`pending: true, flag: "1"`) |
| Layout shift of 0.0374 on the Full Stack tab in the proposal against 0.0002 shipped, in the traces but never sampled by T8 | Investigated, below: my font-pinning harness, not the layer. T8 now samples every view |
| The GSAP spike blinked | Fixed; the new detector caught the original bug (7 dips) and passes the fixed spike (0) |
| Stale comments (`opacity only, no height`; the `0 of 5` figure; "no dropped frame") | Corrected; the dropped-frame claim is now "at most a small cost, median of 5, headless" |
| Pending covered only tabs and the filter submit | Now any same-page link and any valid GET form; export and Apply links are excluded and tested |
| Arrival class removed on a timer from head parse | Now from the first frame |

**Claims in the draft note that the evidence did not support, and their correction.** The reviewer listed 13; every one was
fixed: "zero `focus()` calls" (now scoped to the prototype's scripts; the app has three); "GSAP strictly worse when slow or
missing" (now: worse when slow, equal when blocked if written carefully, invisible when deferred and blocked); ".7 is D2's
floor" (now D1's floor, which D2 then declined to use); the Motion block line (2038); the script sizes (now 15 and 22 lines);
the measured arrival (now the T2 figures); the last-press counts (now ranges over runs); "opacity and height" (now with the
row gap); the T10 gate's slack (stated, with the new click-to-paint measure); "height costs nothing" at n = 1 (now median of
five, headless caveat); "six things deleted (section 14)" (section 14 now lists them); the unfilled GSAP table (filled from
the data); and "four durations are enough" (two are used).

**Two of its inferences tested and not supported.**

1. *The font-swap CLS.* With fonts replayed through a request route (my harness), the route answered asynchronously, so the
   fonts were still "loading" at first paint and a table row moved 3 px: 0.0374 in the proposal, against 0.0002 shipped
   because the shipped section was still at opacity 0 (the shift was invisible). With fonts blocked, both pages scored 0; with
   real cached fonts, both scored 0; on a genuine first visit with the cache cold, desktop was 0.0016 to 0.0017 shipped
   against 0.0004 to 0.0020 proposed, and 0 on mobile in both. The shift is the page's own `font-display: swap`, which the
   shipped entrance fade happens to hide. The harness now warms the real HTTP cache instead of replaying fonts.
2. *"Row opacity looks main-thread bound".* The reviewer read animating-frame counts (31/9/5 against 55/49/42 at 1x/4x/6x).
   Those counts measure how many frames ran while an animation was running: the proposal's animation is 280 ms against the
   shipped 480 ms, and on the 240-row page it begins while the main thread is laying out. Tested directly: with the main thread
   deliberately jammed (45 ms busy in every 60), the recorded brightness ramp of the first rows was the same length as idle
   for the shipped section fade (7 frames) and for my row fade (4 frames). I cannot prove compositor promotion from here, and
   the shipped fade and mine behaved alike.

**What needs the video** (the reviewer's list, and the answers I cannot give): whether the 20 ms stagger reads as a sequence
at all; whether .85 reads as "waiting" on a slow answer (it is the fainter of the two options, and in the filmstrips the dim is barely visible, so this is the judgement most likely to go the other way);
frame pacing of the panel's height animation on a real display; the mobile first frame; and the reduced-motion clips.

## 13. Performance and accessibility observations

Every check below is in `harness/verify.mjs` or `harness/verify-gsap.mjs` and was run against the final prototype in
headless Chromium 151.0.7922.34. 28 of 28 checks pass. Absolute frame times are this machine's and a headless, non-vsync
clock: the comparison between the shipped page and the proposal is what they establish.

| Check | What it establishes | Result |
|---|---|---|
| T1-baseline | no JavaScript: every row is readable (baseline) | pass |
| T1-proposed | no JavaScript: every row is readable (proposed) | pass |
| T2 | entrance animates at most 8 elements and lasts the same (and under 400 ms, frame-quantised) for 19 and 240 rows | pass |
| T2-baseline | for the record: what ships today animates whole sections (fixed count), at every load | pass |
| T3 | after the arrival: tool toggles, a row click, a re-render of the rows, a resize and a visibility change start no entrance | pass |
| T4 | proposed: a quick tab, a quick filter apply and a reload are instant swaps: no row entrance, no list animation, no view transition | pass |
| T4-baseline | for the record: today a tab, a filter and a reload each replay the section entrance | pass |
| T5 | reduced motion: no arrival, no swap, no animation on any frame, the tool panel opens at once, nothing is missing | pass |
| T6 | slow server (700 ms): untouched at 60 ms, marked pending by ~200 ms and settled at .85 (AA for every text colour) once the 160 ms transition has run; the new page starts at .85, un-dims once, and is clean | pass |
| T6b | a page restored from the back/forward cache keeps neither a pending class nor the un-dim flag | pass |
| T7-baseline-fast | three tabs pressed 30/50/70/90/120/30/50/70/90/120 ms apart: a real view, nothing stuck, nothing running, no error (baseline, fast) | pass |
| T7-parity | the proposal drops no more last presses than the shipped page does, within one run of 10 (a press during a navigation is the browser's to keep or lose) | pass |
| T7-proposed-fast | three tabs pressed 30/50/70/90/120/30/50/70/90/120 ms apart: a real view, nothing stuck, nothing running, no error (proposed, fast) | pass |
| T7-proposed-slow (700 ms) | three tabs pressed 30/50/70/90/120/30/50/70/90/120 ms apart: a real view, nothing stuck, nothing running, no error (proposed, slow (700 ms)) | pass |
| T7-vt-alt | for the record (the alternative, not the proposal): with a cross-document view transition the last-pressed tab is shown in 0/10 runs | pass |
| T8a | no horizontal overflow on any frame of any page, 1440 and 390 | pass |
| T8b | layout shift on every view (All Jobs and all three résumés, arrival and tab changes, 1440 and 390): within 0.004 of the shipped page and far under the 0.1 "good" line | pass |
| T9-baseline | keyboard (baseline): Tab reaches Filter and sort, Enter opens it, Space closes it, focus stays on the button, the script moves no focus | pass |
| T9-proposed | keyboard (proposed): Tab reaches Filter and sort, Enter opens it, Space closes it, focus stays on the button, the script moves no focus | pass |
| T9c | after a tab is chosen from the keyboard, focus lands exactly where it does on the shipped page (nothing is moved by the prototype) | pass |
| T10 | CPU throttled 1x/4x/6x on the 240-row page, median of 3: the proposed arrival is no worse than shipped (within 30 ms and one slow frame), and a click opens the panel in ~one transition | pass |
| T11 | measured, median of 5: height vs opacity animation of a tool panel, 19 and 240 rows, 1x and 6x CPU (headless, non-vsync clock: a relative measure, n=5; data for the decision, see the note) | pass |
| T12a | the panel grows from 0 to its natural height, ends with no clip, no margin and no leftover class, and closes to nothing | pass |
| T12b | five presses 60 ms apart leave it open, at natural height, consistent with aria-expanded, with nothing left clipped | pass |
| T12c | reduced motion: across 20 frames of opening a panel there is no partial frame (no hidden-but-present state) | pass |
| T13 | time from navigation start until the first six rows are visible / half opaque / fully readable (effective opacity), shipped vs proposed, arrival and tab change | pass |
| T14 | at rest (reduced motion, so nothing is in flight) every screenshot of the proposal is byte-identical to the shipped page: 2 widths x 3 views, full page | pass |
| T15 | the dim cannot stick: an invalid number field does not dim; a navigation stopped mid-flight clears itself within 10 s; same-page links dim, export and Apply links do not | pass |

**Time until the list is readable** (first six rows, effective opacity, from navigation start; the shipped page animates the
section, so effective opacity is the product up the tree):

| View | Arrival: shipped | Arrival: proposed | Tab change: shipped | Tab change: proposed |
|---|---|---|---|---|
| desktop first pixel / half / readable (ms) | 49 / 149 / **333** | 54 / 180 / **263** | 46 / 145 / **329** | 36 / 36 / **36** |
| mobile first pixel / half / readable (ms) | 64 / 164 / **347** | 4 / 114 / **198** | 45 / 145 / **328** | 30 / 30 / **30** |

The shipped page's whole-section fade is slower to readable than the proposed rows in every case, and a quick tab change is
instant.

**CPU throttled, 240-row page, median of three** (the long page is dominated by laying out the rows, which is the same for
both; no cost of the proposal is visible beyond the run-to-run noise). The last column is a real press on Filter and sort, from input to
the browser being able to paint (Event Timing; under 16 ms is not reported):

| CPU slowdown | Page | Worst frame (ms) | Frames over 50 ms | Longest animation frame (ms) | Real click to next paint (ms) |
|---|---|---|---|---|---|
| 1x | shipped | 75 | 1 | 75 | 40 |
| 1x | proposed | 62.9 | 2 | 58 | 48 |
| 4x | shipped | 166.6 | 3 | 154 | 64 |
| 4x | proposed | 153.6 | 4 | 140 | 56 |
| 6x | shipped | 166.5 | 6 | 169 | 72 |
| 6x | proposed | 158.2 | 6 | 162 | 80 |

At 6x the proposal's real press reaches the next paint in 80 ms against 72 ms shipped (+8 ms), well inside the 200 ms "good" line. I did not isolate the cause of any difference.

**Panel height against opacity** (a 200 ms height animation, a 160 ms opacity fade; median of five runs per cell; frames are
a headless clock near 130 Hz, so a 16.7 ms worst frame is about two display ticks, not a dropped 60 Hz frame):

| Panel animation | List | CPU | Median worst frame (ms) | Median mean frame (ms) | Slowest run (ms) |
|---|---|---|---|---|---|
| opacity | 19 rows | 1x | 16.7 | 7.7 | 17.3 |
| height | 19 rows | 1x | 16.3 | 7.8 | 16.8 |
| opacity | 240 rows | 1x | 16.5 | 7.8 | 16.8 |
| height | 240 rows | 1x | 16.8 | 7.9 | 17.7 |
| opacity | 19 rows | 6x | 9.2 | 7.5 | 17.5 |
| height | 19 rows | 6x | 16.1 | 7.8 | 17.3 |
| opacity | 240 rows | 6x | 16.7 | 7.7 | 17.5 |
| height | 240 rows | 6x | 17.4 | 9.1 | 17.6 |

**Layout shift** (T8): worst CLS baseline 0, proposed 0.0001. **Overflow:** none on any frame of any page at 1440 or 390. **Stagger cap** (T2): 321 ms on 19 rows, 357 ms on 240 rows, 8 animated rows in both.
**Focus:** no `focus()` call, and after a tab is chosen from the keyboard focus lands exactly where it does on the shipped page
(the `<body>`, because the page is a navigation); a keyboard user starts again from the top of the page on every tab, which is
a D6 polish candidate and not motion (section 16). **Keyboard:** Tab reaches Filter and sort, Enter opens it, Space closes it,
focus stays on the button. **No JavaScript:** every row readable. **Contrast:** section 4.

**What was not measured.** Safari and Firefox (not installed here); a real phone; the compositor's layers; anything over a real
network. The height reveal and the dim are Chromium-verified only.

## 14. Proposed production scope (D7B)

Not started, and not to start without owner approval of the clips and of section 15. Each step is its own commit, in this
order, with a stop for review after each, as every phase so far.

**The six deletions**, which carry most of the value: (1) the `sweepCount` money tween; (2) the spend rail draw, the cap tick
and the head script behind them; (3) the cap overshoot and shake; (4) the waiting-screen `rise`; (5) the tile column-delay
ripple; (6) the `.reveal` section entrance that replays on every load. Plus two simplifications of things that stay: the feed
arrival loses its slide, and the price dim moves to .85.

**D7B-1. Tokens and Results (effects F1, F3, F4) and the deletions that belong with them.**
- `sweep.css`: replace the `Motion` block (lines 2038 to 2133) with the layer in
  [`motion-proposed.css`](prototype/motion/motion-proposed.css) (36 lines, inside `prefers-reduced-motion: no-preference`);
  keep the four existing reduced-motion end states; keep the blanket rule as a net for everything else until D7B-4.
- Delete items 2 and 6 above here, and the `.cell` column delays; the `.updating` figure dim moves to `--pending-dim`.
- `results.html` and `base.html`: the 15-line head script scoped to Results (a `{% block head %}` or a script in
  `results.html`'s own head area), so no other page pays for it; the wrapper around the sections with the `.stack` class; two
  `x-transition` attributes; the 22-line script at the end of the page. The markup otherwise unchanged.
- Tests to change on purpose: `test_results_ui.py:303`, `test_app.py` around 5040 to 5141. Tests to add, written first and
  watched to fail against `7487f3d`: (a) the head script is one class and never hides a row; (b) no `will-change` and no
  `transition: all` anywhere; (c) every animation rule is inside `no-preference`; (d) the stagger cap is 8 and 3; (e)
  `--pending-dim` is at least .85; (f) the wrapper carries `stack`; and, in a real browser, the measured checks that
  `harness/verify.mjs` already makes (T2 to T7, T12, T14, T15), kept as a script outside the unit suite.
- Acceptance: T1 to T15 pass against the real `results.html` (not the fixture); one-résumé and three-résumé runs; public and
  operator modes; checked by hand in Safari and Firefox.

**D7B-2. Progress (E2 to E5).**
- Ending banners: Alpine `x-transition.opacity.duration.160ms` on the `x-show` ending blocks, nothing before `p.state`
  changes. Tile landing without the column delays. Feed arrival at 160 ms with no slide. Delete the `.working` rise.
- Tests: the Running screen's state machine is untouched and its tests must pass unchanged (`test_progress_ui.py`,
  `test_terminal_states.py`); add one that every ending block keeps its text when the transition never runs.

**D7B-3. Configure, Confirm and Upload.**
- Delete the `sweepCount` tween (keep the function, which then only writes the figure; keep `motion_test.js`'s "first call
  sets outright" assertion and replace the tween assertions). Shorten the meter fill to 160 ms. Replace the cap-cross moment
  with a colour change (15.2). Upload: the accepted-file row (160 ms) and the drop-zone hover (120 ms). Location picker menu
  fade (120 ms).
- Tests: `price_test.js` and `test_live_price.py` must pass unchanged: the price logic (only the newest answer counts, the
  figure is dimmed from the change until it is answered) is not touched.

**D7B-4. Reduced motion as an alternative, and the shell.**
- Replace the blanket `*{animation:none !important}` with the opt-in pattern already used by the layer, keep one small safety
  rule; make `motion.js` (or what is left of it) read the preference live.
- Optional: the feedback dialog fade (`@starting-style`); the Review status mark (B1) if the owner wants it, which touches
  `reading.js` and `reading_test.js`.

**Not in D7B:** GSAP, WAAPI, view transitions, any JavaScript animation library, any change to the worker, polling, prices,
scoring or exports, and the launch film.

**Release gates that D7B must not disturb** (each must still pass): the single-résumé P0 regression guard, the terminal-state
tests, the price-isolation tests, the public copy tests, and a visual check that every screen other than the ones named is
pixel-identical before and after at 1440 and 390.

## 15. Open questions for the owner

Ordered by how much they change the work.

1. **The money counter (`motion.js`).** It writes every intermediate dollar figure while a total changes. The brief forbids
   interpolating money, so the recommendation is to delete the tween and keep the dim while a price is being re-checked. This
   removes something the original Stitch motion spec asked for. *Approve the deletion?*
2. **The cap-cross moment.** Overshoot and a 500 ms sideways shake when an estimate crosses the cap, also played on Confirm's
   load. Recommendation: no shake; a 160 ms colour change and the words that already exist. The shake is the only dramatic
   motion in the product, and you may want exactly that for a safety cue. *Keep it, or simplify?*
3. **The 1.2 s pause before Results.** After a run finishes, the Running screen waits 1.2 s before redirecting
   (`running.html`, both polling and the stream). The brief says not to delay navigation unnecessarily. *Keep, shorten (for
   instance 600 ms), or go straight there?*
4. **A quick tab change: instant, or a cue?** The proposal is an instant swap, and a dim and un-dim only when an answer is
   slow. Two alternatives were built and set aside: an un-dim on every change (a dip on a fast server), and a view-transition
   crossfade (the prettier frame, but it drops a second press inside its 160 ms and does not exist in Firefox). *Does an
   instant swap feel right in the clips, or do you want the crossfade despite the lost presses?*
5. **Height animation is Chromium only.** `interpolate-size` is Chrome and Edge 129 and later; Safari and Firefox lack it
   (caniuse, checked 2026-09-30), so there the panel opens with the fade and closes at once. Cross-document view transitions
   are Chrome and Edge 126 and Safari 18.2, not Firefox. **I could not test Safari or Firefox here; D7B must be checked in
   both by hand.** *Accept that?*
6. **The dim level.** .85, because at .7 the muted captions are 3.45:1 (AA needs 4.5:1) and a slow answer can hold the dim for
   seconds. At .85 the cue is fainter: in the filmstrips (sheet `04-slow-server-proposed-desktop`) the old list at .85 is barely
   distinguishable from full strength, so the clip has to decide whether it reads as "waiting". *Keep .85, or accept .7 and
   the lost contrast (muted captions 3.45:1 while it lasts) for a clearer cue?* Either way, move Configure's price dim from .5
   (muted text 2.34:1) to the same level?
7. **The arrival stagger.** The brief asked for a capped stagger, and it is the most distinctive thing on the page, but it
   cannot be judged from 25 fps frames (the step is 20 ms). *If it reads as noise in the clip, the alternative is one fade of
   the first section's table; the stagger is what to drop first, not the arrival.*
8. **Operator-only items.** The rail draw, the cap tick and the meter width are console only. *Delete them with no public
   consequence?*
9. **The Review status mark (B1).** Worth a change to `reading.js`, or omit?
10. **GSAP.** The recommendation is none. If it is wanted for a later surface, its licence page still says the "no charge"
    licence applies while end users are not charged, and otherwise a Business membership is needed, although the same page
    says GSAP is now free for everyone. *If Sweep will ever charge for access, this needs reading in full before adoption.*
11. **The clips.** They are real-time but 25 fps, and the recorder's clock runs short of wall time by about 0.5%. *Do they show
    what you meant by "restrained"?* If the motion feels like too little, the lever is the row fade, not more effects.

## 16. Recorded for later (not part of D7A)

Final-release issues carried forward, unchanged by this phase: the saved-profile same-second bytecode caching
(`SWEEP_RELEASE_BLOCKERS.md` entry 1); the paid run with a complete ledger and a failed process reading as finished (3); the
worker's own `stopped` state not recovered after a web restart (4); public visibility of raw internal résumé-reading
diagnostics; unsaved expanded résumé-editor state on navigation; the remaining operator-header consistency.

Two small D6 polish candidates: make **Filter and sort** and **Export** easier to find without oversized primary buttons (the
review called the discoverability "bordering weak"); and consider **"jobs found"** instead of "jobs matched your profile" for
All Jobs, since negative scores are deliberately kept.

Observations from this phase that belong with the first list and are not motion: after a résumé tab is chosen, focus is on the
`<body>` (the page is a navigation), so a keyboard user starts from the top of the page on every tab (a skip to the list, or
returning focus to the current tab, is a polish candidate); the page's `font-display: swap` reflows on a first visit and is
hidden by the shipped entrance fade only while it lasts (preloading the fonts would remove the reflow); and on a phone the
default tap highlight shows as a teal block on a pressed tab (`-webkit-tap-highlight-color` is not set).
