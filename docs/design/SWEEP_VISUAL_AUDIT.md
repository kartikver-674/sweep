# Sweep visual audit (Phase D1)

Audit only. No application code, template, stylesheet or test was changed.
Baseline: `origin/main` at `fdb0da0` (2026-09-30). Everything below was observed in a
running copy of the app or read from source at that commit, and each claim says which.

## 1. How this audit was done

**Method.** The real Render public app (`sweep/app.py`, public mode, multi-résumé on) was
served over HTTP on loopback by a scratch harness kept outside the repo. The harness reuses
the test suite's sealed environment: synthetic personas, model calls stubbed, sockets
restricted to loopback, the real worker app behind it. Six session states were prepared
(fresh, three uploaded, one read, all read, configured and confirmed, run finished with
synthetic engine-shaped rows) and driven with headless Chromium at 1440x900 and 390x844.
Measurements (contrast, target size, font sizes, nesting) were taken from the live DOM.
No production account, real key, model call or paid search was used.

**Evidence.** About 45 screenshots are in `output/design-audit/` (git-ignored, local only,
synthetic data only). They are named `<screen>-d.png` (desktop) and `<screen>-m.png`
(mobile). This document cites them by name.

**Skills actually used, and why.**

| Skill | Used for | Note |
|---|---|---|
| `web-design-guidelines` | Live rules fetched from the Vercel guidelines repo and applied to templates and CSS | Its rules are React-flavoured; only the HTML/CSS-relevant ones were applied |
| `redesign-existing-projects` | The audit checklist (typography, colour, layout, states, content, components, omissions) | Its "upgrade techniques" section was ignored: parallax, grain, spring physics do not fit this product |
| `design-taste-frontend-v1` | Anti-slop lens and the three dials | Its default dials (variance 8, motion 6, density 4) are wrong for a data workspace. Used at variance 2, motion 2, density 7 |
| `minimalist-ui` | Cross-check on flat surfaces and restrained colour | Not adopted wholesale (see the direction document) |
| `high-end-visual-design` | Read, then set aside | Its rules (double-bezel cards, pill buttons, glass nav, `py-24` sections, scroll-blur reveals) contradict the anti-goals and a dense workspace |
| `brandkit` | Read for its framing questions only | It is an image-generation skill. Nothing was generated |
| `webapp-testing` | Its Playwright approach | Its `with_server.py` could not start the harness, so a small script was used |

Not used: `gpt-taste` (landing-page and GSAP oriented), the image/Stitch skills (out of
scope for D1), `design-taste-frontend` v2 (87 KB, marked experimental, not read). "Awesome
design" is not installed. The untracked `DESIGN.md` in the repo root is an analysis of
Claude's own marketing site, not of Sweep, and was neither committed nor used as a basis.

## 2. Frontend architecture

| Aspect | What exists |
|---|---|
| Stack | Flask + Jinja templates, one hand-written stylesheet, vendored Alpine 3.14.1, three small scripts (`motion.js`, `pick.js`, `reading.js`). No build step, no Tailwind, no icon library |
| Templates | `base.html` (shell, header, step tracker, feedback dialog, run strip) plus 12 screens and 7 partials. `running.html` (793 lines) and `configure.html` (675) are the largest |
| CSS | `sweep/static/sweep.css`, 1,883 lines, no preprocessor |
| Tokens | 15 hex colour custom properties plus `--rule` (an `rgba`), a 7-step spacing scale (`--s1`..`--s7`, 2 to 32 px), one radius (`--radius: 4px`), two font stacks. Each of the 15 hex values appears once, as a token. A few values escape the tokens: one hard-coded `#fff` (primary hover, line 435) and four `rgba()` values (lines 103, 236, 458, 491) |
| Type | Geist (UI) and Bricolage Grotesque (display) from Google Fonts, system fallbacks. Base 13 px |
| Type scale | 19 distinct `font-size` values in CSS (9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 24, 26, 28, 30, 32, 34, 44, 56 px) |
| Radii | 43 uses: 28 of `var(--radius)`, 7 circles, and stragglers at 2, 3 and 4 px |
| Breakpoints | 30, 40, 48, 60 and 64 rem, plus `(pointer: coarse)` and `prefers-reduced-motion` |
| Icons | None as a library. One inline SVG per use (feedback bubble, file glyph, mark), tick and triangle drawn in CSS |
| Loading | Indeterminate 4 px bar, a pulsing dot, "bone" placeholders that do not shimmer by design. All CSS |
| Inline styles | 38 `style=` attributes across templates, 26 of them in `running.html` |
| Stitch remnants | The stylesheet header calls itself "the v3 Stitch design system, ported to plain CSS" and cites `docs/stitch-ui-prompt.md`. The palette, the 10 px uppercase label, the 4 px radius and the meter are Stitch v3 outputs |

