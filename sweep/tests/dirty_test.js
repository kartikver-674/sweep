/* dirty.js, the résumé editor's unsaved-changes guard, against a stand-in page: when it asks, what it asks, what each answer
   does, and everything it must leave alone. The real browsers run the same flows in docs/design/motion-d7b/harness. */
const fs = require("fs");
const SOURCE = fs.readFileSync(__dirname + "/../static/dirty.js", "utf8");

let fails = 0;
const ok = (cond, msg) => { console.log((cond ? "  ok   " : "  FAIL ") + msg); if (!cond) fails++; };

function control(o) {
  return Object.assign({ tagName: "INPUT", type: "text", name: "x", value: "", defaultValue: "", checked: false,
                         defaultChecked: false, disabled: false }, o);
}
function select(name, options) {
  return { tagName: "SELECT", type: "select-one", name, disabled: false, options };
}

/* One page load. `controls` are the editor's fields; returns the handles a test drives. */
function page(controls, { dialog = true, form = true, extraForms = [] } = {}) {
  const log = { assigned: [], requested: [], focused: [], shown: 0 };
  const listeners = { window: {}, document: {}, form: {}, dialog: {} };
  const on = (bucket) => (type, fn) => { (listeners[bucket][type] = listeners[bucket][type] || []).push(fn); };
  const formEl = { elements: controls, addEventListener: on("form"), getAttribute: () => "post", closest: () => null };
  const dlg = {
    returnValue: "", open: false,
    addEventListener: on("dialog"),
    showModal() { this.open = true; log.shown++; },
    close() { this.open = false; (listeners.dialog.close || []).forEach((f) => f({})); },
  };
  if (!dialog) delete dlg.showModal;
  global.window = { addEventListener: on("window") };
  global.location = { origin: "http://t", pathname: "/review", search: "?track=a", assign(u) { log.assigned.push(u); } };
  global.document = {
    querySelector: (sel) => (sel === "form[data-editor]" && form ? formEl : null),
    getElementById: (id) => (id === "leave-guard" && dialog !== null ? dlg : null),
    addEventListener: on("document"),
  };
  global.setTimeout = (fn) => { log.timer = fn; return 1; };
  eval(SOURCE);
  const fire = (bucket, type, ev) => { (listeners[bucket][type] || []).forEach((f) => f(ev)); return ev; };
  const event = (extra) => Object.assign({ defaultPrevented: false, button: 0, preventDefault() { this.defaultPrevented = true; } }, extra);
  const link = (o) => Object.assign({
    href: "http://t/review?track=b", protocol: "http:", origin: "http://t", pathname: "/review", search: "?track=b", hash: "", target: "",
    hasAttribute: () => false, focus() { log.focused.push("link"); }, closest(sel) { return sel === "a[href]" ? this : null; },
  }, o);
  return {
    log, dlg, link,
    click(a, extra) { return fire("document", "click", event(Object.assign({ target: a }, extra))); },
    unload() { return fire("window", "beforeunload", event({ returnValue: undefined })); },
    save() { return fire("form", "submit", event({})); },
    submitOther(f, by) { return fire("document", "submit", event({ target: f, submitter: by })); },
    answer(value) { dlg.returnValue = value; dlg.close(); },
    pageshow(persisted) { return fire("window", "pageshow", { persisted }); },
    backdrop() { return fire("dialog", "click", { target: dlg }); },
  };
}

const years = (value, was) => control({ name: "experience_years", type: "number", value, defaultValue: was });

console.log("an editor nobody has changed asks nothing");
{
  const p = page([years("3", "3"), control({ name: "add_skills" })]);
  const e = p.click(p.link());
  ok(!e.defaultPrevented && p.log.shown === 0, "a link to another résumé goes straight there");
  ok(p.unload().defaultPrevented === false, "closing or reloading the tab is not stopped");
}

console.log("a changed editor stops what would take the page away");
{
  const p = page([years("4", "3")]);
  const e = p.click(p.link());
  ok(e.defaultPrevented && p.log.shown === 1 && p.dlg.open, "the link is held and the question is asked");
  ok(p.log.assigned.length === 0, "and nothing has navigated");
  const u = p.unload();
  ok(u.defaultPrevented && u.returnValue === "", "closing, reloading and Back get the browser's own prompt");
}

console.log("stay keeps the edit and hands focus back; discard leaves");
{
  const p = page([years("4", "3")]);
  p.click(p.link());
  p.answer("stay");
  ok(p.log.assigned.length === 0 && p.log.focused.length === 1, "stay: no navigation, focus back on what was pressed");
  ok(!p.dlg.open, "the question is closed");
  ok(p.click(p.link()).defaultPrevented, "and still dirty: the next press asks again");
  p.answer("");
  ok(p.log.assigned.length === 0, "Escape (an empty answer) is stay too");
  p.click(p.link());
  p.backdrop();
  ok(p.log.assigned.length === 0 && !p.dlg.open, "the backdrop is stay too");

  const q = page([years("4", "3")]);
  q.click(q.link({ href: "http://t/review?track=b" }));
  q.answer("leave");
  ok(q.log.assigned.join() === "http://t/review?track=b", "discard: goes where the link went");
  ok(q.unload().defaultPrevented === false, "and the browser is not asked a second time");
}

