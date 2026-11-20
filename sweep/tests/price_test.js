/* price.js, the Configure screen's live price, against a network the test
   controls: every question is held open until the test answers it, so the
   order the answers arrive in is the one the case names. Nothing here waits on
   a clock. */
const fs = require("fs");

global.window = {};
global.FormData = function (form) { return form.entries; };   // what Object.fromEntries reads
eval(fs.readFileSync(__dirname + "/../static/price.js", "utf8"));
const { sweepPricer } = window;

let fails = 0;
const ok = (cond, msg) => { console.log((cond ? "  ok   " : "  FAIL ") + msg); if (!cond) fails++; };
const flush = () => new Promise((resolve) => setImmediate(resolve));

const reply = (status, data) => ({ ok: status >= 200 && status < 300, status: status, json: () => Promise.resolve(data) });
const estimate = (total) => ({ total: total, lines: [], over_cap: false });
const form = (depth, scope = "india") => ({ entries: [["scope", scope], ["max_results", String(depth)]] });
const body = (f) => JSON.stringify(Object.fromEntries(f.entries));

/* A network whose answers are the test's to give. `honour`: whether cancelling a
   question stops its answer arriving. A browser does, mostly; an answer that has
   already landed, or a browser with no AbortController, does not, so the ordering
   cases run both ways. */
function network(honour) {
  const calls = [];
  const ask = (url, init) => new Promise((resolve, reject) => {
    const call = {
      url: url, init: init,
      price: (total) => resolve(reply(200, estimate(total))),
      refuse: (status, text) => resolve(reply(status, { error: text })),
      garbage: () => resolve({ ok: true, status: 200, json: () => Promise.reject(new SyntaxError("not JSON")) }),
      drop: () => reject(new TypeError("Failed to fetch")),
    };
    if (init.signal && honour) {
      init.signal.addEventListener("abort", () => {
        const aborted = new Error("The operation was aborted.");
        aborted.name = "AbortError";
        reject(aborted);
      });
    }
    calls.push(call);
  });
  return { calls: calls, ask: ask };
}

function pricer(honour = true) {
  const net = network(honour);
  return { net: net, p: sweepPricer({ est: estimate(1), cap: 8.41, url: "/estimate" }, net.ask) };
}

