// Shared helpers for the D7B evidence harness: checks, recordings and at-rest captures against the PRODUCTION
// application (harness/app.py serves the real Render app and the real worker on loopback, with synthetic data).
//
// Playwright is resolved from PLAYWRIGHT_NODE_MODULES, else from the Codex runtime already on this machine;
// nothing is installed and nothing in the application's dependencies is touched.
import { createRequire } from 'module';
import { spawn, execFileSync } from 'child_process';
import fs from 'fs';
import os from 'os';
import path from 'path';
import zlib from 'zlib';
import { fileURLToPath } from 'url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const D7B = path.resolve(HERE, '..');
export const ROOT = path.resolve(D7B, '../../..');
// D7_OUT=output/design-D7C sends every script's evidence somewhere else (D7C reuses these scripts); D7B's own default is unchanged.
export const OUT = process.env.D7_OUT ? path.resolve(ROOT, process.env.D7_OUT) : path.join(ROOT, 'output', 'design-D7B');

const nm = process.env.PLAYWRIGHT_NODE_MODULES
  || path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/');
const pw = createRequire(nm)('playwright');
export const PW_VERSION = createRequire(nm)('playwright/package.json').version;
export const engines = { chromium: pw.chromium, firefox: pw.firefox, webkit: pw.webkit };

// Every uncaught script error and every console error any page of the run raised (the run reports them at the end).
// A failed load that a check causes on purpose (a navigation it stops, a request it holds) shows up here too, and is listed, not hidden.
export const RUNTIME = { pageErrors: [], consoleErrors: [] };

export const VIEWPORTS = {
  desktop: { width: 1440, height: 900, isMobile: false, hasTouch: false },
  mobile: { width: 390, height: 844, isMobile: true, hasTouch: true },
};
export const TRACK = { a: 'a'.repeat(16), b: 'b'.repeat(16), c: 'c'.repeat(16) };
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export const mkdir = (...p) => { const d = path.join(OUT, ...p); fs.mkdirSync(d, { recursive: true }); return d; };

// ---- which engine -------------------------------------------------------------------------------------------------------
// --engine chromium|firefox|webkit (default chromium). An engine whose binary is not installed is reported, not faked.
export const argv = (name, dflt = '') => { const i = process.argv.indexOf('--' + name); return i < 0 ? dflt : (process.argv[i + 1] ?? true); };
export async function launch(engine = argv('engine', 'chromium'), args = [], channel = argv('channel', '')) {
  const e = engines[engine];
  try {
    return await e.launch({ args, ...(channel ? { channel } : {}) });
  } catch (err) {
    console.log(`ENGINE ${engine}: not available here — ${String(err.message).split('\n')[0]}`);
    return null;
  }
}

// ---- the application -------------------------------------------------------------------------------------------------------
// harness/app.py, either a tree of this repository (D7B_REPO unset) or an export of another commit.
export async function serveApp({ port = 5077, repo = '', python = path.join(ROOT, '.venv/bin/python'), attach = !!process.env.D7B_ATTACH, script = path.join(HERE, 'app.py') } = {}) {
  const url = `http://127.0.0.1:${port}`;
  const api = async (p_) => { const r = await fetch(url + p_); return r.json(); };
  const make = async (scenario) => { const j = await api(`/__make/${scenario}`); if (!j.ok) throw new Error(`${scenario}: ${j.error}\n${j.trace}`); return j.cookie; };
  if (attach) return { url, api, make, stop: () => {}, log: () => '' };       // a server already running (development)
  const env = { ...process.env, D7B_PORT: String(port), ...(repo ? { D7B_REPO: repo } : {}) };
  const p = spawn(python, [script], { env, stdio: ['ignore', 'pipe', 'pipe'] });
  let log = '';
  p.stdout.on('data', (d) => { log += d; }); p.stderr.on('data', (d) => { log += d; });
  for (let i = 0; i < 300; i++) { if (log.includes('READY')) break; await sleep(100); }
  if (!log.includes('READY')) { p.kill(); throw new Error('app.py did not start: ' + log.slice(-600)); }
  return { url, api, make, stop: () => p.kill(), log: () => log };
}

