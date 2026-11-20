// D7B: Configure, Confirm, Upload and the operator console's Running and Results, as assertions against the PRODUCTION application.
//
//   node docs/design/motion-d7b/harness/verify-forms.mjs [--engine chromium] [--only F1,F3]
//
// The public app (harness/app.py, real Render app and worker) and the operator console (harness/local.py). Synthetic data, no provider.
import { launch, argv, serveApp, serveLocal, visitor, M, count, sleep, checker, CONTRAST } from './lib.mjs';
import path from 'path';
import fs from 'fs';
import os from 'os';

const engine = argv('engine', 'chromium');
const channel = argv('channel', '');
const tag = channel || engine;
const only = String(argv('only', '')).split(',').filter(Boolean);
const want = (id) => { const w = !only.length || only.some((o) => id === o || id.replace(/[a-z]$/, '') === o); if (w) globalThis.__check = id; return w; };      // __check: which check a runtime error belongs to
// --suffix NAME writes verify-forms-NAME-<engine>.json instead, so a later pass never overwrites an earlier one
const suffix = argv('suffix', '');
const { check, finish } = checker(suffix ? `verify-forms-${suffix}-${tag}.json` : tag === 'chromium' ? 'verify-forms.json' : `verify-forms-${tag}.json`);
const app = await serveApp({ port: 5077 });
const local = await serveLocal({ port: 5078 });
const browser = await launch(engine);
if (!browser) { app.stop(); local.stop(); process.exit(2); }
const version = `${channel ? 'Google Chrome (channel chrome)' : engine} ${browser.version()}`;
const cookieEdge = await app.make('edge'), cookiePaid = await app.make('paid');
const op = (n) => ({ url: local.at(n) });
const hold = (n, ms) => local.api(n, `/__latency/${ms}`);
const names = (m) => [...new Set(m.anim.map((a) => a[0]))];
const pulse = (n) => ['runpulse', 'pulse', 'slide', 'cellbreath', 'bone-sweep'].includes(n);
const dur = (d) => String(d).split(',').map((x) => x.trim());      // a computed duration lists one per property
const all = (d, v) => dur(d).every((x) => x === v);

// every write to the figure, with its time: a counter would show up as many writes of in-between values
const WRITES = `(() => { window.__w = []; const t0 = performance.now();
  const go = () => { const el = document.querySelector('.meter .numeral') || document.querySelector('.headline-figure .numeral'); if (!el) return setTimeout(go, 20);
    new MutationObserver(() => window.__w.push([Math.round(performance.now() - t0), el.textContent.trim()])).observe(el, { childList: true, characterData: true, subtree: true }); };
  document.addEventListener('DOMContentLoaded', go); })();`;
// the opacity of the figure and of the meter, every frame
const SAMPLER = `window.__o = []; window.__sample = (ms) => { const t0 = performance.now(); const el = () => document.querySelector('.meter') || document.querySelector('.headline-figure');
  (function tick() { const e = el(), n = (e && (e.querySelector('.numeral') || e)); window.__o.push([Math.round(performance.now() - t0), +getComputedStyle(e).opacity, +getComputedStyle(n).opacity, e.className.includes('updating'),
    e.className.includes('over') || !!document.querySelector('.numeral.over'), getComputedStyle(document.querySelector('.meter-fill') || e).transform]); if (performance.now() - t0 < ms) requestAnimationFrame(tick); })(); };`;
// the results stepper lives under Advanced (a closed <details>)
const bump = async (page) => { const d = page.locator('details.advanced'); if (!(await d.evaluate((e) => e.open))) await d.locator('> summary').click(); await sleep(200); await page.locator('button[aria-label="Five more results per search"]').click(); };
const estimates = (page) => { const l = []; page.on('response', async (r) => { if (r.url().endsWith('/estimate')) { try { const j = await r.json(); if (j.total !== undefined) l.push('$' + j.total.toFixed(2)); } catch (e) { /* cancelled */ } } }); return l; };

