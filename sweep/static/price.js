/* The Configure screen's live price: only the newest answer counts.

   Every change on the form asks POST /estimate to price the form as it now
   stands, and the answers do not come back in the order the questions went: a
   slow early check (a cold dry run, a busy worker) used to land after a quick
   later one and put the older figure on screen, undimmed, under a form that no
   longer said it. So an answer is heard only if no newer question has been
   asked since. A newer change also cancels the older fetch, and whatever the
   older one still manages to report (a price, a 400, a 429, a dropped
   connection) is thrown away: none of it is about the form on screen.

   `stale` is what the figures are dimmed on: from the moment a change is made
   until the newest question is answered with a price. Answered with an error
   instead, the last good figures stay, dimmed, beside the error. The Save is
   the form's own POST and is untouched by any of this; the server prices again
   at Confirm. Loaded before Alpine, which calls sweepPricer.

   soon() is the depth stepper's: each +/- click used to be its own engine dry run, so 25 -> 50 started five on the
   worker at once and the one that counted waited behind the other four. A burst is now one question, asked once
   the clicks stop; from the first click the figures are stale and anything already out no longer counts. */
(function () {
  "use strict";

  const OFFLINE = "Could not reach the estimator — the figures below may be out of date.";
  const UNPRICED = "That could not be priced.";

  const SETTLE_MS = 400;

  /* start: { est, cap, url }, the page's own estimate and the estimate route.
     ask: fetch, and wait: a timer, both replaceable for the test. */
  window.sweepPricer = function (start, ask, wait) {
    ask = ask || ((url, init) => window.fetch(url, init));
    wait = wait || ((fn) => window.setTimeout(fn, SETTLE_MS));
    let asked = 0;        // questions so far: an answer counts only if it answers the last
    let pending = null;   // the last question's AbortController (not state: nothing on screen reads it)
    return {
      est: start.est,
      cap: start.cap,
      busy: false,        // a question is out
      err: null,          // what the newest answer said, when it was not a price
      current: true,      // est is the price of the form as it now stands
      priced: null,       // the form est was priced from, as sent; null = the saved one the page loaded with
      get stale() { return !this.current; },
      /* The one sentence under the figure when the plan does not fit, worded for what is actually true of it
         (D7C). It used to be "That is $X more than your key has" whenever the plan was flagged, which for a visitor's
         paid sweep (flagged by how many searches their accounts can hold, with no shortfall in dollars to state) read
         "That is $0.00 more". Four causes, each said only on the engine's own figures: the paid searches are not
         available; the accounts can run only some of them; the estimate is more than the key's credit; or it is flagged
         and there is no figure to name. "" when there is nothing to say. */
      get overWhy() {
        const e = this.est || {};
        const cov = e.coverage;
        if (e.paid_unavailable) return "Paid searches are temporarily unavailable, so none will start. Nothing is charged.";
        if (e.over_cap && cov && !cov.full) {
          if (cov.no_ceiling_cut) {
            const names = cov.no_ceiling_sites.join(" and ") + " can't run on connected Apify keys yet";
            return cov.placeable_units
              ? names + ", so " + (cov.total_units - cov.placeable_units) + " of these " + cov.total_units + " paid searches are left out."
              : names + ". Untick " + (cov.no_ceiling_sites.length > 1 ? "them" : "it") + " to start the sweep.";
          }
          return cov.placeable_units
            ? "Your connected accounts can run " + cov.placeable_units + " of " + cov.total_units + " of these paid searches."
            : "None of these paid searches fit within the credit on your connected accounts.";
        }
        if (e.over_cap && e.shortfall >= 0.005) return "That is $" + e.shortfall.toFixed(2) + " more than your key has.";
        if (e.over_cap) return "This costs more than your key's credit covers.";
        return "";
      },
      /* The plan ticket (T2), from the newest estimate: the paid boards it searches, and how many paid searches. */
      get boards() {
        const paid = ((this.est || {}).lines || []).filter((l) => !l.free && l.searches);
        return paid.length ? paid.map((l) => l.label || l.site).join(", ") + ", and the free boards" : "Free boards only";
      },
      get paidSearches() {
        return ((this.est || {}).lines || []).reduce((n, l) => n + (l.free ? 0 : l.searches), 0);
      },
      /* A ticket line that changed is written in again: a citrus wash that fades (sweep-a.css, .inked). Not on first
         paint, and not when the value is what it was. The last value lives on the element, so this tracks nothing. */
      ink(el, value) {
        const now = String(value);
        if (el.dataset.was !== undefined && el.dataset.was !== now) {
          el.classList.remove("inked");
          void el.offsetWidth;            // restart the wash on a second change before the first has faded
          el.classList.add("inked");
        }
        el.dataset.was = now;
      },
      soon(form) {
        const mine = ++asked;
        if (pending) pending.abort();
        pending = null;
        this.busy = true;
        this.current = false;
        this.err = null;
        wait(() => { if (mine === asked) this.price(form); });
      },
      price(form) {
        const mine = ++asked;
        if (pending) pending.abort();
        pending = typeof AbortController === "function" ? new AbortController() : null;
        const body = JSON.stringify(Object.fromEntries(new FormData(form)));
        this.busy = true;
        this.current = false;
        this.err = null;
        return ask(start.url, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: body,
          signal: pending ? pending.signal : undefined,
        }).then((r) => r.json().then((d) => ({ ok: r.ok, d: d })))
          .then((res) => {
            if (mine !== asked) return;
            if (res.ok) { this.est = res.d; this.priced = body; this.current = true; }
            else { this.err = res.d.error || UNPRICED; }
          })
          .catch(() => { if (mine === asked) this.err = OFFLINE; })
          .finally(() => { if (mine === asked) this.busy = false; });
      },
    };
  };
})();
