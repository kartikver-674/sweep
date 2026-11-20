"""The unified review: two or three résumés on one page, read one after
another while the visitor reviews the ones already read.

The page's script asks POST /derive for JSON (read_next): the server picks
the next résumé in the search — not read, not being read, not failed — and
claims it under the parse lock in the same step, reads it through the one
metered path, and answers read / failed / limited / busy / idle. So reads
never overlap (two tabs included), each costs one attempt, a failure waits
for a deliberate Try again, and a résumé left out or removed is never read.
A read writes only its own track's fields, so a review saved meanwhile
survives. GET /review never reads anything.

The P4-U1 harness (sealed env, the real worker on loopback, the real engine
dry run at Confirm), with a model stub that can be held mid-call. No model,
provider or external network.
"""
import copy
import html
import os
import pathlib
import re
import subprocess
import threading
import time
import unittest

from sweep.tests import test_batch_upload as b1
from sweep.tests import test_multi_render as r1
from sweep.tests import test_multi_setup as u1
from sweep.tests.test_one_track_goldens import derived_for
from sweep.tests.test_worker_link import render_app

setUpModule, tearDownModule = r1.setUpModule, r1.tearDownModule
TEXT, EDIT, PERSONA, LABEL = u1.TEXT, u1.EDIT, u1.PERSONA, u1.LABEL
# What a card is headed by. Until a résumé is read its label is only the
# placeholder "Résumé N", which says less than the file does, so the file stands
# in for it; once read, the label (the name the visitor may change) heads it.
FILE = {"ada": "Default.pdf", "bhaskar": "MERN.pdf", "chen": "AI.pdf"}
IDS = ["cccccccccccccccc", "aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"]
FORM = re.compile(r'<form method="post" action="/review')


class Unified(b1.Batch):
    """Three résumés uploaded together; the model can be held mid-read."""

    def render(self):
        self.derived_texts, self.failing, self.while_reading = [], set(), None
        self.held, self.inside = {}, {}

        def extract(path):
            with open(path, "rb") as fh:
                who = fh.read()[len(b"%PDF-1.7 "):].decode()
            self.extracted.append(path)
            if self.while_reading:
                self.while_reading()
            return {"blank": "  ", **TEXT}.get(who, who)

        def derive(text, prefs):
            self.derived_texts.append(text)
            if text in self.held:
                self.inside[text].set()
                self.held[text].wait(20)
            if text in self.failing:
                raise RuntimeError("the model did not answer")
            who = next(k for k, v in TEXT.items() if v == text)
            return copy.deepcopy(derived_for(PERSONA[who]))

        self.extracted = []
        return render_app(self.worker.url, check_token=lambda token: (42.0, None),
                          extract=extract, derive=derive)

    def setUp(self):
        super().setUp()
        with u1.fixed_ids(*IDS):
            self.assertEqual(self.send("ada", "bhaskar", "chen").status_code, 302)
        self.a, self.b, self.c = IDS

    # -- gestures --------------------------------------------------------------
    def read(self, client=None):
        r = (client or self.client).post("/derive", headers={"Accept": "application/json"})
        return r.status_code, r.get_json()

    def hold(self, who):
        """The next read of `who` stops inside the model call until let go."""
        self.held[TEXT[who]], self.inside[TEXT[who]] = threading.Event(), threading.Event()
        return self.held[TEXT[who]]

    def reading_in_background(self, who, client=None):
        """A read of `who`, started on another thread and held inside the
        model call; returns (let_go, finish) — finish joins and answers."""
        gate, out = self.hold(who), {}
        worker = threading.Thread(target=lambda: out.update(answer=self.read(client)))
        worker.start()
        self.assertTrue(self.inside[TEXT[who]].wait(10), "the read never reached the model")

        def finish():
            gate.set()
            worker.join(20)
            return out["answer"]
        return gate, finish

    def view(self, track=None, client=None):
        r = (client or self.client).get("/review" + (f"?track={track}" if track else ""))
        self.assertEqual(r.status_code, 200)
        return r.get_data(as_text=True)

    # The shape drawn beside each word (D3): a state is never a colour alone.
    SHAPE = {"Waiting": "waiting", "Reading now": "reading", "Ready to review": "ready",
             "Reviewed": "reviewed", "Couldn't finish": "failed", "Not read yet": "failed",
             "Left out": "out"}

    def cards(self, body):
        """[(n, heading, status, open, text)] for each card, in résumé order
        (the deck puts the others in its side and the open one last in the
        page, so the page's own order is not the setup's). The heading is
        what is SHOWN: the hidden "Résumé N: " a screen reader gets first is
        taken off."""
        out = []
        for m in re.finditer(r'<section class="resume" data-card="(\w+)"'
                             r'( data-open)? aria-labelledby="resume-(\d)">(.*?)</section>',
                             body, re.S):
            head = re.search(r"<h2[^>]*>(.*?)</h2>", m.group(4), re.S)
            state = re.search(r'<span class="status (\w+)">(.*?)</span>', m.group(4), re.S)
            shown = re.sub(r'<span\s+class="visually-hidden">.*?</span>', "", head.group(1), flags=re.S)
            assert f"Résumé {m.group(3)}: " in head.group(1), "the accessible name keeps the number"
            assert self.SHAPE[html.unescape(state.group(2))] == state.group(1), state.group(0)
            out.append((int(m.group(3)), html.unescape(re.sub(r"<[^>]+>", "", shown)),
                        html.unescape(state.group(2)), bool(m.group(2)),
                        html.unescape(m.group(4))))
        return sorted(out, key=lambda c: c[0])

    def banner(self, body):
        # A5: the public banner opens with the eyebrow ("Step 2 · profile check"), before the h1.
        m = re.search(r'id="resumes-banner">\s*(?:<span class="eyebrow">.*?</span>\s*)?<h1>(.*?)</h1>\s*<p class="lede" '
                      r'role="status">(.*?)</p>', body, re.S)
        return html.unescape(m.group(1)), html.unescape(m.group(2))

    def way_on(self, body):
        m = re.search(r'id="resumes-continue">(.*?)</div>\s*</div>', body, re.S)
        text = re.sub(r"<[^>]+>", " ", m.group(1))
        return " ".join(html.unescape(text).replace("Manage your résumés", "").split())

    def review(self, tid, **form):
        return self.client.post(f"/review?track={tid}", data=form)


