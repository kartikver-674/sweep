"""D6: the live Results page, in the Quiet Ledger.

The suggested résumé is a line of its own and its name is set apart by the ROLE of a
piece of the engine's sentence, never by searching the sentence; the match is a raw
signed figure; Pay and Experience are columns only where a job states them; Export is a
door of its own, outside Filter and sort, with all four formats alike; the tabs are
links to the same ids; Apply is a word you can see is one; nothing that happens to a
row fades it. Legacy (one résumé) and Multi-Track rows, public and operator, through
the same fakes the other Results tests use. No model, provider or network.
"""
import html
import itertools
import json
import os
import pathlib
import re
import tempfile
import unittest

import markupsafe

from deploy import sweep_worker
from sweep import app as app_module
from sweep import logic, worker_link
from sweep.tests import test_multi_results_view as rv
from sweep.tests.test_terminal_states import app_ended
from sweep.tests.test_progress_ui import sweep_app

setUpModule, tearDownModule = rv.setUpModule, rv.tearDownModule

CSS = (pathlib.Path(app_module.__file__).parent / "static" / "sweep.css").read_text(encoding="utf-8")


def rule(selector):
    """The body of the first rule whose selector list ends with `selector`."""
    m = re.search(r"(?:^|\n)\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    return m.group(1) if m else ""


def flat(markup):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", markup))).strip()


def row(n, title="Senior Backend Engineer", score="62", pay="", exp="", site="linkedin", skills="python, django",
        url=None, where="Pune, India", **kw):
    return dict({"title": f"{title} {n}" if n else title, "company": f"Company {n}", "location": where,
                 "score": score, "salary": pay, "experience_required": exp, "source_site": site,
                 "matched_skills": skills, "apply_url": url if url is not None else f"https://jobs.test/{n}",
                 "date_posted": "2026-09-27"}, **kw)


def legacy_app(rows, public=False):
    """A one-résumé Results screen on the console's own injected fakes."""
    app = app_module.create_app(
        state={"profile": "kabir", "cap_usd": 8.41, **({"free_only": True} if public else {})},
        extract=lambda p: "x", derive=lambda t, p: {}, check_token=lambda t: (8.41, None),
        read_rows=lambda profile: [dict(r) for r in rows], start_rescore=lambda profile, hours: None,
        output_dir=tempfile.mkdtemp())
    app.config.update(TESTING=True, PUBLIC_MODE=public)
    return app


def page(app, path="/results"):
    return app.test_client().get(path).get_data(as_text=True)


# ---------------------------------------------------------------------------------------------
# What the engine's recommendation said before it could be cut into pieces (75130e0), kept here
# verbatim so that "the same words" is a comparison against the original and not against itself.
def _reference_words(typed, labels):
    if "recommendation" not in typed:
        return None
    names = [labels[tid] for tid in typed["recommended_tracks"]]
    lead, rest = names[0], names[1:]
    are = "is" if len(rest) == 1 else "are"
    kind = typed["recommendation"]
    if kind == "clear":
        said = [f"Suggested résumé: {lead}."]
    elif kind == "close":
        said = [f"Suggested résumé: {lead}.", f"{logic.and_list(rest)} {are} close behind."]
    elif kind == "tied":
        said = [f"{logic.and_list(names)} fit equally."]
    else:
        said = [f"{lead} covers more of this posting.", f"{logic.and_list(rest)} {are} also suggested."]
    caution = None
    if typed.get("recommendation_caution") == logic.NO_FOCUS_EVIDENCE:
        caution = (f"This posting doesn't mention the skills or role your suggested "
                   f"résumé ({lead}) focuses on." if len(names) == 1 else
                   "This posting doesn't mention the skills or role these suggested "
                   "résumés focus on.")
    return {"caution": caution, "suggestion": said}


NAMES = ["Backend Engineer", "Backend", "A", "A (2)", "Senior Full Stack Developer (Payments)", "x" * 40,
         """<b onmouseover="x">&'y'</b>""", "It's — “quoted”, and: (nested (twice))", "Backend Engineer and Platform",
         "Résumé 1"]


def typed(kind, ids, caution=None):
    out = {"recommended_tracks": list(ids), "recommendation": kind}
    if caution is not None:
        out["recommendation_caution"] = caution
    return out


class Pieces(unittest.TestCase):
    """The sentence the page draws is the sentence the engine's words say."""

    def cases(self):
        for kind in ("clear", "close", "tied", "split"):
            for n in (1, 2, 3):
                for chosen in itertools.islice(itertools.permutations(NAMES, n), 0, None, 37):
                    labels = {f"t{i}": name for i, name in enumerate(chosen)}
                    for caution in (None, "", logic.NO_FOCUS_EVIDENCE):
                        yield kind, labels, typed(kind, labels, caution)

    def test_the_pieces_join_to_exactly_the_original_words(self):
        seen = 0
        for kind, labels, t in self.cases():
            with self.subTest(kind=kind, labels=list(labels.values()), caution=t.get("recommendation_caution")):
                want = _reference_words(t, labels)
                self.assertEqual(logic.recommendation_words(t, labels), want)
                got = logic.recommendation_pieces(t, labels)
                self.assertEqual([("".join(x for x, _ in s)) for s in got["suggestion"]], want["suggestion"])
                self.assertEqual("".join(x for x, _ in got["caution"]) if got["caution"] else None, want["caution"])
            seen += 1
        self.assertGreater(seen, 250)

    def test_no_recommendation_is_none_in_both(self):
        self.assertIsNone(logic.recommendation_pieces({"best_track": "t0"}, {"t0": "A"}))
        self.assertIsNone(logic.recommendation_words({"best_track": "t0"}, {"t0": "A"}))

    def test_a_name_is_a_piece_of_its_own_with_the_role_the_engines_order_gives_it(self):
        labels = {"a": "Alpha", "b": "Beta", "c": "Gamma"}
        roles = lambda kind, ids, caution=None: [  # noqa: E731
            [(t, r) for t, r in s if r] for s in logic.recommendation_pieces(typed(kind, ids, caution), labels)["suggestion"]]
        self.assertEqual(roles("clear", "a"), [[("Alpha", "name")]])
        self.assertEqual(roles("close", "abc"), [[("Alpha", "name")], [("Beta", "other"), ("Gamma", "other")]])
        self.assertEqual(roles("split", "ba"), [[("Beta", "name")], [("Alpha", "other")]])
        self.assertEqual(roles("tied", "cab"), [[("Gamma", "peer"), ("Alpha", "peer"), ("Beta", "peer")]])
        one = logic.recommendation_pieces(typed("clear", "a", logic.NO_FOCUS_EVIDENCE), labels)["caution"]
        self.assertEqual([p for p in one if p[1]], [("Alpha", "name")])
        many = logic.recommendation_pieces(typed("tied", "ab", logic.NO_FOCUS_EVIDENCE), labels)["caution"]
        self.assertEqual([p for p in many if p[1]], [])             # names nothing it did not name

    def test_a_label_inside_the_engines_own_words_is_never_searched_for(self):
        # "Backend" is inside "Backend Engineer" and "A" is inside everything; the pieces are
        # built, not found, so the second name cannot be mistaken for part of the first.
        labels = {"a": "Backend Engineer", "b": "Backend", "c": "A"}
        got = logic.recommendation_pieces(typed("close", "abc"), labels)["suggestion"]
        self.assertEqual([(t, r) for t, r in got[0] if r], [("Backend Engineer", "name")])
        self.assertEqual([(t, r) for t, r in got[1] if r], [("Backend", "other"), ("A", "other")])


class Legacy(unittest.TestCase):
    """One résumé: today's Results, redrawn."""

    ROWS = [row(1, score="104", pay="INR 45–60 LPA", exp="8+"), row(2, score="62"),
            row(3, score="7", exp="4+"), row(4, score="-3", site="greenhouse")]

    def test_pay_and_experience_are_columns_only_where_a_job_states_them(self):
        body = page(legacy_app(self.ROWS))
        self.assertRegex(body, r'<th scope="col" class="pay">Pay</th>')
        self.assertRegex(body, r'<th scope="col" class="exp">Experience</th>')
        bare = page(legacy_app([row(n, score=str(40 - n)) for n in (1, 2, 3)]))
        self.assertNotIn(">Pay</th>", bare)
        self.assertNotIn(">Experience</th>", bare)
        self.assertNotIn('class="pay', bare)
        only_pay = page(legacy_app([row(1, pay="USD 70k"), row(2)]))
        self.assertIn(">Pay</th>", only_pay)
        self.assertNotIn(">Experience</th>", only_pay)

    def test_an_absent_fact_is_a_dash_spoken_as_not_stated_and_never_drawn_on_a_phone(self):
        body = page(legacy_app(self.ROWS))
        cell = re.search(r'<td class="pay none">(.*?)</td>', body, re.S).group(1)
        self.assertIn('<span aria-hidden="true">—</span>', cell)
        self.assertIn('<span class="visually-hidden">Not stated</span>', cell)
        self.assertNotRegex(re.sub(r'<span class="visually-hidden">.*?</span>', "", body),
                            r"Not stated")                      # never a visible word, row after row
        phone = CSS[CSS.index("@media (max-width: 47.99rem)"):]
        self.assertIn(".jobs td.none { display: none; }", phone[:phone.index("\n}\n")])

    def test_a_fact_that_is_shown_says_what_it_is_on_a_phone(self):
        body = page(legacy_app(self.ROWS))
        self.assertIn('<span class="mlabel">Pay </span>INR 45–60 LPA', body)
        self.assertIn('<span class="mlabel">Experience </span>8+', body)
        self.assertNotIn("yrs", body)                           # no unit the data never gave
        self.assertIn("display: none", rule(".mlabel, .m-only"))

    def test_the_score_is_the_raw_signed_value_in_its_own_cell(self):
        # Today's floor of 0 on a one-résumé run: a negative row is there once the floor is lowered.
        self.assertNotIn(">-3</td>", page(legacy_app(self.ROWS)))
        body = page(legacy_app(self.ROWS), "/results?min=-10")
        for score in ("104", "62", "7", "-3"):
            self.assertIn(f">{score}</td>", body)
        visible = re.sub(r"<[^>]+>", " ", body)
        self.assertNotRegex(visible, r"\b\d+\s*%")              # never a percentage
        for word in ("confidence", "probability", "chance", "strong match", "weak match"):
            self.assertNotIn(word, visible.lower())
        rules = rule(".jobs td.score")
        self.assertIn("text-align: right", rules)
        self.assertIn("font-variant-numeric: tabular-nums", rules)

    def test_no_row_state_fades_a_row(self):
        self.assertNotRegex(CSS, r"tr\.(applied|opened)[^{]*\{[^}]*opacity")
        self.assertNotRegex(CSS, r"\.jobs[^{]*\{[^}]*opacity\s*:\s*0?\.\d")

    def test_the_applied_column_and_tick_are_the_consoles_only(self):
        rows = [row(1)]
        console, public = page(legacy_app(rows)), page(legacy_app(rows, public=True))
        self.assertIn('<td class="did">', console)
        self.assertIn("data-key=", console)
        self.assertIn("&check;</span> Applied", console)
        self.assertNotIn('class="did"', public)
        self.assertNotIn("data-key=", public)
        self.assertNotIn("Applied", re.sub(r'<span class="visually-hidden">.*?</span>', "", public))
        self.assertNotIn("/applied", public)
        self.assertIn('x-data="{ done: false }"', public)       # the row still owns its state

    def test_apply_keeps_its_destination_and_is_a_named_action(self):
        body = page(legacy_app([row(1), row(2, url="javascript:alert(1)"), row(3, url="")]))
        self.assertIn('<a class="apply" href="https://jobs.test/1" target="_blank" rel="noopener">Apply', body)
        self.assertIn('<span class="visually-hidden"> to Senior Backend Engineer 1 at Company 1</span>', body)
        self.assertNotIn("javascript:", body)
        self.assertEqual(body.count("No link"), 2)
        self.assertEqual(body.count('class="rowlink" data-href='), 1)
        a = rule(".jobs td.act .apply")
        self.assertRegex(a, r"font:\s*600 14px")
        self.assertIn("text-decoration: underline", a)

    def test_apply_is_a_44px_target_on_a_phone_and_24px_with_a_mouse(self):
        phone = CSS[CSS.index("@media (max-width: 47.99rem)"):]
        phone = phone[:phone.index("\n}\n")]
        self.assertRegex(phone, r"\.jobs td\.act \.apply \{[^}]*min-height: 44px")
        self.assertRegex(CSS, r"@media \(not \(pointer: coarse\)\) and \(min-width: 48rem\) \{\s*\.listings td\.act \.apply \{[^}]*padding-block: 4px")

    def panel(self, body, which):
        """The markup of one tool panel (filter or export), and only it."""
        start = body.index(f'id="tool-{which}"')
        return body[start:body.index("\n    </div>", start)]

    def test_tools_are_one_line_and_export_is_a_button_of_its_own_outside_filter_and_sort(self):
        body = page(legacy_app(self.ROWS, public=True))
        toggles = re.findall(r'<button type="button" class="secondary tool-toggle"[^>]*>(.*?)</button>', body, re.S)
        self.assertEqual(toggles, ["Filter and sort", "Export…"])              # one line, two buttons
        self.assertIn('aria-controls="tool-filter"', body)
        self.assertIn('aria-controls="tool-export"', body)
        filt = self.panel(body, "filter")
        self.assertIn("Minimum score", filt)
        self.assertNotIn("/export.", filt)
        door = self.panel(body, "export")
        links = re.findall(r'<a class="(\w+)" href="(/export\.(\w+))', door)
        self.assertEqual([fmt for _c, _h, fmt in links], ["xlsx", "csv", "json", "html"])
        self.assertEqual({c for c, _h, _f in links}, {"secondary"})          # none is the one you are meant to want
        self.assertIn("Export 3 listings", flat(door))

    def test_the_exports_carry_the_applied_filters_and_not_the_typed_ones(self):
        body = page(legacy_app(self.ROWS, public=True), "/results?min=10&q=backend&sort=recent")
        for fmt in ("xlsx", "csv", "json", "html"):
            href = html.unescape(re.search(rf'href="(/export\.{fmt}[^"]*)"', body).group(1))
            self.assertIn("min=10", href)
            self.assertIn("q=backend", href)
            self.assertIn("sort=recent", href)
        # the state that made the list is not hidden from it: the filter panel is drawn open
        self.assertIn('aria-expanded="true"', body)
        self.assertNotIn('id="tool-filter" x-show="tool === \'filter\'" style="display:none"', body)

    def test_the_filter_panel_is_closed_until_something_is_filtered_and_the_buttons_say_so(self):
        for public in (True, False):
            body = page(legacy_app(self.ROWS, public=public))
            self.assertIn('id="tool-filter" x-show="tool === \'filter\'" style="display:none"', body)
            self.assertIn('aria-expanded="false"', body)
            self.assertIn("Sorted by Best match", body)
            self.assertNotIn("filters applied", body)
        filtered = page(legacy_app(self.ROWS), "/results?min=10")
        self.assertIn("filters applied", filtered)
        self.assertIn("Sorted by Newest first", page(legacy_app(self.ROWS), "/results?sort=recent"))

    def test_the_clear_link_is_not_offered_twice_over_an_empty_result(self):
        body = page(legacy_app(self.ROWS, public=True), "/results?min=999")
        self.assertNotIn("filters applied", body)                              # the empty state carries the way out
        self.assertIn("Clear the minimum score", body)

    def test_the_count_still_leads_and_the_score_is_explained_behind_one_door(self):
        body = page(legacy_app(self.ROWS, public=True), "/results?min=-10")
        self.assertIn("4 jobs found", flat(body))
        self.assertIn("<summary>How match scores work</summary>", body)
        self.assertIn("It is a raw score, not a percentage, and it can be negative.", flat(body))
        self.assertNotIn("A résumé's view lists", body)                        # no tabs, no tab paragraph
        self.assertNotIn('class="views"', body)

    def test_an_empty_run_and_an_empty_filter_each_say_one_thing_and_offer_one_way_on(self):
        nothing = page(legacy_app([], public=True))
        self.assertIn("No jobs to show", nothing)
        self.assertIn('href="/configure"', nothing)
        self.assertNotIn(">Export…<", nothing)                                # nothing to export
        filtered = page(legacy_app(self.ROWS, public=True), "/results?min=999")
        self.assertIn("The minimum score filter removed the most", flat(filtered))
        self.assertIn("Clear the minimum score", filtered)

    def test_a_section_is_a_heading_over_ruled_rows_not_a_box(self):
        body = page(legacy_app(self.ROWS))
        self.assertIn('<section class="jobs-section">', body)
        self.assertNotIn('class="panel reveal', body)
        self.assertNotIn(' reveal ', body)                            # D7B: no section entrance that replays on every load
        self.assertIn('<table class="jobs" aria-label="Onsite and hybrid in India">', body)

    def test_the_phone_labels_the_figure_groups_the_tabs_and_keeps_the_company_on_its_own_line(self):
        phone = CSS[CSS.index("@media (max-width: 47.99rem)"):]
        phone = phone[:phone.index("\n}\n")]
        self.assertRegex(phone, r'\.jobs td\.score::after \{[^}]*content: "match"')
        self.assertRegex(phone, r"\.views \{[^}]*display: grid[^}]*grid-template-columns: 1fr 1fr")
        self.assertIn(".job-line .co { flex: 0 0 100%; }", phone)
        self.assertRegex(rule(".jobs td"), r"vertical-align: baseline")
        self.assertRegex(CSS, r"@media \(pointer: coarse\) \{ \.views a \{[^}]*min-height: 44px")

    def test_a_name_in_the_recommendation_stays_whole_and_the_two_lines_share_a_left_edge(self):
        self.assertIn("white-space: nowrap", rule(".nb"))                    # a name and its full stop are one unit
        self.assertRegex(rule(".suggest"), r"padding-left: 20px")             # 2px rule + 20px = the caution's 16px ring + 6px gap
        self.assertRegex(rule(".caution"), r"gap: 6px")
        self.assertRegex(rule(".bang"), r"width: 16px")
        self.assertRegex(rule(".rname"), r"font-weight: 600")
        self.assertRegex(rule(".rpeer"), r"font-weight: 500")
        self.assertRegex(rule(".rname2"), r"font-weight: 400")

    def test_amber_is_money_only_and_no_results_text_is_under_12px(self):
        results_rules = CSS[CSS.index("/* ---- Results ----"):CSS.index("/* How many listings the section holds")]
        self.assertNotIn("--paid", results_rules)
        self.assertNotRegex(results_rules, r"#f0a22e|#ffc376")
        self.assertIn("accent-color: var(--chalk)", rule(".tick input"))
        for size in re.findall(r"font(?:-size)?:[^;{}]*?\b(\d+)px", results_rules):
            self.assertGreaterEqual(int(size), 12, size)


class Ending(unittest.TestCase):
    """Results must not read like a finished search when the run behind it was not one.

    The run strip stands down on Results for every ending (it would point at where the reader
    already is), so the page itself says how the run ended, in the Running screen's own state
    (sweep_state) and the same banner. Nothing for a run that finished whole."""

    PARTIAL = {"outcome": "partial", "skipped_insufficient_capacity": 27, "skipped_budget": 0,
               "placeable_paid_units": 19, "total_planned_paid_units": 46, "partial_estimate_usd": 1.1}

    def banner(self, app):
        body = page(app)
        m = re.search(r'<div class="banner ?([^"]*)" role="note">\s*<div><b>(.*?)</b> <span>(.*?)</span>', body, re.S)
        return m and (m.group(1), m.group(2), m.group(3))

    def test_a_run_that_finished_whole_says_nothing_and_so_does_one_still_going(self):
        for app in (app_ended(0, free=True), sweep_app(free=True, alive=True), app_ended(0, done=46),
                    app_ended(1, free=True, ready=True)):                 # a result the worker declared final
            self.assertIsNone(self.banner(app))

    def test_each_ending_says_what_it_was_in_the_running_screens_words(self):
        for app, want in (
                (app_ended(1, free=True), ("warn", "This search did not finish", "These are the jobs it found before it stopped.")),
                (app_ended(1, free=True, timed_out=True), ("warn", "This search ran out of time", "These are the jobs it found before it stopped.")),
                (app_ended(1, free=True, stopped=True), ("", "You stopped this search", "These are the jobs it found before you stopped it.")),
                (app_ended(1, done=19), ("warn", "This search did not finish", "These are the jobs it found before it stopped.")),
                (app_ended(1, done=19, stopped=True), ("", "You stopped this search", "These are the jobs it found before you stopped it.")),
                (app_ended(0, done=19, authorization=self.PARTIAL),
                 ("part", "Part of your search ran", "These are the jobs from the paid searches your credit covers, as you chose. "
                                                     "The others were not run, and nothing was charged for them.")),
                (app_ended(1, done=0, authorization={"outcome": "refused"}),
                 ("warn", "Your search did not start", "Nothing was searched and nothing was charged."))):
            self.assertEqual(self.banner(app), want)

    def test_it_is_the_same_on_the_console_and_in_public_and_never_a_cause_nobody_recorded(self):
        for kw in ({}, {"timed_out": True}, {"stopped": True}):
            pub = self.banner(app_ended(1, free=True, public=True, **kw))
            con = self.banner(app_ended(1, free=True, public=False, **kw))
            self.assertEqual(pub, con)
        unexplained = page(app_ended(1, free=True))
        self.assertNotIn("ran out of time", unexplained)
        self.assertNotIn("credit ran out", unexplained)

    def test_a_partial_run_is_not_a_failure_and_a_failure_is_not_a_success(self):
        body = page(app_ended(0, done=19, authorization=self.PARTIAL))
        self.assertIn('<div class="banner part" role="note">', body)
        self.assertNotIn('class="banner warn"', body)
        self.assertIn('class="banner warn" role="note"', page(app_ended(1, free=True)))

    def test_the_mapping_is_the_running_screens_state_word_for_word(self):
        for state in ("running", "finished"):
            self.assertIsNone(logic.results_ending(state))
        for state in ("partial", "credit_changed", "stopped", "out_of_credit", "halted"):
            got = logic.results_ending(state)
            self.assertTrue(got["headline"] and got["detail"], state)
            self.assertIn(got["tone"], ("", "warn", "part"))
        self.assertEqual(logic.results_ending("halted", timed_out=True)["headline"], "This search ran out of time")
        self.assertEqual(logic.results_ending("halted")["headline"], "This search did not finish")
        for state in logic.SWEEP_STATES:
            logic.results_ending(state)                                     # every state the screen can have has an answer


class MultiTrack(rv.Results):
    """Several résumés: the tabs, the recommendation line and the export's meaning."""

    def setUp(self):
        super().setUp()
        self.ids = self.run_multi("ada", "bhaskar", "chen")

    def test_the_tabs_are_links_to_the_same_ids_with_the_same_counts(self):
        self.serve()
        body = self.page()
        nav = re.search(r'<nav class="views" aria-label="Which jobs to show">(.*?)</nav>', body, re.S).group(1)
        hrefs = [html.unescape(h) for h in re.findall(r'href="([^"]*)"', nav)]
        self.assertEqual(hrefs, ["/results", f"/results?track={rv.A}", f"/results?track={rv.B}", f"/results?track={rv.C}"])
        self.assertEqual([t for t, _c in self.views(body)],
                         [f"All Jobs (6) — showing", f"{rv.LA} (5)", f"{rv.LB} (5)", f"{rv.LC} (4)"])
        self.assertEqual(nav.count("<a"), 4)
        self.assertNotIn("primary", nav)

    def test_a_tab_keeps_the_filters_and_the_sort(self):
        self.serve()
        body = self.page(min=5, sort="recent", source="greenhouse")
        nav = re.search(r'<nav class="views".*?</nav>', body, re.S).group(0)
        for href in re.findall(r'href="([^"]*)"', nav):
            href = html.unescape(href)
            self.assertIn("min=5", href)
            self.assertIn("sort=recent", href)
            self.assertIn("source=greenhouse", href)

    def test_one_job_is_in_several_views_with_each_views_own_score(self):
        self.serve()
        in_all = self.rows_of(self.page())
        in_a, in_b = self.rows_of(self.page(track=rv.A)), self.rows_of(self.page(track=rv.B))
        self.assertIn(1, in_a)
        self.assertIn(1, in_b)                                  # evaluated for both, so in both
        self.assertIn(">30</td>", in_a[1])                      # A's own
        self.assertIn(">12</td>", in_b[1])                      # B's own
        self.assertIn(">30</td>", in_all[1])                    # All Jobs: the row's own
        self.assertNotIn(6, self.rows_of(self.page(track=rv.C)))   # no evaluation for C, so not there
        self.assertIn(">-3</td>", in_all[6])                    # a negative row is still a row

    def test_every_situation_is_a_line_of_its_own_caution_first_with_the_name_set_apart(self):
        self.serve()
        rows = self.rows_of(self.page())
        nb = lambda inner, mark="": f'<span class="nb">{inner}{mark}</span>'          # noqa: E731  a name and its mark, one unit
        lead = lambda name: f'<b class="rname">{name}</b>'                              # noqa: E731
        other = lambda name: f'<span class="rname2">{name}</span>'                      # noqa: E731
        self.assertEqual(re.findall(r'<p class="suggest">(.*?)</p>', rows[1], re.S)[0],
                         f'Suggested résumé: {nb(lead(rv.LA), ".")}')
        self.assertIn(f'{nb(lead(rv.LB), ".")} {nb(other(rv.LA))} is close behind.', rows[2])
        self.assertEqual(rows[2].count('<b class="rname">'), 1)                        # the lead carries the weight, nobody else
        self.assertIn(f'{nb(lead(rv.LB))} covers more of this posting. '
                      f'{nb(other(rv.LC))} is also suggested.', rows[5])
        peer = lambda name: f'<span class="rpeer">{name}</span>'                        # noqa: E731
        self.assertIn(f'{nb(peer(rv.LA), ",")} {nb(peer(rv.LB))} and {nb(peer(rv.LC))} fit equally.', rows[4])   # peers: none leads, so none shouts
        for n in (3, 4):                                         # the caution is the first of the two lines
            self.assertLess(rows[n].index('<p class="caution">'), rows[n].index('<p class="suggest">'))
        self.assertIn(f'(<span class="nb"><b class="rname">{rv.LC}</b>)</span> focuses on.', rows[3])
        self.assertIn("these suggested résumés focus on.", rows[4])
        self.assertNotIn('class="caution"', rows[1])
        self.assertEqual(self.said(rows[1]), [f"Suggested résumé: {rv.LA}."])
        self.assertIn('<span class="bang" aria-hidden="true">!</span>', rows[3])

    def test_a_caution_is_a_quiet_qualification_not_an_error(self):
        self.assertNotIn("--over", rule(".caution"))
        self.assertNotRegex(rule(".caution"), r"background")
        self.assertIn("var(--warm)", rule(".caution"))

    def test_the_words_are_the_engines_and_nothing_the_template_made_up(self):
        self.serve()
        page = self.page()
        visible = flat(re.sub(r"<(script|style)\b.*?</\1>", "", page, flags=re.S))
        for imperative in ("Use this résumé", "use this résumé", "Apply with", "Send this résumé", "best résumé"):
            self.assertNotIn(imperative, visible)
        labels = {rv.A: rv.LA, rv.B: rv.LB, rv.C: rv.LC}
        for n, markup in self.rows_of(page).items():
            src = next(x for x in rv.ROWS if x["title"] == f"Job {n}")
            t = {"recommended_tracks": src["recommended_tracks"].split(";"), "recommendation": src["recommendation"]}
            if src.get("recommendation_caution") is not None:
                t["recommendation_caution"] = src["recommendation_caution"]
            want = logic.recommendation_words(t, labels)
            self.assertEqual(self.said(markup),
                             ([f"Note: {want['caution']}"] if want["caution"] else []) + [" ".join(want["suggestion"])])

    def test_a_name_with_markup_and_parentheses_is_text_and_its_parentheses_stay_its_own(self):
        evil = """<b onmouseover="x">&'y'</b> (Payments (EU))"""[:40]
        self.act(rv.C, "rename", name=evil)                      # job 3's suggestion, with the singular caution
        self.serve()
        body = self.page()
        self.assertNotIn("<b onmouseover", body)
        self.assertIn(f'<b class="rname">{markupsafe.escape(evil)}</b>', body)
        self.assertIn(f'(<span class="nb"><b class="rname">{markupsafe.escape(evil)}</b>)</span> focuses on.', body)

    def test_a_long_label_is_not_shortened_and_the_file_is_not_put_in_its_place(self):
        long = "Senior Full Stack Developer (Payments)"
        self.act(rv.B, "rename", name=long)
        self.serve()
        body = self.page(track=rv.B)
        self.assertIn(long, self.flat(re.search(r'<nav class="views".*?</nav>', body, re.S).group(0)))
        self.assertIn(f'title="From {rv.FB}"', body)
        self.assertIn(f"{rv.FB}", self.flat(re.search(r'<p class="meta view-note">(.*?)</p>', body, re.S).group(1)))
        self.assertNotIn(rv.FB, self.flat(re.search(r'<table class="jobs".*?</table>', body, re.S).group(0)))

    def test_a_run_with_no_recommendation_draws_no_suggestion_line(self):
        self.serve(rv.ROWS, recommend=False, caution=False)
        body = self.page()
        self.assertNotIn('class="suggest"', body)
        self.assertNotIn('class="caution"', body)
        self.assertNotIn("Job and suggested résumé", body)       # nothing to head the column with
        self.assertRegex(body, r'<th scope="col">Job</th>')
        self.assertIn("Every job once.", self.flat(body))
        self.assertNotIn("the résumé Sweep suggests", self.flat(body))
        self.assertEqual(self.seen(body), rv.ORDER[None])

    def test_pay_and_experience_follow_the_jobs_in_the_view(self):
        rows = [dict(r, salary="", experience_required="") for r in rv.ROWS]
        self.serve(rows)
        body = self.page()
        self.assertNotIn(">Pay</th>", body)
        self.assertNotIn(">Experience</th>", body)
        rows[0]["salary"] = "INR 28–36 LPA"
        self.serve(rows)
        body = self.page()
        self.assertIn(">Pay</th>", body)
        self.assertNotIn(">Experience</th>", body)
        self.assertEqual(body.count('class="pay none"'), 5)
        self.assertEqual(body.count('<td class="pay">'), 1)
        csv_text = self.client.get("/export.csv").get_data(as_text=True)
        self.assertIn(",Pay,", csv_text.splitlines()[0])         # the data is never dropped, only the column

    def worker_says(self, **status):
        """The worker's status for this run changes; its answer is cached for a few seconds per
        owner (P4-S1C), so the cache is emptied as a clock would."""
        self.worker.store.update(self.run_id, **status)
        worker_link._ASKED.clear()
        proc = self.room()["proc"]            # a RemoteRun keeps the first ending it sees; one test plays several
        proc._code, proc.timed_out, proc.stopped = None, False, False

    def test_a_run_the_worker_says_failed_stopped_or_timed_out_says_so_on_its_results(self):
        self.serve()
        self.assertNotIn('role="note"', self.page())                        # whole: nothing
        out = self.worker.store.output_dir(self.run_id)
        marker = os.path.join(out, sweep_worker.READY_MARKER)
        with open(marker, "w", encoding="utf-8") as fh:                     # the engine's word that the result is final
            json.dump({"at": 1.0}, fh)
        self.worker_says(state="failed", error=None)
        self.assertNotIn('role="note"', self.page())                        # …survives a crash after it
        os.remove(marker)                                                  # a run that failed part-way never said so
        for state, error, headline in (("failed", None, "This search did not finish"),
                                       ("failed", "run_timeout", "This search ran out of time"),
                                       # no Stop click of ours in this session: the worker's own `stopped` is the word (D7C)
                                       ("stopped", None, "You stopped this search"),
                                       ("interrupted", None, "This search did not finish")):   # a worker restart is not a stop
            self.worker_says(state=state, error=error)
            body = self.page()
            self.assertIn(f"<b>{headline}</b>", body, (state, error))
            self.assertEqual(self.seen(body), rv.ORDER[None])                # the jobs are all still there

    def test_D7C_a_paid_run_whose_every_search_ran_and_whose_process_then_failed_is_not_a_finished_search(self):
        """Schema 2, through the real worker: the planned Sweep has paid searches and the worker's ledger (.done_combos, which the
        engine appends to as each search ends) holds every one of them. The ledger proves the searches ran, not that the engine ended
        well: failed, interrupted or timed out with the result never declared final, it is "did not finish" (every search ran, then it
        stopped); stopped by the visitor, stopped; a result the worker declared final stays final. The jobs stay on the page."""
        from sweep import runs as runs_mod
        self.serve()
        room = self.room()
        raw = dict(room["raw_plan"], sites={"linkedin": [{"keywords": f"Backend{n}", "location": "India", "company": ""} for n in range(3)]},
                   max_results={"linkedin": 15})
        room["raw_plan"] = raw
        keys = runs_mod.combo_keys(raw, runs_mod.today())
        self.assertEqual(len(set(keys)), 3)
        out = self.worker.store.output_dir(self.run_id)

        def ledger(have):
            with open(os.path.join(out, ".done_combos"), "w", encoding="utf-8") as fh:
                fh.write("".join(k + "\n" for k in have))
            worker_link._ASKED.clear()

        def says(state, error, have=keys):
            ledger(have)
            self.worker_says(state=state, error=error)
            body = self.page()
            return body, self.flat(body)

        def want(cond, msg):
            if not cond:
                self.fail(msg)

        every = "Every search ran, then the sweep stopped before it finished. These are the jobs it found."
        for state, error, headline in (("failed", None, "This search did not finish"),
                                       ("interrupted", None, "This search did not finish"),
                                       ("failed", "run_timeout", "This search ran out of time")):
            body, flat = says(state, error)
            want(f"<b>{headline}</b>" in body, f"{state}/{error}: the headline should be {headline!r}")
            want(every in flat, f"{state}/{error}: the ending should say every search ran")
            self.assertEqual(self.seen(body), rv.ORDER[None], "the jobs are all still there")
        body, _ = says("stopped", None)
        want("<b>You stopped this search</b>" in body, "an explicit stop is a stop")
        body, _ = says("done", None)
        want('role="note"' not in body, "a clean exit with the ledger complete is a finished search")
        marker = os.path.join(out, sweep_worker.READY_MARKER)
        with open(marker, "w", encoding="utf-8") as fh:                     # declared final, then a crash after it
            json.dump({"at": 1.0}, fh)
        body, _ = says("failed", None)
        want('role="note"' not in body, "a result the worker declared final stays final")
        os.remove(marker)
        body, flat = says("failed", None, have=keys[:1])                    # short of its searches: unchanged
        want("<b>This search did not finish</b>" in body, "short of its searches it did not finish")
        want("Every search ran" not in flat, "and it does not say every search ran")

    def test_a_views_tabs_and_banner_do_not_hide_each_other(self):
        self.serve()
        self.worker_says(state="failed", error=None)
        body = self.page(track=rv.B)
        self.assertLess(body.index('role="note"'), body.index('<nav class="views"'))
        self.assertIn(f'<a aria-current="page"', body)


    def test_export_is_a_button_of_its_own_and_says_it_holds_all_jobs_in_every_view(self):
        self.serve()
        for track in (None, rv.B):
            body = self.page(track=track)
            start = body.index('id="tool-export"')
            door = body[start:body.index("\n    </div>", start)]
            self.assertIn("Export All Jobs: 6 listings", flat(door))
            links = re.findall(r'<a class="(\w+)" href="(/export\.\w+)', door)
            self.assertEqual(len(links), 4)
            self.assertEqual({c for c, _h in links}, {"secondary"})
            self.assertFalse(any("track=" in html.unescape(h) for _c, h in links))   # a view never narrows the file
            fstart = body.index('id="tool-filter"')
            self.assertNotIn("/export.", body[fstart:body.index("\n    </div>", fstart)])
        self.assertIn("Exports always hold All Jobs.", self.flat(self.page(track=rv.B)))
        self.assertEqual(len(self.client.get("/export.csv").get_data(as_text=True).splitlines()), 1 + 6)
        self.assertEqual(len(self.client.get(f"/export.csv?track={rv.B}").get_data(as_text=True).splitlines()), 1 + 6)

    def test_all_jobs_says_found_never_matched_because_it_holds_the_negative_scores_too(self):
        """D7C. All Jobs is every job the run evaluated, scores below zero included ("It is a raw score, not a
        percentage, and it can be negative"), so it cannot say they matched a profile. A résumé's own view still says
        what was done for it, because that is accurate."""
        self.serve()
        all_jobs = self.flat(self.page())
        self.assertIn("6 jobs found", all_jobs)
        self.assertNotIn("matched", all_jobs.split("jobs found", 1)[0][-40:])
        self.assertIn(f"5 jobs evaluated for {rv.LA}", self.flat(self.page(track=rv.A)))
        self.assertNotIn("jobs found", self.flat(self.page(track=rv.A)).split("How match scores")[0])

    def test_a_views_heading_names_the_view_and_a_run_with_nothing_draws_no_chrome(self):
        self.serve()
        self.assertIn("6 jobs found", self.flat(self.page()))
        self.assertIn(f"5 jobs evaluated for {rv.LA}", self.flat(self.page(track=rv.A)))
        self.assertIn(f"4 jobs evaluated for {rv.LC}", self.flat(self.page(track=rv.C)))
        self.serve([rv.job(1, rv.A, {rv.A: 30, rv.B: 12}, [rv.A], "clear", "")])
        body = self.page(track=rv.C)                                               # a view with no evaluations, in a run that has a job
        self.assertIn(f"0 jobs evaluated for {rv.LC}", self.flat(body))
        self.assertIn('class="views"', body)                                       # the tabs stay: there are jobs to switch between

    def test_a_run_that_did_not_finish_does_not_call_its_jobs_a_match_for_the_profile(self):
        self.serve()
        self.worker_says(state="failed", error=None)
        self.assertIn("6 jobs found before the search stopped", self.flat(self.page()))
        self.assertNotIn("matched your profile", self.flat(self.page()))
        self.worker_says(state="failed", error="run_timeout")
        self.assertIn("6 jobs found before the search stopped", self.flat(self.page()))

    def test_the_exports_keep_naming_the_files_while_the_screen_names_the_labels(self):
        # Deliberately unchanged by D6 (export label cells are frozen): the screen follows the
        # editable name, the file still says the uploaded file. One line apart if the owner wants
        # them to agree (app.run_labels vs app.run_identities).
        self.serve()
        head, *lines = self.client.get("/export.csv").get_data(as_text=True).splitlines()
        self.assertIn(FILE_IN_EXPORT, "\n".join(lines))
        self.assertNotIn(rv.LA, "\n".join(lines))


FILE_IN_EXPORT = rv.FA


if __name__ == "__main__":
    unittest.main()
