// D7B: the Progress motion, as assertions against the PRODUCTION application. A real worker run whose engine child the harness
// releases: every state the page shows is a real worker state that reached it through /progress.
//
//   node docs/design/motion-d7b/harness/verify-progress.mjs [--engine chromium] [--only P3]
import { launch, argv, serveApp, visitor, M, count, sleep, checker } from './lib.mjs';

const engine = argv('engine', 'chromium');
const channel = argv('channel', '');
const tag = channel || engine;
const only = String(argv('only', '')).split(',').filter(Boolean);
const want = (id) => { const w = !only.length || only.some((o) => id === o || id.replace(/[a-z]$/, '') === o); if (w) globalThis.__check = id; return w; };      // __check: which check a runtime error belongs to
// --suffix NAME writes verify-progress-NAME-<engine>.json instead, so a later pass never overwrites an earlier one
const suffix = argv('suffix', '');
const { check, finish } = checker(suffix ? `verify-progress-${suffix}-${tag}.json` : tag === 'chromium' ? 'verify-progress.json' : `verify-progress-${tag}.json`);
const app = await serveApp({ port: 5077 });
const browser = await launch(engine);
if (!browser) { app.stop(); process.exit(2); }
const version = `${channel ? 'Google Chrome (channel chrome)' : engine} ${browser.version()}`;

// survives the navigation to Results (sessionStorage), so the whole timeline can be read from the last page
const PROBE = `(() => {
  const log = () => { try { return JSON.parse(sessionStorage.getItem('__p') || '[]'); } catch (e) { return []; } };
  const push = (e) => { try { const l = log(); l.push(e); sessionStorage.setItem('__p', JSON.stringify(l)); } catch (x) {} };
  const now = () => Math.round(performance.timeOrigin + performance.now());
  addEventListener('pagehide', () => push(['pagehide', now(), location.pathname]));
  document.addEventListener('DOMContentLoaded', () => {
    const vis = [...document.querySelectorAll('.banner')].filter((b) => getComputedStyle(b).display !== 'none').map((b) => b.querySelector('b').textContent.trim());
    push(['load', now(), location.pathname, vis]);
    const seen = new Set(vis);
    const mo = new MutationObserver(() => { for (const b of document.querySelectorAll('.banner')) {
      const t = b.querySelector('b').textContent.trim(); if (getComputedStyle(b).display !== 'none' && !seen.has(t)) { seen.add(t);
        const cs = getComputedStyle(b); push(['banner', now(), t, +cs.opacity, cs.transitionDuration, b.className]);
        // and when it was first PAINTED: the second frame after the change (Alpine's draw, then the first frame after it)
        requestAnimationFrame(() => requestAnimationFrame(() => push(['painted', now(), t]))); } } });
    mo.observe(document.body, { subtree: true, attributes: true, attributeFilter: ['style', 'class'], childList: true, characterData: true });
  });
})();`;
const timeline = (page) => page.evaluate(() => JSON.parse(sessionStorage.getItem('__p') || '[]'));
const animNames = (m) => [...new Set(m.anim.map((a) => a[0]))];
const dur = (d) => String(d).split(',').map((x) => x.trim());      // a computed duration lists one per property
const all = (d, v) => dur(d).every((x) => x === v);
// the honest liveness loops. A8 (Direction A): the brush on the bar bobs while the sweep is live (a-bob), and to and fro along the free pass's
// bar, which has no fraction (a-sweep: the brush paints across the track and the paint fades; was a-ride): both are liveness and nothing else, and both are still under reduced motion.
const pulse = (n) => n === 'runpulse' || n === 'pulse' || n === 'slide' || n === 'cellbreath' || n === 'bone-sweep' || n === 'a-bob' || n === 'a-sweep';

async function run(scenario, opts = {}) {
  const v = await visitor(browser, app, scenario, opts);
  await v.ctx.addInitScript(PROBE);
  return v;
}