// harness/local.py: the operator console. Four apps on consecutive ports (see the file): Configure ($8.41 cap), Configure ($2.00 cap),
// Results, and a live Running screen. `local.at(n)` is the base URL of the n-th.
export async function serveLocal({ port = 5078, repo = '', python = path.join(ROOT, '.venv/bin/python'), attach = !!process.env.D7B_ATTACH, script = path.join(HERE, 'local.py') } = {}) {
  const at = (n) => `http://127.0.0.1:${port + n}`;
  const api = async (n, p_) => { const r = await fetch(at(n) + p_); return r.json(); };
  if (attach) return { at, api, stop: () => {}, url: at(0) };
  const env = { ...process.env, D7B_PORT: String(port), ...(repo ? { D7B_REPO: repo } : {}) };
  const p = spawn(python, [script], { env, stdio: ['ignore', 'pipe', 'pipe'] });
  let log = '';
  p.stdout.on('data', (d) => { log += d; }); p.stderr.on('data', (d) => { log += d; });
  for (let i = 0; i < 300; i++) { if (log.includes('READY')) break; await sleep(100); }
  if (!log.includes('READY')) { p.kill(); throw new Error('local.py did not start: ' + log.slice(-600)); }
  return { at, api, stop: () => p.kill(), url: at(0) };
}

// A browser context that is one visitor in a scenario: its session cookie, its viewport, its motion preference.
export async function visitor(browser, app, scenario, { vp = 'desktop', reduced = false, js = true, trace = true, cursor = false,
  video = null, throttle = 1, cookie = null } = {}) {
  const v = VIEWPORTS[vp];
  const opts = { viewport: { width: v.width, height: v.height }, isMobile: v.isMobile && browserName(browser) !== 'firefox', hasTouch: v.hasTouch,
    deviceScaleFactor: 1, javaScriptEnabled: js, reducedMotion: reduced ? 'reduce' : 'no-preference', colorScheme: process.env.D7_SCHEME || 'dark' };  // A1: D7_SCHEME=light captures the public light theme
  if (video) opts.recordVideo = { dir: video, size: { width: v.width, height: v.height } };
  const ctx = await browser.newContext(opts);
  const c = cookie || (scenario ? await app.make(scenario) : null);
  if (c) await ctx.addCookies([{ name: 'session', value: c, url: app.url }]);
  if (js && trace) await ctx.addInitScript(TRACE);
  if (js && cursor) await ctx.addInitScript(CURSOR);
  const page = await ctx.newPage();
  page.on('pageerror', (e) => RUNTIME.pageErrors.push(`[${globalThis.__check || '-'}] ${page.url().replace(app.url, '')} ${String(e.message || e).slice(0, 160)}`));
  page.on('console', (m) => { if (m.type() === 'error') RUNTIME.consoleErrors.push(`[${globalThis.__check || '-'}] ${page.url().replace(app.url, '')} ${m.text().slice(0, 160)}`); });
  if (throttle > 1 && browserName(browser) === 'chromium') { const s = await ctx.newCDPSession(page); await s.send('Emulation.setCPUThrottlingRate', { rate: throttle }); }   // a Chromium-only emulation
  return { ctx, page, cookie: c };
}
const browserName = (b) => (b.browserType ? b.browserType().name() : 'chromium');

// Fonts: the real ones, already in the HTTP cache (D7A: a font swap a second visit would not have must not be in a take).
export async function warmFonts(ctx, url) {
  const w = await ctx.newPage();
  try { await w.goto(`${url}/`, { waitUntil: 'load' }); await w.evaluate(() => document.fonts.ready); await sleep(150); } catch { /* offline: system fonts */ }
  await w.close();
}

