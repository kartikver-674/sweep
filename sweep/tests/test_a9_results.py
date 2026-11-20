"""A9: Results, in Direction A (public only).

One sticker card per job, "Why it matched" (a peek holding every matched skill), the score explainer as a peek with a small picture,
"Top of the pile", sticker tabs, tools and sections. The recommendation, raw scores, All Jobs, the exports, the Apply link and the
row link are the ones HEAD drew, and the console renders byte-identical.

Two kinds of test. Those in `Unchanged` assert what HEAD (1aa1c30) said and drew; they were run against a `git archive` of HEAD with
this file copied in and pass there too, so "the same" is a comparison with the old tree and not with itself. The rest assert what A9
adds. The browser half is docs/design/sweep-a/harness/results-a.mjs.
"""
import html
import importlib.util
import pathlib
import re
import unittest

from sweep import app as app_module
from sweep.tests import test_results_ui as ui
from sweep.tests import test_multi_results_view as rv
from sweep.tests.test_motion import Quiet

setUpModule, tearDownModule = rv.setUpModule, rv.tearDownModule

ROOT = pathlib.Path(app_module.__file__).parent
REPO = ROOT.parent
CSS = (ROOT / "static" / "sweep-a.css").read_text(encoding="utf-8")
TEMPLATE = (ROOT / "templates" / "results.html").read_text(encoding="utf-8")
A9_START = CSS.rindex("/*", 0, CSS.index("==== A9: Results")) if "==== A9: Results" in CSS else len(CSS)       # (absent in the HEAD tree this file is also run against)
A10_AT = CSS.rindex("/*", 0, CSS.index("==== A10: the other states")) if "==== A10: the other states" in CSS else len(CSS)        # A10 is the section after it
A9 = re.sub(r"/\*.*?\*/", "", CSS[A9_START:A10_AT], flags=re.S)

row = ui.row
public_page = lambda rows, path="/results": ui.page(ui.legacy_app(rows, public=True), path)  # noqa: E731
console_page = lambda rows, path="/results": ui.page(ui.legacy_app(rows, public=False), path)  # noqa: E731

NINE = "python, django, flask, sql, redis, docker, aws, git, linux"
ROWS = [row(1, score="104", pay="INR 45–60 LPA", exp="8+", skills=NINE),
        row(2, score="62", skills=""),
        row(3, score="7", where="Berlin, Germany"),
        row(4, score="3", site="greenhouse", skills=" , ,")]


def h1(body):
    return re.search(r"<h1>(.*?)</h1>", body, re.S).group(1).strip()


def cards(body):
    """{n: the markup of job n's row}."""
    return {int(m.group(1)): m.group(0) for m in re.finditer(r"<tr\b(?:(?!</tr>).)*?<b>[^<]*? (\d)</b>.*?</tr>", body, re.S)}


def first_row(markup):
    return re.search(r"<tr x-data.*?</tr>", markup, re.S).group(0)


def sections(body):
    """[(heading, the section's markup)] in page order, the collapsed abroad one included."""
    out = []
    for m in re.finditer(r'<(section|details) class="jobs-section".*?</\1>', body, re.S):
        out.append((re.search(r"<h2>(.*?)</h2>", m.group(0)).group(1), m.group(0)))
    return out


