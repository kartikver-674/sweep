# Sweep design, phase D4: upload, résumé management, search preferences

Branch `design/sweep-ui-overhaul`, starting at `4061b1e` (D3, approved). Evidence is in `output/design-D4/`
(git-ignored, synthetic data only). This note records what changed, what was found, and what is left. The direction
is in [SWEEP_DESIGN_DIRECTION.md](SWEEP_DESIGN_DIRECTION.md); the shared rules are in [SWEEP_D3_NOTES.md](SWEEP_D3_NOTES.md)
and were applied, not re-decided. **Presentation only**: `app.py`, `pick.js`, `reading.js`, `motion.js`, every form
field name, every route, the 15 MiB total limit and the three-résumé maximum are byte-for-byte as they were.

## 1. What each screen was, and is

| | Before (D3 commit) | After |
|---|---|---|
| **Upload, empty** | The mark twice (header, then 56px beside the title); a 34px title; three headings that said one thing ("Find jobs…", "Start with your résumé", "Add up to 3 résumés"); a panel around the form; "What happens next" as a fourth box; three reassurance tiles under a rule; the whole page 74rem wide and left-anchored | One `h1` and one sentence (what Sweep does), one `h2` and one sentence (what to give it), the drop zone, the button. One rail to the right for what to expect. The page uses the shared 88rem measure and the same main-plus-rail split as Configure |
| **Batch picker** | The drop zone stayed 160px tall under its own list; each chosen PDF was a `PDF` chip, a name, a size and an outline button; "3 of up to 3 chosen." | Empty: the dashed zone, the one thing with a dashed edge. One chosen: the zone shrinks to a line that says how many more fit ("Add another PDF — 2 more fit"). Full: it is not drawn, and the count says "3 of 3 selected. Remove one to add another." The list is ruled rows: name, size, an underlined **Remove** (its accessible name still says which file) |
| **Reassurance** | Three tiles of equal weight (Free every run, Priced per search, Nothing is kept), a steps panel, and a free-note in the form panel | One rail of ruled notes: what happens next; **Free** (teal word); **Paid, and optional** (amber word); **Nothing is kept**. Every fact is kept; none is added or strengthened. The free-note beside the button is one short sentence |
| **Résumé list** | A panel containing a panel per résumé: `1. Backend Engineer` + file name top-right, a status sentence ("Ready · In this search"), four to five equal outline buttons, then a rename form always open (label, field, button) | The D3 ledger: a numeral, the editable name as the heading with the file under it, status as a shape and a word. Review is the one outline (until a résumé is reviewed; then it is **Edit**, a word, as on Review); Leave out, Move up and Move down are words; **Remove** is a word in the error colour, set apart at the far end of the row; **Rename** is a door beside the name and opens the field under it (a `<details>`, so it works without a script) |
| **Capacity** | At three résumés the heading still said "Add another résumé" | 0 to 2 left: "Add up to 3 / 2 more résumés", "Add another résumé". None left: no heading, no drop zone, one sentence |
| **Preferences** | Five to seven panels, three nested when Advanced opened; every panel a full-width box | Ruled rows on one page: what the group is and what it means on the left, its controls on the right, the same shape as a finding on Review. Advanced is a door between rows, with its own rows; no panel, no sub-panel |
| **Preferences summary** | Two panels (what it searches; estimated cost) | One panel, because it is one thing; the cost figure keeps its own well, the one boundary that means something |

## 2. Shared rules this phase touched

Everything new reuses a D3 rule; nothing is a second vocabulary.

