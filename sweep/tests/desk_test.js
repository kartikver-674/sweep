/* desk.js, the brush desk on the public Upload screen, against a stand-in page: which cards the brush sweeps, where the strong ones
   land, how the weak ones are counted, what "Sweep it for me" and "Start over" do, and what reduced motion switches off. A real
   browser runs it in docs/design (A4 evidence). DESK_JS=<path> points the test at a mutated copy (how the mutation check was run).

   The stand-in desk is 1000 x 500 CSS pixels, so a pointer at (x%, y%) is clientX = 10x, clientY = 5y. Its seven cards are the
   markup's own, in the template's order: a Kestrel 104, b Pebble 12, c Orrin 55, d Halden 62, e Lumen -3, f Brightwell 47,
   g Tidepool 21 (strong = 40 or more: a, c, d, f). */
const fs = require("fs");
const vm = require("vm");
const SOURCE = fs.readFileSync(process.env.DESK_JS || __dirname + "/../static/desk.js", "utf8");

let fails = 0;
const ok = (cond, msg) => { console.log((cond ? "  ok   " : "  FAIL ") + msg); if (!cond) fails++; };

// x, y, rotation, depth, raw score
const DATA = [[2, 4, -7, 18, 104], [32, 2, 6, 30, 12], [5, 29, 4, 24, 55], [34, 27, -5, 14, 62], [2, 54, 7, 28, -3], [32, 53, -3, 20, 47], [16, 77, -9, 34, 21]];
const [A, B, C, D, E, F, G] = [0, 1, 2, 3, 4, 5, 6];

function page({ reduced = false, loading = true, noDesk = false, noButtons = false } = {}) {
  // fake timers, advanced by hand
  let now = 0, seq = 0;
  const pending = new Map();
  const fakeSetTimeout = (fn, ms) => { const id = ++seq; pending.set(id, { at: now + ms, fn }); return id; };
  const fakeClearTimeout = (id) => { pending.delete(id); };
  const advance = (ms) => {
    const end = now + ms;
    for (;;) {
      let next = null;
      for (const [id, t] of pending) if (t.at <= end && (!next || t.at < next[1].at || (t.at === next[1].at && id < next[0]))) next = [id, t];
      if (!next) break;
      pending.delete(next[0]); now = next[1].at; next[1].fn();
    }
    now = end;
  };

  const mk = (attrs = {}, hidden = false) => ({
    attrs, style: {}, hidden, textContent: "", listeners: {}, classes: new Set(),
    classList: null,
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    addEventListener(t, f) { this.listeners[t] = f; },
  });
  const withClasses = (el) => {
    el.classList = { add: (c) => el.classes.add(c), remove: (c) => el.classes.delete(c), contains: (c) => el.classes.has(c) };
    return el;
  };
  const cards = DATA.map(([x, y, r, d, m]) => withClasses(mk({ "data-x": x, "data-y": y, "data-r": r, "data-d": d, "data-m": m })));
  const count = mk(); count.textContent = "0 / 4";
  const empty = mk();
  const weak = mk({}, true);
  const trail = mk({ points: "" });
  const brush = withClasses(mk());
  const desk = withClasses(mk());
  const sweepBtn = mk({}, true), resetBtn = mk({}, true);
  const captured = [];
  const parts = { "[data-desk-count]": count, "[data-desk-empty]": empty, "[data-desk-weak]": weak, "[data-desk-trail]": trail, "[data-desk-brush]": brush };
  desk.querySelector = (s) => parts[s] || null;
  desk.querySelectorAll = (s) => (s === ".jc" ? cards : []);
  desk.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1000, height: 500 });
  desk.setPointerCapture = (id) => captured.push(id);

  const mq = { matches: reduced };
  const window = { matchMedia: (q) => (q.indexOf("reduce") >= 0 ? mq : { matches: false }) };
  const docListeners = {};
  const document = {
    readyState: loading ? "loading" : "complete",
    addEventListener: (t, f) => { (docListeners[t] = docListeners[t] || []).push(f); },
    querySelector: (s) => (s === "[data-desk]" ? (noDesk ? null : desk)
      : s === "[data-desk-sweep]" ? (noButtons ? null : sweepBtn)
      : s === "[data-desk-reset]" ? (noButtons ? null : resetBtn) : null),
  };
  vm.runInNewContext(SOURCE, { document, window, setTimeout: fakeSetTimeout, clearTimeout: fakeClearTimeout });

  const ev = (x, y, extra) => Object.assign({ clientX: x * 10, clientY: y * 5, pointerId: 7, button: 0 }, extra);
  return {
    desk, cards, count, empty, weak, trail, brush, sweepBtn, resetBtn, captured, mq, advance,
    pendingTimers: () => pending.size,
    ready() { (docListeners.DOMContentLoaded || []).forEach((f) => f({})); },
    down(x, y, extra) { desk.listeners.pointerdown(ev(x, y, extra)); },
    move(x, y) { desk.listeners.pointermove(ev(x, y)); },
    up() { desk.listeners.pointerup({}); },
    cancel() { desk.listeners.pointercancel({}); },
    leave() { desk.listeners.pointerleave({}); },
    clickSweep() { sweepBtn.listeners.click({}); },
    clickReset() { resetBtn.listeners.click({}); },
    swept: () => cards.map((c, i) => (c.classes.has("swept") ? i : -1)).filter((i) => i >= 0),
    tf: (i) => cards[i].style.transform,
  };
}
/* A press-and-release at one point, to sweep what is under it and nothing else. */
const tap = (p, x, y) => { p.down(x, y); p.up(); };
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

