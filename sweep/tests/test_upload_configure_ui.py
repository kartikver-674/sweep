"""The résumé front door, the résumé list and Search preferences, as the quiet
ledger draws them (design phase D4).

Nothing here is a behaviour the other suites do not already pin; this is what
the presentation promises and must keep: one primary action per view, a row that
says its name, its file and its state, the actions grouped so the destructive one
is set apart, the capacity that is left said truthfully, a front door that says
each thing once, and a Configure form whose every control still has its name and
whose Advanced door opens when the thing that is wrong is inside it.

The P4-U1 harness for the upload and the list (the setup on, the real worker on
loopback), and test_search_prefs' own app for Configure. No model, provider or
network.
"""
import copy
import pathlib
import re
import tempfile
import unittest

from sweep import app as app_module
from sweep.tests import test_multi_render as r1
from sweep.tests import test_multi_setup as u1
from sweep.tests import test_search_prefs as sp
from sweep.tests.test_batch_upload import Batch, NAMES, part

setUpModule, tearDownModule = r1.setUpModule, r1.tearDownModule


def content(body):
    """What is inside <main>: the page, without the header or the dialogs."""
    return body.split("<main", 1)[1].split("</main>", 1)[0]


def primaries(body):
    return re.findall(r'class="primary[^"]*"', content(body))


class Row:
    """A résumé's row on the list, as text."""

    def __init__(self, body, n):
        at = body.index(f'<h2 id="resume-{n}"')
        end = body.find('<li class="resume"', at)
        self.html = body[at:end if end != -1 else body.index("</ol>", at)]

    def status(self):
        m = re.search(r'<span class="status (\w+)">([^<]*)</span>', self.html)
        return m.group(1), m.group(2)


# ===========================================================================
class TheFrontDoor(Batch):
    """One heading and one sentence, then the thing to do."""

    def test_it_says_each_thing_once(self):
        body = self.page()
        page = content(body)
        self.assertEqual(body.count('class="mark"'), 1, "the mark is in the header, once")
        self.assertEqual(page.count("<h1"), 1)
        # What it is, what to give it, what to do: one h1, one h2, one control.
        self.assertIn('<h1>Messy job boards in. A <span class="hl">tidy shortlist</span> out.</h1>', page)
        self.assertEqual(re.findall(r"<h2>([^<]*)</h2>", page), ["Add up to 3 résumés"])
        self.assertNotIn("Start with your résumé", page)
        self.assertEqual(page.count('type="file"'), 1)
        self.assertEqual(len(primaries(body)), 1)

    def test_nothing_on_it_is_a_box_inside_a_box(self):
        """The drop zone has an edge because it is the thing to hit; the rest is
        ruled. No panel, inset or tile survives in the page."""
        page = content(self.page())
        for box in ('class="panel', 'class="inset', 'class="tile', 'class="strip'):
            self.assertNotIn(box, page)

    def test_what_to_expect_is_three_peeks_a_desk_and_three_steps_and_keeps_every_fact(self):
        """A4: the rail's "What happens next", Quick Sweep, Deep Sweep and Nothing is kept are gone from the public page.
        Their facts live in the three peeks under the form and in the trail closing the page; the rail holds the desk."""
        page = " ".join(content(self.page()).split())
        self.assertEqual(page.count('class="rail-block"'), 0)       # nothing read yet: no "What Sweep read last time"
        for gone in ('<h2 class="label free">Quick Sweep</h2>', '<h2 class="label paid">Deep Sweep, and optional</h2>',
                     "Nothing is kept", "next-steps", "free-note"):
            self.assertNotIn(gone, page)
        for fact in ("Reading your résumé spends no credit.",
                     "A Quick Sweep is free too.",
                     "A Deep Sweep adds LinkedIn, Indeed and Naukri through your own Apify account, which bills per search.",
                     "Apify’s free plan includes $5 in monthly credits, with no card required; actual search usage varies.",
                     "The PDF itself is never saved",
                     "forgotten within two hours",
                     "A scanned image with no text layer has none to read."):
            self.assertIn(fact, page)
        self.assertEqual(re.findall(r'<span class="peek-label">([^<]*)</span>', page),
                         ["Is it free?", "Is my résumé kept?", "Why only text PDFs?"])
        self.assertIn('<ol class="trail3" aria-label="What happens next">', page)
        for step in ("We read it", "You pick how wide", "We sweep and rank"):
            self.assertIn(step, page)
        self.assertIn('<div class="desk" data-desk aria-hidden="true">', page)

    def test_the_limit_is_still_read_from_the_app(self):
        page = " ".join(content(self.page()).split())
        self.assertIn("PDFs only, up to 15 MB in total.", page)

    def test_the_picker_compacts_and_counts_what_is_left(self):
        """The drop zone shrinks to a line once something is chosen, is not drawn
        when no place is left, and the count is said as a sentence."""
        body = self.page()
        self.assertIn(":class=\"{ over: over, compact: files.length }\"", body)
        self.assertIn('x-show="files.length < room"', body)
        self.assertIn("'Add another PDF — ' + (room - files.length) + ' more fit'", body)
        self.assertIn("files.length + ' of ' + room + ' selected.'", body)
        self.assertIn("' You can add ' + (room - files.length) + ' more.'", body)
        self.assertIn("Remove one to add another.", body)
        # The list is ruled rows; each way out names its file.
        self.assertIn('class="picked-row"', body)
        self.assertIn(":aria-label=\"'Remove ' + f.name\"", body)
        self.assertNotIn('class="tag">PDF', body)
        # And the server-rendered copy, before any script runs, is the old one.
        self.assertIn("Drop up to 3 résumés here, or click to choose PDFs", body)


