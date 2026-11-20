/* The two small scripts on the Results page (D7B), run against the page the application renders, on a fake
   clock, a fake DOM and a fake sessionStorage, so every case is exact.

   usage: node results_motion_test.js <rendered-results.html>

   They are inline in the template on purpose (the first has to run before the first paint). They are found by
   their data-motion attribute, so this tests what the page really carries, not a copy. */
const fs = require("fs");

const html = fs.readFileSync(process.argv[2], "utf8");
function script(name) {
  const m = html.match(new RegExp('<script data-motion="' + name + '">([\\s\\S]*?)</script>'));
  if (!m) { console.log("  FAIL the page has no <script data-motion=\"" + name + "\">"); process.exit(1); }
  return m[1];
}
const HEAD = script("arrive"), BODY = script("pending");

let fails = 0;
const ok = (cond, msg) => { console.log((cond ? "  ok   " : "  FAIL ") + msg); if (!cond) fails++; };

const ORIGIN = "https://sweep.example";

/* A page environment. `o` says what the browser would say; `store: "throws"` is a privacy mode. */
function env(o) {
  o = Object.assign({ path: "/results", search: "", referrer: "", nav: "navigate", reduced: false, store: {} }, o);
  const classes = new Set();
  const timers = [];
  let now = o.now || 1e9;
  const storage = {};
  Object.keys(o.store === "throws" ? {} : o.store).forEach((k) => { storage[k] = o.store[k]; });
  const sessionStorage = {
    getItem(k) { if (o.store === "throws") throw new Error("blocked"); return k in storage ? storage[k] : null; },
    setItem(k, v) { if (o.store === "throws") throw new Error("blocked"); storage[k] = String(v); },
    removeItem(k) { if (o.store === "throws") throw new Error("blocked"); delete storage[k]; },
  };
  const handlers = { document: {}, window: {} };
  const rafs = [];
  const ctx = {
    document: {
      referrer: o.referrer,
      documentElement: { classList: {
        add: (c) => classes.add(c), remove: (c) => classes.delete(c), contains: (c) => classes.has(c) } },
      addEventListener: (t, f) => { (handlers.document[t] = handlers.document[t] || []).push(f); },
    },
    location: { origin: ORIGIN, pathname: o.path, search: o.search, href: ORIGIN + o.path + o.search },
    sessionStorage,
    performance: o.noPerformance ? undefined : { getEntriesByType: () => [{ type: o.nav }] },
    matchMedia: () => ({ matches: o.reduced }),
    requestAnimationFrame: (f) => { rafs.push(f); return rafs.length; },
    setTimeout: (f, ms) => { timers.push({ f, at: now + ms, id: timers.length + 1, live: true }); return timers.length; },
    clearTimeout: (id) => { if (timers[id - 1]) timers[id - 1].live = false; },
    addEventListener: (t, f) => { (handlers.window[t] = handlers.window[t] || []).push(f); },
    Date: { now: () => now },
    URL,
  };
  ctx.window = ctx;
  return {
    ctx, classes, storage, handlers,
    frame() { const fs_ = rafs.splice(0); fs_.forEach((f) => f()); },
    advance(ms) {
      const until = now + ms;
      for (;;) {
        const due = timers.filter((t) => t.live && t.at <= until).sort((a, b) => a.at - b.at)[0];
        if (!due) break;
        now = due.at; due.live = false; due.f();
      }
      now = until;
    },
    run(src) {
      const names = Object.keys(ctx);
      new Function(...names, src)(...names.map((n) => ctx[n]));
    },
    fire(target, type, ev) { (handlers[target][type] || []).forEach((f) => f(ev)); },
    get now() { return now; },
  };
}

