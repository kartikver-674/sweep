/* The public theme switch (and, since A5, the `js` class). Loaded in <head>, not deferred: it sets data-theme on <html> before the first paint, so a
   remembered choice never flashes the other theme. With nothing stored the page opens LIGHT, whatever the OS prefers (the
   owner's call: the light theme is the brand's first look); the switch stores whichever theme the visitor picks. */
(function () {
  var KEY = "sweep-theme";
  var GROUND = { light: "#FFF6EE", dark: "#151024" };
  var root = document.documentElement;
  // A5: the page has JavaScript. sweep-a.css hides a closed reveal (a tuned skill, the experience edit, the extra
  // chips) only under `.skin-a.js`, so without a script everything stays visible and the plain form works; with one,
  // the closed things are already hidden at first paint. Alpine opens them.
  root.classList.add("js");

  function stored() {
    try {
      var v = window.localStorage.getItem(KEY);
      return v === "light" || v === "dark" ? v : null;
    } catch (e) { return null; }
  }
  function store(v) {
    try { if (v) window.localStorage.setItem(KEY, v); else window.localStorage.removeItem(KEY); } catch (e) { /* private mode */ }
  }
  function effective() { return root.getAttribute("data-theme") || "light"; }

  function sync() {
    var now = effective();
    var toggles = document.querySelectorAll("[data-theme-toggle]");
    for (var i = 0; i < toggles.length; i++) toggles[i].setAttribute("aria-pressed", now === "dark" ? "true" : "false");
    var metas = document.querySelectorAll('meta[name="theme-color"]');
    for (var j = 0; j < metas.length; j++) metas[j].setAttribute("content", GROUND[now]);
  }

  root.setAttribute("data-theme", stored() || "light");

  document.addEventListener("click", function (e) {
    var t = e.target;
    if (!t || !t.closest || !t.closest("[data-theme-toggle]")) return;
    var next = effective() === "dark" ? "light" : "dark";
    store(next);
    root.setAttribute("data-theme", next);
    sync();
  });
  document.addEventListener("DOMContentLoaded", sync);
  sync();
})();