# ===========================================================================
class TheList(Batch):
    """The résumés, as ruled rows."""

    def test_a_row_is_a_name_a_file_and_a_state(self):
        with u1.fixed_ids("a" * 16):
            self.send(("ada", "backend_resume.pdf"))
        a = self.ids()[0]
        row = Row(self.page(), 1)
        # Not named yet: the file stands in for the name, once.
        self.assertIn('class="is-file" title="backend_resume.pdf"', row.html)
        self.assertEqual(row.html.count('class="file-head"'), 1)
        self.assertNotIn('<p class="file"', row.html)
        self.assertEqual(row.status(), ("waiting", "Not read yet"))
        self.assertIn('<span class="rank" aria-hidden="true">01</span>', self.page())
        # Named: the name is the heading and the file is the line under it.
        self.assertEqual(self.act(a, "rename", name="Backend Engineer").status_code, 303)
        row = Row(self.page(), 1)
        self.assertIn('</span>Backend Engineer</h2>', row.html)
        self.assertIn('<p class="file" title="backend_resume.pdf">', row.html)
        self.assertNotIn("is-file", row.html)
        # The name a screen reader hears has the place in it.
        self.assertIn('<span\n                      class="visually-hidden">Résumé 1: </span>', row.html)

    def test_review_names_each_resume_and_a_rename_there_comes_back_there(self):
        """The engine's label is a guess (three backend résumés all read "Back End Developer"), so Review offers the
        same Rename as this list; from there it lands back on Review, under the new name."""
        self.send(("ada", "backend_resume.pdf"), ("bhaskar", "mern_resume.pdf"))
        a, b = self.ids()
        review = self.client.get("/review").get_data(as_text=True)
        for n, tid in ((1, a), (2, b)):
            self.assertIn(f'<input type="hidden" name="track" value="{tid}">\n            <input type="hidden" name="back" value="review">', review)
            self.assertIn(f'<summary>Rename<span class="visually-hidden"> résumé {n}</span></summary>', review)
        r = self.act(b, "rename", name="MERN Full Stack", back="review")
        self.assertEqual((r.status_code, r.headers["Location"]), (303, "/review"))
        self.assertIn("</span>MERN Full Stack</h2>", self.client.get("/review").get_data(as_text=True))
        # From the list it still comes back to the list.
        self.assertEqual(self.act(a, "rename", name="Backend").headers["Location"], "/")

    def test_state_is_a_shape_and_a_word_for_each_of_six(self):
        """The review screen's shapes, here. Never colour alone."""
        self.send("ada", "bhaskar", "chen")
        a, b, c = self.ids()
        self.assertEqual(Row(self.page(), 1).status(), ("waiting", "Not read yet"))
        self.client.post(f"/derive?track={a}")
        self.assertEqual(Row(self.page(), 1).status(), ("ready", "Ready to review"))
        self.client.post(f"/review?track={a}", data={})
        self.assertEqual(Row(self.page(), 1).status(), ("reviewed", "Reviewed"))
        self.act(a, "deselect")
        left = Row(self.page(), 1)
        self.assertEqual(left.status(), ("out", "Left out"))
        self.assertIn("Not in this search.", left.html)
        self.failing.add(TEXT_OF["chen"])
        self.client.post(f"/derive?track={c}")
        self.assertEqual(Row(self.page(), 3).status(), ("failed", "Couldn't finish"))

    def test_the_actions_are_grouped_and_remove_is_set_apart(self):
        self.send("ada", "bhaskar", "chen")
        page = self.page()
        second = Row(page, 2).html
        second = second[second.index('class="row-actions"'):]
        groups = re.findall(r'<span class="(a-[a-z]+)">', second)
        self.assertEqual(groups, ["a-main", "a-state", "a-arrange", "a-danger"])
        # Review is the outline; every other action is a word; Remove is the
        # one in the error colour, alone in its group. In or out of the search
        # is beside the first action, so it is in the same place on every row.
        self.assertRegex(second, r'<a class="secondary" href="/review\?track=\w+">Review')
        self.assertEqual(re.findall(r'<button class="([^"]*)"', second),
                         ["tertiary", "tertiary", "tertiary", "tertiary danger"])
        danger = second[second.index('class="a-danger"'):]
        self.assertIn('value="remove">Remove<span', danger)
        self.assertNotIn("Leave out", danger)
        # First has no Move up, last has no Move down; both still have Remove.
        self.assertNotIn(">Move up<", Row(page, 1).html)
        self.assertNotIn(">Move down<", Row(page, 3).html)
        for n in (1, 2, 3):
            self.assertIn(">Remove<span", Row(page, n).html)

    def test_a_reviewed_row_offers_edit_as_a_word_like_the_review_screen(self):
        with self.as_browser(self.browser()):
            self.add("ada")
            self.send("bhaskar")
            first = Row(self.page(), 1).html
            self.assertRegex(first, r'<a class="tertiary" href="/review\?track=\w+">Edit')
            self.assertNotIn('class="secondary"', first[first.index('class="row-actions"'):])
            # Still to review: the outline.
            self.assertRegex(Row(self.page(), 2).html, r'<a class="secondary" href="/review\?track=\w+">Review')

    def test_the_steps_are_for_someone_who_has_not_started(self):
        self.assertIn('<ol class="trail3" aria-label="What happens next">', self.page())
        self.send("ada")
        page = self.page()
        self.assertNotIn("What happens next", page)
        self.assertNotIn('class="trail3"', page)
        # The desk stays, alone in the rail (test_a4_upload.TestTheListOfResumes).
        self.assertEqual(page.count('class="desk" data-desk'), 1)
        # What it costs and what is kept are still said, in the peeks under the add form (A4).
        self.assertIn('<span class="peek-label">Is it free?</span>', page)
        self.assertIn('<span class="peek-label">Is my résumé kept?</span>', page)
        self.assertNotIn('<h2 class="label free">Quick Sweep</h2>', page)
        self.assertNotIn("Nothing is kept", page)

    def test_a_refused_rename_opens_its_row_on_what_was_typed(self):
        self.send("ada", "bhaskar")
        a, b = self.ids()
        self.act(b, "rename", name="Platform")
        page = self.act(a, "rename", name="platform").get_data(as_text=True)
        self.assertIn("Another résumé already has that name", page)
        first, second = Row(page, 1).html, Row(page, 2).html
        self.assertIn('<details class="rename" open>', first)
        self.assertIn('value="platform" maxlength="40" required aria-invalid="true"', first)
        # Only that row; the other keeps its door shut and its own name.
        self.assertIn('<details class="rename">', second)
        self.assertNotIn("aria-invalid", second)
        # Nothing was saved.
        self.assertEqual([t["name"] for t in self.tracks()], ["Résumé 1", "Platform"])

    def test_a_left_out_row_offers_include_and_keeps_review_quiet(self):
        self.send("ada", "bhaskar")
        a = self.ids()[0]
        self.act(a, "deselect")
        row = Row(self.page(), 1).html
        self.assertRegex(row, r'<button class="secondary" type="submit" name="do" value="select">Include')
        self.assertRegex(row, r'<a class="tertiary" href="/review\?track=\w+">Review')
        self.assertNotIn("Leave out", row)

    def test_rename_is_a_door_that_works_without_a_script(self):
        self.send("ada")
        row = Row(self.page(), 1).html
        door = re.search(r'<details class="rename">(.*?)</details>', row, re.S).group(1)
        self.assertIn("<summary>Rename", door)
        self.assertRegex(door, r'<input name="name" value="Résumé 1" maxlength="40" required>')
        self.assertIn('name="do" value="rename"', door)
        self.assertIn("Name for résumé 1", door)


