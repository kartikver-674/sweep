/* theme.js, the public theme switch, against a stand-in page: what it applies before first paint, what a click stores, and
   when it forgets a choice. The real browsers run it in docs/design (A1 evidence). */
const fs = require("fs");
const vm = require("vm");
const SOURCE = fs.readFileSync(__dirname + "/../static/theme.js", "utf8");

let fails = 0;
const ok = (cond, msg) => { console.log((cond ? "  ok   " : "  FAIL ") + msg); if (!cond) fails++; };

/* One page load. `stored` is what localStorage holds ("throws" makes every access throw); `dark` is the OS scheme. */
function page({ stored = null, dark = false, noMatchMedia = false } = {}) {
  const store = {};
  if (stored !== null && stored !== "throws") store["sweep-theme"] = stored;
  const attrs = {};
  const classes = new Set();
  const listeners = { document: {}, mql: [] };
  const mql = { matches: dark, addEventListener: (t, f) => listeners.mql.push(f) };
  const toggle = { attrs: {}, setAttribute(k, v) { this.attrs[k] = v; }, closest(s) { return s === "[data-theme-toggle]" ? this : null; } };
  const meta = (media) => ({ attrs: { media, content: "" }, getAttribute(k) { return this.attrs[k] || null; }, setAttribute(k, v) { this.attrs[k] = v; } });
  const metas = [meta("(prefers-color-scheme: light)"), meta("(prefers-color-scheme: dark)")];
  const localStorage = {
    getItem(k) { if (stored === "throws") throw new Error("denied"); return k in store ? store[k] : null; },
    setItem(k, v) { if (stored === "throws") throw new Error("denied"); store[k] = String(v); },
    removeItem(k) { if (stored === "throws") throw new Error("denied"); delete store[k]; },
  };
  const document = {
    documentElement: {
      getAttribute: (k) => (k in attrs ? attrs[k] : null),
      setAttribute: (k, v) => { attrs[k] = String(v); },
      removeAttribute: (k) => { delete attrs[k]; },
      classList: { add: (c) => { classes.add(c); }, contains: (c) => classes.has(c) },
    },
    addEventListener: (type, fn) => { (listeners.document[type] = listeners.document[type] || []).push(fn); },
    querySelectorAll: (sel) => (sel === "[data-theme-toggle]" ? [toggle] : sel === 'meta[name="theme-color"]' ? metas : []),
  };
  const window = { localStorage, matchMedia: noMatchMedia ? undefined : () => mql };
  vm.runInNewContext(SOURCE, { document, window });
  return {
    store, attrs, classes, toggle, metas,
    ready() { (listeners.document.DOMContentLoaded || []).forEach((f) => f({})); },
    click() { (listeners.document.click || []).forEach((f) => f({ target: toggle })); },
    clickElsewhere() { (listeners.document.click || []).forEach((f) => f({ target: { closest: () => null } })); },
    os(isDark) { mql.matches = isDark; listeners.mql.forEach((f) => f({})); },
  };
}
const contents = (p) => p.metas.map((m) => m.attrs.content).join(",");

console.log("before first paint");
{
  const p = page({ stored: "dark" });
  ok(p.attrs["data-theme"] === "dark", "a stored dark choice sets data-theme before DOMContentLoaded");
  const q = page({ stored: "light", dark: true });
  ok(q.attrs["data-theme"] === "light", "a stored light choice wins over a dark OS");
  const n = page({});
  ok(!("data-theme" in n.attrs), "nothing stored leaves data-theme off, so the OS decides");
  const bad = page({ stored: "purple" });
  ok(!("data-theme" in bad.attrs), "a stored value that is not light or dark is ignored");
  const t = page({ stored: "throws" });
  ok(!("data-theme" in t.attrs), "a localStorage that throws on read does not break the page");
}

console.log("the js class (A5)");
{
  // sweep-a.css hides a closed reveal only under .skin-a.js, so the class must be there before first paint, whatever else fails.
  ok(page({}).classes.has("js"), "<html> gets the class js before DOMContentLoaded");
  ok(page({ stored: "dark" }).classes.has("js"), "with a remembered theme too");
  ok(page({ stored: "throws" }).classes.has("js"), "with a localStorage that throws on read");
  ok(page({ noMatchMedia: true }).classes.has("js"), "with no matchMedia");
  const p = page({});
  p.ready(); p.click(); p.click();
  ok(p.classes.has("js") && p.classes.size === 1, "pressing the switch neither removes it nor adds another class");
}

console.log("the switch");
{
  const p = page({});
  p.ready();
  ok(p.toggle.attrs["aria-pressed"] === "false", "on a light OS the switch reads off");
  p.click();
  ok(p.attrs["data-theme"] === "dark" && p.store["sweep-theme"] === "dark", "light OS: one press stores dark and applies it");
  ok(p.toggle.attrs["aria-pressed"] === "true", "aria-pressed follows to true");
  p.click();
  ok(!("data-theme" in p.attrs) && !("sweep-theme" in p.store), "pressing back to the OS's own theme forgets the choice");
  ok(p.toggle.attrs["aria-pressed"] === "false", "aria-pressed follows back to false");
  p.clickElsewhere();
  ok(!("data-theme" in p.attrs), "a click anywhere else does nothing");
}
{
  const p = page({ dark: true });
  p.ready();
  ok(p.toggle.attrs["aria-pressed"] === "true", "on a dark OS the switch reads on");
  p.click();
  ok(p.attrs["data-theme"] === "light" && p.store["sweep-theme"] === "light", "dark OS: one press stores light");
  p.click();
  ok(!("data-theme" in p.attrs) && !("sweep-theme" in p.store), "and the next press returns to following the OS");
}
{
  const p = page({ stored: "dark" });
  p.ready();
  ok(p.toggle.attrs["aria-pressed"] === "true", "a remembered dark choice reads on");
  p.click();
  ok(!("data-theme" in p.attrs) && !("sweep-theme" in p.store), "on a light OS, undoing it clears storage and the attribute");
}
{
  const p = page({ stored: "throws" });
  p.ready();
  p.click();
  ok(p.attrs["data-theme"] === "dark", "with storage that throws, a press still switches the page");
  p.click();
  ok(!("data-theme" in p.attrs), "and switches back");
}
{
  const p = page({ noMatchMedia: true });
  p.ready(); p.click();
  ok(p.attrs["data-theme"] === "dark", "with no matchMedia the system counts as light and the switch still works");
}

console.log("theme-color follows");
{
  const p = page({});
  p.ready();
  ok(contents(p) === "#FFF6EE,#151024", "no override: each meta keeps its own scheme's ground");
  p.click();
  ok(contents(p) === "#151024,#151024", "dark override: both metas are the dark ground");
  p.click();
  ok(contents(p) === "#FFF6EE,#151024", "override cleared: each meta is restored");
  const q = page({ stored: "light", dark: true });
  ok(contents(q) === "#FFF6EE,#FFF6EE", "a light override on a dark OS makes both metas the light ground, at load");
}

console.log("the OS changes under an open page");
{
  const p = page({});
  p.ready();
  p.os(true);
  ok(p.toggle.attrs["aria-pressed"] === "true", "with no override the switch follows the OS to dark");
  p.os(false);
  ok(p.toggle.attrs["aria-pressed"] === "false", "and back");
  p.click(); p.os(true);
  ok(p.attrs["data-theme"] === "dark" && p.store["sweep-theme"] === "dark", "a stored choice survives an OS change (it is only forgotten by pressing)");
}

console.log(fails ? `\n${fails} FAILED` : "\nall ok");
process.exit(fails ? 1 : 0);
