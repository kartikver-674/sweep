# Sweep — Direction A integration plan (A0)

Direction A ("Sunny Desk") is the playful public reskin approved on the design canvas *Sweep Redesign Concepts*
(claude.ai artifact `JYtHonzFif4hGJqfYDVuhY`, page "Direction A · full flow": seven screens, desktop and phone, light and dark).
This file is the plan it is integrated by. A0 adds no application change: it fixes the decisions, the method and the baseline.

| | |
|---|---|
| Branch | `design/sweep-a`, from `652bf8d` (the D7C release candidate, pushed to `origin/main` and running on Render) |
| Rollback point | `652bf8d` |
| Scope | **Public mode only.** The operator console (local mode) keeps Quiet Ledger and stays pixel-identical in every stage |
| Cadence | One commit per stage (two when docs/evidence are split), focused tests, desktop + phone evidence in both themes, then **stop for review** |
| Evidence | `output/design-A<n>/` (git-ignored) with `docs/design/EVIDENCE_MANIFEST_A<n>.sha256` |

## 1. Owner decisions (2026-10-01)

1. The RC is pushed and deployed; it is the baseline every stage is compared against.
2. Design work stays on `design/sweep-a` until final review. No merge, push or deploy without an explicit ask.
3. Public screens only. Shared templates branch on `public_mode`; `sweep.css` keeps serving the console.
4. The D7B motion contract may be reopened where a move earns its place (§4). Every move has a reduced-motion state.
5. The theme follows the system (`prefers-color-scheme`); the header switch overrides it and is remembered per browser.
6. "Free / Paid" becomes "Quick Sweep / Deep Sweep" on public screens only — not in export files, not in the console.
7. The Apify claim is verified and may ship: the free plan includes $5 in monthly credits, no card required; usage varies.
8. The live feed may carry each listing's matched skills (a read-only addition to `live_items`) so Progress can say why a match matched.

## 2. How the skin is layered

- `sweep/static/sweep-a.css` is a new stylesheet that `base.html` loads **only when `public_mode`**, after `sweep.css`, and
  `<html>` gets `class="skin-a"` plus `data-theme` in public mode. The console never receives either, so it cannot change.
- `sweep.css` is already token-based (660 `var(--…)` uses: `--ground`, `--surface`, `--chalk`, `--paid`, `--free`, `--over`, `--control`,
  the type stacks). A1 re-points those tokens under `.skin-a` for light and dark. Layout and markup do not move in A1.
- A pre-paint inline script in `<head>` (public only) sets `data-theme` from `localStorage` or the system before first paint, so there is no
  flash of the wrong theme; `color-scheme` and `<meta name="theme-color">` follow it.
- Fonts: Bricolage Grotesque stays; Geist is replaced by Instrument Sans for public pages (one Google Fonts link per mode).
- Money keeps one colour. Quiet Ledger's rule "amber = money only" becomes "**peach = money only**" (paid boards, estimates, the jar).
- New screen markup lands per stage (A4–A9) inside the existing templates' `public_mode` branches, keeping every pinned hook
  (`<main>`, the skip link, no `tabindex` on /results, `.listings`, `class="src free"`, form field names).
- Interactions are progressive enhancement over the forms that already work: the server-rendered fields stay in the page and post the
  same contract; without JavaScript a visitor gets the plain form.

## 3. Stages

| Stage | Change | Acceptance |
|---|---|---|
| **A0** | This plan; branch; baseline evidence (104 at-rest states × 2 widths, the 11 browser flows, the `sweep/tests` suite) | Baseline captured and manifested; no application diff |
| **A1** | `sweep-a.css` tokens (light + dark), `skin-a` + `data-theme` on public pages, pre-paint theme script, header theme switch, Instrument Sans. Colour and type only | Every public state renders in Direction A colours in both themes with layout unchanged; console states identical to A0; contrast pairs pass in both themes; `test_visual_rules.py` keeps pinning `sweep.css`, and a new `test_visual_rules_a.py` pins `sweep-a.css` |
| **A2** | Shared parts: sticker buttons, chips, peeks (native `<details>`), the brush tip (dismissible), wavy-underline headings, stamps, phone stepper ("2 of 4"), sticky phone action bar | Pinned markup hooks intact; 44 px targets; reduced motion verified |
| **A3** | Copy: Quick Sweep / Deep Sweep on public screens; the verified Apify line | Copy tests updated deliberately, console and exports unchanged |
| **A4** | Upload (`/`, `/tracks`) and reading (`/derive`): hero, form with peeks, three-step trail, reading list, management list; the brush desk as `desk.js` (aria-hidden, button equivalent, static without JS) | Same form fields; one résumé and three; batch upload; `pick_test.js` |
| **A5** | Review (`/review`): résumé deck, experience chip, tap-to-tune skill chips over the existing `weight_editor` inputs | Same POST contract to `logic.reweighted()`; unsaved-edits guard still fires; one-résumé review has no deck |
| **A6** | Search coverage (`/key`, `/key/free`): radio cards, live coverage diagram, Deep setup one step at a time over the existing key form | Key never stored; a rejected key reopens the paste step; no-JS shows every step |
| **A7** | Configure + Confirm (`/configure`, `/estimate`, `/confirm`): credit jar fed by `price.js` and the real balance; ticket with peeks; second key and remove key kept | Estimate isolation contracts untouched; over-credit copy by real cause unchanged |
| **A8** | Progress (`/running`, `/progress`, `/events`): "Now: board · city" from the running tile, tiles behind a peek, brush rider, matches that open to their matched skills | Every ending keeps its words; ready-early redirect; `live_items` addition is read-only |
| **A9** | Results (`/results`, `/export`): job cards, "Why it matched", score explainer, "Top of the pile" | Recommendation, suggested résumé, raw/negative scores, All Jobs membership, export schemas, phone Apply target unchanged |
| **A10** | States the canvas did not draw: errors, empty, every terminal state, the active-run banner, beta/feedback, plan error, 404 — plus a full console check | Console identical to A0 |
| **A11** | Release hardening: full suite, 11 flows × 4 engines × 2 widths × 2 themes + reduced motion, at-rest comparison against A0, contrast audit, Safari by hand, staging deploy | RC verdict, then the merge/deploy decision |

