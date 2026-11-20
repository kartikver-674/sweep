/* The brush desk on the public Upload screen (deferred; templates/_desk.html). The page ships the desk finished and still:
   seven made-up listings scattered over it, an empty shortlist, and two buttons that are `hidden`. Without this script that is
   all a visitor sees. Here it comes alive: drag across the desk and every listing the brush passes over is swept. A strong match
   (raw score 40 or more) lands on the shortlist, ranked by score; a weak one fades away and is counted. "Sweep it for me" runs the
   same thing by itself, in reading order; "Start over" puts it back. The desk is aria-hidden illustration, so the two buttons are
   the way in without a pointer, and this script is what reveals them.

   Reduced motion (read each time, so a change of setting takes effect at once): no parallax, no trail, "Sweep it for me" is
   instant. The cards' own travel is a CSS transition that only exists under no-preference.

   Plain DOM, no Alpine. Positions are percentages of the desk, as the markup's data-x / data-y are. */
(function () {
  "use strict";

  var GOOD = 40;                          // a raw score of 40 or more is a strong match
  var SLOT_LEFT = 66, SLOT_TOP = 13, SLOT_STEP = 20.5;   // the shortlist's slots, in % of the desk
  var FIRST = 260, EVERY = 240, SETTLE = 300, TRAIL_FADE = 450;   // ms: "Sweep it for me", and the trail's fade

  function init() {
    var desk = document.querySelector("[data-desk]");
    if (!desk) return;
    var sweepBtn = document.querySelector("[data-desk-sweep]");
    var resetBtn = document.querySelector("[data-desk-reset]");
    var countEl = desk.querySelector("[data-desk-count]");
    var emptyEl = desk.querySelector("[data-desk-empty]");
    var weakEl = desk.querySelector("[data-desk-weak]");
    var trailEl = desk.querySelector("[data-desk-trail]");
    var brushEl = desk.querySelector("[data-desk-brush]");
    var mq = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
    function reduced() { return !!(mq && mq.matches); }

    var cards = [].map.call(desk.querySelectorAll(".jc"), function (el) {
      function n(k) { return parseFloat(el.getAttribute("data-" + k)); }
      return { el: el, x: n("x"), y: n("y"), r: n("r"), d: n("d"), m: n("m"), swept: false };
    });
    var strong = cards.filter(function (c) { return c.m >= GOOD; }).length;

    var px = 0.5, py = 0.5, bx = 50, by = 50;   // pointer (0..1, for the parallax), brush (%)
    var hover = false, down = false, auto = false, trailOn = false, trail = [], timers = [];

    function later(fn, ms) { timers.push(setTimeout(fn, ms)); }

    function render() {
      var rm = reduced();
      var good = cards.filter(function (c) { return c.swept && c.m >= GOOD; })
                      .sort(function (a, b) { return b.m - a.m; });
      var weak = cards.filter(function (c) { return c.swept && c.m < GOOD; }).length;
      cards.forEach(function (c) {
        var left = c.x, top = c.y, tf, op = "1", z = c.d;
        if (c.swept && c.m >= GOOD) {
          var i = good.indexOf(c);
          left = SLOT_LEFT; top = SLOT_TOP + i * SLOT_STEP; tf = "scale(.9) rotate(0deg)"; z = 60 + i;
        } else if (c.swept) {
          left = c.x - 16; top = c.y + 12; tf = "rotate(" + c.r * 4 + "deg) scale(.6)"; op = "0";
        } else {
          var dx = rm ? 0 : (px - 0.5) * -c.d * 1.3, dy = rm ? 0 : (py - 0.5) * -c.d * 1.3;
          tf = "translate(" + dx.toFixed(1) + "px, " + dy.toFixed(1) + "px) rotate(" + c.r + "deg)";
        }
        c.el.style.left = left + "%";
        c.el.style.top = top + "%";
        c.el.style.transform = tf;
        c.el.style.opacity = op;
        c.el.style.zIndex = String(z);
        c.el.classList[c.swept ? "add" : "remove"]("swept");
      });
      if (countEl) countEl.textContent = good.length + " / " + strong;
      if (emptyEl) emptyEl.hidden = good.length > 0;
      if (weakEl) {
        weakEl.hidden = weak === 0;
        weakEl.textContent = weak + (weak === 1 ? " weak match" : " weak matches") + " swept away";
      }
      if (resetBtn) resetBtn.hidden = !cards.some(function (c) { return c.swept; });
      if (trailEl) {
        trailEl.setAttribute("points", trail.map(function (p) { return p[0].toFixed(1) + "," + p[1].toFixed(1); }).join(" "));
        trailEl.style.opacity = trailOn ? "1" : "0";
      }
      if (brushEl) {
        brushEl.style.left = bx.toFixed(1) + "%";
        brushEl.style.top = by.toFixed(1) + "%";
        brushEl.style.opacity = hover || auto ? "1" : "0";
        brushEl.classList[down ? "add" : "remove"]("down");
        brushEl.classList[auto ? "add" : "remove"]("auto");
      }
    }

    function where(e) {
      var r = desk.getBoundingClientRect();
      function clamp(v) { return Math.max(0, Math.min(100, v)); }
      return [clamp((e.clientX - r.left) / r.width * 100), clamp((e.clientY - r.top) / r.height * 100)];
    }

    // What the visitor hears (sound.js, only when they have turned sound on): a swish as cards are swept, at most one
    // every half second, and a light tick for each strong match that lands on the shortlist.
    var lastSwish = 0;
    function heard(fresh) {
      var s = window.sweepSound, now = Date.now();
      if (!s || !fresh.length) return;
      if (now - lastSwish > 500) { s.play("swish"); lastSwish = now; }
      fresh.filter(function (c) { return c.m >= GOOD; }).forEach(function (c, i) {
        later(function () { s.play("tick"); }, 120 + i * 140);
      });
    }

    // The brush sweeps every card whose box (a little larger than the card) it is inside.
    function sweepAt(p) {
      var fresh = [];
      cards.forEach(function (c) {
        if (!c.swept && p[0] > c.x - 3 && p[0] < c.x + 30 && p[1] > c.y - 3 && p[1] < c.y + 21) { c.swept = true; fresh.push(c); }
      });
      heard(fresh);
    }

    desk.addEventListener("pointerdown", function (e) {
      if (auto || (e.button && e.button > 0)) return;
      if (desk.setPointerCapture) { try { desk.setPointerCapture(e.pointerId); } catch (x) { /* not capturable */ } }
      var p = where(e);
      down = true; hover = true; bx = p[0]; by = p[1];
      if (!reduced()) { trail = [p]; trailOn = true; }
      sweepAt(p);
      render();
    });
    desk.addEventListener("pointermove", function (e) {
      if (auto) return;
      var p = where(e);
      px = p[0] / 100; py = p[1] / 100; bx = p[0]; by = p[1]; hover = true;
      if (down) {
        if (!reduced()) trail = trail.concat([p]).slice(-30);
        sweepAt(p);
      }
      render();
    });
    function up() {
      if (!down) return;
      down = false; trailOn = false;
      later(function () { if (!down) { trail = []; render(); } }, TRAIL_FADE);
      render();
    }
    desk.addEventListener("pointerup", up);
    desk.addEventListener("pointercancel", up);
    desk.addEventListener("pointerleave", function () {
      if (down || auto) return;
      hover = false; px = 0.5; py = 0.5;
      render();
    });

    function sweepAll() {
      if (auto) return;
      var rest = cards.filter(function (c) { return !c.swept; })
                      .sort(function (a, b) { return a.y - b.y || a.x - b.x; });
      if (!rest.length) return;
      if (reduced()) {
        rest.forEach(function (c) { c.swept = true; });
        heard(rest);
        render();
        return;
      }
      auto = true; hover = true; bx = rest[0].x + 13.5; by = rest[0].y + 10;
      render();
      rest.forEach(function (c, i) {
        later(function () { c.swept = true; bx = c.x + 13.5; by = c.y + 10; heard([c]); render(); }, FIRST + i * EVERY);
      });
      later(function () { auto = false; hover = false; render(); }, FIRST + rest.length * EVERY + SETTLE);
    }

    function reset() {
      timers.forEach(clearTimeout);
      timers = [];
      cards.forEach(function (c) { c.swept = false; });
      auto = false; hover = false; trail = []; trailOn = false;
      render();
    }

    if (sweepBtn) { sweepBtn.addEventListener("click", sweepAll); sweepBtn.hidden = false; }
    if (resetBtn) resetBtn.addEventListener("click", reset);
    desk.classList.add("desk-live");   // the cursor is the brush only while this script is running
    render();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