TEXT_OF = u1.TEXT


class OnePrimary(Batch):
    """One primary action per state of the page; a list can have none."""

    def test_each_state(self):
        # Nothing yet: the read button.
        self.assertEqual(len(primaries(self.page())), 1)
        # Some waiting, room left: still the read button (nothing else moves on).
        self.send("ada")
        body = self.page()
        self.assertEqual(len(primaries(body)), 1)
        self.assertIn('<button class="primary" type="submit" :disabled="sent"', body)
        # Three waiting: no room, no way on yet. Review is an outline on each.
        self.send("bhaskar", "chen")
        self.assertEqual(primaries(self.page()), [])
        # One reviewed with room left: the way on is the primary and adding
        # another résumé is the outline beside it.
        with self.as_browser(self.browser()):
            self.add("ada")
            body = self.page()
            self.assertEqual(primaries(body), ['class="primary"'])
            self.assertIn("Continue to job search", body)
            self.assertIn('<button class="secondary" type="submit" :disabled="sent"', body)
        # Three reviewed: the way on, and no add area at all.
        with self.as_browser(self.browser()):
            self.free("ada", "bhaskar", "chen")
            body = self.page()
            self.assertEqual(len(primaries(body)), 1)
            self.assertIn("Continue to job search", body)


class Capacity(Batch):
    """What is left is said truthfully, from none to three."""

    def test_zero_one_two_three(self):
        for whos, heading, file_input in (
                ((), "Add up to 3 résumés", True),
                (("ada",), "Add up to 2 more résumés", True),
                (("ada", "bhaskar"), "Add another résumé", True),
                (("ada", "bhaskar", "chen"), None, False)):
            with self.subTest(n=len(whos)), self.as_browser(self.browser()):
                if whos:
                    self.send(*whos)
                body = self.page()
                page = content(body)
                self.assertEqual(page.count('type="file"'), 1 if file_input else 0)
                self.assertEqual(re.findall(r"<h2>(Add[^<]*)</h2>", page), [heading] if heading else [])
                if whos:
                    self.assertIn(f"{len(whos)} of 3 added.", page)
                if not file_input:
                    self.assertNotIn("Add another", page)
                    self.assertNotIn('class="drop', page)
                    self.assertIn("A search takes up to 3 résumés. Remove one to add another.",
                                  " ".join(page.split()))
                # Never more than three rows.
                self.assertLessEqual(page.count('<li class="resume"'), 3)

    def test_one_place_left_is_the_one_file_picker_and_the_drop_zone_hides_once_chosen(self):
        self.send("ada", "bhaskar")
        body = self.page()
        self.assertIn('x-show="!file"', body)
        self.assertIn("Replace file", body)
        self.assertNotIn("multiple", re.search(r'<input type="file"[^>]*>', body).group(0))