# ===========================================================================
class Orchestration(Unified):
    """Items 1-11, 15: what the page's script asks, and what the server does."""

    def test_the_upload_lands_on_one_page_reading_nothing_yet(self):
        body = self.view(self.a)
        self.assertEqual([c[:4] for c in self.cards(body)],
                         [(1, "Default.pdf", "Waiting", False), (2, "MERN.pdf", "Waiting", False),
                          (3, "AI.pdf", "Waiting", False)])
        self.assertEqual(self.banner(body), ("Reading your résumés", "0 of 3 ready · Résumé 1 is next"))
        self.assertEqual(self.way_on(body), "Reading 3 résumés…")
        self.assertIn('data-reading="1"', body)
        self.assertIn('<script src="/static/reading.js"></script>', body)
        self.assertEqual(self.client.get("/static/reading.js").status_code, 200)
        self.assertIsNone(FORM.search(body))
        self.assertEqual(self.derived_texts, [], "a GET read something")
        self.assertEqual(self.app.beta_limit.taken(), 0)

    def test_read_one_after_another_in_order_then_idle(self):
        for tid, who in zip(IDS, ("ada", "bhaskar", "chen")):
            self.assertEqual(self.read(), (200, {"state": "read", "track": tid}))
            self.assertEqual(self.derived_texts[-1], TEXT[who])
        self.assertEqual(self.read(), (200, {"state": "idle"}))
        self.assertEqual(self.derived_texts, [TEXT["ada"], TEXT["bhaskar"], TEXT["chen"]])
        self.assertEqual(self.app.beta_limit.taken(), 3)

    def test_a_read_or_reviewed_resume_is_skipped(self):
        self.client.post(f"/derive?track={self.a}")                 # read by its own form
        self.review(self.a)
        self.assertEqual(self.read()[1], {"state": "read", "track": self.b})
        self.assertEqual(self.derived_texts.count(TEXT["ada"]), 1)

    def test_left_out_or_removed_queued_resumes_are_never_read(self):
        self.act(self.b, "deselect", back="review")
        self.act(self.c, "remove", back="review")
        self.assertEqual(self.read()[1], {"state": "read", "track": self.a})
        self.assertEqual(self.read()[1], {"state": "idle"})
        self.assertEqual(self.derived_texts, [TEXT["ada"]])
        self.assertEqual(self.app.beta_limit.taken(), 1)
        # Included again, never read: back in the queue, read once.
        self.act(self.b, "select", back="review")
        self.assertEqual(self.read()[1], {"state": "read", "track": self.b})
        self.act(self.b, "deselect", back="review")
        self.act(self.b, "select", back="review")
        self.assertEqual(self.read()[1], {"state": "idle"})        # read already: not again
        self.assertEqual(self.derived_texts.count(TEXT["bhaskar"]), 1)

    def test_a_failure_is_not_retried_until_try_again(self):
        self.failing.add(TEXT["bhaskar"])
        self.assertEqual(self.read()[1]["state"], "read")
        self.assertEqual(self.read(), (200, {"state": "failed", "track": self.b}))
        self.assertEqual(self.read()[1], {"state": "read", "track": self.c})   # C still read
        self.assertEqual(self.read()[1], {"state": "idle"})                    # B not again
        self.assertEqual(self.derived_texts.count(TEXT["bhaskar"]), 1)
        self.assertEqual(self.app.beta_limit.taken(), 3)
        failed = self.cards(self.view())[1]
        self.assertEqual(failed[2], "Couldn't finish")
        self.assertIn("Couldn't finish reading this résumé.", failed[4])
        self.assertIn("Sweep could not read your résumé just now.", failed[4])  # the fixed sentence
        self.assertIn('value="retry">Try again', failed[4])
        self.assertIn('value="deselect">Leave out', failed[4])
        # Try again: one deliberate click, one more attempt, when it is read.
        self.failing.clear()
        r = self.act(self.b, "retry", back="review")
        self.assertEqual((r.status_code, r.headers["Location"]), (303, "/review"))
        self.assertEqual(self.app.beta_limit.taken(), 3)                       # nothing yet
        self.assertEqual(self.read()[1], {"state": "read", "track": self.b})
        self.assertEqual(self.app.beta_limit.taken(), 4)
        self.assertEqual(self.derived_texts.count(TEXT["bhaskar"]), 2)

    def test_retry_touches_only_a_failed_read(self):
        self.read()
        before = copy.deepcopy(self.tracks())
        for tid in (self.a, self.b):                   # read, and queued
            self.act(tid, "retry", back="review")
        self.assertEqual(self.tracks(), before)

    def test_a_limit_stops_the_reading_without_a_loop(self):
        self.app.beta_limit.per_ip = 2
        self.assertEqual(self.read()[1]["state"], "read")
        self.assertEqual(self.read()[1]["state"], "read")
        status, answer = self.read()
        self.assertEqual((status, answer), (429, {"state": "limited", "track": self.c}))
        self.assertEqual(self.read(), (200, {"state": "idle"}))   # asked again: nothing tried
        self.assertEqual(self.app.beta_limit.taken(), 2)
        self.assertEqual(len(self.derived_texts), 2)
        card = self.cards(self.view())[2]
        self.assertEqual(card[2], "Not read yet")
        # Said once, by the status: the body does not repeat it.
        self.assertEqual(card[4].count("Not read yet"), 1)
        self.assertIn("You've reached today's limit of 2 résumé reads from your network.", card[4])
        self.assertNotIn("Couldn't finish", card[4])
        self.assertIn('value="retry">Try again', card[4])
        self.assertEqual(self.banner(self.view())[1],
                         "2 résumés ready to review. Résumé 3 wasn't read: today's limit "
                         "is reached. Try again, or leave it out to continue.")

    def test_a_page_coming_back_picks_up_where_it_stopped(self):
        self.read()
        body = self.view()
        self.assertEqual(self.cards(body)[0][2:4], ("Ready to review", True))   # opened
        self.assertIn('data-reading="1"', body)
        self.assertEqual(self.read()[1], {"state": "read", "track": self.b})
        # A read whose request died stays "reading" for a while (busy), then
        # counts as failed — and waits for Try again.
        self.track(self.c)["parse"] = {"state": "reading", "at": time.time()}
        self.assertEqual(self.read()[1], {"state": "busy", "track": self.c})
        self.track(self.c)["parse"]["at"] = time.time() - 21 * 60
        self.assertEqual(self.read()[1], {"state": "idle"})
        self.assertEqual(self.cards(self.view())[2][2], "Couldn't finish")
        self.assertEqual(len(self.derived_texts), 2)


