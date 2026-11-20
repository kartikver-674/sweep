# Sweep design, phase D6: live Results

Branch `design/sweep-ui-overhaul`, starting at `75130e0`. Evidence is in `output/design-D6/`
(git-ignored, synthetic engine-shaped data only, no model, provider or paid search). The direction is
[SWEEP_DESIGN_DIRECTION.md](SWEEP_DESIGN_DIRECTION.md) section 5 and its section 0; the starting point was the
D3 prototype (`prototype/results.html`, `prototype/results-rows.css`), which is now in `sweep.css`.

## 1. The Results data contract, and what is presentation

**Authoritative (engine, through the worker and the strict reader `worker_link.multi_row`; none of it is computed
here):**

| Field | Meaning on the screen |
|---|---|
| `score`, `matched_skills`, `title`, `company`, `location`, `salary`, `experience_required`, `source_site`, `apply_url`, `date_posted` | The row. `score` is Sweep's raw fit score, signed. All Jobs shows the row's own |
| `best_track`, `track_evals` (`{id: {s, m}}`), `found_by` | A résumé's view is the rows its id is in `track_evals` (never `best_track`, never `found_by`), each with **that track's own** `s` and `m`, ranked by it. One job can be in several views with different scores |
| `recommended_tracks`, `recommendation` (`clear`, `close`, `tied`, `split`), `recommendation_caution` (absent, `""`, `no_focus_evidence`) | The job's recommendation, the same in every view. Sentences come from `logic.recommendation_words`; the caution comes first |
| All Jobs | Every row once, in the engine's order, no floor unless one is asked for (a negative score included). A one-résumé run keeps today's floor of 0 |

**Presentation only (decided in the app from the above, never fed back):** the résumé's label (the setup's editable
name, else the one the cookie froze at run start, else "Résumé n"), the file it came from, `_for`, the section a row
is filed under (`linkedin_shortlist.bucket`), `posted_age`, the source's display name and "Paid", the first three or
six skill tags, whether a Pay or Experience column is drawn, the ending notice, and the roles in the recommendation
pieces.

**Not Results' business and unchanged:** scoring, ranking, recommendation decisions, `track_evals` membership,
deduplication, the worker protocol, exports (serialisation, columns, the All-Jobs rule), plan and approval, quotas.

## 2. What changed

| | Before | After |
|---|---|---|
| Heading area | Count, a three-line lede with the scoring paragraph, a four-line note under the buttons | Count (worded for the view and for a run that did not finish), one door ("How match scores work"), one sentence for the current view |
| Résumé switcher | Three or four outline buttons, the current one a filled primary | Tabs (`nav.views`): current is text colour, 600, a 2px underline and `aria-current`; the others are warm. They wrap on a phone |
| Résumé names | The uploaded file name, in every tab, sentence and header | The résumé's **editable name** (decision 4). The file is the tab's hover and a line under the tabs, "(from mern_resume.pdf)" |
| Tools | "Filter and sort" bar with the four exports inside it | One line: "Sorted by Best match" and two buttons, **Filter and sort** and **Export…**. The line never changes: what a button opens appears under it (first built as two `<details>`, each of which jumped to a new row when opened, which the review caught). Exports are outside the filters. Four formats, all `secondary`: none is the one you are meant to want |
| Sections | A bordered panel per section with a long right-aligned caption | A heading, a count, one quiet sentence, then ruled rows; no box |
| Row (desktop) | Nine columns, the recommendation an 11px grey line, Pay and Experience "Not stated" on most rows | Match (right-aligned, tabular, 22px) · Job (title, company, then the recommendation) · Location · Pay and Experience only if some job states them · Source · Matched skills · Apply |
| Row (phone) | A grid card with the score, a cramped two-column job, a grey 12px Apply | A card: the figure beside the job, the recommendation and caution across the full width, each present fact with its word, three skills, **Apply →** as a 44px target |
| Recommendation | 11px, `meta` colour, the résumé as a file name | 13px, chalk, a 2px rule, the suggested résumé in 600, a name after it plain, and the résumés of a tie in 500 (peers: none leads, so none shouts). A caution above it in 12px warm with a ring-and-`!` (a qualification, never coral); both lines share a left edge |
| Apply | 12px underlined | 14px, 600, underlined, with an arrow, named for screen readers ("Apply to Senior Backend Engineer at Kestrel") |
| Applied tick | Amber | Chalk (amber is money); the ceiling in `test_visual_rules` fell from 16 lines to 15 |
| A run that did not end whole | Results looked like a finished search | A banner in the Running screen's own words, see section 5 |

**Shared rules touched:** only Results'. Every other screen is pixel-identical at 1440 and 390 (section 7).
`.toolbar`, `.score-help`, the `.listings` grid and the old `.head-note` caption rules are gone; `.listings` remains as
the scroll wrapper whose `overflow`/`contain` keep the page from scrolling sideways.

## 3. The recommendation, and why the names are bold

