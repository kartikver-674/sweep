# Sweep design, phase D3: shared rules, unified review, Results prototype

Branch `design/sweep-ui-overhaul`, starting at `075afdf`. Evidence is in `output/design-D3/`
(git-ignored, synthetic data only). This note records what was changed, what was learned, and
what is deliberately left for the later phases. It is not a spec; the direction is in
[SWEEP_DESIGN_DIRECTION.md](SWEEP_DESIGN_DIRECTION.md) and its section 0 still governs.

## 1. What changed in the shared stylesheet

Shared rules change on every screen; nothing was restructured on a screen that is not in this phase.

| Rule | Before | After |
|---|---|---|
| Body | Geist 13 / 1.4 | Geist 14 / 1.55 |
| h1 | Bricolage 24 to 28, 700 | Bricolage 22 (26 from 48rem), 600 |
| h2 | Bricolage 18, 600 | Bricolage 17 / 1.4, 600 |
| h3 | Bricolage 15 | Geist 14 / 20, 600 |
| `.label` | 10px uppercase, 0.08em, slate | 12px, sentence case, 500, warm (9.6:1) |
| `.meta`, `.tag`, `.chip`, credit, tracker count | 11px | 12px |
| Table column heads | 10px uppercase | 12px uppercase, 0.06em (the ledger's small caps) |
| Links | teal | chalk, underlined |
| Focus ring | amber | chalk, 2px, 2px offset |
| Checkbox and radio accent | amber | chalk |
| Selected choice card | amber border, amber title | 2px chalk left rule, chalk title |
| Current step in the tracker | amber fill | bold label, 2px chalk ring |
| Weight bars | amber | warm (`--warm`); eight chalk bars out-shouted the Save under them |
| Stepper hover, drop-zone hover | amber | chalk |
| Reading dot, run strip dot, progress fill, working bar, passes marker | amber | chalk (teal when done, coral when wrong) |
| Primary hover | hard-coded `#fff` | `--chalk-lift` |
| Buttons | primary + secondary | primary, secondary (control-colour outline) and a new **tertiary** (underlined word); pressed `translateY(1px)` |
| Reduced motion | `*` only | `*::before` and `*::after` too (a pseudo-element is not matched by `*`, so the pulses drawn on `::before` kept moving) |
| Keyboard | none | `scroll-padding-top` so a sticky header cannot cover a focused control; `touch-action: manipulation`; `theme-color` |

The type scale in use on the review screen is now 12, 13, 14, 15, 17, 22, 26 (was 9 to 56 in 19 steps).

### New components (all on the Review screen)

- **Ledger** (`.ledger`, `.resume`): ruled rows, a rank numeral, the name, a status. Only the row open for editing is boxed.
- **Status** (`.status`): a shape beside a word. Ring = waiting, half-filled disc that breathes = reading, dot = ready, tick = reviewed, `!` = couldn't finish, dash = left out. (Reading was first a ringed dot, which is what a selected radio button looks like; the critique caught it.) Named `.status`, not `.state`, because Results already uses `.state` for its "Applied" word.
- **Read rows** (`.read-block`): the name of each finding on the left, the finding beside it. Replaces three inset cards.
- **Disclosures** (`details.notes`, `details.adjust`): a door under a rule, no box.

## 2. The Unified Review

Markup hooks kept: `data-card`, `data-open`, `aria-labelledby="resume-N"` with a single `id="resume-N"`, `id="resumes-banner"` (its three children, which `reading.js` compares by index), `id="resumes-continue"`, every form field name, the route for each action. `reading.js` is untouched and still swaps whole `[data-card]` elements.

- **Identity.** The editable label heads a row, the file it came from is the line under it (cut in the middle, the whole name for a screen reader), and the ordinal is a numeral in its own column. Until a résumé is read its label is only the placeholder "Résumé N", which says less than the file does, so **the file name stands in for it and is not repeated**. That fallback is the one place the file name is a heading; the owner should confirm it (section 6).
- **One primary per view.** The open row's Save. A ready row's "Review" is an outline; "Edit", "Leave out" and "Manage your résumés" are underlined words. While a row is open the page's "Continue to job search" is an outline too (it leaves without saving), so two primaries cannot appear.
- **Weight editor.** Importance badge no longer flush against the skill name; one neutral bar; the dashed square is now the word "Remove" (and "Undo" once ticked); the experience group title has room above its labels; the `.drop` class collision is gone (the cell is `.del`).
- **No behaviour changed.** Sequential derivation, independent reviewed and included states, retry, the gate on Continue, saving one résumé while another derives, and the single-résumé review are as they were; 29 review tests, the batch-upload, multi-track, public and 546 `test_app` tests pass.

### "Worth knowing": what it actually is

The D1 audit could not say what real users see there because it only saw the local engine in its harness. `render.yaml` sets `SWEEP_PROFILE_ENGINE=local`, so **Render runs the local engine**, and the notes are `local_profile._notes` plus whatever `skill_scan.widen` appends:

> Generated locally — no API key, no data left this machine. Target field read as 'software engineering'; years_experience COMPUTED from the extracted employment dates, not asked for. … The two domain halves, the title-alone promoters and title_exclude are empty on purpose — see auto-apply/local_profile.py.

That is a derivation log for someone checking the profile, in production, for strangers. It is not a user explanation. It also mixes one genuinely useful kind of sentence (what was corrected or added) with boilerplate that is always the same, and the two are not tagged, so a reliable separation would mean either matching on sentence text or changing `local_profile` and `skill_scan`, which this phase may not touch.

What D3 did, presentation only: the text is unchanged and verbatim, in a closed disclosure headed **"Technical notes on how this was read"** (the wording is a proposal) instead of a paragraph printed under three cards. Nothing is discarded, nothing is presented as an explanation, and it is one line tall until opened. **Owner decision needed**: whether to rewrite the notes at the source for people (and keep the log for the profile docstring), and what the replacement says.

## 3. Results prototype

`docs/design/prototype/results.html` with `results-rows.css`. Open from disk. It loads the real `sweep.css` for tokens and type, plus one stylesheet of candidate row rules that the app does not reference. No route, template or test points at either; the live Results page is unchanged.

Findings, against the real-shaped data (7 rows; 3 in a view with no pay or experience):

- **The suggestion can be the second thing you read.** 13px, text colour, a 2px rule at its left, the résumé name in 600. A second name in a close or split sentence is 500, so the suggested one carries the weight; in a tie every name does.
- **The engine orders the caution before the suggestion** (`logic.recommendation_words`: "so the suggestion after it is never read as an endorsement it does not make"). The direction doc said "beneath". The prototype follows the engine. It is a quiet line with a `!`, not coral, because it is a qualification and not an error.
- **Emphasising a name inside the engine's own sentence needs a small data change.** `recommendation_words` returns plain strings; bolding the name needs it to return the name as a separate piece (or the template to substitute it). That is a Results-phase task, and it must not change a word of the sentences.
- **Pay and experience columns are dropped when no row in the view states them**, and on a phone an absent value is not drawn at all, so two unlabelled "Not stated" cannot sit side by side. Facts carry their word: `Pay INR 28–36 LPA`, `5+ yrs`. The "yrs" unit is formatting the prototype adds; the live value is `5+`.
- **Right-aligned, tabular, 22px figure** (28px on a phone); a negative score stays on the ones digit.
- **Phone card.** The recommendation and the facts take the whole row under the figure instead of the narrow column beside it, which is what lets a 55-character résumé name fit.
- **Source is plain text** (and says "Paid" for a paid board), the résumé tabs keep their counts, and the scoring paragraph is one sentence plus a "How match scores work" disclosure, as the direction specifies.
- **A résumé name that contains parentheses nests them** inside the engine's own: "…résumé (Senior Full Stack Web Developer (Payments and Fintech)) focuses on." The sentence is frozen, so this is a fact to design around (names are user-editable), not a bug the prototype can fix.
- **Bugs found while building it** (all would have shipped): a desktop `tr:last-child td` rule out-specified the phone `display` rules, which pinned the last card's job cell at 24rem (27px of horizontal scroll) and let an absent value through; and a desktop padding on the figure cell survived into the card; and a "·" used as a separator wrapped to the start of a line and stood alone (now a word, `via`, `Pay`, or a gap).

## 4. Remaining migration (not done on purpose)

- **Boxes.** `.panel`, `.inset`, `.tile` still box Upload, Configure, Confirm, Search progress and Results. The review screen no longer uses them.
- **Type below 12px** still in the stylesheet (17 declarations): tracker marker numerals (10px, `aria-hidden`), the `.summary dt`, `.affects`, `.disclosure > summary > .meta` and `.next-steps` labels (10px uppercase), the search grid cells (9px), `.listings .state`, `.posted`, `.src` (11px), `.howto` counters, the picker caret, the key mask. Results, Configure and Confirm phases.
- **Amber that is not money** (6 rules, 9 lines): `.tick input` accent (applied tick), `.next-steps` numerals, `.cell.running` and `.key.running`, `.numeral-inline b` (the count in "133 free sources", amber on a free figure), `.callout.warn` and `.banner.warn`. The rest of the 21 lines are cost (`.paid`, meter, headline figure, `.affects`, `.costs`, paid cells and legend, keypill balance) and stay.
- **Teal that is not free or done:** source names and the row dot in Results (`tr.free td`).
- **Results:** the résumé switcher is still buttons with `.primary`; exports are still inside "Filter and sort"; the résumé labels in the recommendation are still file names (`fdb0da0`; decision 4 reverses that in the Results phase).
- **System:** the 404 is the unstyled server default (its page is the only one in the regression set that fails contrast and widens a phone); the quota and plan-error screens were not reviewed.
- **Upload:** the second, 56px mark in the hero; the triple restatement before the drop zone; `.hero h1` 34px.

## 5. Independent critique, and what came of it

A fresh reviewer, told to be adversarial and to judge against the direction, looked at the before and after screenshots with `design-taste-frontend-v1` and `minimalist-ui` as lenses. Verdicts on the twelve questions: **strong** on "more considered" (Review), containment, readability and the open editor; **adequate** on hierarchy, résumé identity, status legibility, mobile composition, the Results prototype, the suggestion's prominence, new clichés, and still feeling like Sweep. Nothing came back weak.

Defects it found, all fixed and re-captured: a 20px horizontal overflow on the mobile editor (caused by an earlier change of mine to the stepper, and hidden from my own check, see section 6); an orphaned "·" in the prototype; a hairline and a half-row hover band across the mobile weight cards (an inherited table rule); Review and Edit starting at a different x on each row; "Not read yet" said twice; the editor content sitting 15px right of the rows above it; a left-out row not muted; a long file name breaking mid-word when it stood in as the heading; the reading status looking like a selected radio button; the Source column and scoring paragraph the prototype had dropped; the primary action being half-width on one mobile state and right-aligned on another.

Raised and deliberately not changed here (judgement, or another phase's): **amber drained** (owner decision 3; Review now shows amber only on the brand mark, and the warm bars and parchment captions carry what warmth is left); **résumé names read like job titles** (the default label, decision 4, still open); **the recommendation competes with the job title** in the prototype (a tie or a split puts three bold names on the line, which is the engine's sentence); **Apply is 12px underlined text** (decision D10); the repeated **2px left rule** motif (open box, suggestion) is a risk of template feel; failure being stated five ways on the failed-read page across the run strip, lede, status and body (shared components, copy); three names for the résumé list ("All your résumés", "Your résumés", "Manage your résumés"); and the regression screens that still use the old language, which section 4 lists.

## 6. Evidence



`output/design-D3/` (git-ignored, every capture at 1440 and 390, every mobile capture checked to be exactly 390px wide; overflow is measured *before* a full-page screenshot, because the screenshot re-lays the page out and a phone emulation widens `innerWidth`, which is how a 20px overflow once printed as 0): `before-075afdf/` (this phase's own "before", including states D1 never captured: reviewed, failed, limited, reading beside a reviewed row), `after/`, `regression/` (screens that share the stylesheet but were not redesigned), `prototype/`, `compare/` and two contact sheets, `a11y.json`. Its `before-075afdf/` is listed in `EVIDENCE_MANIFEST_D3.sha256`. The original D1 and D2 sets are unmodified and still verify against `EVIDENCE_MANIFEST.sha256`.

## 7. Open decisions for the owner

1. **The placeholder fallback.** Until a résumé is read the file name is its heading. Alternative: keep "Résumé 1" as the heading and drop the numeral for that row.
2. **What the editable name defaults to** (decision 4, still open). Today it is the first search title, title-cased, which `62b7174` showed is a poor label; the screen now shows it as the heading, so the quality of that default matters more than it did.
3. **The notes**: rewrite at the source, and the wording of the disclosure ("Technical notes on how this was read").
4. **Caution before or after the suggestion.** The engine says before; the direction said beneath.
5. **Exact exports placement and the list view's lack of a primary button** (D6, D10): still to be seen on the Results page itself.