// ---- F1: the operator meter: the figure is written, never counted; the wait is .85 ------------------------------------------
if (want('F1')) {
  const out = {};
  for (const [label, ms] of [['slow answer (900 ms)', 900], ['fast answer', 0]]) {
    await hold(0, ms);
    const { ctx, page } = await visitor(browser, op(0), null);
    await ctx.addInitScript(WRITES);
    const answered = estimates(page);
    await page.goto(`${op(0).url}/configure`, { waitUntil: 'load' }); await sleep(1000);
    const before = await page.evaluate(() => ({ num: document.querySelector('.meter .numeral').textContent.trim(), fill: Math.round(document.querySelector('.meter-fill').getBoundingClientRect().width) }));
    await page.evaluate(SAMPLER); await page.evaluate(() => window.__sample(1800));
    await page.evaluate(() => { window.__w.length = 0; });
    await page.locator('input[name=site_indeed]').evaluate((el) => { el.checked = !el.checked; el.dispatchEvent(new Event('change', { bubbles: true })); });
    let audit = null;
    if (ms) { await sleep(600); audit = await page.evaluate(`(${CONTRAST})()`); }
    await sleep(ms ? 1800 : 900);
    const s = await page.evaluate(() => ({ writes: window.__w, o: window.__o, num: document.querySelector('.meter .numeral').textContent.trim(), cls: document.querySelector('.meter').className, fill: Math.round(document.querySelector('.meter-fill').getBoundingClientRect().width) }));
    const m = await M(page);
    const minOp = Math.min(...s.o.map((x) => x[1])), minNum = Math.min(...s.o.map((x) => x[2]));
    out[label] = { before, after: { num: s.num, fill: s.fill, cls: s.cls }, writes: s.writes.map((w) => w[1]), answered, minMeterOpacity: +minOp.toFixed(3), minNumeralOpacity: +minNum.toFixed(3),
      widthTransitions: m.trans.filter((t) => t[0] === 'width').map((t) => t[3]), audit: audit && { worst: audit.worst, fails: audit.failCount, nodes: audit.nodes } };
    await ctx.close();
  }
  await hold(0, 0);
  const slow = out['slow answer (900 ms)'], fast = out['fast answer'];
  check('F1', 'the console meter: the figure is written once, with the answer, and is never a figure nobody priced (every write equals an /estimate answer); while the answer is out it keeps the old figure at .85 (every text node AA); the fill follows in 160 ms; a fast answer shows at most a hint of a dip',
    slow.writes.length === 1 && slow.answered.includes(slow.writes[0]) && slow.before.num !== slow.after.num &&
    Math.abs(slow.minMeterOpacity - .85) < .006 && slow.audit.fails === 0 && slow.audit.worst >= 4.5 && slow.widthTransitions.every((d) => all(d, '0.16s')) && slow.widthTransitions.length >= 1 &&
    fast.writes.length === 1 && fast.answered.includes(fast.writes[0]) && fast.minMeterOpacity >= .85,
    JSON.stringify(out));
}

