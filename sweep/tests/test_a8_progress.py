"""Direction A, stage A8: the public Progress screen (/running, /progress).

THE ONE SERVER CHANGE. Each fresh item of the live feed carries `skills` (the row's matched_skills, split exactly as results.html
splits it: `split(',')`, trim each, drop the empty ones, the first six) in PUBLIC mode only. Nothing else in the item, the feed, its
order, FEED_LEN, the seen-keys logic or snapshot() moves, and the console's items (and so the console's /running, which embeds
`progress|tojson`) carry no such key and render the bytes they rendered at HEAD (docs/design/sweep-a/harness/running-hash.py).

THE CONTRACT (A8 changes none of it). Every state's words: the headline's x-text and its server twin, the ledes, every ending banner,
the activity lines, the "Finish the remaining..." panel, the exports, the Stop form: pinned below as the words of each region at
33eb49d (`WORDS_AT_HEAD`: each element's x-text expression and its text, in order, minus what A8 adds). The `meter_scope` block's
x-data, the poll / SSE x-init, `leave()` and its timing, `fed` / `.fresh`, `nowRunning()`, the tiles' class logic and the progressbar's
aria are the template's header region, held by its sha256. The run endings are frozen contracts and are not touched.

Around it: the eyebrow, the figure beside the headline, the brush on the track (decoration, set by the fill's own number, no Jinja in
a style attribute), "Now: board · city" from the tile that is running, the Searches peek with its aside, the matches that open to the
skills they mention (one open at a time, a plain row when there are none, `job.skills || []` everywhere), one tip, the passes, the
quiet Stop, and the stylesheet's reach: every A8 rule hangs on `.run-a`, the class only running.html carries. Fakes only: no model,
provider or network.
"""
import csv
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

import jinja2

from sweep import app as app_module
from sweep import runs as runs_mod
from sweep.logic import site_label
from sweep.tests.test_a6_key import Dom, flat
from sweep.tests.test_app import DERIVED, RUNNING_PLAN, FakeProc
from sweep.tests.test_progress_ui import sweep_app
from sweep.tests.test_terminal_states import app_ended

ROOT = pathlib.Path(app_module.__file__).parent
REPO = ROOT.parent
TEMPLATES = {p.name: p.read_text() for p in (ROOT / "templates").glob("*.html")}
RUNNING = TEMPLATES["running.html"]
CSS = (ROOT / "static" / "sweep-a.css").read_text()
SWEEP_CSS = (ROOT / "static" / "sweep.css").read_text()
A8_CSS = re.sub(r"/\*.*?\*/", "", CSS[CSS.rindex("/*", 0, CSS.index("==== A8: Progress")):CSS.rindex("/*", 0, CSS.index("==== A9: Results"))], flags=re.S)   # A9 appends its own section after this one


