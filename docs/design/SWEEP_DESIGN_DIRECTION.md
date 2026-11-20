# Sweep design direction (Phase D1)

**Status (2026-09-30): Quiet Ledger approved by the owner as the direction to prototype,
with the amendments in §0.** Every value below is still provisional until a
representative screen has been built and looked at. Evidence for each claim is in
[SWEEP_VISUAL_AUDIT.md](SWEEP_VISUAL_AUDIT.md) (section numbers below refer to it); the
audit is a record of what was observed at `fdb0da0` and is not edited.
An independent critique of the first draft changed this document materially; §7 says how.

## 0. Owner decisions (approved 2026-09-30)

These override anything later in the document that says otherwise. Where they changed
the text, the text has been corrected and marked *(amended)*.

1. **Direction.** Quiet Ledger is approved as the visual direction to prototype.
2. **Identity.** Sweep's warm-on-teal identity stays. Bricolage Grotesque and Geist stay.
3. **Amber** is reserved for **monetary information and the existing brand mark**.
   Teal means free or ok, coral means error, over cap or destructive. Focus, selection,
   progress and "you are here" are neutral.
4. **Résumé identity.** The **editable résumé name is primary; the original file name is
   secondary.** This supersedes the first draft's "file name everywhere" (and the audit's
   §4.2 principle). It also reverses `fdb0da0`'s choice to label a run's résumés by file
   name on Results; that is done in the Results phase, not before. What the editable name
   defaults to is **open** (today it is "Résumé N" until read, then a role title read off
   the résumé, which `62b7174` showed is a poor label): to be proposed with the
   Upload and Review phase and approved there.
5. **Recommendation wording** keeps its existing relative-suggestion semantics. "Suggested
   résumé" is **not** turned into an imperative "Use"; the engine's five phrasings
   (`logic.recommendation_words`) are preserved as they are.
6. **Scores** remain raw fit/coverage scores: no percentage, band, letter or rename.
7. **Dark theme only** for this redesign.
8. **Exports** may move out of "Filter and sort".
9. **No pinned mobile call-to-action** without visual approval. A pinned bar may be shown
   as a clearly labelled variant for that approval; it is not built into a screen until
   approved.
10. **Internal diagnostic notes** (the text behind "Worth knowing", field names, file
    paths) must not be presented as a user-facing explanation. The principle is decided;
    the replacement wording is **open** and will be proposed for approval in the Review phase.
11. **Shared visual changes cover both** the public app and the local operator console,
    which share templates and this stylesheet.
12. **One branch.** The whole overhaul is developed on `design/sweep-ui-overhaul` and
    merged to main only after the complete redesign passes final review (§8).

## 1. Verdict on the hypothesis

The hypothesis was **Calm. Precise. Utilitarian. Premium.** The audit supports the first
three and changes how to get to the fourth.

Sweep is already calm, precise and utilitarian. It has no gradients, glass, shadows or
decorative icons, and it is honest about states. What it lacks is **decisiveness**: nothing
on any screen is clearly the most important thing (§4.3, 4.4, 4.8), every block is boxed
equally (§4.5), and the screens do not share a grid (§4.6). The "generated" feeling comes
from uniform treatment, not from excess.

So this is a **tightening, not a reskin.** It keeps what is already ownable (the
warm-on-teal palette, Bricolage Grotesque, the amber mark) and fixes what is unresolved.
"Premium" comes from restraint and finish: colour that means one thing, one grid, type
that can be read, components that behave the same everywhere. A redesign that added
texture, glow, or a fashionable neutral palette would make Sweep look more generated.

## 2. The direction: a quiet ledger

Sweep takes résumés in and puts ranked roles out. Its interface should look like a
well-kept ledger: ruled sections on one ground, figures set as figures, colour reserved
for meaning, and the decision (which résumé, which job, what it costs) as the loudest
thing on each screen.

Five rules carry the direction:

1. **Rules, not boxes.** A bordered container appears only where a boundary changes
   meaning: the résumé being edited, a dialog, a cost total. Everything else is separated
   by a hairline and spacing. Hierarchy comes from type, rules and space, not from fill
   (fills differ by only ~1.13:1 and cannot carry it).
