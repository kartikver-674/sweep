// A7: Configure and Confirm (public) in a real browser, over the production app on loopback (D7B's harness/app.py).
//   node docs/design/sweep-a/harness/money-a.mjs                         checks only
//   MONEY_A_SHOTS=1 node docs/design/sweep-a/harness/money-a.mjs        also writes screenshots to output/design-A7/money-a/
// Configure (Deep): switching a paid board off re-prices (the figure and the jar dim while stale, the figure is WRITTEN once and the
// jar's fill moves with it, and the fill is the rule: the estimate's share of the credit, 88% = the dashed line); crossing into over
// (est.over_cap false to true) wobbles the jar once, drops the class after the animation, never on first paint, and not at all with
// reduced motion; the phone strip stays in view while the settings scroll and follows the estimate; Quick is a citrus card with no
// jar. Confirm: the ticket's halves side by side at 1440 and stacked at 390; the breakdown peek opens; Start still starts. Both themes,
// four widths for overflow. Nothing here posts a key: the scenarios are the harness's own synthetic sessions.
import fs from 'fs';
import path from 'path';
import { launch, serveApp, visitor, sleep, ROOT, OUT } from '../../motion-d7b/harness/lib.mjs';

const SHOTS = !!process.env.MONEY_A_SHOTS;
const PSHOTS = process.env.POLISH_SHOTS !== '0';        // A11 polish evidence: output/design-A11/polish/ (D7_OUT decides the root)
const polishDir = path.join(OUT, 'polish');
if (PSHOTS) fs.mkdirSync(polishDir, { recursive: true });
const pshot = async (page, name, opts = {}) => { if (PSHOTS) await page.screenshot({ path: path.join(polishDir, name + '.png'), ...opts }); };
const shotDir = path.join(ROOT, 'output', 'design-A7', 'money-a');
if (SHOTS) fs.mkdirSync(shotDir, { recursive: true });

const app = await serveApp({ port: 5487, attach: false });
const browser = await launch();
const out = []; let ok = true;
const check = (name, cond, info) => { out.push(`${cond ? 'ok  ' : 'FAIL'} ${name}${info === undefined ? '' : ' ' + info}`); ok = ok && !!cond; };
const shot = async (page, name) => { if (SHOTS) await page.screenshot({ path: path.join(shotDir, name + '.png'), fullPage: true }); };
const go = async (page, p) => { await page.goto(app.url + p, { waitUntil: 'networkidle' }); await sleep(500); };

// ---- readers ---------------------------------------------------------------------------------------------------------
const est = (page) => page.evaluate(() => { const e = Alpine.$data(document.querySelector('.headline-figure')).est; return { total: e.total, over: !!e.over_cap, unavailable: !!e.paid_unavailable, cov: e.coverage ? { avail: e.coverage.available_usd, full: e.coverage.full } : null }; });
// the brief's rule, from the estimate alone
const rule = (e) => !e.cov ? 0 : (e.cov.avail > 0 ? Math.min(100, e.total / e.cov.avail * 88) : (e.total > 0 ? 100 : 0));
const fillPct = (page) => page.evaluate(() => { const j = document.querySelector('.jar'), f = document.querySelector('.jar-fill'); return f.getBoundingClientRect().height / j.clientHeight * 100; });
const money = (n) => '$' + n.toFixed(2);
// textContent, not innerText: the eyebrow and the stamp are drawn in capitals (text-transform), the words are not
const text = (page, sel) => page.locator(sel).first().textContent().then((t) => t.replace(/\s+/g, ' ').trim());
const visible = (page, sel) => page.locator(sel).first().isVisible();
// Against the viewport the visitor was given, not `innerWidth`: an emulated phone widens its layout viewport to fit overflowing content (A8).
const overflow = (page) => page.evaluate((w) => document.documentElement.scrollWidth - w, page.viewportSize().width);
// Waiting for a re-price is event-driven, never a fixed sleep (a loaded machine made the fixed ones flake): the answer arrives (armed before the
// action), the pricer has taken it (busy off, est current, the figure no longer .updating), the jar's class change and the pour have had their
// frame, and nothing is still animating on the jar (the pour, a wobble).
const settled = async (page) => {
  await page.waitForFunction(() => { const fig = document.querySelector('.headline-figure'); const d = Alpine.$data(fig); return !d.busy && d.current && !fig.classList.contains('updating'); }, null, { timeout: 15000 });
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
  await page.waitForFunction(() => document.querySelector('.jar').getAnimations({ subtree: true }).length === 0, null, { timeout: 15000 });
};
const reprice = async (page, act) => { const answer = page.waitForResponse((r) => r.url().endsWith('/estimate'), { timeout: 15000 }); await act(); await answer; await settled(page); };
// the held answer is still out: the figure (and the jar, or the strip) carries .updating and its dim has finished fading in
const dimmed = (page, sels) => page.waitForFunction((l) => l.every((q) => { const e = document.querySelector(q); return e.classList.contains('updating') && e.getAnimations().length === 0; }), sels, { timeout: 15000 });
const rgb = (page, sel, prop = 'backgroundColor') => page.evaluate(([s, p]) => getComputedStyle(document.querySelector(s))[p], [sel, prop]);
const open = (scenario, o = {}) => visitor(browser, app, scenario, { trace: true, ...o });
// every animation the page has started on the jar, from the harness's own TRACE
const wobbles = (page) => page.evaluate(() => (window.__m ? window.__m.anim.filter((a) => a[0] === 'a-wobble').length : -1));
const stepper = async (page, more) => { await page.getByLabel(more ? 'Five more results per search' : 'Five fewer results per search').click(); };