// ---- F2: crossing the cap: a colour and the words that were already there, no shake ----------------------------------------------------
if (want('F2')) {
  await hold(1, 0);
  const { ctx, page } = await visitor(browser, op(1), null);
  const answered = estimates(page);
  await page.goto(`${op(1).url}/configure`, { waitUntil: 'load' }); await sleep(1200);
  const toggle = () => page.locator('input[name=site_indeed]').evaluate((el) => { el.checked = !el.checked; el.dispatchEvent(new Event('change', { bubbles: true })); });
  const snap = () => page.evaluate(() => ({ over: document.querySelector('.meter').classList.contains('over'), fill: getComputedStyle(document.querySelector('.meter-fill')).backgroundColor, num: document.querySelector('.meter .numeral').textContent.trim() }));
  const start = await snap();
  const cross = async (label) => {
    await page.evaluate(() => { window.__m.anim.length = 0; window.__m.trans.length = 0; window.__f = []; const t0 = performance.now();
      (function tick() { const tr = document.querySelector('.meter-track'), fi = document.querySelector('.meter-fill'), nu = document.querySelector('.meter .numeral');
        window.__f.push([Math.round(performance.now() - t0), getComputedStyle(tr).transform, getComputedStyle(fi).transform, getComputedStyle(nu).transform, getComputedStyle(fi).backgroundColor, document.getAnimations().map((a) => a.constructor.name + ':' + (a.animationName || a.transitionProperty)).join(',')]);
        if (performance.now() - t0 < 700) requestAnimationFrame(tick); })(); });
    await toggle(); await sleep(900);
    const f = await page.evaluate(() => window.__f); const m = await M(page);
    const colours = [...new Set(f.map((x) => x[4]))];
    return { label, frames: f.length, transforms: [...new Set(f.flatMap((x) => [x[1], x[2], x[3]]))], colours: colours.length, animationObjects: [...new Set(f.flatMap((x) => x[5].split(',').filter(Boolean)))].filter((a) => !pulse(a.split(':')[1])),
      keyframeAnimations: names(m).filter((n) => !pulse(n)), colourTransitions: m.trans.filter((t) => t[0] === 'background-color' || t[0] === 'color').map((t) => [t[0], t[3]]) };
  };
  const down = await cross('over to under'); const mid = await snap(); const up = await cross('under to over'); const end = await snap();
  check('F2', 'crossing the cap on the console meter, both ways: the fill changes colour over 160 ms and the state is the colour and the words already there; no shake, no overshoot (every transform stays "none" on every frame), no keyframe animation, only transitions',
    start.over && !mid.over && end.over && [down, up].every((x) => x.transforms.every((t) => t === 'none') && x.keyframeAnimations.length === 0 && x.animationObjects.every((a) => a.startsWith('CSSTransition')) && x.colours > 1 &&
      x.colourTransitions.length > 0 && x.colourTransitions.every((c) => all(c[1], '0.16s'))),
    JSON.stringify({ start, mid, end, down, up }));
  await ctx.close();
}

// ---- F3: public Configure: the price is written, the wait is .85 and AA, the cap is a colour ---------------------------------------
if (want('F3')) {
  const out = {};
  for (const vp of ['desktop', 'mobile']) {
    await app.api('/__latency/estimate/900');
    const { ctx, page } = await visitor(browser, app, null, { cookie: cookiePaid, vp });
    await ctx.addInitScript(WRITES);
    const answered = estimates(page);
    await page.goto(`${app.url}/configure`, { waitUntil: 'load' }); await sleep(1200);
    const before = await page.evaluate(() => document.querySelector('.headline-figure .numeral').textContent.trim());
    await page.evaluate(() => { window.__w.length = 0; });
    await page.evaluate(SAMPLER); await page.evaluate(() => window.__sample(2400));
    await bump(page);
    await sleep(600);
    const pend = await page.evaluate(() => ({ figure: +getComputedStyle(document.querySelector('.headline-figure')).opacity, lines: +getComputedStyle(document.querySelector('table.lines')).opacity,
      cls: [document.querySelector('.headline-figure').className, document.querySelector('table.lines').className], num: document.querySelector('.headline-figure .numeral').textContent.trim() }));
    const audit = await page.evaluate(`(${CONTRAST})()`);
    await sleep(2200);
    const s = await page.evaluate(() => ({ writes: window.__w.map((w) => w[1]), num: document.querySelector('.headline-figure .numeral').textContent.trim(), cls: document.querySelector('.headline-figure').className, o: window.__o.map((x) => x[1]) }));
    out[vp] = { before, pending: pend, writes: s.writes, answered, after: s.num, settled: s.cls, worstAudit: audit.worst, auditFails: audit.failCount, nodes: audit.nodes, minFigureOpacity: +Math.min(...s.o).toFixed(3) };
    await ctx.close(); await app.api('/__latency/estimate/0');
  }
  const ok = (vp) => out[vp].pending.cls.every((c) => c.includes('updating')) && Math.abs(out[vp].pending.figure - .85) < .006 && Math.abs(out[vp].pending.lines - .85) < .006 && out[vp].pending.num === out[vp].before &&
    out[vp].writes.length === 1 && out[vp].answered.includes(out[vp].writes[0]) && out[vp].writes[0] === out[vp].after && !out[vp].settled.includes('updating') && out[vp].auditFails === 0 && out[vp].worstAudit >= 4.5;
  check('F3', 'public Configure: while the newest answer is out the old figure stays, at .85, with every text node AA; the new figure is written once with the answer (it equals the /estimate answer) and the dim goes; at 1440 and 390',
    ok('desktop') && ok('mobile'), JSON.stringify(out));
}

