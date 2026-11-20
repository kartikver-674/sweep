/* peek.js, the open / close animation for every <details> on a public page, against a stand-in page: when it takes over a click,
   when it leaves the browser's own toggle alone, what it animates, when `open` changes, and that a click during an animation turns
   the run round instead of sticking. Real browsers run it in docs/design (A11 polish evidence).
   PEEK_JS=<path> points the test at a mutated copy (how the mutation check was run).

   The stand-in <details> is 46px tall shut (a 4px border, a 42px summary) and 200px open. An animation is a fake whose progress the
   test sets by hand (`at(0.5)` is half way), and it reports the height the page would be laid out at, which is what a click
   in the middle of an animation measures. */
const fs = require("fs");
const vm = require("vm");
const SOURCE = fs.readFileSync(process.env.PEEK_JS || __dirname + "/../static/peek.js", "utf8");

let fails = 0;
const ok = (cond, msg) => { console.log((cond ? "  ok   " : "  FAIL ") + msg); if (!cond) fails++; };

const CONTROL = /^(A|BUTTON|INPUT|SELECT|TEXTAREA)$/;

function node(tag, extra = {}) {
  const n = {
    tagName: tag, parentNode: null, children: [], style: { overflow: "" }, attrs: {},
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    contains(o) { for (let x = o; x; x = x.parentNode) if (x === this) return true; return false; },
    closest(sel) {
      for (let x = this; x; x = x.parentNode) {
        if (sel === "summary" ? x.tagName === "SUMMARY"
            : (CONTROL.test(x.tagName) && (x.tagName !== "A" || "href" in x.attrs))) return x;
      }
      return null;
    },
    ...extra,
  };
  return n;
}
function add(parent, child) { child.parentNode = parent; parent.children.push(child); return child; }

/* A <details> with a summary and one body. `body` heights: 46 shut, `openH` open. */
function details({ open = false, openH = 200, bodies = 1, noAnimate = false } = {}) {
  const log = [];
  const d = node("DETAILS", {
    open, pin: null, pinOwner: null, animations: [], shutH: 46,
    get offsetHeight() { return this.open ? openH : this.shutH; },
    get clientHeight() { return this.offsetHeight - 4; },
    getBoundingClientRect() { return { height: this.pin !== null ? this.pin : (this.open ? openH : this.shutH) }; },
  });
  const summary = add(d, node("SUMMARY", { offsetHeight: 42 }));
  const kids = [];
  for (let i = 0; i < bodies; i++) kids.push(add(d, node("DIV", { animations: [], animate(kf, o) { return track(this, kf, o); } })));
  function track(el, kf, o) {
    const a = {
      el, kf, o, canceled: false, onfinish: null,
      cancel() { this.canceled = true; if (el.pinOwner === this) { el.pin = null; el.pinOwner = null; } },
      at(f) { if (el === d) { const [a0, a1] = [parseFloat(kf[0].height), parseFloat(kf[1].height)]; d.pin = a0 + (a1 - a0) * f; } },
      finish() { if (!this.canceled && this.onfinish) this.onfinish({}); },
      lateFinish() { if (this.onfinish) this.onfinish({}); },       // an event that arrives after a cancel
    };
    if (el === d) { d.pin = parseFloat(kf[0].height); d.pinOwner = a; }
    log.push(a); el.animations.push(a);
    return a;
  }
  if (!noAnimate) d.animate = function (kf, o) { return track(this, kf, o); };
  return { d, summary, kids, log, shut: (a) => a.el === d };
}

function page({ reduced = false, noMatchMedia = false } = {}) {
  const listeners = [];
  const mq = { matches: reduced };
  const window = noMatchMedia ? {} : { matchMedia: (q) => (q.indexOf("reduce") >= 0 ? mq : { matches: false }) };
  const document = { addEventListener: (t, f, cap) => listeners.push({ t, f, cap }) };
  const getComputedStyle = () => ({ paddingTop: "0px", paddingBottom: "0px", marginTop: "0px", marginBottom: "0px" });
  vm.runInNewContext(SOURCE, { document, window, getComputedStyle, WeakMap });
  return {
    listeners, mq,
    click(target, extra = {}) {
      const e = { target, defaultPrevented: !!extra.defaultPrevented, preventDefault() { this.defaultPrevented = true; } };
      listeners.filter((l) => l.t === "click").forEach((l) => l.f(e));
      return e;
    },
  };
}