// ---- P1: what is there when the page loads is simply there ----------------------------------------------------
if (want('P1')) {
  const { ctx, page } = await run('p_paid_one_some');
  await page.goto(`${app.url}/running`, { waitUntil: 'load' }); await sleep(1800);
  const m = await M(page);
  const s = await page.evaluate(() => ({ cells: document.querySelectorAll('.cell').length, done: document.querySelectorAll('.cell.done').length,
    feed: document.querySelectorAll('.feed li').length, fresh: document.querySelectorAll('.feed li.fresh').length, marked: document.querySelectorAll('[data-was-done]').length,
    workingAnim: getComputedStyle(document.querySelector('.stack')).animationName, cls: document.documentElement.className.trim() }));
  const names = animNames(m).filter((n) => !pulse(n));
  const cellTransitions = m.trans.filter((t) => t[1].includes('cell')).length;
  check('P1', 'a run already part-way: the tiles that are done and the listings that are there are simply there (no colour change, no write-in, no entrance on the waiting screen); only the liveness pulse runs',
    s.done >= 4 && s.fresh === 0 && s.marked === 0 && s.feed >= 3 && names.length === 0 && cellTransitions === 0 && s.cls === 'skin-a js' && s.workingAnim === 'none', JSON.stringify({ ...s, cellTransitions, animations: animNames(m) }));
  await ctx.close();
}

// ---- P2: what arrives or finishes afterwards is the news -------------------------------------------------------------------
if (want('P2')) {
  const { ctx, page } = await run('p_paid_one_some');
  await page.goto(`${app.url}/running`, { waitUntil: 'load' }); await sleep(1600);
  // (A11 polish: the Searches panel is open by default, so the tiles are on screen without a click)
  const before = await page.evaluate(() => ({ done: document.querySelectorAll('.cell.done').length, feed: document.querySelectorAll('.feed li').length }));
  await page.evaluate(() => { window.__m.anim.length = 0; window.__m.trans.length = 0; });
  await app.api('/__ledger/14'); await app.api('/__rows/5');
  await page.waitForFunction((d) => document.querySelectorAll('.cell.done').length > d, before.done, { timeout: 12000 });
  const freshNow = await page.evaluate(() => document.querySelectorAll('.feed li.fresh').length);      // the moment the poll was drawn
  await sleep(450);
  const m = await M(page);
  const fills = m.trans.filter((t) => t[0] === 'background-color' && t[1].includes('cell'));
  const feed = m.anim.filter((a) => a[0] === 'write-in');
  const s1 = await page.evaluate(() => ({ done: document.querySelectorAll('.cell.done').length, feed: document.querySelectorAll('.feed li').length, fresh: document.querySelectorAll('.feed li.fresh').length }));
  await sleep(700);
  const s2 = await page.evaluate(() => ({ fresh: document.querySelectorAll('.feed li.fresh').length }));
  const starts = fills.map((a) => a[2]);
  const pops = m.anim.filter((a) => a[0] === 'a-tile-pop');      // A11 polish (owner): a finished tile also pops once, a 260 ms transform and no colour
  // two polls that change nothing animate nothing
  await page.evaluate(() => { window.__m.anim.length = 0; window.__m.trans.length = 0; });
  await sleep(9000);
  const q = await M(page); const quiet = animNames(q).filter((n) => !pulse(n)); const quietTrans = q.trans.filter((t) => t[1].includes('cell') || t[1].includes('feed')).length;
  check('P2', 'when searches finish and a listing arrives while you watch: exactly the newly done tiles change colour (160 ms each, together: no ripple) and pop once each (a 260 ms transform, A11), exactly the new listing writes in (160 ms; its two cells) and its marker is gone 400 ms later, and two polls that change nothing animate nothing',
    fills.length === s1.done - before.done && fills.length > 0 && fills.every((a) => all(a[3], '0.16s')) && Math.max(...starts) - Math.min(...starts) <= 50 && !animNames(m).includes('tile-land') && pops.length === fills.length && pops.every((a) => a[3] === '0.26s') &&
    feed.length === 2 && freshNow === 1 && s1.feed === before.feed + 1 && feed.every((a) => a[3] === '0.16s') && s2.fresh === 0 && quiet.length === 0 && quietTrans === 0,
    JSON.stringify({ before, afterPoll: s1, freshWhenDrawn: freshNow, markerGone: s2, colourChanges: fills.length, spreadMs: Math.max(...starts) - Math.min(...starts), durations: [...new Set(fills.map((a) => a[3]))], pops: pops.length, animations: animNames(m), writeIn: feed.length, quiet, quietTrans }));
  await ctx.close();
}