async function main() {
  // --- the page as it loads ---------------------------------------------------
  let { p } = pricer();
  ok(p.est.total === 1 && p.cap === 8.41 && !p.busy && p.err === null && !p.stale && p.priced === null,
     "it starts on the page's own estimate: nothing pending, nothing stale, no error");

  // --- one change -------------------------------------------------------------
  let net;
  ({ net, p } = pricer());
  const f1 = form(20);
  p.price(f1);
  ok(net.calls.length === 1 && net.calls[0].url === "/estimate" && net.calls[0].init.method === "POST" &&
     net.calls[0].init.headers["Content-Type"] === "application/json" && net.calls[0].init.body === body(f1),
     "a change asks POST /estimate for the form as it stands, as JSON");
  ok(p.busy && p.stale && p.err === null && p.est.total === 1,
     "from the moment of the change the figures are stale and a check is out, and they are still the old ones");
  net.calls[0].price(7);
  await flush();
  ok(p.est.total === 7 && p.priced === body(f1) && !p.busy && !p.stale && p.err === null,
     "its price lands: the figures are current, and remember the form they were priced from");

  // --- two changes, answers in either order, with the cancel honoured and without ------
  const fa = form(20), fb = form(25);
  for (const [honour, how] of [[true, "cancel honoured"], [false, "cancel too late"]]) {
    ({ net, p } = pricer(honour));
    p.price(fa);
    p.price(fb);
    net.calls[1].price(25);                       // B, the newer, is the quick one
    await flush();
    ok(p.est.total === 25 && !p.busy && !p.stale && p.priced === body(fb), "B (newer, fast) is what is shown (" + how + ")");
    net.calls[0].price(20);                       // and A, the slow one, turns up late
    await flush();
    ok(p.est.total === 25 && p.priced === body(fb) && !p.busy && !p.stale,
       "A slow, B fast: A arriving late does not replace B, and nothing flickers back to stale (" + how + ")");

    ({ net, p } = pricer(honour));
    p.price(fa);
    p.price(fb);
    net.calls[0].price(20);                       // A, the older, is the quick one
    await flush();
    ok(p.est.total === 1 && p.busy && p.stale && p.priced === null,
       "B slow, A fast: A is not shown (it answers a form that is gone), and B is still awaited (" + how + ")");
    net.calls[1].price(25);
    await flush();
    ok(p.est.total === 25 && !p.busy && !p.stale && p.priced === body(fb), "B slow, A fast: B is what is shown once it finishes (" + how + ")");

    // --- superseded answers that are not prices ---------------------------------
    for (const [what, act] of [
      ["an error", (c) => c.refuse(400, "The engine could not price that combination. Nothing was charged.")],
      ["a 429", (c) => c.refuse(429, "Too many search plans in the last minute.")],
      ["a dropped connection", (c) => c.drop()],
      ["an unreadable answer", (c) => c.garbage()],
    ]) {
      ({ net, p } = pricer(honour));
      p.price(fa);
      p.price(fb);
      net.calls[1].price(25);
      await flush();
      act(net.calls[0]);                           // the OLDER question fails after the newer one succeeded
      await flush();
      ok(p.err === null && p.est.total === 25 && !p.busy && !p.stale && p.priced === body(fb),
         "late " + what + " from a superseded check leaves the valid newer price alone (" + how + ")");

      ({ net, p } = pricer(honour));
      p.price(fa);
      p.price(fb);
      act(net.calls[0]);                           // ...and before it, too
      await flush();
      ok(p.err === null && p.busy && p.stale, "early " + what + " from a superseded check is not shown either (" + how + ")");
      net.calls[1].price(25);
      await flush();
      ok(p.err === null && p.est.total === 25 && !p.stale, "and the newer price then lands (" + how + ")");
    }
  }

  // --- a form changed while its previous estimate is pending ------------------
  ({ net, p } = pricer());
  p.price(fa);
  const first = net.calls[0].init.signal;
  ok(first && !first.aborted, "the first check is live while it is the newest");
  p.price(fb);
  ok(first.aborted && !net.calls[1].init.signal.aborted, "the next change cancels the older check and keeps its own");
  await flush();
  ok(p.busy && p.stale && p.err === null && p.est.total === 1,
     "the cancelled check's own failure is not an error: the newer check is still awaited");
  net.calls[1].price(25);
  await flush();
  ok(p.est.total === 25 && !p.stale, "and the newer check's price is shown");

  // --- a burst of stepper clicks is one question, asked once they stop -------
  {
    const net2 = network(true), timers = [];
    const q = sweepPricer({ est: estimate(1), cap: 8.41, url: "/estimate" }, net2.ask, (fn) => timers.push(fn));
    q.price(fa);                                  // a check already out when the clicking starts
    const out = net2.calls[0].init.signal;
    q.soon(form(30)); q.soon(form(35)); q.soon(fb);
    ok(net2.calls.length === 1 && out.aborted && q.busy && q.stale && q.est.total === 1,
       "clicks ask nothing yet: the figures go stale at once and the check already out is cancelled");
    net2.calls[0].price(20);
    await flush();
    ok(q.est.total === 1 && q.stale, "an answer that lands mid-burst is not shown under the newer number");
    timers.slice(0, 2).forEach((fn) => fn());
    ok(net2.calls.length === 1, "the earlier clicks' timers ask nothing");
    timers[2]();
    ok(net2.calls.length === 2 && net2.calls[1].init.body === body(fb), "the last click's timer asks once, for the form as it stands");
    net2.calls[1].price(25);
    await flush();
    ok(q.est.total === 25 && !q.busy && !q.stale && q.priced === body(fb), "and its price lands");

    const net3 = network(true), later = [];
    const r = sweepPricer({ est: estimate(1), cap: 8.41, url: "/estimate" }, net3.ask, (fn) => later.push(fn));
    r.soon(fa);
    r.price(fb);                                  // another control changed before the clicks settled
    later[0]();
    ok(net3.calls.length === 1 && net3.calls[0].init.body === body(fb),
       "a direct change before the clicks settle prices now, and the stepper's timer then asks nothing");
  }

  // --- the newest answer is an error ------------------------------------------
  ({ net, p } = pricer());
  p.price(fa);
  net.calls[0].price(20);
  await flush();
  p.price(fb);
  net.calls[1].refuse(400, "That combination cannot be priced.");
  await flush();
  ok(p.err === "That combination cannot be priced." && p.est.total === 20 && p.priced === body(fa),
     "the newest answer being an error shows it, over the last good figures, never as the estimate");
  ok(p.stale && !p.busy, "and those figures stay marked stale: they price a form that is gone");
  p.price(form(30));
  ok(p.err === null && p.busy, "the next change clears the error and asks again");
  net.calls[2].price(30);
  await flush();
  ok(p.err === null && p.est.total === 30 && !p.stale, "a price then makes the figures current");

  ({ net, p } = pricer());
  p.price(fa);
  net.calls[0].refuse(429, "You have asked for too many prices.");
  await flush();
  ok(p.err === "You have asked for too many prices." && p.stale && !p.busy, "a 429 to the newest check is shown, figures stale");

  ({ net, p } = pricer());
  p.price(fa);
  net.calls[0].drop();
  await flush();
  ok(p.err === "Could not reach the estimator — the figures below may be out of date." && p.stale && !p.busy,
     "a dropped connection to the newest check says the figures may be out of date");

  ({ net, p } = pricer());
  p.price(fa);
  net.calls[0].refuse(400, "");
  await flush();
  ok(p.err === "That could not be priced.", "an error with no words still says something");

  // --- many changes: every arrival order -------------------------------------
  const orders = [[0, 1, 2], [0, 2, 1], [1, 0, 2], [1, 2, 0], [2, 0, 1], [2, 1, 0]];
  for (const [honour, how] of [[true, "cancel honoured"], [false, "cancel too late"]]) {
  for (const order of orders) {
    ({ net, p } = pricer(honour));
    const forms = [form(10), form(15), form(20)];
    forms.forEach((f) => p.price(f));
    let right = true, newest = false;
    for (const k of order) {
      net.calls[k].price(100 + k);
      await flush();
      if (k === 2) newest = true;
      // until the third is answered nothing is shown but the page's own figures, marked stale
      const shown = newest ? (p.est.total === 102 && !p.busy && !p.stale)
                           : (p.est.total === 1 && p.busy && p.stale);
      if (!shown) right = false;
    }
    ok(right && p.priced === body(forms[2]),
       "three changes answered in order " + order.join(",") + ": only the third is ever shown (" + how + ")");
  }
  }

  // The sentence under the figure when the plan does not fit (D7C): worded for the real cause, never "$0.00 more".
  {
    const say = (est) => sweepPricer({ est: Object.assign({ total: 3, lines: [], over_cap: false, shortfall: 0 }, est),
                                       cap: 8.41, url: "/estimate" }, () => {}).overWhy;
    ok(say({}) === "", "a plan that fits says nothing");
    ok(say({ over_cap: true, shortfall: 1.5 }) === "That is $1.50 more than your key has.", "the estimate over the key's credit names the dollars");
    ok(say({ over_cap: true, shortfall: 0.004 }) === "This costs more than your key's credit covers.", "a shortfall that rounds to nothing has no figure worth naming: never \"$0.00 more\"");
    const part = (placeable) => ({ over_cap: true, shortfall: 0, coverage: { full: false, placeable_units: placeable, total_units: 90, accounts: 2 } });
    ok(say(part(61)) === "Your connected accounts can run 61 of 90 of these paid searches.", "partial coverage says how many fit, with no dollars to state");
    ok(say(part(0)) === "None of these paid searches fit within the credit on your connected accounts.", "no coverage at all says that");
    ok(!/\$0\.00/.test(say(part(61))) && !/\$0\.00/.test(say(part(0))), "neither is ever a $0.00 shortfall");
    ok(say({ over_cap: false, paid_unavailable: true }) === "Paid searches are temporarily unavailable, so none will start. Nothing is charged.",
       "unavailable paid searches are said as that, though nothing is over");
    ok(say({ over_cap: true, shortfall: 0 }) === "This costs more than your key's credit covers.", "flagged with no figure to name: a sentence with no number in it");
    ok(say({ over_cap: false, coverage: { full: true, placeable_units: 90, total_units: 90 } }) === "", "full coverage says nothing");
    ok(say({ over_cap: true, shortfall: 2, coverage: { full: true, placeable_units: 90, total_units: 90 } }) === "That is $2.00 more than your key has.",
       "a console estimate over the credit, whatever else is on the plan");
  }

  // The plan ticket (T2): its boards and searches lines, and the wash on a line that changed.
  {
    const lines = [{ site: "linkedin", label: "LinkedIn", free: false, searches: 36 }, { site: "indeed", label: "Indeed", free: false, searches: 36 },
                   { site: "naukri", label: "Naukri", free: false, searches: 0 }, { site: "greenhouse", free: true, searches: 120 }];
    const p = sweepPricer({ est: { total: 4.21, lines: lines, over_cap: false }, cap: 8, url: "/estimate" }, () => {});
    ok(p.boards === "LinkedIn, Indeed, and the free boards", "the boards line names the paid boards with searches, then the free ones");
    ok(p.paidSearches === 72, "paid searches only, the free boards not counted");
    p.est = { total: 0, lines: [lines[3]], over_cap: false };
    ok(p.boards === "Free boards only" && p.paidSearches === 0, "no paid board on: free boards only");
    const cls = new Set();
    const el = { dataset: {}, offsetWidth: 0, classList: { add: (c) => cls.add(c), remove: (c) => cls.delete(c) } };
    p.ink(el, "India");
    ok(!cls.has("inked"), "first paint is not a change");
    p.ink(el, "India");
    ok(!cls.has("inked"), "the same value again is not a change");
    p.ink(el, "Remote roles");
    ok(cls.has("inked"), "a new value washes the line");
  }

  process.exit(fails ? 1 : 0);
}

main().catch((e) => { console.log("  FAIL " + (e && e.stack || e)); process.exit(1); });