2. **Colour means one thing each.** Amber is **cost**. Teal is **free / done / ok**.
   Coral is **error, over cap, destructive**. Everything else, including focus, selection,
   progress and "you are here", is neutral. This restores the signal that the stylesheet's
   own header already promises (§4.3).
3. **The decision is loudest.** Each screen names its one decision and gives it the
   strongest weight. Zeros, repeats and reassurances get quieter. A list view may have no
   primary button at all.
4. **Figures are typeset as figures.** Tabular figures, right-aligned numeric columns,
   scores at display size. Absent fields are omitted or shown as a dash, not as a sentence.
5. **One résumé identity** *(amended)*. The résumé's **editable name**, everywhere, with the
   original file name as secondary text (middle-truncated, full name in the accessible
   name). Position numbers appear only where order is the point (Upload and Review).

What makes this a ledger and not just "less boxes": ruled rows, a right-aligned figure
column, small-caps column heads, rank numerals, tabular numerals everywhere, and a single
measure. The existing rank numerals and column heads are the seed of it.

## 3. Brand direction (lightweight)

| Aspect | Direction |
|---|---|
| Personality | Exact, unhurried, dependable, a little dry. Says what it did and what it will do. Never excited |
| Wordmark | Keep the existing mark and "Sweep" in Bricolage Grotesque. No replacement. Drop the second, 56 px copy of the mark in the Upload hero (§4.11) |
| Palette identity | **Keep** the warm-on-teal pairing: a teal-black ground with warm parchment secondary text and an amber mark. It is the most ownable thing Sweep has and an unusual combination; replacing it with graphite and cool greys would make Sweep look like every other dark developer tool |
| Accent | No new accent. Amber (`#f0a22e`) stays as the cost colour and the brand mark, and nothing else *(decision 3)*. The primary button stays a neutral high-contrast fill |
| Type pairing | **Bricolage Grotesque** for page titles, section headings and large figures (cost, score). **Geist** for body, UI and data. Only h3 and widget labels move to Geist |
| Icon philosophy | Almost none, as today. State is shown with the shapes the app already draws (ring, filled dot, tick, `!`), always beside a word |
| Surface and shape | One 4 px radius (removing the 2 and 3 px stragglers), hairline rules, no shadows, gradients or blur |
| Motion | Only for real events: a read finishing, a search completing, a cap crossed. 120 to 200 ms, `transform` and `opacity`, the one existing "alive" pulse, reduced motion already honoured globally |
| Light and dark | Dark only for the redesign. Making tokens semantic (cost, free, danger, focus) rather than named by hue lets a light theme follow later. Declare `color-scheme: dark` now. Light is out of scope for this redesign (§0.7) |

## 4. Provisional design system

"Existing" values are read from `sweep.css` at `fdb0da0`. "Proposed" values are starting
points to be judged on a built screen. Contrast figures were computed.

### 4.1 Typography

| Role | Existing | Proposed |
|---|---|---|
| Display (Upload hero only) | Bricolage 34 / 700 | Bricolage 36 / 40, 600, -0.02em |
| Page heading (h1) | Bricolage 24 to 28 / 700 | Bricolage 26 / 30 (22 / 28 mobile), 600 |
| Section heading (h2) | Bricolage 18 / 600 | Bricolage 17 / 24, 600 |
| Sub-heading (h3) | Bricolage 15 / 600 | Geist 14 / 20, 600 |
| Body | Geist 13 / 18 | Geist 14 / 22, `max-width: 68ch` (already), `text-wrap: pretty` |
| Supporting | 11 to 12 px, `--slate` | Geist 12 / 16 floor, `--slate` for captions, `--warm` for anything that must be read |
| Labels | 10 px uppercase, 0.08em | 12 px medium, sentence case. Table column heads may keep small caps at 12 px |
| Data | Geist tabular 12 to 13 | Geist 13 / 18 tabular, numeric columns right-aligned |
| Figures | Bricolage 20 px desktop, 28 px mobile (score); 44 to 56 px (cost) | Scores stay **raw fit/coverage scores** *(decision 6)*. Score stays **at least 20 px**, right-aligned, tabular (check that Bricolage has tabular figures on the prototype; fall back to Geist 600 only if not). Cost numeral keeps size when money is at stake |
| Scale | 19 sizes | 8: 12, 13 (table cells), 14, 17, 22, 26, 36, plus the 44 px meter numeral |

