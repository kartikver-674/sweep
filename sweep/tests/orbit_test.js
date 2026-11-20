/* orbit.js, the coverage diagram's pointer parallax on /key, against a stand-in page: what it writes on the diagram (the pointer's place
   in it, -1 to 1), when it writes nothing (a touch pointer, a device that does not hover, reduced motion), and that it lets go when the
   pointer leaves. Real browsers run it in docs/design (key-a.mjs). ORBIT_JS=<path> points the test at a mutated copy. */
const fs = require("fs");
const vm = require("vm");
const SOURCE = fs.readFileSync(process.env.ORBIT_JS || __dirname + "/../static/orbit.js", "utf8");

let fails = 0;
const ok = (cond, msg) => { console.log((cond ? "  ok   " : "  FAIL ") + msg); if (!cond) fails++; };

/* The diagram is 400 x 400 at (100, 50). */
function page({ fine = true, reduced = false, noBox = false, noMatchMedia = false, loading = false } = {}) {
  const props = {};
  const listeners = {};
  const box = {
    style: { setProperty(k, v) { props[k] = v; } },
    getBoundingClientRect: () => ({ left: 100, top: 50, width: 400, height: 400 }),
    addEventListener(t, f) { listeners[t] = f; },
  };
  const mq = { fine: { matches: fine }, reduce: { matches: reduced } };
  const window = noMatchMedia ? {} : { matchMedia: (q) => (q.indexOf("reduce") >= 0 ? mq.reduce : mq.fine) };
  let ready = null;
  const queries = [];
  const document = {
    readyState: loading ? "loading" : "complete",
    addEventListener: (t, f) => { if (t === "DOMContentLoaded") ready = f; },
    querySelector: (s) => { queries.push(s); return noBox ? null : box; },
  };
  vm.runInNewContext(SOURCE, { document, window, String, Math });
  if (loading && ready) ready();
  return {
    props, listeners, mq, queries,
    move(x, y, extra) { listeners.pointermove && listeners.pointermove(Object.assign({ clientX: x, clientY: y, pointerType: "mouse" }, extra)); },
    leave() { listeners.pointerleave && listeners.pointerleave({}); },
  };
}

console.log("a mouse");
{
  const p = page();
  ok(p.queries[0] === ".cov-choose .orbit-box", "it finds the choice's diagram only (never the one beside the setup)");
  p.move(500, 250);                                   // the right edge, mid height
  ok(p.props["--ox"] === "1" && p.props["--oy"] === "0", "the right edge is x = 1, y = 0");
  p.move(100, 50);
  ok(p.props["--ox"] === "-1" && p.props["--oy"] === "-1", "the top left corner is -1, -1");
  p.move(300, 350);
  ok(p.props["--ox"] === "0" && p.props["--oy"] === "0.5", "the middle of the lower half is 0, 0.5");
  p.move(900, -400);
  ok(p.props["--ox"] === "1" && p.props["--oy"] === "-1", "a pointer outside the box (a fast move) is clamped to the edge");
  p.leave();
  ok(p.props["--ox"] === "0" && p.props["--oy"] === "0", "leaving sets both back to 0 (the CSS transition eases the rings home)");
}
console.log("when it does nothing");
{
  const p = page({ fine: false });
  p.move(500, 250);
  ok(!("--ox" in p.props), "a device that does not hover with a fine pointer: nothing written");
}
{
  const p = page({ reduced: true });
  p.move(500, 250);
  ok(!("--ox" in p.props), "reduced motion: nothing written");
  p.mq.reduce.matches = false;
  p.move(500, 250);
  ok(p.props["--ox"] === "1", "the setting is read at each move, so a change takes effect at once");
}
{
  const p = page();
  p.move(500, 250, { pointerType: "touch" });
  ok(!("--ox" in p.props), "a touch pointer: nothing written");
  p.move(500, 250, { pointerType: "pen" });
  ok(p.props["--ox"] === "1", "a pen hovers, so it counts");
}
{
  const p = page({ noBox: true });
  ok(Object.keys(p.listeners).length === 0, "no diagram on the page (the console, another screen): no listeners");
  const q = page({ noMatchMedia: true });
  ok(Object.keys(q.listeners).length === 0, "no way to ask about the pointer: no listeners");
}
{
  const p = page({ loading: true });
  ok(p.queries.length === 1 && Object.keys(p.listeners).length === 2, "a script that runs while the page is loading waits for it");
}
console.log(fails ? `\n${fails} FAILED` : "\nall ok");
process.exit(fails ? 1 : 0);