// ---- F4: public Configure crossing the credit: colour and words, nothing else ------------------------------------------------------------
if (want('F4')) {
  const { ctx, page } = await visitor(browser, app, null, { cookie: cookieEdge });
  await page.goto(`${app.url}/configure`, { waitUntil: 'load' }); await sleep(1300);
  const snap = () => page.evaluate(() => ({ over: document.querySelector('.headline-figure .numeral').classList.contains('over'), num: document.querySelector('.headline-figure .numeral').textContent.trim(),
    colour: getComputedStyle(document.querySelector('.headline-figure .numeral')).color, border: getComputedStyle(document.querySelector('.headline-figure')).borderTopColor,
    words: (document.querySelector('.headline-figure p.over:not(.numeral)') && getComputedStyle(document.querySelector('.headline-figure p.over:not(.numeral)')).display !== 'none') ? document.querySelector('.headline-figure p.over:not(.numeral)').textContent.trim() : '' }));
  const start = await snap();
  await page.evaluate(() => { window.__m.anim.length = 0; window.__m.trans.length = 0; window.__f = []; const t0 = performance.now();
    (function tick() { const n = document.querySelector('.headline-figure .numeral'), h = document.querySelector('.headline-figure');
      window.__f.push([Math.round(performance.now() - t0), getComputedStyle(n).transform, getComputedStyle(h).transform, getComputedStyle(n).color, document.getAnimations().map((a) => a.constructor.name).join(',')]); if (performance.now() - t0 < 900) requestAnimationFrame(tick); })(); });
  await bump(page);
  await sleep(1300);
  const end = await snap(); const f = await page.evaluate(() => window.__f); const m = await M(page);
  // A7: D7C changed the sentence a visitor's accounts get (the coverage one), and the credit jar wobbles once (a-wobble) when the plan crosses into over: the only keyframe here besides the pulse.
  check('F4', 'public Configure, the estimate crosses the key\'s credit: the figure and the box change colour over 160 ms and the words say so; no animation, no transform on any frame',
    !start.over && end.over && start.words === '' && /more than your key has|^Your connected accounts can run \d+ of \d+ of these paid searches\.$/.test(end.words) && start.colour !== end.colour && start.border !== end.border &&
    f.every((x) => x[1] === 'none' && x[2] === 'none') && names(m).filter((n) => !pulse(n) && n !== 'a-wobble').length === 0 && [...new Set(f.flatMap((x) => x[4].split(',').filter(Boolean)))].every((c) => c === 'CSSTransition' || c === 'CSSAnimation') &&
    m.trans.filter((t) => t[0] === 'color' || t[0] === 'border-color').every((t) => all(t[3], '0.16s')) && m.trans.some((t) => t[0] === 'color'),
    JSON.stringify({ start, end, colourFrames: new Set(f.map((x) => x[3])).size, keyframes: names(m), transitions: m.trans.filter((t) => ['color', 'border-top-color'].includes(t[0])).map((t) => [t[0], t[3]]) }));
  await ctx.close();
}