/* An anchor the way the script reads one. */
function link(href, o) {
  o = o || {};
  const u = new URL(href, ORIGIN + "/results");
  const attrs = Object.assign({ href }, o.attrs || {});
  const a = {
    href: u.href, target: o.target || "",
    hasAttribute: (n) => n in attrs, getAttribute: (n) => attrs[n] === undefined ? null : attrs[n],
  };
  a.closest = (sel) => (/^a\[href\]$|^a$/.test(sel) ? a : null);
  return a;
}
const click = (a, o) => Object.assign({ target: { closest: (s) => (s.startsWith("a") ? a : null) }, defaultPrevented: false, button: 0 }, o);
const submit = (form, o) => Object.assign({ target: form, defaultPrevented: false }, o);

// ---------------------------------------------------------------------------------------------------
console.log("head script: which arrivals are news");

function head(o) { const e = env(o); e.run(HEAD); return e; }

let e = head({ referrer: ORIGIN + "/running" });
ok(e.classes.has("arrive"), "from another product stage (the Running screen): html.arrive");
e.frame();
e.advance(499);
ok(e.classes.has("arrive"), "the class is still there 499 ms after the first frame");
e.advance(2);
ok(!e.classes.has("arrive"), "and gone 500 ms after it: nothing can replay it later");

e = head({ referrer: ORIGIN + "/running" });
e.advance(10000);
ok(e.classes.has("arrive"), "before the first frame nothing has started the clock (a slow first paint must not cut the animation short)");

e = head({ referrer: ORIGIN + "/upload" });
ok(e.classes.has("arrive"), "from any other stage of the product: arrive");

e = head({ referrer: "" });
ok(e.classes.size === 0, "no referrer (a typed address, a bookmark): not an arrival from a stage, nothing");

e = head({ referrer: ORIGIN + "/results?track=abc", search: "?track=def" });
ok(e.classes.size === 0, "from Results itself (a tab, a filter, a sort, Show all): an instant swap, no class");

e = head({ referrer: "https://elsewhere.example/results" });
ok(e.classes.size === 0, "from another site, even one with the same path: nothing");

e = head({ referrer: ORIGIN + "/running", nav: "reload" });
ok(e.classes.size === 0, "a reload is not news");

e = head({ referrer: ORIGIN + "/running", nav: "back_forward" });
ok(e.classes.size === 0, "back and forward are not news");

e = head({ referrer: ORIGIN + "/running", reduced: true });
ok(e.classes.size === 0, "reduced motion: no class at all, the rows are simply there");

e = head({ referrer: ORIGIN + "/running", noPerformance: true });
ok(e.classes.has("arrive"), "a browser without the navigation timing entry still gets the arrival");

e = head({ referrer: ORIGIN + "/running", store: "throws" });
ok(e.classes.has("arrive"), "sessionStorage blocked (a privacy mode): the arrival still works, nothing throws");

e = head({ referrer: ORIGIN + "/results?track=abc", store: "throws" });
ok(e.classes.size === 0, "sessionStorage blocked, from Results: still nothing");

console.log("head script: the un-dim that ends a wait");
e = head({ referrer: ORIGIN + "/results?track=abc", search: "?track=def", store: { "sweep.dimmed": String(1e9 - 500) } });
ok(e.classes.has("swap"), "the previous page dimmed (a fresh flag): html.swap, so the new list continues the cue");
ok(!("sweep.dimmed" in e.storage), "the flag is consumed, so a reload cannot replay it");
e.frame(); e.advance(501);
ok(!e.classes.has("swap"), "and the class removes itself");

e = head({ referrer: ORIGIN + "/results?track=abc", search: "?track=def", store: { "sweep.dimmed": String(1e9 - 10001) } });
ok(e.classes.size === 0, "a flag older than the 10 s give-up is stale: no swap");
ok(!("sweep.dimmed" in e.storage), "a stale flag is cleared too");

e = head({ referrer: ORIGIN + "/running", store: { "sweep.dimmed": String(1e9 - 5000) } });
ok(e.classes.has("arrive") && !e.classes.has("swap"),
   "a fresh flag only means something right after Results: from another screen it is ignored, the arrival is an arrival, and never two classes");
