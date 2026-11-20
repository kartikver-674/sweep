"""D7A: render the real Results page with synthetic, engine-shaped rows, then derive the prototype variants.

Run from the repository root:

    .venv/bin/python docs/design/prototype/motion/build_fixtures.py

The Results HTML is NOT hand-written. It is what `sweep/templates/results.html` renders, through the same
worker-backed harness the Results tests use (a real Render-side app against a real worker app on loopback,
the engine child replaced by a fake; the same strict row reader). Only the rows are invented: people,
companies and postings here are fictional. No model, provider, paid search or external network.

Output, under fixtures/:

  baseline/   the page exactly as the application renders it today (the "before" of this phase)
  proposed/   baseline + the motion layer (motion-proposed.css, a head script, a wrapper div around the
              sections, `x-transition` on the two tool panels). The edits are made by `make_proposed()`
              below, so the difference between the two directories is one readable function.
  proposed-vt/ proposed + motion-vt-alt.css: the cross-document view transition, kept as a measured alternative.
  gsap/       baseline + the GSAP spike (see motion-gsap-spike.js) — for the dependency evaluation only.

Views (the route in serve.py maps /results?track=<id> to these, so the URL shape is production's):
  results-all / -a / -b / -c   All Jobs and the three résumés (19 jobs)
  long-all / long-a            the same views with 240 jobs and "Show all" on (the stagger-cap test)
"""
import json
import os
import pathlib
import random
import re
import sys
import unittest
from datetime import date, timedelta

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))

from sweep.tests import test_multi_results_view as rv  # noqa: E402

A, B, C = rv.A, rv.B, rv.C
KEY = {A: "a", B: "b", C: "c", None: "all"}
SKILLS = {
    A: ["python", "django", "postgresql", "aws", "rest apis", "celery", "redis"],
    B: ["react", "node.js", "typescript", "graphql", "next.js", "tailwind"],
    C: ["go", "kubernetes", "terraform", "aws", "prometheus", "linux"],
}
TITLES = {
    A: ["Senior Backend Engineer", "Backend Engineer, Payments", "Python Developer", "Staff Software Engineer, APIs",
        "Backend Engineer (Django)", "Software Engineer II, Data Services", "Principal Engineer, Billing"],
    B: ["Full Stack Engineer", "Senior Full Stack Developer", "Frontend Engineer, Growth", "Software Engineer, Web",
        "Product Engineer", "Full Stack Developer (React, Node)"],
    C: ["Platform Engineer", "Site Reliability Engineer", "Infrastructure Engineer", "Senior DevOps Engineer",
        "Cloud Platform Engineer", "Kubernetes Engineer"],
}
COMPANIES = ["Kestrel", "Halcyon Freight", "Marrow Labs", "Northwind Ledger", "Tessellate", "Ostrava Systems", "Fennel",
             "Pinecrest Health", "Quillon", "Brightwater", "Lumen & Co", "Vantage Ridge", "Copperline", "Alder Analytics",
             "Stonebridge", "Hollow Oak", "Meridian Works", "Tallow", "Juniper Row", "Cobalt Harbour"]
INDIA = ["Bengaluru, India", "Pune, India", "Hyderabad, India", "Gurugram, India (Hybrid)", "Mumbai, India",
         "Chennai, India", "Noida, India"]
ABROAD = ["Berlin, Germany", "Amsterdam, Netherlands", "Toronto, Canada", "Dublin, Ireland"]
PAY = ["", "", "INR 18-26 LPA", "INR 28-40 LPA", "", "INR 45-60 LPA", ""]
EXP = ["", "3-5", "5-8", "8+", "", "2-4", ""]
SITES = ["greenhouse", "lever", "ashby", "linkedin", "naukri", "indeed"]