// ---- what every page reports about itself ---------------------------------------------------------------------
// Runs in each document before anything else. Observation only: it adds no class, moves no focus, changes no style.
// `window.__m` is read by the harness after a page settles.
export const TRACE = `(() => {
  const m = window.__m = { t0: performance.now(), cls: 0, shifts: [], anim: [], trans: [], frames: [], focusCalls: 0,
    overflowMax: 0, errors: [], opened: [], pageshow: null };
  const origFocus = HTMLElement.prototype.focus;
  HTMLElement.prototype.focus = function (...a) { m.focusCalls++; return origFocus.apply(this, a); };
  addEventListener('error', (e) => m.errors.push(String(e.message)));
  addEventListener('unhandledrejection', (e) => m.errors.push('rejection: ' + e.reason));
  const w = console.warn; console.warn = (...a) => { m.errors.push('warn: ' + a.join(' ').slice(0, 200)); w.apply(console, a); };
  window.open = (...a) => { m.opened.push(a[0]); return null; };   // Apply links never leave loopback
  try {
    new PerformanceObserver((l) => l.getEntries().forEach((e) => { if (!e.hadRecentInput) { m.cls += e.value; m.shifts.push([Math.round(e.startTime), +e.value.toFixed(4)]); } }))
      .observe({ type: 'layout-shift', buffered: true });
  } catch (e) {}
  const name = (el) => el && el.nodeType === 1 ? (el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (el.className && el.className.baseVal === undefined ? '.' + String(el.className).split(' ').filter(Boolean).slice(0, 3).join('.') : '')) : String(el);
  document.addEventListener('animationstart', (e) => m.anim.push([e.animationName, name(e.target), Math.round(e.timeStamp), getComputedStyle(e.target).animationDuration, getComputedStyle(e.target).animationDelay]), true);
  document.addEventListener('transitionrun', (e) => m.trans.push([e.propertyName, name(e.target), Math.round(e.timeStamp), getComputedStyle(e.target).transitionDuration]), true);
  m.loaf = []; m.events = [];
  try { new PerformanceObserver((l) => l.getEntries().forEach((e) => m.loaf.push([Math.round(e.startTime), Math.round(e.duration), Math.round(e.blockingDuration)])))
    .observe({ type: 'long-animation-frame', buffered: true }); } catch (e) {}
  try { new PerformanceObserver((l) => l.getEntries().forEach((e) => m.events.push([e.name, Math.round(e.startTime), Math.round(e.processingStart - e.startTime), Math.round(e.duration)])))
    .observe({ type: 'event', durationThreshold: 16, buffered: true }); } catch (e) {}
  // one sample per frame for the first 2 s of the document: frame gap, running animations, overflow
  let last = performance.now(); const end = last + 2000;
  (function tick(now) {
    // running only: a finished fill-forwards animation stays in getAnimations() for as long as its element does
    m.frames.push([Math.round(now - m.t0), +(now - last).toFixed(1), document.getAnimations ? document.getAnimations().filter((a) => a.playState === 'running').length : 0]);
    const de = document.documentElement; const ov = de ? de.scrollWidth - innerWidth : 0; if (ov > m.overflowMax) m.overflowMax = ov;
    last = now; if (now < end) requestAnimationFrame(tick);
  })(last);
})();`;

// ---- a visible pointer, for the recordings only ---------------------------------------------------------
export const CURSOR = `(() => {
  const mk = () => {
    const d = document.createElement('div');
    d.style.cssText = 'position:fixed;left:0;top:0;width:14px;height:14px;margin:-7px 0 0 -7px;border-radius:50%;background:rgba(255,255,255,.85);box-shadow:0 0 0 1.5px rgba(0,0,0,.55);pointer-events:none;z-index:2147483647;transform:translate(-40px,-40px)';
    const ring = document.createElement('div');
    ring.style.cssText = 'position:fixed;left:0;top:0;width:34px;height:34px;margin:-17px 0 0 -17px;border-radius:50%;border:2px solid rgba(255,255,255,.9);pointer-events:none;z-index:2147483647;opacity:0';
    document.documentElement.append(d, ring);
    let p; try { p = JSON.parse(sessionStorage.getItem('__cur')); } catch (e) {}
    const at = (x, y) => { d.style.transform = 'translate(' + x + 'px,' + y + 'px)'; ring.style.left = x + 'px'; ring.style.top = y + 'px'; try { sessionStorage.setItem('__cur', JSON.stringify([x, y])); } catch (e) {} };
    if (p) at(p[0], p[1]);
    addEventListener('pointermove', (e) => at(e.clientX, e.clientY), true);
    addEventListener('pointerdown', (e) => { at(e.clientX, e.clientY); ring.animate([{ opacity: 1, transform: 'scale(.4)' }, { opacity: 0, transform: 'scale(1.2)' }], { duration: 380, easing: 'ease-out' }); }, true);
  };
  if (document.documentElement) mk(); else document.addEventListener('DOMContentLoaded', mk);
})();`;

// ---- driving the page like a person ---------------------------------------------------------------------
export async function glide(page, x, y, ms = 260) {
  const steps = Math.max(6, Math.round(ms / 16));
  const cur = page.__cur || { x: x - 120, y: y - 60 };
  await page.mouse.move(cur.x, cur.y);
  for (let i = 1; i <= steps; i++) {
    const t = i / steps, e = 1 - Math.pow(1 - t, 3);
    await page.mouse.move(cur.x + (x - cur.x) * e, cur.y + (y - cur.y) * e);
    await sleep(ms / steps);
  }
  page.__cur = { x, y };
}
export async function press(page, locator, { touch = false, glideMs = 260, settle = 120 } = {}) {
  const box = await locator.boundingBox();
  const x = box.x + box.width / 2, y = box.y + Math.min(box.height / 2, 14);
  if (!touch) { await glide(page, x, y, glideMs); await sleep(settle); const t = Date.now(); await page.mouse.click(x, y); return t; }
  const t = Date.now(); await page.touchscreen.tap(x, y); return t;
}
export const M = (page) => page.evaluate(() => window.__m);
export const count = (m, name) => m.anim.filter((a) => a[0] === name).length;