ok(!("sweep.dimmed" in e.storage), "and it is cleared");

e = head({ referrer: ORIGIN + "/running", store: { "sweep.dimmed": String(1e9 - 20000) } });
ok(e.classes.has("arrive") && !e.classes.has("swap"), "a stale flag left by a page the visitor abandoned does not turn a real arrival into a swap");

e = head({ referrer: ORIGIN + "/results?track=abc", search: "?track=def", nav: "reload", store: { "sweep.dimmed": String(1e9 - 500) } });
ok(e.classes.size === 0 && !("sweep.dimmed" in e.storage), "a reload with a flag set: nothing, and the flag is gone");

e = head({ referrer: ORIGIN + "/results?track=abc", search: "?track=def", reduced: true, store: { "sweep.dimmed": String(1e9 - 500) } });
ok(e.classes.size === 0, "reduced motion: no swap class either (the dim itself is a state and is drawn by the pending rule)");

ok(!/\.style|hidden|display|opacity|visibility/.test(HEAD.replace(/\/\*[\s\S]*?\*\//g, "")),
   "the head script never hides, dims or styles anything: it can only add and remove a class");

// ---------------------------------------------------------------------------------------------------
console.log("body script: a slow answer");

function body(o) { const e = env(o); e.run(BODY); return e; }
const fresh = () => body({ store: {} });
const a = (href, o) => link(href, o);

e = fresh();
e.fire("document", "click", click(a("/results?track=def")));
e.advance(159);
ok(!e.classes.has("pending"), "a same-page link answered within 159 ms: never marked pending (no dip on a fast server)");
e.advance(1);
ok(e.classes.has("pending") && "sweep.dimmed" in e.storage, "after 160 ms of waiting: html.pending, and the flag the next page reads");
e.advance(9839);
ok(e.classes.has("pending"), "still pending at 9.999 s");
e.advance(2);
ok(!e.classes.has("pending") && !("sweep.dimmed" in e.storage),
   "gives up at 10 s: the class and the flag are both gone (an abandoned navigation never leaves the list dimmed)");

function arms(href, o, ev) {
  const x = fresh();
  x.fire("document", "click", click(a(href, o), ev));
  x.advance(200);
  return x.classes.has("pending");
}
ok(arms("/results?track=def"), "a tab (same path, other query) arms");
ok(arms("/results?min=40&full=1"), "Show all / a filtered link arms");
ok(arms("/results"), "Clear (the bare path) arms");
ok(!arms("/results?track=abc", { attrs: { "aria-current": "page" } }), "the current tab does not");
ok(!arms("/export.csv"), "an export link does not (another path: the page stays, the browser downloads)");
ok(!arms("/export/xlsx?min=3"), "an export link with a query does not");
ok(!arms("https://jobs.example.test/1", { target: "_blank" }), "Apply (external, new tab) does not");
ok(!arms("/results?track=def", { target: "_blank" }), "a link that opens a new tab does not, even on this path");
ok(!arms("/results?track=def", { attrs: { download: "" } }), "a download does not");
ok(!arms("#main-content"), "a fragment does not");
ok(!arms("https://elsewhere.example/results"), "another origin does not, even with the same path");
ok(!arms("/results?track=def", {}, { metaKey: true }), "a modified click (new tab) does not");
ok(!arms("/results?track=def", {}, { ctrlKey: true }), "a ctrl-click does not");
ok(!arms("/results?track=def", {}, { shiftKey: true }), "a shift-click does not");
ok(!arms("/results?track=def", {}, { button: 1 }), "a middle click does not");
ok(!arms("/results?track=def", {}, { defaultPrevented: true }), "a click something else already handled does not");
ok(!arms("/configure"), "a link to another screen does not (that page is a different screen, not a swap of this list)");

console.log("body script: a filter form");
const form = (o) => Object.assign({ method: "get", action: ORIGIN + "/results" }, o || {});
function submits(f, ev) {
  const x = fresh();
  x.fire("document", "submit", submit(f, ev));
  x.advance(200);
  return x.classes.has("pending");
}
ok(submits(form()), "a valid GET form to this page arms (the filter and sort form)");
ok(submits(form({ action: "" })), "an empty action means this page, and arms");
ok(!submits(form({ method: "post" })), "a POST form does not (re-rank, merge: not a swap of the list)");
ok(!submits(form({ action: ORIGIN + "/export.csv" })), "a GET form to another path does not");
ok(!submits(form(), { defaultPrevented: true }), "a submit something else cancelled does not");

e = fresh();
e.fire("document", "click", { target: { closest: () => null }, defaultPrevented: false, button: 0 });
e.advance(200);
ok(!e.classes.has("pending"),
   "pressing a submit button arms nothing by itself: only the browser's own submit event does, and it fires after validation, so an invalid number field cannot leave the list dimmed");

console.log("body script: interruption and recovery");
e = fresh();
e.fire("document", "click", click(a("/results?track=def")));
e.advance(100);
e.fire("document", "click", click(a("/results?track=ghi")));
e.advance(100);
ok(!e.classes.has("pending"), "a second press before the dim restarts the 160 ms clock (the first press's timer did not survive it)");
e.advance(60);
ok(e.classes.has("pending"), "and the new wait is marked 160 ms after the second press");

e = fresh();
e.fire("document", "click", click(a("/results?track=def")));
e.advance(300);
ok(e.classes.has("pending"), "(setup) dimmed");
const first = e.storage["sweep.dimmed"];
e.advance(500);
e.fire("document", "click", click(a("/results?track=ghi")));
ok(e.classes.has("pending"), "a second press while it is dimmed keeps the dim at once: one continuous wait, not an un-dim and a dim");
ok(+e.storage["sweep.dimmed"] > +first, "and refreshes the flag, so the next page's 10 s freshness covers the new wait");
e.advance(9900);
ok(e.classes.has("pending"), "it is still pending 9.9 s after the second press (the first press's give-up did not fire)");
e.advance(200);
ok(!e.classes.has("pending"), "and gives up 10 s after the second press");

e = fresh();
e.fire("document", "click", click(a("/results?track=def")));
e.advance(300);
ok(e.classes.has("pending"), "(setup) dimmed");
e.fire("window", "pageshow", { persisted: true });
ok(!e.classes.has("pending") && !("sweep.dimmed" in e.storage),
   "a page restored from the back/forward cache keeps neither the class nor the flag");
e.advance(20000);
ok(!e.classes.has("pending"), "and no old timer puts it back");
e.fire("window", "pageshow", { persisted: false });
ok(true, "a normal pageshow is ignored");

e = fresh();
e.fire("document", "click", click(a("/results?track=def")));
e.advance(300);
e.fire("window", "pageshow", { persisted: false });
ok(e.classes.has("pending"), "an ordinary pageshow does not clear a real wait");

e = body({ store: "throws" });
e.fire("document", "click", click(a("/results?track=def")));
e.advance(300);
ok(e.classes.has("pending"), "sessionStorage blocked: the list still dims (the un-dim just is not carried over)");
e.advance(10000);
ok(!e.classes.has("pending"), "and still gives up");

ok(!/focus\s*\(|scrollTo|scrollIntoView|scrollTop|preventDefault|location\.(href|assign|replace)\s*=|\.submit\(/.test(BODY.replace(/\/\*[\s\S]*?\*\//g, "")),
   "the body script never moves focus, scrolls, cancels or performs a navigation, or submits: it only watches");

console.log(fails ? "\n" + fails + " FAILED" : "\nresults motion scripts: all assertions hold");
process.exit(fails ? 1 : 0);