for (const scheme of ['light', 'dark']) {
  process.env.D7_SCHEME = scheme;
  const T = (s) => `${scheme}/${s}`;

  // ================= Configure, Deep, desktop =====================================================================
  {
    const { ctx, page } = await open('paid', { vp: 'desktop' });
    await go(page, '/configure');
    const e0 = await est(page);
    check(T('configure: eyebrow, headline, lede'),
      (await text(page, 'main .eyebrow')) === 'Step 3 · Deep Sweep' && (await text(page, 'main h1')) === 'Where should we look?'
      && (await text(page, 'main .lede')) === 'Sweep has set these up from your résumés already. Change anything, or carry on.', await text(page, 'main .lede'));
    check(T('configure: the free boards are a chip and the paid boards three toggle chips on one row'),
      (await text(page, '.free-chip')) === '✓ 133 free job boards always on'
      && await page.evaluate(() => { const r = [...document.querySelectorAll('.boards > .choice')].map((c) => c.getBoundingClientRect()); return r.length === 3 && r.every((x) => Math.abs(x.top - r[0].top) < 3); }));
    check(T('configure: only the chosen scope says why'), await page.evaluate(() => [...document.querySelectorAll('[role=radiogroup] .why')].filter((w) => getComputedStyle(w).display !== 'none').length) === 1);
    check(T('configure: the jar is decoration and its fill is the rule'),
      (await page.locator('.jar').getAttribute('aria-hidden')) === 'true' && Math.abs((await fillPct(page)) - rule(e0)) < 0.6, `${(await fillPct(page)).toFixed(2)} vs ${rule(e0).toFixed(2)}`);
    check(T('configure: the credit line is the credit Confirm shows'), (await text(page, '.jar-lim')) === `${money(e0.cov.avail)} available`, await text(page, '.jar-lim'));
    check(T('configure: the fits line is shown and says what Confirm says'), (await visible(page, '.fits')) && (await text(page, '.fits')) === 'Your connected Apify accounts can cover the full Sweep.');
    check(T('configure: the strip is not drawn above 40rem'), !(await visible(page, '.cf-strip')));
    check(T('configure: both peeks are shut, the summary is a peek, the table is in a peek'),
      (await page.locator('.summary-cost details.peek').count()) === 1 && !(await page.locator('.summary-cost details.peek').evaluate((d) => d.open))
      && (await page.locator('.summary-panel > details.peek .tag').count()) >= 3 && (await page.locator('.summary-cost details.peek table.lines').count()) === 1);
    await shot(page, `${scheme}-1-configure-deep`);

    // re-price: hold the answer, switch LinkedIn off
    await app.api('/__latency/estimate/3000');       // long enough that the in-flight state can be read however slow the machine
    await page.evaluate(() => {
      window.__f = []; const fig = document.querySelector('.headline-figure .numeral'), fill = document.querySelector('.jar-fill'), j = document.querySelector('.jar');
      (function tick() { window.__f.push([Math.round(performance.now()), fig.textContent.trim(), +(fill.getBoundingClientRect().height / j.clientHeight * 100).toFixed(2)]); requestAnimationFrame(tick); })();
    });
    const answer = page.waitForResponse((r) => r.url().endsWith('/estimate'), { timeout: 15000 });
    await page.locator('.boards .choice', { hasText: 'LinkedIn' }).click();
    await dimmed(page, ['.headline-figure', '.jar']);
    const mid = await page.evaluate(() => ({ fig: +getComputedStyle(document.querySelector('.headline-figure')).opacity, jar: +getComputedStyle(document.querySelector('.jar')).opacity,
      figCls: document.querySelector('.headline-figure').className, jarCls: document.querySelector('.jar').className, text: document.querySelector('.headline-figure .numeral').textContent.trim(),
      busy: getComputedStyle(document.querySelector('span.sending')).display !== 'none' }));
    check(T('configure: while the check is out the figure and the jar keep the last price, dimmed to .85'),
      mid.figCls.includes('updating') && mid.jarCls.includes('updating') && Math.abs(mid.fig - .85) < .01 && Math.abs(mid.jar - .85) < .01 && mid.text === money(e0.total) && mid.busy, JSON.stringify(mid));
    await answer; await settled(page);
    const e1 = await est(page);
    const f = await page.evaluate(() => window.__f);
    const figs = [...new Set(f.map((x) => x[1]))];
    const firstNew = f.findIndex((x) => x[1] === money(e1.total));
    const moved = f.findIndex((x, i) => i > 0 && Math.abs(x[2] - f[0][2]) > 0.05);
    check(T('configure: the new figure is WRITTEN (two values, the old then the new), never counted'), figs.length === 2 && figs[0] === money(e0.total) && figs[1] === money(e1.total) && e1.total < e0.total, JSON.stringify(figs));
    check(T('configure: the jar starts to pour when the figure changes, not before, and ends on the rule'),
      firstNew > 0 && moved >= firstNew - 1 && Math.abs((await fillPct(page)) - rule(e1)) < 0.6 && (await fillPct(page)) < f[0][2], `figure at frame ${firstNew}, fill moves at ${moved}, ${(await fillPct(page)).toFixed(2)} vs ${rule(e1).toFixed(2)}`);
    check(T('configure: undimmed once answered'), !(await page.locator('.jar').evaluate((j) => j.className.includes('updating'))) && !(await page.locator('.headline-figure').evaluate((j) => j.className.includes('updating'))));
    await app.api('/__latency/estimate/0');
    await ctx.close();
  }

  // ================= Configure, crossing into over: the wobble, once ===============================================
  for (const reduced of [false, true]) {
    const { ctx, page } = await open('edge', { vp: 'desktop', reduced });
    const R = (s) => T(`${reduced ? 'reduced motion' : 'wobble'}: ${s}`);
    await go(page, '/configure');
    const e0 = await est(page);
    const first = await page.evaluate(() => ({ cls: document.querySelector('.jar').className, anims: document.getAnimations().filter((a) => document.querySelector('.jar').contains(a.effect && a.effect.target)).length }));
    check(R('not over on first paint, and the jar has no animation then'), !e0.over && !first.cls.includes('over') && !first.cls.includes('wobble') && first.anims === 0, JSON.stringify(first));
    await page.locator('details.advanced > summary').click(); await sleep(250);
    await reprice(page, () => stepper(page, true));
    const e1 = await est(page);
    const at = { cls: await page.locator('.jar').getAttribute('class'), fill: await fillPct(page), w: await wobbles(page) };
    check(R('five more results per search crosses the credit: est.over_cap, the jar says over, the fill is still under the line'),
      e1.over && at.cls.includes('over') && !e1.cov.full && at.fill < 88 && Math.abs(at.fill - rule(e1)) < 0.6, JSON.stringify({ e1, at }));
    check(R('the sentence says why (placement, not a dollar shortfall)'), /^Your connected accounts can run \d+ of \d+ of these paid searches\.$/.test(await text(page, 'p[x-show="overWhy"]')), await text(page, 'p[x-show="overWhy"]'));
    // (with reduced motion no animation ever ends, so the page's own `wobble` class may stay on the jar: no keyframe is attached to it, which the next check proves)
    check(R(reduced ? 'nothing wobbles: no animation ever starts' : 'it wobbled once, and the class is gone after the animation'),
      reduced ? at.w === 0 : at.w === 1 && !at.cls.includes('wobble'), JSON.stringify(at));
    check(R('the keyframe does not run at all with reduced motion'), (await page.evaluate(() => getComputedStyle(document.querySelector('.jar')).animationName)) === 'none');
    const duration = await page.evaluate(() => getComputedStyle(document.querySelector('.jar-fill')).transitionDuration);
    check(R(reduced ? 'the fill changes at once (no transition)' : 'the fill pours (.6s)'), reduced ? duration === '0s' : duration === '0.6s', duration);
    await shot(page, `${scheme}-2-configure-over${reduced ? '-reduced' : ''}`);
    await reprice(page, () => stepper(page, true));
    check(R('still over and no second wobble'), (await wobbles(page)) === (reduced ? 0 : 1));
    await reprice(page, async () => { await stepper(page, false); await stepper(page, false); });
    const e2 = await est(page);
    check(R('back under: not over, and nothing wobbles on the way out'), !e2.over && !(await page.locator('.jar').getAttribute('class')).includes('over') && (await wobbles(page)) === (reduced ? 0 : 1), JSON.stringify(e2));
    await reprice(page, () => stepper(page, true));
    check(R('over again: ' + (reduced ? 'still nothing moves' : 'a second wobble')), (await wobbles(page)) === (reduced ? 0 : 2), String(await wobbles(page)));
    await ctx.close();
  }

  // ================= Configure, covered / none / unavailable: the jar tells only the estimate's truth ===============
  for (const [scen, label, expect] of [['c_over_one', 'little credit', { over: true }], ['c_none_one', 'almost none', { over: true }]]) {
    const { ctx, page } = await open(scen, { vp: 'desktop' });
    await go(page, '/configure');
    const e = await est(page);
    check(T(`configure (${label}): over is est.over_cap and the fill is the rule`), e.over === expect.over && (await page.locator('.jar').getAttribute('class')).includes('over') && Math.abs((await fillPct(page)) - rule(e)) < 0.6, `${(await fillPct(page)).toFixed(1)} ${JSON.stringify(e)}`);
    check(T(`configure (${label}): the sentence is price.js's`), /^(Your connected accounts can run \d+ of \d+ of these paid searches\.|None of these paid searches fit within the credit on your connected accounts\.)$/.test(await text(page, 'p[x-show="overWhy"]')));
    await shot(page, `${scheme}-3-configure-${scen}`);
    await ctx.close();
  }
  {
    const { ctx, page } = await open('c_paid_one', { vp: 'desktop' });
    await go(page, '/configure');
    await app.api('/__nopaid/1');
    await go(page, '/configure');
    const e = await est(page);
    const cls = await page.locator('.jar').getAttribute('class');
    check(T('configure (paid searches unavailable): an empty, off jar, no credit line, no fits line'),
      e.unavailable && !e.cov && cls.includes('off') && !cls.includes('over') && (await fillPct(page)) === 0 && !(await visible(page, '.jar-lim')) && !(await visible(page, '.fits')), cls);
    check(T('configure (paid searches unavailable): the sentence is price.js\'s'), (await text(page, 'p[x-show="overWhy"]')) === 'Paid searches are temporarily unavailable, so none will start. Nothing is charged.');
    await shot(page, `${scheme}-4-configure-unavailable`);
    await app.api('/__nopaid/0');
    await ctx.close();
  }

  // ================= Configure, Quick ===============================================================================
  {
    const { ctx, page } = await open('free3', { vp: 'desktop' });
    await go(page, '/configure');
    check(T('quick: eyebrow, and the same headline'), (await text(page, 'main .eyebrow')) === 'Step 3 · Quick Sweep' && (await text(page, 'main h1')) === 'Where should we look?');
    const bg = await rgb(page, '.cf-quick .summary-panel');
    check(T('quick: a citrus card (never peach), no jar, no strip, the summary visible'),
      bg === 'rgb(228, 242, 92)' && (await page.locator('.jar').count()) === 0 && (await page.locator('.cf-strip').count()) === 0 && (await visible(page, '.summary-panel dl.summary')), bg);
    check(T('quick: Save and review is the one submit'), (await page.locator('main form button[type=submit]').count()) === 1);
    await shot(page, `${scheme}-5-configure-quick`);
    await ctx.close();
  }

  // ================= Configure, Deep, phone: the strip =================================================================
  {
    const { ctx, page } = await open('paid', { vp: 'mobile' });
    await go(page, '/configure');
    const e0 = await est(page);
    const strip = page.locator('.cf-strip');
    check(T('phone: the strip is a link to the cost, not a button, and the form keeps one submit'),
      (await strip.evaluate((a) => a.tagName)) === 'A' && (await strip.getAttribute('href')) === '#cost-h' && (await page.locator('main form button[type=submit]').count()) === 1);
    check(T('phone: the strip says Estimated cost and the live figure'), (await text(page, '.cf-strip-t')) === 'Estimated cost' && (await text(page, '.cf-strip-v')) === money(e0.total), await text(page, '.cf-strip-v'));
    await page.evaluate(() => window.scrollTo(0, 700)); await sleep(300);
    const r = await strip.boundingBox(); const vh = await page.evaluate(() => innerHeight);
    check(T('phone: scrolling the settings, the strip stays pinned to the foot of the screen'), r && Math.abs(r.y + r.height - vh) <= 2 && (await page.evaluate(() => scrollY)) >= 600, JSON.stringify({ r, vh }));
    await app.api('/__latency/estimate/3000');
    const answer = page.waitForResponse((r) => r.url().endsWith('/estimate'), { timeout: 15000 });
    await page.locator('.boards .choice', { hasText: 'LinkedIn' }).click();
    await dimmed(page, ['.headline-figure']); await page.waitForFunction(() => document.querySelector('.cf-strip-v').getAnimations().length === 0, null, { timeout: 15000 });
    const dim = await page.evaluate(() => +getComputedStyle(document.querySelector('.cf-strip-v')).opacity);
    check(T('phone: while the check is out the strip keeps the last price, dimmed'), Math.abs(dim - .85) < .02 && (await text(page, '.cf-strip-v')) === money(e0.total), String(dim));
    await answer; await settled(page);
    const e1 = await est(page);
    check(T('phone: the strip follows the estimate'), e1.total !== e0.total && (await text(page, '.cf-strip-v')) === money(e1.total), `${await text(page, '.cf-strip-v')} vs ${money(e1.total)}`);
    await app.api('/__latency/estimate/0');
    await strip.click(); await sleep(700);
    const where = await page.evaluate(() => { const h = document.getElementById('cost-h').getBoundingClientRect(); return h.top >= 0 && h.bottom <= innerHeight; });
    check(T('phone: the strip takes you to the cost'), where);
    await shot(page, `${scheme}-6-configure-phone`);
    await ctx.close();
  }

  // ================= Confirm: the ticket =================================================================================
  for (const [scen, label, tone] of [['c_paid_one', 'covered', 'rgb(255, 179, 138)'], ['c_over_multi', 'partly covered', 'rgb(255, 179, 138)'], ['c_free_one', 'free', 'rgb(228, 242, 92)']]) {
    for (const vp of ['desktop', 'mobile']) {
      const { ctx, page } = await open(scen, { vp });
      await go(page, '/confirm');
      const box = (sel) => page.locator(sel).first().boundingBox();
      const what = await box('.confirm > .what'), decide = await box('.confirm > .decide');
      const wide = vp === 'desktop';
      check(T(`confirm ${label} ${vp}: the halves are ${wide ? 'side by side, one height' : 'stacked, one left edge'}`),
        wide ? Math.abs(what.y - decide.y) < 2 && decide.x >= what.x + what.width - 2 && Math.abs(what.height - decide.height) < 2
          : decide.y >= what.y + what.height - 2 && Math.abs(what.x - decide.x) < 2, JSON.stringify({ what, decide }));
      const bg = await rgb(page, '.confirm > .decide');
      check(T(`confirm ${label} ${vp}: the stub is ${tone === 'rgb(228, 242, 92)' ? 'citrus (free)' : 'peach (money)'}`), bg === tone, bg);
      check(T(`confirm ${label} ${vp}: back link, stamp, lede`),
        (await text(page, 'main .tlink')) === '← Change something' && (await text(page, '.what .stamp')) === 'Not started'
        && (await text(page, 'main h1')) === 'Ready when you are.' && (await text(page, 'main .lede')) === `Here’s your sweep, on one ticket. Nothing has been ${scen === 'c_free_one' ? 'started' : 'charged'} yet.`);
      check(T(`confirm ${label} ${vp}: the duration note is in the stub, under the form`),
        await page.evaluate(() => { const n = [...document.querySelectorAll('.decide > p.muted')].find((p) => p.textContent.includes('Searching takes a few minutes')); const f = document.querySelector('.decide form.start'); return !!n && !!f && (f.compareDocumentPosition(n) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0; }));
      if (scen !== 'c_free_one') {
        const peek = page.locator('.decide > details.peek');
        check(T(`confirm ${label} ${vp}: the breakdown peek is shut, and opens onto the table and its sentence`),
          !(await peek.evaluate((d) => d.open)) && !(await visible(page, '.decide .peek table.lines')));
        await peek.locator('summary').click(); await sleep(250);
        check(T(`confirm ${label} ${vp}: ...opened`), (await visible(page, '.decide .peek table.lines')) && (await text(page, '.decide .peek-body')).includes('The figure is an estimate from measured per-search rates'));
        const peekBox = await box('.decide .peek');
        check(T(`confirm ${label} ${vp}: ...and the open peek stays inside the stub`), await page.evaluate(() => { const p = document.querySelector('.decide .peek').getBoundingClientRect(), d = document.querySelector('.decide').getBoundingClientRect(); return p.left >= d.left && p.right <= d.right; }), JSON.stringify(peekBox));
      }
      check(T(`confirm ${label} ${vp}: one primary in the stub, one submit before the key door`), (await page.locator('.decide .primary').count()) === 1 && (await page.locator('main form button[type=submit]').first().evaluate((b) => !!b.closest('.decide'))));
      await shot(page, `${scheme}-7-confirm-${scen}-${vp}`);
      await ctx.close();
    }
  }
  {
    const { ctx, page } = await open('c_paid_one', { vp: 'desktop' });
    await go(page, '/confirm');
    const btn = page.locator('main form button[type=submit]').first();
    const label = (await btn.innerText()).replace(/\s+/g, ' ').trim();
    await Promise.all([page.waitForURL('**/running', { timeout: 20000 }), btn.click()]);
    check(T('confirm: the Start button still starts'), /^Start Deep Sweep · \$\d+\.\d\d/.test(label) && new URL(page.url()).pathname === '/running', `${label} -> ${new URL(page.url()).pathname}`);
    await ctx.close();
  }
}

// ================= A11 polish: the rail beside the ticket, and the stamp that flips when Start is pressed ===================================
for (const scheme of ['light', 'dark']) {
  process.env.D7_SCHEME = scheme;
  const T = (s) => `${scheme}/A11/6 ${s}`;
  const lit = (page) => page.evaluate(() => [...document.querySelectorAll('.cf-next li')].map((li) => ({ bg: getComputedStyle(li).backgroundColor, tick: +getComputedStyle(li, '::after').opacity, num: +getComputedStyle(li, '::before').opacity })));
  const litCount = (l, plain) => l.filter((x) => x.tick > 0.95 && x.num < 0.05 && x.bg !== plain).length;
  for (const [scen, name] of [['c_paid_one', 'Deep'], ['c_free_one', 'Quick']]) {
    const { ctx, page } = await open(scen, { vp: 'desktop' });
    await go(page, '/confirm');
    const g = await page.evaluate(() => { const r = (s) => document.querySelector(s).getBoundingClientRect(); const rail = document.querySelector('.cf-next');
      return { t: r('.confirm'), rail: r('.cf-next'), disp: getComputedStyle(rail).display, h: rail.querySelector('h2').textContent, items: [...rail.querySelectorAll('li')].map((li) => li.textContent.trim()), tag: rail.tagName, ol: !!rail.querySelector('ol'), tab: rail.getAttribute('tabindex'), sw: document.documentElement.scrollWidth,
        nums: [...rail.querySelectorAll('li')].map((li) => getComputedStyle(li, '::before').content) }; });
    check(T(`${name} 1440: the rail is on the right of the ticket, at its top`), g.disp !== 'none' && g.rail.left >= g.t.right + 20 && Math.abs(g.rail.top - g.t.top) < 40 && g.rail.width >= 220 && g.rail.width <= 280, JSON.stringify({ t: [g.t.left, g.t.right, g.t.top], rail: [g.rail.left, g.rail.width, g.rail.top] }));
    check(T(`${name} 1440: "What happens next", an ordered list of the three steps`), g.h === 'What happens next' && g.ol && g.items.join('|') === 'Sweep searches the boards|Scores every job against your résumé|Your shortlist, best first', g.items.join('|'));
    check(T(`${name} 1440: the numbers are drawn, not written (the list reads as sentences)`), g.nums.join(',') === 'counter(nx),counter(nx),counter(nx)', g.nums.join(','));
    check(T(`${name} 1440: no horizontal scroll with the rail`), g.sw <= 1440, String(g.sw));
    const plain = await lit(page);
    check(T(`${name} 1440: at rest all three are plain (no tick, numbers shown)`), plain.every((x) => x.tick === 0 && x.num === 1), JSON.stringify(plain));
    await pshot(page, `${scheme}-6-confirm-rail-${name.toLowerCase()}-desktop`);
    // hover: they light up in turn
    const rb = await page.locator('.cf-next').boundingBox();
    await page.mouse.move(rb.x + rb.width / 2, rb.y + 30, { steps: 3 });
    await sleep(120); const a1 = await lit(page);
    await sleep(520); const a2 = await lit(page);
    await sleep(1100); const a3 = await lit(page);
    const p0 = plain[0].bg;
    check(T(`${name} 1440: hovering lights the steps one after the other (${litCount(a1, p0)} -> ${litCount(a2, p0)} -> ${litCount(a3, p0)})`),
      litCount(a1, p0) <= 1 && litCount(a2, p0) >= 1 && litCount(a2, p0) < 3 && litCount(a3, p0) === 3, JSON.stringify([a1.map((x) => x.tick), a2.map((x) => x.tick), a3.map((x) => x.tick)]));
    check(T(`${name} 1440: a lit step has a tint and a tick in place of its number`), a3.every((x) => x.bg !== p0 && x.tick === 1 && x.num === 0), JSON.stringify(a3[0]));
    await pshot(page, `${scheme}-6-confirm-rail-${name.toLowerCase()}-hover`);
    await page.mouse.move(40, 40, { steps: 3 }); await sleep(1900);
    const back = await lit(page);
    check(T(`${name} 1440: moving away puts them back`), back.every((x) => x.tick === 0 && x.num === 1 && x.bg === p0), JSON.stringify(back));
    // not a tab stop (A11 review): nothing in the rail can be acted on, and its words read the same unlit
    check(T(`${name} 1440: the rail is not a tab stop`), (await page.evaluate(() => document.querySelector('.cf-next').getAttribute('tabindex'))) === null);
    await ctx.close();
  }
  {   // widths: 1200 shows it, 1199 and a phone do not
    const { ctx, page } = await open('c_paid_one', { vp: 'desktop' });
    for (const [w, want] of [[1200, true], [1199, false], [1024, false], [768, false], [390, false]]) {
      await page.setViewportSize({ width: w, height: 900 });
      await go(page, '/confirm');
      const g = await page.evaluate(() => [getComputedStyle(document.querySelector('.cf-next')).display !== 'none', document.documentElement.scrollWidth]);
      check(T(`${w}px: the rail is ${want ? 'beside the ticket' : 'not drawn'}, no horizontal scroll`), g[0] === want && g[1] <= w, JSON.stringify(g));
      if (w === 1200) { const t = await page.evaluate(() => { const a = document.querySelector('.confirm').getBoundingClientRect(), b = document.querySelector('.cf-next').getBoundingClientRect(); return [a.right, b.left, b.right]; }); check(T('1200px: the ticket gave the rail its room (rail fully on screen, ticket narrower than 62rem)'), t[2] <= 1200 && t[1] >= t[0] + 20 && t[0] < 40 + 992, JSON.stringify(t)); await pshot(page, `${scheme}-6-confirm-rail-1200`); }
    }
    await ctx.close();
  }
  {   // reduced motion: the steps are shown plainly and stay so
    const { ctx, page } = await open('c_paid_one', { vp: 'desktop', reduced: true });
    await go(page, '/confirm');
    const rb = await page.locator('.cf-next').boundingBox();
    await page.mouse.move(rb.x + rb.width / 2, rb.y + 30, { steps: 3 }); await sleep(1500);
    const l = await lit(page);
    check(T('reduced motion: hovering the rail changes nothing: three plain steps with their numbers'), l.every((x) => x.tick === 0 && x.num === 1), JSON.stringify(l));
    check(T('reduced motion: ...and they are all there to read'), (await page.locator('.cf-next li').allInnerTexts()).length === 3 && await visible(page, '.cf-next li:last-child'));
    await ctx.close();
  }
  // the stamp: Start flips it while the submit goes straight out and the navigation still happens
  for (const [scen, reduced] of [['c_paid_one', false], ['c_free_one', false], ['c_paid_one', true]]) {
    const { ctx, page } = await open(scen, { vp: 'desktop', reduced });
    await ctx.addInitScript(() => { document.addEventListener('submit', (e) => {
      if (!e.target.classList || !e.target.classList.contains('start')) return;
      const rec = (tag) => { const s = document.querySelector('.what .stamp'), b = e.target.querySelector('button[type=submit]'); const l = JSON.parse(sessionStorage.getItem('__st') || '{}');
        l[tag] = { t: s.textContent.trim(), cls: s.className, names: s.getAnimations().map((a) => a.animationName), dis: b.disabled, sending: getComputedStyle(e.target.querySelector('.sending')).display !== 'none' }; sessionStorage.setItem('__st', JSON.stringify(l)); };
      setTimeout(() => rec('t120'), 120); }, true); });
    await go(page, '/confirm');
    const before = await page.evaluate(() => { const s = document.querySelector('.what .stamp'); return { t: s.textContent.trim(), cls: s.className, anim: s.getAnimations().length, form: document.querySelector('form.start').outerHTML.length }; });
    check(T(`${scen}${reduced ? ' (reduced)' : ''}: the stamp says "Not started" until Start`), before.t === 'Not started' && !/\bsent\b/.test(before.cls) && before.anim === 0, JSON.stringify(before));
    const hits = []; let clicked = 0;
    await page.route('**/run', async (route) => { hits.push(Date.now() - clicked); await sleep(1500); await route.continue(); });
    const btn = page.locator('main form.start button[type=submit]').first();
    clicked = Date.now();
    const nav = page.waitForURL('**/running', { timeout: 25000 });
    await btn.click({ noWaitAfter: true });     // the held POST is not waited for; the page records the stamp itself, 120ms after the submit, into sessionStorage
    await sleep(250);
    if (!reduced) await pshot(page, `${scheme}-6-confirm-stamp-sweeping-${scen === 'c_free_one' ? 'quick' : 'deep'}`);
    await nav;
    const during = (await page.evaluate(() => JSON.parse(sessionStorage.getItem('__st') || '{}'))).t120 || {};
    check(T(`${scen}${reduced ? ' (reduced)' : ''}: pressing Start flips the stamp to "Sweeping…"`), during.t === 'Sweeping…' && /\bsent\b/.test(during.cls), JSON.stringify(during));
    if (!reduced) check(T(`${scen}: ...with a stamp-press`), during.names.includes('a-stamp'), JSON.stringify(during.names));
    else check(T(`${scen} (reduced): ...with no animation`), during.names.length === 0, JSON.stringify(during.names));
    check(T(`${scen}${reduced ? ' (reduced)' : ''}: the form's own logic is untouched: the button is disabled and "Starting the sweep…" shows`), during.dis && during.sending, JSON.stringify(during));
    check(T(`${scen}${reduced ? ' (reduced)' : ''}: the submit was sent at once (not held back for the stamp)`), hits.length === 1 && hits[0] < 700, JSON.stringify(hits));
    check(T(`${scen}${reduced ? ' (reduced)' : ''}: navigation still happens: /running`), new URL(page.url()).pathname === '/running', page.url());
    await ctx.close();
  }
}

// ================= Overflow: four widths, every touched screen ===========================================================
for (const scheme of ['light', 'dark']) {
  process.env.D7_SCHEME = scheme;
  for (const [scen, p] of [['paid', '/configure'], ['c_over_one', '/configure'], ['free3', '/configure'], ['c_paid_one', '/confirm'], ['c_over_multi', '/confirm'], ['c_free_one', '/confirm']]) {
    const { ctx, page } = await visitor(browser, app, scen, { vp: 'desktop', trace: false });
    for (const w of [390, 768, 1024, 1440]) {
      await page.setViewportSize({ width: w, height: 900 });
      await go(page, p);
      if (p === '/confirm') { const d = page.locator('.decide > details.peek summary'); if (await d.count()) { await d.click(); await sleep(150); } }
      const o = await overflow(page);
      check(`${scheme}/overflow: ${scen} ${p} at ${w}`, o <= 0, `scrollWidth - configured width = ${o}`);
    }
    await ctx.close();
  }
}

await browser.close(); app.stop();
const fails = out.filter((l) => l.startsWith('FAIL'));
console.log(out.join('\n'));
console.log(`\n${out.length - fails.length} of ${out.length} checks pass${SHOTS ? ' (screenshots in output/design-A7/money-a/)' : ''}`);
process.exit(ok ? 0 : 1);