class Concurrency(Unified):
    """Items 12-14, 16, 38-40, 47: never two reads, never a lost edit."""

    def test_the_same_resume_asked_twice_is_read_once(self):
        _gate, finish = self.reading_in_background("ada")
        self.assertEqual(self.read(), (200, {"state": "busy", "track": self.a}))
        # The reading screen's own form, the other way in: no second read.
        self.assertEqual(self.client.post(f"/derive?track={self.a}").status_code, 302)
        self.assertEqual(self.client.post(f"/derive?track={self.b}").status_code, 302)
        self.assertEqual(finish(), (200, {"state": "read", "track": self.a}))
        self.assertEqual(self.derived_texts, [TEXT["ada"]])
        self.assertEqual(self.app.beta_limit.taken(), 1)

    def test_two_tabs_are_one_read(self):
        twin = self.app.test_client()
        twin.set_cookie("session", self.client.get_cookie("session").value)
        self.hold("ada")
        gate, answers = threading.Barrier(2), []

        def ask(client):
            gate.wait()
            answers.append(self.read(client)[1]["state"])
        tabs = [threading.Thread(target=ask, args=(c,)) for c in (self.client, twin)]
        for t in tabs:
            t.start()
        self.assertTrue(self.inside[TEXT["ada"]].wait(10))
        time.sleep(0.2)                                   # the other tab has answered
        self.held[TEXT["ada"]].set()
        for t in tabs:
            t.join(20)
        self.assertEqual(sorted(answers), ["busy", "read"])
        self.assertEqual(self.derived_texts, [TEXT["ada"]])
        self.assertEqual(self.app.beta_limit.taken(), 1)
        self.assertEqual(self.cards(self.view(client=twin)), self.cards(self.view()))

    def check_saved_while_b_reads(self, b_fails):
        self.read()                                             # A read
        if b_fails:
            self.failing.add(TEXT["bhaskar"])
        _gate, finish = self.reading_in_background("bhaskar")
        saved = self.review(self.a, **EDIT)
        self.assertEqual((saved.status_code, saved.headers["Location"]), (302, "/review"))
        edited = copy.deepcopy(self.track(self.a))
        self.assertTrue(edited["reviewed"])
        self.assertEqual({w["term"]: w["weight"] for w in edited["derived"]["skill_weights"]}["celery"], 4)
        self.assertNotIn("django", {w["term"] for w in edited["derived"]["skill_weights"]})
        # Saved, B still reading: nothing open, a calm wait.
        body = self.view()
        self.assertIsNone(FORM.search(body))
        self.assertEqual(self.banner(body)[1], "1 of 3 ready · Reading résumé 2")
        state = finish()[1]["state"]
        self.assertEqual(state, "failed" if b_fails else "read")
        self.assertEqual(self.track(self.a), edited, "B's read wrote over A's review")
        self.assertEqual(self.ids(), IDS)
        self.assertEqual(self.track(self.b)["derived"] is None, b_fails)
        self.view()                                             # and a reload shows it

    def test_a_review_saved_while_b_reads_survives_b(self):
        self.check_saved_while_b_reads(b_fails=False)

    def test_a_review_saved_while_b_fails_survives_b(self):
        self.check_saved_while_b_reads(b_fails=True)

    def test_c_left_out_while_b_reads_is_never_read(self):
        self.read()
        _gate, finish = self.reading_in_background("bhaskar")
        self.act(self.c, "deselect", back="review")
        self.assertEqual(finish()[1], {"state": "read", "track": self.b})
        self.assertEqual(self.read()[1], {"state": "idle"})
        self.assertEqual(self.derived_texts, [TEXT["ada"], TEXT["bhaskar"]])

    def test_a_resume_removed_while_it_reads_does_not_come_back(self):
        self.read()
        _gate, finish = self.reading_in_background("bhaskar")
        self.act(self.b, "remove", back="review")
        self.assertEqual(finish()[1]["state"], "read")
        self.assertEqual(self.ids(), [self.a, self.c])
        self.assertNotIn(self.b, self.view())
        self.assertEqual(self.read()[1], {"state": "read", "track": self.c})

    def test_left_out_while_reading_finishes_and_blocks_nothing(self):
        self.read()
        self.review(self.a)
        _gate, finish = self.reading_in_background("bhaskar")
        self.act(self.b, "deselect", back="review")
        self.act(self.c, "deselect", back="review")
        body = self.view()
        self.assertEqual(self.cards(body)[1][2], "Left out")
        self.assertIn("Sweep is finishing reading it", self.cards(body)[1][4])
        self.assertIn('href="/key">Continue to job search', body)
        self.assertEqual(finish()[1]["state"], "read")


