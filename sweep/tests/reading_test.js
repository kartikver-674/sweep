/* reading.js, the unified page's reader, against a scripted server and a
   stand-in page: what it asks, when it stops, and what it leaves alone. */
const fs = require("fs");
const SOURCE = fs.readFileSync(__dirname + "/../static/reading.js", "utf8");

let fails = 0;
const ok = (cond, msg) => { console.log((cond ? "  ok   " : "  FAIL ") + msg); if (!cond) fails++; };

function el(attrs, children) {
  return {
    attrs: Object.assign({}, attrs), children: children || [], replaced: false, text: "",
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    hasAttribute(k) { return k in this.attrs; },
    replaceWith() { this.replaced = true; },
    get textContent() { return this.text; }, set textContent(v) { this.text = v; },
  };
}

/* One page load: `answers` are read_next's replies in turn; the cards are
   an open one and a compact one. Resolves with what happened. */
function load(answers, reading = "1") {
  return new Promise((done) => {
    const page = el({ "data-resumes": "", "data-reading": reading, "data-review": "/review",
                      "data-derive": "/derive" });
    const openCard = el({ "data-card": "a", "data-open": "" });
    const other = el({ "data-card": "b" });
    const log = { posts: 0, gets: 0, inFlight: 0, maxInFlight: 0, waits: [], reloads: 0 };
    const cards = [openCard, other];
    global.window = {};
    global.location = { href: "http://t/review", reload() { log.reloads++; } };
    global.URL = require("url").URL;
    global.document = {
      querySelector(sel) {
        if (sel === "[data-resumes]") return page;
        if (sel === "[data-card][data-open]") return openCard;
        return null;
      },
      querySelectorAll(sel) { return sel === "[data-card]" ? cards : []; },
      getElementById() { return null; },
      importNode(node) { return node; },
    };
    global.DOMParser = function () {
      this.parseFromString = () => ({
        querySelectorAll: (sel) => (sel === "[data-card]" ? cards.map((c) => el(c.attrs)) : []),
        querySelector: (sel) => el({ "data-card": sel.match(/"(\w+)"/)[1] }),
        getElementById: () => null,
      });
    };
    let queue = answers.slice(), finished = false;
    global.fetch = (url, opts) => {
      if (opts && opts.method === "POST") {
        log.posts++; log.inFlight++; log.maxInFlight = Math.max(log.maxInFlight, log.inFlight);
        const answer = queue.shift() || { state: "idle" };
        return new Promise((r) => setImmediate(() => { log.inFlight--; r({ json: () => Promise.resolve(answer) }); }));
      }
      log.gets++;
      return Promise.resolve({ text: () => Promise.resolve("<html></html>") });
    };
    global.setTimeout = (fn, ms) => { log.waits.push(ms); setImmediate(fn); };
    eval(SOURCE);
    // Settle: let every pending promise and "timer" run out.
    const settle = (n) => (n ? setImmediate(() => settle(n - 1)) : done({ log, openCard, other }));
    settle(200);
  });
}

(async () => {
  let r = await load([{ state: "read" }, { state: "failed" }, { state: "read" }, { state: "idle" }]);
  ok(r.log.posts === 4, "read, failed, read, idle: asks four times and stops (" + r.log.posts + ")");
  ok(r.log.maxInFlight === 1, "never two asks at once");
  ok(!r.openCard.replaced, "the open card is never replaced");
  ok(r.other.replaced, "the other cards are brought up to date");

  r = await load([{ state: "read" }, { state: "limited" }, { state: "read" }]);
  ok(r.log.posts === 2, "a limit refusal stops the asking (" + r.log.posts + " asks)");

  r = await load([{ state: "busy" }, { state: "busy" }, { state: "read" }, { state: "idle" }]);
  ok(r.log.posts === 4, "busy: asks again after a wait");
  ok(r.log.waits.filter((ms) => ms >= 2000).length === 2, "each busy answer waits " +
     "at least 2 s — the app's poll floor (" + r.log.waits.join(",") + ")");

  r = await load([{ state: "idle" }]);
  ok(r.log.posts === 1 && r.log.waits.filter((ms) => ms >= 2000).length === 0, "idle: one ask, no wait, done");

  r = await load([{ state: "read" }], "0");
  ok(r.log.posts === 0 && r.log.gets === 0, "nothing to read: the page asks nothing");

  if (fails) { console.log(fails + " failed"); process.exit(1); }
  console.log("all passed");
})();