console.log("what counts as an edit");
{
  let p = page([years("3.0", "3")]);
  ok(!p.click(p.link()).defaultPrevented, "3 and 3.0 are the same number: not an edit");
  p = page([years("3", "3"), control({ name: "add_skills", value: "  ", defaultValue: "" })]);
  ok(!p.click(p.link()).defaultPrevented, "whitespace typed and nothing else: not an edit");
  p = page([control({ name: "add_skills", value: "terraform", defaultValue: "" })]);
  ok(p.click(p.link()).defaultPrevented, "a skill typed is an edit");
  p = page([control({ name: "drop", type: "checkbox", checked: true, defaultChecked: false })]);
  ok(p.click(p.link()).defaultPrevented, "a ticked removal is an edit");
  p = page([control({ name: "drop", type: "checkbox", checked: false, defaultChecked: false })]);
  ok(!p.click(p.link()).defaultPrevented, "an unticked one is not");
  p = page([select("level", [{ selected: false, defaultSelected: true }, { selected: true, defaultSelected: false }])]);
  ok(p.click(p.link()).defaultPrevented, "a changed select is an edit");
  p = page([control({ name: "term", type: "hidden", value: "a", defaultValue: "b" }),
            control({ name: "weight", value: "9", defaultValue: "1", disabled: true }),
            control({ name: "", value: "9", defaultValue: "1" }),
            control({ name: "go", type: "submit", value: "1", defaultValue: "0" })]);
  ok(!p.click(p.link()).defaultPrevented, "hidden, disabled, unnamed and button controls never count");
  // edited, then put back
  const f = years("4", "3");
  p = page([f]);
  ok(p.click(p.link()).defaultPrevented, "edited: asked");
  p.answer("stay");
  f.value = "3";
  ok(!p.click(p.link()).defaultPrevented && p.unload().defaultPrevented === false, "put back to what it was: clean again, nothing asked");
}

console.log("saving clears it");
{
  const p = page([years("4", "3")]);
  p.save();
  ok(!p.click(p.link()).defaultPrevented, "after Save no link is held");
  ok(p.unload().defaultPrevented === false, "and the page leaving is not stopped: it is being replaced by the answer");
}

console.log("another form on the page that navigates");
{
  const form = { getAttribute: () => "post", closest: () => null, requestSubmit(by) { p.log.requested.push(by); } };
  const by = { focus() { p.log.focused.push("button"); } };
  var p = page([years("4", "3")]);
  const e = p.submitOther(form, by);
  ok(e.defaultPrevented && p.dlg.open, "Leave out, Remove and Try again are held while there are unsaved edits");
  p.answer("leave");
  ok(p.log.requested.length === 1 && p.log.requested[0] === by, "discard re-submits it with the button that was pressed");
  var p = page([years("4", "3")]);
  p.submitOther(form, by);
  p.answer("stay");
  ok(p.log.requested.length === 0 && p.log.focused.join() === "button", "stay: not sent, focus back on the button");
  var p = page([years("4", "3")]);
  ok(!p.submitOther({ getAttribute: () => "dialog", closest: () => null }, null).defaultPrevented, "the guard's own form is never held");
  ok(!p.submitOther({ getAttribute: () => "post", closest: (s) => (s === "dialog" ? {} : null) }, null).defaultPrevented,
     "nor is a form inside a dialog (feedback)");
  var p = page([years("3", "3")]);
  ok(!p.submitOther(form, by).defaultPrevented, "a clean editor holds nothing");
}

console.log("links that do not leave this page are never held");
{
  const p = page([years("4", "3")]);
  const cases = [
    ["a new tab", p.link({ target: "_blank" }), {}],
    ["a download", p.link({ hasAttribute: (k) => k === "download" }), {}],
    ["a modified click", p.link(), { ctrlKey: true }],
    ["a meta click", p.link(), { metaKey: true }],
    ["a shift click", p.link(), { shiftKey: true }],
    ["a middle click", p.link(), { button: 1 }],
    ["a mailto", p.link({ protocol: "mailto:", href: "mailto:a@b.c" }), {}],
    ["a jump within this page", p.link({ pathname: "/review", search: "?track=a", hash: "#skills" }), {}],
  ];
  for (const [name, a, extra] of cases) ok(!p.click(a, extra).defaultPrevented, name);
  ok(p.log.shown === 0, "so the question was never asked");
  ok(p.click(p.link({ target: "_self" })).defaultPrevented, "but a link that stays in this tab is");
  ok(p.click(p.link({ origin: "http://elsewhere", pathname: "/", search: "" })).defaultPrevented, "and so is one to another site");
}

console.log("it degrades without losing the browser's own prompt");
{
  let p = page([years("4", "3")], { dialog: false });
  ok(!p.click(p.link()).defaultPrevented, "no <dialog>: links are left alone");
  ok(p.unload().defaultPrevented, "but closing or reloading is still asked");
  p = page([years("4", "3")], { form: false });
  ok(p.log.shown === 0 && !p.unload().defaultPrevented, "no editor on the page: the script does nothing");
}

console.log("a page restored from the cache asks afresh");
{
  const p = page([years("4", "3")]);
  p.click(p.link()); p.answer("leave");
  p.pageshow(true);
  ok(p.click(p.link()).defaultPrevented, "after a back/forward restore the edit is asked about again");
}

console.log("if the navigation is refused, the question comes back");
{
  const p = page([years("4", "3")]);
  p.click(p.link()); p.answer("leave");
  ok(typeof p.log.timer === "function", "the 'leaving' flag is not kept forever");
  p.log.timer();
  ok(p.click(p.link()).defaultPrevented, "once it lapses the editor is guarded again");
}

console.log(fails ? `\n${fails} FAILED` : "\nall ok");
process.exit(fails ? 1 : 0);