class Continue(Unified):
    """Items 16-18, 24, 30: the way on is there once, and only when due."""

    def read_all(self):
        while self.read()[1]["state"] != "idle":
            pass

    def test_every_included_resume_read_and_reviewed(self):
        self.read_all()
        for tid in IDS[:2]:
            self.review(tid)
        body = self.view()
        self.assertEqual(self.way_on(body), "Review 1 résumé to continue")
        self.assertNotIn('href="/key">Continue to job search', body)
        # The last one's own button saves it first, and says so: it never
        # reads as a way past the review (reported on the live page).
        self.assertEqual(self.cards(body)[2][2:4], ("Ready to review", True))
        self.assertIn('Save and continue to job search<span class="go"', body)
        self.assertNotIn('"sent">Continue to job search', body)
        self.assertFalse(self.track(self.c)["reviewed"])
        self.assertEqual(self.client.post("/key/free").headers["Location"], "/review")
        self.assertEqual(self.review(self.c).headers["Location"], "/key")
        self.assertTrue(self.track(self.c)["reviewed"])
        body = self.view()
        self.assertEqual(self.banner(body), ("All résumés reviewed", "Every résumé in this search is ready."))
        self.assertIn('href="/key">Continue to job search', body)
        self.assertNotIn('data-reading="1"', body)

    def test_a_left_out_resume_blocks_nothing(self):
        self.act(self.c, "deselect", back="review")
        self.read_all()
        self.review(self.a)
        self.assertEqual(self.way_on(self.view()), "Review 1 résumé to continue")
        self.review(self.b)
        self.assertIn('href="/key">Continue to job search', self.view())
        self.assertEqual(self.derived_texts, [TEXT["ada"], TEXT["bhaskar"]])


