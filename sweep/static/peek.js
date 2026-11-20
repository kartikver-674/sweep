/* Disclosures that open and close with a short height + opacity animation (public pages, deferred). Every <details> a visitor can
   open on a Direction A page (the peeks, Why it matched, Advanced, the add-key door, the abroad section, the Searches grid, the
   score explainer) is still the browser's own <details>: without this script, or with reduced motion, the browser toggles it
   natively and nothing here runs.

   With motion allowed, a click on a summary (Enter and Space reach us as a click too) is intercepted: the default is prevented and
   we do the toggle ourselves. Opening sets `open` first, so the body exists to be measured, then grows the <details> from its shut
   height to its open height while the body fades in. Closing keeps `open` while the height shrinks and the body fades out, and
   clears it at the end. So the native `toggle` event still fires, once, when `open` really changes, and `open` always reads true
   while any of the body is on screen. Focus is never touched: the summary keeps it.

   A click during an animation turns it round from where it is (the height it has now), so there is no stuck state: one run per
   <details>, cancelled and replaced, and `overflow` is always handed back. The listener is on the capture phase so a click that an
   ancestor stops (Results' "Why it matched" carries @click.stop) still reaches us. Plain DOM, no Alpine. */
(function () {
  "use strict";

  var MS = 220;
  var EASE = "cubic-bezier(.22, .61, .36, 1)";           // sweep.css --ease-settle, the house easing
  var runs = new WeakMap();                              // <details> -> { open, overflow, anims }

  function allowed() {
    var mq = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)");
    return !!mq && !mq.matches;                          // no way to ask is the same as no: let the browser do it
  }

  function firstSummary(d) {
    for (var i = 0; i < d.children.length; i++) if (d.children[i].tagName === "SUMMARY") return d.children[i];
    return null;
  }

  function px(v) { return parseFloat(v) || 0; }

  /* The height of a shut <details>: its borders and padding and the summary. Measured, not toggled, so no second `toggle` event. */
  function shutHeight(d, summary) {
    var cs = getComputedStyle(d), ss = getComputedStyle(summary);
    return (d.offsetHeight - d.clientHeight) + px(cs.paddingTop) + px(cs.paddingBottom) +
           summary.offsetHeight + px(ss.marginTop) + px(ss.marginBottom);
  }

  function settle(d, run) {
    if (runs.get(d) !== run) return;
    runs.delete(d);
    run.anims.forEach(function (a) { a.cancel(); });
    d.style.overflow = run.overflow;
    if (!run.open) d.open = false;
  }

  function toggle(d, summary) {
    var prev = runs.get(d);
    var open = prev ? !prev.open : !d.open;              // mid-animation, "toggle" means: go back
    var from = d.getBoundingClientRect().height;         // where it is right now, at rest or half way
    var overflow = prev ? prev.overflow : d.style.overflow;
    if (prev) { runs.delete(d); prev.anims.forEach(function (a) { a.cancel(); }); d.style.overflow = overflow; }

    if (open) d.open = true;
    var to = open ? d.getBoundingClientRect().height : shutHeight(d, summary);
    if (Math.abs(to - from) < 1) { d.open = open; return; }   // nothing to animate (an empty body)

    var run = { open: open, overflow: overflow, anims: [] };
    runs.set(d, run);
    d.style.overflow = "hidden";
    var opts = { duration: MS, easing: EASE, fill: "forwards" };
    var grow = d.animate([{ height: from + "px" }, { height: to + "px" }], opts);
    run.anims.push(grow);
    for (var i = 0; i < d.children.length; i++) {
      if (d.children[i] === summary) continue;
      run.anims.push(d.children[i].animate(open ? [{ opacity: 0 }, { opacity: 1 }] : [{ opacity: 1 }, { opacity: 0 }], opts));
    }
    grow.onfinish = function () { settle(d, run); };
  }

  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || !allowed()) return;
    var t = e.target;
    var summary = t && t.closest ? t.closest("summary") : null;
    var d = summary && summary.parentNode;
    if (!d || d.tagName !== "DETAILS" || typeof d.animate !== "function" || firstSummary(d) !== summary) return;
    var inner = t.closest("a[href], button, input, select, textarea");
    if (inner && inner !== summary && summary.contains(inner)) return;   // a control inside the summary is its own
    e.preventDefault();
    toggle(d, summary);
  }, true);
})();