def make_rows(n, seed=7):
    """`n` engine rows, best-score first, the way the engine ranks them.

    Mix: ~60% India, ~25% fully remote, the rest abroad; every recommendation state; a negative score or two.
    """
    rng = random.Random(seed)
    today = date(2026, 9, 30)
    rows = []
    for i in range(n):
        best = rng.choice([A, A, B, C, B, A, C])
        top = 62 - int(i * 58 / max(n - 1, 1)) + rng.randint(-1, 1)
        scores = {best: top}
        for t in (A, B, C):
            if t != best and rng.random() < 0.72:
                scores[t] = top - rng.choice([0, 1, 3, 6, 9, 14, 20])
        ranked = sorted(scores, key=lambda t: -scores[t])
        gap = scores[ranked[0]] - (scores[ranked[1]] if len(ranked) > 1 else -99)
        if len(ranked) == 1 or gap >= 6:
            rec, kind = [ranked[0]], "clear"
        elif gap == 0:
            rec, kind = ranked[: min(len(ranked), 3)], "tied"
        elif gap <= 2:
            rec, kind = ranked[:2], "close"
        else:
            rec, kind = ranked[:2], "split"
        caution = "no_focus_evidence" if i % 7 == 3 else ""
        roll = rng.random()
        if roll < 0.60:
            where, scope = rng.choice(INDIA), ""
        elif roll < 0.85:
            where, scope = "Remote", "worldwide"
        else:
            where, scope = rng.choice(ABROAD), ""
        row = rv.job(i + 1, best, scores, rec, kind, caution)
        row.update({
            "title": rng.choice(TITLES[best]),
            "company": COMPANIES[i % len(COMPANIES)],
            "location": where, "remote_scope": scope,
            "salary": rng.choice(PAY), "experience_required": rng.choice(EXP),
            "source_site": rng.choice(SITES),
            "matched_skills": ", ".join(rng.sample(SKILLS[best], rng.randint(3, 6))),
            "date_posted": (today - timedelta(days=rng.randint(0, 9))).isoformat(),
            "apply_url": f"https://jobs.example.test/{i + 1}",
        })
        evals = {t: {"s": s, "m": ", ".join(rng.sample(SKILLS[t], rng.randint(3, 6)))} for t, s in scores.items()}
        evals[best]["m"] = row["matched_skills"]
        row["track_evals"] = json.dumps(evals, separators=(",", ":"))
        rows.append(row)
    return rows


setUpModule, tearDownModule = rv.setUpModule, rv.tearDownModule


class Generate(rv.Results):
    def test_render(self):
        self.run_multi("ada", "bhaskar", "chen")
        out = HERE / "fixtures" / "baseline"
        out.mkdir(parents=True, exist_ok=True)
        self.serve(make_rows(19))
        for tid in (None, A, B, C):
            (out / f"results-{KEY[tid]}.html").write_text(self.page(track=tid), encoding="utf-8")
        self.serve(make_rows(240, seed=11))
        for tid in (None, A):
            (out / f"long-{KEY[tid]}.html").write_text(self.page(track=tid, full=1), encoding="utf-8")


# ---------------------------------------------------------------------------------------------------------
# The variants. Plain string edits of the rendered page, so the diff from the application's own output is
# this function and nothing else. Every edit here is one a template change would make in D7B.

HEAD_SCRIPT = r"""
<script>
/* D7A. One class on <html>, removed again, so nothing is hidden if this never runs and nothing replays when
   the page's own nodes are replaced later.
     arrive = reached from somewhere that is not /results (the Running screen, a link)
     swap   = the previous page was /results AND it had dimmed the list while it waited (see the script at the end
              of the page): the new list continues that cue instead of jumping back to full strength
   A move between views that was answered quickly has neither: it is an instant swap. A reload and a back/forward
   keep the old referrer but are not news either. */
(function () {
  var d = document.documentElement;
  try {
    var dimmed = false;
    try { dimmed = sessionStorage.getItem("sweep.dimmed") === "1"; sessionStorage.removeItem("sweep.dimmed"); } catch (e) {}
    var r = document.referrer ? new URL(document.referrer) : null;
    var nav = performance.getEntriesByType("navigation")[0];
    var same = r && r.origin === location.origin && r.pathname === location.pathname;
    var cls = dimmed ? "swap" : same ? "" : "arrive";
    if (cls && (!nav || nav.type === "navigate") && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
      d.classList.add(cls);
      /* from the first frame, not from head parse: a slow first paint must not cut the animation short */
      requestAnimationFrame(function () { setTimeout(function () { d.classList.remove(cls); }, 500); });
    }
  } catch (e) { /* no motion: the page is simply there */ }
})();
</script>
"""