## 4. Motion policy

D7B's five verbs (press, write in, dim, open, mark) stay as they are. Direction A adds only moves that tell the visitor something:

| Move | Where | What it says | Reduced motion |
|---|---|---|---|
| sweep (brush desk) | Upload | how Sweep sorts: strong matches stay, weak ones go | no parallax; cards jump to their places |
| pop | a file added, a tip opening, a tuned skill | something just arrived because you did it | appears without scale |
| pour / wobble | the credit jar | the estimate moved; it crossed your credit | fill changes instantly; a word, not a wobble |
| drop-in | Progress latest matches | a new listing arrived | appears in place |
| ride | Progress brush on the bar | the run is moving | static marker |
| bob | the brush tip's avatar | idle character, very slow | still |

Each move is CSS (plus `desk.js` for the desk), has a `prefers-reduced-motion` state, and is pinned in `test_motion.py` the way D7B's are.

## 5. Frozen contracts (no stage changes these)

The D7C list stands: recommendation semantics and "Suggested résumé"; raw scores (negative allowed); All Jobs and `track_evals` membership;
export schemas; the mobile Apply target; planning, pricing, AccountPool, quotas, provider execution; estimate isolation (D4.1) and scratch-profile
pricing (D4.2); the run endings (`incomplete`, worker `stopped`, timeouts, `charged_unknown`); the public privacy redaction; the unsaved-edits
guard. Plus the single-résumé P0: one résumé uses its existing path end to end, with no visual regression treated as acceptable.

## 6. Evidence and regression method

- **At rest:** `docs/design/motion-d7b/harness/regress.mjs` with `D7_OUT=output/design-A<n>`. A0 writes `regression-before/` from this tree.
  Each later stage writes `regression-after/` and `--compare`s against A0's. Expected differences: the public states that stage touched.
  Console states (`console-*`) must be identical in every stage.
- **Flows:** `docs/design/d7c/harness/flows.mjs` (W1–W10, H). A0 records the baseline; flows that assert old copy or markup are updated in the
  stage that changes them, never silently.
- **Tests:** each stage runs only the tests its change touches (named in its brief) plus the at-rest comparison and the relevant flows.
  The full suite (20–25 min) is the owner's, run on `main`; it is asked for at most once, in A11.

## 7. Working method

Implementation-heavy work goes to Sonnet 5.5 subagents from a precise stage brief (files, contracts, pinned hooks, acceptance tests);
planning, design calls, review of every diff and the accept/reject decision stay on Opus 5.5. Opus also keeps the parts where a
small mistake is costly: theme tokens and contrast (A1), the weight form contract (A5), pricing and credit (A7), the live-feed server
change (A8), release hardening (A11).

## 8. A0 baseline (recorded)

| Check | Result |
|---|---|
| Tree | `652bf8d` = `origin/main`, the deployed RC; branch `design/sweep-a` created from it |
| At rest | `output/design-A0/regression-before/`: **104 captured, 0 failed** (52 states × 1440 and 390; public and console) |
| Browser flows | `output/design-A0/flows.json`: **11 of 11 pass** on Chromium 151.0.7922.34; 0 page errors, 0 console errors |
| Suite | Owner ran the full suite on `main` (`652bf8d`) on 2026-10-01: all pass. Not re-run here |
| Manifest | `docs/design/EVIDENCE_MANIFEST_A0.sha256`: 146 files, all verify |

## 9. A1 theme foundation (recorded)

**Change.** `sweep/static/sweep-a.css` (new) re-points sweep.css's tokens under `html.skin-a` in three scopes (light base;
`prefers-color-scheme: dark` unless `data-theme="light"`; `data-theme="dark"`), re-declares the four places sweep.css hard-codes a
dark colour (the base `.chip` border at `.chip`'s own specificity via `:where`, the feedback backdrop, `.error`, table row hover),
and styles the switch. `sweep/static/theme.js` (new, not deferred) applies a remembered choice before first paint, keeps
`aria-pressed` and both `theme-color` metas in step, and forgets the choice when it equals the system's. `base.html`: public mode
only gets `class="skin-a"`, the two media-scoped metas, sweep-a.css, theme.js, Instrument Sans and the switch; console output is
byte-identical. Harness: `lib.mjs` reads `D7_SCHEME` (default `dark`, as before); `docs/design/sweep-a/harness/` adds
`contrast-a.mjs` and `toggle-a.mjs`.

**Tokens** (light / dark): ground #FFF6EE / #151024, well #FFFBF7 / #100C1C, surface #FFFFFF / #211936, surface-low #FFF9F3 / #1B1430,
surface-high #F2EDFF / #2D2453, surface-edge #E6DDFB / #3A2F62, chalk #1E1530 / #FFF6EE, chalk-lift #3A2B5C / #FFFFFF,
warm #43385A / #E2DAF2, slate #574B6E / #C2B8DA, dim #7C7194 / #6E6390, paid #A6420F / #FFB38A, paid-lift #7F2F05 / #FFD2BC,
free #4B6200 / #E4F25C, free-lift #3A4C00 / #F0F98F, over #A12A1A / #FF9F8C, control #7A6E92 / #9A8FBB, pending-slate #4F4466 / #CFC6E4.

| Check | Result |
|---|---|
| At rest, dark system (`output/design-A1/dark/`) | 104 captured; the 12 console states pixel-identical to A0; every public state differs (colour and type, by design) |
| At rest, light system (`output/design-A1/light/`) | the same: 12 console identical, public all differ |
| Contrast, rendered (`contrast-a.mjs`, 20 public states × 2 widths × 2 themes) | **80 of 80 pages** have no text under AA; 4,313 nodes per theme; tightest 5.77:1 light ("Paid, and optional"), 7.5:1 dark |
| Contrast, tokens (`test_visual_rules_a.py`) | every text token ≥ 4.5 on all six grounds in both themes (tightest 4.72, light `--paid` on `--surface-edge`); control ≥ 3.6 |
| Theme switch (`toggle-a.mjs`) | 20 of 20: system default, click, remembered across reload, Enter returns to system and forgets, 64×44 target, both themes, both widths |
| Browser flows | 11 of 11 on Chromium, 0 script or console errors |
| Focused tests | `theme_test.js` (25 checks, 10 mutations caught); `test_visual_rules` + `test_visual_rules_a` (36); `test_public`, `test_public_copy`, `test_d7c_copy`, `test_motion` (154); `dirty_test.js`, `pick_test.js`, `price_test.js` |
| Manifest | `docs/design/EVIDENCE_MANIFEST_A1.sha256`: 461 files, all verify |

Implemented by a Sonnet 5.5 subagent from an Opus brief; tokens, contrast targets and review by Opus.

## 10. A2 shared components (recorded)

**Change.** `sweep-a.css` gains the component tokens (`--a-line`, `--a-shadow`, `--a-primary`, `--a-on-primary`, `--a-link`,
`--a-focus`, `--a-lav`, `--a-cit`, `--a-pch`, `--a-ink`, `--a-tint`; light / dark) and `--radius: 12px`, and gives the shared parts
their Direction A shape on public pages: sticker buttons (2px outline, hard offset shadow, lift on hover, press on active),
underlined-word tertiaries, one 3px focus ring, pill chips and tags, sticker panels (a closed disclosure is dashed; a panel inside
a panel stays a hairline), 14px fields, choice cards, h1/h2/lede, the brush mark (`mark_a` in `_mark.html`), the pill tracker with
a citrus "2 of 4" chip on phones, the feedback button and the credit chip. New primitives for A4–A9 live in `templates/_a.html`
(`peek`, `tip`, `stamp`, `mbar`) with `.sticker`, `.scrib` and `a-pop`; `static/tips.js` (deferred, public only) dismisses a tip
for the session and moves focus to what follows it. Everything that moves sits behind `prefers-reduced-motion: no-preference`.

**Motion, deliberately.** On public pages D7B's *press* (`translateY(1px)`) becomes the sticker press (`translate(2px, 2px)` with the
shadow shrinking) and a hover lifts the sticker; the console keeps D7B's press. New moves: `a-bob` (the tip's face) and `a-pop`
(for A4+). Durations reuse `--ms-1`.