### 4.2 Colour

Most of the existing palette is kept. The changes are to the specific problems the audit
measured.

| Token | Existing | Proposed | Reason |
|---|---|---|---|
| ground, surface, surface-low, surface-high, well | `#03161c`, `#0f2228`, `#0b1e24`, `#1a2c33`, `#001017` | unchanged | identity; no fill contrast gain is available, so hierarchy does not rely on fill |
| hairline (decorative) | `rgba(37,55,62,.9)` | unchanged | dividers only |
| **control border** | same hairline, 1.32:1 | `#5d7078` (3.17:1 on surface, 3.31 on surface-low, 3.73 on well) | A7: fields, selects, radio cards |
| text | `#d2e6ee` | unchanged | 12.7:1 on surface |
| warm (secondary) | `#d7c3af` | unchanged | 9.6:1 |
| slate (muted) | `#9f8e7b` | unchanged; captions only | 5.2:1 |
| **dim** | `#524435`, 1.75:1 | **never for text**; hairline-only use | A1 (rank numerals, `.stages .next .meta`) |
| amber | `#f0a22e` | unchanged, **cost only** (plus the mark and cost warnings) | see rule 2 |
| teal | `#7ed6cd` | unchanged; free, done, ok. **Not** for links or source names | §4.3 |
| coral | `#ffb4ab` | unchanged; error, over cap, destructive text | |
| links | teal | `text` colour, underlined | rule change, not a token change |
| **focus ring** | amber 2 px | `text` colour 2 px, 2 px offset (12.7:1) | amber is cost; focus must not borrow it |
| primary button | `--chalk` fill, hard-coded `#fff` hover | `--chalk` fill, hover from a token | one primary per view |

Money: the cost figure stays amber, because it is the product's one safety cue that an
action spends credit. "Start Free Sweep" and a paid start must not look the same:
**paid actions carry the amber cost figure beside the button**, and free ones do not.
Amber leaves everything that is not cost: the focus ring, selected radio, checkbox accent,
weight bars, stepper and drop-zone hover, the tracker's current step, and the progress
dot. The tracker's current step becomes `text` colour with a filled marker; done is a
tick; locked is muted.

### 4.3 Geometry and layout

| Item | Existing | Proposed |
|---|---|---|
| Spacing | 2, 4, 8, 12, 16, 24, 32 px | Keep; add 48 px between page sections |
| Radius | 4 px plus 2 and 3 px stragglers | One 4 px |
| Page measure | `main` 88 rem; Upload 74 rem left-anchored | **Keep 88 rem on every screen** (Results needs it: the table sets `min-width: 60rem`). Upload uses the same main-plus-aside split as Configure, so its content no longer stops 216 px short of the others |
| Breakpoints | 30, 40, 48, 60, 64 rem | **Unchanged.** The table-to-card switch at 47.99 rem depends on the table's 60 rem minimum width; moving it would create a 40 to 60 rem band where the table scrolls |
| Responsive principle | Stack every desktop box | Reflow by priority. Collapse résumés not being edited to a row. Omit absent fields. Keep the primary action reachable |

### 4.4 Components

