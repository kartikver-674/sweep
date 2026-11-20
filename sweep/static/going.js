/* The press that leaves the page: the painted line (every page change) and the reading splash (going.css).

   Started by a left click on a link to another page of this site, or by a form's submit, once every handler that
   might cancel it has run (bubble phase: dirty.js's capture-phase "unsaved edits" question has already had its say).
   Not for: a new tab, a download (a `download` link, or an address ending in a file extension: /export.csv,
   /profile.py), a link within this page, a dialog's form, or a submit no one pressed (requestSubmit() with no
   submitter: the reading page posting itself, which has its own bar). A form marked data-going="splash" gets the
   splash instead of the line. Back to the page from the back/forward cache, it is all undone.

   The page change waits for the line or the splash to be PAINTED (50ms, a few frames):
   once a navigation is under way a browser may stop painting the page it is leaving (Safari does), and a class added
   in the same instant as the submit was never seen, so "Read my résumé" sat on a still page for the whole upload.
   So the press is held, painted, then sent on: a link by its address, a form by form.submit() with the pressed
   button's name and value carried in a hidden field (form.submit() sends no submitter, and many buttons here are
   name="do"), and a button's own formaction lent to the form for that send. Validation and every other handler have
   already run: this listener is the last word on the submit.

   Painted is not enough for the splash: it opens with a reveal that starts as a circle of nothing, and the first
   painted frame of it is that. Safari freezes the page's animations once the upload starts (screen recording,
   2026-10-03), so the form waits for the reveal to END before it is sent (immediately with reduced motion). The line
   starts a fifth of the way along for the same reason: its first frame is already a line.

   The shuffle (V2, the résumé deck): the unified review's form that goes on to the next résumé is marked
   data-going="shuffle". It gets the line AND the shuffle: the front sheet of the deck flies to the back and the sheets
   behind it come up (going.css, is-shuffle), so the page change has something to wait for, as the splash's reveal does.
   "Leave this résumé out" (data-going="toss") is the same move, except the front sheet drops off the pile.
   The form is sent when the front sheet's transform ends (a timer for a tab that runs none; at once, after the paint, with
   reduced motion: there the shuffle is just its end state). */
(function () {
  "use strict";
  var root = document.documentElement;
  if (!document.querySelector("[data-going-line]")) return;
  var splash = document.querySelector("[data-going-splash]");
  var timers = [], carried = [], moved = null;

  function reset() {
    timers.forEach(clearTimeout);
    timers = [];
    carried.forEach(function (el) { if (el.parentNode) el.parentNode.removeChild(el); });   // back from the cache
    carried = [];
    if (moved) { moved[0].setAttribute("action", moved[1]); moved = null; }   // a button's own address, given back
    root.classList.remove("is-going", "is-splash", "is-shuffle", "is-toss");
    Array.prototype.forEach.call(document.querySelectorAll(".going-press"), function (el) {
      el.classList.remove("going-press");
      el.removeAttribute("aria-busy");
    });
  }

  function say(i) {
    Array.prototype.forEach.call(splash.querySelectorAll("[data-say]"), function (s, j) {
      s.classList.toggle("on", j === i);
    });
  }

  function start(pressed, form) {
    reset();
    if (pressed) {
      pressed.classList.add("going-press");
      pressed.setAttribute("aria-busy", "true");
    }
    if (!(splash && form && form.getAttribute("data-going") === "splash")) {
      root.classList.add("is-going");
      var deck = form && form.getAttribute("data-going");
      if (deck === "shuffle" || deck === "toss") root.classList.add("is-shuffle");
      if (deck === "toss") root.classList.add("is-toss");
      return;
    }
    var n = 0;
    Array.prototype.forEach.call(form.querySelectorAll("input[type=file]"), function (i) { n += i.files ? i.files.length : 0; });
    Array.prototype.forEach.call(splash.querySelectorAll("[data-plural]"), function (el) {
      el.textContent = n > 1 ? el.getAttribute("data-plural") : el.getAttribute("data-one");
    });
    // The paper grows out of the button that was pressed.
    if (pressed && pressed.getBoundingClientRect) {
      var r = pressed.getBoundingClientRect();
      splash.style.setProperty("--going-x", Math.round(r.left + r.width / 2) + "px");
      splash.style.setProperty("--going-y", Math.round(r.top + r.height / 2) + "px");
    }
    say(0);
    root.classList.add("is-splash");
    if (window.sweepSound) window.sweepSound.play("swoosh");
    timers.push(setTimeout(function () { say(1); }, 1200));
    timers.push(setTimeout(function () { say(2); }, 2600));
  }

  // A few frames (a frame is ~16ms): enough for the press, the line or the splash to be on screen. A timer rather than
  // frame callbacks, which test_motion keeps out of every script, and which a hidden tab never runs anyway.
  function painted(fn) { setTimeout(fn, 50); }

  // The splash's reveal, finished: its transitionend, or a timer for a tab that runs none (and reduced motion, at once).
  function revealed(fn) {
    var done = false, still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    function once() { if (!done) { done = true; splash.removeEventListener("transitionend", end); fn(); } }
    function end(e) { if (e.target === splash && e.propertyName === "clip-path") once(); }
    if (still) return painted(fn);
    splash.addEventListener("transitionend", end);
    setTimeout(once, 600);
  }

  // The shuffle, finished: the front sheet's transform transitionend, or a timer for a tab that runs none. Reduced motion
  // has no transition to wait for, and the sheets are already where they end.
  function shuffled(fn) {
    var front = document.querySelector("[data-deck-front]"), done = false;
    var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (still || !front) return painted(fn);
    function once() { if (!done) { done = true; front.removeEventListener("transitionend", end); fn(); } }
    function end(e) { if (e.target === front && e.propertyName === "transform") once(); }
    front.addEventListener("transitionend", end);
    timers.push(setTimeout(once, 520));
  }

  function leaves(a) {
    if ((a.target && a.target !== "_self") || a.hasAttribute("download")) return false;
    if (a.origin !== location.origin) return false;
    if (/\.[a-z0-9]{2,5}$/i.test(a.pathname)) return false;
    return !(a.pathname === location.pathname && a.search === location.search && a.hash);
  }

  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target && e.target.closest && e.target.closest("a[href]");
    if (!a || !leaves(a)) return;
    e.preventDefault();
    start(a, null);
    painted(function () { location.assign(a.href); });
  });

  document.addEventListener("submit", function (e) {
    var f = e.target;
    if (e.defaultPrevented || !e.submitter) return;
    if (f.getAttribute("method") === "dialog" || (f.closest && f.closest("dialog"))) return;
    if (f.target && f.target !== "_self") return;
    var by = e.submitter;
    e.sweepHeld = true;          // held to be painted, not refused: sound.js still queues this form's moment
    e.preventDefault();
    start(by, f);
    (root.classList.contains("is-splash") ? revealed : root.classList.contains("is-shuffle") ? shuffled : painted)(function () {
      if (by.name) {
        var carry = document.createElement("input");
        carry.type = "hidden"; carry.name = by.name; carry.value = by.value;
        f.appendChild(carry);
        carried.push(carry);
      }
      // form.submit() goes to the FORM's address, so a button with an address of its own (formaction: the plan ticket's
      // "Add another Apify key" saves the settings instead of starting) lends it to the form for this one send.
      if (by.hasAttribute("formaction")) {
        moved = [f, f.getAttribute("action")];
        f.setAttribute("action", by.formAction);
      }
      HTMLFormElement.prototype.submit.call(f);
    });
  });

  window.addEventListener("pageshow", function (e) { if (e.persisted) reset(); });
})();