# Sits at the end of <body>, where the links exist. A tab, "Show all", "Clear" and Apply filters are ordinary links and
# a GET form, so the page navigates. This only says "still waiting" if the answer is slow. It never prevents, delays or
# replaces the navigation. Armed on `submit` (which a browser fires only after its own validation passes), so a number
# field that refuses its input cannot leave the list dimmed; and it gives up after 10 s, so a navigation stopped with
# Esc or lost to the network cannot either.
BODY_SCRIPT = r"""
<script>
(function () {
  var d = document.documentElement, on = null, off = null, WAIT = 160, GIVE_UP = 10000;
  function idle() { clearTimeout(on); clearTimeout(off); d.classList.remove("pending"); try { sessionStorage.removeItem("sweep.dimmed"); } catch (e) {} }
  function start() {
    idle();
    on = setTimeout(function () { d.classList.add("pending"); try { sessionStorage.setItem("sweep.dimmed", "1"); } catch (e) {} }, WAIT);
    off = setTimeout(idle, GIVE_UP);
  }
  function here(url) { try { var u = new URL(url, location.href); return u.origin === location.origin && u.pathname === location.pathname; } catch (e) { return false; } }
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a[href]");
    if (!a || e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    if (a.target === "_blank" || a.hasAttribute("download") || a.hasAttribute("aria-current") || a.getAttribute("href").charAt(0) === "#" || !here(a.href)) return;
    start();
  });
  document.addEventListener("submit", function (e) {
    var f = e.target;
    if (e.defaultPrevented || (f.method || "get").toLowerCase() !== "get" || !here(f.action || location.href)) return;
    start();
  });
  /* Back/forward can restore this page from the bfcache with the flag still set. */
  addEventListener("pageshow", function (e) { if (e.persisted) idle(); });
})();
</script>
"""

CSS_LINK = '<link rel="stylesheet" href="/motion/motion-proposed.css">'
CSS_VT = '<link rel="stylesheet" href="/motion/motion-vt-alt.css">'


def _wrap_sections(page):
    """<div id="results-body"> around every jobs-section, so one region can be named and dimmed."""
    m = re.search(r'<(?:section|details) class="jobs-section', page)
    end = page.rfind("<script>")            # the opened-rows script that closes the screen
    tail = page.rfind("</div>", 0, end)    # the .stack that holds the sections
    if not m or tail < 0:
        return page
    # `stack` keeps the flex column and the 32 px gap the sections had as direct children of the screen's own .stack;
    # a plain wrapper lost that spacing (caught by verify.mjs T14, a pixel comparison with the shipped page).
    return page[:m.start()] + '<div id="results-body" class="stack results-body">' + page[m.start():tail] + "</div>" + page[tail:]


def make_proposed(page, vt=False):
    page = page.replace('<link rel="stylesheet" href="/static/sweep.css">',
                        '<link rel="stylesheet" href="/static/sweep.css">\n' + CSS_LINK + (CSS_VT if vt else '') + HEAD_SCRIPT, 1)
    page = _wrap_sections(page)
    # The two tool panels: Alpine's own class transition (height, the row gap above, opacity; see motion-proposed.css).
    for pid in ("tool-filter", "tool-export"):
        page = page.replace(
            f'id="{pid}" x-show="tool === \'{pid[5:]}\'"',
            f'id="{pid}" x-show="tool === \'{pid[5:]}\'" x-transition:enter="t-in" x-transition:enter-start="t-from" '
            f'x-transition:enter-end="t-to" x-transition:leave="t-out" x-transition:leave-start="t-to" '
            f'x-transition:leave-end="t-from"', 1)
    return page.replace("</body>", BODY_SCRIPT + "</body>") if "</body>" in page else page + BODY_SCRIPT


def make_gsap(page):
    """Baseline + the GSAP spike: the same arrival choreography written with gsap.timeline()."""
    page = page.replace('<link rel="stylesheet" href="/static/sweep.css">',
                        '<link rel="stylesheet" href="/static/sweep.css">\n'
                        '<link rel="stylesheet" href="/motion/motion-gsap-spike.css">\n'
                        '<script src="/vendor/gsap.min.js"></script>\n'
                        '<script src="/motion/motion-gsap-spike.js"></script>', 1)
    return _wrap_sections(page)


def build_variants():
    base = HERE / "fixtures" / "baseline"
    for name, fn in (("proposed", make_proposed), ("proposed-vt", lambda p: make_proposed(p, vt=True)), ("gsap", make_gsap)):
        out = HERE / "fixtures" / name
        out.mkdir(parents=True, exist_ok=True)
        for f in sorted(base.glob("*.html")):
            (out / f.name).write_text(fn(f.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    if "--variants-only" not in sys.argv:
        suite = unittest.TestSuite([Generate("test_render")])
        result = unittest.TextTestRunner(verbosity=0, stream=open(os.devnull, "w")).run(suite)
        if not result.wasSuccessful():
            for _, tb in result.errors + result.failures:
                print(tb)
            sys.exit(1)
    build_variants()
    print("fixtures:", *(sorted(p.name for p in (HERE / "fixtures" / "baseline").glob("*.html"))))