class Screens(Unified):
    """Items 5, 6, 18, 20-23, 42-45, 48-49: each state of the page."""

    FORBIDDEN = ("%", "complete", "✓", "Step ", "Strong résumé", "Weak résumé",
                 "Best résumé", "Poor match")

    def check(self, body, expect, opened=None):
        cards = self.cards(body)
        self.assertEqual([(n, head, status) for n, head, status, _o, _t in cards], expect)
        self.assertEqual([n for n, _h, _s, is_open, _t in cards if is_open],
                         [opened] if opened else [])
        self.assertLessEqual(len(FORM.findall(body)), 1)
        for n, _head, status, is_open, text in cards:
            self.assertEqual(text.count("<h2"), 1 if not is_open else text.count("<h2"))
            self.assertEqual(text.count(f'id="resume-{n}"'), 1)
            self.assertNotIn(IDS[n - 1], re.sub(r'(value|href|action)="[^"]*"', "", text))
            if status == "Waiting":
                self.assertNotIn("bone", text)
                self.assertRegex(text, r"Sweep (reads this next|will read this after résumé \d)\.")
            if status == "Reading now":
                self.assertIn('class="bone', text)
                self.assertIn('aria-hidden="true"', text)
                self.assertIn("experience, the roles to search", text)
            if status == "Reviewed" and not is_open:
                self.assertRegex(text, r"\d+ roles · \d+ skills")
                self.assertIn(">Edit<", text)
                self.assertNotIn('class="tag"', text)
            if status == "Ready to review" and not is_open:
                self.assertIn(">Review<", text)
        # The page's own words: banner, compact cards, the way on — the
        # open card's form is the review screen as it has always been.
        said = self.banner(body) + (self.way_on(body),) + tuple(
            re.sub(r"<[^>]+>", " ", text) for _n, _h, _s, is_open, text in cards if not is_open)
        for word in self.FORBIDDEN:
            for part in said:
                self.assertNotIn(word, part)
        self.assertEqual(body.count("No scraping credit is spent"), 1)

    def reading(self, tid):
        self.track(tid)["parse"] = {"state": "reading", "at": time.time()}

    def test_the_states(self):
        # Headed by the label, which is only a placeholder until a résumé is
        # read: the file stands in for it then (Default.pdf), and after the
        # read the label heads it with the file under it (Backend Engineer).
        B, R, P = LABEL["ada"], LABEL["bhaskar"], LABEL["chen"]
        self.check(self.view(), [(1, "Default.pdf", "Waiting"), (2, "MERN.pdf", "Waiting"),
                                 (3, "AI.pdf", "Waiting")])
        self.reading(self.a)
        self.check(self.view(), [(1, "Default.pdf", "Reading now"), (2, "MERN.pdf", "Waiting"),
                                 (3, "AI.pdf", "Waiting")])
        self.assertEqual(self.banner(self.view())[1], "0 of 3 ready · Reading résumé 1")
        del self.track(self.a)["parse"]
        self.read()
        self.reading(self.b)
        body = self.view()
        self.check(body, [(1, B, "Ready to review"), (2, "MERN.pdf", "Reading now"),
                          (3, "AI.pdf", "Waiting")], opened=1)
        self.assertIn("Save résumé 1", body)
        self.assertIn("Sweep will read this after résumé 2.", self.cards(body)[2][4])
        del self.track(self.b)["parse"]
        self.read()
        self.review(self.a)
        self.reading(self.c)
        body = self.view()
        self.check(body, [(1, B, "Reviewed"), (2, R, "Ready to review"),
                          (3, "AI.pdf", "Reading now")], opened=2)
        self.assertEqual(self.banner(body), ("Reading your résumés", "2 of 3 ready · Reading résumé 3"))
        # While B is open, C coming ready does not open it: its card says so.
        del self.track(self.c)["parse"]
        self.read()
        body = self.view(self.b)
        self.check(body, [(1, B, "Reviewed"), (2, R, "Ready to review"), (3, P, "Ready to review")],
                   opened=2)
        self.assertIn("Looks right, next résumé", body)
        self.assertEqual(self.banner(body), ("Review your résumés",
                         "All résumés are read — review the remaining 2 résumés to continue."))
        self.review(self.b)
        self.review(self.c)
        body = self.view()
        self.check(body, [(1, B, "Reviewed"), (2, R, "Reviewed"), (3, P, "Reviewed")])
        # A reviewed one opens again only when asked to (Edit).
        self.check(self.view(self.a), [(1, B, "Reviewed"), (2, R, "Reviewed"), (3, P, "Reviewed")],
                   opened=1)

    def test_all_ready_opens_the_first_only(self):
        while self.read()[1]["state"] != "idle":
            pass
        body = self.view()
        self.assertEqual([c[2:4] for c in self.cards(body)],
                         [("Ready to review", True), ("Ready to review", False),
                          ("Ready to review", False)])
        self.assertIn("Looks right, next résumé", body)

    def test_one_failed_and_one_left_out(self):
        self.failing.add(TEXT["bhaskar"])
        self.act(self.c, "deselect", back="review")
        self.read()
        self.read()
        body = self.view()
        self.check(body, [(1, LABEL["ada"], "Ready to review"),
                          (2, "MERN.pdf", "Couldn't finish"), (3, "AI.pdf", "Left out")],
                   opened=1)
        self.assertIn('value="select">Include', self.cards(body)[2][4])
        self.assertEqual(self.way_on(body), "Review 1 résumé to continue")
        self.review(self.a)
        self.assertEqual(self.way_on(self.view()), "Try again or leave out résumé 2 to continue")
        self.act(self.b, "deselect", back="review")
        self.assertIn('href="/key">Continue to job search', self.view())

    def test_a_file_name_is_secondary_once_there_is_a_label(self):
        # Unread: the label is a placeholder, so the file is the heading and
        # is not said twice.
        body = self.view()
        self.assertEqual(self.cards(body)[0][1], "Default.pdf")
        self.assertNotIn('<p class="file"', self.cards(body)[0][4])
        # Read: the label heads the card; the file is the line under it, in
        # full for a screen reader and cut in the middle for the eye.
        self.read()
        card = self.cards(self.view())[0]
        self.assertEqual(card[1], LABEL["ada"])
        self.assertIn('<p class="file" title="Default.pdf"><span class="visually-hidden">'
                      'Default.pdf</span>', card[4])

    def test_a_long_file_name_is_cut_in_the_middle_and_escaped(self):
        self.read()
        # (no "/": track_view takes the basename, and "</b>" has one)
        name = 'quarterly <b>"résumé" & co ' + "x" * 40 + "_final.pdf"
        self.track(self.a)["resume_name"] = name
        raw = re.search(r'<p class="file".*?</p>', self.view(), re.S).group(0)
        # Escaped in the page, not just in the test's reading of it.
        self.assertNotIn("<b>", raw)
        self.assertNotIn(" & co", raw)
        self.assertIn("&lt;b&gt;", raw)
        head = re.search(r'file-head" aria-hidden="true">(.*?)</span>', raw, re.S).group(1)
        tail = re.search(r'file-tail" aria-hidden="true">(.*?)</span>', raw, re.S).group(1)
        self.assertEqual(html.unescape(tail), name[-12:])
        self.assertTrue(html.unescape(head).startswith('quarterly <b>"résumé" & co'))
        self.assertEqual(html.unescape(head) + html.unescape(tail), name)
        # The whole name is what a screen reader is given.
        whole = re.search(r'<span class="visually-hidden">(.*?)</span>', raw, re.S).group(1)
        self.assertEqual(html.unescape(whole), name)

    def main(self, body):
        return body.split("<main>")[1].split("</main>")[0]       # the page's content: a dialog after it is not

    def test_unsaved_edits_are_guarded_on_the_open_résumé_and_nothing_is_drawn_when_none_is_open(self):
        """D7C: the open card's form is the editor (data-editor) and carries the unsaved-changes guard; switching to another
        résumé is a link or a button on this page, which dirty.js holds while there is something unsaved. A page with no card
        open has no editor, so nothing to guard and nothing drawn."""
        from sweep.tests.test_dirty_guard import guard_parts
        while self.read()[1]["state"] != "idle":
            pass
        for tid in (self.a, self.b, self.c):
            dialog, marked, loaded = guard_parts(self.view(tid))
            self.assertTrue(dialog and marked and loaded, tid)
            self.assertEqual(self.view(tid).count("data-editor"), 1, "one editor: the open card's")
        for tid in (self.a, self.b, self.c):
            self.review(tid)
        self.assertEqual(guard_parts(self.view()), (None, False, False), "everything reviewed, nothing open")
        # the ways off an open editor are the ones the guard holds: a link to another résumé, the way on
        body = self.view(self.a)
        self.assertIn('href="/review?track=', body)
        self.assertIn('href="/key"', body)

    def test_one_primary_action_per_view(self):
        """The decision is the loudest thing: the open résumé's Save. A ready
        résumé's Review is an outline, management is underlined words, and the
        way on leaves the primary to the Save while a résumé is open."""
        while self.read()[1]["state"] != "idle":
            pass
        main = self.main(self.view())
        self.assertEqual(main.count('class="primary"'), 1)
        self.assertIn('<button class="primary" type="submit"', main)
        self.assertEqual(main.count('class="secondary" href="/review?track='), 2)
        self.assertIn('name="do" value="deselect">Leave out', main)
        self.assertIn('class="tertiary" type="submit" name="do" value="deselect"', main)
        for tid in (self.a, self.b, self.c):
            self.review(tid)
        # Nothing open, everything reviewed: the way on is the one primary.
        main = self.main(self.view())
        self.assertEqual(main.count('class="primary"'), 1)
        self.assertIn('<a class="primary" href="/key">Continue to job search', main)
        self.assertEqual(main.count('class="tertiary" href="/review?track='), 3)
        # Editing one of them (all still reviewed): its Save is the primary,
        # and leaving without saving is an outline.
        main = self.main(self.view(self.a))
        self.assertEqual(main.count('class="primary"'), 1)
        self.assertIn('<a class="secondary" href="/key">Continue to job search', main)

    def test_the_readings_internal_notes_are_never_shown_to_a_visitor(self):
        """Render runs the local engine, so the notes are how the profile was arrived at: field names, the
        corrections the router made, the terms it dropped. They are written for whoever checks the derivation,
        not for the person it is about (D7C; this page used to show them behind a disclosure, verbatim). They are
        kept on the profile, and the operator's console still shows them. The visitor is told what was read."""
        self.read()
        body = self.view()
        notes = self.track(self.a)["derived"]["notes"]
        self.assertTrue(notes)
        flat = html.unescape(body)
        self.assertNotIn(notes, flat)
        self.assertNotIn("Worth knowing", body)
        self.assertNotIn("Technical notes on how this was read", body)
        self.assertNotIn('class="notes"', body)
        self.assertEqual(self.track(self.a)["derived"]["notes"], notes, "kept, never shown")

    def test_a_long_file_name_standing_in_as_the_heading_is_cut_not_broken(self):
        """Unread, the file is the heading (the label is only a placeholder), in
        the largest type on the row. It is cut in the middle, exactly as the
        secondary line is, so it never breaks mid-word; a screen reader gets all
        of it."""
        name = "kartik_verma_fullstack_payments_fintech_resume_final_v7.pdf"
        self.track(self.a)["resume_name"] = name
        raw = re.search(r'<h2 id="resume-1".*?</h2>', self.view(), re.S).group(0)
        self.assertIn('class="is-file"', raw)
        self.assertEqual(html.unescape(re.search(r'title="(.*?)"', raw).group(1)), name)
        head = re.search(r'file-head" aria-hidden="true">(.*?)</span>', raw, re.S).group(1)
        tail = re.search(r'file-tail" aria-hidden="true">(.*?)</span>', raw, re.S).group(1)
        self.assertEqual(head + tail, name)
        self.assertEqual(tail, name[-12:])
        self.assertIn(f'<span class="visually-hidden">{name}</span>', raw)

    def test_the_remove_word_is_a_control_with_its_own_chalk_focus_ring(self):
        """The one focus ring drawn by hand: the checkbox behind "Remove" is
        invisible, so the word takes the ring, in chalk like every other."""
        import pathlib
        from sweep import app as app_module
        css = (pathlib.Path(app_module.__file__).parent / "static" / "sweep.css").read_text()
        self.assertRegex(css, r"\.remove input:focus-visible \+ \.remove-ui \{\s*outline: 2px solid var\(--chalk\)")
        # ...and the cell that holds it is not the upload screen's drop zone.
        self.assertNotIn("td.drop", css)
        self.read()
        # A5: the public review draws the control inside a skill's tune panel, not in a table cell.
        self.assertIn('<div class="tune-pop" id="tune-1">', self.view())
        self.assertIn('<label class="remove">', self.view())
        self.assertNotIn('<td class="del">', self.view())

    def test_the_page_sends_nothing_built_for_the_engine(self):
        while self.read()[1]["state"] != "idle":
            pass
        body = self.view()
        for word in u1.ENGINE_WORDS[:4] + ("TRACKS", "plan_hash", "run_id", "track_evals"):
            self.assertNotIn(word, body)