// ---- F5: the location menu: in at the speed of a press, out at once --------------------------------------------------------------------
if (want('F5')) {
  const { ctx, page } = await visitor(browser, app, null, { cookie: cookiePaid });
  await page.goto(`${app.url}/configure`, { waitUntil: 'load' }); await sleep(1200);
  await page.evaluate(() => { window.__m.trans.length = 0; window.__op = []; const t0 = performance.now(); const menu = document.getElementById('location-menu');
    (function tick() { window.__op.push([Math.round(performance.now() - t0), getComputedStyle(menu).display, +getComputedStyle(menu).opacity, menu.className]); if (performance.now() - t0 < 500) requestAnimationFrame(tick); })(); });
  await page.locator('.picker-toggle').click(); await sleep(700);
  const open = await page.evaluate(() => window.__op); const m = await M(page);
  await page.evaluate(() => { window.__c = []; const t0 = performance.now(); const menu = document.getElementById('location-menu'); document.addEventListener('keydown', () => {}, { once: true });
    (function tick() { window.__c.push([Math.round(performance.now() - t0), getComputedStyle(menu).display, +getComputedStyle(menu).opacity]); if (performance.now() - t0 < 300) requestAnimationFrame(tick); })(); });
  await page.locator('.picker-toggle').click(); await sleep(450);
  const closing = await page.evaluate(() => window.__c);
  const shown = open.filter((x) => x[1] !== 'none');
  const trans = m.trans.filter((t) => t[1].includes('picker-menu') || t[1].includes('location-menu'));
  check('F5', 'the location menu fades in over 120 ms (first shown frame is nearly transparent, it ends fully opaque with no leftover class) and closes at once (no frame where it is half open)',
    shown.length > 2 && shown[0][2] < .6 && shown.at(-1)[2] === 1 && shown.at(-1)[3] === 'picker-menu' && trans.some((t) => t[0] === 'opacity' && t[3] === '0.12s') &&
    closing.filter((x) => x[1] !== 'none' && x[2] < 1).length === 0,
    JSON.stringify({ firstShown: shown[0], last: shown.at(-1), transitions: trans.map((t) => [t[0], t[3]]), closingPartialFrames: closing.filter((x) => x[1] !== 'none' && x[2] < 1).length }));
  await ctx.close();
}

// ---- F6: Upload: an accepted file writes in (only the new one); nothing else moves ------------------------------------------------------------
if (want('F6')) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'pdfs-'));
  const pdf = (n) => { const f = path.join(tmp, n); fs.writeFileSync(f, '%PDF-1.7 synthetic\n'); return f; };
  const fresh = await app.make('fresh');
  const { ctx, page } = await visitor(browser, app, null, { cookie: fresh });
  await page.goto(`${app.url}/`, { waitUntil: 'load' }); await sleep(1200);
  await page.evaluate(() => { window.__m.anim.length = 0; });
  // each file is made ONCE and the same paths are picked again: rewriting a file changes its modification time, and the picker (rightly) treats a file with a
  // new time as a different file (WebKit keeps whole seconds, Firefox milliseconds, so the same sequence read differently in the two)
  const A = pdf('ada_backend.pdf'), B = pdf('bhaskar_fullstack.pdf'), C = pdf('chen_platform.pdf');
  await page.locator('input[type=file]').setInputFiles([A, B]);
  await sleep(700);
  const m1 = await M(page);
  await page.evaluate(() => { window.__m.anim.length = 0; });
  await page.locator('input[type=file]').setInputFiles([A, B, C]);
  await sleep(700);
  const m2 = await M(page);
  const rows = await page.evaluate(() => document.querySelectorAll('.picked-row').length);
  await page.evaluate(() => { window.__m.anim.length = 0; window.__m.trans.length = 0; });
  await page.locator('.picked-row button, .picked-row .tertiary').first().click(); await sleep(500);
  const m3 = await M(page);
  // a message that says what is wrong is on the first frame, not faded in (the drop zone is hidden while the list is full)
  await page.evaluate(() => { window.__e = []; const t0 = performance.now(); const e = document.querySelector('p.error[x-text="bad"]');
    (function tick() { window.__e.push([Math.round(performance.now() - t0), getComputedStyle(e).display, +getComputedStyle(e).opacity]); if (performance.now() - t0 < 400) requestAnimationFrame(tick); })(); });
  const txt = path.join(tmp, 'notes.txt'); fs.writeFileSync(txt, 'x');
  await page.locator('input[type=file]').setInputFiles([txt]); await sleep(600);
  const err = await page.evaluate(() => ({ text: document.querySelector('p.error[x-text="bad"]').textContent.trim().slice(0, 50), frames: window.__e.filter((x) => x[1] !== 'none'), op: window.__e.filter((x) => x[1] !== 'none').map((x) => x[2]) }));
  // drag over the drop zone: a 120 ms colour answer. The pointer is taken off the zone first (the last press, on a row's remove button, can leave it
  // hovering the zone, which is already its "over" colour in WebKit: a drag then changes nothing to answer)
  await page.mouse.move(2, 2); await page.evaluate(() => document.activeElement && document.activeElement.blur()); await sleep(300);
  await page.evaluate(() => { window.__m.trans.length = 0; });
  await page.locator('label.drop').dispatchEvent('dragover'); await sleep(300);
  const over = await page.evaluate(() => ({ cls: document.querySelector('label.drop').className, border: getComputedStyle(document.querySelector('label.drop')).borderTopColor }));
  const m4 = await M(page);
  await page.locator('label.drop').dispatchEvent('dragleave'); await sleep(300);
  check('F6', 'Upload: two accepted files write in over 160 ms, a third writes in alone, removing one moves nothing, an error message is fully there on its first frame, and the drop zone answers a drag over in 120 ms of colour',
    count(m1, 'write-in') === 2 && m1.anim.every((a) => a[3] === '0.16s') && rows === 3 && count(m2, 'write-in') === 1 && names(m3).length === 0 && m3.trans.filter((t) => t[1].includes('picked')).length === 0 &&
    /PDF/.test(err.text) && err.frames.length > 0 && err.op.every((o) => o === 1) &&
    over.cls.includes('over') && m4.trans.some((t) => t[0].startsWith('border') && all(t[3], '0.12s')) && m4.trans.some((t) => t[0] === 'background-color' && all(t[3], '0.12s')),
    JSON.stringify({ firstTwo: count(m1, 'write-in'), third: count(m2, 'write-in'), rows, removal: names(m3), error: err, dragTransitions: m4.trans.map((t) => [t[0], t[3]]) }));
  await ctx.close();
}