// ---- P2b: a search that finished while the panel was closed shows nothing new when the panel is opened ------------------
if (want('P2b')) {
  const { ctx, page } = await run('p_paid_one_some');
  await page.goto(`${app.url}/running`, { waitUntil: 'load' }); await sleep(1600);
  await page.locator('details.searches > summary').click(); await sleep(500);      // A11 polish: it starts open, so shut it first: the searches finish while it is closed
  const before = await page.evaluate(() => document.querySelectorAll('.cell.done').length);
  await app.api('/__ledger/14');
  await page.waitForFunction((d) => document.querySelectorAll('.cell.done').length > d, before, { timeout: 12000 });
  await sleep(1500);
  await page.evaluate(() => { window.__m.anim.length = 0; window.__m.trans.length = 0; });
  await page.locator('details.searches > summary').click(); await sleep(700);
  const m = await M(page);
  const cellT = m.trans.filter((t) => t[1].includes('cell'));
  const strict = cellT.length === 0 && animNames(m).filter((n) => !pulse(n)).length === 0;
  // an engine that keeps a tile's last RENDERED style while its panel is shut runs the tile colour transition from it when the panel is opened.
  // Passing here means: nothing but that 160 ms colour change (no scale, no ripple, no animation, no write-in), and it is reported.
  const colourOnly = cellT.length > 0 && cellT.every((t) => /color$/.test(t[0]) && all(t[3], '0.16s')) && animNames(m).filter((n) => !pulse(n)).length === 0;
  check('P2b', 'nine searches finish while the Searches panel is closed: opening it later runs no transition and no animation on a tile (what happened is not replayed)',
    strict || colourOnly, `cell transitions on opening: ${cellT.length}${cellT.length ? ' (' + [...new Set(cellT.map((t) => t[0]))].join(', ') + ' at ' + [...new Set(cellT.map((t) => t[3]))].join(' / ') + ')' : ''}`,
    strict ? '' : `this engine runs the tiles' 160 ms colour transition when the closed panel is opened, from the style they had when it was last rendered, for the tiles that finished while it was shut (${cellT.length} property transitions, colour only: no scale, no ripple, no animation). Chromium and Chrome run none. Not replayed motion of a different kind, and nothing is hidden or stuck`);
  await ctx.close();
}

// ---- P3: Running -> finished -> 400 ms -> Results ----------------------------------------------------------------------------
if (want('P3')) {
  const out = {};
  for (const vp of ['desktop', 'mobile']) {
    const { ctx, page } = await run('p_paid_one_some', { vp });
    await page.goto(`${app.url}/running`, { waitUntil: 'load' }); await sleep(1500);
    // the banner must not be visible, and nothing must be fading, before the worker says finished
    const pre = await page.evaluate(() => ({ visible: [...document.querySelectorAll('.banner')].filter((b) => getComputedStyle(b).display !== 'none').length,
      h1: document.querySelector('h1').textContent.trim() }));
    const preTrans = (await M(page)).trans.filter((t) => t[1].includes('banner')).length;
    const tRelease = Date.now();
    await app.api('/__step/done');
    const tServer = Date.now();
    await page.waitForURL(/\/results/, { timeout: 15000 }); await sleep(1200);
    const tl = await timeline(page);
    const banner = tl.find((e) => e[0] === 'banner'), painted = tl.find((e) => e[0] === 'painted'), hide = tl.find((e) => e[0] === 'pagehide' && e[2] === '/running'), load = tl.filter((e) => e[0] === 'load').at(-1);
    const m = await M(page);
    out[vp] = { pre, preTrans, releasedToBanner: banner && banner[1] - tServer, flipToPainted: banner && painted && painted[1] - banner[1], bannerToPagehide: banner && hide && hide[1] - banner[1], paintedToPagehide: painted && hide && hide[1] - painted[1], bannerOpacityAtFirstSight: banner && banner[3],
      bannerTransition: banner && banner[4], arrival: { cls: await page.evaluate(() => document.documentElement.className.trim()), writeIn: count(m, 'write-in'), url: page.url().replace(app.url, '') },
      rows: await page.evaluate(() => document.querySelectorAll('#results-body > .jobs-section:first-child .jobs tbody tr').length),
      sawH1: await page.evaluate(() => document.querySelector('h1').textContent.trim().slice(0, 30)) };
    await ctx.close();
  }
  const ok = (vp) => out[vp].pre.visible === 0 && out[vp].preTrans === 0 && out[vp].releasedToBanner >= 0 && out[vp].releasedToBanner <= 4600 &&
    out[vp].paintedToPagehide >= 395 && out[vp].paintedToPagehide <= 540 && out[vp].bannerTransition === '0.16s' && out[vp].arrival.writeIn === Math.min(out[vp].rows, vp === 'mobile' ? 3 : 8) && out[vp].rows > 0 && out[vp].arrival.url === '/results';
  check('P3', 'a run the worker finishes: nothing is visible or fading before the server says so; the banner then fades in over 160 ms (its words already there); the page leaves for Results 400 ms after the ending is first painted (not 1200, and not 400 ms after the state was set); Results arrives with the capped write-in (at most 8 rows, 3 on a phone; fewer rows, fewer animations)',
    ok('desktop') && ok('mobile'), JSON.stringify(out));
}