// ---- arriving the way a visitor does: from another stage of the product --------------------------------------------------
export async function arrive(page, app, query = '') {
  await page.goto(`${app.url}/results${query}`, { referer: `${app.url}/running`, waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);
}

// ---- aligning a trace with a video (D7A): each clip starts and ends with a 160 ms white flash at a known wall time ------------
const FF = path.join(os.homedir(), 'Library/Caches/ms-playwright/ffmpeg-1011/ffmpeg-mac');
export { FF };
export async function flash(page, log, label) {
  await page.setContent('<!doctype html><body style="margin:0;background:#fff"></body>');
  log.sync.push({ label: label + ':on', wall: Date.now() - log.t0 });
  await sleep(160);
  await page.setContent('<!doctype html><body style="margin:0;background:#000"></body>');
  log.sync.push({ label: label + ':off', wall: Date.now() - log.t0 });
  await sleep(label === 'end' ? 900 : 240);
}
export function brightness(webm) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'bright-'));
  execFileSync(FF, ['-hide_banner', '-loglevel', 'error', '-i', webm, '-vf', 'scale=1:1,format=gray', '-fps_mode', 'passthrough', '-frame_pts', '1', path.join(tmp, '%08d.png')]);
  const out = fs.readdirSync(tmp).filter((f) => f.endsWith('.png')).sort().map((f) => {
    const b = fs.readFileSync(path.join(tmp, f)); let o = 8; const idat = [];
    while (o < b.length) { const n = b.readUInt32BE(o), t = b.toString('ascii', o + 4, o + 8); if (t === 'IDAT') idat.push(b.subarray(o + 8, o + 8 + n)); o += 12 + n; }
    return [parseInt(f.slice(0, 8), 10) * 40, zlib.inflateSync(Buffer.concat(idat))[1]];
  });
  fs.rmSync(tmp, { recursive: true, force: true });
  return out;
}

// ---- checks ---------------------------------------------------------------------------------------------------------------------
export function checker(file) {
  const results = [], skipped = [];
  // `note`: this check passed through an ENGINE DIFFERENCE branch: what the engine does differently, in words. Never silent.
  const check = (id, what, pass, detail = '', note = '') => {
    results.push({ id, what, pass: !!pass, detail, ...(note ? { engineDifference: note } : {}) });
    console.log(`${pass ? 'PASS' : 'FAIL'}${note ? ' (engine difference)' : ''}  ${id}  ${what}${note ? '\n      ENGINE DIFFERENCE: ' + note : ''}${detail ? '\n      — ' + String(detail).slice(0, 700) : ''}`);
  };
  const skip = (id, reason) => { skipped.push({ id, reason }); console.log(`SKIP  ${id}  ${reason}`); };
  const finish = (extra = {}) => {
    const pass = results.filter((r) => r.pass).length, diffs = results.filter((r) => r.engineDifference).length;
    const unique = (a) => [...new Set(a)];
    const env = { playwright: PW_VERSION, node: process.version, os: `${os.type()} ${os.release()} ${os.arch()}` };
    fs.writeFileSync(path.join(mkdir(), file), JSON.stringify({ when: new Date().toISOString(), pass, total: results.length, engineDifferences: diffs, skipped, env,
      runtime: { pageErrors: unique(RUNTIME.pageErrors), consoleErrors: unique(RUNTIME.consoleErrors) }, ...extra, results }, null, 1));
    console.log(`\n${pass} of ${results.length} checks pass${diffs ? ` (${diffs} through an engine-difference branch)` : ''}${skipped.length ? `, ${skipped.length} skipped (${skipped.map((x) => x.id).join(', ')})` : ''}  -> ${path.relative(ROOT, path.join(OUT, file))}`);
    console.log(`runtime: ${RUNTIME.pageErrors.length} uncaught script errors${RUNTIME.pageErrors.length ? ': ' + unique(RUNTIME.pageErrors).slice(0, 5).join(' | ') : ''}; ${RUNTIME.consoleErrors.length} console errors${RUNTIME.consoleErrors.length ? ': ' + unique(RUNTIME.consoleErrors).slice(0, 5).join(' | ') : ''}`);
    return pass === results.length;
  };
  return { check, finish, skip, results };
}

// The contrast of every visible text node, on its real composited backdrop and the opacity it really has: what D6's
// measure did, and what a group opacity (a dimmed list) does to text AND the background it sits on (contrast.js).
export const CONTRAST = fs.readFileSync(path.join(HERE, 'contrast.js'), 'utf8');
export { fs, path, os };