// ---- F7: reduced motion on the forms: the same states, no transition, no animation -------------------------------------------------------
if (want('F7')) {
  const out = {};
  {
    const { ctx, page } = await visitor(browser, app, null, { cookie: cookieEdge, reduced: true });
    await page.goto(`${app.url}/configure`, { waitUntil: 'load' }); await sleep(1200);
    await page.evaluate(() => { window.__m.trans.length = 0; window.__m.anim.length = 0; });
    await bump(page); await sleep(1300);
    await page.locator('.picker-toggle').click(); await sleep(400);
    const m = await M(page);
    out.configure = { over: await page.evaluate(() => document.querySelector('.headline-figure .numeral').classList.contains('over')), transitions: m.trans.filter((t) => t[3] !== '0s').length, animations: names(m),
      menu: await page.evaluate(() => { const e = document.getElementById('location-menu'); return [getComputedStyle(e).display, getComputedStyle(e).opacity]; }) };
    await ctx.close();
  }
  {
    const fresh = await app.make('fresh');
    const { ctx, page } = await visitor(browser, app, null, { cookie: fresh, reduced: true });
    await page.goto(`${app.url}/`, { waitUntil: 'load' }); await sleep(1000);
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'pdfs-')); const f = path.join(tmp, 'ada.pdf'); fs.writeFileSync(f, '%PDF-1.7 x');
    await page.locator('input[type=file]').setInputFiles([f]); await sleep(500);
    const m = await M(page);
    out.upload = { rows: await page.evaluate(() => [...document.querySelectorAll('.picked-row')].map((r) => +getComputedStyle(r).opacity)), animations: names(m) };
    await ctx.close();
  }
  {
    const { ctx, page } = await visitor(browser, op(0), null, { reduced: true });
    await page.goto(`${op(0).url}/configure`, { waitUntil: 'load' }); await sleep(1000);
    await page.evaluate(() => { window.__m.trans.length = 0; });
    await page.locator('input[name=site_indeed]').evaluate((el) => { el.checked = !el.checked; el.dispatchEvent(new Event('change', { bubbles: true })); }); await sleep(900);
    const m = await M(page);
    out.meter = { transitions: m.trans.filter((t) => t[3] !== '0s').length, fill: await page.evaluate(() => Math.round(document.querySelector('.meter-fill').getBoundingClientRect().width)) };
    await ctx.close();
  }
  check('F7', 'reduced motion on Configure, Upload and the console meter: the cap is crossed, the menu opens, a file is listed and the fill moves to its value, all complete and at once; no transition or animation runs',
    out.configure.over && out.configure.transitions === 0 && out.configure.animations.length === 0 && out.configure.menu[0] !== 'none' && out.configure.menu[1] === '1' &&
    out.upload.rows.length === 1 && out.upload.rows[0] === 1 && out.upload.animations.length === 0 && out.meter.transitions === 0 && out.meter.fill > 0, JSON.stringify(out));
}