console.log("before and after the script starts");
{
  const p = page();
  ok(p.sweepBtn.hidden === true && p.resetBtn.hidden === true, "while the page is loading (and with no JS at all) both buttons stay hidden");
  ok(!p.desk.classes.has("desk-live"), "and the desk does not claim the cursor");
  p.ready();
  ok(p.sweepBtn.hidden === false, "once the script runs, 'Sweep it for me' is revealed");
  ok(p.resetBtn.hidden === true, "'Start over' is not revealed until something is swept");
  ok(p.desk.classes.has("desk-live"), "the desk takes the brush cursor only now (a class added from the script)");
  ok(p.count.textContent === "0 / 4", "the shortlist starts at 0 of the 4 strong matches");
  ok(p.empty.hidden === false && p.weak.hidden === true, "the empty line shows and the weak line does not");
  ok(p.cards[A].style.left === "2%" && p.cards[A].style.top === "4%" && p.cards[G].style.left === "16%" && p.cards[G].style.top === "77%",
     "every card is placed from its data-x / data-y");
  ok(p.tf(A) === "translate(0.0px, 0.0px) rotate(-7deg)" && p.cards[A].style.zIndex === "18", "at rest a card is at its own rotation and depth, with no parallax offset");
  ok(p.brush.style.opacity === "0", "the brush is hidden until the pointer is over the desk");
}
{
  const p = page({ loading: false });
  ok(p.sweepBtn.hidden === false && p.desk.classes.has("desk-live"), "a script that runs after the page is ready starts at once");
}
{
  let threw = false;
  try { page({ noDesk: true }); } catch (e) { threw = true; }
  ok(!threw, "a page without the desk is left alone");
  threw = false;
  try { const p = page({ noButtons: true }); p.ready(); p.down(10, 15); p.up(); } catch (e) { threw = true; }
  ok(!threw, "a desk without its buttons still works");
}