# ---- what each region said at 33eb49d, read off that commit's rendered pages before A8 touched a template -----------------------
# Each element's x-text expression ({...}) and its text, in order. Skipped: <template> (the rows' own markup is pinned below), and what
# A8 adds: the eyebrow, the ticker, the rider, the aside of the Searches summary, and the tip's wrapper.
SKIP = {"lm-tip", "peek-aside", "eyebrow", "ticker", "rider"}
WORDS_AT_HEAD = {
    "paid_running": {
        "hero": "{p.queued ? 'You are in the queue' : (p.state === 'running' ? 'Sweep is searching for you' : (p.state === 'finished' ? 'Your jobs are ready' : (p.state === 'partial' ? 'Part of your search ran' : (p.state === 'credit_changed' ? 'Your search did not start' : (p.state === 'incomplete' ? 'The sweep did not finish' : (p.state === 'stopped' ? 'You stopped the sweep' : 'Sweep stopped early'))))))} Sweep is searching for you {p.queue_position === 1 ? 'Another Sweep is running right now. Yours is next, and it ' + 'starts automatically.' : 'There are ' + p.queue_position + ' sweeps ahead of yours. ' + 'It starts automatically when they finish.'} {p.state === 'finished' ? 'Sweep searched, scored and ranked every job it found.' : (p.state === 'partial' ? 'Everything Sweep found is saved and ranked.' : (p.state === 'credit_changed' ? 'Nothing was searched and nothing was charged.' : (p.state !== 'running' ? 'Stopped early. Everything Sweep already found is saved.' : (p.elapsed === null || p.elapsed < 20 ? 'Preparing your search.' : (p.free_running ? 'Searching job boards. Results are scored and ranked as they arrive.' : 'Searching job boards and scoring what it finds.')))))} {p.found} {(p.found === 1 ? 'job found' : 'jobs found') + (p.state === 'running' ? ' so far' : '')} Estimated cost $2.70 . {p.authorization ? 'Running the ' + p.authorization.placeable_paid_units + ' of ' + p.authorization.total_planned_paid_units + ' paid searches your Apify credit covers, estimated at $' + Number(p.authorization.partial_estimate_usd).toFixed(2) + '.' : ''} This can take a few minutes to a few tens of minutes, depending on how wide your search is. You can close this tab — Sweep keeps searching, and your jobs will be here when you come back.",
        "activity": ["{p.queued ? 'Waiting to start' : (p.free_running ? 'Searching free sources' : (p.state === 'running' ? 'Searching live' : (p.state === 'finished' ? 'Search complete' : (p.state === 'partial' ? 'Searched what your credit covers' : (p.state === 'incomplete' ? 'Searches complete' : 'Search stopped')))))} Searching live {p.free_running ? 'all ' + p.planned + ' paid searches done' : p.done + ' of ' + p.planned + ' searches complete'} 5 of 46 searches complete | {pct() + '%'} 11%"],
        "banners": [
            [
                "banner ok",
                "{p.planned ? 'Every search ran' : 'The search finished'} Every search ran {p.planned ? 'All ' + p.planned + ' of them. Nothing was left outstanding.' : 'Everything Sweep found is scored, ranked and saved.'} Opening the results… See the results",
            ],
            [
                "banner",
                "You stopped it {p.planned ? (p.outstanding ? p.outstanding + ' of ' + p.planned + ' searches did not run. Everything already fetched is saved.' : 'Every search had already run. Everything already fetched is saved.') : 'The sweep ended before it finished. ' + (p.charged_unknown ? '' : 'Nothing was charged. ') + 'Anything already fetched is saved.'}",
            ],
            [
                "banner warn",
                "The credit ran out {'Every key on file is spent, so the sweep stopped at ' + p.done + ' of ' + p.planned + ' searches. Everything already fetched is saved.'}",
            ],
            [
                "banner warn",
                "Your Apify credit changed When the Sweep came to start, your connected Apify accounts could no longer safely cover the full plan, so no paid search ran and nothing was charged. Add another Apify key, or choose to run with your available credit, and start it again. Back to Confirm",
            ],
            [
                "banner part",
                "The part your credit covers ran {p.done + ' of ' + p.planned + ' paid searches ran, as you chose. ' + 'The other ' + p.outstanding + ' were left out because your ' + 'connected Apify accounts could not safely cover them — they did ' + 'not fail, and nothing was charged for them.'} See the results",
            ],
            [
                "banner warn",
                "{p.timed_out ? 'The sweep ran out of time' : (p.planned ? 'The reason is not recorded' : 'The sweep did not finish')} The reason is not recorded {p.timed_out ? (p.planned ? p.outstanding + ' of ' + p.planned + ' searches did not run because the sweep reached its time limit. Everything already fetched is saved, so your results are still there.' : 'The sweep reached its time limit before it finished. ' + (p.charged_unknown ? '' : 'Nothing was charged. ') + 'Anything already fetched is saved.') : (p.planned ? p.outstanding + ' of ' + p.planned + ' searches did not run, and the reason is not recorded — the credit is not spent. Everything already fetched is saved, so your results are still there.' : 'It stopped before it finished, and the reason is not recorded. ' + (p.charged_unknown ? '' : 'Nothing was charged. ') + 'Anything already fetched is saved.')}",
            ],
            [
                "banner warn",
                "{p.timed_out ? 'Every search ran, then the sweep ran out of time' : 'Every search ran, then the sweep stopped'} Every search ran, then the sweep stopped {'All ' + p.planned + ' searches ran, so their credit is spent. ' + (p.timed_out ? 'The sweep reached its time limit before it finished. ' : 'The sweep stopped before it finished, and the reason is not recorded. ') + 'Everything already fetched is saved, so your results are still there.'} All 46 searches ran, so their credit is spent. The sweep stopped before it finished, and the reason is not recorded. Everything already fetched is saved, so your results are still there. See what it found",
            ],
        ],
        "ended": ["{'Finish the remaining ' + p.outstanding + ' searches'} The {p.done} searches already done are recorded, so they will not be re-run and will not be billed again. Only the {p.outstanding} left would run, at about {'$' + p.remaining_cost.toFixed(2)} . Continue the sweep Re-priced on the Confirm screen before anything runs. There is nothing left to spend on the keys you have, so finishing this needs another one. To search the paid boards again, start a new sweep and paste your Apify key then. It is held for one sweep and never saved, so there is nothing here to top up. Start a new sweep Or keep what it found {p.found} listings are already scored and saved. Stopping here costs nothing more and loses nothing that was fetched. See what it found Export what it found Excel CSV"],
        "actions_free_end": [],
        "stop": ["Stop the sweep Everything already fetched is kept, and you can pick it up again from here."],
        "figures": ["Searches finished {p.done} {'of ' + p.planned + ' planned'} Still to run {p.outstanding} {p.remaining_text}"],
        "searches": ["Searches paid free search running not run yet did not run No paid searches in this sweep Only the free feeds are running, so there is nothing metered to track here. The listings still land on the results screen. {p.done + ' of ' + p.planned + ' finished'} 134 free sources also run, at no cost. Now searching those free sources. There is no grid for them — new listings appear on the right as each one answers."],
        "aside": [
            "Latest matches {p.found} found Nothing yet The first search has to finish before anything lands here. That usually takes a minute or two. {p.state === 'finished' ? 'Nothing matched' : 'Nothing was fetched'} {p.state === 'finished' ? 'The searches ran and no listing came back. Widening the search in Configure may help.' : 'The sweep ended before any listing came back.'} Last listing {ago(p.since)} . They arrive in batches, as each search finishes.",
            "Or keep what it found {p.found} listings are already scored and saved. Stopping here costs nothing more and loses nothing that was fetched. See what it found Export what it found Excel CSV",
        ],
        "free_flow": [],
    },
    "free_running": {
        "hero": "{p.queued ? 'You are in the queue' : (p.state === 'running' ? 'Sweep is searching for you' : (p.state === 'finished' ? 'Your jobs are ready' : (p.state === 'partial' ? 'Part of your search ran' : (p.state === 'credit_changed' ? 'Your search did not start' : (p.state === 'incomplete' ? 'The sweep did not finish' : (p.state === 'stopped' ? 'You stopped the sweep' : 'Sweep stopped early'))))))} Sweep is searching for you {p.queue_position === 1 ? 'Another Sweep is running right now. Yours is next, and it ' + 'starts automatically.' : 'There are ' + p.queue_position + ' sweeps ahead of yours. ' + 'It starts automatically when they finish.'} {p.state === 'finished' ? 'Sweep searched, scored and ranked every job it found.' : (p.state === 'partial' ? 'Everything Sweep found is saved and ranked.' : (p.state === 'credit_changed' ? 'Nothing was searched and nothing was charged.' : (p.state !== 'running' ? 'Stopped early. Everything Sweep already found is saved.' : (p.elapsed === null || p.elapsed < 20 ? 'Preparing your search.' : (p.free_running ? 'Searching job boards. Results are scored and ranked as they arrive.' : 'Searching job boards and scoring what it finds.')))))} {p.found} {(p.found === 1 ? 'job found' : 'jobs found') + (p.state === 'running' ? ' so far' : '')} Nothing is lost while you wait — you can close this tab and come back.",
        "activity": ["Searching live no exact count while the pass runs | "],
        "banners": [
            [
                "banner ok",
                "{p.planned ? 'Every search ran' : 'The search finished'} Every search ran {p.planned ? 'All ' + p.planned + ' of them. Nothing was left outstanding.' : 'Everything Sweep found is scored, ranked and saved.'} Opening the results… See the results",
            ],
            [
                "banner",
                "You stopped it {p.planned ? (p.outstanding ? p.outstanding + ' of ' + p.planned + ' searches did not run. Everything already fetched is saved.' : 'Every search had already run. Everything already fetched is saved.') : 'The sweep ended before it finished. ' + (p.charged_unknown ? '' : 'Nothing was charged. ') + 'Anything already fetched is saved.'}",
            ],
            [
                "banner warn",
                "The credit ran out {'Every key on file is spent, so the sweep stopped at ' + p.done + ' of ' + p.planned + ' searches. Everything already fetched is saved.'}",
            ],
            [
                "banner warn",
                "Your Apify credit changed When the Sweep came to start, your connected Apify accounts could no longer safely cover the full plan, so no paid search ran and nothing was charged. Add another Apify key, or choose to run with your available credit, and start it again. Back to Confirm",
            ],
            [
                "banner part",
                "The part your credit covers ran {p.done + ' of ' + p.planned + ' paid searches ran, as you chose. ' + 'The other ' + p.outstanding + ' were left out because your ' + 'connected Apify accounts could not safely cover them — they did ' + 'not fail, and nothing was charged for them.'} See the results",
            ],
            [
                "banner warn",
                "{p.timed_out ? 'The sweep ran out of time' : (p.planned ? 'The reason is not recorded' : 'The sweep did not finish')} The sweep did not finish {p.timed_out ? (p.planned ? p.outstanding + ' of ' + p.planned + ' searches did not run because the sweep reached its time limit. Everything already fetched is saved, so your results are still there.' : 'The sweep reached its time limit before it finished. ' + (p.charged_unknown ? '' : 'Nothing was charged. ') + 'Anything already fetched is saved.') : (p.planned ? p.outstanding + ' of ' + p.planned + ' searches did not run, and the reason is not recorded — the credit is not spent. Everything already fetched is saved, so your results are still there.' : 'It stopped before it finished, and the reason is not recorded. ' + (p.charged_unknown ? '' : 'Nothing was charged. ') + 'Anything already fetched is saved.')}",
            ],
            [
                "banner warn",
                "{p.timed_out ? 'Every search ran, then the sweep ran out of time' : 'Every search ran, then the sweep stopped'} Every search ran, then the sweep stopped {'All ' + p.planned + ' searches ran, so their credit is spent. ' + (p.timed_out ? 'The sweep reached its time limit before it finished. ' : 'The sweep stopped before it finished, and the reason is not recorded. ') + 'Everything already fetched is saved, so your results are still there.'} All 0 searches ran, so their credit is spent. The sweep stopped before it finished, and the reason is not recorded. Everything already fetched is saved, so your results are still there. See what it found",
            ],
        ],
        "ended": [],
        "actions_free_end": ["See what it found"],
        "stop": ["Stop the sweep Everything already fetched is kept, and you can pick it up again from here."],
        "figures": [],
        "searches": [],
        "aside": [],
        "free_flow": ["What Sweep is doing Preparing your search {stageWord(0)} Turning your profile into queries the free boards understand. Searching free sources {stageWord(1)} Company job boards, enterprise career sites and remote feeds, in one pass. Scoring against your profile {stageWord(2)} Every listing is read and scored on what your résumé actually shows. Preparing your shortlist {stageWord(3)} Ranked, de-duplicated, and ready to export. These are the passes, not a progress meter — the free sources answer in one batch, so there is no honest percentage to show until they do. Latest matches {p.found} found Last job {ago(p.since)} . They arrive in batches, as each board answers. Your shortlist lands here The free sources return everything together at the end of the pass, so this fills in one go rather than trickling. What Sweep searches, and how it ranks Where Sweep is searching 134 free sources, at no cost. Company job boards Greenhouse, Lever, Ashby, Breezy and SmartRecruiters postings, straight from the employer. Enterprise career sites Large employers that publish their own listings. Remote job feeds Public remote-work feeds, fetched directly. No paid board is touched on a Quick Sweep, and nothing here can be billed. How jobs are ranked Skills from your résumé Each one weighted by how much your own document shows you used it. Whether the role is reachable A listing demanding more experience than you have is dropped, not ranked. What you asked to avoid Terms and companies on your avoid list count against a listing. Remote and timezone fit A remote role far outside your working hours loses points. What to expect A few minutes Usually around five, depending on how wide your search is. You can close this tab The search runs on Sweep's own machine, not in this browser. Come back any time This page finds your sweep again, and opens the results itself when it finishes."],
    },
    "paid_finished": {
        "hero": "{p.queued ? 'You are in the queue' : (p.state === 'running' ? 'Sweep is searching for you' : (p.state === 'finished' ? 'Your jobs are ready' : (p.state === 'partial' ? 'Part of your search ran' : (p.state === 'credit_changed' ? 'Your search did not start' : (p.state === 'incomplete' ? 'The sweep did not finish' : (p.state === 'stopped' ? 'You stopped the sweep' : 'Sweep stopped early'))))))} Your jobs are ready {p.queue_position === 1 ? 'Another Sweep is running right now. Yours is next, and it ' + 'starts automatically.' : 'There are ' + p.queue_position + ' sweeps ahead of yours. ' + 'It starts automatically when they finish.'} {p.state === 'finished' ? 'Sweep searched, scored and ranked every job it found.' : (p.state === 'partial' ? 'Everything Sweep found is saved and ranked.' : (p.state === 'credit_changed' ? 'Nothing was searched and nothing was charged.' : (p.state !== 'running' ? 'Stopped early. Everything Sweep already found is saved.' : (p.elapsed === null || p.elapsed < 20 ? 'Preparing your search.' : (p.free_running ? 'Searching job boards. Results are scored and ranked as they arrive.' : 'Searching job boards and scoring what it finds.')))))} {p.found} {(p.found === 1 ? 'job found' : 'jobs found') + (p.state === 'running' ? ' so far' : '')} Estimated cost $2.70 . {p.authorization ? 'Running the ' + p.authorization.placeable_paid_units + ' of ' + p.authorization.total_planned_paid_units + ' paid searches your Apify credit covers, estimated at $' + Number(p.authorization.partial_estimate_usd).toFixed(2) + '.' : ''} This can take a few minutes to a few tens of minutes, depending on how wide your search is. You can close this tab — Sweep keeps searching, and your jobs will be here when you come back.",
        "activity": ["{p.queued ? 'Waiting to start' : (p.free_running ? 'Searching free sources' : (p.state === 'running' ? 'Searching live' : (p.state === 'finished' ? 'Search complete' : (p.state === 'partial' ? 'Searched what your credit covers' : (p.state === 'incomplete' ? 'Searches complete' : 'Search stopped')))))} Search complete {p.free_running ? 'all ' + p.planned + ' paid searches done' : p.done + ' of ' + p.planned + ' searches complete'} 46 of 46 searches complete | {pct() + '%'} 100%"],
    },
    "free_halted": {
        "hero": "{p.queued ? 'You are in the queue' : (p.state === 'running' ? 'Sweep is searching for you' : (p.state === 'finished' ? 'Your jobs are ready' : (p.state === 'partial' ? 'Part of your search ran' : (p.state === 'credit_changed' ? 'Your search did not start' : (p.state === 'incomplete' ? 'The sweep did not finish' : (p.state === 'stopped' ? 'You stopped the sweep' : 'Sweep stopped early'))))))} Sweep stopped early {p.queue_position === 1 ? 'Another Sweep is running right now. Yours is next, and it ' + 'starts automatically.' : 'There are ' + p.queue_position + ' sweeps ahead of yours. ' + 'It starts automatically when they finish.'} {p.state === 'finished' ? 'Sweep searched, scored and ranked every job it found.' : (p.state === 'partial' ? 'Everything Sweep found is saved and ranked.' : (p.state === 'credit_changed' ? 'Nothing was searched and nothing was charged.' : (p.state !== 'running' ? 'Stopped early. Everything Sweep already found is saved.' : (p.elapsed === null || p.elapsed < 20 ? 'Preparing your search.' : (p.free_running ? 'Searching job boards. Results are scored and ranked as they arrive.' : 'Searching job boards and scoring what it finds.')))))} {p.found} {(p.found === 1 ? 'job found' : 'jobs found') + (p.state === 'running' ? ' so far' : '')} Nothing is lost while you wait — you can close this tab and come back.",
        "activity": ["Searching live no exact count while the pass runs | "],
    },
}