// ---- F8: Confirm: nothing draws or shakes on load, over the cap or not ------------------------------------------------------------------------
if (want('F8')) {
  const out = {};
  for (const sc of ['c_over_multi', 'c_paid_multi', 'c_free_one']) {
    const { ctx, page } = await visitor(browser, app, sc);
    await page.goto(`${app.url}/confirm`, { waitUntil: 'load' }); await sleep(1600);
    const m = await M(page);
    out[sc] = { animations: names(m), transitions: m.trans.filter((t) => !t[1].startsWith('button.')).length, over: await page.evaluate(() => !!document.querySelector('.is-over, .numeral.over')), overflow: m.overflowMax };
    await ctx.close();
  }
  check('F8', 'Confirm, over the credit or not, free or paid: nothing animates or transitions on load (no rail drawn, no figure counted, no shake; only the 120 ms press colour of a button as Alpine enables it), and the over-cap state is simply shown',
    Object.values(out).every((x) => x.animations.length === 0 && x.transitions === 0 && x.overflow <= 0) && out.c_over_multi.over, JSON.stringify(out));
}

// ---- F9: the operator console's Running screen: no rail, tiles and listings only when new, the ending, the redirect --------------------------------
if (want('F9')) {
  const PROBE = `(() => { const log = () => { try { return JSON.parse(sessionStorage.getItem('__p') || '[]'); } catch (e) { return []; } };
    const push = (e) => { try { const l = log(); l.push(e); sessionStorage.setItem('__p', JSON.stringify(l)); } catch (x) {} };
    const now = () => Math.round(performance.timeOrigin + performance.now());
    addEventListener('pagehide', () => push(['pagehide', now(), location.pathname]));
    document.addEventListener('DOMContentLoaded', () => { push(['load', now(), location.pathname]);
      const seen = new Set(); const mo = new MutationObserver(() => { for (const b of document.querySelectorAll('.banner')) { const t = b.querySelector('b').textContent.trim();
        if (getComputedStyle(b).display !== 'none' && !seen.has(t)) { seen.add(t); push(['banner', now(), t, +getComputedStyle(b).opacity, getComputedStyle(b).transitionDuration]); requestAnimationFrame(() => requestAnimationFrame(() => push(['painted', now(), t]))); } } });
      mo.observe(document.body, { subtree: true, attributes: true, attributeFilter: ['style', 'class'] }); });
  })();`;
  await local.api(3, '/__reset');
  const { ctx, page } = await visitor(browser, op(3), null);
  await ctx.addInitScript(PROBE);
  await page.goto(`${op(3).url}/running`, { waitUntil: 'load' }); await sleep(2200);
  const load = await M(page);
  const s0 = await page.evaluate(() => ({ done: document.querySelectorAll('.cell.done').length, marked: document.querySelectorAll('.cell.done[data-was-done]').length, feed: document.querySelectorAll('.feed li').length, fresh: document.querySelectorAll('.feed li.fresh').length,
    meterFill: getComputedStyle(document.querySelector('.meter-fill')).animationName, cap: document.querySelector('.meter-cap') ? getComputedStyle(document.querySelector('.meter-cap')).animationName : 'none' }));
  await page.evaluate(() => { window.__m.anim.length = 0; window.__m.trans.length = 0; });
  // count every listing that is given the write-in marker, whenever the stream brings it
  await page.evaluate(() => { window.__freshAdds = 0; new MutationObserver((l) => l.forEach((m) => { if (m.target.classList && m.target.classList.contains('fresh') && !(m.oldValue || '').includes('fresh')) window.__freshAdds++; })).observe(document.querySelector('.feed'), { subtree: true, attributes: true, attributeFilter: ['class'], attributeOldValue: true }); });
  await local.api(3, '/__done/14'); await local.api(3, '/__rows/6');
  await page.waitForFunction((d) => document.querySelectorAll('.cell.done').length > d, s0.done, { timeout: 15000 });
  await sleep(1200);
  const mid = await M(page);
  const tiles = mid.trans.filter((a) => a[0] === 'background-color' && a[1].includes('cell'));
  const s1 = await page.evaluate(() => ({ done: document.querySelectorAll('.cell.done').length, fresh: document.querySelectorAll('.feed li.fresh').length, feed: document.querySelectorAll('.feed li').length }));
  await sleep(900);
  const s2 = await page.evaluate(() => ({ fresh: document.querySelectorAll('.feed li.fresh').length }));
  const freshAdds = await page.evaluate(() => window.__freshAdds);
  await local.api(3, '/__finish');
  await page.waitForURL(/\/results/, { timeout: 20000 }); await sleep(1500);
  const tl = await page.evaluate(() => JSON.parse(sessionStorage.getItem('__p')));
  const banner = tl.find((e) => e[0] === 'banner'), painted = tl.find((e) => e[0] === 'painted'), hide = tl.find((e) => e[0] === 'pagehide' && e[2] === '/running');
  const res = await M(page);
  check('F9', 'the console\'s Running screen: no rail drawn or cap tick at load (nothing but the liveness pulse runs); the tiles that finish while you watch change colour together (no ripple, no scale) and only the new listing writes in; when the stream says finished the ending fades in and the page goes to Results 400 ms after the ending is painted, which writes in its first rows',
    s0.done >= 4 && s0.fresh === 0 && load.anim.filter((a) => !pulse(a[0])).length === 0 && s0.meterFill === 'none' && s0.cap === 'none' &&
    tiles.length === s1.done - s0.done && tiles.length > 0 && tiles.every((a) => all(a[3], '0.16s')) && !names(mid).includes('tile-land') && freshAdds >= 1 && s2.fresh === 0 &&
    banner && banner[4] === '0.16s' && hide[1] - painted[1] >= 395 && hide[1] - painted[1] <= 540 && count(res, 'write-in') === 8,
    JSON.stringify({ load: { done: s0.done, marked: s0.marked, fresh: s0.fresh, animations: names(load), rail: s0.meterFill, cap: s0.cap }, colourChanges: { tiles: tiles.length, durations: [...new Set(tiles.map((a) => a[3]))] }, feedMarked: freshAdds, markerGone: s2, banner, paintedToPagehide: hide && painted && hide[1] - painted[1], resultsWriteIn: count(res, 'write-in') }));
  await ctx.close();
}