console.log("the hit test");
{
  const p = page(); p.ready();
  p.down(10, 15);
  ok(same(p.swept(), [A]), "pressing at (10, 15) sweeps card a and only a");
  ok(p.captured.join() === "7", "and the desk captures the pointer, so the drag keeps going outside it");
  p.move(35, 15);
  ok(same(p.swept(), [A, B]), "dragging to (35, 15) also sweeps b, which the brush now covers");
  p.move(60, 15);
  ok(same(p.swept(), [A, B]), "dragging on over nothing sweeps nothing");
  p.up();
  p.move(20, 40);
  ok(same(p.swept(), [A, B]), "moving with the button up (hovering) sweeps nothing");
}
{
  const p = page(); p.ready();
  tap(p, 1, 15);
  ok(same(p.swept(), [A]), "the box is 3% larger than the card on its left: (1, 15) is 2% left of a and sweeps it");
}
{
  const p = page(); p.ready();
  tap(p, 35, 60);
  ok(same(p.swept(), [F]), "(35, 60) sweeps f and not e: e's box ends at exactly 35 and the edge is outside it");
}
{
  const p = page(); p.ready();
  tap(p, 50, 40);
  ok(same(p.swept(), [D]), "d alone at (50, 40)");
  tap(p, 10, 40);
  ok(same(p.swept(), [C, D]), "then c alone at (10, 40)");
  tap(p, 10, 40);
  ok(same(p.swept(), [C, D]), "sweeping the same place again changes nothing");
}
{
  const p = page(); p.ready();
  p.down(10, 15, { button: 2 });
  ok(p.swept().length === 0 && p.captured.length === 0, "a right-button press sweeps nothing");
  p.cancel();
  p.down(10, 15);
  p.cancel();
  p.move(35, 15);
  ok(same(p.swept(), [A]), "a cancelled gesture (the page took over to scroll) ends the drag: no more sweeping");
}

console.log("the shortlist");
{
  const p = page(); p.ready();
  tap(p, 50, 40);   // d  62
  tap(p, 10, 15);   // a 104
  tap(p, 50, 70);   // f  47
  tap(p, 10, 40);   // c  55
  ok(p.count.textContent === "4 / 4" && p.empty.hidden === true, "all four strong cards: 4 / 4, and the empty line goes");
  const at = (i) => p.cards[i].style.left + "/" + p.cards[i].style.top;
  ok(at(A) === "66%/13%" && at(D) === "66%/33.5%" && at(C) === "66%/54%" && at(F) === "66%/74.5%",
     "they sit in slots by score, highest first (104, 62, 55, 47), whatever order they were swept in");
  ok(p.tf(A) === "scale(.9) rotate(0deg)" && p.cards[A].style.opacity === "1", "a shortlisted card is scaled to .9, straight, and still visible");
  ok([A, D, C, F].map((i) => p.cards[i].style.zIndex).join() === "60,61,62,63", "and above every card still on the desk (depth 34 at most), in slot order");
  ok(p.weak.hidden === true, "nothing weak was swept, so no weak line");
}
{
  const p = page(); p.ready();
  tap(p, 50, 40); tap(p, 10, 15);
  const first = p.cards[D].style.top;
  tap(p, 10, 40);   // c (55) scores below both, so it takes the third slot
  ok(p.cards[A].style.top === "13%" && p.cards[D].style.top === "33.5%" && p.cards[C].style.top === "54%" && first === "33.5%",
     "a card swept later takes its place by score and the others keep theirs");
}

console.log("weak matches");
{
  const p = page(); p.ready();
  tap(p, 40, 10);    // b  12  (and nothing else at (40, 10))
  ok(same(p.swept(), [B]), "(40, 10) is only b");
  ok(p.count.textContent === "0 / 4" && p.empty.hidden === false, "a weak card does not count and does not fill the shortlist");
  ok(p.weak.hidden === false && p.weak.textContent === "1 weak match swept away", "it is counted, in the singular");
  ok(p.cards[B].style.opacity === "0" && p.cards[B].style.left === "16%" && p.cards[B].style.top === "14%", "and it fades out, drifting down-left of where it lay");
  ok(p.tf(B) === "rotate(24deg) scale(.6)", "turning four times as far as it was lying, and shrinking");
  // The box is the card's own 27% plus 3 either side: g (x16) reaches x 46 and no further. Nothing else is near (46.5, 85).
  { const q = page(); q.ready(); tap(q, 46.5, 85); ok(q.swept().length === 0, "just past g's right edge (46.5, 85) sweeps nothing");
    tap(q, 45.5, 85); ok(same(q.swept(), [G]), "just inside it (45.5, 85) sweeps g"); }
  tap(p, 20, 74.5);  // e -3 and g 21: their boxes overlap here (y 74..75) and f's does not reach
  ok(same(p.swept(), [B, E, G]), "(20, 74.5) sweeps e and g, both weak");
  ok(p.weak.textContent === "3 weak matches swept away", "three weak matches, in the plural");
  ok(p.count.textContent === "0 / 4", "still none on the shortlist");
}