- **Reused unchanged:** `.ledger`, `.resume`, `.status` (and its six shapes), `.actionbar`, `.choice` with its 2px chalk rule, `.stepper`, `.picker`, `.headline-figure`, `.tag`, the primary / secondary / tertiary weights, `details` + `::before` marker, the focus ring.
- **Changed (shared):** `.summary dt` 10px uppercase to 12px sentence case (Confirm's three labels change with it: the only screen D4 did not redesign whose pixels moved, by a few lines, see section 6). `.affects` 10px uppercase amber to 12px amber words ("Affects cost"). `.next-steps` numerals from amber 10px to neutral 12px (a step is not money; the amber ceiling in `test_visual_rules` fell from 21 lines to 20).
- **New (Upload and Preferences only):** `.drop.compact`, `.picked-list` / `.picked-row`, `.upload-foot`, `.rail` / `.rail-block`, `ol.ledger`, `.name-line`, `details.rename`, `.row-actions` and its four groups, `button.tertiary.danger`, `.setting` / `.setting-head` / `.setting-body`, `details.advanced`, `.summary-panel` / `.summary-cost`.
- **Removed:** `.hero`, `.front*` (the 74rem column), `.strip`, `.picked` (the chip row).

## 3. Decisions worth knowing

- **Status words on the list now match Review.** "Ready" meant *reviewed* here and "Ready to review" meant *not yet* on Review, for the same résumé. The list now says Reviewed, Ready to review, Reading now, Not read yet (kept: nothing on this page reads it), Couldn't finish, Left out. `In this search` is no longer printed on every row; a résumé left out says so as its status and in a line, and is muted like Review's.
- **One primary per view, and the list may have none.** (Review is an outline only while a résumé still needs reviewing; a reviewed row offers *Edit* as a word, as Review does, so three outlined buttons never compete with *Continue*.) With a ready setup the primary is *Continue to job search* and adding another résumé is an outline beside it; with files chosen and nothing ready, the read button is the primary; with three résumés still to review there is no primary and each row's Review is the way on (the direction allows a list with no primary; the owner may prefer to promote the first unreviewed row's Review).
- **The file name stands in as the heading until a résumé is named**, exactly as on Review (D3 open decision 1 stands; the same rule is applied here so the two screens agree).
- **Advanced opens when the screen comes back with an error**, because the field that is wrong is inside it. Before, a refused "Words to rank lower" left Advanced shut and the message pointed at a field nobody could see. The form does not keep the refused text (it never did).
- **The depth stepper is no longer inside a `<label>`.** A label around two buttons and a field forwards a click on its text to the first of them, the minus, so clicking "Jobs per search" lowered the depth by five. The field keeps its accessible name; the text is now a heading.
- **Fields are described by their explanation** (`aria-describedby` on How recent, Jobs per search, Minimum salary, Words to rank lower) and the scope choices are a labelled radio group.
- **Free versus paid, unchanged in meaning:** a free sweep's "Where Sweep searches" is a statement and one link (was a dashed paragraph and an outline button); a paid sweep's Sources, Locations and Jobs per search carry an amber **Affects cost** beside the heading, the filters carry nothing, and the summary panel shows the paid boards in amber, the free ones in teal, the cost lines and the cost figure. Over the credit the figure stays amber and the sentence under it stays coral. No copy about cost, credit, the cap or approval was reworded.

## 4. Mobile

- **Upload:** the heading and sentence, the zone, the list as ruled rows (name, size, Remove on one line), the count, one note, the button at full width, then the rail as ruled notes. No empty margins; no stacked box.
- **List:** the four groups of actions fall into two lines on purpose: the first action and *Leave out* above (what moves the résumé on, and in or out of the search), *Move up / down* and *Remove* below, Remove alone at the far end and never stacked over the word used most. *Rename* sits at the end of the file line on every row, and an open Rename takes the line under it. Every target is 44px. A long résumé name wraps at word boundaries and a long file name is cut in the middle; the 21px horizontal overflow that a 57-character file name caused before is gone. The way on is full width and in the flow (not pinned).
- **Preferences:** rows stack (name, explanation, control), full-width choices and fields, the summary panel and its one action after the last row, in the flow (not pinned, as instructed).

## 5. Findings that are not D4's

- **A pre-existing race in `POST /estimate` can put a price check's candidate into the saved session.** `estimate()` snapshots `app.state`, swaps a candidate in, prices it, and restores the snapshot. Two price checks that overlap (any two edits inside one check's latency: rapid clicks on the depth stepper, two sources ticked in a row, tabbing from one field to the next) leave the session holding the *earlier check's candidate*, because the later check's snapshot was taken while that candidate was swapped in: a value the visitor never saved becomes the saved value. And a check that started before a Save can finish after it and write the old values back. Reproduced with no template involved (a throwaway script outside the repo: two overlapping `POST /estimate` and no save committed a candidate in 3 of 6 trials), and in the browser (a quick run of edits and a Save came back with the last edit missing, or an earlier one restored). `app.py`, the `@change` handler in `configure.html` and the scripts are unchanged by D4 (`git diff 4061b1e -- sweep/app.py` is empty), so this is identical at `4061b1e`. **Not fixed: it is Configure logic and this phase is presentation.** A real fix is small (serialise `/estimate` behind a lock, or price the candidate without swapping the shared state) and wants its own test. The browser flow for the free path was therefore run with the price check held back, which isolates D4's own serialisation and save; the paid path was run with it live. **Fixed afterwards, in D4.1** (`fix(web): isolate price estimates from saved session state`): `/estimate` now prices a private copy that only its own request can see (`SweepApp.state` + `priced_as`), so the live session is never written to and there is nothing to restore; `sweep/tests/test_estimate_isolation.py` holds the barrier-driven regressions, which fail 19 of 28 on `a2b9f75`. **D4.2** then closed the three things D4.1 left: the Configure page hears only the newest price check (`static/price.js`, tested in `price_test.js`), so a slow early answer can no longer put an older price on screen or an old error beside a valid one, and the figures are dimmed from the change until the newest check answers with a price; a preference save is applied as one `update()` of only what it changed, so no snapshot sees a half-applied session and another request's edit is not put back; and a console estimate prices a scratch profile (`<name>_est_<12 hex>`, discarded afterwards) instead of overwriting the saved one, which also stops a same-second, same-size rewrite of `profiles/<name>.py` being priced from stale bytecode.
- **Nothing on the Confirm screen was redesigned**, but it shows three summary labels in the new 12px words, and its phone layout is two pixels taller.
- **Pre-existing, unchanged:** the local operator console's paid Configure is 1px wider than the phone viewport (`.meter-cap`, identical at `4061b1e`).

## 6. Shared-CSS regression

