// D7A: the brief's safeguards, as assertions against the running prototype (and, where it means something, the
// page as shipped today).
//
//   node docs/design/prototype/motion/harness/verify.mjs
//
// Writes output/design-D7A/verify.json and prints one line per check. Headless Chromium on the machine it runs
// on: absolute frame times are not a phone's; the comparison between variants, and every pass/fail that does not
// depend on a clock, is what this establishes. No video is recorded here and no cursor is drawn.
import { chromium, serve, warmFonts, VIEWPORTS, TRACK, TRACE, sleep, mkdir, OUT, fs, path } from './lib.mjs';

const only = (process.argv.includes('--only') ? process.argv[process.argv.indexOf('--only') + 1] : '').split(',').filter(Boolean);
const want = (id) => !only.length || only.some((o) => id.startsWith(o));
const results = [];
const check = (id, what, pass, detail = '') => {
  results.push({ id, what, pass: !!pass, detail });
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${id}  ${what}${detail ? '  — ' + detail : ''}`);
};

const note_t13 = (o) => check('T13', 'time from navigation start until the first six rows are visible / half opaque / fully readable (effective opacity), shipped vs proposed, arrival and tab change', true, JSON.stringify(o));
const srv = {
  baseline: await serve('baseline', 8801),
  proposed: await serve('proposed', 8802),
  slow: await serve('proposed', 8803, 700),
  slowBase: await serve('baseline', 8804, 700),
  vt: await serve('proposed-vt', 8805),
};
const browser = await chromium.launch();

async function open({ vp = 'desktop', reduced = false, js = true, throttle = 1 } = {}) {
  const v = VIEWPORTS[vp];
  const ctx = await browser.newContext({ viewport: { width: v.width, height: v.height }, isMobile: v.isMobile, hasTouch: v.hasTouch,
    deviceScaleFactor: 1, javaScriptEnabled: js, reducedMotion: reduced ? 'reduce' : 'no-preference', colorScheme: 'dark' });
  await warmFonts(ctx, srv.baseline.url);
  if (js) await ctx.addInitScript(TRACE);
  const page = await ctx.newPage();
  if (throttle > 1) { const c = await ctx.newCDPSession(page); await c.send('Emulation.setCPUThrottlingRate', { rate: throttle }); }
  return { ctx, page };
}
const arrive = async (page, base, query = '') => {
  await page.goto(`${base}/results${query}`, { referer: `${base}/running`, waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);
};
const M = (page) => page.evaluate(() => window.__m);
const rowIn = (m, name) => m.anim.filter((a) => a[0] === name).length;
const motionMs = (m) => {            // how long anything was running: first running frame to the last
  const on = m.frames.filter((f) => f[2] > 0).map((f) => f[0]);
  return on.length ? on.at(-1) - on[0] : 0;
};

// ---- T1: the page without JavaScript ---------------------------------------------------------------------
if (want('T1')) {
for (const v of ['baseline', 'proposed']) {
  const { ctx, page } = await open({ js: false });
  await page.goto(`${srv[v].url}/results`, { referer: `${srv[v].url}/running`, waitUntil: 'load' });
  await sleep(1500);
  const r = await page.evaluate(() => {
    const rows = [...document.querySelectorAll('tbody tr')];
    return { n: rows.length, hidden: rows.filter((t) => +getComputedStyle(t).opacity < 1 || getComputedStyle(t).visibility !== 'visible').length,
      h1: getComputedStyle(document.querySelector('h1')).opacity };
  });
  check(`T1-${v}`, `no JavaScript: every row is readable (${v})`, r.n === 19 && r.hidden === 0 && r.h1 === '1', JSON.stringify(r));
  await ctx.close();
}
}

// ---- T2: the stagger has a cap, whatever the list ---------------------------------------------------------
if (want('T2')) {
{
  const out = {};
  for (const [label, q] of [['19 jobs', ''], ['240 jobs, Show all', '?set=long']]) {
    const { ctx, page } = await open();
    await arrive(page, srv.proposed.url, q); await sleep(1600);
    const m = await M(page);
    const rows = await page.evaluate(() => document.querySelectorAll('tbody tr').length);
    out[label] = { rows, rowIn: rowIn(m, 'row-in'), maxConcurrent: Math.max(...m.frames.map((f) => f[2])), motionMs: motionMs(m) };
    await ctx.close();
  }
  const a = out['19 jobs'], b = out['240 jobs, Show all'];
  check('T2', 'entrance animates at most 8 elements and lasts the same (and under 400 ms, frame-quantised) for 19 and 240 rows',
    a.rowIn <= 8 && b.rowIn <= 8 && a.rowIn === b.rowIn && b.rows >= 200 && Math.abs(a.motionMs - b.motionMs) <= 80 && b.motionMs <= 400,
    JSON.stringify(out));
  const base = {};
  for (const [label, q] of [['19 jobs', ''], ['240 jobs', '?set=long']]) {
    const { ctx, page } = await open();
    await arrive(page, srv.baseline.url, q); await sleep(1600);
    const m = await M(page);
    base[label] = { sectionIn: rowIn(m, 'section-in'), maxConcurrent: Math.max(...m.frames.map((f) => f[2])) };
    await ctx.close();
  }
  check('T2-baseline', 'for the record: what ships today animates whole sections (fixed count), at every load', true, JSON.stringify(base));
}
}

// ---- T3: nothing replays because something unrelated changed ---------------------------------------------
if (want('T3')) {
{
  const { ctx, page } = await open();
  await arrive(page, srv.proposed.url); await sleep(1400);
  await page.evaluate(() => { window.__m.anim.length = 0; });
  await page.locator('button.tool-toggle', { hasText: 'Filter and sort' }).click(); await sleep(300);
  await page.locator('button.tool-toggle', { hasText: 'Filter and sort' }).click(); await sleep(300);
  await page.locator('tr[data-href]').first().click({ position: { x: 240, y: 20 } }); await sleep(200);
  await page.evaluate(() => { const t = document.querySelector('.jobs tbody'); t.innerHTML = t.innerHTML; });   // a re-render of the rows
  await page.setViewportSize({ width: 1100, height: 900 }); await sleep(200);
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
  await sleep(500);
  const m = await M(page);
  const names = [...new Set(m.anim.map((a) => a[0]))];
  check('T3', 'after the arrival: tool toggles, a row click, a re-render of the rows, a resize and a visibility change start no entrance',
    rowIn(m, 'row-in') === 0 && rowIn(m, 'section-in') === 0, `animations started: ${JSON.stringify(names)}`);
  await ctx.close();
}
}

// ---- T4: a move between views is not an arrival -----------------------------------------------------------
if (want('T4')) {
for (const v of ['baseline', 'proposed']) {
  const { ctx, page } = await open();
  await arrive(page, srv[v].url); await sleep(1400);
  const tab = page.locator('nav.views a', { hasText: 'Backend Engineer' });
  await tab.click(); await page.waitForLoadState('load'); await sleep(900);
  const m1 = await M(page);
  await page.locator('button.tool-toggle', { hasText: 'Filter and sort' }).click(); await sleep(300);
  await page.locator('.tool-panel form button[type=submit]').click(); await page.waitForLoadState('load'); await sleep(900);
  const m2 = await M(page);
  await page.reload({ waitUntil: 'load' }); await sleep(900);
  const m3 = await M(page);
  if (v === 'baseline') {
    check('T4-baseline', 'for the record: today a tab, a filter and a reload each replay the section entrance',
      rowIn(m1, 'section-in') > 0 && rowIn(m2, 'section-in') > 0, `tab ${rowIn(m1, 'section-in')}, filter ${rowIn(m2, 'section-in')}, reload ${rowIn(m3, 'section-in')} section-in`);
  } else {
    check('T4', 'proposed: a quick tab, a quick filter apply and a reload are instant swaps: no row entrance, no list animation, no view transition',
      rowIn(m1, 'row-in') + rowIn(m2, 'row-in') + rowIn(m3, 'row-in') === 0 && rowIn(m1, 'list-in') + rowIn(m2, 'list-in') + rowIn(m3, 'list-in') === 0 && !m1.vt && !m2.vt,
      `row-in ${rowIn(m1, 'row-in')}/${rowIn(m2, 'row-in')}/${rowIn(m3, 'row-in')}; list-in ${rowIn(m1, 'list-in')}/${rowIn(m2, 'list-in')}/${rowIn(m3, 'list-in')}; vt ${m1.vt}/${m2.vt}/${m3.vt}`);
  }
  await ctx.close();
}
}

// ---- T5: reduced motion is a real alternative --------------------------------------------------------------
if (want('T5')) {
{
  const { ctx, page } = await open({ reduced: true });
  await arrive(page, srv.proposed.url); await sleep(1200);
  const m0 = await M(page);
  const cls = await page.evaluate(() => document.documentElement.className);
  await page.locator('button.tool-toggle', { hasText: 'Filter and sort' }).click(); await sleep(400);
  const tool = await page.evaluate(() => ({ shown: getComputedStyle(document.getElementById('tool-filter')).display !== 'none',
    op: getComputedStyle(document.getElementById('tool-filter')).opacity, trans: window.__m.trans.filter((t) => t[1].includes('tool-filter')).length }));
  await page.locator('nav.views a', { hasText: 'Platform Engineer' }).click(); await page.waitForLoadState('load'); await sleep(800);
  const m1 = await M(page);
  const animating = [m0, m1].flatMap((m) => m.frames.filter((f) => f[2] > 0)).length;
  check('T5', 'reduced motion: no arrival, no swap, no animation on any frame, the tool panel opens at once, nothing is missing',
    !cls.includes('arrive') && !cls.includes('swap') && rowIn(m0, 'row-in') === 0 && rowIn(m1, 'list-in') === 0 && animating === 0 && !m1.vt && tool.shown && tool.op === '1' && tool.trans === 0,
    `html.class="${cls}", animating frames ${animating}, vt ${m1.vt}, panel shown ${tool.shown} opacity ${tool.op} transitions ${tool.trans}`);
  await ctx.close();
}
}

// ---- T6: a slow answer dims, the new page un-dims, and the dim never sticks ---------------------------------------------------
if (want('T6')) {
  const { ctx, page } = await open();
  await arrive(page, srv.slow.url); await sleep(1800);       // the first load itself took 700 ms
  // Sample from inside the old document (Playwright's own click waits for the navigation to commit). The
  // samples ride across the navigation in sessionStorage.
  await page.evaluate(() => {
    sessionStorage.setItem('t6', '[]');
    document.addEventListener('click', () => { [60, 200, 320, 450, 600].forEach((ms) => setTimeout(() => {
      const b = document.getElementById('results-body'); const l = JSON.parse(sessionStorage.getItem('t6'));
      l.push({ ms, cls: document.documentElement.className.replace('first-paint', '').trim(), op: +getComputedStyle(b).opacity,
        row: +getComputedStyle(document.querySelector('tbody tr')).opacity, flag: sessionStorage.getItem('sweep.dimmed') });
      sessionStorage.setItem('t6', JSON.stringify(l)); }, ms)); }, { once: true, capture: true });
  });
  const tb = await page.locator('nav.views a', { hasText: 'Backend Engineer' }).boundingBox();
  await page.mouse.click(tb.x + tb.width / 2, tb.y + tb.height / 2);
  await page.waitForURL(/track=a/); await page.waitForFunction(() => !document.documentElement.classList.contains('swap'), null, { timeout: 4000 });
  const samples = JSON.parse(await page.evaluate(() => sessionStorage.getItem('t6')));
  const at = (ms) => samples.find((x) => x.ms === ms);
  const m = await M(page);
  const after = await page.evaluate(() => ({ cls: document.documentElement.className.replace('first-paint', '').trim(), op: getComputedStyle(document.getElementById('results-body')).opacity, flag: sessionStorage.getItem('sweep.dimmed') }));
  check('T6', 'slow server (700 ms): untouched at 60 ms, marked pending by ~200 ms and settled at .85 (AA for every text colour) once the 160 ms transition has run; the new page starts at .85, un-dims once, and is clean',
    at(60) && at(60).cls === '' && at(60).op === 1 && at(60).flag === null &&
    [200, 320, 450, 600].every((ms) => at(ms) && at(ms).cls === 'pending' && at(ms).flag === '1') &&
    [320, 450, 600].every((ms) => at(ms).op >= .84 && at(ms).op <= .86 && at(ms).row === 1) &&
    rowIn(m, 'list-in') === 1 && after.cls === '' && after.op === '1' && after.flag === null,
    `samples ${JSON.stringify(samples.map((x) => [x.ms, x.cls, x.op, x.flag]))}; list-in on the new page ${rowIn(m, 'list-in')}; loaded ${JSON.stringify(after)}`);
  await page.evaluate(() => { document.documentElement.classList.add('pending'); sessionStorage.setItem('sweep.dimmed', '1'); dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true })); });
  const restored = await page.evaluate(() => [document.documentElement.classList.contains('pending'), sessionStorage.getItem('sweep.dimmed')]);
  check('T6b', 'a page restored from the back/forward cache keeps neither a pending class nor the un-dim flag', restored[0] === false && restored[1] === null);
  await ctx.close();
}

// ---- T15: the dim can never stick --------------------------------------------------------------------------------------------------
if (want('T15')) {
  const out = {};
  // (a) a number field that refuses its input: the browser's own validation stops the submit, so nothing may dim
  { const { ctx, page } = await open();
    await arrive(page, srv.slow.url); await sleep(1800);
    await page.locator('button.tool-toggle', { hasText: 'Filter and sort' }).click(); await sleep(500);
    await page.locator('input[name=min]').click(); await page.keyboard.type('1e'); await sleep(50);
    const before = page.url();
    await page.locator('.tool-panel form button[type=submit]').click(); await sleep(700);
    out.invalidNumber = await page.evaluate((u) => ({ moved: location.href !== u, pending: document.documentElement.classList.contains('pending'), flag: sessionStorage.getItem('sweep.dimmed') }), before);
    await ctx.close(); }
  // (b) a navigation that never finishes (stopped, as Esc does): the dim must give up on its own
  { const { ctx, page } = await open();
    await arrive(page, srv.slow.url); await sleep(1800);
    const tb = await page.locator('nav.views a', { hasText: 'Platform Engineer' }).boundingBox();
    await page.evaluate(() => { document.addEventListener('click', () => setTimeout(() => window.stop(), 250), { once: true, capture: true }); });
    await page.mouse.click(tb.x + tb.width / 2, tb.y + tb.height / 2);
    await sleep(600);
    out.dimmedWhileWaiting = await page.evaluate(() => document.documentElement.classList.contains('pending'));
    await sleep(10000);
    out.afterGiveUp = await page.evaluate(() => ({ pending: document.documentElement.classList.contains('pending'), flag: sessionStorage.getItem('sweep.dimmed'), url: location.search }));
    await ctx.close(); }
  // (c) which links count: a same-page link (Back to the top) does; an export and an Apply link do not. Nothing is
  // suppressed: the export gets a 204 from the prototype server (no navigation), and the popup Apply opens is closed.
  { const { ctx, page } = await open();
    ctx.on('page', (p) => { p.close().catch(() => {}); });
    await arrive(page, srv.slow.url, '?set=long'); await sleep(1800);
    // sampled from inside the page at 320 ms after the press (a slow page navigates away before Node could look)
    const arm = () => page.evaluate(() => { sessionStorage.removeItem('t15p'); document.addEventListener('click', () => setTimeout(() => sessionStorage.setItem('t15p', String(document.documentElement.classList.contains('pending'))), 320), { once: true, capture: true }); });
    const read = () => page.evaluate(() => sessionStorage.getItem('t15p'));
    await page.locator('button.tool-toggle', { hasText: 'Export' }).click(); await sleep(400);
    await arm(); await page.locator('.exports a', { hasText: 'CSV' }).click(); await sleep(600);
    out.exportDims = await read() === 'true';
    await arm(); await page.locator('a.apply').first().click(); await sleep(600);
    out.applyDims = await read() === 'true';
    await arm(); await page.locator('a', { hasText: 'Back to the top' }).first().click(); await sleep(1500);
    out.backToTopDims = await read() === 'true';
    await ctx.close(); }
  check('T15', 'the dim cannot stick: an invalid number field does not dim; a navigation stopped mid-flight clears itself within 10 s; same-page links dim, export and Apply links do not',
    out.invalidNumber.moved === false && out.invalidNumber.pending === false && out.invalidNumber.flag === null &&
    out.dimmedWhileWaiting === true && out.afterGiveUp.pending === false && out.afterGiveUp.flag === null &&
    out.backToTopDims === true && out.exportDims === false && out.applyDims === false, JSON.stringify(out));
}

// ---- T7: interruption ---------------------------------------------------------------------------------------
if (want('T7')) {
  const won = {};
  for (const v of ['baseline', 'proposed']) {
    for (const [label, base] of [['fast', srv[v].url], ...(v === 'proposed' ? [['slow (700 ms)', srv.slow.url]] : [])]) {
      const gaps = [30, 50, 70, 90, 120, 30, 50, 70, 90, 120];
      const bad = [], last = [];
      for (const gap of gaps) {
        const { ctx, page } = await open();
        await arrive(page, base); await sleep(1400);
        const xy = {};
        for (const t of ['Backend Engineer', 'Full Stack Web Developer', 'Platform Engineer']) {
          const b = await page.locator('nav.views a', { hasText: t }).boundingBox(); xy[t] = [b.x + b.width / 2, b.y + b.height / 2];
        }
        const errors = []; page.on('pageerror', (e) => errors.push(String(e)));
        for (const t of ['Backend Engineer', 'Full Stack Web Developer', 'Platform Engineer']) {
          await page.mouse.click(...xy[t]); await sleep(gap);
        }
        await sleep(label === 'fast' ? 1500 : 3500);
        await page.waitForLoadState('load');
        const s = await page.evaluate(() => ({ url: location.search, pending: document.documentElement.classList.contains('pending'),
          arrive: document.documentElement.classList.contains('arrive') || document.documentElement.classList.contains('swap'), running: document.getAnimations().filter((a) => a.playState === 'running').length,
          body: +getComputedStyle(document.getElementById('results-body') || document.body).opacity, ov: document.documentElement.scrollWidth - innerWidth,
          row: +getComputedStyle(document.querySelector('tbody tr')).opacity }));
        last.push(s.url.includes('c'.repeat(16)));
        // What must hold whichever tab the browser ended on: a real view, no stuck state, nothing running, no error.
        if (!/track=[abc]{16}/.test(s.url) || s.pending || s.arrive || s.running || s.body !== 1 || s.ov || s.row !== 1 || errors.length) bad.push({ gap, s, errors });
        await ctx.close();
      }
      won[`${v}-${label}`] = last.filter(Boolean).length;
      check(`T7-${v}-${label}`, `three tabs pressed ${gaps.join('/')} ms apart: a real view, nothing stuck, nothing running, no error (${v}, ${label})`,
        bad.length === 0, bad.length ? JSON.stringify(bad[0]) : `${gaps.length} runs clean; the last-pressed tab was the one shown in ${last.filter(Boolean).length}/${gaps.length}`);
    }
  }
  {
    const gaps = [30, 50, 70, 90, 120, 30, 50, 70, 90, 120]; let last = 0;
    for (const gap of gaps) {
      const { ctx, page } = await open();
      await arrive(page, srv.vt.url); await sleep(1400);
      const xy = {};
      for (const t of ['Backend Engineer', 'Full Stack Web Developer', 'Platform Engineer']) { const b = await page.locator('nav.views a', { hasText: t }).boundingBox(); xy[t] = [b.x + b.width / 2, b.y + b.height / 2]; }
      for (const t of Object.keys(xy)) { await page.mouse.click(...xy[t]); await sleep(gap); }
      await sleep(1500);
      if ((await page.evaluate(() => location.search)).includes('c'.repeat(16))) last++;
      await ctx.close();
    }
    won['vt-alt-fast'] = last;
    check('T7-vt-alt', 'for the record (the alternative, not the proposal): with a cross-document view transition the last-pressed tab is shown in ' + last + '/' + gaps.length + ' runs', true, JSON.stringify(won));
  }
  check('T7-parity', 'the proposal drops no more last presses than the shipped page does, within one run of 10 (a press during a navigation is the browser\'s to keep or lose)',
    won['proposed-fast'] >= won['baseline-fast'] - 1, JSON.stringify(won));
}

// ---- T8: overflow and layout shift --------------------------------------------------------------------------
if (want('T8')) {
{
  const rows = [];
  for (const vp of ['desktop', 'mobile']) {
    for (const v of ['baseline', 'proposed']) {
      const { ctx, page } = await open({ vp });
      await arrive(page, srv[v].url); await sleep(1500);
      let m = await M(page); rows.push({ vp, v, at: 'arrival', cls: +m.cls.toFixed(4), ov: m.overflowMax });
      for (const t of ['Backend Engineer', 'Full Stack Web Developer', 'Platform Engineer', 'All Jobs']) {
        await page.locator('nav.views a', { hasText: t }).first().click(); await page.waitForLoadState('load'); await sleep(1100);
        m = await M(page); rows.push({ vp, v, at: t, cls: +m.cls.toFixed(4), ov: m.overflowMax });
      }
      await ctx.close();
    }
  }
  const worst = (v) => Math.max(...rows.filter((r) => r.v === v).map((r) => r.cls));
  check('T8a', 'no horizontal overflow on any frame of any page, 1440 and 390', rows.every((r) => r.ov === 0), `max overflow ${Math.max(...rows.map((r) => r.ov))}px`);
  check('T8b', 'layout shift on every view (All Jobs and all three résumés, arrival and tab changes, 1440 and 390): within 0.004 of the shipped page and far under the 0.1 "good" line',
    worst('proposed') <= worst('baseline') + 0.004 && worst('proposed') < 0.02, `worst CLS baseline ${worst('baseline')}, proposed ${worst('proposed')}; ${JSON.stringify(rows.filter((r) => r.cls > 0))}`);
}
}

// ---- T9: keyboard ---------------------------------------------------------------------------------------------
if (want('T9')) {
for (const v of ['baseline', 'proposed']) {
  const { ctx, page } = await open();
  await arrive(page, srv[v].url); await sleep(1300);
  let hops = 0, label = '';
  for (; hops < 40; hops++) { await page.keyboard.press('Tab'); label = await page.evaluate(() => document.activeElement.textContent.trim().slice(0, 20)); if (label.startsWith('Filter and sort')) break; }
  await page.keyboard.press('Enter'); await sleep(350);
  const st = await page.evaluate(() => ({ active: document.activeElement.textContent.trim().slice(0, 14), expanded: document.activeElement.getAttribute('aria-expanded'),
    shown: getComputedStyle(document.getElementById('tool-filter')).display !== 'none', op: getComputedStyle(document.getElementById('tool-filter')).opacity, focusCalls: window.__m.focusCalls }));
  await page.keyboard.press('Space'); await sleep(350);
  const closed = await page.evaluate(() => ({ expanded: document.activeElement.getAttribute('aria-expanded'), shown: getComputedStyle(document.getElementById('tool-filter')).display !== 'none' }));
  check(`T9-${v}`, `keyboard (${v}): Tab reaches Filter and sort, Enter opens it, Space closes it, focus stays on the button, the script moves no focus`,
    label.startsWith('Filter and sort') && st.expanded === 'true' && st.shown && st.op === '1' && st.active.startsWith('Filter') && st.focusCalls === 0 && closed.expanded === 'false' && !closed.shown,
    `tab stops ${hops + 1}; ${JSON.stringify(st)}; after Space ${JSON.stringify(closed)}`);
  await ctx.close();
}
{
  const r = {};
  for (const v of ['baseline', 'proposed']) {
    const { ctx, page } = await open();
    await arrive(page, srv[v].url); await sleep(1000);
    for (let i = 0; i < 40; i++) { await page.keyboard.press('Tab'); const l = await page.evaluate(() => document.activeElement.textContent.trim()); if (l.startsWith('Backend Engineer')) break; }
    await page.keyboard.press('Enter'); await page.waitForLoadState('load'); await sleep(900);
    r[v] = await page.evaluate(() => ({ active: document.activeElement.tagName, y: Math.round(scrollY), focusCalls: window.__m.focusCalls }));
    await ctx.close();
  }
  check('T9c', 'after a tab is chosen from the keyboard, focus lands exactly where it does on the shipped page (nothing is moved by the prototype)',
    JSON.stringify(r.baseline) === JSON.stringify(r.proposed) && r.proposed.focusCalls === 0, JSON.stringify(r));
}
}

// ---- T10: CPU throttling ----------------------------------------------------------------------------------------
if (want('T10')) {
const pct = (a, p) => { const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(p * s.length))]; };
const perf = {};
const med = (xs) => { const s2 = [...xs].sort((x, y) => x - y); return s2[Math.floor(s2.length / 2)]; };
for (const rate of [1, 4, 6]) {
  for (const v of ['baseline', 'proposed']) {
    const reps = [];
    for (let rep = 0; rep < 3; rep++) {          // three runs each; the figures below are medians
      const { ctx, page } = await open({ throttle: rate });
      await arrive(page, srv[v].url, '?set=long'); await sleep(2200 * (rate > 1 ? 1.6 : 1));
      const m = await M(page);
      const fr = m.frames.map((f) => f[1]).slice(1);
      const animFrames = m.frames.filter((f) => f[2] > 0).map((f) => f[1]);
      // a real press on Filter and sort: how long until the browser could paint the result (Event Timing; entries under 16 ms are not reported, so 0 means under 16)
      const slowWait = 500 * (rate > 1 ? 2 : 1);
      await page.locator('button.tool-toggle', { hasText: 'Filter and sort' }).click(); await sleep(slowWait);
      const ev = await page.evaluate(() => window.__m.events.filter((e) => ['click', 'pointerup', 'mouseup'].includes(e[0])));
      await page.locator('button.tool-toggle', { hasText: 'Filter and sort' }).click(); await sleep(slowWait);
      // the toggle: a click until the panel is fully shown
      const t = await page.evaluate(() => new Promise((res) => {
        const b = [...document.querySelectorAll('button.tool-toggle')].find((x) => x.textContent.includes('Filter'));
        const p = document.getElementById('tool-filter'); const t0 = performance.now(); const gaps = []; let last = t0;
        b.click();
        (function f(now) { gaps.push(now - last); last = now;
          if (getComputedStyle(p).display !== 'none' && +getComputedStyle(p).opacity > .99 || now - t0 > 1500) res({ to: now - t0, maxGap: Math.max(...gaps) }); else requestAnimationFrame(f); })(t0);
      }));
      reps.push({ worstGap: Math.max(...fr), p95Gap: +pct(fr, .95).toFixed(1), animatingFrames: animFrames.length, animatingWorstGap: animFrames.length ? Math.max(...animFrames) : 0,
        over50: fr.filter((g) => g > 50).length, toggleToShownMs: Math.round(t.to), toggleMaxGap: +t.maxGap.toFixed(1), clickToPaintMs: ev.length ? Math.max(...ev.map((e) => e[3])) : 0, loafMax: m.loaf.length ? Math.max(...m.loaf.map((l) => l[1])) : 0 });
      await ctx.close();
    }
    const k = (key) => med(reps.map((r) => r[key]));
    perf[`${v}@${rate}x`] = { runs: 3, worstGap: k('worstGap'), p95Gap: k('p95Gap'), animatingFrames: k('animatingFrames'), animatingWorstGap: k('animatingWorstGap'),
      over50: k('over50'), toggleToShownMs: k('toggleToShownMs'), toggleMaxGap: k('toggleMaxGap'), clickToPaintMs: k('clickToPaintMs'), longestAnimationFrameMs: k('loafMax') };
  }
}
fs.writeFileSync(path.join(mkdir(), 'perf-throttle.json'), JSON.stringify(perf, null, 1));
check('T10', 'CPU throttled 1x/4x/6x on the 240-row page, median of 3: the proposed arrival is no worse than shipped (within 30 ms and one slow frame), and a click opens the panel in ~one transition',
  ['1', '4', '6'].every((r) => perf[`proposed@${r}x`].worstGap <= perf[`baseline@${r}x`].worstGap + 30 && perf[`proposed@${r}x`].over50 <= perf[`baseline@${r}x`].over50 + 1) &&
  ['1', '4', '6'].every((r) => perf[`proposed@${r}x`].toggleToShownMs < 600), JSON.stringify(perf));
}

// ---- T11: should a tool panel animate its height? (measured, not assumed; median of 5 per cell) -------------------------------
if (want('T11')) {
  const lab = {};
  const med = (xs) => { const s2 = [...xs].sort((x, y) => x - y); return s2[Math.floor(s2.length / 2)]; };
  for (const rate of [1, 6]) {
    for (const [label, q] of [['19 rows', ''], ['240 rows', '?set=long']]) {
      for (const mode of ['opacity', 'height']) {
        const reps = [];
        for (let rep = 0; rep < 5; rep++) {
          const { ctx, page } = await open({ throttle: rate });
          await arrive(page, srv.proposed.url, q); await sleep(1500 * (rate > 1 ? 2 : 1));
          await page.locator('button.tool-toggle', { hasText: 'Filter and sort' }).click(); await sleep(700 * (rate > 1 ? 2 : 1));   // open
          reps.push(await page.evaluate((mode) => new Promise((res) => {
            const p = document.getElementById('tool-filter'); const h = p.getBoundingClientRect().height; const gaps = []; let last = performance.now();
            const a = mode === 'height'
              ? p.animate([{ height: '0px', overflow: 'hidden' }, { height: h + 'px', overflow: 'hidden' }], { duration: 200, easing: 'cubic-bezier(.22,.61,.36,1)' })
              : p.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 160, easing: 'cubic-bezier(.22,.61,.36,1)' });
            (function f(now) { gaps.push(now - last); last = now; if (a.playState === 'running') requestAnimationFrame(f); else res({ worst: Math.max(...gaps), mean: gaps.reduce((x, y) => x + y) / gaps.length }); })(last);
          }), mode));
          await ctx.close();
        }
        lab[`${mode} ${label} @${rate}x`] = { runs: 5, medianWorstFrameMs: +med(reps.map((r) => r.worst)).toFixed(1), medianMeanFrameMs: +med(reps.map((r) => r.mean)).toFixed(1), slowestRunWorstMs: +Math.max(...reps.map((r) => r.worst)).toFixed(1) };
      }
    }
  }
  fs.writeFileSync(path.join(mkdir(), 'disclosure-lab.json'), JSON.stringify(lab, null, 1));
  check('T11', 'measured, median of 5: height vs opacity animation of a tool panel, 19 and 240 rows, 1x and 6x CPU (headless, non-vsync clock: a relative measure, n=5; data for the decision, see the note)', true, JSON.stringify(lab));
}

// ---- T13: how long until the list is readable? (effective opacity: the product up the tree) ---------------------------------
if (want('T13')) {
  const readable = (page) => page.evaluate(() => new Promise((res) => {
    const eff = (el) => { let o = 1; for (; el && el.nodeType === 1; el = el.parentElement) o *= +getComputedStyle(el).opacity; return o; };
    const t0 = performance.now(); let t50 = null, t99 = null, first = null;
    (function f(now) {
      const rows = [...document.querySelectorAll('.jobs-section .jobs tbody tr')].slice(0, 6);
      if (rows.length) { const lo = Math.min(...rows.map(eff)), hi = Math.max(...rows.map(eff));
        if (first === null && hi > .05) first = Math.round(now); if (t50 === null && lo >= .5) t50 = Math.round(now); if (t99 === null && lo >= .99) { t99 = Math.round(now); } }
      if (t99 !== null || now - t0 > 2500) res({ firstPixelMs: first, halfwayMs: t50, readableMs: t99 }); else requestAnimationFrame(f);
    })(t0);
  }));
  const out = {};
  for (const vp of ['desktop', 'mobile']) for (const v of ['baseline', 'proposed']) {
    const a = await open({ vp }); await a.page.addInitScript(() => { window.__ready = null; });
    await a.page.goto(`${srv[v].url}/results`, { referer: `${srv[v].url}/running`, waitUntil: 'commit' });
    const arr = await readable(a.page);
    await sleep(900);
    await a.page.locator('nav.views a', { hasText: 'Backend Engineer' }).first().click({ noWaitAfter: true }); await a.page.waitForURL(/track=a/); 
    const swp = await readable(a.page);
    out[`${v} ${vp}`] = { arrival: arr, tabChange: swp };
    await a.ctx.close();
  }
  note_t13(out);
}

// ---- T14: at rest, the proposal is the shipped page, pixel for pixel ---------------------------------------------------------
if (want('T14')) {
  const shots = {};
  for (const vp of ['desktop', 'mobile']) for (const [label, q] of [['All Jobs', ''], ['Backend Engineer', `?track=${'a'.repeat(16)}`], ['240 rows', '?set=long']]) for (const v of ['baseline', 'proposed']) {
    const { ctx, page } = await open({ vp, reduced: true });          // reduced motion: nothing in flight, and the page must still match
    await page.goto(`${srv[v].url}/results${q}`, { waitUntil: 'load' }); await page.evaluate(() => document.fonts.ready); await sleep(900);
    shots[`${vp} ${label} ${v}`] = await page.screenshot({ fullPage: true });
    await ctx.close();
  }
  const diffs = [];
  for (const vp of ['desktop', 'mobile']) for (const label of ['All Jobs', 'Backend Engineer', '240 rows']) {
    const a = shots[`${vp} ${label} baseline`], b = shots[`${vp} ${label} proposed`];
    if (!a.equals(b)) diffs.push(`${vp} ${label}`);
  }
  check('T14', 'at rest (reduced motion, so nothing is in flight) every screenshot of the proposal is byte-identical to the shipped page: 2 widths x 3 views, full page',
    diffs.length === 0, diffs.length ? `differs: ${diffs.join('; ')}` : '6 of 6 identical');
}

// ---- T12: the tool panels' reveal ends clean, survives being hammered, and never flashes for reduced motion ------------
if (want('T12')) {
  const probe = (page) => page.evaluate(() => { const p = document.getElementById('tool-filter'); const cs = getComputedStyle(p);
    return { shown: cs.display !== 'none', h: Math.round(p.getBoundingClientRect().height), op: cs.opacity, overflow: cs.overflow, margin: cs.marginTop, cls: p.className,
      expanded: document.querySelector('[aria-controls=tool-filter]').getAttribute('aria-expanded') }; });
  const { ctx, page } = await open();
  await arrive(page, srv.proposed.url); await sleep(1300);
  const btn = page.locator('button.tool-toggle', { hasText: 'Filter and sort' });
  const natural = await (async () => { await btn.click(); await sleep(600); const r = await probe(page); await btn.click(); await sleep(500); return r; })();
  // mid-flight: sample the height while it opens
  await btn.click(); await sleep(70); const mid = await probe(page); await sleep(400); const opened = await probe(page);
  await btn.click(); await sleep(60); const midClose = await probe(page); await sleep(400); const closed = await probe(page);
  // hammer it: five presses 60 ms apart, an odd number, so it must end open
  for (let i = 0; i < 5; i++) { await btn.click(); await sleep(60); }
  await sleep(600); const hammered = await probe(page);
  check('T12a', 'the panel grows from 0 to its natural height, ends with no clip, no margin and no leftover class, and closes to nothing',
    mid.h > 0 && mid.h < natural.h && opened.h === natural.h && opened.op === '1' && opened.overflow === 'visible' && opened.margin === '0px' && !/t-(in|out|from|to)/.test(opened.cls) &&
    midClose.h < natural.h && !closed.shown, JSON.stringify({ natural: natural.h, mid: mid.h, opened, midClose: midClose.h, closed: closed.shown }));
  check('T12b', 'five presses 60 ms apart leave it open, at natural height, consistent with aria-expanded, with nothing left clipped',
    hammered.shown && hammered.h === natural.h && hammered.op === '1' && hammered.overflow === 'visible' && hammered.expanded === 'true' && !/t-(in|out|from|to)/.test(hammered.cls), JSON.stringify(hammered));
  await ctx.close();
  // reduced motion: sample every frame of a toggle; the panel is either absent or complete, never a hidden-but-present frame
  const r = await open({ reduced: true });
  await arrive(r.page, srv.proposed.url); await sleep(1000);
  const frames = await r.page.evaluate(() => new Promise((res) => {
    const p = document.getElementById('tool-filter'); const b = [...document.querySelectorAll('button.tool-toggle')].find((x) => x.textContent.includes('Filter'));
    const seen = []; let n = 0; b.click();
    (function f() { const cs = getComputedStyle(p); seen.push([cs.display !== 'none', cs.opacity, Math.round(p.getBoundingClientRect().height)]); if (++n < 20) requestAnimationFrame(f); else res(seen); })();
  }));
  const partial = frames.filter(([shown, op, h]) => shown && (op !== '1' || h === 0));
  check('T12c', 'reduced motion: across 20 frames of opening a panel there is no partial frame (no hidden-but-present state)', partial.length === 0, `${frames.length} frames, ${partial.length} partial`);
  await r.ctx.close();
}

{ const f = path.join(mkdir(), 'verify.json'); let prev = []; try { prev = JSON.parse(fs.readFileSync(f, 'utf8')).results; } catch {}
  const ids = new Set(results.map((r) => r.id)); const merged = prev.filter((r) => !ids.has(r.id)).concat(results).sort((a, b) => a.id.localeCompare(b.id, undefined, { numeric: true }));
  fs.writeFileSync(f, JSON.stringify({ at: new Date().toISOString(), chromium: browser.version(), results: merged }, null, 1)); }
await browser.close();
Object.values(srv).forEach((s) => s.stop());
const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} passed`);
process.exit(failed.length ? 1 : 0);