**Is this a design system or individually styled screens?** A token layer plus a coherent
component vocabulary (`.panel`, `.inset`, `.tile`, `.tag`, `.choice`, `.primary/.secondary`,
`.banner`, `.callout`, `.label/.meta`) does exist, and the discipline in it is better than
most hand-built apps. What is missing is the layer above it: there are no rules for
*when* to use a panel, which colour means what, or how screens share a width. The result is
consistent parts assembled into screens that differ in width, density and emphasis. It reads
as one system built in phases, with the seams visible.

## 3. Screen inventory

| Screen | Route | States inspected | Not reachable or not captured |
|---|---|---|---|
| Upload | `/` | empty; two files selected; wrong file type; submit with nothing (validation error); three résumés already added (this is the résumé-management view: rename, reorder, include/exclude, remove) | drag-over |
| Unified review | `/review` | waiting (one résumé still queued); reading; ready to review; one résumé expanded to its editor; all read; single-résumé variant | a failed read, a rate-limited read, "reviewed" ticks after saving |
| Configure | `/configure` | defaults; Advanced settings expanded | paid-source variant (key attached) |
| Confirm | `/confirm` | free sweep, $0.00 | paid cost and capacity states, over-cap state |
| Search progress | `/running` | finished state only | **waiting and in-progress states.** The stub worker finishes instantly, so only the completed page was captured. The "All 0 of them" text on it is an artefact of that stub, not a product defect |
| Results | `/results` | All Jobs; per-résumé view; Filter and sort expanded; keyboard focus; feedback dialog | applied and opened row states, empty results, paid rows |
| System | | validation error, feedback dialog, 404 | quota/429 messages, plan error, server error |

## 4. Findings

Ordered by user impact first, then by effect on the visual system. Each names where it
occurs, the problem, why it matters, and the principle that fixes it. Files named are
screenshots in `output/design-audit/`.

### 4.1 High: results are hard to scan, and the résumé recommendation is buried

- **Where.** `/results`, `results-d.png`, `results-m.png`, `results-filter-d.png`. Source: `results.html` and `.listings` in `sweep.css`.
- **Problem.** The recommendation (which résumé to send) is the one thing a multi-résumé
  user cannot get elsewhere, yet it is an 11 px muted line under the company name, the same
  weight and colour as the "Note:" caveat beneath it. On desktop the row's widest column
  (Role) carries three stacked lines while Pay and Experience read "Not stated" on every
  row. On mobile those two "Not stated" strings sit unlabelled beside the location, so a
  reader cannot tell which is pay and which is experience.
- **States.** The recommendation is not one thing. `results-d.png` shows five: clear
  ("Suggested résumé: ada-cv.pdf"), close ("bhaskar-cv.pdf. ada-cv.pdf is close behind."),
  split ("bhaskar-cv.pdf covers more of this posting. chen-cv.pdf is also suggested."), tie
  ("ada-cv.pdf, bhaskar-cv.pdf and chen-cv.pdf fit equally.") and a separate "Note:" caveat.
  Any redesign has to carry all five.
- **Why it matters.** Sweep's differentiator is being read as an afterthought, and scanning
  for it means reading every sentence.
- **Principle.** The decision, not the metadata, gets the emphasis. Give the suggested résumé a fixed
  position and a compact, consistent form; collapse absent fields.

### 4.2 High: three résumé identities compete, and filenames are poor labels