| Component | Direction |
|---|---|
| Primary button | Existing neutral fill, one per view. A collapsed résumé's "Review" becomes secondary. Hover and pressed are defined: lighten by token, then `translateY(1px)`. Disabled stays as is |
| Secondary | Transparent, control-border outline |
| Tertiary | Underlined text: "Manage your résumés", "Back", "Leave out" |
| Destructive | Secondary shape with coral text, never filled; confirm only where data is lost |
| Input / select | Existing fill with the new 3:1 control border, label above, helper below; `color-scheme: dark` for native menus |
| Checkbox / radio | Whole row is the target (already true). Selected row takes a 2 px `text`-colour left rule instead of an amber border |
| Tabs (results switcher) | Same `<nav>` and `aria-current`; tab labels are the résumés' editable names *(amended)*. Current tab: `text` colour, 600, 2 px `text` underline. Others: warm. Maximum four tabs (All plus up to three résumés), so they **wrap** rather than scroll on mobile. No button fill |
| Status | The shapes the app already draws in `.stages` and the tracker: ring = waiting, pulsing filled dot = reading, filled dot = ready to review, tick = reviewed, `!` in coral = couldn't read, dash and muted text = left out. Always with the word. Replaces the uniform grey "Ready to review". The per-row source bullet on Results is removed so the dot keeps one meaning |
| Résumé section | A ruled row *(amended)*: position number (Upload and Review only), **editable name** (primary), original file name (secondary, smaller), status at right. Only the **open** résumé is emphasised, with a `text`-colour left rule and a full control-border outline, not a lighter fill |
| Job result item | See §5, Results |
| Skeletons | Keep the still bones and single pulse |
| Error and empty | Keep the left-rule banner. Add a branded 404 and error page in the shell. Empty = one instruction plus one action. Remove the empty dashed "No paid sources" box on Confirm |

### 4.5 Accessibility fixes (designed, to ship first)

| Finding | Fix |
|---|---|
| A1 rank numerals | Use `--slate` |
| A2 applied and opened rows at .45 / .62 opacity | Keep full opacity. Mark Applied with a muted `✓ Applied` word and `--warm` text (9.6:1); opened rows use the browser's visited colour only |
| A3 arrival feed dimming to .35 | Floor at .7 or drop the dimming |
| A4 skip link | One visually hidden, focus-visible link before the header |
| A5 small targets on fine pointers | Give Apply, "Manage your résumés" and summary rows a 24 px minimum height (the 44 px coarse-pointer rules stay) |
| A6 colour-only state | Status always has a word or shape (§4.4) |
| A7 control boundaries | `#5d7078` control border |
| Guidelines gaps | `color-scheme: dark`, `theme-color`, `text-wrap: pretty` on headings and ledes, "…" and curly apostrophes |

## 5. Screen recommendations

### Unified résumé review (the representative screen)
- **Works:** progressive review while others read; the three-part summary; the disclosure hiding the editor; honest "Waiting / Reading".
- **Improve:** three equal boxed columns inside a boxed card, three times; every status the same; three filled buttons; internal notes text (§4.9).
- **Keep:** the flow, the banner, "Save and review next résumé", the editor's contents.
- **Simplify:** drop the inset boxes. *You / Roles / Skills* become three labelled, ruled blocks. Résumés not being edited collapse to one row.
- **Emphasise:** the open résumé and its single primary action; the status shapes.
- **De-emphasise:** "Adjust what Sweep looks for" stays a disclosure without a box. The "Worth knowing" callout is not shown verbatim: internal diagnostic notes are not a user-facing explanation (decision 10); replacement wording to be proposed for approval in this phase.
- **Weight editor:** a gap between skill name and chip; one neutral bar; a labelled "Remove" text button in place of the dashed square; fix the wrapped "Experience years" label.
- **Mobile:** résumés collapsed to rows, the open one expands in place.

### Upload and résumé management
- **Works:** the dropzone, the selected-files list, the reassurance copy, the rename/reorder model.
- **Improve:** the same instruction three times before the dropzone; the mark twice; the narrow left-anchored page; four outline buttons per résumé row.
- **Keep:** batch upload, limits, per-résumé controls.
- **Simplify:** one heading and one sentence. Move up/down, Rename and Remove become tertiary actions on each row; Review stays secondary.
- **Emphasise:** the dropzone; on the manage view, each résumé's status.
- **De-emphasise:** the three reassurance tiles become one quiet line.
- **Mobile:** the four-button row wraps unevenly today (`upload-existing-m.png`); use two consistent rows.

### Search configuration
- **Works:** defaults first, Advanced behind a disclosure, the side summary, the radio cards' plain explanations.
- **Improve:** every group is a panel and three nest when Advanced opens; field edges are invisible (A7).
- **Keep:** all controls and their order.
- **Simplify:** ruled groups instead of panels; selected radio gets a left rule.
- **Emphasise:** the side summary and its single primary action.
- **De-emphasise:** "Where Sweep searches" for a free sweep becomes a statement with one link.
- **Mobile:** the summary collapses to one line above the form.