// ---- F10: the console's Results: the same arrival, the same instant swap, the same panels -------------------------------------------------------
if (want('F10')) {
  const { ctx, page } = await visitor(browser, op(2), null);
  await page.goto(`${op(2).url}/results`, { referer: `${op(2).url}/running`, waitUntil: 'load' }); await sleep(1800);
  const m = await M(page);
  const arrive = { writeIn: count(m, 'write-in'), cls: await page.evaluate(() => document.documentElement.className.trim()) };
  await page.evaluate(() => { window.__m.anim.length = 0; });
  await page.locator('button.tool-toggle', { hasText: 'Filter and sort' }).click(); await sleep(450);
  await page.locator('.tool-panel form button[type=submit]').click(); await page.waitForLoadState('load'); await sleep(900);
  const swap = names(await M(page));
  const rows = await page.evaluate(() => ({ n: document.querySelectorAll('tbody tr').length, applied: document.querySelectorAll('tr.applied').length, opacity: [...document.querySelectorAll('tr.applied')].map((r) => getComputedStyle(r).opacity) }));
  const c = await page.evaluate(`(${CONTRAST})()`);
  check('F10', 'the console\'s Results: the first eight rows write in on arrival, a filter apply is an instant swap, applied rows are still readable, no text is under AA at rest',
    arrive.writeIn === 8 && arrive.cls === '' && swap.length === 0 && rows.applied === 2 && rows.opacity.every((o) => o === '1') && c.failCount === 0, JSON.stringify({ arrive, swap, rows, contrast: { worst: c.worst, fails: c.failCount } }));
  await ctx.close();
}

app.stop(); local.stop(); await browser.close();
const ok = finish({ engine: version });
process.exit(ok ? 0 : 1);
