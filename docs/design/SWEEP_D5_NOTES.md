# Sweep design, phase D5: Confirm and Progress

Branch `design/sweep-ui-overhaul`, starting at `78702ff`. Evidence is in `output/design-D5/`
(git-ignored, synthetic data only). Direction: [SWEEP_DESIGN_DIRECTION.md](SWEEP_DESIGN_DIRECTION.md)
(section 0 governs); earlier phases: [D3](SWEEP_D3_NOTES.md), [D4](SWEEP_D4_NOTES.md). This is a
presentation phase: nothing was changed in planning, pricing, AccountPool, capacity, approval,
the worker protocol, run ownership, polling, queue limits, timeouts, results or exports.
What D5 found that is **not** presentation is in [SWEEP_RELEASE_BLOCKERS.md](SWEEP_RELEASE_BLOCKERS.md).

## 1. What the old screens were

The D1 audit saw Confirm only as a free search and Progress only after it finished. D5 drove a real
worker app through every state first (queued, starting, working, part-done, free sources running,
finished, empty, failed, stopped, timed out, part-run, refused start), for one résumé and three, free
and paid, in the public app and in the operator console.

| Screen | Found |
|---|---|
| Confirm | a 56px amber `$0.00` was the loudest thing on a free search; the same "nothing is charged" said in three boxes; the action in a right-hand card, so **at the very bottom of a phone** after four stacked panels; an over-credit plan whose figure still painted amber; two primaries at once (the add-a-key submit next to a disabled run); the coverage numbers in a box separate from the cost they qualify |
| Progress (paid, public) | a real markup bug: the Searches section opened a `<div class="panel">` and closed a `</details>`, so the Latest matches panel sat **inside** it instead of beside it; an amber count of jobs; a giant amber "not known" tile for a spend a visitor's sweep never has; an amber "warn" banner; two primaries after a part-run |
| Progress (free, public) | three side panels repeating the page, plus a stages panel and a skeleton; the skeleton still promising a shortlist "lands here" after the run was over |
| Both | a part-run headed "Sweep stopped early"; a refused start offering to "finish the remaining 120 searches"; state carried by colour in places |

## 2. Confirm

One question, answered in reading order: **what is searched** (a ruled ledger), **what it costs**,
**whether it can be covered**, then **the action**. On a wide screen the decision is the right-hand
column beside the summary and its detail; on a phone it follows the summary directly, so the cost and
capacity are above the button. Nothing is pinned.