### Plan / confirmation
- **Works:** the plain "what is about to happen" summary and the cost breakdown.
- **Improve:** a 56 px amber "$0.00" dominates a free search (§4.8); the action is ~1,050 px down on mobile; two boxes repeat "nothing is charged".
- **Keep:** the cost breakdown, cap handling, the over-cap moment.
- **Simplify:** free sweep: one line, "Free. Nothing is charged.", and the action. Paid: the cost numeral keeps its size and amber.
- **Emphasise:** the action and, when paid, the cap.
- **Mobile:** the action follows the summary directly; it is not pinned without visual approval (§0.9).

### Search progress
- **Works:** honest passes, no fake percentage, a determinate bar only when a fraction is true, the header run strip.
- **Improve (limited evidence, audit §3):** only the finished state was captured. The side stack of three explanatory panels repeats the page.
- **Keep:** all state logic and its honesty.
- **Emphasise:** the current pass and, when paid, the live cost.
- **De-emphasise:** "How jobs are ranked", "What to expect", "Where Sweep is searching" into one disclosure.
- **Note:** re-inspect the waiting and in-progress states before designing this screen.

### Results and filtering
- **Works:** the information model (All Jobs vs a résumé's view), "Best matches first", the table-to-card reflow, the honest note when no résumé clearly fits.
- **Improve:** recommendation buried (§4.1); switcher styled as buttons (§4.4); exports inside Filter and sort (§4.10); unlabelled mobile fields; file names wrapping; a three-line intro paragraph; a panel titled "Onsite and hybrid in India" with a long right-aligned caption under a separate "Filter and sort" bar.
- **Keep:** the table (this is data; it does not become large cards), the order, the notes, Apply.
- **Structure:** tab row for views; one line with count, filters and "Export…" (four formats, none pre-emphasised); then ruled rows with no surrounding panel. The scoring explanation moves to one sentence plus a "How scoring works" disclosure.
- **Desktop row:** match figure (right-aligned, at least 20 px) | role and company on one line | recommendation line | location | skills | Apply (underlined, 24 px minimum height). Pay and experience columns are omitted when no row in the view has a value; otherwise a value or `—`. Source is plain text.
- **Recommendation line** *(amended, decisions 4 and 5)*. The engine's existing wording is kept, in
  its five states, as the current screen shows them. The layout changes (a fixed line
  under the role, a consistent résumé reference, a `!` shape for the caution); the
  sentences do not. Résumé references become editable names, with the file name secondary
  where there is room:
  - clear: `Suggested résumé: <name>.`
  - close: `Suggested résumé: <name>. <other> is close behind.`
  - split: `<name> covers more of this posting. <other> is also suggested.`
  - tie: `<a>, <b> and <c> fit equally.`
  - caution: a separate quieter line beneath, `Note: …`
  Names wrap at word boundaries or truncate in the middle, never mid-word.
- **Mobile row (390 px):** line 1: score (28 px) | role and company. Line 2: the recommendation. Line 3: location, then pay and experience **only when present**, each with its word ("Pay ₹18–24 LPA · 3–5 yrs"). Line 4: first three skills. Line 5: Apply as a 44 px target. The card border stays; the border on the surrounding panel goes.
- **Validation needed before step 8:** a static mock at 390 px with realistic pay and experience values, including all five recommendation states, because the synthetic audit data had none.

### System states
Branded 404 and error pages inside the shell; one empty-state pattern; quota and validation messages keep the left-rule banner and gain a fix in the sentence; internal notes are not shown as explanation and their replacement wording is reviewed (§0.10).

## 6. Design anti-goals (how this proposal respects them)

| Anti-goal | How |
|---|---|
| Purple-gradient AI dashboard | Existing teal-black and parchment palette; no gradients |
| Glassmorphism | No blur or transparency |
| Brutalism without justification | Hairlines and tabular figures exist for scanning, not attitude |
| Huge cards | Fewer boxes, not bigger ones; Results stay a table |
| Animation showcase | No new motion |
| Landing page as app | Upload keeps one H1 and one instruction |
| Information-poor | Nothing is removed; absent fields are compacted, not deleted |
| Dribbble recreation | Derived from measured findings |
| Blind Stitch regeneration | Stitch is not used |
| **Replacing one trend with another** | Graphite-plus-one-accent was the first draft's proposal and was rejected for exactly this reason (§7) |

## 7. Independent critique

A separate reviewer (a fresh subagent with no part in writing the audit, told to be
adversarial, using `design-taste-frontend-v1` and `minimalist-ui` as lenses and checking
claims against the CSS and screenshots) reviewed the first draft. I verified its checkable
claims before acting on them.

**Confirmed and changed.**
- *Distinctiveness.* The first draft moved to graphite, cool greys, Geist and one amber accent, which is the current default dark-tool look. Sweep's warm-on-teal palette and Bricolage are its own. **Reverted:** palette kept, Bricolage kept at h1, h2 and figures.
- *Amber as primary would remove a safety cue.* Amber marks money; making it the button fill would make a free and a paid start look alike. **Reversed:** amber stays cost-only and leaves everything else (§4.2).
- *Surface tiers would not read.* The proposed fills differed by 1.08:1 and 1.09:1, worse than today's 1.13:1. **Changed:** hierarchy is rules, type and a left rule, not fill.
- *Score demoted.* The draft shrank the score to 18 px while saying to emphasise it. **Fixed:** at least 20 px, right-aligned.
- *Positional number tokens* are unstable under reorder and add a fourth identifier. **Dropped.** *(Amended by §0.4: the identity is the editable name, with the file name secondary.)*
- *Unicode status glyphs* clash with fonts and with the row bullet. **Replaced:** the shapes the app already draws, bullet removed.
- *80 rem measure* would narrow the densest screen, and moving the card breakpoint would create a scrolling band. **Reverted:** 88 rem, breakpoints unchanged.
- *"CSS-only token remap"* was wrong. **Corrected** in §8.
- *Mobile Results and the five recommendation states* were under-specified. **Specified** in §5.
- *Audit errors:* "every hex appears once" was false (one `#fff`, four `rgba()`), and the score-alignment claim was overstated. **Corrected** in the audit.

**Not accepted.**
- "Quiet ledger is only a label." It is a label, but §2 now ties it to specific devices (ruled rows, right-aligned figure columns, rank numerals, tabular figures) that exist in the product's own data. Whether that is *enough* distinctiveness is a judgement; it was decision D1 and the owner approved it to prototype (§0.1).
- Dropping `text-wrap: pretty` and the reading-column claim as unmotivated: the column claim was removed (body already has `max-width: 68ch`); `text-wrap` stays because it answers a guideline gap (audit §5).

**Real trade-offs that remain.**
- Body 13 to 14 px and labels 10 to 12 px make non-table screens taller. Removing boxes should offset it, but that is unverified until the review screen is built.
- Keeping the teal ground means the redesign looks *evolved* rather than *new*. That is the intent, but it will be less dramatic than an owner may expect.
- Reserving amber for cost makes the tracker and focus neutral, which loses a little warmth and "where you are" salience.
- A list view with no primary action and a text-link Apply is deliberate but unusual; it may test as too quiet.
- The status shapes reuse an existing vocabulary, which is cheaper to learn but less expressive.

## 8. Implementation strategy

**Branch policy (decision 12).** All work is on `design/sweep-ui-overhaul`, branched from
`origin/main` at `fdb0da0`. It already carries two commits: this audit and direction
(phase D1) and the accessibility foundation (phase D2, step 0 below). Each phase is its own
commit, in this order:

1. Accessibility foundation *(done)*
2. Shared visual rules
3. Unified Review
4. Upload and résumé management
5. Configure and Confirm
6. Search Progress
7. Results and filtering
8. Secondary screens
9. Responsive and accessibility polish

Nothing on the branch is merged to main or deployed to Render until the whole redesign
passes final review; Oracle and Modal are not touched. After each phase: focused
regression results, real desktop and mobile screenshots, a before/after comparison (the
D1 screenshots are kept unchanged as the "before"), an independent visual critique, the
commit SHA and the remaining problems, then a stop for owner approval. The full
regression suite is for the release candidate.

The table below is the original step list; step 0 is complete.

| # | Step | Risk class | Notes |
|---|---|---|---|
| 0 | Accessibility fixes from §4.5 | small CSS and one template line | **Done** (`c131a8e` on the audit branch, `51a121d` here). Not shipped alone: it travels with the overhaul |
| 1 | Approve direction and §9 decisions | none | |
| 2 | **Rule audit and shared component rules** (not a token remap) | CSS only, but visible on every screen | The explicit list of rule changes is below |
| 3 | Redesign unified review as the representative screen, **plus a static Results row and mobile card mock** | template and CSS | Review tests forms, status and disclosure but has no dense data. The Results mock tests the same rules against the hard case before they freeze |
| 4 | Review real desktop and mobile screenshots | none | |
| 5 | Refine the system | CSS | |
| 6 | Upload and Configure | template and CSS | |
| 7 | Search progress | template and CSS | Re-inspect in-progress states first |
| 8 | Results and filtering | template and CSS, **highest regression risk** | Row restructure, tabs, export move |
| 9 | Secondary screens and system states | template and CSS | The key screen is operator-facing in local mode |
| 10 | Visual, accessibility and functional regression | | Both public and local mode, one résumé and three |
| 11 | Deploy | | |

**Step 2 is a list of rule changes, because meaning is encoded in names.** `--paid` and
`--free` are used about 60 times in `sweep.css` and once in `_mark.html`, so retuning values
does not move a meaning. The changes are: amber out of focus (line 789), selected choice
(425), checkbox accent (411), weight bars (901), stepper and drop hover (1034, 1479),
tracker current step (153) and run dot (692); links off teal (61); the hard-coded `#fff`
primary hover (435); the four hard-coded `rgba()` values (103, 236, 458, 491); `--dim` off
text (`.weights .rank`, `.stages li.next .meta`); the control border; the `.listings`
hooks if row markup changes.

**Constraints found in the code.**
- Tests pin markup and CSS. `test_app.py` has about 20 references to `sweep.css` and asserts `<div class="listings">` and the `.listings` rules; the multi-résumé tests match `data-card`, `aria-labelledby="resume-N"`, `id="resumes-banner"` and `<b>Job N</b>`; `test_app.py` also pins the `paid` and `free` cell classes on the cost table. Template changes keep these hooks or change the tests in the same step, deliberately.
- `test_public_copy.py` asserts rendered public copy. Edits to Upload headings and "Worth knowing" go through it.
- The local operator console shares these templates and this stylesheet. Because the palette is kept, it inherits the same rules; each step is checked in both modes.
- Single-résumé behaviour is a P0 guard; every step is checked with one résumé as well as three.

Low-risk, CSS only: 0 (mostly), 2, 5. Needs UX and regression attention: 3, 8 (row markup, tabs, export move), and any pinned mobile action bar (§0.9).

## 9. Decisions

Status as of 2026-09-30. Decided items are recorded in §0.

| # | Decision | Status |
|---|---|---|
| D1 | Quiet Ledger as a tightening rather than a reskin | **Approved** to prototype (§0.1) |
| D2 | Dark only | **Decided** (§0.7) |
| D3 | Colour reserved for meaning | **Decided**: amber for monetary information and the brand mark (§0.3) |
| D4 | "Worth knowing" and internal notes | Principle **decided** (§0.10). Replacement wording **open**; needs a check of what the production model path emits (the audit saw only the local path) |
| D5 | Résumé identity | **Decided, amended**: editable name primary, file name secondary (§0.4). Default value of the editable name **open** |
| D6 | Exports out of "Filter and sort" | **Decided** (§0.8). Exact placement to be shown in the Results phase |
| D7 | Accessibility fixes first | **Done** as a separate commit; released only with the overhaul (§0.12) |
| D8 | Mobile pinned action bar | **Decided**: not without visual approval (§0.9) |
| D9 | Public and local operator modes | **Decided**: both (§0.11) |
| D10 | Results list with no primary button and an underlined Apply | **Open.** To be tested in the static Results prototype |