class Unchanged(unittest.TestCase):
    """What HEAD said and drew, and A9 must still."""

    def test_the_one_resume_headlines(self):
        three = ROWS[:3]
        self.assertEqual(h1(public_page(three)), "3 jobs found")
        self.assertEqual(h1(public_page(three, "/results?min=50")), "2 of 3 jobs shown")
        self.assertEqual(h1(public_page(three, "/results?q=zzz")), "0 of 3 jobs shown")
        self.assertEqual(h1(public_page([])), "0 jobs found")
        self.assertEqual(h1(console_page(three)), "3 listings kept")

    def test_the_apply_link_and_the_score_cell_are_exactly_what_they_were(self):
        cell = cards(public_page(ROWS))[1]
        self.assertIn('<a class="apply" href="https://jobs.test/1" target="_blank" rel="noopener">Apply'
                      '<span class="visually-hidden"> to Senior Backend Engineer 1 at Company 1</span>'
                      '<span class="go" aria-hidden="true">→</span></a>', cell)
        self.assertIn('<td class="score" title="Match score 104 — how much of your résumé this job asks for">104</td>', cell)
        self.assertIn('class="rowlink" data-href="https://jobs.test/1"', cell)
        self.assertIn('<td class="src"><span class="mlabel">via </span>LinkedIn<span class="paid-word">Paid</span></td>', cell)
        self.assertIn('<td class="pay"><span class="mlabel">Pay </span>INR 45–60 LPA</td>', cell)
        self.assertIn('<td class="exp"><span class="mlabel">Experience </span>8+</td>', cell)
        self.assertIn('<td class="loc">Pune, India</td>', cell)
        self.assertIn('<span class="posted">', cell)

    def test_a_negative_score_is_the_number_and_the_floor_is_todays(self):
        self.assertNotIn(">-3</td>", public_page(ROWS[:2] + [row(5, score="-3")]))
        self.assertIn('>-3</td>', public_page(ROWS[:2] + [row(5, score="-3")], "/results?min=-10"))

    def test_the_row_without_a_safe_link_is_not_clickable(self):
        cell = cards(public_page([row(1, url="javascript:alert(1)")]))[1]
        self.assertNotIn("data-href", cell)
        self.assertIn('<span class="muted">No link</span>', cell)

    def test_the_exports_are_the_same_links_with_the_same_labels(self):
        body = public_page(ROWS[:3], "/results?min=50&sort=recent")
        self.assertEqual(re.findall(r'<a class="secondary" href="([^"]*)">([^<]*)</a>', body),
                         [("/export.xlsx?min=50&amp;sort=recent", "Excel"), ("/export.csv?min=50&amp;sort=recent", "CSV"),
                          ("/export.json?min=50&amp;sort=recent", "JSON"), ("/export.html?min=50&amp;sort=recent", "Web page")])
        self.assertEqual(re.findall(r'<span class="label">(Export[^<]*)</span>', body), ["Export 2 listings"])
        plain = public_page(ROWS[:3])
        self.assertEqual(re.findall(r'<a class="secondary" href="(/export[^"]*)">', plain),
                         ["/export.xlsx", "/export.csv", "/export.json", "/export.html"])

    def test_the_tools_and_their_words(self):
        body = public_page(ROWS[:3])
        self.assertIn('<p class="count">Sorted by Best match</p>', body)
        for word in ('aria-controls="tool-filter"', ">Filter and sort</button>", ">Export…</button>", ">Apply filters</button>",
                     'name="min"', 'name="source"', 'name="q"', 'name="sort"', "Minimum score", "Title or company"):
            self.assertIn(word, body)

    def test_the_explainer_keeps_its_class_summary_and_sentences(self):
        body = public_page(ROWS[:3])
        self.assertIn('<details class="notes how-scoring">\n      <summary>How match scores work</summary>', body)
        self.assertIn("Match score is how much of your résumé — skills and experience — a job actually asks for, so a higher score means more of what you have.",
                      " ".join(body.split()))
        self.assertIn("It is a raw score, not a percentage, and it can be negative.", " ".join(body.split()))

    def test_the_sections_their_notes_and_the_collapsed_abroad_one(self):
        got = sections(public_page(ROWS[:3]))
        self.assertEqual([h for h, _ in got], ["Onsite and hybrid in India", "Onsite abroad — needs a visa"])
        self.assertTrue(got[0][1].startswith('<section class="jobs-section">'))
        self.assertTrue(got[1][1].startswith('<details class="jobs-section">'))
        self.assertIn('<span class="meta head-note"><b>2 listings</b></span>', got[0][1])

    def test_the_row_click_script_and_its_exclusion_list_are_untouched(self):
        self.assertIn('if (e.target.closest("a, button, input, label, summary")) {', TEMPLATE)
        self.assertIn('document.querySelectorAll("tr[data-href]")', TEMPLATE)
        self.assertIn('window.open(row.dataset.href, "_blank", "noopener");', TEMPLATE)

    def test_there_is_no_tabindex_on_results_and_main_is_main(self):
        body = public_page(ROWS)
        main = body[body.index("<main>"):body.index("</main>")]
        self.assertNotIn("tabindex", main)
        self.assertIn('<a id="main-content"></a>', body)
        self.assertIn('class="skip-link"', body)