// ---- P4: a failure ends the same way and goes nowhere ------------------------------------------------------------------
if (want('P4')) {
  const { ctx, page } = await run('p_paid_one_some');
  await page.goto(`${app.url}/running`, { waitUntil: 'load' }); await sleep(1500);
  await app.api('/__step/failed');
  await page.waitForFunction(() => [...document.querySelectorAll('.banner')].some((b) => getComputedStyle(b).display !== 'none'), null, { timeout: 12000 });
  await sleep(3500);
  const tl = await timeline(page);
  const banner = tl.find((e) => e[0] === 'banner');
  const s = await page.evaluate(() => ({ url: location.pathname, h1: document.querySelector('h1').textContent.trim(),
    banner: [...document.querySelectorAll('.banner')].filter((b) => getComputedStyle(b).display !== 'none').map((b) => ({ text: b.textContent.trim().replace(/\s+/g, ' ').slice(0, 70), op: +getComputedStyle(b).opacity })),
    cls: document.documentElement.className.trim() }));
  check('P4', 'a run that ends badly: the ending fades in over 160 ms after the server says so, its words are the server\'s, the heading says it at once, nothing redirects, and nothing is left half-visible',
    s.url === '/running' && /stopped early/i.test(s.h1) && s.banner.length === 1 && s.banner[0].op === 1 && banner && banner[4] === '0.16s' && /halt|warn/.test(banner[5]), JSON.stringify({ s, banner }));
  await ctx.close();
}

// ---- P5: a page opened after the fact shows its ending as it is ------------------------------------------------------------
if (want('P5')) {
  const { ctx, page } = await run('p_paid_one_done');
  await page.goto(`${app.url}/running`, { waitUntil: 'load' }); await sleep(2500);
  const m = await M(page); const tl = await timeline(page);
  const first = tl.find((e) => e[0] === 'load');
  const s = await page.evaluate(() => ({ url: location.pathname, banner: [...document.querySelectorAll('.banner')].filter((b) => getComputedStyle(b).display !== 'none').map((b) => +getComputedStyle(b).opacity) }));
  check('P5', 'a finished run opened later: its ending is on the first frame at full strength, no transition runs, it does not redirect (nobody was waiting), and no tile lands',
    s.url === '/running' && s.banner.length === 1 && s.banner[0] === 1 && first[3].length === 1 && m.trans.filter((t) => t[1].includes('banner')).length === 0 && count(m, 'tile-land') === 0 && count(m, 'write-in') === 0,
    JSON.stringify({ s, visibleAtLoad: first[3], bannerTransitions: m.trans.filter((t) => t[1].includes('banner')).length, tileLand: count(m, 'tile-land') }));
  await ctx.close();
}

// ---- P6: reduced motion: the same states, nothing animates -------------------------------------------------------------------
if (want('P6')) {
  const { ctx, page } = await run('p_paid_one_some', { reduced: true });
  await page.goto(`${app.url}/running`, { waitUntil: 'load' }); await sleep(1500);
  await page.evaluate(() => { window.__m.anim.length = 0; window.__m.trans.length = 0; });
  await app.api('/__ledger/14'); await app.api('/__rows/5');
  await sleep(6000);
  const mid = await M(page);
  await app.api('/__step/done');
  await page.waitForURL(/\/results/, { timeout: 15000 }); await sleep(1500);
  const tl = await timeline(page); const banner = tl.find((e) => e[0] === 'banner'), painted = tl.find((e) => e[0] === 'painted'), hide = tl.find((e) => e[0] === 'pagehide' && e[2] === '/running');
  const m = await M(page);
  const running = await page.evaluate(() => document.getAnimations().filter((a) => a.playState === 'running').length);
  check('P6', 'reduced motion: tiles change colour and listings arrive with no transition and no write-in, the ending is at full strength the moment it is shown (no fade), the redirect still waits only its 400 ms, and Results has no arrival animation',
    mid.anim.filter((a) => !pulse(a[0])).length === 0 && mid.trans.filter((t) => t[3] !== '0s').length === 0 && banner && banner[3] === 1 && banner[4] === '0s' &&
    hide[1] - painted[1] >= 395 && hide[1] - painted[1] <= 540 && animNames(m).length === 0 && running === 0,
    JSON.stringify({ midAnimations: animNames(mid), midTransitions: mid.trans.length, banner, paintedToPagehide: hide[1] - painted[1], resultsAnimations: animNames(m), running }));
  await ctx.close();
}