console.log("Sweep it for me");
{
  const p = page(); p.ready();
  p.clickSweep();
  ok(p.swept().length === 0, "nothing is swept in the first instant");
  ok(p.brush.style.left === "45.5%" && p.brush.style.top === "12.0%" && p.brush.style.opacity === "1" && p.brush.classes.has("auto"),
     "the brush glides to the first card in reading order (b, top row, left to right), centre of its box");
  p.advance(259);
  ok(p.swept().length === 0, "a quarter of a second in, nothing yet");
  p.advance(1);
  ok(same(p.swept(), [B]), "260 ms: b, the first in reading order");
  p.advance(240);
  ok(same(p.swept(), [A, B]), "240 ms later: a");
  p.advance(239);
  ok(same(p.swept(), [A, B]), "one tick short of the next: nothing new");
  p.advance(1);
  ok(same(p.swept(), [A, B, D]), "then d, then c, f, e and g in reading order (by row, then by column)");
  ok(p.brush.style.left === "47.5%" && p.brush.style.top === "37.0%", "with the brush over the card just swept");
  p.advance(240 * 3);
  ok(same(p.swept(), [A, B, C, D, E, F]), "six of seven by 1460 ms (c, f, e as it goes)");
  p.advance(240);
  ok(p.swept().length === 7, "all seven swept by 1700 ms");
  ok(p.brush.classes.has("auto"), "the brush is still gliding until the pause after the last");
  p.advance(540);
  ok(!p.brush.classes.has("auto") && p.brush.style.opacity === "0", "and then it puts itself away");
  ok(p.count.textContent === "4 / 4" && p.weak.textContent === "3 weak matches swept away", "4 on the shortlist and 3 swept away");
  ok(p.resetBtn.hidden === false, "'Start over' is revealed once something has been swept");
  ok(p.pendingTimers() === 0, "no timers are left running");
}
{
  const p = page(); p.ready();
  p.clickSweep();
  const n = p.pendingTimers();
  p.clickSweep();
  ok(p.pendingTimers() === n, "pressing it again while it runs adds nothing");
  p.down(10, 15);
  ok(!p.brush.classes.has("down") && p.swept().length === 0 && p.captured.length === 0, "and a pointer press during it is ignored");
  p.advance(5000);
  p.clickSweep();
  ok(p.pendingTimers() === 0, "with nothing left to sweep, pressing it does nothing");
}
{
  const p = page(); p.ready();
  tap(p, 10, 15); tap(p, 50, 40);       // a and d are already on the shortlist
  p.clickSweep();
  p.advance(260 + 240 * 4 + 400);
  ok(p.swept().length === 7 && p.count.textContent === "4 / 4", "it sweeps only what is left, and finishes the shortlist");
}

console.log("Start over");
{
  const p = page(); p.ready();
  p.clickSweep(); p.advance(5000);
  p.clickReset();
  ok(p.swept().length === 0, "every card is back on the desk");
  ok(p.cards[A].style.left === "2%" && p.cards[A].style.top === "4%" && p.tf(A) === "translate(0.0px, 0.0px) rotate(-7deg)" &&
     p.cards[B].style.opacity === "1" && p.cards[A].style.zIndex === "18", "in its own place, at its own angle, visible");
  ok(p.count.textContent === "0 / 4" && p.empty.hidden === false && p.weak.hidden === true, "the shortlist is empty again and the weak line is gone");
  ok(p.resetBtn.hidden === true, "'Start over' hides itself again");
  ok(p.brush.style.opacity === "0" && !p.brush.classes.has("auto"), "and the brush is put away");
}
{
  const p = page(); p.ready();
  p.clickSweep(); p.advance(600);
  const done = p.swept().length;
  p.clickReset();
  ok(p.pendingTimers() === 0, "starting over in the middle of a sweep cancels what was still to come");
  p.advance(5000);
  ok(done > 0 && done < 7 && p.swept().length === 0, "so nothing is swept after it");
  tap(p, 10, 15);
  ok(same(p.swept(), [A]), "and the desk works again");
}

