/* Unsaved edits on the résumé editor (Review / Edit): never lost without a choice.

   The editor is one form (`form[data-editor]`): experience, skill weights, removals, added skills and, on the
   console, the profile name. It is DIRTY when any of its controls differs from the value the server rendered it
   with (`defaultValue`, `defaultChecked`), so there is no snapshot to take at the wrong moment, and editing a
   value and putting it back is clean, not dirty. Nothing is asked of a form that has not been changed.

   When it is dirty, anything that would take the page away stops and asks, with two answers in plain words:
     - a link to somewhere else (another résumé's Review or Edit, "All your résumés", the steps, Continue to job
       search, the logo), unless it opens in a new tab, downloads, or only moves within this page;
     - another form on the page that navigates (Leave out, Remove, Try again);
     - closing the tab, reloading, a typed address, the Back button: the browser's own prompt (beforeunload),
       because a page cannot draw its own at that moment.
   The answers are a native <dialog>: "Stay and keep editing" (focused, and what Escape and the backdrop do) and
   "Discard changes and leave". Saving is the form's own submit: it clears the question for good, because the
   page is being replaced by the answer. The script moves no focus except to hand it back to what was pressed
   when the answer is "stay", scrolls nothing, and changes nothing without a script: without one the form
   works exactly as it did. */
(function () {
  "use strict";
  var form = document.querySelector("form[data-editor]");
  if (!form) return;
  var dlg = document.getElementById("leave-guard");
  var leaving = false;                                   // the visitor has chosen, or is saving: nothing more to ask

  function changed(el) {
    if (el.disabled || !el.name) return false;
    var type = String(el.type || "").toLowerCase();
    if (type === "hidden" || type === "submit" || type === "button" || type === "reset" || type === "file") return false;
    if (type === "checkbox" || type === "radio") return el.checked !== el.defaultChecked;
    if (el.tagName === "SELECT") {
      return Array.prototype.some.call(el.options, function (o) { return o.selected !== o.defaultSelected; });
    }
    var now = String(el.value).trim(), was = String(el.defaultValue).trim();
    if (type === "number" && now !== "" && was !== "") return Number(now) !== Number(was);
    return now !== was;
  }

  function dirty() { return Array.prototype.some.call(form.elements, changed); }

  // Closing, reloading, a typed address, Back: the browser's own prompt.
  window.addEventListener("beforeunload", function (e) {
    if (leaving || !dirty()) return;
    e.preventDefault();
    e.returnValue = "";
  });
  // A page restored from the back/forward cache is a fresh question.
  window.addEventListener("pageshow", function (e) { if (e.persisted) leaving = false; });
  // Saving: the page is about to be replaced by the answer.
  form.addEventListener("submit", function () { leaving = true; });

  if (!dlg || typeof dlg.showModal !== "function") return;   // no <dialog>: beforeunload above still stands

  var pending = null;                                       // what the visitor was doing when they were stopped

  function ask(go, trigger) {
    pending = { go: go, trigger: trigger };
    dlg.showModal();
  }

  dlg.addEventListener("close", function () {
    var p = pending, answer = dlg.returnValue;
    pending = null;
    dlg.returnValue = "";
    if (!p) return;
    if (answer === "leave") {
      leaving = true;
      // if the navigation is somehow refused (a download, a blocked popup), the question is open again
      setTimeout(function () { leaving = false; }, 1500);
      p.go();
    } else if (p.trigger && typeof p.trigger.focus === "function") {
      p.trigger.focus();
    }
  });
  // The dialog has no padding of its own, so a click whose target is the dialog landed on the backdrop: stay.
  dlg.addEventListener("click", function (e) { if (e.target === dlg) dlg.close(); });

  function leavesThisPage(a) {
    if ((a.target && a.target !== "_self") || a.hasAttribute("download")) return false;
    if (a.protocol !== "http:" && a.protocol !== "https:") return false;
    return !(a.origin === location.origin && a.pathname === location.pathname && a.search === location.search && a.hash);
  }

  document.addEventListener("click", function (e) {
    if (leaving || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target && e.target.closest && e.target.closest("a[href]");
    if (!a || !leavesThisPage(a) || !dirty()) return;
    e.preventDefault();
    ask(function () { location.assign(a.href); }, a);
  }, true);

  document.addEventListener("submit", function (e) {
    var f = e.target;
    if (leaving || e.defaultPrevented || f === form || !dirty()) return;
    if (f.getAttribute("method") === "dialog" || (f.closest && f.closest("dialog"))) return;   // the guard's own, the feedback form
    e.preventDefault();
    var by = e.submitter;
    ask(function () { if (f.requestSubmit) f.requestSubmit(by || undefined); else f.submit(); }, by);
  }, true);
})();