- **Free.** "133 free job boards" (the plan's own count; "Free job boards" if it has none), a teal
  "Free" tag and "No account is used and nothing is charged." No figure. A paid session with every
  metered source off gets the same treatment.
- **Paid.** The estimate is the one bordered figure, amber, labelled an estimate. Under it the capacity
  rows (available credit, searches covered), then a verdict: a teal tick only when the allocator says the
  full plan places; otherwise a coral "!" and the figure and its well turn coral. **A configured key is
  not shown as proof of credit**: the tick is the allocator's answer and nothing else.
- **Partial** is unchanged in contract and clearer in words: an unticked consent (`over_cap_ack`), the
  button disabled until it is ticked and naming the partial estimate, and "some searches will not run".
  A plan nothing can cover has no consent and no "$0.00" run. A refused or unavailable plan has a
  disabled primary, a neutral (not live-amber) estimate and the way back.
- **One primary.** Adding a key is a door under a rule, open only when the plan is short, and its submit
  is a secondary. The disabled primary is readable (warm text on an outlined fill), not the chalk fill at
  half opacity (it measured 3.3:1).
- Smaller: the job titles are one line of words (eleven chips took five rows on a phone); the price by
  source is two lines per source on a phone; an account is removed with the word "Remove" (a 44px target on
  touch); a refusal carries a "!" and is announced (`role="alert"`).
- **Operator.** Same composition, same copy, same over-cap remedies ("Start it anyway", "Narrow the search
  instead", another key, spend less); the hard stop is still stated beside the estimate.

## 3. Progress

What is happening now is the focus: one activity row (a shape, a word, the count, and a bar **only** where
the backend gives a true numerator and denominator). What it is working through sits under it as ruled
sections, not boxes.

- **Honest.** No percentage is shown for a free sweep (an indeterminate bar and "no exact count while the
  pass runs"); the paid determinate bar is `done / planned` from the engine's own ledger, as before. Nothing
  interpolates. The estimate is amber money and is never called a charge; "Spent so far" appears only in the
  operator console, only from the account's own reading, and is absent from a visitor's sweep, which has none.
- **Endings.** Each ends in words and a shape: a teal tick (every search ran), a coral "!" (credit ran out,
  credit changed, reason not recorded), a half-disc (**part of the search ran**, as the visitor chose), a ring
  ("you stopped it"). Amber is gone from banners. A part-run is headed "Part of your search ran", a refused
  start "Your search did not start" and a visitor's own Stop "You stopped the sweep".
- **One primary.** The banner's action wins (See the results / Back to Confirm); "Continue the sweep" is an
  outline beside it, filled only when it is the way on. A refused start offers only the way back.
- **Amber drained** from the count of jobs, the running cell and its legend, the inline source count.
- **Structure.** The public paid page is one sound structure (the Searches section is a real `<details>`,
  closed, with its legend in the summary); the free page's three panels are one door, "What Sweep searches,
  and how it ranks"; the skeleton goes when the run is over; a finished run that found nothing says so instead
  of "the first search has to finish".
- **Announcements.** The heading is the page's polite live region for the state (its words change only when
  the state does); the count that moves every poll is not one.
- Also fixed: the per-search cells were 9px (now 12px), a running cell's opacity pulse took its label to
  3.06:1 (the pulse is now the border's), and the meter's cap marker stood 1px outside its track and widened the
  page by a pixel on every console screen that shows a cap.

## 4. Shared CSS

`sweep.css` gained two marked blocks (Confirm, Progress) and five originals changed in place (`.cell.running`,
`.key.running::before`, `.numeral-inline b`, `.banner.warn`, `.meter-cap`, `.cell`). The amber ceiling in
`test_visual_rules` fell from 20 lines to 16. **Review, Upload, Configure, Results and Key are pixel-identical to
`78702ff` at 1440 and 390 (22 of 22).** The exception by design is the console's meter cap (1px), which was a bug.

## 5. Independent critique

A fresh reviewer, told to be adversarial and to judge only from the screenshots, answered the ten questions:
**strong** on free Confirm, primary prominence and the shared-CSS regression (byte-identical); **adequate** on
paid Confirm, partial approval, progress honesty, endings and "same product"; **weak to adequate** on how far a
phone has to scroll to the paid action (about 1,130px, the estimate at about 815px) before the fix.

Objective defects it found, all fixed and re-captured: an amber estimate for a plan whose paid search is unavailable;
a "$0.00" run offered when nothing is coverable; "All 0 of them" on a finished free run; the last pass of a finished
run drawn as still in progress; a refused start offering to finish searches that never ran; a finished run that found
nothing saying the first search had to finish; "so far" on a finished count; the running sub-label repeating its
number; a wrapped, squeezed activity label on a phone; the price rows wrapping a word per line; a refusal with no
shape; a bare "×". It also asked for stopped and failed to have different headings (done: "You stopped the sweep").

Not changed, and why: **the free-path failed and stopped states still read "Your jobs are ready"** (the worst honesty
gap it could see; it is state derivation, release blocker 2); the console header still shows an amber `$0.00` on a free
sweep and the header's "Credit left" is unchanged when paid search is unavailable (shared chrome, not these screens);
the per-search grid is behind a disclosure on the public paid page (its count and bar are not), which one reviewer
would rather have open; source chips Indeed and LinkedIn stay amber (they are the paid boards).

## 6. Decisions for the owner

1. **Release blockers** (separate document): the saved-profile bytecode issue, and the free-path failed/stopped state.
2. Whether the public paid page should show the per-search grid open rather than behind its disclosure.
3. The console header meter: muted zero on a free sweep, and whether it should say "Credit left" at all when paid
   search is unavailable.
4. The refused-start page now offers only "Back to Confirm". "Start a new sweep" (which only the old block carried)
   is reachable through the header's Sweep link.
5. Results, the Key step and the 404 remain for their phases; Confirm and Progress are no longer the odd ones out.

## 7. Verification

- **Focused tests:** 1,401 pass, 4 skipped (the Linux-only `RLIMIT_AS` checks), 467 s: the two new files
  (`test_confirm_ui`, `test_progress_ui`), D4.1 and D4.2's, `test_app`, the public, paid, guardrail, copy and
  active-run suites, both Multi-Track suites, unified review, results and exports, and the D2 to D4 visual rules.
  25 of the 33 new tests fail on `78702ff`; the rest hold behaviour both trees share. The Confirm commit alone
  passes in an exported tree (the one exception there is a test that reads the git-ignored `.env`, unrelated).
  Not run: the full release suite.
- **Browser flows** (real clicks, worker engine children released by the harness): one résumé (schema 1) and
  three (schema 2), each at 1440 and 390, Confirm through the start, the searching screen, a poll later with real
  counts, and the finish: 42 of 42 steps pass. For schema 2 no "jobs found" figure appears because the harness
  writes single-résumé rows and a Multi-Track run reads its own columns; nothing is counted rather than counted wrong.
- **Accessibility:** 0 text nodes under 12px on every state; worst text contrast 4.57:1 (the partial consent
  ticked), every other state 5.4:1 or better; every target 24px or more with a mouse and 44px or more on touch; a 2px
  chalk focus ring on every tab stop; headings h1 then h2 (then h3); reduced motion stops the activity dot, the
  running cell, the indeterminate bar and the fill's transition; the state is announced once, by the heading.
- **Overflow:** none at 1440 or 390 in any of the 85 captures (the console's 1px cap-marker overflow is fixed).
- **Model, provider, network:** none. The app ran on loopback with synthetic data and a worker whose engine child
  is released by the harness; no key, model call, paid search or Oracle/Modal. One independent reviewer subagent.