Before (`4061b1e`, served from an exported tree on another port) and after, the same states, pixel-compared at 1440 and 390: Review (all states), Results (both views), Key and Running are **pixel-identical**. Confirm's three summary labels changed (12px words for 10px capitals), which is the change listed in section 2. No overflow and no contrast failure on any of them.

## 7. Independent critique, and what came of it

A fresh reviewer, told to be adversarial and to judge against the direction and against the approved Review screen, looked at the before and after screenshots of every state (and the screens D4 did not redesign) with `design-taste-frontend-v1` and `minimalist-ui` as lenses. **Verdicts on the eleven questions:**

| | |
|---|---|
| Stronger first impression | adequate ("cleaner, not stronger": calmer and the repeats are gone, but nothing on the empty page is memorable) |
| Concise instructions | adequate (the process is still told at three levels: the sentence, the steps, the notes) |
| Picker obvious | strong empty; adequate selected, full and refused |
| File rows compact | strong |
| Management easy to scan | strong on desktop; adequate on a phone (before the fixes below) |
| Preferences less technical | adequate (the structure is calmer; some of the copy is still technical, and that copy is not D4's to reword) |
| One dominant action | strong on Upload and Preferences; adequate on the list |
| Paid and free distinct | strong; the over-credit state was underplayed (fixed below) |
| Mobile composed | adequate (before the fixes below) |
| Same product as Review | strong |
| Shared-CSS regressions | none; Confirm's label change is correct, and it leaves Confirm as the odd one out beside two ruled screens |

**Objective defects it found, all fixed and re-captured:** (1) a refused rename came back with every door shut, so the message pointed at nothing: the refused row now opens on what was typed, marked `aria-invalid` (read from the request that just failed, not from state; nothing was saved, and `app.py` is untouched); (2) on a phone *Leave out* sat directly over *Remove*: it now sits beside the first action and Remove is alone at the far end of the second line; (3) *Leave out* moved between rows on a desktop: it is now second in every row; (4) *Rename* wrapped differently from row to row on a phone: it is now at the end of the file line on every row; (5) a reviewed row kept an outlined Review: it is now the word Edit, as on Review; (6) the depth stepper's field sat 4px below its buttons: a global field rule's margin outranked the stepper's (fixed in Preferences only, so the approved Review steppers are as they were); (7) the Locations field's caret rendered as a 3px dot: it is drawn like the select's chevron; (8) over the credit the figure stayed amber, identical to a figure within it: it is now coral with a coral well and a `!` beside the sentence (the same shape Review uses for "couldn't finish"); (9) the "What happens next" steps still showed on a list of résumés already read: they are for someone who has not started, and are not shown there; (10 and 11) the gutter before the rail and the summary widened from 1.5rem to 2rem, and the count line has room above the free note.

**Raised and not changed:**
- *The process told three times* (lede, steps, notes): each says it at a different level and all are kept; removing one is a copy decision for the owner.
- *Field errors are far from the field* (a refused value in Advanced; the upload banner sits above the heading): the route returns one sentence and the template cannot tell which field it names, so only the rename case could be placed. Advanced does open on an error.
- *Underline soup* (five underlined words on a row): only Remove's colour separates it; a judgement.
- *Free to paid is a quiet link*: the direction specified "a statement with one link".
- *The open Locations menu is eight boxed rows*: each is a thing to press and keeps its edge, as the brief asks.
- *On a phone the cost is at the end of a paid page*: the summary is in the flow and nothing is pinned, as instructed.
- *Confirm is now the odd one out*: its phase is next.
- *Type is 12 and 13px beside a 14px body*: the floor is 12 and the scale is D3's.

## 8. Evidence

`output/design-D4/` (git-ignored, every capture at 1440 and 390; overflow is measured before each full-page screenshot and each PNG's width is checked against the viewport): `before-4061b1e/` (this phase's own "before", every required state), `after/`, `regression-before/` and `regression-after/`, `compare/` (one before-and-after image per state), `contact-sheet-desktop.png`, `contact-sheet-mobile.png`, `contact-sheet-shared-css-desktop.png` and `-mobile.png`, `flows/` (the three browser flows), `a11y.json`. `before-4061b1e/` and `regression-before/` are listed in `EVIDENCE_MANIFEST_D4.sha256` and made read-only; the D1, D2 and D3 manifests still verify.

## 9. Remaining migration and open decisions

- Still in the old language: Confirm's boxes, Search progress, Results (the D3 prototype is the plan), the Key step's two cards, the 404, 17 sub-12px declarations (down by the `.summary dt`, `.affects` and `.next-steps` ones), the non-money amber in `.tick`, `.cell.running`, `.numeral-inline`, `.callout.warn` and `.banner.warn`.
- **Owner decisions:** (1) whether the first unreviewed row's Review should be the page's primary when nothing is ready; (2) whether the file name may stand in as the heading until a résumé is named (D3 decision 1, now applied on two screens); (3) the `/estimate` race, since fixed as its own change (D4.1); (4) the wording of the free-note beside the read button ("Free. Reading your résumé spends no credit. Sweep reads it with an AI model to work out what to search for.").