# sha256 of running.html from `{% block title %}` to `{% block body %}` at 33eb49d: the page's title, the root x-data (p, cap, drift, fed,
# waiting, pct, stage, stageClass, stageWord, nowRunning, hms, leave and its 400 ms, ago), the poll and SSE x-init, the meter's binds.
# Since then one line, in the public poll only: the finished sweep queues its chime for Results (sound.js) before leave().
HEADER_SHA256 = "bd7df8c0532829a3d020902e359bcf82c65b9aa309acf8ca47695a36bc5e1ef4"

# sha256 (first 16 hex) of the console's /running, GET only, in local mode over a temporary tree, with a frozen clock and the suite's own
# fakes (docs/design/sweep-a/harness/running-hash.py), taken from 33eb49d before A8 edited a template. The listings in the feed carry
# matched_skills, so a leak of `skills` into the console's embedded progress would change these.
CONSOLE_AT_HEAD = {
    "paid running, listings in the feed": "e987d1fe768a146f",
    "paid running, the free pass": "7d8ea20548dc7f43",
    "paid running, nothing yet": "df1457428d77e775",
    "paid finished": "ec3538e416f590c6",
    "paid stopped": "55163f94fea1b763",
    "paid out of credit": "d25964e6c0dbf183",
    "paid halted": "9a7dc85bb7c46498",
    "paid halted, timed out": "9a6150152e2f23a2",
    "paid incomplete": "bc292d03f788aa24",
    "paid partial": "29f662fd3581a4f5",
    "paid credit changed": "f3fedca86f0f4670",
    "free running": "a881fec0b9c7ef45",
    "free finished": "08ed20a772634fd9",
    "free halted": "bf2f42b2e81f4281",
}

# What a page that never ran A8 does not have: none of this is in a console page.
NEW_MARKUP = ("run-a", "run-hero", 'class="rider"', 'class="ticker"', "peek-aside", "lm-b", "lm-why", "lm-tip", "progress-tap",
              'class="eyebrow"', "Step 3 ·", "Now:", "x-data='{ boards", "open: null", "skin-a", "job.skills", "viewBox=\"0 0 36 36\"")

# Classes that are NOT only on running.html and that A8 styles anyway, each one only under `.run-a` (checked below).
SHARED = {"skin-a", "js", "activity", "activity-count", "activity-dot", "activity-said", "aside", "banner", "done", "eyebrow", "free",
          "fresh", "headline-figure", "label", "lede", "live", "meta", "next", "now", "numeral", "off", "ok", "paid", "panel",
          "panel-head", "peek-aside", "secondary", "settled", "split", "tag", "warn", "part", "working-bar",
          "pop"}   # `pop`: set by the page's own x-effect on a tile that finished after it was drawn (classList.toggle), so it is in no class attribute


def words(n):
    if isinstance(n, str):
        return n
    if n.tag == "template" or SKIP & set(n.classes()):
        return ""
    out = []
    if n.attrs.get("x-text"):
        out.append("{" + flat(n.attrs["x-text"]) + "}")
    out.extend(words(k) for k in n.kids)
    return " ".join(out)


def W(n):
    return flat(words(n))


def dom_of(body):
    return Dom(body[body.index("<main>"):body.index("</main>")]).root


def body_of(app):
    return app.test_client().get("/running").get_data(as_text=True)


def page_of(app):
    return dom_of(body_of(app))


def kids(n):
    return [k for k in n.kids if hasattr(k, "tag")]


def regions(root):
    out = {}
    out["hero"] = W([n for n in root.walk() if n.tag == "div" and "stack-tight" in n.classes()][0])
    out["activity"] = [W(a.find("p", "activity-said")[0]) + " | " + " ".join(W(x) for x in a.find("span", "activity-pct"))
                       for a in root.walk() if a.tag == "div" and "activity" in a.classes()]
    out["banners"] = [[" ".join(b.classes()), W(b)] for b in root.walk() if b.tag == "div" and "banner" in b.classes()]
    out["ended"] = [W(e) for e in root.walk() if e.tag == "div" and {"ended", "split"} <= set(e.classes())]
    out["actions_free_end"] = [W(n) for n in root.walk() if n.tag == "div" and "actions" in n.classes()
                               and n.attrs.get("x-show", "").startswith("p.state === 'stopped'")]
    out["stop"] = [W(n) for n in root.walk() if n.tag == "form" and n.attrs.get("action", "").endswith("/stop")]
    out["figures"] = [W(n) for n in root.walk() if n.tag == "dl" and "figures" in n.classes()]
    out["searches"] = [W(n) for n in root.walk() if n.tag == "details" and "searches" in n.classes()]
    out["aside"] = [W(n) for n in root.walk() if n.tag == "aside" and "aside" in n.classes()]
    out["free_flow"] = [W(n) for n in root.walk() if n.tag == "div" and {"flow", "one"} <= set(n.classes())]
    return out