- **Where.** Upload manage view, Review cards, Results switcher and rows.
- **Problem.** A résumé is "Résumé 1", "Default.pdf", a user-editable name ("Backend
  Engineer") and, on Results, the file name again ("ada-cv.pdf"). The recommendation
  sentences embed the file name mid-sentence, and at 390 px it wraps mid-name
  ("ada-\ncv.pdf", `results-m.png`). File names were chosen deliberately (commits `62b7174`,
  `fdb0da0`), so the fix is presentation, not renaming.
- **Principle.** One stable identity token per résumé (its number) that appears identically on every screen, with the file name as secondary text that truncates in the middle.

### 4.3 High: accent colours carry too many meanings

- **Where.** Whole app. Source: `sweep.css`.
- **Problem.** The stylesheet header promises amber means "paid" and "you are here" only.
  In fact amber is also the focus ring (line 789), the checked-radio border and title
  (425), the checkbox accent (411), the weight bars (901), stepper hover (1034), drop-zone
  hover (1479), the running pulse and the "affects cost" marks. Teal means "free", but is
  also the link colour (61), the success banner, the Source column on every result row
  (`tr.free td`), and the tick list. Source names in teal read as links, and "Apply", the actual link,
  is teal too.
- **Why it matters.** A colour that always means something is a signal. One that means
  nine things is decoration, and the money semantics, which is the reason for the
  restraint, are no longer readable at a glance.
- **Principle.** Spend colour on one job each: one brand/primary accent, status colours only for status.

### 4.4 High: several competing primary buttons; navigation styled as actions

- **Where.** `review-allread-d.png`: Résumé 2 and 3 each carry a filled "Review" primary next to the open card's filled "Save and review next résumé". `results-d.png`: the résumé switcher uses `.primary` for the current view and `.secondary` for the rest.
- **Problem.** Three filled buttons on one screen have no order of importance. The results switcher is a `<nav>` of links that look identical to submit buttons, so "which view am I in" and "what should I click" use the same visual signal. The primary fill (`#d2e6ee`, pale blue-grey) also reads as neutral rather than as *the* action.
- **Principle.** One primary per view. Navigation state is a tab or selected state, never a button fill.

### 4.5 Medium: the system boxes everything

- **Where.** Every screen. Measured: 10 to 15 bordered, filled boxes per screen and up to 3 nested (card, inset, tag) on Review. `review-allread-d.png`: a résumé card contains three inset cards and a callout; `configure-advanced-d.png`: panel, disclosure, sub-panel.
- **Problem.** Every unit of content is a bordered panel with an H2, so hierarchy is expressed by
  *containment* rather than by type and spacing. The nesting is the clearest "generated
  UI" signature here. It also spends width: at 1440 px the Review card's three columns are
  ~430 px each and mostly empty.
- **Principle.** Boxes only where a boundary changes meaning (a résumé, a dialog, a cost total); everywhere else use rules and space.

### 4.6 Medium: screens do not share a grid

- **Where.** `upload-empty-d.png` vs `review-allread-d.png`.
- **Problem.** Upload content stops at x=1224 (`.front { max-width: 74rem }`, left-anchored
  inside a centred 88 rem `main`), leaving a 216 px void on the right; Review, Configure and
  Results run to x=1400. The header brand is at 16 px, page content at 40 px. Switching
  step-to-step visibly jumps.
- **Principle.** One content measure, with a narrower reading column inside it where text needs it.

### 4.7 Medium: type is very small and over-uppercased

- **Where.** Measured on live text nodes. Review (desktop): 44% of text nodes are 11 px or
  smaller. Results (desktop): 76% are 12 px or smaller, 40% are 11 px or smaller. The 10 px
  uppercase letter-spaced label (`.label`, `.meta`, column heads, `dt`) appears 4 to 15 times per screen.
- **Problem.** 10 to 11 px uppercase muted text carries real content (group names, "Suggested résumé", "Ready to review"). Body is 13 px, helper text 11 to 12 px, and there are 19 sizes in CSS. The hierarchy is made by
  shrinking the small end rather than by strengthening the large end. See §5 for what is
  a genuine accessibility problem versus taste.
- **Principle.** A short type scale with a floor of 12 px, sentence case for labels, weight and colour for hierarchy.

### 4.8 Medium: emphasis lands on the wrong number

- **Where.** `confirm-d.png`, `confirm-m.png`.
- **Problem.** On a free sweep the largest, brightest thing on the page is "$0.00" in 56 px amber inside its own
  well. On mobile the page's only action, "Start Free Sweep", is ~1,050 px down, below four boxes.
  Two of those boxes (Cost breakdown's empty dashed state, and a sentence repeating "nothing is charged") say the same thing the numeral already said.
- **Principle.** Emphasise the decision. Show a zero as calm, not as a headline.

### 4.9 Medium: internal text reaches users

- **Where.** `review-allread-d.png` ("Worth knowing"). Source: `review.html:127-128` and `:273-277` print `derived.notes` verbatim.
- **Problem.** The note observed reads "years_experience COMPUTED from the extracted employment dates … title_exclude are empty on purpose — see auto-apply/local_profile.py". It is produced by `local_profile._notes`,
  the local derivation path used in this harness. The production model path was stubbed, so what real users
  see there is **not verified**. The template will print whatever is in `notes`.
- **Why it matters.** File paths and field names in a user-facing callout break trust in a product that sells clarity.
- **Principle.** User-facing surfaces show user-facing language; a separate, quieter place for diagnostics.

### 4.10 Medium: exports are hidden in an unrelated disclosure

- **Where.** `results-filter-d.png`. Export (Excel, CSV, JSON, Web page) sits inside "Filter and sort", and the Excel button is the only filled button in the panel.
- **Problem.** Someone who wants the file must open a disclosure named for something else, and Excel is
  privileged over the other three formats for no stated reason.
- **Principle.** Put a control where its name would be looked for.

### 4.11 Low to medium: local defects in otherwise good components

- **Weight editor** (`review-editor-d.png`). Importance chips sit flush against the skill name ("celery[Used at work]", no gap), 8 rows repeat the same amber bar, and the remove control is a dashed square that looks like an empty slot rather than a delete. "EXPERIENCE / YEARS" wraps to two lines and misaligns with "MONTHS".
- **Score column** (`results-d.png`). Scores are left-aligned, so a column of 30, 25, 20, 18, 10 lines up only because every value has two digits; the negative and any single-digit score sit off the ones digit (the -3 is pushed left). Right-aligned tabular figures would fix it. Whether Bricolage has tabular figures was not checked.
- **Status text.** Every card says "Ready to review" in the same 11 px grey top-right, whether it is open, waiting or done. State is a word, not a shape.
- **Repeated brand.** The mark appears in the header and again at 56 px in the upload hero beside the H1.
- **Redundant headings** (`upload-empty-d.png`). "Find jobs that match your résumé" (H1), "Start with your résumé" (H2 plus sentence), "Add up to 3 résumés" (H2 plus sentence) say the same instruction three times before the dropzone.
- **Feedback dialog** (`feedback-d.png`) and 404 (`404-d.png`). The 404 is the browser/Werkzeug default: white page, serif, no navigation, inside a dark product. (Behaviour for other error codes was not observed.)

## 5. Accessibility (WCAG 2.2 AA) and interface guidelines

Separated from taste. "Observed" means measured in the browser; "computed" means calculated
from the CSS and not seen on screen.

### Genuine issues

| # | Issue | Evidence | Criterion |
|---|---|---|---|
| A1 | Rank numerals in the weight editor use `--dim`: 1.75:1 on the panel, 2.06:1 on the well | Observed, `review-*`: 9 nodes at 1.83:1 | 1.4.3 Contrast (Minimum) |
| A2 | Applied and opened result rows drop to `opacity: .45` / `.62`. Body text becomes 3.65:1, muted text 2.1:1, links 3.06:1 at .45 | Computed from `sweep.css:500-512` and the token values. Not observed, because the state was not created | 1.4.3 |
| A3 | The arrival feed dims entries to `opacity: .35` (2.3:1) and below | Computed from `sweep.css:1176-1182` | 1.4.3 |
| A4 | No skip link. Every page repeats the header, tracker and run strip before content | Observed: none of 7 pages has one | 2.4.1 Bypass Blocks |
| A5 | Small targets on a fine pointer: "Apply" 31x16, "Manage your résumés" 131x18, summary rows 18 px tall | Observed. On a coarse pointer the app raises these to 44 px (`sweep.css:1853-1874`), which is good, but a small laptop trackpad user gets 16 px | 2.5.8 Target Size (Minimum) |
| A6 | Status carried by colour and position alone in places: source name teal vs muted, résumé state as a grey word, weight bar colour | Observed | 1.4.1 Use of Color (partly mitigated by text) |
| A7 | Text-field, select and radio-card boundaries are almost invisible: border `#25373e` is 1.32:1 against the panel and the recessed fill 1.18:1. The dropzone's dashed edge is 2.06:1. Fields are findable by their label and by position, not by their edge | Computed from tokens (`--rule`, `--well`, `--surface`, `--dim`); consistent with the screenshots, where fields read as dark slots | 1.4.11 Non-text Contrast (3:1 for the boundary that identifies a control) |

### Guidelines gaps (lower severity)

`color-scheme: dark` is not set, so native select menus, scrollbars and form controls render with light defaults on a dark page. There is no `theme-color` meta. There is no `text-wrap: balance` or `pretty`, so headings orphan. Placeholders and the feedback textarea use "..." rather than "…", and copy uses straight apostrophes ("Here's", "doesn't"). Sentence case is used throughout, which is a deliberate and better choice for this product than the guideline's Title Case; keep it.

### Verified good

Visible, high-contrast focus ring (amber 2 px, `focus-visible`, seen on the results switcher in `focus-results-d.png`). `aria-current` on the tracker and results switcher. Every form control has a label. Landmarks (`header`, `nav`, `main`) and a real H1 on every page. `lang` set. `prefers-reduced-motion` honoured globally. Tabular numerals. No horizontal overflow on any of 12 screens at 390 px (measured: `scrollWidth - innerWidth = 0`). 44 px targets on touch. `role="status"` and `role="alert"` on 11 live regions. Tables reflow into cards on mobile from the same DOM. No `transition: all`, no `outline: none`.

## 6. What makes it feel AI-generated

The candidate list from the brief, checked against Sweep. The honest result: **Sweep avoids
most of the loud tells**, and the feeling comes from a quieter set.

| Candidate | Present? |
|---|---|
| Purple/generic SaaS gradients, glass, heavy shadows | **No.** No gradients, no shadows, no blur |
| Excessive rounded cards | **No.** Radius is a flat 4 px. Cards are square-ish |
| Cards inside cards | **Yes**, see 4.5 |
| Inconsistent radii | Minor (2, 3, 4 px stragglers) |
| Decorative icons | **No.** Almost none. This is a strength |
| Pills and badges | Some: `.tag` chips carry many things (roles, skills, sources, importance) with one shape |
| Weak type hierarchy | **Yes**, see 4.7. Everything is 11 to 13 px with uppercase micro-labels |
| Muted-grey overuse | **Yes.** `--slate` and `--warm` carry most secondary content, and `--dim` leaks into text |
| Too many accents | **Yes**, see 4.3 (amber and teal each overloaded) |
| Generic AI copy | Mostly plain and specific. Exceptions: "Worth knowing", the triple restatement on Upload, "Sweep searches, scores and ranks every job it found" |
| Excess whitespace | **No.** If anything the opposite on results |
| Mobile as compressed desktop | **Partly.** Tables become cards well, but Review and Confirm stack every desktop box in full |
| Unnecessarily elaborate loading | **No.** Restrained and honest (indeterminate bars, "not known" instead of $0.00) |
| Poorly distinguished interactive vs not | **Yes**, see 4.4 (tab-as-button, teal source text vs teal links) |

The dominant tell is **uniform treatment**: every block is a titled panel, every label is
10 px uppercase, every secondary line is slate, every button pair is filled plus outlined. The default Stitch dark-teal ground and pale
primary button add to the "template" feel because they carry no brand decision beyond
the amber mark.

## 7. Existing strengths to preserve

1. **Token discipline.** The 15 hex colours each exist once, as tokens (five stray literals aside, §2). The radius, spacing scale and type faces are shared. This makes a re-theme *possible*, but not merely a value swap: several tokens are named for what they mean (`--paid`, `--free`, about 60 uses), so changing what a colour means is a rule change at each use.
2. **Honesty in states.** No fake progress, "not known" instead of a fabricated $0.00, indeterminate bars where there is nothing to measure, and skeletons that do not pretend rows are coming.
3. **Money legibility.** The idea of one always-present meter and one estimate is sound. The problem is how much colour it borrows, not the concept.
4. **Flat, ornament-free surfaces**: 4 px radius, hairline borders, no shadow, gradient or glass.
5. **The amber mark and wordmark**, and Bricolage Grotesque for page titles, are ownable.
6. **Plain-language copy** in most places, sentence case, active voice.
7. **Responsive craft**: same-DOM table-to-card reflow, coarse-pointer target sizes, `contain: paint` overflow control, tracker collapse.
8. **Accessibility foundations**: focus ring, labels, landmarks, live regions, reduced motion.
9. **The workflow itself**: the tracker, progressive review, the results switcher's information model (All Jobs vs a résumé's view). These are frozen and should stay.

## 8. Prioritised problem list

| Priority | Item | Basis |
|---|---|---|
| P1 | Results: recommendation prominence, unlabelled mobile fields, résumé identity (4.1, 4.2) | Highest user impact, the product's differentiator |
| P1 | Colour semantics and primary-button rules (4.3, 4.4) | Affects every screen and every later decision |
| P1 | A1 to A4 and A7 (rank contrast, dimmed rows, skip link, control boundaries) | Genuine AA failures |
| P2 | Boxing and nesting (4.5), shared grid (4.6), type floor and scale (4.7) | Largest visual-system effect |
| P2 | Confirm emphasis (4.8), notes copy (4.9), exports placement (4.10) | Clear, local, cheap |
| P3 | Weight editor details, score alignment, status shapes, 404, `color-scheme`, punctuation (4.11, §5) | Polish |

## 9. Limitations

Search progress was observed only in its finished state. Applied and opened row treatments,
quota and error messages, paid-key states and the model-produced "notes" text were not
observed and are marked above as computed or unverified. The fonts loaded from Google in the
audit browser, so screenshots show Bricolage Grotesque and Geist; a blocked font request
would fall back to system fonts. Contrast figures for observed text are computed by the
harness from resolved colours and opacity, not by an external tool.