The engine's sentences are frozen. `logic.recommendation_pieces` now writes them once, as `(text, role)` pieces (role
`name` for the résumé the engine leads with, `peer` for each résumé of a tie, `other` for one named after the lead, `None`
for the engine's own words), and `recommendation_words` is the flat text of the pieces. The template draws each piece as
escaped text, so:

- nothing searches a finished sentence for a name, so a label inside another label ("Backend" inside "Backend
  Engineer"), one with parentheses, punctuation, quotes or markup cannot mis-split or inject;
- `test_results_ui.Pieces` compares the pieces' joined text with a **frozen copy of the pre-D6 implementation** for
  every kind, one to three names, three caution states and ten awkward labels (288 cases), and compares
  `recommendation_words` with it too: "the same words" is checked against the original, not against itself;
- no word changed: "Suggested résumé:" is not "Use", a caution comes first, an absent caution and `""` say
  nothing, no engine code reaches the screen, and a low or negative score never hides a recommendation.

## 4. Résumé identity, and the one thing deliberately left inconsistent

The screen's label is `app.run_identities()`: the setup's editable name for that **id** (a rename after the run
started is followed, and the cookie's frozen label is updated by the rename as before), else the cookie's frozen
label, else "Résumé n"; two labels that read alike are told apart by their place in the run. The file name never
replaces it. This reverses `fdb0da0`'s file-name labels on Results, as decision 4 says, and the tests that pinned
file names were restored to the rename-following versions they were before `fdb0da0`.

**The exports keep `run_labels()` (file names) on purpose:** the brief freezes export serialisation, and a label cell
is the exports' data. So the screen says "Backend Engineer" and the file says `backend_resume.pdf`.
`test_the_exports_keep_naming_the_files_while_the_screen_names_the_labels` pins the difference so it is a decision and
not an accident. **Owner decision:** make the two agree (`run_labels` and `run_identities` are one line apart).

## 5. States

- **Missing facts.** A Pay or Experience column exists only when some job in the list states it; a job that does not
  shows a quiet dash spoken as "Not stated" (never a visible "Not stated" on every row), and on a phone an absent fact
  is not drawn at all. A fact that is drawn carries its word on a phone ("Pay INR 45–60 LPA", "Experience 8+"). No unit
  is added: the data says `8+`, not "8+ yrs". The data is untouched and stays in every export.
- **Negative and one-digit scores** keep their sign and sit on the ones digit; titles align at one x whatever the
  score's width (measured on a phone).
- **Applied and Opened.** Unchanged in where they exist and how they persist: Applied is the operator console's ledger
  (`POST /applied`, not reachable in public mode, so the public page draws neither the tick nor its column); Opened is
  this browser's `localStorage`, in both modes. Neither fades a row (D2): the title steps down one notch and the row
  says "Applied" or "Opened" in words.
- **Empty.** A run that found nothing, a filter that removed everything (the filter that removed most is named, with a
  way to clear it), and a résumé with no evaluations each say one thing and offer one way on ("Show All Jobs").
- **A run that did not end whole.** The run strip stands down on Results for every ending (it would point at where the
  reader already is), so a failed, stopped or part-run search looked exactly like a finished one. Results now reads
  the Running screen's own state (`sweep_state` through `_liveness`, so the two cannot disagree) and says, in D5's
  banner: "This search did not finish", "This search ran out of time" (only on the worker's own `run_timeout`), "You
  stopped this search", "Part of your search ran", "Your search did not start", "This search stopped when the credit ran
  out", each with one plain sentence and nothing for a search that finished whole. A result the worker declared final
  stays a success after a crash, as in D5.1. Two limits are recorded in `SWEEP_RELEASE_BLOCKERS.md` (entries 3 and 4).

## 6. Tests

`test_results_ui.py` (43 tests): the recommendation pieces (exact-wording guarantee, roles, hostile labels); columns,
dashes, phone labels, the score's CSS and text, no percentages; Applied and the tick in the console only; Apply's
destination, name and targets; the tools (closed until filtered, Export outside Filter and sort, four alike links,
filters carried, All Jobs whatever view is open); tabs (same ids, counts and carried filters; one current);
membership (one job in several views with each view's own score; a negative row still a row); every recommendation
situation with the name set apart and the caution first; markup and parentheses in a label; a run with no
recommendation; the endings on the console, in public, and through the real worker; amber and type-size rules in the
Results CSS. Presentation pins in `test_app`, `test_multi_results_view`, `test_public_copy` and `test_visual_rules`
were updated to the new markup (nav class, `<thead>`, `.jobs`, the label source, flat text for sentences with bold
names); their behavioural assertions are unchanged.

## 7. Evidence

`output/design-D6/` (git-ignored, every capture at 1440 and 390, overflow measured before the full-page screenshot,
every PNG's width checked):

- `before-75130e0/` (read-only; listed in `EVIDENCE_MANIFEST_D6.sha256`): the live Results at the parent, every state.
- `after/`, `flows/`, `a11y.json`, `contact-sheet-*.png`, `recommendation-states-*.png`, `compare-prototype-*.png`.
- `regression-before/` and `regression-after/`: Upload, Review, Configure, Key, Confirm and Progress states that share
  the stylesheet. Every one is pixel-identical except two animation frames (the indeterminate bar and the activity dot).
- `flows/` and `flows.log`: four browser flows (A schema 1: filter, sort, export, Apply; B schema 2: All Jobs then each
  résumé then back; C each recommendation situation, desktop and phone; D long label, long title, missing values, a
  negative score), with Apply links intercepted so nothing leaves loopback.

The D1 to D5.1 sets and manifests are untouched and still verify.

## 8. Independent critique, and what came of it

A fresh reviewer who had seen neither the code nor this conversation judged the before/after captures and sheets
against ten questions and seven states. **Strong:** score readability and Apply on desktop, tabs on desktop, the
"no evaluations" and "filters match nothing" states. **Adequate:** desktop scanning, recommendation prominence, mobile
hierarchy, filter and export discoverability ("bordering weak"), consistency with D3 to D5 (the shared-CSS sheets show
no difference), accessibility, noise. **Weak:** a search that failed part-way, and a run with no recommendation.

It listed twenty defects. Fixed and recaptured:

| Defect | Fix |
|---|---|
| A failed or part-way run kept "14 jobs matched your profile" | The count says "14 jobs found before the search stopped" (or "from the part of your search that ran") whenever the ending notice is shown |
| A résumé with no evaluations said "0 jobs matched your profile" beside tabs showing other jobs | A résumé's view says "5 jobs evaluated for Backend Engineer" |
| With no recommendation the column and caption still said "suggested résumé" | "Job" and "Every job once." unless a row carries a suggestion |
| The opened Filter or Export door jumped to a new row, and the other stayed put | Two buttons; the line never changes, the panel opens under it (and the triggers are underlined words, as in the prototype) |
| A résumé's view lost the visible "for <résumé>" on the score header | The view sentence is 13px warm and names the résumé and the file; the score cell's hover still says which résumé's score it is |
| No "match" label near the score on a phone | The word "match" under the figure, phone only |
| Wrapped tabs left the current underline floating | Two-column grid on a phone, each tab with its own rule |
| Mobile tabs about 40px | 44px on a coarse pointer |
| "Applied" and "Opened" sat in different places | Both directly after the title |
| Console empty state offered "Clear every filter" with none set | Only when one is |
| A name broke mid-name ("MERN Stack / Developer"), and its full stop could wrap onto a line alone | A name and the mark after it are one unbreakable unit (`.nb`); the sentence's text is unchanged |
| Company inline on some phone items and stacked on others | Always its own line on a phone |
| Caution text and suggestion text started at different x | Both start 22px in (ring 16 + 6, rule 2 + 20) |
| "Sorted by Best match" bold, like a control | Plain text |
| Cells 2px off the title's baseline; the columns of each section sized themselves | `vertical-align: baseline`; fixed layout and one set of widths, so every section's columns start at the same x |
| Three "Clear" controls over an empty filter result | The bar's Clear stands down when the empty state offers them |
| Four "(0)" tabs, "Filter and sort" and a scoring door wrapped around nothing | A run with no jobs draws none of them |
| "Best matches first." and "Sorted by Best match" said the same thing (and the first was wrong under another sort) | The public lede is gone; the tools line says the real order |
| Tied names nearly as heavy as the title | Peers of a tie are 500; a name after the lead is plain; only the lead is 600 |

Raised and deliberately not changed: the console header's "Spent" bar with its 1px tick at the right edge (present
before D6, on D5's list); the nested parentheses when a label contains its own ("... (Payments (EU))"), which is the
engine's sentence around the visitor's own words; the bare experience values ("8+", "3–5"), because the data says
`8+` and adding "yrs" would invent a unit; the hyphen in "-3" (the raw signed value is kept as it is); the ring
beside "Note:" (a shape so the caution does not rest on colour; it is in the approved prototype); the dashed "+N"
chip; "Paid" under a paid source (it says so in words, not colour); identical skill chips on every synthetic row (an
artefact of the test data); the operator's Applied tick, which has never been drawn on a phone (`td.did` is hidden
there, as before), so Applied can be read but not set from one.

## 9. Open decisions for the owner

1. **Export label cells.** The screen names résumés by their editable name; the exports still carry the uploaded file
   (frozen by the brief). Make them agree? One line: `run_labels` and `run_identities`.
2. **The operator's Applied tick on a phone** (unchanged): show it, or leave Applied a desktop action.
3. **A unit for Experience.** The data says `8+`; the prototype said "8+ yrs". Only if the engine's field is always years.
4. **The per-card Apply row on a phone** (a rule, then "Apply →" and the posted age) is about 65px of a card. The review
   called it dead space; it is the 44px target the brief asked for. Moving the age up beside the company would shorten it.
5. **Release blockers 3 and 4** (paid run with a complete ledger but a failed process; the worker's own `stopped`
   status after a restart) are recorded in `SWEEP_RELEASE_BLOCKERS.md`. The saved-profile bytecode blocker (1) is still open.