def node_eval(expression, scope):
    """Run an Alpine expression taken from the page, with `scope`'s names in view, in node: the page's own words, not a copy of them."""
    script = ("const s = JSON.parse(process.argv[2]); const names = Object.keys(s); "
              "const f = new Function(...names, 'return (' + process.argv[1] + ')'); "
              "process.stdout.write(JSON.stringify(f(...names.map((k) => s[k]))))")
    done = subprocess.run(["node", "-e", script, expression, json.dumps(scope)], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr[-400:]
    return json.loads(done.stdout) if done.stdout else None


def classes_of(markup):
    found = set()
    for v in re.findall(r'class="([^"]*)"', markup):
        v = re.sub(r"\{\{(.*?)\}\}", lambda m: " " + " ".join(re.findall(r"'([^']*)'", m.group(1))) + " ", v)
        v = re.sub(r"\{%.*?%\}", " ", v)
        found.update(x for x in v.split() if re.fullmatch(r"[A-Za-z_][\w-]*", x))
    return found


def build(done=5, free=False, public=True, items=None, queued=0, found=None, exit_code=None, elapsed=700):
    """The Running screen over the suite's own fakes (test_progress_ui.sweep_app's build, plus the worker's queue)."""
    proc = FakeProc()
    if exit_code is not None:
        proc.poll = lambda: exit_code
    raw = {"profile": "kabir", "sites": {} if free else RUNNING_PLAN["sites"], "max_results": {}, "free_sources": 134}
    state = {"profile": "kabir", "cap_usd": 8.41, "proc": proc, "baseline_usd": 1.0, "raw_plan": raw,
             "run_started_at": time.time() - elapsed, "live_found": len(items or []) if found is None else found,
             "live_items": list(items or []),
             "plan": {"total": 0.0 if free else 2.70, "total_searches": 0 if free else 46, "over_cap": False, "spend_cap": 0.0,
                      "free_sources": 134, "lines": []}}
    if free:
        state["free_only"] = True
    keys = [] if free else runs_mod.combo_keys(raw, runs_mod.today())
    env = os.path.join(tempfile.mkdtemp(), ".env")
    pathlib.Path(env).write_text("APIFY_TOKEN=tok\n")
    app = app_module.create_app(
        state=state, extract=lambda p: "x", derive=lambda t, p: DERIVED, check_token=lambda t: (8.41, None),
        fetch_plan=lambda p: raw, start_sweep=lambda p: proc, read_spend=lambda: 2.42,
        read_done=lambda p, d: set(keys[:done]), read_rows=lambda p: [], env_path=env, read_queue=lambda: queued or None,
        output_dir=tempfile.mkdtemp())
    app.config.update(TESTING=True, PUBLIC_MODE=public)
    return app


JOBS = [
    {"key": "k1", "title": "Senior Backend Engineer", "company": "Kestrel Payments", "site": "linkedin", "score": 62,
     "skills": ["python", "django", "redis"]},
    {"key": "k2", "title": "Platform Engineer", "company": "Halden Labs", "site": "indeed", "score": 55, "skills": []},
    {"key": "k3", "title": "Full Stack Developer", "company": "Orrin Health", "site": "greenhouse:orrin", "score": 47},   # made before the feed carried skills
]
ALL_DONE = len(runs_mod.combo_keys(RUNNING_PLAN, runs_mod.today()))


# =====================================================================================================================
class FeedCase(unittest.TestCase):
    """The REAL reader (the globbing, the diff between two readings), over files in a temporary output directory."""
    COLUMNS = ["score", "title", "company", "source_site", "req_number", "apply_url", "matched_skills"]

    def setUp(self):
        self.out = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.out)
        os.makedirs(os.path.join(self.out, "kabir"))
        self.clock = [1_000_000.0]

    def write(self, rows, columns=None, name="jobs_2026-09-09_1800.csv"):
        with open(os.path.join(self.out, "kabir", name), "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(columns or self.COLUMNS)
            w.writerows(rows)

    def job(self, n, skills="", score=70, site="linkedin"):
        return (score, f"Engineer {n}", f"Company {n}", site, "", "", skills)

    def app(self, public):
        state = {"profile": "kabir", "cap_usd": 8.41, "proc": FakeProc(), "baseline_usd": 1.0, "raw_plan": RUNNING_PLAN,
                 "plan": {"total": 2.70, "total_searches": 46, "over_cap": False, "lines": []}, "run_started_at": self.clock[0]}
        app = app_module.create_app(
            state=state, extract=lambda p: "x", derive=lambda t, p: DERIVED, check_token=lambda t: (8.41, None),
            fetch_plan=lambda profile: RUNNING_PLAN, read_spend=lambda: 2.42, read_done=lambda profile, day: set(),
            output_dir=self.out, wall_now=lambda: self.clock[0])
        app.config.update(TESTING=True, PUBLIC_MODE=public)
        return app

    def progress(self, app):
        return app.test_client().get("/progress").get_json()


class TheFeedCarriesSkills(FeedCase):
    def test_skills_are_split_the_way_results_html_splits_them(self):
        rows = [self.job(1, " react , , node.js,typescript ,a,b,c,d"), self.job(2, "python, django"), self.job(3, ""),
                self.job(4, "  ,  , "), self.job(5, "a,b,c,d,e,f"), self.job(6, "a,b,c,d,e,f,g"), self.job(7, "\tgo\t,\n rust ")]
        self.write(rows)
        items = {j["title"]: j["skills"] for j in self.progress(self.app(True))["latest"]}
        self.assertEqual(items, {
            "Engineer 1": ["react", "node.js", "typescript", "a", "b", "c"],
            "Engineer 2": ["python", "django"],
            "Engineer 3": [],
            "Engineer 4": [],
            "Engineer 5": ["a", "b", "c", "d", "e", "f"],
            "Engineer 6": ["a", "b", "c", "d", "e", "f"],
            "Engineer 7": ["go", "rust"],
        })

    def test_it_is_results_htmls_own_rule_run_through_jinja(self):
        """Not a copy of the rule: the expression results.html carries, evaluated, agrees with the feed on a spread of inputs."""
        rule = "(row['matched_skills'] or '').split(',')|map('trim')|select|list"
        self.assertIn(rule, TEMPLATES["results.html"])
        render = jinja2.Environment().from_string("{{ ((" + rule + ")[:6])|tojson }}")
        cases = [" react , , node.js,typescript ,a,b,c,d", "python, django", "", "  ,  , ", ",", "x", "a,b,c,d,e,f,g,h", "\tgo\t,\n rust ",
                 "c++, c#,  .net ", "ünïcode, ß"]
        self.write([self.job(i, c) for i, c in enumerate(cases)])
        got = {j["title"]: j["skills"] for j in self.progress(self.app(True))["latest"]}
        self.assertEqual(len(got), min(len(cases), app_module.FEED_LEN))
        for i, c in enumerate(cases[:app_module.FEED_LEN]):
            with self.subTest(matched_skills=c):
                self.assertEqual(got[f"Engineer {i}"], json.loads(render.render(row={"matched_skills": c})))

    def test_a_file_with_no_skills_column_or_a_short_row_carries_an_empty_list(self):
        self.write([(70, "Engineer 1", "Company 1", "linkedin", "", "")], columns=self.COLUMNS[:-1])
        self.assertEqual([j["skills"] for j in self.progress(self.app(True))["latest"]], [[]])
        path = os.path.join(self.out, "kabir", "jobs_2026-09-09_1800.csv")
        pathlib.Path(path).write_text(",".join(self.COLUMNS) + "\n70,Engineer 2,Company 2,linkedin,,\n")      # DictReader gives None for the short row's last cell
        self.assertEqual([j["skills"] for j in self.progress(self.app(True))["latest"]], [[]])

    def test_everything_else_in_the_item_is_the_consoles_and_skills_is_last(self):
        self.write([self.job(1, "python, django"), self.job(2, ""), self.job(3, "react")])
        apps = {p: self.app(p) for p in (True, False)}
        public, console = (self.progress(apps[p])["latest"] for p in (True, False))
        self.assertEqual([{k: v for k, v in j.items() if k != "skills"} for j in public], console)
        # the JSON sorts its keys, so the order the item is BUILT in is read off the state the app keeps it in
        for item in apps[True].state["live_items"]:
            self.assertEqual(list(item), ["key", "title", "company", "site", "score", "skills"])
        for item in apps[False].state["live_items"]:
            self.assertEqual(list(item), ["key", "title", "company", "site", "score"])

    def test_the_console_items_carry_no_skills_key_at_all(self):
        self.write([self.job(1, "python, django")])
        app = self.app(False)
        for p in (self.progress(app), self.progress(app)):
            self.assertTrue(p["latest"])
            self.assertTrue(all("skills" not in j for j in p["latest"]))
        self.assertNotIn("skills", app.test_client().get("/running").get_data(as_text=True).split("<main>", 1)[1])

    def test_the_feed_its_order_its_cap_and_its_seen_logic_are_unchanged(self):
        """The same files, read in the same order by a public and a console app: every reading's `latest`, `found` and `since` agree
        (skills aside), including the cap, a new batch on top, a re-read that adds nothing, a torn read and a row with no identity."""
        public, console = self.app(True), self.app(False)
        steps = [
            [self.job(i, f"s{i}, t{i}") for i in range(40)],                                  # more than FEED_LEN
            [self.job(i, f"s{i}") for i in range(40)],                                        # the same again: nothing new
            [self.job(99, "new")] + [self.job(i, f"s{i}") for i in range(40)],                # a new row ranks first: a new batch on top
            [self.job(0), self.job(1)],                                                       # a shorter reading: torn, ignored
            [self.job(99), (50, "", "", "indeed", "", "", "x"), self.job(100, "b")] + [self.job(i) for i in range(40)],     # no identity: counted, never shown
        ]
        for n, rows in enumerate(steps):
            self.write(rows)
            self.clock[0] += 30
            pub, con = self.progress(public), self.progress(console)
            with self.subTest(step=n):
                self.assertEqual([{k: v for k, v in j.items() if k != "skills"} for j in pub["latest"]], con["latest"])
                self.assertEqual((pub["found"], pub["since"]), (con["found"], con["since"]))
                self.assertLessEqual(len(pub["latest"]), app_module.FEED_LEN)
        last = self.progress(public)
        self.assertEqual(len(last["latest"]), app_module.FEED_LEN)
        self.assertEqual(last["latest"][0]["title"], "Engineer 100")
        self.assertEqual(last["found"], 43)                   # every row counted, the one with no identity too

    def test_the_rest_of_the_progress_payload_is_the_consoles(self):
        self.write([self.job(1, "python"), self.job(2, "")])
        public, console = (self.progress(self.app(p)) for p in (True, False))
        public["latest"] = [{k: v for k, v in j.items() if k != "skills"} for j in public["latest"]]
        self.assertEqual(public, console)

    def test_an_item_made_before_the_deploy_has_no_skills_and_is_served_as_it_was(self):
        app = build(items=[JOBS[2]])
        self.assertNotIn("skills", app.test_client().get("/progress").get_json()["latest"][0])
        self.assertEqual(app.test_client().get("/running").status_code, 200)

    def test_live_feed_adds_the_field_and_changes_nothing_else_in_its_source(self):
        text = (ROOT / "app.py").read_text()
        body = text[text.index("    def live_feed(p):"):text.index("    def snapshot():")]
        self.assertEqual(body.count('app.config.get("PUBLIC_MODE")'), 1)
        self.assertEqual(body.count('item["skills"]'), 1)
        for kept in ('p["found"] = app.state.get("live_found", 0)', 'seen = app.state.setdefault("live_seen", set())', "[:FEED_LEN]",
                     "if not key or key in seen:", 'if len(rows) < p["found"]:', "if free_only():\n            return",
                     'app.state["live_found"] = p["found"] = len(rows)'):
            self.assertIn(kept, body)


# =====================================================================================================================
class ThePage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paid_body = body_of(build(items=JOBS))
        cls.paid = dom_of(cls.paid_body)
        cls.free_body = body_of(build(free=True, items=JOBS))
        cls.free = dom_of(cls.free_body)

    # ---- the top ----------------------------------------------------------------------------------------------------
    def test_the_eyebrow_names_the_step_and_the_sweep_above_an_unchanged_headline(self):
        for root, name in ((self.paid, "Deep Sweep"), (self.free, "Quick Sweep")):
            hero = [n for n in root.walk() if n.tag == "div" and "run-hero" in n.classes()]
            self.assertEqual(len(hero), 1)
            first, second = kids(hero[0])[:2]
            self.assertEqual((first.tag, first.classes(), first.text()), ("span", ["eyebrow"], f"Step 3 · {name}"))
            self.assertEqual(second.tag, "h1")
            self.assertIn("p.queued ? 'You are in the queue'", second.attrs["x-text"])
            self.assertEqual(second.attrs["aria-live"], "polite")

    def test_the_found_figure_is_the_same_markup_inside_the_hero(self):
        for body, root in ((self.paid_body, self.paid), (self.free_body, self.free)):
            self.assertIn('<div class="headline-figure found" x-show="!p.queued && p.found" x-cloak', body)
            hero = [n for n in root.walk() if n.tag == "div" and "run-hero" in n.classes()][0]
            found = hero.one("div", "found")
            self.assertEqual(found.one("p", "numeral").attrs["x-text"], "p.found")
            self.assertEqual(flat(found.one("span", "label").attrs["x-text"]), "(p.found === 1 ? 'job found' : 'jobs found') + (p.state === 'running' ? ' so far' : '')")

    def test_the_wrapper_carries_the_hook_every_rule_hangs_on(self):
        self.assertIn('<div class="stack run-a">', self.paid_body)
        self.assertIn('<div class="stack run-a">', self.free_body)

    # ---- the track and its brush --------------------------------------------------------------------------------------
    def test_the_brush_rides_the_end_of_the_fill_by_the_fills_own_number(self):
        track = self.paid.one("div", "activity-track")
        fill, rider = kids(track)
        self.assertEqual((fill.classes(), rider.classes()), (["activity-fill"], ["rider"]))
        self.assertEqual(fill.attrs[":style"], "'width: ' + pct() + '%'")
        self.assertEqual(rider.attrs[":style"], "'left: ' + pct() + '%'")
        self.assertEqual(rider.attrs["aria-hidden"], "true")
        self.assertNotIn("style", rider.attrs)
        svg = rider.find("svg")[0]
        self.assertEqual(svg.attrs["viewbox"], "0 0 36 36")           # (the parser lower-cases attribute names)
        handle, bristles = rider.find("path")
        self.assertEqual((handle.attrs["stroke"], bristles.attrs["stroke"], bristles.attrs["fill"]), ("var(--a-ink)", "var(--a-ink)", "#FFFFFF"))   # the tip's own brush

    def test_the_progressbar_keeps_its_aria_exactly(self):
        track = build(done=5, items=JOBS).test_client().get("/running").get_data(as_text=True)
        track = dom_of(track).one("div", "activity-track")
        self.assertEqual(track.attrs["role"], "progressbar")
        self.assertEqual((track.attrs["aria-valuemin"], track.attrs["aria-valuemax"], track.attrs["aria-valuenow"]), ("0", "100", "11"))
        self.assertEqual(track.attrs["aria-valuetext"], "5 of 46 searches complete")
        self.assertEqual(track.attrs[":aria-valuenow"], "pct()")
        self.assertEqual(track.attrs[":aria-valuetext"], "p.done + ' of ' + p.planned + ' searches complete'")
        self.assertNotIn("aria-hidden", track.attrs)

    def test_the_brush_is_in_the_free_bar_inside_the_moving_segment_and_in_the_paid_pages_free_pass(self):
        self.assertIn('<div class="working-bar"><span><i class="rider" aria-hidden="true"><svg', self.free_body)
        bars = [n for n in self.paid.walk() if n.tag == "div" and "working-bar" in n.classes()]
        self.assertEqual(len(bars), 1)
        seg = kids(bars[0])
        self.assertEqual([s.tag for s in seg], ["span"])
        self.assertEqual([(r.tag, r.classes()) for r in kids(seg[0])], [("i", ["rider"])])

    def test_the_free_bars_markup_keeps_the_brush_on_the_end_of_the_painted_span(self):
        self.assertIn('<div class="working-bar"><span><i class="rider" aria-hidden="true"><svg', self.free_body)
        self.assertIn("no exact count while the pass runs", self.free_body)
        self.assertRegex(A8_CSS, r"\.skin-a \.run-a \.working-bar \.rider \{ right: 0; \}")

    def test_no_jinja_sits_in_a_style_attribute_here(self):
        for line in RUNNING.splitlines():
            self.assertNotRegex(line, r'\sstyle="[^"]*\{[{%]')

    # ---- the ticker ---------------------------------------------------------------------------------------------------
    @staticmethod
    def ticker(app):
        found = [n for n in page_of(app).walk() if n.tag == "p" and "ticker" in n.classes()]
        return found[0] if found else None

    def test_the_ticker_is_in_the_activity_row_after_the_track_and_names_the_running_tile(self):
        t = self.ticker(build(done=5))
        row = t.within("div", "activity")
        order = [k.classes() for k in kids(row)]
        self.assertLess(order.index(["activity-track"]), order.index(["ticker"]))
        self.assertNotIn("style", t.attrs)
        self.assertEqual(t.text(), "Now: LinkedIn · India")                  # the 6th search of the plan: kw5 @ India
        self.assertEqual(self.ticker(build(done=33)).text(), "Now: Indeed · Pune")

    def test_the_ticker_says_the_free_boards_when_every_paid_search_is_done_and_the_process_goes_on(self):
        self.assertEqual(self.ticker(build(done=ALL_DONE)).text(), "Now: the free job boards")

    def test_the_ticker_is_hidden_by_the_server_unless_a_search_is_running(self):
        for label, app in (("finished", build(done=ALL_DONE, exit_code=0)), ("stopped or halted", build(done=3, exit_code=1)),
                           ("queued", build(done=0, queued=2))):
            tag = re.search(r'<p class="ticker"[^>]*>', body_of(app)).group(0)
            with self.subTest(state=label):
                self.assertIn('style="display:none"', tag)
        self.assertNotIn("display:none", re.search(r'<p class="ticker"[^>]*>', body_of(build(done=5))).group(0))

    def test_the_ticker_follows_the_poll_and_is_not_a_live_region(self):
        t = self.ticker(build(done=5))
        self.assertEqual(t.attrs["x-show"], "!p.queued && p.state === 'running'")
        self.assertFalse({"aria-live", "role", "aria-atomic"} & set(t.attrs))
        node = t.parent
        while node is not None and node.tag != "#root":
            self.assertNotIn("aria-live", node.attrs, node.tag)
            node = node.parent

    def test_the_boards_are_the_boards_own_spelling_from_the_plans_sites(self):
        t = self.ticker(build(done=5))
        boards = json.loads(re.search(r"boards:\s*(\{.*\})\s*\}", t.attrs["x-data"]).group(1))
        sites = runs_mod.progress(app_module.planned_keys({"raw_plan": RUNNING_PLAN}), set())["sites"]
        self.assertEqual(boards, {s: site_label(s) for s in sites})
        self.assertEqual(boards, {"linkedin": "LinkedIn", "indeed": "Indeed"})
        self.assertEqual(RUNNING.count("x-data='{ boards"), 1)           # a nested scope: the root's x-data is the header region, held by its sha256

    def test_the_ticker_says_board_dot_place_where_place_is_what_follows_the_last_at(self):
        expression = self.ticker(build(done=5)).find("b")[0].attrs["x-text"]
        boards = {"linkedin": "LinkedIn", "indeed": "Indeed"}

        def say(tile):
            return node_eval(expression.replace("nowRunning()", "(" + json.dumps(tile) + ")"), {"boards": boards})
        self.assertEqual(say({"site": "linkedin", "label": "backend engineer @ Delhi", "state": "pending"}), "LinkedIn · Delhi")
        self.assertEqual(say({"site": "indeed", "label": "react @ native @ Pune, India", "state": "pending"}), "Indeed · Pune, India")
        self.assertEqual(say({"site": "naukri", "label": "(all) @ Noida", "state": "pending"}), "naukri · Noida")        # a board it has no word for is named as it is
        self.assertEqual(say(None), "the free job boards")

    def test_the_tile_the_ticker_names_is_the_one_the_grid_marks_running(self):
        """One function: the grid's `t === nowRunning()` and the ticker's reading of it."""
        self.assertIn("t === nowRunning() ? 'running' : ''", RUNNING)
        self.assertEqual(len(re.findall(r"\bnowRunning\(\) \{", RUNNING)), 1)

    # ---- the Searches peek --------------------------------------------------------------------------------------------
    def test_the_searches_summary_says_how_many_are_done_after_its_heading(self):
        d = self.paid.one("details", "searches")
        summary = kids(d)[0]
        self.assertEqual(summary.tag, "summary")
        parts = kids(summary)
        self.assertEqual([(k.tag, k.classes()) for k in parts], [("h2", []), ("span", ["peek-aside"]), ("span", ["meta"])])
        self.assertEqual(parts[1].attrs["x-text"], "p.done + ' of ' + p.planned + ' done'")
        self.assertEqual(parts[1].text(), "5 of 46 done")
        self.assertIn('<details class="pane searches" open>', self.paid_body)        # A11 polish: open by default, server-rendered; it still closes

    def test_the_grid_its_keys_and_its_tiles_are_unchanged(self):
        """The tile's own class logic and title are HEAD's, byte for byte, on both pages; the public page only adds attributes before it."""
        head = """:class="t.state === 'done' ? (t.free ? 'done free' : 'done')
                           : (p.state !== 'running' ? 'parked'
                              : (t === nowRunning() ? 'running' : ''))"
                   x-text="t.short"></div>"""
        self.assertIn(head, RUNNING)
        self.assertIn('<div class="cell" :title="t.label"{% if public_mode %}', RUNNING)
        console = body_of(build(done=5, public=False))
        self.assertIn('<div class="cell" :title="t.label"\n                   ' + head, console)
        self.assertNotIn("data-label", console)
        self.assertNotIn("x-effect", console)

    # ---- A11 polish: the grid is open, a tile says its search, a tile that finishes pops once ----------------------------
    def test_the_searches_peek_is_open_by_default_and_the_console_panel_is_the_plain_div(self):
        self.assertEqual(len(re.findall(r"<details class=\"pane searches\" open>", self.paid_body)), 1)
        console = body_of(build(done=5, public=False))
        self.assertIn('<div class="panel">\n    <div class="panel-head">\n      <h2>Searches</h2>', console)
        self.assertNotIn("<details", console.split("<h2>Searches</h2>", 1)[0].rsplit('<div class="panel">', 1)[1])

    def test_each_tile_carries_its_full_search_as_data_label_beside_its_title(self):
        tiles = [n for n in self.paid.walk() if n.tag == "div" and "cell" in n.classes()]
        self.assertTrue(tiles)
        for t in tiles:
            self.assertEqual(t.attrs[":title"], "t.label")                     # the title stays
            self.assertEqual(t.attrs[":data-label"], "t.label")                # the CSS tooltip's text (`::after { content: attr(data-label) }`)

    def test_a_tile_pops_only_if_it_was_not_done_when_it_was_drawn(self):
        tiles = [n for n in self.paid.walk() if n.tag == "div" and "cell" in n.classes()]
        for t in tiles:
            self.assertEqual(t.attrs["x-data"], "{ was: t.state === 'done' }")
            self.assertEqual(t.attrs["x-effect"], "t.state === 'done' && !was && !$el._seen && ($el._seen = true, $el.getClientRects().length > 0 && $el.classList.add('pop'))")   # once only (`_seen`: a poll re-runs the effect), and not for one that finished while the panel was shut (nothing is replayed on opening)
            self.assertEqual(t.attrs["@animationend"], "$el.classList.remove('pop')")                                                          # and the class is gone when the pop ends, so closing and opening again does not replay it
        self.assertNotIn("pop", classes_of(RUNNING.replace("x-effect", "")), "the class is set by the effect, never written into the markup")

    # ---- the matches ---------------------------------------------------------------------------------------------------
    def feeds(self):
        return [("paid", self.paid_body, self.paid), ("free", self.free_body, self.free)]

    def test_each_public_feed_has_its_own_open_scope_and_keeps_its_live_region_and_its_keys(self):
        li = "<li x-init=\"fed &amp;&amp; ($el.classList.add('fresh'), setTimeout(() =&gt; $el.classList.remove('fresh'), 400))\">"
        for label, body, root in self.feeds():
            with self.subTest(page=label):
                feed = root.one("ul", "feed")
                self.assertEqual(feed.attrs["x-data"], "{ open: null }")
                self.assertEqual((feed.attrs["aria-live"], feed.attrs["aria-relevant"]), ("polite", "additions"))
                tpl = kids(feed)[0]
                self.assertEqual((tpl.tag, tpl.attrs["x-for"], tpl.attrs[":key"]), ("template", "job in p.latest", "job.key"))
                self.assertEqual(body.count(li), 1)

    @staticmethod
    def row_templates(root):
        feed = root.one("ul", "feed")
        return kids([n for n in feed.walk() if n.tag == "li"][0])

    def test_a_match_with_skills_is_a_button_that_opens_a_panel_and_one_without_is_todays_plain_row(self):
        for label, body, root in self.feeds():
            with self.subTest(page=label):
                parts = self.row_templates(root)
                self.assertEqual([p.tag for p in parts], ["template"] * 4)
                self.assertEqual([p.attrs["x-if"] for p in parts],
                                 ["(job.skills || []).length", "(job.skills || []).length", "!(job.skills || []).length", "!(job.skills || []).length"])
                button, panel, plain, score = (kids(p)[0] for p in parts)
                self.assertEqual((button.tag, button.classes(), button.attrs["type"]), ("button", ["lm-b"], "button"))
                self.assertEqual(button.attrs[":aria-expanded"], "open === job.key ? 'true' : 'false'")
                self.assertEqual(button.attrs["@click"], "open = (open === job.key ? null : job.key)")
                self.assertEqual((panel.tag, panel.classes(), panel.attrs["x-show"]), ("div", ["lm-why"], "open === job.key"))
                self.assertIn("x-cloak", panel.attrs)
                self.assertEqual(panel.one("span", "lm-why-t").text(), "Your skills this listing mentions")
                chips = panel.find("template")[0]
                self.assertEqual(chips.attrs["x-for"], "(skill, i) in job.skills")
                self.assertEqual(kids(chips)[0].classes(), ["tag"])
                self.assertEqual(kids(chips)[0].attrs["x-text"], "skill")
                # the same words in the button and in the plain row: title, "company · site", the score and its title
                self.assertEqual(button.find("b")[0].attrs["x-text"], "job.title")
                for first, second in ((button.find("b")[0], plain.find("b")[0]), (button.one("span", "meta"), plain.one("span", "meta")),
                                      (button.one("span", "feed-score"), score)):
                    self.assertEqual(flat(first.attrs.get("x-text")), flat(second.attrs.get("x-text")))
                self.assertEqual(flat(button.one("span", "meta").attrs["x-text"]), "job.company + (job.site ? ' · ' + job.site : '')")
                self.assertEqual((score.attrs[":title"], score.attrs["x-text"]), ("'Match score ' + job.score", "job.score"))
                self.assertEqual((plain.tag, plain.classes(), [k.tag for k in kids(plain)]), ("span", [], ["b", "span"]))     # today's <span><b/><span class=meta/></span>

    def test_every_use_of_skills_is_guarded_for_an_item_that_has_none(self):
        """An item made before this deploy carries no `skills`: `job.skills.length` would throw, and the feed with it."""
        code = re.sub(r"\{#.*?#\}", "", RUNNING, flags=re.S)                  # the template's comments talk about it too
        uses = [m for m in re.finditer(r"job\.skills", code)]
        self.assertEqual(len(uses), 5)
        guards = [m for m in uses if code[m.start() - 1] == "(" and code[m.end():m.end() + 7] == " || [])"]
        loops = [m for m in uses if code[m.start() - 4:m.start()] == " in "]
        self.assertEqual((len(guards), len(loops)), (4, 1))
        self.assertNotRegex(code, r"skills\.(length|map|slice|some|join|filter)")
        # the one loop is inside the template that is only made when there are skills
        panel = kids(self.row_templates(self.paid)[1])[0]
        self.assertEqual(self.row_templates(self.paid)[1].attrs["x-if"], "(job.skills || []).length")
        self.assertEqual(panel.find("template")[0].attrs["x-for"], "(skill, i) in job.skills")
        # the page's OWN expressions, run in node against an item made before the deploy (no `skills` at all), an empty list and a full one:
        # dropping a guard makes node throw on the first, and this fails
        for root in (self.paid, self.free):
            conditions = [t.attrs["x-if"] for t in self.row_templates(root)]
            for job, has in (({}, False), ({"skills": []}, False), ({"skills": ["a"]}, True)):
                with self.subTest(job=job):
                    self.assertEqual([bool(node_eval(c, {"job": job})) for c in conditions], [has, has, not has, not has])
            wrap = root.one("aside", "tip").within("div", "lm-tip").attrs["x-show"]
            for latest, want in (([], False), ([{}], False), ([{"skills": []}], False), ([{}, {"skills": ["a"]}], True)):
                self.assertIs(node_eval(wrap, {"p": {"latest": latest}}), want)

    def test_one_tip_above_each_feed(self):
        for label, body, root in self.feeds():
            with self.subTest(page=label):
                self.assertEqual(body.count('data-tip="progress-tap"'), 1)
                self.assertEqual(body.count('<aside class="tip"'), 1)
                tip = root.one("aside", "tip")
                self.assertEqual(tip.one("p", "tip-say").text(), "Tap a match to see which of your skills it mentions.")
                wrap = tip.within("div", "lm-tip")
                self.assertEqual(wrap.attrs["x-show"], "p.latest.some(j => (j.skills || []).length)")
                self.assertIn("x-cloak", wrap.attrs)
                order = [n.classes()[0] for n in kids(wrap.parent) if n.classes() and n.classes()[0] in ("lm-tip", "feed")]
                self.assertEqual(order, ["lm-tip", "feed"])
        self.assertEqual(self.paid_body.count("progress-tap") + self.free_body.count("progress-tap"), 2)

    def test_the_tip_shows_once_there_is_something_to_tap(self):
        for items, shown in (([], False), ([JOBS[2]], False), ([JOBS[1]], False), ([JOBS[0]], True)):
            for free in (False, True):
                with self.subTest(items=len(items), free=free):
                    tag = re.search(r'<div class="lm-tip"[^>]*>', body_of(build(free=free, items=items))).group(0)
                    self.assertEqual("display:none" not in tag, shown)

    # ---- the words -----------------------------------------------------------------------------------------------------
    def test_every_state_says_what_it_said_at_head(self):
        states = {"paid_running": sweep_app(done=5, found=4), "free_running": sweep_app(free=True),
                  "paid_finished": app_ended(0, done=ALL_DONE), "free_halted": app_ended(1, free=True)}
        for name, app in states.items():
            now = regions(page_of(app))
            for region, want in WORDS_AT_HEAD[name].items():
                with self.subTest(state=name, region=region):
                    self.assertEqual(now[region], want)

    def test_the_header_region_the_poll_leave_fed_and_nowrunning_live_in_is_byte_for_byte_head(self):
        region = RUNNING[RUNNING.index("{% block title %}"):RUNNING.index("{% block body %}")]
        self.assertEqual(hashlib.sha256(region.encode()).hexdigest(), HEADER_SHA256)

    def test_every_ending_banner_is_still_wired_the_same_way(self):
        banners = [n for n in self.paid.walk() if n.tag == "div" and "banner" in n.classes()]
        self.assertEqual([b.attrs["x-show"] for b in banners], [f"p.state === '{s}'" for s in
                         ("finished", "stopped", "out_of_credit", "credit_changed", "partial", "halted", "incomplete")])
        for b in banners:
            self.assertEqual((b.attrs["x-transition:enter"], b.attrs["x-transition:enter-start"], b.attrs["x-transition:enter-end"]),
                             ("m-in", "m-from", "m-to"))
            self.assertNotIn("x-transition:leave", b.attrs)

    def test_stop_is_the_same_form_with_the_same_button(self):
        form = self.paid.one("form", action="/stop")
        self.assertEqual((form.attrs["method"], form.attrs["x-show"]), ("post", "p.state === 'running'"))
        button = form.one("button")
        self.assertEqual((button.classes(), button.attrs["type"], button.text()), (["secondary"], "submit", "Stop the sweep"))

    # ---- the console ----------------------------------------------------------------------------------------------------
    def test_a_console_page_has_none_of_the_new_markup(self):
        for label, app in (("paid", build(done=5, public=False, items=JOBS[:1])), ("free", build(free=True, public=False)),
                           ("finished", build(done=ALL_DONE, exit_code=0, public=False))):
            body = body_of(app)
            for needle in NEW_MARKUP:
                with self.subTest(page=label, needle=needle):
                    self.assertNotIn(needle, body)

    def test_the_console_wrapper_is_the_plain_stack(self):
        self.assertIn('<div class="stack">', body_of(build(public=False)))


class TheConsoleIsUntouched(unittest.TestCase):
    @staticmethod
    def console():
        out = subprocess.run([sys.executable, str(REPO / "docs/design/sweep-a/harness/running-hash.py"), str(REPO)], capture_output=True, text=True,
                             timeout=240, env={**os.environ, "SWEEP_PUBLIC_MODE": ""}, cwd=str(REPO))
        assert out.returncode == 0, out.stderr[-600:]
        return {re.sub(r"\s+", " ", line[len("console "):-17]).strip(): line.split()[-1] for line in out.stdout.splitlines() if line.startswith("console ")}

    def test_every_console_state_renders_the_bytes_it_rendered_at_head(self):
        self.assertEqual(self.console(), CONSOLE_AT_HEAD)


# =====================================================================================================================
def rules(css):
    return [(" ".join(sel.split()), body) for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)]