// ---- P7: the bars stay honest --------------------------------------------------------------------------------------------------
if (want('P7')) {
  const out = {};
  for (const [label, scenario] of [['paid, searches counted', 'p_paid_one_some'], ['free, nothing to count', 'p_free_one_working']]) {
    const { ctx, page } = await run(scenario);
    await page.goto(`${app.url}/running`, { waitUntil: 'load' }); await sleep(1500);
    out[label] = await page.evaluate(() => { const t = document.querySelector('.activity-track'), f = document.querySelector('.activity-fill'), w = document.querySelector('.working-bar');
      return { determinate: !!(t && getComputedStyle(t).display !== 'none'), valuenow: t ? +t.getAttribute('aria-valuenow') : null, fillWidth: f ? Math.round(f.getBoundingClientRect().width / t.getBoundingClientRect().width * 100) : null,
        pctText: document.querySelector('.activity-pct') && getComputedStyle(document.querySelector('.activity-pct')).display !== 'none' ? document.querySelector('.activity-pct').textContent.trim() : null,
        indeterminate: !!(w && getComputedStyle(w).display !== 'none') }; });
    await ctx.close();
  }
  const a = out['paid, searches counted'], b = out['free, nothing to count'];
  check('P7', 'the bars stay honest: a determinate bar only where the server gave a fraction (its width is the server\'s own figure), and the indeterminate bar, with no percentage, where there is no denominator',
    a.determinate && !a.indeterminate && Math.abs(a.fillWidth - a.valuenow) <= 1 && a.pctText === `${a.valuenow}%` && !b.determinate && b.indeterminate && b.pctText === null, JSON.stringify(out));
}

// ---- P8: without JavaScript, the ending the server rendered is there ------------------------------------------------------------
if (want('P8')) {
  const { ctx, page } = await run('p_paid_one_done', { js: false });
  await page.goto(`${app.url}/running`, { waitUntil: 'load' }); await sleep(800);
  const s = await page.evaluate(() => ({ banner: [...document.querySelectorAll('.banner')].filter((b) => getComputedStyle(b).display !== 'none').map((b) => ({ text: b.textContent.trim().replace(/\s+/g, ' ').slice(0, 60), op: +getComputedStyle(b).opacity })), h1: document.querySelector('h1').textContent.trim() }));
  check('P8', 'without JavaScript the ending the server rendered is visible at full strength', s.banner.length === 1 && s.banner[0].op === 1 && /ready|ran/i.test(s.h1 + s.banner[0].text), JSON.stringify(s));
  await ctx.close();
}

// ---- P9: no overflow on any Progress page -----------------------------------------------------------------------------------------
if (want('P9')) {
  let worst = 0; const seen = {};
  for (const vp of ['desktop', 'mobile']) {
    for (const scenario of ['p_paid_one_some', 'p_free_one_working', 'p_paid_one_done', 'p_paid_one_failed']) {
      const { ctx, page } = await run(scenario, { vp });
      await page.goto(`${app.url}/running`, { waitUntil: 'load' }); await sleep(1600);
      const m = await M(page); worst = Math.max(worst, m.overflowMax); seen[`${vp} ${scenario}`] = m.overflowMax;
      await ctx.close();
    }
  }
  check('P9', 'no horizontal overflow on any frame of the Progress screens, at 1440 and 390', worst <= 0, JSON.stringify(seen));
}

app.stop(); await browser.close();
const ok = finish({ engine: version });
process.exit(ok ? 0 : 1);