class Public(Quiet):
    """What A9 adds, on the one-résumé public page."""

    def setUp(self):
        self.body = public_page(ROWS)

    def test_the_eyebrow_sits_above_the_headline(self):
        self.assertEqual(self.body.count('<span class="eyebrow">Step 4 · your jobs</span>'), 1)
        self.assertLess(self.body.index("Step 4 · your jobs"), self.body.index("<h1>"))
        self.assertLess(self.body.index("<h1>"), self.body.index("How match scores work"))

    def test_the_root_carries_the_results_class_only_in_public_mode(self):
        self.assertIn('<div class="stack res-a">', self.body)
        self.assertIn('<div class="stack">', console_page(ROWS))
        self.assertNotIn("res-a", console_page(ROWS))

    def test_the_explainer_gains_an_aria_hidden_picture_with_two_words_and_no_numbers(self):
        pic = re.search(r'<div class="scale" aria-hidden="true">(.*?)</div>', self.body, re.S).group(1)
        self.assertIn('<span class="scale-l">below zero</span>', pic)
        self.assertIn('<span class="scale-r">more of your résumé</span>', pic)
        self.assertIn('<i class="scale-zero"></i>', pic)
        self.assertNotRegex(re.sub(r"<[^>]+>", " ", pic), r"\d")
        self.assertNotRegex(pic, r"%|threshold|band|good|bad|strong|weak")
        self.assertLess(self.body.index("It is a raw score"), self.body.index('class="scale"'))
        self.assertLess(self.body.index('class="scale"'), self.body.index("</details>", self.body.index('class="scale"')))

    def test_why_it_matched_holds_every_term_uncapped(self):
        cell = re.search(r'<td class="skills">(.*)</td>', cards(self.body)[1].replace("\n", " ")).group(1)
        why = re.search(r'<details class="why" @click\.stop><summary>Why it matched</summary><div class="why-body">(.*?)</div></details>', cell).group(1)
        self.assertIn('<span class="why-t">Your skills this job mentions</span>', why)
        self.assertEqual(re.findall(r'<span class="tag">([^<]*)</span>', why), NINE.split(", "))
        self.assertEqual(len(re.findall(r'<span class="tag">', why)), 9)
        self.assertNotIn("tag more", cell)
        self.assertNotIn("+3", cell)

    def test_no_terms_is_an_empty_cell_and_no_peek(self):
        got = cards(self.body)
        for n in (2, 4):                                  # an empty string; commas and blanks only
            with self.subTest(job=n):
                self.assertIn('<td class="skills"></td>', got[n])
                self.assertNotIn("details", got[n])
        self.assertEqual(self.body.count('<details class="why"'), 2)    # jobs 1 and 3

    def test_the_peek_stops_the_click_so_the_row_script_never_sees_it(self):
        for tag in re.findall(r'<details class="why"[^>]*>', self.body):
            self.assertIn("@click.stop", tag)
        self.assertEqual(self.body.count("@click.stop"), 2)
        self.assertNotIn("@click.stop", console_page(ROWS))

    def test_a_terms_text_is_escaped(self):
        body = public_page([row(1, skills="<b>x</b>, a&b")])
        self.assertIn('<span class="tag">&lt;b&gt;x&lt;/b&gt;</span><span class="tag">a&amp;b</span>', body)

    def test_the_recommendation_is_not_a_peek_and_the_peek_holds_only_skills(self):
        for why in re.findall(r'<details class="why".*?</details>', self.body, re.S):
            self.assertNotRegex(why, r"caution|suggest|Suggested|rname")
            self.assertEqual(set(re.findall(r'class="([^"]*)"', why)), {"why", "why-body", "why-t", "tag"})

    def test_no_score_band_anywhere(self):
        classes = set(" ".join(re.findall(r'class="([^"]*)"', self.body)).split())
        self.assertFalse(classes & {"hi", "mid", "lo", "neg", "band", "high", "low", "good", "bad", "positive", "negative"}, classes)
        self.assertNotRegex(TEMPLATE, r'class="[^"]*\{\{[^}]*score')            # no class is computed from a score
        self.assertNotRegex(A9, r"td\.score\.|\.score\.(hi|mid|lo|neg)|\.score\[")
        for score, n in (("104", 1), ("62", 2), ("7", 3), ("3", 4)):
            self.assertRegex(cards(self.body)[n], rf'<td class="score"[^>]*>{score}</td>')

    def test_top_of_the_pile_is_one_stamp_on_the_first_card_of_the_first_section_that_is_not_abroad(self):
        self.assertEqual(self.body.count("Top of the pile"), 1)
        got = sections(self.body)
        self.assertEqual(got[0][1].count("Top of the pile"), 1)
        first = first_row(got[0][1])
        self.assertIn('<td class="role"><span class="stamp">Top of the pile</span>', first)
        self.assertEqual(got[1][1].count("Top of the pile"), 0)

    def test_the_stamp_skips_abroad_even_when_abroad_ranks_first(self):
        rows = [row(1, score="90", where="Berlin, Germany"), row(2, score="40")]
        got = dict(sections(public_page(rows)))
        self.assertIn("Top of the pile", got["Onsite and hybrid in India"])
        self.assertNotIn("Top of the pile", got["Onsite abroad — needs a visa"])

    def test_nothing_is_stamped_when_the_only_section_is_abroad(self):
        self.assertNotIn("Top of the pile", public_page([row(1, where="Berlin, Germany")]))

    def test_the_stamp_is_on_the_best_match_sort_only(self):
        self.assertIn("Top of the pile", public_page(ROWS, "/results?sort=score"))
        for sort in ("recent", "experience"):
            with self.subTest(sort=sort):
                self.assertNotIn("Top of the pile", public_page(ROWS, f"/results?sort={sort}"))

    def test_the_stamp_goes_on_the_first_card_whatever_its_section(self):
        rows = [row(1, where="Remote — worldwide", score="30", remote_scope="worldwide"), row(2, score="20")]
        body = public_page(rows)
        got = sections(body)
        self.assertEqual(sum("Top of the pile" in s for _, s in got), 1)
        self.assertIn("Top of the pile", got[0][1])

    def test_the_tip_once_above_the_first_section_when_a_shown_card_has_skills(self):
        tip = '<aside class="tip" data-tip="results-why"'
        self.assertEqual(self.body.count(tip), 1)
        self.assertIn("Open “Why it matched” to see which of your skills a job mentions.", self.body)
        self.assertLess(self.body.index(tip), self.body.index('id="results-body"'))
        self.assertGreater(self.body.index(tip), self.body.index('class="bar"'))

    def test_no_tip_when_no_shown_card_has_skills(self):
        self.assertNotIn("results-why", public_page([row(1, skills=""), row(2, skills=", ,")]))

    def test_the_tip_is_about_the_cards_that_are_shown_not_the_ones_held_back(self):
        cap = app_module.SECTION_CAP
        rows = [row(i, score=str(500 - i), skills="") for i in range(1, cap + 2)] + [row(cap + 2, score="1", skills="python")]
        self.assertNotIn("results-why", public_page(rows))
        self.assertIn("results-why", public_page(rows, "/results?full=1"))

    def test_the_tip_is_not_on_an_empty_page(self):
        self.assertNotIn("results-why", public_page([]))

    def test_the_thead_and_the_aria_label_are_kept(self):
        self.assertIn('<table class="jobs" aria-label="Onsite and hybrid in India">', self.body)
        self.assertEqual(len(re.findall(r'<th scope="col"', sections(self.body)[0][1])), 8)         # Match, Job, Location, Pay, Experience, Source, Matched skills, Apply
        self.assertNotIn('class="did"', self.body)                             # the applied tick does not exist publicly

    def test_the_markup_the_console_has_none_of(self):
        body = console_page(ROWS)
        for needle in ("res-a", "eyebrow", 'class="why"', "why-body", "class=\"stamp\"", "class=\"scale\"", "results-why", "@click.stop", "Step 4", "Why it matched",
                       "Top of the pile", "below zero", "skin-a"):
            with self.subTest(needle=needle):
                self.assertNotIn(needle, body)