console.log("the brush, the parallax and the trail");
{
  const p = page(); p.ready();
  p.move(100, 100);
  ok(p.brush.style.opacity === "1" && p.brush.style.left === "100.0%" && p.brush.style.top === "100.0%", "the brush follows the pointer over the desk");
  ok(p.tf(A) === "translate(-11.7px, -11.7px) rotate(-7deg)", "an unswept card leans away from the pointer by (pointer - .5) x -depth x 1.3");
  p.move(0, 0);
  ok(p.tf(A) === "translate(11.7px, 11.7px) rotate(-7deg)", "and the other way from the other corner");
  p.leave();
  ok(p.brush.style.opacity === "0" && p.tf(A) === "translate(0.0px, 0.0px) rotate(-7deg)", "leaving the desk puts the brush away and the cards back");
  p.move(10, 15); p.down(10, 15); p.move(11, 16); p.leave();
  ok(p.brush.style.opacity === "1", "but leaving mid-drag keeps the brush (the pointer is captured)");
  ok(p.brush.classes.has("down"), "and it presses down while the button is held");
  p.up();
  ok(!p.brush.classes.has("down"), "and lifts on release");
}
{
  const p = page(); p.ready();
  ok(p.trail.attrs.points === "" && p.trail.style.opacity === "0", "no trail before a drag");
  p.down(10, 15);
  ok(p.trail.attrs.points === "10.0,15.0" && p.trail.style.opacity === "1", "a drag starts one at the press");
  for (let i = 1; i <= 40; i++) p.move(10 + i, 15);
  ok(p.trail.attrs.points.split(" ").length === 30, "it keeps the last 30 points");
  p.up();
  ok(p.trail.style.opacity === "0" && p.trail.attrs.points !== "", "on release it fades out (opacity) with its points still there");
  p.advance(449);
  ok(p.trail.attrs.points !== "", "then clears itself 450 ms later, not before");
  p.advance(1);
  ok(p.trail.attrs.points === "", "and is gone");
}

console.log("reduced motion");
{
  const p = page({ reduced: true }); p.ready();
  p.move(100, 100);
  ok(p.tf(A) === "translate(0.0px, 0.0px) rotate(-7deg)" && p.tf(G) === "translate(0.0px, 0.0px) rotate(-9deg)", "no parallax: cards do not follow the pointer");
  ok(p.brush.style.opacity === "1", "the brush is still the cursor");
  p.move(10, 15); p.down(10, 15); p.move(30, 15);
  ok(p.trail.attrs.points === "" && p.trail.style.opacity === "0", "no trail");
  ok(same(p.swept(), [A, B]), "but dragging still sweeps");
  p.up();
  p.clickReset();
  p.clickSweep();
  ok(p.swept().length === 7 && p.pendingTimers() === 0, "'Sweep it for me' is instant: all seven at once, no timers");
  ok(!p.brush.classes.has("auto") && p.brush.style.opacity === "0", "with no brush gliding about");
  ok(p.count.textContent === "4 / 4" && p.weak.textContent === "3 weak matches swept away" && p.resetBtn.hidden === false, "and the same result");
}
{
  const p = page(); p.ready();
  p.move(100, 100);
  ok(p.tf(A) === "translate(-11.7px, -11.7px) rotate(-7deg)", "(without the preference there is parallax)");
  p.mq.matches = true;
  p.move(100, 100);
  ok(p.tf(A) === "translate(0.0px, 0.0px) rotate(-7deg)", "switching the preference on mid-visit takes effect at once");
}

console.log(fails ? `\n${fails} FAILED` : "\nall ok");
process.exit(fails ? 1 : 0);
