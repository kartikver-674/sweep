/* The coverage diagram's parallax on /key (public, deferred). The diagram is decoration (aria-hidden) and stays so: this only tells
   the stylesheet where the pointer is inside it, as two numbers from -1 to 1 (--ox, --oy on the diagram), and the stylesheet moves
   the inner ring and the outer ring a few pixels toward it at different depths (sweep-a.css, A6). When the pointer leaves, the
   numbers go back to 0 and the CSS transition eases the rings home. Hovering a board chip (lift, pause) is CSS alone.

   Only on a device whose pointer hovers and is fine (a mouse or a trackpad), and only with motion allowed; both are read at each
   move, so a changed setting takes effect at once. A touch pointer, or reduced motion, sets nothing. Only the choice's diagram:
   the one beside the Deep setup stays still. Plain DOM, no Alpine. */
(function () {
  "use strict";

  function init() {
    var box = document.querySelector(".cov-choose .orbit-box");
    if (!box || !window.matchMedia) return;
    var fine = window.matchMedia("(hover: hover) and (pointer: fine)");
    var calm = window.matchMedia("(prefers-reduced-motion: reduce)");

    function set(x, y) {
      box.style.setProperty("--ox", String(x));
      box.style.setProperty("--oy", String(y));
    }
    function unit(v) { return Math.max(-1, Math.min(1, Math.round(v * 100) / 100)); }

    box.addEventListener("pointermove", function (e) {
      if (!fine.matches || calm.matches || e.pointerType === "touch") return;
      var r = box.getBoundingClientRect();
      if (!r.width || !r.height) return;
      set(unit(((e.clientX - r.left) / r.width) * 2 - 1), unit(((e.clientY - r.top) / r.height) * 2 - 1));
    });
    box.addEventListener("pointerleave", function () { set(0, 0); });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