class Script(unittest.TestCase):
    """reading.js against a scripted server (sweep/tests/reading_test.js):
    one ask at a time, a real wait while busy, no ask after idle or a limit
    refusal, and the open card never replaced."""

    def test_the_reader(self):
        if not b1.NODE:
            self.skipTest("node not installed")
        run = subprocess.run([b1.NODE, os.path.join(os.path.dirname(__file__), "reading_test.js")],
                             capture_output=True, text=True, env={"PATH": os.path.dirname(b1.NODE)})
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


class OneResume(u1.Setup):
    """Item 53: one résumé keeps its own reading screen and review."""

    def test_one_resume_is_the_page_it_always_was(self):
        self.upload("ada")
        reading = self.client.get("/review").get_data(as_text=True)
        self.assertIn('id="derive-now"', reading)
        self.assertNotIn("data-resumes", reading)
        # A JSON ask with one résumé is the ordinary form post.
        r = self.client.post("/derive", headers={"Accept": "application/json"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].startswith("/review"))
        page = self.client.get("/review").get_data(as_text=True)
        self.assertNotIn("data-resumes", page)
        self.assertIn("Continue to job search", page)
        self.assertEqual(self.client.post("/review", data={}).headers["Location"], "/key")


class Flow(Unified):
    """Items 50-51: the A/B/C journey, and A-ok / B-fails / C-ok."""

    def test_a_b_c_reviewed_while_the_next_is_read(self):
        self.assertEqual(self.read()[1]["track"], self.a)
        body = self.view()                                     # A opened as it came ready
        self.assertEqual(self.cards(body)[0][2:4], ("Ready to review", True))
        _gate, finish = self.reading_in_background("bhaskar")
        self.assertEqual(self.review(self.a, **EDIT).headers["Location"], "/review")
        edited = copy.deepcopy(self.track(self.a)["derived"])
        self.assertEqual(finish()[1], {"state": "read", "track": self.b})
        body = self.view()
        self.assertEqual([c[2:4] for c in self.cards(body)],
                         [("Reviewed", False), ("Ready to review", True), ("Waiting", False)])
        self.assertEqual(self.read()[1], {"state": "read", "track": self.c})
        self.assertEqual(self.review(self.b).headers["Location"], "/review")
        self.assertIn("Save and continue to job search", self.view())
        self.assertEqual(self.review(self.c).headers["Location"], "/key")
        self.assertEqual(self.derived_texts, [TEXT["ada"], TEXT["bhaskar"], TEXT["chen"]])
        self.assertEqual(self.app.beta_limit.taken(), 3)
        self.assertEqual(self.track(self.a)["derived"], edited)
        self.assertEqual(self.client.post("/key/free").status_code, 302)
        self.assertEqual(self.client.post("/configure", data=r1.FORMS["india"]).status_code, 303)
        self.confirm()
        plan = self.last_plan()
        self.assertEqual(sorted(plan), ["free_only", "owner", "prefs", "tracks"])
        self.assertEqual([t["id"] for t in plan["tracks"]], IDS)

    def test_b_fails_and_is_left_out(self):
        self.failing.add(TEXT["bhaskar"])
        states = [self.read()[1]["state"] for _ in range(4)]
        self.assertEqual(states, ["read", "failed", "read", "idle"])
        self.review(self.a)
        self.review(self.c)
        body = self.view()
        self.assertEqual(self.way_on(body), "Try again or leave out résumé 2 to continue")
        self.assertEqual(self.client.post("/key/free").headers["Location"], "/review")
        self.act(self.b, "deselect", back="review")
        self.assertIn('href="/key">Continue to job search', self.view())
        self.assertEqual(self.client.post("/key/free").status_code, 302)
        self.assertEqual(self.client.post("/configure", data=r1.FORMS["india"]).status_code, 303)
        self.confirm()
        self.assertEqual([t["id"] for t in self.last_plan()["tracks"]], [self.a, self.c])
        self.assertEqual(self.derived_texts.count(TEXT["bhaskar"]), 1)