console.log("opening");
{
  const p = page(), x = details();
  const e = p.click(x.summary);
  ok(e.defaultPrevented, "a click on a closed summary is taken over (default prevented)");
  ok(x.d.open === true, "`open` is set at once, so the body exists to be shown");
  const grow = x.log.find(x.shut);
  ok(grow && grow.kf[0].height === "46px" && grow.kf[1].height === "200px", "the <details> grows from its shut height to its open height");
  ok(grow.o.duration === 220 && /cubic-bezier\(\.22, \.61, \.36, 1\)/.test(grow.o.easing), "in 220ms, on the house easing");
  const fade = x.log.filter((a) => !x.shut(a));
  ok(fade.length === 1 && fade[0].el === x.kids[0] && fade[0].kf[0].opacity === 0 && fade[0].kf[1].opacity === 1, "the body fades in");
  ok(!x.log.some((a) => a.el === x.summary), "the summary is not animated");
  ok(x.d.style.overflow === "hidden", "the content is clipped while it grows");
  grow.finish();
  ok(x.d.open === true && x.d.style.overflow === "" && x.log.every((a) => a.canceled), "at the end it is open, unclipped, and nothing is left running or held");
}
{
  const p = page(), x = details({ bodies: 3 });
  p.click(x.summary);
  ok(x.log.filter((a) => !x.shut(a)).length === 3, "every part of the body fades, not only the first (the add-key door has a form and a note)");
}
{
  const p = page(), x = details({ openH: 46 });
  const e = p.click(x.summary);
  ok(e.defaultPrevented && x.d.open === true && x.log.length === 0, "a body with nothing to show just opens, with nothing to animate");
}

console.log("closing");
{
  const p = page(), x = details({ open: true });
  const e = p.click(x.summary);
  ok(e.defaultPrevented, "a click on an open summary (open from the server) is taken over too");
  ok(x.d.open === true, "`open` stays while the body is still on screen");
  const grow = x.log.find(x.shut);
  ok(grow.kf[0].height === "200px" && grow.kf[1].height === "46px", "it shrinks from its open height to the summary's own");
  const fade = x.log.filter((a) => !x.shut(a));
  ok(fade.length === 1 && fade[0].kf[0].opacity === 1 && fade[0].kf[1].opacity === 0, "the body fades out");
  ok(x.d.style.overflow === "hidden", "clipped while it shrinks");
  grow.finish();
  ok(x.d.open === false, "`open` is cleared only when the animation ends");
  ok(x.d.style.overflow === "" && x.log.every((a) => a.canceled), "and the clip and the held animations are let go");
}
{
  const p = page(), x = details({ open: true });
  x.d.style.overflow = "auto";
  p.click(x.summary);
  x.log.find(x.shut).finish();
  ok(x.d.style.overflow === "auto", "an overflow the page had set is handed back, not blanked");
}

