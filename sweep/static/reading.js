/* The unified review page's reader (two or three résumés). It asks the
   server to read the next résumé (POST /derive as JSON: read_next), waits
   for the answer, brings the page up to date, and asks again — so the
   résumés are read one after another while the visitor reviews the ones
   already read. The server chooses which résumé and whether to read at all;
   this only keeps asking while there is something to read, and stops the
   moment the page closes.

   It never asks twice at once, never asks again after a limit refusal (429),
   and while another request is already reading one of this browser's
   résumés (a second tab, or a page reopened mid-read) it looks back every
   few seconds instead. The card open for editing is never touched: typing
   survives every update. */
(function () {
  "use strict";
  var page = document.querySelector("[data-resumes]");
  if (!page) return;
  var BUSY_MS = 3000, SHOW_MS = 600;

  function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  function openCard() { return document.querySelector("[data-card][data-open]"); }

  /* The page as the server now sees it, swapped in piece by piece: every
     card but the open one, the banner's words (so its status line is
     announced as the change it is), and the way on. */
  function refresh() {
    var open = openCard();
    var url = new URL(page.getAttribute("data-review"), location.href);
    if (open) url.searchParams.set("track", open.getAttribute("data-card"));
    return fetch(url, { credentials: "same-origin" })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, "text/html");
        var ids = function (root) {
          return Array.prototype.map.call(root.querySelectorAll("[data-card]"),
            function (el) { return el.getAttribute("data-card"); }).join();
        };
        if (ids(doc) !== ids(document)) {
          // A résumé added, removed or moved elsewhere: start again from the
          // server's page, unless that would throw away an open edit.
          if (!open) location.reload();
          return;
        }
        Array.prototype.forEach.call(document.querySelectorAll("[data-card]"), function (el) {
          if (el === open) return;
          var fresh = doc.querySelector('[data-card="' + el.getAttribute("data-card") + '"]');
          if (fresh) el.replaceWith(document.importNode(fresh, true));
        });
        var banner = document.getElementById("resumes-banner"),
            said = doc.getElementById("resumes-banner");
        if (banner && said) {
          Array.prototype.forEach.call(banner.children, function (el, i) {
            if (said.children[i] && el.textContent !== said.children[i].textContent) {
              el.textContent = said.children[i].textContent;
            }
          });
        }
        var way = document.getElementById("resumes-continue"),
            next = doc.getElementById("resumes-continue");
        if (way && next) way.replaceWith(document.importNode(next, true));
      });
  }

  function read() {
    return fetch(page.getAttribute("data-derive"), {
      method: "POST", credentials: "same-origin",
      headers: { "Accept": "application/json" },
    }).then(function (r) { return r.json(); });
  }

  function run() {
    var answered = false,
        asked = read().then(function (answer) { answered = true; return answer; });
    // The server claims the résumé it reads before calling the model, so a
    // moment in, the page can show which one is being read — once, not a
    // poll, and not at all if the answer came straight back.
    var shown = wait(SHOW_MS).then(function () { if (!answered) return refresh(); });
    return asked.then(function (answer) {
      return shown.then(function () { return answer; });
    }).then(function (answer) {
      if (answer.state === "busy") return wait(BUSY_MS).then(run);
      return refresh().then(function () {
        // A résumé read, or one that could not be: on to the next. Nothing
        // left, or a limit refusal: stop, and ask no more.
        if (answer.state === "read" && window.sweepSound) window.sweepSound.play("ready");
        if (answer.state === "read" || answer.state === "failed") return run();
      });
    }).catch(function () { /* offline, or not JSON: a reload starts again */ });
  }

  if (page.getAttribute("data-reading") === "1") run();
})();