class MultiTrack(rv.Results):
    """Three résumés, All Jobs and a résumé's own view."""

    def setUp(self):
        super().setUp()
        self.ids = self.run_multi("ada", "bhaskar", "chen")
        self.serve()

    def test_the_headlines_are_what_they_were(self):
        self.assertEqual(h1(self.page()), "6 jobs found")
        self.assertEqual(h1(self.page(track=rv.A)), f"5 jobs evaluated for {rv.LA}")
        self.assertEqual(h1(self.page(track=rv.C)), f"4 jobs evaluated for {rv.LC}")
        self.assertEqual(h1(self.page(min=20)), "3 of 6 jobs shown")
        self.assertEqual(h1(self.page(q="zzzz")), "0 of 6 jobs shown")
        self.serve([rv.job(1, rv.A, {rv.A: 30, rv.B: 12}, [rv.A], "clear", "")])
        self.assertEqual(h1(self.page(track=rv.C)), f"0 jobs evaluated for {rv.LC}")

    def test_the_views_nav_is_as_it_was(self):
        body = self.page()
        self.assertEqual(self.views(body), [("All Jobs (6) — showing", True), (f"{rv.LA} (5)", False), (f"{rv.LB} (5)", False), (f"{rv.LC} (4)", False)])
        nav = re.search(r'<nav class="views" aria-label="Which jobs to show">(.*?)</nav>', body, re.S).group(1)
        self.assertEqual([html.unescape(h) for h in re.findall(r'href="([^"]*)"', nav)],
                         ["/results", f"/results?track={rv.A}", f"/results?track={rv.B}", f"/results?track={rv.C}"])
        self.assertEqual(nav.count('aria-current="page"'), 1)

    def test_the_recommendation_is_visible_in_order_and_outside_the_peek(self):
        rows = self.rows_of(self.page())
        self.assertEqual(self.said(rows[1]), [f"Suggested résumé: {rv.LA}."])
        self.assertEqual(self.said(rows[3])[0].split(":")[0], "Note")                     # the caution first
        self.assertEqual(len(self.said(rows[3])), 2)
        self.assertEqual(self.said(rows[4])[-1], f"{rv.LA}, {rv.LB} and {rv.LC} fit equally.")
        for n, markup in rows.items():
            with self.subTest(job=n):
                caution, suggest = markup.find('<p class="caution">'), markup.find('<p class="suggest">')
                self.assertGreater(suggest, 0)
                if caution >= 0:
                    self.assertLess(caution, suggest)
                for peek in re.findall(r'<details class="why".*?</details>', markup, re.S):
                    self.assertNotIn('class="caution"', peek)
                    self.assertNotIn('class="suggest"', peek)
                self.assertLess(markup.find('<p class="suggest">'), markup.find('<td class="skills">'))

    def test_a_row_s_peek_holds_the_terms_of_the_view_that_scored_it(self):
        for track, skills in ((None, None), (rv.A, "python, django"), (rv.B, "react, node.js")):
            body = self.page(track=track)
            for n, markup in self.rows_of(body).items():
                tags = re.findall(r'<span class="tag">([^<]*)</span>', markup)
                with self.subTest(track=track, job=n):
                    self.assertEqual(len(tags), len(set(tags)))
                    self.assertEqual(markup.count('<details class="why"'), 1)
                    if skills:
                        self.assertEqual(tags, skills.split(", "))

    def test_the_stamp_is_on_the_first_card_in_every_view(self):
        for track in (None, rv.A, rv.B, rv.C):
            with self.subTest(track=track):
                body = self.page(track=track)
                self.assertEqual(body.count("Top of the pile"), 1)
                first = first_row(sections(body)[0][1])
                self.assertIn("Top of the pile", first)
        self.assertNotIn("Top of the pile", self.page(sort="recent"))

    def test_the_export_links_say_all_jobs_and_carry_the_view_s_filters(self):
        body = self.page(track=rv.B, min=5)
        self.assertEqual(re.findall(r'<span class="label">(Export[^<]*)</span>', body), ["Export All Jobs: 5 listings"])
        self.assertEqual(re.findall(r'<a class="secondary" href="(/export[^"]*)">', body),
                         [f"/export.{f}?min=5" for f in ("xlsx", "csv", "json", "html")])


