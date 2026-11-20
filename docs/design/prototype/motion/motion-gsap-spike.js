/* D7A GSAP spike: the proposed arrival, in gsap. Loaded SYNCHRONOUSLY in <head> after gsap.min.js, which is
   what makes the pre-hide possible before first paint (and what makes the page wait for 73 KB first). Everything
   that the CSS version gets for free is explicit here: the same-screen test, the reduced-motion branch, the
   pre-hide, the failsafe and the cleanup. */
(function () {
  var d = document.documentElement;
  if (!window.gsap) return;                                   // the library did not load: the page is simply there
  try {
    var r = document.referrer ? new URL(document.referrer) : null;
    var nav = performance.getEntriesByType("navigation")[0];
    var same = (r && r.origin === location.origin && r.pathname === location.pathname) || (nav && nav.type !== "navigate");
    if (same) return;
    var mm = gsap.matchMedia();
    mm.add("(prefers-reduced-motion: no-preference)", function () {
      d.classList.add("gsap-arrive");
      var failsafe = setTimeout(function () { d.classList.remove("gsap-arrive"); }, 1200);
      document.addEventListener("DOMContentLoaded", function () {
        var all = document.querySelectorAll("#results-body > .jobs-section:first-child .jobs tbody tr");
        var rows = Array.prototype.slice.call(all, 0, matchMedia("(max-width: 47.99rem)").matches ? 3 : 8);
        gsap.fromTo(rows, { opacity: 0 }, {
          opacity: 1, duration: 0.14, ease: "power2.out", stagger: 0.02,
          /* Not clearProps per tween: that hands each row back to the pre-hide rule the moment ITS tween ends, and the
             row vanishes again until every row is done (it did, in the first version of this spike). The class goes
             first, then the inline styles. */
          onComplete: function () { clearTimeout(failsafe); d.classList.remove("gsap-arrive"); gsap.set(rows, { clearProps: "opacity" }); }
        });
      });
      return function () { d.classList.remove("gsap-arrive"); };   // matchMedia cleanup if the preference flips
    });
  } catch (e) { d.classList.remove("gsap-arrive"); }
})();
