/* tips.js, the brush tip's dismiss script, against a stand-in page: which tips it hides on load, when the dismiss button
   appears, and where focus goes after a dismiss. Real browsers run it in docs/design (A2 evidence).
   TIPS_JS=<path> points the test at a mutated copy (how the mutation check was run). */
const fs = require("fs");
const vm = require("vm");
const SOURCE = fs.readFileSync(process.env.TIPS_JS || __dirname + "/../static/tips.js", "utf8");

let fails = 0;
const ok = (cond, msg) => { console.log((cond ? "  ok   " : "  FAIL ") + msg); if (!cond) fails++; };

/* A tiny document. `order` is document order; a node is "inside" another by `parent`. Layout of the page:
   0 link-before, 1 tip-a (button-a inside), 2 link-after, 3 tip-b (button-b inside), 4 main (last, so a tip with nothing
   after it falls through to <main>). `mainFirst:false` keeps that; `lastTip:true` drops link-after so tip-a has nothing after. */
function page({ stored = null, throws = false, lastTip = false } = {}) {
  let n = 0;
  const mk = (name, extra = {}) => ({
    name, order: n++, hidden: false, attrs: {}, focused: false, parent: null, rects: 1,
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    removeAttribute(k) { delete this.attrs[k]; },
    getClientRects() { return { length: this.rects }; },
    focus() { this.focused = true; },
    listeners: {},
    addEventListener(t, f) { this.listeners[t] = f; },
    compareDocumentPosition(o) {
      if (o.parent === this) return 4 | 16;
      return o.order > this.order ? 4 : 2;
    },
    ...extra,
  });
  const linkBefore = mk("link-before", { focusable: true });
  const tipA = mk("tip-a", { cls: "tip", attrs: { "data-tip": "a" } });
  const btnA = mk("button-a", { focusable: true, dismiss: true, hidden: true }); btnA.parent = tipA;
  const linkAfter = lastTip ? null : mk("link-after", { focusable: true });
  const tipB = mk("tip-b", { cls: "tip", attrs: { "data-tip": "b" } });
  const btnB = mk("button-b", { focusable: true, dismiss: true, hidden: true }); btnB.parent = tipB;
  const main = mk("main");
  btnA.closest = (s) => (s === "[data-tip-dismiss]" ? btnA : s === ".tip" ? tipA : null);
  btnB.closest = (s) => (s === "[data-tip-dismiss]" ? btnB : s === ".tip" ? tipB : null);
  const all = [linkBefore, tipA, btnA, linkAfter, tipB, btnB, main].filter(Boolean);

  const store = {};
  if (stored !== null) store["sweep-tips"] = stored;
  const sessionStorage = {
    getItem(k) { if (throws) throw new Error("denied"); return k in store ? store[k] : null; },
    setItem(k, v) { if (throws) throw new Error("denied"); store[k] = String(v); },
  };
  const listeners = {};
  const document = {
    addEventListener: (t, f) => { (listeners[t] = listeners[t] || []).push(f); },
    querySelectorAll(sel) {
      if (sel === ".tip[data-tip]") return [tipA, tipB];
      if (sel === "[data-tip-dismiss]") return [btnA, btnB];
      if (sel.indexOf("a[href]") === 0) return all.filter((x) => x.focusable);
      return [];
    },
    querySelector: (sel) => (sel === "main" ? main : sel === ".tip[data-tip]" ? tipA : null),
  };
  vm.runInNewContext(SOURCE, { document, window: { sessionStorage } });
  return {
    store, tipA, tipB, btnA, btnB, linkAfter, linkBefore, main,
    ready() { (listeners.DOMContentLoaded || []).forEach((f) => f({})); },
    click(btn) { (listeners.click || []).forEach((f) => f({ target: btn })); },
    clickElsewhere() { (listeners.click || []).forEach((f) => f({ target: { closest: () => null } })); },
  };
}

console.log("on load");
{
  const p = page({ stored: JSON.stringify(["b"]) });
  p.ready();
  ok(p.tipB.hidden === true, "a tip whose id is already dismissed is hidden");
  ok(p.tipA.hidden === false, "a tip that was not dismissed stays");
  ok(p.btnA.hidden === false && p.btnB.hidden === false, "the dismiss buttons are revealed by the script");
}
{
  const p = page({});
  ok(p.btnA.hidden === true && p.btnB.hidden === true, "before the script has run (no JS), the dismiss buttons are still hidden");
  p.ready();
  ok(p.tipA.hidden === false && p.tipB.hidden === false, "nothing stored hides nothing");
}

console.log("dismissing");
{
  const p = page({});
  p.ready();
  p.click(p.btnA);
  ok(p.tipA.hidden === true, "clicking dismiss hides that tip");
  ok(p.tipB.hidden === false, "and only that tip");
  ok(JSON.parse(p.store["sweep-tips"]).join() === "a", "its id is stored");
  ok(p.linkAfter.focused === true, "focus moves to the next focusable after the tip");
  ok(p.linkBefore.focused === false && p.main.focused === false, "not the one before it, and not <main> while something follows");
  p.click(p.btnB);
  ok(JSON.parse(p.store["sweep-tips"]).join() === "a,b", "a second dismiss adds to the list");
  p.click(p.btnB);
  ok(JSON.parse(p.store["sweep-tips"]).join() === "a,b", "dismissing the same id twice does not duplicate it");
}
{
  const p = page({});
  p.ready();
  p.clickElsewhere();
  ok(p.tipA.hidden === false && p.tipB.hidden === false && !("sweep-tips" in p.store) && !p.linkAfter.focused,
     "a click elsewhere hides, stores and focuses nothing");
}
{
  const p = page({ lastTip: true });
  p.ready();
  p.click(p.btnA);
  ok(p.tipA.hidden === true, "(nothing after tip a but tip b) dismiss still hides it");
  ok(p.btnB.focused === true, "the next focusable can be another tip's own button");
}
{
  const p = page({});
  p.ready();
  p.linkAfter.rects = 0;      // display:none somewhere above it
  p.click(p.btnA);
  ok(p.linkAfter.focused === false && p.btnB.focused === true, "a control that is not rendered is skipped");
  p.click(p.btnB);
  ok(p.main.focused === true && p.main.attrs.tabindex === "-1", "with nothing after, focus goes to <main> (made focusable for the hand-off)");
  p.main.listeners.blur({});
  ok(!("tabindex" in p.main.attrs), "and <main> loses the tabindex again when focus leaves");
}

console.log("storage that fails");
{
  const p = page({ throws: true });
  p.ready();
  ok(p.btnA.hidden === false, "storage that throws on read does not stop the buttons appearing");
  p.click(p.btnA);
  ok(p.tipA.hidden === true && p.linkAfter.focused === true, "and a dismiss still hides the tip and moves focus when it cannot write");
}
for (const bad of ["not json", "{\"a\":1}", "\"a\"", "null", "42"]) {
  const p = page({ stored: bad });
  p.ready();
  ok(p.tipA.hidden === false && p.tipB.hidden === false && p.btnA.hidden === false, "stored " + JSON.stringify(bad) + " is ignored");
  p.click(p.btnA);
  ok(JSON.parse(p.store["sweep-tips"]).join() === "a", "and the next dismiss starts a clean list from it");
}

console.log(fails ? `\n${fails} FAILED` : "\nall ok");
process.exit(fails ? 1 : 0);