def hung_on_the_wrapper(part):
    """`.skin-a .run-a ...`, or `.skin-a.js .run-a ...` for the one rule that hides something (A5 to A7 spell every such rule under .js)."""
    return part.startswith((".skin-a .run-a", ".skin-a.js .run-a"))


def parts_of(css):
    return [p.strip() for sel, _ in rules(css) for p in sel.split(",") if not re.fullmatch(r"\s*(from|to|\d+(\.\d+)?%)\s*", p)]


def unscoped(css, running_only):
    """Selector parts that name no class only running.html carries (keyframe steps aside)."""
    return [p for p in parts_of(css) if not (set(re.findall(r"\.([A-Za-z_][\w-]*)", p)) & running_only)]


def tokens_of(css):
    return {t for p in parts_of(css) for t in re.findall(r"\.([A-Za-z_][\w-]*)", p)}


class TheStylesheetReachesOnlyProgress(unittest.TestCase):
    running = classes_of(RUNNING)
    elsewhere = set().union(*(classes_of(t) for n, t in TEMPLATES.items() if n != "running.html"))
    running_only = running - elsewhere

    def test_run_a_is_a_class_only_running_html_carries(self):
        self.assertIn("run-a", self.running_only)
        self.assertEqual([n for n, t in TEMPLATES.items() if "run-a" in t], ["running.html"])

    def test_every_a8_selector_names_a_class_only_running_html_has(self):
        self.assertEqual(unscoped(A8_CSS, self.running_only), [])

    def test_every_a8_rule_hangs_on_the_skin_and_the_running_wrapper(self):
        parts = parts_of(A8_CSS)
        self.assertGreater(len(parts), 60)
        for part in parts:
            with self.subTest(selector=part):
                self.assertTrue(hung_on_the_wrapper(part), part)

    def test_the_shared_classes_it_reuses_are_these_and_only_under_the_running_wrapper(self):
        reused = {t for t in tokens_of(A8_CSS) if t not in self.running_only}
        self.assertEqual(reused - SHARED, set(), "a class that is not running-only and is not in the list of the ones reused on purpose")
        for t in sorted(reused - {"skin-a"}):
            hits = [p for p in parts_of(A8_CSS) if re.search(rf"\.{re.escape(t)}(?![\w-])", p)]
            self.assertTrue(hits and all(".run-a" in p for p in hits), t)

    def test_the_method_does_catch_a_bare_rule_on_a_shared_class(self):
        for bad in (".skin-a .tag { color: var(--chalk); }", ".skin-a .banner { border: 0; }", ".skin-a .peek-aside { margin: 0; }",
                    ".skin-a .stepper button { width: 1px; }", ".skin-a .aside .panel { padding: 0; }"):
            with self.subTest(rule=bad):
                self.assertEqual(len(unscoped(A8_CSS + "\n" + bad, self.running_only)), 1)

    def test_the_hook_test_catches_a_rule_that_is_running_only_but_not_under_the_wrapper(self):
        """`.feed` is on running.html alone, so a bare `.skin-a .feed li` is no leak onto another page; it is still not how this section is
        written, and the hook test says so."""
        self.assertIn("feed", self.running_only)
        extra = ".skin-a .feed li { color: var(--chalk); }"
        self.assertEqual(unscoped(A8_CSS + "\n" + extra, self.running_only), [])
        self.assertEqual([p for p in parts_of(A8_CSS + "\n" + extra) if not hung_on_the_wrapper(p)], [".skin-a .feed li"])

    def test_no_other_page_carries_the_wrapper(self):
        """The shared classes (.activity, .working-bar, .aside, .banner, .eyebrow) are also on /derive, Results and the steps: none of
        those pages carries the wrapper, so none of these rules can reach them."""
        for name, text in TEMPLATES.items():
            if name != "running.html":
                with self.subTest(template=name):
                    self.assertNotIn("run-a", text)

    def test_no_raw_colour(self):
        self.assertNotRegex(A8_CSS, r"#[0-9A-Fa-f]{3,8}\b")
        self.assertNotRegex(A8_CSS, r"rgba?\(")
        self.assertNotRegex(A8_CSS, r"[:\s](white|black|red|green|blue|orange|yellow|purple)\s*[;}]")

    def test_motion_is_only_in_no_preference_and_there_is_no_reduce_block(self):
        self.assertNotIn("@media (prefers-reduced-motion: reduce)", A8_CSS)
        at = A8_CSS.index("@media (prefers-reduced-motion: no-preference)")
        self.assertEqual(re.findall(r"(?<![\w-])(animation|transition)(?:-[\w-]+)?\s*:\s*([^;}]*)", A8_CSS[:at]), [("animation", "none")])
        block = A8_CSS[at:]
        for needle in ("transition: left var(--ms-2) var(--ease-settle);", "animation: a-bob 3.2s ease-in-out infinite;",
                       "animation: a-sweep 2.9s infinite;", "animation: a-sweep-paint 2.9s infinite;", "animation: a-sweep-brush 2.9s infinite;",
                       "animation: a-tile-pop .26s ease-out;",
                       "animation: a-drop .35s cubic-bezier(.3, 1.4, .5, 1) both;",
                       "animation: a-pop 0.32s cubic-bezier(0.3, 1.6, 0.5, 1) both;"):
            self.assertIn(needle, block)
        # pre-merge polish: the free bar's sweep is three animations on one clock and none of them a size (a-sweep: the fade; a-sweep-paint: a clip-path;
        # a-sweep-brush: a transform), so a frame costs no layout
        self.assertEqual(sorted(re.findall(r"@keyframes\s+([\w-]+)", A8_CSS)), ["a-drop", "a-sweep", "a-sweep-brush", "a-sweep-paint", "a-tile-pop"])
        self.assertNotIn("a-ride", CSS, "the to-and-fro is gone: the free bar sweeps now")
        self.assertEqual(len(re.findall(r"@keyframes\s+a-bob\b", CSS)), 1, "the bob is A2's, reused, not defined again")

    def test_the_brush_moves_with_the_fill_on_the_fills_own_clock_and_bobs_only_while_live(self):
        fill = [m for m in re.findall(r"\.activity-fill \{ transition: ([^}]*) \}", SWEEP_CSS) if m != "none;"][0]
        self.assertEqual(fill, "width var(--ms-2) var(--ease-settle);")
        self.assertIn(fill.replace("width", "left"), A8_CSS)
        self.assertIn(".skin-a .run-a .activity.live .rider svg { animation: a-bob", A8_CSS)
        for sel, body in rules(A8_CSS):
            if sel == ".skin-a .run-a .rider":
                self.assertNotRegex(body, r"animation|transition")             # the anchor carries `left`; only the page moves it

    def test_the_free_bar_sweeps_in_no_preference_and_is_static_half_painted_with_reduced_motion(self):
        """Pre-merge polish: the sweep no longer animates a width (layout, every frame). The span is the track's full width and carries only
        the fade; the stripes are its ::before, shown by a clip-path that opens from the left; the brush (the rider, inside the span) is carried
        by a transform. Same look and timing as the A11 polish it replaces: the crossing is the first 82.8% of 2.9s (2.4s, ease in and out),
        then the fade to 0 over the last 17.2% (0.5s), and it starts over. At rest, and with reduced motion (where sweep.css's `animation: none`
        stands and its width: 100%; opacity: .5 is out-ranked), the stripes are half painted at full opacity and the brush rests at their end."""
        at = A8_CSS.index("@media (prefers-reduced-motion: no-preference)")
        seg = [(sel, body) for sel, body in rules(A8_CSS) if sel.endswith(".working-bar > span")]
        self.assertEqual(len(seg), 2)
        (base_sel, base), (move_sel, move) = seg
        self.assertIn("width: 100%; opacity: 1; background: none;", base)         # the whole track; nothing is painted by the span itself
        self.assertNotRegex(base, r"animation|transition")
        self.assertEqual(move.strip(), "animation: a-sweep 2.9s infinite;")
        self.assertGreater(A8_CSS.rindex(move_sel + " {"), at)
        self.assertIn(".working-bar span { animation: none; width: 100%; opacity: .5; }", SWEEP_CSS)
        self.assertGreater(len(base_sel), len(".working-bar span"))            # more specific than sweep.css's reduced rule, so it wins
        # the stripes: the ::before, fixed in place, half shown at rest
        paint_move = [b for s, b in rules(A8_CSS) if s == base_sel + "::before"]
        self.assertEqual(len(paint_move), 2)
        paint = paint_move[0]
        self.assertIn("position: absolute; inset: 0;", paint)
        self.assertIn("clip-path: inset(0 50% 0 0 round 999px);", paint)           # half painted, the right end rounded like the pill
        self.assertIn("repeating-linear-gradient(-45deg, var(--a-lav) 0 10px", paint)
        self.assertNotRegex(paint, r"width|animation|transition")
        self.assertEqual(paint_move[1].strip(), "animation: a-sweep-paint 2.9s infinite;")
        self.assertGreater(A8_CSS.rindex(base_sel + "::before {"), at)
        # the brush: the rider's box is the track's width at its right end, so translateX in percent is a place on the track (-50%: half way)
        rider_sel = base_sel + " > .rider"
        rider = [b for s, b in rules(A8_CSS) if s == rider_sel]
        self.assertEqual(len(rider), 2)
        self.assertEqual(rider[0].strip(), "width: 100%; transform: translateX(-50%);")
        self.assertEqual(rider[1].strip(), "animation: a-sweep-brush 2.9s infinite;")
        self.assertIn(".skin-a .run-a .working-bar .rider { right: 0; }", A8_CSS)    # still anchored at the right end
        self.assertEqual(dict(rules(A8_CSS))[rider_sel + " svg"].strip(), "left: calc(100% - 12px);")   # the brush hangs off the end, as it always did
        self.assertGreater(A8_CSS.rindex(rider_sel + " {"), at)

        def stops(name):
            kf = re.search(r"@keyframes " + name + r" \{(.*?)\n  \}", A8_CSS, re.S).group(1)
            found = re.findall(r"([\d.]+)% \{ ([^}]*) \}", kf)
            self.assertEqual([k for k, _ in found], ["0", "82.8", "100"], name)
            self.assertNotRegex(kf, r"\bwidth\b|\bleft\b|\bright\b|\bheight\b|\btop\b", name + " animates no box property")
            return dict(found)

        fade = stops("a-sweep")                                            # the span: only opacity, 1 until 82.8%, then ease out to 0
        self.assertEqual(fade["0"].strip(), "opacity: 1;")
        self.assertEqual(fade["82.8"].strip(), "opacity: 1; animation-timing-function: ease-out;")
        self.assertEqual(fade["100"].strip(), "opacity: 0;")
        opens = stops("a-sweep-paint")                                     # the stripes: a clip-path, ease in and out across the whole track
        self.assertEqual(opens["0"].strip(), "clip-path: inset(0 100% 0 0 round 999px); animation-timing-function: ease-in-out;")
        self.assertEqual(opens["82.8"].strip(), "clip-path: inset(0 0 0 0 round 999px);")
        self.assertEqual(opens["100"].strip(), "clip-path: inset(0 0 0 0 round 999px);")
        ride = stops("a-sweep-brush")                                      # the brush: a transform on the same stops and easing
        self.assertEqual(ride["0"].strip(), "transform: translateX(-100%); animation-timing-function: ease-in-out;")
        self.assertEqual(ride["82.8"].strip(), "transform: translateX(0);")
        self.assertEqual(ride["100"].strip(), "transform: translateX(0);")
        self.assertAlmostEqual(82.8 / 100 * 2.9, 2.4, places=1)
        self.assertAlmostEqual((1 - 82.8 / 100) * 2.9, 0.5, places=1)

    def test_the_tooltip_the_pop_and_the_clip_are_scoped_and_the_pop_is_a_transform_only_in_no_preference(self):
        tip = [(sel, body) for sel, body in rules(A8_CSS) if sel.endswith("[data-label]:hover::after")]
        self.assertEqual(len(tip), 1)
        self.assertTrue(tip[0][0].startswith(".skin-a .run-a .cell"))
        self.assertIn("content: attr(data-label)", tip[0][1])
        self.assertIn("pointer-events: none", tip[0][1])
        self.assertIn("@media (hover: hover) {\n  .skin-a .run-a .cell[data-label]:hover::after", A8_CSS)       # no hover, no tooltip
        pop = [(sel, body) for sel, body in rules(A8_CSS) if sel == ".skin-a .run-a .cell.pop"]
        self.assertEqual(len(pop), 1)
        self.assertGreater(A8_CSS.index(pop[0][0] + " {"), A8_CSS.index("@media (prefers-reduced-motion: no-preference)"))
        self.assertIn("animation: a-tile-pop .26s ease-out;", pop[0][1])
        kf = re.search(r"@keyframes a-tile-pop \{(.*?)\n  \}", A8_CSS, re.S).group(1)
        self.assertEqual(sorted(set(re.findall(r"([\w-]+)\s*:", re.sub(r"[\d.%, ]+\{", "{", kf)))), ["transform"])   # transform only
        self.assertIn("scale(1.12)", kf)
        self.assertNotRegex(kf, r"color|background|border|opacity")                                # a transform is not a colour (D7B's P2)

    def test_the_d7b_verbs_on_this_page_are_still_there_and_the_drop_in_is_alongside(self):
        self.assertIn(".feed li.fresh > * { animation: write-in var(--ms-2) var(--ease-settle) both; }", SWEEP_CSS)
        self.assertIn(".skin-a .run-a .feed li.fresh { animation: a-drop", A8_CSS)
        self.assertIn(".cell { transition: background-color var(--ms-2) var(--ease-settle)", SWEEP_CSS)
        # D7B's colour change on a finished tile is sweep.css's own transition and nothing here re-times or re-colours it; the one
        # animation on a tile is the pop (a transform, above), on a `.pop` the page sets only on a tile that finished after it was drawn.
        self.assertEqual([sel for sel, body in rules(A8_CSS) if re.search(r"\.cell\b", sel) and re.search(r"animation|transition", body)],
                         [".skin-a .run-a .cell.pop"])
        self.assertNotRegex(A8_CSS, r"\.(m-in|m-from|m-to|banner)[^{]*\{[^}]*(animation|transition)")
        self.assertNotIn(".feed li.fresh > ", A8_CSS)

    def test_the_only_thing_hidden_is_the_summarys_legend_while_the_peek_is_shut_and_only_with_a_script(self):
        self.assertEqual([sel for sel, body in rules(A8_CSS) if re.search(r"display:\s*none", body)],
                         [".skin-a.js .run-a details.searches:not([open]) > summary > .meta"])

    def test_the_stop_buttons_quiet_look_is_scoped_by_the_form_it_belongs_to(self):
        sels = [sel for sel, _ in rules(A8_CSS) if "/stop" in sel]
        self.assertTrue(sels)
        for sel in sels:
            self.assertIn('.run-a form[action$="/stop"] button.secondary', sel)

    def test_the_figure_sits_on_the_right_on_wide_screens_and_under_the_headline_on_a_phone_and_nothing_is_pinned(self):
        self.assertRegex(A8_CSS, r"\.run-hero > \.headline-figure\.found \{ grid-column: 2;")
        phone = A8_CSS[A8_CSS.index("@media (max-width: 40rem)"):A8_CSS.index("@media (prefers-reduced-motion: no-preference)")]
        self.assertIn(".skin-a .run-a .run-hero { grid-template-columns: minmax(0, 1fr); }", phone)
        self.assertIn("grid-column: 1; grid-row: auto;", phone)
        self.assertNotRegex(A8_CSS, r"position:\s*(sticky|fixed)")


if __name__ == "__main__":
    unittest.main()