**Review findings, fixed in this stage.**
1. A disabled primary faded to `opacity: .5` measured 2.39:1 (light) on Confirm when credit is short, where it is the screen's one
   decision until "run anyway" is ticked. Disabled is now "not yet": full opacity, the tint, slate words (6.95:1 / 7.5:1), a dashed
   control edge, no shadow. Pinned in `test_visual_rules_a.py`. Wrapped button labels get `line-height: 1.2`.
2. Flow W10 asserted Filter/Export borders were exactly 1px (Quiet Ledger). The intent is "an outlined button, not an underlined word";
   the check now accepts any real border on a `.secondary` (Direction A's is 2px).

| Check | Result |
|---|---|
| At rest, dark and light systems (`output/design-A2/{dark,light}/`) | 104 captured each; the 12 console states pixel-identical to A0 in both; public states differ by design |
| Contrast, rendered | **80 of 80** pages pass AA in both themes; tightest 5.77:1 light, 7.5:1 dark |
| Component gallery (`docs/design/sweep-a/harness/gallery.py`, `gallery-shots.mjs`) | `output/design-A2/gallery/`: every primitive, light and dark, 1440 and 390 |
| Browser flows | 11 of 11 on Chromium, 0 script or console errors |
| Focused tests | `tips_test.js` (30 checks, 15 mutations caught), `theme_test.js`, `dirty_test.js`, `pick_test.js`, `price_test.js`; Python: `test_visual_rules`, `test_visual_rules_a`, `test_motion`, `test_public`, `test_public_copy`, `test_d7c_copy`, `test_results_ui`, `test_upload_configure_ui`, `test_unified_review`, `test_confirm_ui`, `test_progress_ui`, `test_dirty_guard` (359, OK) |
| Manifest | `docs/design/EVIDENCE_MANIFEST_A2.sha256`: 466 files, all verify |

Implemented by a Sonnet 5.5 subagent from an Opus brief; component tokens, contrast, the disabled-state redesign, the W10 judgement
and review by Opus.

## 11. A3 Quick Sweep / Deep Sweep (recorded)

**Rule.** Only the names of the two choices change, and only on public pages: "Free Sweep" → **Quick Sweep**; the sweep that uses the
visitor's own Apify key → **Deep Sweep** ("Start Deep Sweep — $X"). Words that state a cost fact stay as they were: "paid searches",
"22 of 72 paid searches", a result's "Paid" source, the tile legend, "Affects cost", "133 free job boards", "Nothing to pay".
Exports, the console and engine strings are untouched.

**Copy.** key.html (card, button, "Deep Sweep: add LinkedIn, Indeed, Naukri", plus the Apify paragraph), upload.html (aside headings,
"a Quick Sweep needs no key" plus the Apify sentence), configure.html (the sentence and the button), confirm.html (Start Quick / Deep
Sweep), running.html ("No paid board is touched on a Quick Sweep"). Shared templates use a `public_mode` branch, so console output is
byte-identical. The verified Apify line: "Apify’s free plan includes $5 in monthly credits, with no card required. Actual search usage
varies, and you see the estimated cost before anything runs." `PaidUnavailable`'s wire string never reaches a page and is pinned by
test_public_guardrails, so it stays.

**Review findings, fixed in this stage.**
1. A1 regression found here: the theme switch was named by `aria-label` only, and `test_multi_setup` requires every button to carry text
   (not run in A1/A2). The name is now a visually hidden "Dark mode" span; `test_visual_rules_a` pins it.
2. `toggle-a.mjs` and `contrast-a.mjs` left their app.py running, holding the port for the next run; both now stop it.

| Check | Result |
|---|---|
| At rest, dark and light (`output/design-A3/`) | 104 captured each; the 12 console states pixel-identical to A0 in both |
| Browser flows | 11 of 11 on Chromium (W3 now presses "Start Deep Sweep — $7.02"), 0 script or console errors |
| Theme switch | 20 of 20 |
| Focused tests | new `test_a3_copy.py` (9) with `test_multi_setup`, `test_visual_rules_a`, `test_public_copy`, `test_d7c_copy`, `test_confirm_ui`, `test_upload_configure_ui`, `test_public_paid`, `test_active_run`, `test_public`: 286, OK; `theme_test.js`, `price_test.js` |
| Manifest | `docs/design/EVIDENCE_MANIFEST_A3.sha256`:      460 files, all verify |

Implemented by a Sonnet 5.5 subagent from an Opus brief; the copy rule, the switch's name fix and review by Opus.

## 12. A4 Upload and reading (recorded)

**Change (public only; console byte-identical).** Upload's fresh state gets the eyebrow "Step 1 · your résumé", the headline
"Messy job boards in. A *tidy shortlist* out." and the lede "Drop in your résumé. Sweep works out what to look for, then ranks
what it finds." The add-résumé form is the screen's one sticker card; its free-note and the scanned-PDF sentence become three
peeks under it ("Is it free?" yes · "Is my résumé kept?" no · "Why only text PDFs?"). The rail's What happens next / Quick Sweep /
Deep Sweep / Nothing is kept blocks are gone (their facts are in the peeks and in the three-step trail that closes the page);
"What Sweep read last time" stays. The fresh rail is the **brush desk** (`templates/_desk.html`, `static/desk.js`): seven
fictional listings with raw scores; drag the brush and strong ones (≥ 40) land on the shortlist, ranked, weak ones are swept;
"Sweep it for me" and "Start over" are the keyboard way; static without JS, no parallax or trail under reduced motion. The
management list is CSS only: each résumé a sticker card. `/derive` gets the brush mark and the A2 look; no copy change. Every
form contract (action, `name="resume"`, Alpine bindings, management forms, Continue) is unchanged.

**Review findings, fixed in this stage.**
1. Desk cards overlapped enough to cut titles mid-word ("…ior Backend / …gineer"). Cards are now 27% wide in two columns
   (x 2–5 and 32–34) so they meet only at rotated corners; the brush aims at the new centre (x + 13.5); the phone desk is 480px.
   `desk_test.js` gained a right-edge check (the +33 → +30 hit-box change was not caught before; now it is).
2. The "Is it free?" peek said Deep Sweep runs "through your own Apify account" but no longer that it bills per search (Upload's
   rail used to). Now "…through your own Apify account, which bills per search." and `test_a3_copy` pins it.
3. `test_a3_copy` rendered console pages against the real repo and wrote `profiles/kartik.py` on every run (the stray file
   seen in A3). It now uses a temporary tree.
4. Incident, not code: a stopped first A4 agent's ad-hoc console check posted an upload in local mode, which saves to the real
   `auto-apply/resume/resume.pdf`; it was overwritten with "nope" and restored with `git restore`. Briefs now forbid local-mode
   uploads outside a temporary resume_dir.
5. Not a regression: 8 console states differed in the light run only because the run crossed midnight ("posted 3d ago",
   elapsed time). HEAD and this tree captured at the same moment: **12 of 12 console states identical**
   (`output/design-A4/console-now/`). From A5 on, console states are compared with a same-day HEAD capture.

| Check | Result |
|---|---|
| At rest (`output/design-A4/{dark,light}/`) | 104 captured each; dark run: 12 console states identical to A0; light run: see finding 5 |
| Console, same moment (`console-now/`) | 12 of 12 identical, HEAD vs this tree |
| Console Upload bytes (`docs/design/sweep-a/harness/console-hash.py`) | `/` fresh and with a résumé read: identical sha256, HEAD vs this tree |
| /derive (`derive-pages.py`, `derive-shots.mjs`, `output/design-A4/derive/`) | working, waiting, failed × light/dark × 1440/390 |
| Contrast, rendered | 80 of 80 pages AA in both themes (rerun after the desk fix) |
| Browser flows | 11 of 11 on Chromium, 0 script or console errors (before the desk geometry fix, which no flow touches) |
| Focused tests | `desk_test.js` (90 checks; 31 mutations by the implementer, plus the right edge), `pick_test.js`, `theme_test.js`, `tips_test.js`, `dirty_test.js`; Python: `test_a4_upload` (38), `test_a3_copy`, `test_upload_configure_ui`, `test_batch_upload`, `test_multi_setup`, `test_public`, `test_public_copy`, `test_d7c_copy`, `test_visual_rules`, `test_visual_rules_a`, `test_motion`: 352 OK |
| Manifest | `docs/design/EVIDENCE_MANIFEST_A4.sha256`: 503 files, all verify |

Implemented by a Sonnet 5.5 subagent from an Opus brief; the desk geometry, the cost-fact copy fix, the console checks and review
by Opus.

## 13. A5 Review, tap to tune (recorded)

**Production paths.** Multi-Track is ON in production (owner, 2026-10-02). One résumé reaches the one-résumé review (after
`/derive`); two or three reach the unified review (`reading.js`, the open card holding the form). A5 covers both.

**Change (public only; console and Results' re-rank editor byte-identical).** Eyebrow "Step 2 · profile check"; the one-résumé h1
"Did we get you *right*?" and lede "Read from {file}. Tap anything that looks off." (the unified banner keeps its server-written
title and status, plus the eyebrow). The experience line is a chip that opens the existing year/month steppers; roles show six
then "+N more"; skills are **tap-to-tune chips** (`weight_editor(..., tune=true)`): each chip shows five weight dots and opens its
own panel (the existing stepper, a word for the level, Remove, the badges, and why); ten show, the rest behind "+N more"; "+ Add a
skill" opens the existing add row; a brush tip above. The Adjust disclosure is gone: its explanations are the peeks "How does
ranking work?" and "What counts against a match?". Unified cards are sticker cards, the open one ringed. Phones: the save bar is
sticky. Without JavaScript every part is open and the page is the plain form; with it, `theme.js` sets `<html class="js">` before
paint and only then are closed parts hidden.

**The contract, proved.** `logic.reweighted()` zips the i-th posted `term` with the i-th `weight`. In tune mode every skill row
still carries exactly one hidden `term` and one `weight` input in the table's sort order; hidden rows are hidden by CSS, never
removed or disabled. `test_a5_review.py` parses the form in document order as a browser would and, on all three production shapes
(one résumé MT off, one résumé MT on, three résumés), asserts the pairs equal the console table's, counts match, and a real save
applies exactly the edits made (weight change, remove, add, experience) and nothing else. Breaks it catches: a dropped term input,
`add_weight` renamed `weight`, `disabled` on hidden rows (implementer), and the tune order reversed (review: 8 failures + 1 error
across all three shapes).

**Review findings, fixed in this stage.**
1. The experience chip carried a fixed `aria-expanded="false"` beside its live binding: without JavaScript the editor is open, so
   it told a screen reader the opposite of the screen. Now only the binding sets it; pinned.
2. `.skin-a .ledger { gap }` also reached Upload's résumé list (also `.ledger`). Scoped to `[data-resumes]`; Upload's list is
   pixel-identical to HEAD again (`output/design-A5/probe-ledger/`).
3. Measured, not a regression: with the same-day HEAD capture as "before", a few non-Review screens differed by glyph-edge
   anti-aliasing only (same size, same layout). HEAD's tree with nothing but A5's `theme.js` reproduces them exactly
   (`probe-js/`): adding the `js` class to <html> shifts Chromium's text rasterisation; HEAD's CSS has no rule that uses it. Two
   states (`m-long-m`, `progress-free-failed-m`) also differ between two captures of the same tree (noise).

| Check | Result |
|---|---|
| At rest vs a same-day HEAD capture (`output/design-A5/{dark,light}/`) | 104 each; the 8 Review states differ by design; console states identical; other public differences explained in finding 3 |
| Console `/review` and `/results`, Results re-rank editor (`docs/design/sweep-a/harness/review-hash.py`) | sha256 identical, HEAD vs this tree |
| Contrast, rendered | 80 of 80 pages AA in both themes |
| Browser flows (final tree) | 11 of 11 on Chromium, 0 script or console errors; W7 opens the experience chip |
| Focused tests (final tree) | 465 Python OK (`test_a5_review` 48); `theme_test.js`, `dirty_test.js`, `reading_test.js`, `tips_test.js`, `desk_test.js` |
| Manifest | `docs/design/EVIDENCE_MANIFEST_A5.sha256`: 516 files, all verify |

Implemented by a Sonnet 5.5 subagent from an Opus brief; the contract design and its proof, the order break, the aria and
`.ledger` fixes, the anti-aliasing diagnosis and review by Opus.

## 14. A6 Search coverage (recorded)

**Change (public `/key` only; the console `/key` is byte-identical).** Eyebrow "Step 3 · coverage", h1 "How wide should we
*sweep*?", lede "Same ranking either way. Deep Sweep adds {paid}." Two radio cards (Quick Sweep; Deep Sweep with a "+3 big
boards" sticker) beside a **coverage diagram**: "Your résumés" at the core, "Career pages" and "Public boards" on the inner ring,
one chip per paid board (from `paid_sites()`, never typed) on the outer ring, which pops in and slowly orbits for Deep (motion only
in no-preference; reduced motion: they simply appear). No source counts: the free-board count is not known on this screen. One call
to action follows the radios: Quick shows the Quick form's own submit; Deep shows "Set up Deep Sweep", which opens the setup **one
step at a time** (1 grab a free Apify account, 2 copy your API token, 3 paste it here = the real key form), with dots, "Step N of 3",
"I already have one", "Already have a key? Paste it", back links, a brush tip, and focus moved to each step's heading. The three A3
money paragraphs keep their words and order inside the peek "Does Deep Sweep cost money?". Phones: the diagram sits above the
cards and the call to action is the pinned bar. Without JavaScript nothing is hidden: the choice, then all three numbered steps and
both forms. The radios are in neither form and are never sent.

**The contract (unchanged, pinned by `test_a6_key.py`).** The Quick submit is inside `form[action=/key/free]`; the key form posts
the one `token` password field (no `value`, `autocomplete=off`, `required`, described by the visible privacy sentence and the cost
note) to `/key`; a refused or malformed key is never echoed and reopens the page at step 3 with the error beside the field. Break
it catches: the Quick submit moved out of its form (implementer).

**Review findings, fixed in this stage.**
1. `key_screen` also shows errors that are not about a key: Quick's profile-rewrite failure (`POST /key/free`), the
   plans-per-minute limit (`PlanLimited`) and the daily run limit. The first build sent every `error` to Deep, step 3, so a Quick
   visitor would have been shown the Apify paste field with "too many plans" beside it. Now only a refusal from `POST /key`
   (`request.endpoint == 'key_post'`) opens the paste step; any other error stays on the choice, under the headline. Pinned (two
   tests, both fail under the old rule).
2. The build dropped the line that tells a reader which Apify token to copy. Restored in step 2, under the token picture
   (reworded to stand on its own: "Copy the Personal API token with the button beside it. Apify calls it the token created on
   sign-up — that is the one.").
3. Step 1's sticker "$5 a month, free" could read as a price; now "$5 free every month".
4. Measured, not a regression: against a same-day HEAD export, dark `s1-19-m` (public Results, untouched by A6) differs in two
   text lines by glyph anti-aliasing only (same size and layout). A HEAD export carrying every A6 app file reproduces it, and this
   tree's capture is pixel-identical to A5's working-tree capture in both themes: it is the export, not the change. `m-empty`
   (delta ≤ 2), `progress-paid-one-some-tiles-d` and `confirm-over-multi-d` were capture noise (identical on re-capture).

| Check | Result |
|---|---|
| At rest vs a same-day HEAD capture (`output/design-A6/{dark,light}/`) | light 102 of 104 identical, dark 98 of 104; `key-d`/`key-m` differ by design; the rest explained in finding 4 (`probe-dark/`, `probe-css/`) |
| Console `/key`, `/`, `/review`, `/results`, Results re-rank editor (`key-hash.py`, `console-hash.py`, `review-hash.py`) | sha256 identical, HEAD vs this tree |
| `/key` in a real browser (`docs/design/sweep-a/harness/key-a.mjs`) | 120 of 120 checks, both themes: radios, diagram, CTA swap, steps and focus, back, refused key at step 3, no-JS, phone bar, 1024/768, reduced motion |
| Contrast, rendered (now including each setup step) | 92 of 92 pages AA in both themes |
| Browser flows | 11 of 11 on Chromium, 0 script or console errors |
| Focused tests | 487 Python OK (`test_a6_key` 56); `theme_test.js`, `tips_test.js`, `dirty_test.js`, `desk_test.js`, `reading_test.js` |
| Manifest | `docs/design/EVIDENCE_MANIFEST_A6.sha256`: 519 files, all verify |

Implemented by a Sonnet 5.5 subagent from an Opus brief; the error-routing fix, the restored token line, the export
anti-aliasing diagnosis and review by Opus.

## 15. A7 Configure and Confirm (recorded)

**Change (public `/configure` and `/confirm` only; the console renders byte-identical).**
- **Configure:** eyebrow "Step 3 · Quick Sweep / Deep Sweep", h1 "Where should we *look*?", lede "Sweep has set these up from your
  résumé(s) already. Change anything, or carry on." The settings are sticker blocks, the paid boards toggle chips beside a "✓ N
  free job boards · always on" chip, the scope radios a row of pills (only the chosen one's line shows), the Advanced door a
  peek-like door; every control, name, value and Alpine binding is unchanged. Beside them, Deep: **the credit jar**. Its dashed
  line is `est.coverage.available_usd` (the credit of the account(s) the sweep would spend from, Confirm's "Available Apify
  credit"), drawn only with coverage at 88% of the jar; its fill is the estimate's share of that (capped at 100; 0 with no paid
  lines; 0 and an `off` look when paid searches are unavailable); its `over` is `est.over_cap` and nothing else, so placement can
  say "over" with the fill under the line and the existing sentence says why. It dims with `stale`, pours (no-preference), and
  wobbles once when `over_cap` turns true — never on first paint, never with reduced motion. Under the figure, when the engine
  says the whole plan fits: "Your connected Apify accounts can cover the full Sweep." (Confirm's own sentence). The lines table
  is in "How is this worked out?"; the search summary is a peek at the panel's end (Quick keeps it visible: on one résumé that
  screen starts the run). Phones: a sticky strip with the live figure that links to the cost (a link, never a second submit).
- **Confirm:** "← Change something", h1 "Ready when *you* are.", lede "Here’s your sweep, on one ticket. Nothing has been charged
  / started yet." The summary and the decision are one **ticket**: the main part with a "Not started" stamp, the stub perforated
  and notched, peach for money and citrus when free, holding the figure, a "How is this worked out?" peek with the price by
  source, every verdict, the over-cap box, the Start form and the duration note. After it: the accounts with their Remove forms
  and the add-key door (open when the plan is not fully covered). Phones: stacked, not pinned.

**Frozen and proved.** `price.js` (sha256 pinned), `app.py`, `logic.py`, `plan.py`, `sweep.css` byte-identical; the form's named
controls in document order pinned for Deep and Quick; exactly one submit; the over sentence's server twin checked against
`overWhy` run through node for each cause; every Confirm verdict, button label, disabled tag and over-cap box equal to what
6e6719d rendered in six states; estimate isolation suites unchanged and passing. Breaks caught (implementer): the jar's over bound
to its fill (12 failures); a second submit in the form (6).

**Review findings, fixed in this stage.**
1. The depth stepper's restyle was written for every `.stepper`, so it also moved Review's experience and weight steppers (A5)
   and would have moved the Results re-rank editor's. Scoped to `.setting-body .stepper`; pinned by
   `test_the_depth_stepper_rules_reach_only_configure`. Review is pixel-identical to HEAD again (`output/design-A7/probe-*`).
2. The implementer found that the contrast measure (`motion-d7b/harness/contrast.js`) could not read `color(srgb …)`, which
   Chromium returns for a computed `color-mix()`: a text colour made that way crashed it, and a background made that way was read
   as no background. Fixed; the audit now re-measures every earlier public state with it too, and all pass.
3. Noted, not changed: the header's "Credit left $42.00" is the account's headroom; the jar's and Confirm's "$41.99 available"
   is its usable capacity. Two true figures, as Confirm has shown since D7C.
4. Measured noise: `console-configure-over-d` (light) and `review-editor-d` (dark) were identical on re-capture; two captures of
   HEAD itself differ in the same region of the latter.

| Check | Result |
|---|---|
| At rest vs a same-day HEAD capture (`output/design-A7/{dark,light}/`, re-captures in `probe-*`) | the 12 Configure and Confirm states differ by design; every other state identical (after finding 1; finding 4 noise) |
| Console `/configure` and `/confirm`, 10 states (`docs/design/sweep-a/harness/configure-hash.py`) | sha256 identical, HEAD vs this tree; pinned in `test_a7_money` |
| Configure and Confirm in a real browser (`docs/design/sweep-a/harness/money-a.mjs`) | 224 of 224, both themes: re-pricing dims then writes once, the jar pours to the rule, wobbles once on crossing (fill 70.7%, under the line), never on first paint or reduced motion; the phone strip; the ticket at 1440 and 390; no overflow at 390/768/1024/1440 |
| Contrast, rendered | 116 of 116 pages AA in both themes (tightest new: 5.61:1, muted text on the peach stub) |
| Browser flows (final tree) | 11 of 11 on Chromium, 0 script or console errors; W3–W5 unchanged |
| Focused tests | 878 Python OK (implementer, before finding 1) and the CSS-sensitive modules again after it; `price_test.js`, `pick_test.js`, `theme_test.js`, `tips_test.js`, `dirty_test.js` |
| Manifest | `docs/design/EVIDENCE_MANIFEST_A7.sha256`: 519 files, all verify |

Implemented by a Sonnet 5.5 subagent from an Opus brief; the jar's truth rule (coverage, never the fill), the frozen list, the
stepper scoping and review by Opus.

**Fix after A7 (before A8): no Jinja inside a style attribute.** `test_app.test_no_template_puts_jinja_inside_a_style_attribute`
(style="" is CSS; only a continuous percentage may be written into one) was never in a stage's focused run, and A4, A6 and A7 each
broke it. Found before A8 by running `test_app` (537 tests, about 20 s; it holds template-wide rules, so it is in every later
stage's run). Fixed: the desk's seven resting places are classes `c1`–`c7` in sweep-a.css, held equal to the data-* numbers
desk.js reads (`test_a4_upload`); the orbit's angles are the spin's `n<count>` class (`test_a6_key` reads them from the
stylesheet); the jar's fill is a continuous 0–100 like the header meter's and is named beside it as the second allowed one.
Upload, `/key` and Configure are pixel-identical to a2e784d in both themes (`output/design-A7/probe-style-*`), and the Deep
orbit's chips sit at the same pixels.

## 16. A8 Progress (recorded)

**The one server change (owner-approved).** `live_feed()` gives each fresh listing, in public mode only, `skills`: its
`matched_skills` split as results.html splits it (comma, trim, drop empties), first six. Nothing else in the feed moves. Public only,
so the console's /running (which embeds `progress|tojson`) stays byte-identical; a Multi-Track row's column already holds the best
track's skills; an item made before a deploy has none and renders as the plain row (`job.skills || []`).

**Change (public `/running` only; console byte-identical in 14 states).** Eyebrow "Step 3 · Deep Sweep / Quick Sweep" (the
header's tracker keeps Progress on step 3, Search); every heading, lede, banner and ending keeps HEAD's words (pinned). The paid
track is a chunky striped track with the brush riding the fill's end (Alpine `:style`, no Jinja in style; a gentle bob while live;
static under reduced motion); the free bar's brush rides its moving segment. Under the track a ticker, "Now: {board} · {place}",
from the tile `nowRunning()` already marks (board spelled by `site_label`), or "the free job boards" during the free pass.
The searches grid is a peek with "N of M done". **The interaction:** a listing that carries skills is a button that opens
"Your skills this listing mentions" with its chips (one open at a time); a tip says so once some listing has skills. New
listings drop in (no-preference). Endings, panels and the passes list are sticker cards; Stop is quiet. Every A8 selector hangs on
`.skin-a .run-a` (pinned).

**Review finding, fixed in this stage.** The first build's eyebrow said "Step 4" while the header's tracker highlights step 3
(Search) on this screen; now "Step 3".

**Noted for A11.** The implementer found that with mobile emulation `scrollWidth - innerWidth` cannot see horizontal overflow (the
layout viewport widens), so the "no overflow at 390" checks in key-a/money-a may under-report; progress-a measures against the
configured width. A11 re-measures every screen that way.

| Check | Result |
|---|---|
| At rest vs a same-day HEAD capture (`output/design-A8/{dark,light}/`) | 90 of 104 identical in each theme; the 14 that differ are the Progress states |
| Console `/running`, 14 states (`docs/design/sweep-a/harness/running-hash.py`) | sha256 identical, HEAD vs this tree; pinned in `test_a8_progress` |
| Progress in a real browser (`docs/design/sweep-a/harness/progress-a.mjs`) | 138 of 138, both themes: rider within 2px of the fill, ticker follows the tile, drop-in / none under reduced motion, a listing opens by click, Enter and Space, a stale item renders plain, every ending with HEAD's words and the redirect, free path, no overflow 390–1440 |
| `verify-progress.mjs` (D7B) | 10 of 10 (P1 updated: `<html>` now carries `skin-a js`) |
| Contrast, rendered | 140 of 140 pages AA in both themes |
| Browser flows (final tree) | 11 of 11 on Chromium |
| Focused tests | 1,575 Python OK (implementer, incl. `test_app`), and the touched modules again after the eyebrow fix |
| Manifest | `docs/design/EVIDENCE_MANIFEST_A8.sha256`: 489 files, all verify |

Implemented by a Sonnet 5.5 subagent from an Opus brief; the server change's shape and its public-only gate, the eyebrow fix and
review by Opus.

## 17. A9 Results (recorded)

**Change (public `/results` only; console byte-identical).** Eyebrow "Step 4 · your jobs" (h1 unchanged). Every listing is a sticker
**card** at every width — the same `<table>` markup, rows laid out as cards (thead visually hidden): the raw score as a neutral
badge (no colour bands: the engine publishes no scale), title, company and place, the recommendation lines exactly as before
(caution first, visible), fact chips (pay, experience, "via X" with its peach "Paid", posted age), Apply as a sticker button.
**The interaction:** "Why it matched" (a peek in place of the capped inline tags) lists every matched skill under "Your skills
this job mentions"; `@click.stop` keeps a click in its body from opening the listing. A tip says so once. "Top of the pile" marks
the first card of the first section on the best-match sort only. The score explainer is "How match scores work" as a peek with
its words kept and a picture (a line with zero marked, "below zero" / "more of your résumé", no numbers). Tabs, tools, sections,
the abroad peek, the ending and no-results blocks are sticker parts; every word, link, export and the row link are unchanged.
Phones: the Apply button is the card's full-width foot (322×48, HEAD 73×44).

**Also in this commit: the jar fix (owner-spotted, A7).** A sliver of a fill (e.g. $4.21 of $41.99) stuck out past the jar's
walls: a fill shorter than its own corner radius has those corners flattened by the browser. The fill now sits in `.jar-in`, the
jar's inside, which clips it to the curve; the lid and the credit line still overhang on purpose. Pinned in `test_a7_money`.

**Noted for A11.** `verify-results.mjs` (D7B) fails the same 8 of 18 at HEAD as here (its checks expect no class on `<html>`, count
the tip's idle bob as an animation, and one back-step tolerance) — stale since A1/A5, to be updated in A11. `money-a.mjs`'s wobble
section waits a fixed time for a re-price and flakes under load (213, 218, then 224 and 224 of 224); make those waits event-driven.

| Check | Result |
|---|---|
| Targeted at-rest comparison vs a same-day HEAD capture (`output/design-A9/{dark,light}/`, 35 states × 2 widths) | 52 Results states differ by design; `configure-paid` by the jar's corners (the fix); the 16 others identical, all 12 console states among them |
| Console `/results` (9 states), `/review`, re-rank table (`results-hash.py`, `review-hash.py`) | sha256 identical, HEAD vs this tree; pinned in `test_a9_results` |
| Results in a real browser (`docs/design/sweep-a/harness/results-a.mjs`) | 123 of 123, both themes, 1440 and 390 |
| Contrast, rendered | 168 of 168 pages AA in both themes |
| Browser flows | 11 of 11 on Chromium |
| Focused tests (owner's narrowed policy) | `test_a9_results` (50), `test_a7_money`, `test_a8_progress`, `test_app`, `test_results_ui`, `test_multi_results_view`, `test_multi_exports`, `test_motion`, `test_visual_rules(_a)`: OK |
| Manifest | `docs/design/EVIDENCE_MANIFEST_A9.sha256`: 369 files, all verify |

## 18. A10 The other states (recorded)

**Audit (40 public states × 2 themes × 2 widths, `docs/design/sweep-a/harness/states-a.mjs` over `states-app.py`).**
- **Errors on every screen** (upload refused/scanned PDF, daily limit, rooms full, deriving, review save, configure, confirm,
  results, every /key worker-trouble message) still wore Quiet Ledger's flat rose bar → one A2 sticker error (outline, hard shadow,
  ringed "!", tint, ink); Confirm's late-night note keeps A7's look.
- **The access lock (beta.html)** rendered in the console's dark look even in light → loads the A skin itself (it does not extend
  base.html): `mark_a`, a sticker card; words and form unchanged.
- **The active-run strip** → a sticker band in the gutters, a tint per tone. **Confirm's "already done today" callouts**, **the
  results notice**, **the feedback dialog**, **plan_error.html** → sticker parts. **The tracker** with no current step (404, plan
  error) no longer shows an empty "of 4" chip.
- Fine as they were: Progress queued, Configure/Confirm with a sweep running, the late-night warning, the failed résumé card.

**The 404 page (the one server change; public only).** Unknown URLs render `not_found.html` ("Lost the trail" / "This page isn't
*here*." / "Back to the start"), status 404, never echoing the path, no step current. Only the router's NotFound: `/static` misses,
a view's own `abort(404)`, OPERATOR_ONLY routes' plain-text answer, JSON bodies and the console's default 404 are unchanged
(pinned in `test_a10_states`; the break — the handler without that restriction — fails five tests).

**Copy.** Two public worker-trouble messages now use the A3 names: "…search the paid boards, or take the free sources." → "…for a
Deep Sweep, or run a Quick Sweep."; "You can search the free sources now…" → "You can run a Quick Sweep now…". **Proposed, not
changed (owner):** Confirm's paid-unavailable verdict still says "from the free or paid step" (pinned by `test_a7_money`'s HEAD
verdicts) → "You can run a Quick Sweep now from the Search coverage step".

**Found and fixed: failures A9 left behind.** Under the narrowed test policy A9 did not run `test_a6_key` or `test_a4_upload`; A9's
CSS section broke A6's "slice to end of file" stylesheet tests (4) and its eyebrow broke A4's one-eyebrow-per-screen rule (1).
Fixed here (A6's slice ends where A7 begins; A4 allows Results' eyebrow); each stage's CSS slice now ends at the next section.

| Check | Result |
|---|---|
| **Console vs the A0 baseline (ce428ef), pixels** — the plan's A10 exit | 12 of 12 console states identical in both themes (`output/design-A10/console-*`) |
| **Console vs A0, bytes** (all six hash scripts: Upload, /key, Review, Configure, Confirm, Progress, Results, re-rank) | 39 of 39 renders identical |
| Public states the A10 rules can reach vs HEAD (`output/design-A10/public-*`) | 61–62 of 64 identical; `review-failed` differs by design (the sticker error); one dark `m-all-filters-m` was noise (identical on re-capture) |
| `states-a.mjs` | 160 of 160 pages: reached, no overflow (configured-width measure), no text under AA |
| Browser flows | 11 of 11 on Chromium |
| Focused tests | 1,307 Python OK (`test_a10_states` 34 and every touched screen's module) |
| Manifest | `docs/design/EVIDENCE_MANIFEST_A10.sha256`: 516 files, all verify |

## 19. A11 Release hardening and the release candidate (recorded)

**Owner's call: a lean A11.** The owner checks every public screen by hand on localhost (`docs/design/sweep-a/MANUAL_CHECK_A11.md`,
port 5277), so the automated browser work the plan listed for A11 was **dropped, not run**:
- Firefox and WebKit runs of the flows and the states audit (Chromium only, as at A10);
- the A0 104-state pixel comparison of the public screens (the console's A0 comparison stands from A10: 12 of 12 identical);
- per-fix screenshot and contrast passes. The owner's manual check found nine issues, all fixed in d149c27, and re-checked.

**Pre-merge fixes (from the fresh-eyes Impeccable critique, owner approved "before the merge").** Public only:
- the one-résumé review's findings are `h2` under the `h1` (they skipped to `h3`); inside a résumé card they stay `h3`;
- two side stripes became full borders (Results' suggestion, Confirm's decide error);
- Confirm's button labels use " · " instead of an em-dash before the price ("Start Deep Sweep · $7.02"); the console keeps "—";
- the header pill says "Apify balance" (it read as the credit jar's figure under another name); the console keeps "Credit left";
- the Quick Sweep bar no longer animates `width`: the paint is a clip-path, the brush a transform, on the same 2.9s clock;
- the setup's "About a minute" tip shows on steps 1 and 2 only (stale at the paste step);
- "+3 big boards" is a citrus sticker (peach is for money).

| Check | Result |
|---|---|
| Console vs HEAD, bytes (all six hash scripts) | identical |
| Focused tests for the fixes | 1,119 OK |
| Full suite (`unittest discover -s sweep/tests`) | 3,091 OK (4 skipped), 844 s |

**Not in this release (frozen, iterated on the design canvas first):** the fresh-eyes concepts V2, K2, T2 and P1. They ship later as a
new UI patch on a fresh branch off main. Rollback point for this release: 652bf8d.