console.log("when it leaves the click alone");
{
  const p = page({ reduced: true }), x = details();
  const e = p.click(x.summary);
  ok(!e.defaultPrevented && x.d.open === false && x.log.length === 0, "reduced motion: nothing intercepted, the browser toggles it");
  p.mq.matches = false;
  ok(p.click(x.summary).defaultPrevented, "the setting is read at each click, so changing it takes effect at once");
}
{
  const p = page({ noMatchMedia: true }), x = details();
  ok(!p.click(x.summary).defaultPrevented && x.log.length === 0, "no way to ask about motion: native");
}
{
  const p = page(), x = details({ noAnimate: true });
  ok(!p.click(x.summary).defaultPrevented, "no Web Animations: native");
}
{
  const p = page(), x = details();
  ok(!p.click(x.d).defaultPrevented && !p.click(x.kids[0]).defaultPrevented, "a click on the <details> itself or its body is not a summary click");
  p.click(x.summary, { defaultPrevented: true });
  ok(x.log.length === 0 && x.d.open === false, "a click somebody already handled is left alone");
}
{
  const p = page(), x = details();
  const link = add(x.summary, node("A", { attrs: { href: "/x" } }));
  ok(!p.click(link).defaultPrevented && x.log.length === 0, "a link inside a summary is its own click");
  const span = add(x.summary, node("SPAN"));
  ok(p.click(span).defaultPrevented, "a word inside the summary is the summary's");
}
{
  const p = page(), x = details();
  const second = add(x.d, node("SUMMARY"));
  ok(!p.click(second).defaultPrevented, "only the first summary toggles a <details>, as in the browser");
  const lone = add(node("DIV"), node("SUMMARY"));
  ok(!p.click(lone).defaultPrevented, "a summary that is not in a <details> is not ours");
}
ok(page().listeners.length === 1 && page().listeners[0].t === "click" && page().listeners[0].cap === true,
   "one click listener, on the capture phase, so an ancestor's stopPropagation (Why it matched) cannot hide a click from it");

console.log("a click during an animation");
{
  const p = page(), x = details();
  p.click(x.summary);
  const first = x.log.find(x.shut);
  first.at(0.5);                                                // 123px
  const e = p.click(x.summary);
  ok(e.defaultPrevented, "taken over again");
  ok(x.log.filter((a) => a.canceled).length === x.log.length - 2, "the earlier run is cancelled (its height and its fade)");
  const back = x.log.filter(x.shut)[1];
  ok(back.kf[0].height === "123px" && back.kf[1].height === "46px", "it turns round from the height it had reached, not from a jump");
  ok(x.d.open === true, "`open` is still set while it closes");
  ok(x.d.style.overflow === "hidden", "still clipped");
  first.lateFinish();                                           // a late finish from the cancelled run
  ok(x.d.open === true && x.d.style.overflow === "hidden", "a cancelled run that reports late changes nothing");
  back.finish();
  ok(x.d.open === false && x.d.style.overflow === "" && x.log.every((a) => a.canceled), "the second run ends it: closed, unclipped, nothing held");
}
{
  const p = page(), x = details({ open: true });
  p.click(x.summary);
  x.log.find(x.shut).at(0.25);                                  // 200 -> 46: 161.5px
  p.click(x.summary);
  const reopen = x.log.filter(x.shut)[1];
  ok(x.d.open === true, "closing then clicking again keeps it open");
  ok(reopen.kf[0].height === "161.5px" && reopen.kf[1].height === "200px", "and grows back from where it was to full height");
  reopen.finish();
  ok(x.d.open === true && x.d.style.overflow === "", "it ends open and unclipped");
}
{
  const p = page(), x = details();
  for (let i = 0; i < 5; i++) p.click(x.summary);               // five quick clicks: open, close, open, close, open
  x.log.filter(x.shut).pop().finish();
  ok(x.d.open === true && x.d.style.overflow === "" && x.log.every((a) => a.canceled), "five quick clicks end open with nothing stuck");
  const q = page(), y = details();
  for (let i = 0; i < 4; i++) q.click(y.summary);
  y.log.filter(y.shut).pop().finish();
  ok(y.d.open === false && y.d.style.overflow === "", "and four end closed");
}
{
  const p = page(), a = details(), b = details({ open: true });
  p.click(a.summary); p.click(b.summary);
  a.log.find(a.shut).finish();
  ok(a.d.open === true && b.d.open === true && b.d.style.overflow === "hidden", "two disclosures animate on their own runs");
  b.log.find(b.shut).finish();
  ok(b.d.open === false, "finishing one does not settle the other");
}

console.log("nested");
{
  const p = page(), outer = details({ open: true }), inner = details();
  add(outer.d, inner.d);
  p.click(inner.summary);
  ok(inner.d.open === true && outer.log.length === 0 && inner.log.length > 0, "a click in an inner summary toggles the inner <details> only");
}

console.log(fails ? `\n${fails} FAILED` : "\nall ok");
process.exit(fails ? 1 : 0);