class TheConsoleIsUntouched(unittest.TestCase):
    """The console's /results, nine states, against the sha256 of what 1aa1c30 rendered (docs/design/sweep-a/harness/results-hash.py)."""

    HEAD = {
        "console /results (one sweep)": "ab68e2c34e674f08",
        "console /results merged": "624204c6e47aa37d",
        "console /results earlier sweeps": "7d5676d6b0c33b31",
        "console /results free-only": "164ea7d02fe6fb74",
        "console /results filtered to nothing": "890077ace50e4334",
        "console /results multi-track view": "ab68e2c34e674f08",
        "console /results sorted, minimum": "e521dbf0191b2434",
        "console /results capped section": "d4657baa3c6d4f72",
        "console /results show all": "53f0331a2821ab92",
    }

    def test_the_bytes_are_the_bytes_head_rendered(self):
        import os
        spec = importlib.util.spec_from_file_location("results_hash", REPO / "docs" / "design" / "sweep-a" / "harness" / "results-hash.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        keep = os.environ.get("SWEEP_PUBLIC_MODE")
        os.environ["SWEEP_PUBLIC_MODE"] = ""
        try:
            got = mod.states(str(REPO))
        finally:
            if keep is None:
                os.environ.pop("SWEEP_PUBLIC_MODE", None)
            else:
                os.environ["SWEEP_PUBLIC_MODE"] = keep
        self.assertEqual(got, self.HEAD)

    def test_the_shared_macro_s_new_branches_are_all_gated_on_public_mode(self):
        body = TEMPLATE[TEMPLATE.index("{% macro listings_table"):TEMPLATE.index("{% endmacro %}", TEMPLATE.index("{% macro listings_table"))]
        self.assertIn("top=false", body)
        self.assertIn("{%- if public_mode and top and loop.first %}", body)
        self.assertIn("{%- if public_mode %}\n          <td class=\"skills\">", body)
        i = TEMPLATE.index("Step 4 · your jobs")
        self.assertIn("{%- if public_mode %}", TEMPLATE[i - 60:i])
        self.assertIn('{% if public_mode %} res-a{% endif %}', TEMPLATE)


def parts(css):
    """Every selector part of every rule in `css` (comments already gone), at-rule preludes skipped."""
    out = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        sel = m.group(1).strip()
        if sel.startswith("@") or sel in ("from", "to"):
            sel = sel.split("{")[-1].strip()
            if sel.startswith("@"):
                continue
        out.extend(p.strip() for p in sel.split(",") if p.strip())
    return out


def enclosing(css, pos):
    stack, start = [], 0
    for i, ch in enumerate(css[:pos]):
        if ch == "{":
            stack.append(css[start:i].strip())
            start = i + 1
        elif ch == "}":
            stack.pop()
            start = i + 1
        elif ch == ";":
            start = i + 1
    return stack


class TheStylesheet(Quiet):
    def test_the_section_exists_and_is_the_last_one(self):
        self.assertIn("==== A9: Results", CSS)
        self.assertGreater(len(parts(A9)), 60)

    def test_every_selector_hangs_on_the_skin_and_the_results_root(self):
        for p in parts(A9):
            with self.subTest(selector=p):
                self.assertTrue(p.startswith(".skin-a .res-a"), p)

    def test_the_root_class_is_results_only_and_public_only(self):
        found = [p.name for p in (ROOT / "templates").glob("*.html") if "res-a" in p.read_text(encoding="utf-8")]
        self.assertEqual(found, ["results.html"])
        self.assertEqual(TEMPLATE.count('class="stack{% if public_mode %} res-a{% endif %}"'), 1)

    def test_motion_is_only_in_the_no_preference_block_and_reuses_a2_s_keyframe(self):
        seen = 0
        for m in re.finditer(r"(?<![\w-])(animation|transition)(?:-[\w-]+)?\s*:\s*([^;}]*)", A9):
            seen += 1
            self.assertIn("@media (prefers-reduced-motion: no-preference)", enclosing(A9, m.start()))
        self.assertGreaterEqual(seen, 3)
        self.assertNotIn("@keyframes", A9)
        self.assertIn("animation: a-pop", A9)

    def test_no_raw_colour(self):
        self.assertNotRegex(A9, r"#[0-9A-Fa-f]{3,8}\b")
        self.assertNotRegex(A9, r"rgba?\(|hsla?\(")
        self.assertNotRegex(A9, r"[:\s](white|black|red|green|blue|orange|yellow|purple|pink)\s*[;}]")

    def test_peach_is_money_only(self):
        for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", A9):
            if re.search(r"var\(--(paid|a-pch)", m.group(2)):
                self.assertEqual(m.group(1).strip(), ".skin-a .res-a .paid-word", m.group(0))
        self.assertIn("var(--paid)", A9)

    def test_nothing_is_banded_by_value(self):
        self.assertNotRegex(A9, r"\.(hi|mid|lo|neg|band|positive|negative)\b")
        self.assertNotRegex(A9, r"nth-child\(\d+\)[^{]*td\.score")

    def test_the_tabs_current_state_is_not_colour_alone(self):
        rule = re.search(r'\.skin-a \.res-a \.views a\[aria-current="page"\][^{]*\{([^}]*)\}', A9).group(1)
        self.assertIn("font-weight: 800", rule)
        self.assertIn("background: var(--chalk)", rule)

    def test_the_head_is_visually_hidden_not_removed(self):
        rule = re.search(r"\.skin-a \.res-a \.jobs thead \{([^}]*)\}", A9).group(1)
        self.assertNotIn("display: none", rule)
        self.assertIn("clip: rect(0 0 0 0)", rule)

    def test_the_phone_rules_and_the_apply_foot(self):
        phone = A9[A9.index("@media (max-width: 40rem)"):]
        phone = phone[:phone.index("@media (prefers-reduced-motion")]
        self.assertRegex(phone, r"\.jobs td\.act \.apply \{[^}]*position: static[^}]*flex: 0 0 100%[^}]*min-height: 48px")
        self.assertRegex(phone, r"\.jobs td\.score \{ position: static")

    def test_the_peek_body_shows_every_tag_against_sweep_css_s_first_three(self):
        sweep = (ROOT / "static" / "sweep.css").read_text(encoding="utf-8")
        self.assertIn(".jobs td.skills .tag:not(.more):nth-child(n+4) { display: none; }", sweep)       # the rule this overrides, in the file this tree does not touch
        self.assertRegex(A9, r"\.skin-a \.res-a \.jobs td\.skills details\.why \.why-body \.tag \{\s*display: inline-block")

    def test_sweep_css_is_not_edited_by_this_stage(self):
        # a lower bound that would fail if a rule for this page's new parts were added to the console's sheet
        sweep = (ROOT / "static" / "sweep.css").read_text(encoding="utf-8")
        for name in (".why-body", ".why-t", "res-a", ".scale-line", ".scale-zero", "details.why"):
            self.assertNotIn(name, sweep)


if __name__ == "__main__":
    unittest.main()
