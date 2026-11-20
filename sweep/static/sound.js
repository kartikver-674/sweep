/* Sound (public pages): five quiet moments, on unless the visitor turns them off with the header's speaker switch,
   which this browser remembers (owner, 2026-10-03: on by default). Nothing plays on hover, on its own, or for errors. Every sound is synthesised here (Web Audio),
   so there are no files; none is longer than a second. The takes chosen on the canvas board "A · Quiet sounds":

     swish + tick  the Upload desk: a bristle swish as cards are swept, a light tick per strong match (desk.js)
     swoosh        "Read my résumé": the reading splash opens (going.js)
     ready         a résumé has been read: two marimba notes (reading.js in-page; else on the next page)
     done          the sweep has finished: two bells and a shimmer, on the Results page it hands over to
     key           an Apify key checked out: a latch, on the page after the key screen

   A moment that ends in a page change is queued (sessionStorage) and played by the next page, unless that page shows an
   error. Browsers only let a page make sound after a click on the site; when one refuses, the sound is dropped, never
   played late. */
(function () {
  "use strict";
  var KEY = "sweep-sound", NEXT = "sweep-sound-next", VOLUME = 0.28, LATE_MS = 1500;

  function store(kind) { try { return window[kind]; } catch (e) { return null; } }
  function read(kind, k) { try { var s = store(kind); return s ? s.getItem(k) : null; } catch (e) { return null; } }
  function write(kind, k, v) {
    try { var s = store(kind); if (s) { if (v === null) s.removeItem(k); else s.setItem(k, v); } } catch (e) { /* private mode */ }
  }

  var on = read("localStorage", KEY) !== "off";
  var ac = null, master = null, noise = null;

  function context() {
    if (!ac) {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      ac = new AC();
      master = ac.createGain();
      master.gain.value = VOLUME;
      master.connect(ac.destination);
    }
    return ac;
  }

  function envelope(g, t0, peak, attack, dur) {
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(peak, t0 + attack);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  }
  function swish(t0, dur, f0, f1, q, peak) {
    if (!noise) {
      noise = ac.createBuffer(1, ac.sampleRate, ac.sampleRate);
      var d = noise.getChannelData(0);
      for (var i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    }
    var src = ac.createBufferSource(), bp = ac.createBiquadFilter(), g = ac.createGain();
    src.buffer = noise;
    bp.type = "bandpass"; bp.Q.value = q;
    bp.frequency.setValueAtTime(f0, t0); bp.frequency.exponentialRampToValueAtTime(f1, t0 + dur);
    envelope(g, t0, peak, dur * 0.3, dur);
    src.connect(bp); bp.connect(g); g.connect(master);
    src.start(t0); src.stop(t0 + dur + 0.05);
  }
  function tone(t0, f, dur, peak, type, attack) {
    var o = ac.createOscillator(), g = ac.createGain();
    o.type = type || "sine";
    o.frequency.setValueAtTime(f, t0);
    envelope(g, t0, peak, attack || 0.005, dur);
    o.connect(g); g.connect(master);
    o.start(t0); o.stop(t0 + dur + 0.05);
  }
  function bell(t0, f, dur, peak) {
    tone(t0, f, dur, peak, "sine", 0.006);
    tone(t0, f * 2, dur * 0.5, peak * 0.22, "sine", 0.004);
    tone(t0, f * 3, dur * 0.25, peak * 0.08, "sine", 0.003);
  }
  function wood(t0, f, peak) {
    tone(t0, f, 0.12, peak, "sine", 0.002);
    tone(t0, f * 4, 0.04, peak * 0.2, "sine", 0.001);
  }

  var SOUNDS = {
    tick: function (t) { tone(t, 1760, 0.05, 0.22, "triangle", 0.002); },
    swish: function (t) { swish(t, 0.24, 900, 2600, 0.9, 0.55); },
    swoosh: function (t) { swish(t, 0.4, 500, 3200, 0.8, 0.55); },
    ready: function (t) { wood(t, 659.3, 0.34); wood(t + 0.12, 880, 0.34); },
    done: function (t) { bell(t, 587.33, 0.8, 0.24); bell(t + 0.14, 880, 0.9, 0.24); swish(t + 0.1, 0.6, 4000, 8000, 2, 0.06); },
    key: function (t) { tone(t, 520, 0.05, 0.3, "triangle", 0.002); tone(t + 0.07, 1040, 0.06, 0.26, "triangle", 0.002); }
  };

  function play(name) {
    if (!on || !SOUNDS[name] || !context()) return;
    var asked = Date.now();
    function go() { if (Date.now() - asked < LATE_MS) SOUNDS[name](ac.currentTime + 0.02); }
    if (ac.state === "running") go();
    else if (ac.resume) ac.resume().then(go, function () { /* refused: dropped */ });
  }

  function queue(name) { if (on) write("sessionStorage", NEXT, name); }

  window.sweepSound = { play: play, queue: queue };

  // A form that ends in a moment says so: data-sound-next="key" (the key screen), "ready" (the reading screen).
  document.addEventListener("submit", function (e) {
    var name = e.target && e.target.getAttribute && e.target.getAttribute("data-sound-next");
    if (name && (!e.defaultPrevented || e.sweepHeld)) queue(name);   // going.js holds a submit to paint first
  });

  // A click is what lets a page make sound: wake the context on the first one, for the sounds that come later.
  document.addEventListener("pointerdown", function () {
    if (on && context() && ac.state !== "running" && ac.resume) ac.resume().catch(function () {});
  }, { once: true, capture: true });

  function init() {
    var btn = document.querySelector("[data-sound-toggle]");
    if (btn) {
      btn.setAttribute("aria-pressed", on ? "true" : "false");
      btn.hidden = false;
      btn.addEventListener("click", function () {
        on = !on;
        write("localStorage", KEY, on ? null : "off");
        btn.setAttribute("aria-pressed", on ? "true" : "false");
        if (on) play("tick");   // so it is clear that sound works
      });
    }
    var next = read("sessionStorage", NEXT);
    write("sessionStorage", NEXT, null);
    var failed = Array.prototype.some.call(document.querySelectorAll(".error"), function (el) {
      return el.textContent.trim() !== "";
    });
    if (next && !failed) play(next);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
