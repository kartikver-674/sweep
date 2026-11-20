/* The brush tip's dismiss button (public pages, deferred). The server renders every tip visible and every dismiss
   button `hidden`: without this script the tip just stays. Here we hide tips already dismissed in this tab
   (sessionStorage "sweep-tips", a JSON array of ids), reveal the buttons, and on a dismiss hide the tip, remember
   its id and hand focus to the next control after it (or <main>) so a keyboard user is not dropped on <body>. */
(function () {
  var KEY = "sweep-tips";
  var FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), ' +
                  'textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])';

  function read() {
    try {
      var v = JSON.parse(window.sessionStorage.getItem(KEY));
      return Array.isArray(v) ? v : [];
    } catch (e) { return []; }
  }
  function write(ids) {
    try { window.sessionStorage.setItem(KEY, JSON.stringify(ids)); } catch (e) { /* private mode */ }
  }
  function each(list, fn) { for (var i = 0; i < list.length; i++) fn(list[i]); }

  function nextAfter(tip) {
    var all = document.querySelectorAll(FOCUSABLE);
    for (var i = 0; i < all.length; i++) {
      var pos = tip.compareDocumentPosition(all[i]);
      // 4 = follows the tip, 16 = inside it
      if ((pos & 4) && !(pos & 16) && all[i].getClientRects().length) return all[i];
    }
    return null;
  }

  document.addEventListener("DOMContentLoaded", function () {
    var gone = read();
    each(document.querySelectorAll(".tip[data-tip]"), function (t) {
      if (gone.indexOf(t.getAttribute("data-tip")) >= 0) t.hidden = true;
    });
    each(document.querySelectorAll("[data-tip-dismiss]"), function (b) { b.hidden = false; });
  });

  document.addEventListener("click", function (e) {
    var t = e.target;
    var btn = t && t.closest ? t.closest("[data-tip-dismiss]") : null;
    var tip = btn && btn.closest(".tip");
    if (!tip) return;
    var next = nextAfter(tip);
    tip.hidden = true;
    var id = tip.getAttribute("data-tip"), ids = read();
    if (ids.indexOf(id) < 0) { ids.push(id); write(ids); }
    if (!next) {
      // <main> is not focusable by default; make it so only for this hand-off.
      next = document.querySelector("main");
      if (next) {
        next.setAttribute("tabindex", "-1");
        next.addEventListener("blur", function () { next.removeAttribute("tabindex"); }, { once: true });
      }
    }
    if (next) next.focus();
  });
})();
