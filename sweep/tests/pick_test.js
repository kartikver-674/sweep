/* pick.js, the batch picker: the pure merge and the component around it,
   with a stand-in input and DataTransfer, so what is on screen and what the
   input will send can be compared exactly. */
const fs = require("fs");

global.window = {};
eval(fs.readFileSync(__dirname + "/../static/pick.js", "utf8"));
const { merge } = window.sweepPicker;

let fails = 0;
const ok = (cond, msg) => { console.log((cond ? "  ok   " : "  FAIL ") + msg); if (!cond) fails++; };
const MB = 1048576;
let clock = 1;
const file = (name, size = 100 * 1024) => ({ name, size, lastModified: clock++ });
const names = (files) => files.map((f) => f.name).join(",");

// --- merge ------------------------------------------------------------------
const [a, b, c, d] = ["Default.pdf", "MERN.pdf", "AI.pdf", "Extra.pdf"].map((n) => file(n));
let got = merge([], [a, b, c], 3, 15 * MB, 15);
ok(names(got.files) === "Default.pdf,MERN.pdf,AI.pdf" && !got.bad, "three at once, in the order chosen");

got = merge([a], [b], 3, 15 * MB, 15);
ok(names(got.files) === "Default.pdf,MERN.pdf", "a second pick adds to the first, never replaces it");

got = merge([a, b], [a], 3, 15 * MB, 15);
ok(names(got.files) === "Default.pdf,MERN.pdf" && !got.bad, "the same file picked twice is held once");

got = merge([], [a, b, c, d], 3, 15 * MB, 15);
ok(names(got.files) === "Default.pdf,MERN.pdf,AI.pdf", "a fourth is not held");
ok(/Extra\.pdf was not added: this upload takes up to 3 résumés\./.test(got.bad), "and is named: " + got.bad);

got = merge([a], [b, c], 2, 15 * MB, 15);
ok(names(got.files) === "Default.pdf,MERN.pdf" && /up to 2 résumés/.test(got.bad),
   "one existing résumé leaves room for two");

got = merge([], [b], 1, 15 * MB, 15);
ok(names(got.files) === "MERN.pdf", "room for one holds one");
got = merge([b], [c], 1, 15 * MB, 15);
ok(/up to 1 résumé\./.test(got.bad), "and says so in the singular");

got = merge([], [file("cv.docx"), b], 3, 15 * MB, 15);
ok(names(got.files) === "MERN.pdf" && /cv\.docx is not a PDF/.test(got.bad), "a non-PDF is refused by name");

got = merge([], [file("huge.pdf", 16 * MB)], 3, 15 * MB, 15);
ok(!got.files.length && /huge\.pdf is larger than 15 MB/.test(got.bad), "one file over the limit");

got = merge([file("x.pdf", 8 * MB)], [file("y.pdf", 8 * MB)], 3, 15 * MB, 15);
ok(got.files.length === 1 && /together these PDFs would be over 15 MB/.test(got.bad),
   "the limit is the upload's total");

// --- the component ------------------------------------------------------------
// On the global, not declared here: pick.js is eval'd in this scope, and a
// local class would shadow the global the last case swaps out.
global.DataTransfer = class {
  constructor() { const list = []; this.items = { add: (f) => list.push(f) }; this.files = list; }
};

function mount(room) {
  const picker = { files: [] };
  const vm = Object.assign(window.sweepPicker(room, 15), { $refs: { picker } });
  return { vm, picker, pick: (...fs) => { picker.files = fs; vm.take(); } };
}
const button = (vm) => (vm.files.length > 1 ? "Read " + vm.files.length + " résumés" : "Read my résumé");

let { vm, picker, pick } = mount(3);
pick(a);
ok(button(vm) === "Read my résumé", "one chosen: " + button(vm));
pick(b);                     // the browser replaced the input's files with just this one
ok(names(vm.files) === "Default.pdf,MERN.pdf", "the second pick is added to the list");
ok(names(picker.files) === "Default.pdf,MERN.pdf", "and the input will send both");
ok(button(vm) === "Read 2 résumés", "two chosen: " + button(vm));
vm.drop({ dataTransfer: { files: [c] } });
ok(button(vm) === "Read 3 résumés" && names(picker.files) === "Default.pdf,MERN.pdf,AI.pdf",
   "a drop adds the third");
pick(d);
ok(names(picker.files) === "Default.pdf,MERN.pdf,AI.pdf" && vm.bad, "a fourth cannot be sent");
vm.remove(vm.files.indexOf(b));
ok(names(vm.files) === "Default.pdf,AI.pdf" && names(picker.files) === "Default.pdf,AI.pdf" && !vm.bad,
   "removing one takes it out of the list and the input");
ok(button(vm) === "Read 2 résumés", "and the button says so");
pick(b);
ok(names(picker.files) === "Default.pdf,AI.pdf,MERN.pdf", "re-added, it goes to the end");
picker.files = [];           // a cancelled pick that cleared the input
vm.take();
ok(names(picker.files) === "Default.pdf,AI.pdf,MERN.pdf", "a cancelled pick loses nothing");
ok(vm.size(file("s.pdf", 103 * 1024)) === "103 KB" && vm.size(file("m.pdf", 2.5 * MB)) === "2.5 MB",
   "sizes read as on the one-file picker");

// A browser that cannot set an input's files: the list is what the input holds.
global.DataTransfer = function () { throw new TypeError("not supported"); };
({ vm, picker, pick } = mount(3));
pick(a);
pick(b);
ok(names(vm.files) === "MERN.pdf" && names(picker.files) === "MERN.pdf",
   "without DataTransfer the list never claims more than will be sent");

if (fails) { console.log(fails + " failed"); process.exit(1); }
console.log("all passed");