class Deck(Unified):
    """V2 F1: with a résumé open for editing the ledger is a deck: a sheet per résumé in the search (the front one the open
    résumé), the pips and the count, the other résumés as rows beside it, and "Leave this résumé out" in the open card's bar.
    Public only (the unified review is); with none open, the ledger is what it was."""

    def setUp(self):
        super().setUp()
        while self.read()[1]["state"] != "idle":
            pass

    SIDE = re.compile(r'<aside class="deck-side" aria-label="Your résumés">(.*?)</aside>', re.S)

    def side(self, body):
        return self.SIDE.search(body).group(1)

    def editor(self, body):
        return re.search(r"<form[^>]*\bdata-editor\b[^>]*>.*?</form>", body, re.S).group(0)

    def test_the_open_page_is_a_deck_with_a_sheet_per_resume(self):
        body = self.view(self.a)
        self.assertEqual(body.count('<div class="ledger deck-on">'), 1)
        side = self.side(body)
        self.assertEqual(re.findall(r'<div class="deck-sheet (p\d)"', side), ["p0", "p1", "p2"])
        front = re.search(r'<div class="deck-sheet p0" data-deck-front>(.*?)</div>', side, re.S).group(1)
        self.assertEqual(body.count("data-deck-front"), 1)
        self.assertIn(f'<b class="deck-name">{LABEL["ada"]}</b>', front)
        self.assertIn("Checking now", front)
        self.assertRegex(front, r'<span class="deck-xp">[^<]+ of experience</span>')
        self.assertIn("Default.pdf", front)
        self.assertNotIn("Checking now", re.sub(r'<div class="deck-sheet p0".*?</div>', "", side, flags=re.S))
        self.assertIn('<div class="deck" aria-hidden="true">', side)
        # The pile is decoration: the words are the rows, which are the cards, once each.
        self.assertEqual(sorted(re.findall(r'data-card="(\w+)"', body)), sorted(IDS))
        self.assertEqual(re.findall(r'data-card="(\w+)"', side), [self.b, self.c])
        self.assertLess(body.index("deck-side"), body.index(" data-open "))
        self.assertNotIn("data-open", side)

    def test_the_pips_and_the_count(self):
        side = self.side(self.view(self.a))
        self.assertIn('<p class="deck-pips" aria-hidden="true"><i class="n"></i><i></i><i></i></p>', side)
        self.assertIn('<p class="meta">0 of 3 looked right</p>', side)
        self.review(self.a)
        self.review(self.b)
        side = self.side(self.view(self.c))
        self.assertIn('<i class="d"></i><i class="d"></i><i class="n"></i>', side)
        self.assertIn("2 of 3 looked right", side)
        # A reviewed one opened to edit again is still one that looked right.
        side = self.side(self.view(self.a))
        self.assertIn('<i class="d"></i><i class="d"></i><i></i>', side)
        self.assertIn("2 of 3 looked right", side)

    def test_a_sheet_per_resume_in_the_search_not_per_resume_uploaded(self):
        self.act(self.c, "deselect", back="review")
        body = self.view(self.a)
        side = self.side(body)
        self.assertEqual(re.findall(r'<div class="deck-sheet (p\d)"', side), ["p0", "p1"])
        self.assertEqual(re.search(r'<p class="deck-pips".*?</p>', side).group(0).count("<i"), 2)
        self.assertIn("0 of 2 looked right", side)
        self.assertEqual(self.cards(body)[2][2], "Left out")       # the one left out is still a row, to include again

    def test_the_shuffle_is_only_for_a_next_resume_that_is_ready(self):
        body = self.view(self.a)                                    # B and C are read: the next one is there
        self.assertIn('data-editor data-going="shuffle">', body)
        self.assertRegex(self.editor(body), r">Looks right, next résumé<span class=\"go\"")
        self.assertNotIn("Save and review next", body)
        for tid in (self.a, self.b):
            self.review(tid)
        body = self.view(self.c)                                    # the last one: nothing to shuffle to
        self.assertNotIn('data-going="shuffle"', body)
        self.assertIn("Save and continue to job search", body)
        # Another résumé still being read is not one to shuffle to.
        for tid in (self.b, self.c):
            self.track(tid).update(derived=None, reviewed=False, parse={"state": "reading", "at": time.time()})
        body = self.view(self.a)
        self.assertNotIn('data-going="shuffle"', body)
        self.assertIn("Save résumé 1", body)

    def test_leave_this_resume_out_is_its_own_form_outside_the_editor(self):
        body = self.view(self.b)
        form = self.editor(body)
        self.assertIn('<button class="tertiary" type="submit" form="leave-out" name="do" value="deselect">'
                      "Leave this résumé out</button>", form)
        self.assertNotIn('id="leave-out"', form)                     # forms do not nest
        leave = re.search(r'<form id="leave-out" method="post" action="/tracks" data-going="toss">(.*?)</form>', body, re.S).group(1)
        self.assertEqual(re.findall(r'<input type="hidden" name="(\w+)" value="(\w+)">', leave),
                         [("track", self.b), ("back", "review")])
        self.assertEqual(body.count('id="leave-out"'), 1)
        # Pressed: out of the search, back to the review, which opens the next résumé to check.
        left = self.act(self.b, "deselect", back="review")
        self.assertEqual((left.status_code, left.headers["Location"]), (303, "/review"))
        after = self.view()
        self.assertEqual([c[2:4] for c in self.cards(after)],
                         [("Ready to review", True), ("Left out", False), ("Ready to review", False)])
        self.assertIn("0 of 2 looked right", self.side(after))

    def test_only_a_deck_page_fades_into_the_next(self):
        """deck.css opts the page into a cross-document view transition; a page change fades only when both pages have it,
        so only deck page to deck page (the next résumé, or one left out) fades, and with reduced motion nothing does."""
        link = '<link rel="stylesheet" href="/static/deck.css">'
        self.assertEqual(self.view(self.a).count(link), 1)
        css = (pathlib.Path(__file__).resolve().parents[1] / "static" / "deck.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"@media \(prefers-reduced-motion: no-preference\) \{\s*@view-transition \{ navigation: auto; \}\s*\}")
        for tid in IDS:
            self.review(tid)
        self.assertEqual(self.view().count(link), 1)                     # all reviewed: still the deck
        for t in self.tracks():                                              # reading: the ledger, no fade
            t["derived"], t["reviewed"] = None, False
        self.assertNotIn("deck.css", self.view())

    def test_every_resume_reviewed_keeps_the_deck_with_the_way_on_beside_it(self):
        """The last "Leave this résumé out" (or a visit after the last save) lands on the deck's own shape: the pile done,
        every card a row, and the way on where the open card stood, said once."""
        for tid in IDS:
            self.review(tid)
        body = self.view()
        self.assertEqual(self.cards(body)[0][3], False)
        self.assertEqual(body.count('<div class="ledger deck-on">'), 1)
        side = self.side(body)
        front = re.search(r'<div class="deck-sheet p0" data-deck-front>(.*?)</div>', side, re.S).group(1)
        self.assertIn('<b class="deck-name">Ready to sweep</b>', front)
        self.assertIn("3 résumés", front)
        self.assertNotIn("Checking now", side)
        self.assertIn('<i class="d"></i><i class="d"></i><i class="d"></i>', side)
        self.assertIn("3 of 3 looked right", side)
        self.assertEqual(re.findall(r'data-card="(\w+)"', side), list(IDS))
        done = body[body.index('<div class="deck-done">'):]
        self.assertIn('id="resumes-continue"', done)
        self.assertEqual(body.count('id="resumes-continue"'), 1)
        for gone in ("leave-out", 'data-going="shuffle"', "data-editor"):
            self.assertNotIn(gone, body)

    def test_leave_this_resume_out_drops_the_sheet_off_the_pile(self):
        body = self.view(self.a)
        self.assertRegex(body, r'<form id="leave-out" method="post" action="/tracks" data-going="toss">')

    def test_nothing_is_read_yet_so_nothing_is_open_and_there_is_no_deck(self):
        # (setUp read them all; a fresh page has none to open.)
        for t in self.tracks():
            t["derived"], t["reviewed"] = None, False
        body = self.view()
        self.assertEqual(body.count('<div class="ledger">'), 1)
        self.assertNotIn("deck-", body)


if __name__ == "__main__":
    unittest.main()