class ErrorsStayOnThePage(Batch):
    def test_a_batch_problem_is_named_above_the_list(self):
        r = self.send("ada", (b"GIF89a-not-a-pdf", "scan.pdf"))
        self.assertIn(r.status_code, (302, 303))
        body = self.page()
        self.assertEqual(self.report(body)[0].startswith("Could not add scan.pdf"), True)
        # Above the rows, across the page, and the list is still there.
        self.assertLess(body.index('class="error"'), body.index('<ol class="ledger manage"'))
        self.assertNotIn('style="margin: 0; padding-left: 1.2em"', body)


# ===========================================================================
def configure(free, **state):
    """The public Configure page for a free or a paid session."""
    app = sp.make_app(free=free, **state)
    return app, app.test_client().get("/configure").get_data(as_text=True)


def names(body):
    start = body.index('<form class="split"')
    form = body[start:body.index("</form>", start)]
    return sorted(set(re.findall(r'<(?:input|select|textarea)\b[^>]*\bname="([^"]+)"', form)))


class Configure(unittest.TestCase):
    def test_every_control_keeps_its_name(self):
        _, free = configure(True)
        _, paid = configure(False)
        self.assertEqual(names(free), ["avoid", "locations", "max_age_days", "min_comp_usd", "scope"])
        # T2: the ticket's stub posts the price it shows (quoted_total) for /run to hold the Sweep to
        self.assertEqual(names(paid), sorted(["avoid", "locations", "max_age_days", "max_results",
                                              "min_comp_usd", "quoted_total", "scope", "sites_present"]
                                             + [f"site_{s}" for s in app_module.paid_sites()]))

    def test_groups_are_ruled_rows_not_panels(self):
        for free in (True, False):
            body = configure(free)[1]
            left = body[body.index('<div class="settings">'):body.index("<aside")]
            with self.subTest(free=free):
                self.assertGreaterEqual(left.count('class="setting"'), 3)
                for box in ('class="panel', 'class="inset', 'class="disclosure', "panel disclosure"):
                    self.assertNotIn(box, left)
                # The one boxed thing beside the form is the summary (Quick) or, since T2, the plan ticket (Deep).
                self.assertEqual(body.count('class="panel summary-panel"'), 1 if free else 0)
                self.assertEqual(body.count('class="pticket"'), 0 if free else 1)

    def test_the_form_is_the_same_form(self):
        """The class the suite and the script know it by, its method, and the
        single Alpine scope that every control reads."""
        for free in (True, False):
            body = configure(free)[1]
            tag = re.search(r'<form class="split"[^>]*>', body, re.S).group(0)
            self.assertIn('method="post"', tag)
            self.assertIn("x-data='{ scope:", tag)
            self.assertEqual(len(re.findall(r"\bpicked:", tag)), 1)

    def test_advanced_is_a_ruled_door_closed_by_default_and_open_when_it_matters(self):
        app, body = configure(True)
        self.assertRegex(body, r'<details class="advanced">')
        self.assertIn("using defaults", body)
        client = app.test_client()
        # Customised: open, and says so.
        client.post("/configure", data=sp.form(max_age_days="30"))
        body = client.get("/configure").get_data(as_text=True)
        self.assertRegex(body, r'<details class="advanced" open>')
        self.assertIn("customised", body)
        # A refused value: the door is open on the field that is wrong, although
        # nothing was saved and the state is still the defaults.
        app, _ = configure(True)
        answer = app.test_client().post("/configure", data=sp.form(avoid="bad%term"))
        self.assertIn(answer.status_code, (200, 400))
        body = answer.get_data(as_text=True)
        self.assertRegex(body, r'<p class="error"( role="alert")?>')
        self.assertRegex(body, r'<details class="advanced" open>')

    def test_what_changes_the_cost_says_so_in_words_and_a_filter_does_not(self):
        body = " ".join(configure(False)[1].split())
        for title in ("Where Sweep searches", "Locations", "Jobs per search"):
            self.assertRegex(body, re.escape(title) + r' <span class="affects">Affects cost</span>', title)
        for title in ("How recent", "Minimum salary", "Words or skills to rank lower",
                      "Which jobs should Sweep include?"):
            self.assertNotRegex(body, re.escape(title) + r'[^<]*<span class="affects"', title)
        # A free sweep has nothing to price, so nothing says it does.
        free = " ".join(configure(True)[1].split())
        self.assertNotIn("Affects cost", free)
        self.assertNotIn('name="max_results"', free)

    def test_paid_and_free_are_told_apart_beside_the_form(self):
        _, paid = configure(False)
        summary = paid[paid.index('class="pticket"'):]       # T2: Deep's aside is the plan ticket
        self.assertIn("Estimated cost", summary)
        self.assertIn('class="numeral"', summary)
        self.assertIn("<dt>Boards</dt>", summary)
        self.assertIn("Nothing is charged until you start.", summary)
        _, free = configure(True)
        summary = free[free.index('class="panel summary-panel"'):]
        self.assertNotIn("Estimated cost", summary)
        self.assertNotIn("headline-figure", summary)
        self.assertIn("Free — no account needed and nothing to pay.", summary)
        self.assertIn('class="tag free-tag"', summary)

    def test_over_the_credit_the_figure_says_so_and_the_price_check_pin_is_kept(self):
        """The figure takes the error colour with a shape beside the sentence; the
        binding the suite pins on the well is still exactly that."""
        body = configure(False)[1]
        self.assertIn(''':class="stale && 'updating'"''', body)
        self.assertIn(''':class="{ over: est.over_cap, updating: stale }" x-text="'$' + est.total.toFixed(2)"''', body)
        css = (pathlib.Path(app_module.__file__).parent / "static" / "sweep.css").read_text()
        self.assertIn("color: var(--over)", re.search(r"\.summary-panel \.headline-figure \.numeral\.over \{([^}]*)\}", css).group(0))
        self.assertIn('content: "!"', css[css.index(".summary-panel .headline-figure p.over:not(.numeral)::before"):][:200])

    def test_one_primary_and_it_is_the_forms_submit(self):
        for free in (True, False):
            body = configure(free)[1]
            with self.subTest(free=free):
                # T2: Deep's ticket has the Start and, behind its coupons, two more (Save and add a key, Start what fits): shown only
                # over the credit and only once a coupon is picked (x-show="pick === ..."), so one at a time.
                self.assertEqual(len(primaries(body)), 3 if not free else 1)
                gated = re.findall(r'<button class="primary[^"]*"[^>]*x-show="pick === ', content(body), re.S)
                self.assertEqual(len(gated), 0 if free else 2)
                self.assertRegex(content(body), r'<button class="primary big" type="submit"')

    def test_the_depth_stepper_is_not_inside_a_label(self):
        """A label around two buttons and a field forwards a click on its text to
        the first of them: the minus."""
        body = configure(False)[1]
        for label in re.findall(r"<label\b[^>]*>(.*?)</label>", body, re.S):
            self.assertNotIn('class="stepper"', label)
        self.assertIn('class="stepper"', body)

    def test_the_scope_is_a_labelled_group_and_the_fields_are_described(self):
        body = configure(False)[1]
        self.assertIn('role="radiogroup" aria-labelledby="scope-h"', body)
        self.assertIn('id="scope-h"', body)
        for field, why in (("max_age_days", "age-why"), ("min_comp_usd", "pay-why"),
                           ("avoid", "avoid-why"), ("max_results", "depth-why")):
            tag = re.search(r'<(?:input|select)\b[^>]*name="%s"[^>]*>' % field, body).group(0)
            self.assertIn(f'aria-describedby="{why}"', tag)
            self.assertIn(f'id="{why}"', body)

    def test_the_local_console_shares_the_rows_and_keeps_its_marks(self):
        """The same template for the operator: same rows, and the asterisk the
        suite has always pinned directly after each heading."""
        app = app_module.create_app(
            state={"profile": "prefs_probe", "derived": copy.deepcopy(sp.DERIVED), "cap_usd": 25.0},
            extract=lambda p: "x", derive=lambda t, p: copy.deepcopy(sp.DERIVED),
            check_token=lambda t: (25.0, None),
            fetch_plan=lambda name: dict(sp.PAID_PLAN, profile=name),
            output_dir=tempfile.mkdtemp(), env_path=tempfile.mktemp())
        app.config.update(TESTING=True)
        app.write_profile = lambda n, src: None    # never a file in the repo's profiles/
        body = app.test_client().get("/configure").get_data(as_text=True)
        flat = " ".join(body.split())
        for heading in ("Sources", "Which jobs should Sweep include?", "Locations", "Results per search"):
            self.assertRegex(flat, re.escape(heading) + r'<span class="costs"')
        for heading in ("Pay floor", "Rank these lower"):
            self.assertIn(f'>{heading}</h2>', flat.replace("> ", ">").replace(" <", "<"))
        self.assertEqual(body.count('class="setting"'), 7)
        self.assertNotIn("<details", content(body).split("<aside")[0])


class TheFrontDoorLocally(unittest.TestCase):
    def test_the_console_front_door_has_one_heading_and_no_second_mark(self):
        app = app_module.create_app(state={}, extract=lambda p: "x", derive=lambda t, p: {})
        app.config.update(TESTING=True)
        body = app.test_client().get("/").get_data(as_text=True)
        self.assertEqual(body.count('class="mark"'), 1)
        self.assertIn("<h1>Sweep</h1>", body)
        self.assertIn("<h2>Point it at your résumé</h2>", body)
        self.assertIn("Job search you can meter.", body)
        self.assertIn("Nothing is charged yet.", body)
        self.assertEqual(len(primaries(body)), 1)
        self.assertEqual(body.count("not read yet"), 3)


if __name__ == "__main__":
    unittest.main()
