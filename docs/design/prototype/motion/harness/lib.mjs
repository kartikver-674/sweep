// Shared helpers for the D7A evidence harness (recordings and checks).
//
// Playwright is resolved from PLAYWRIGHT_NODE_MODULES, else from the Codex runtime already on this machine;
// nothing is installed and nothing in the application's dependencies is touched.
import { createRequire } from 'module';
import { spawn } from 'child_process';
import crypto from 'crypto';
import fs from 'fs';
import os from 'os';
import path from 'path';
import { fileURLToPath } from 'url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const MOTION = path.resolve(HERE, '..');
export const ROOT = path.resolve(MOTION, '../../../..');
export const OUT = path.join(ROOT, 'output', 'design-D7A');

const nm = process.env.PLAYWRIGHT_NODE_MODULES
  || path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/');
export const { chromium } = createRequire(nm)('playwright');

export const VIEWPORTS = {
  desktop: { width: 1440, height: 900, isMobile: false, hasTouch: false },
  mobile: { width: 390, height: 844, isMobile: true, hasTouch: true },
};
export const TRACK = { a: 'a'.repeat(16), b: 'b'.repeat(16), c: 'c'.repeat(16) };
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---- the prototype server -------------------------------------------------------------------------------
export async function serve(variant, port, latency = 0) {
  const py = 'python3';
  const p = spawn(py, [path.join(MOTION, 'serve.py'), '--variant', variant, '--port', String(port), '--latency', String(latency)],
    { stdio: 'ignore' });
  for (let i = 0; i < 50; i++) {
    try { const r = await fetch(`http://127.0.0.1:${port}/results`); if (r.ok) break; } catch { /* starting */ }
    await sleep(100);
  }
  return { url: `http://127.0.0.1:${port}`, stop: () => p.kill() };
}

// ---- fonts: the real ones, already in the HTTP cache ---------------------------------------------------------------
// The page asks Google for Bricolage Grotesque and Geist with font-display: swap. A recording must not show a font
// swap a real second visit does not have, so a throwaway page in the same context loads them first and every page
// after it finds them cached (fonts "loaded" at first frame, measured). An earlier version replayed the fonts from
// disk through a request route; the route answered asynchronously, the fonts were still "loading" at first paint,
// and a 3 px reflow appeared in the proposal (and was hidden in the shipped page only by its opacity-0 entrance).
// Offline, the page falls back to the system fonts and nothing shifts.
export async function warmFonts(ctx, url) {
  const w = await ctx.newPage();
  try { await w.goto(`${url}/results`, { waitUntil: 'load' }); await w.evaluate(() => document.fonts.ready); await sleep(150); } catch { /* offline: system fonts */ }
  await w.close();
}

// ---- what every page reports about itself ---------------------------------------------------------------
// Runs in each document before anything else. Observation only: it adds no class, moves no focus, changes no
// style. `window.__m` is read by the harness after a page settles.
export const TRACE = `(() => {
  const m = window.__m = { t0: performance.now(), cls: 0, shifts: [], anim: [], trans: [], frames: [],
    focusCalls: 0, vt: null, overflowMax: 0, errors: [], opened: [] };
  const origFocus = HTMLElement.prototype.focus;
  HTMLElement.prototype.focus = function (...a) { m.focusCalls++; return origFocus.apply(this, a); };
  addEventListener('error', (e) => m.errors.push(String(e.message)));
  addEventListener('unhandledrejection', (e) => m.errors.push('rejection: ' + e.reason));
  window.open = (...a) => { m.opened.push(a[0]); return null; };   // Apply links never leave loopback
  try {
    new PerformanceObserver((l) => l.getEntries().forEach((e) => { if (!e.hadRecentInput) { m.cls += e.value; m.shifts.push([Math.round(e.startTime), +e.value.toFixed(4)]); } }))
      .observe({ type: 'layout-shift', buffered: true });
  } catch (e) {}
  const name = (el) => el && el.nodeType === 1 ? (el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (el.className && el.className.baseVal === undefined ? '.' + String(el.className).split(' ').filter(Boolean).slice(0, 2).join('.') : '')) : String(el);
  document.addEventListener('animationstart', (e) => m.anim.push([e.animationName, name(e.target), Math.round(e.timeStamp)]), true);
  document.addEventListener('transitionrun', (e) => m.trans.push([e.propertyName, name(e.target), Math.round(e.timeStamp)]), true);
  addEventListener('pagereveal', (e) => { m.vt = !!e.viewTransition; });
  m.loaf = []; m.events = [];
  try { new PerformanceObserver((l) => l.getEntries().forEach((e) => m.loaf.push([Math.round(e.startTime), Math.round(e.duration), Math.round(e.blockingDuration)])))
    .observe({ type: 'long-animation-frame', buffered: true }); } catch (e) {}
  try { new PerformanceObserver((l) => l.getEntries().forEach((e) => m.events.push([e.name, Math.round(e.startTime), Math.round(e.processingStart - e.startTime), Math.round(e.duration)])))
    .observe({ type: 'event', durationThreshold: 16, buffered: true }); } catch (e) {}
  // one sample per frame for the first 1.6 s of the document: frame gap, running animations, overflow
  let last = performance.now(); const end = last + 1600;
  (function tick(now) {
    // running only: a finished fill-forwards animation stays in getAnimations() for as long as its element does
    m.frames.push([Math.round(now - m.t0), +(now - last).toFixed(1), document.getAnimations().filter((a) => a.playState === 'running').length]);
    const de = document.documentElement; const ov = de ? de.scrollWidth - innerWidth : 0; if (ov > m.overflowMax) m.overflowMax = ov;
    last = now; if (now < end) requestAnimationFrame(tick);
  })(last);
})();`;

// ---- a visible pointer, for the recordings only ---------------------------------------------------------
// A headless recording has no cursor, so a viewer cannot tell what was pressed. This draws one, and a ring at
// every press. It is not part of the prototype and is left out of every measurement run.
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

// ---- driving the page like a person --------------------------------------------------------------------
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

export async function settle(page, ms = 900) { await sleep(ms); }
export async function metrics(page) { return page.evaluate(() => window.__m); }
export const mkdir = (...p) => { const d = path.join(OUT, ...p); fs.mkdirSync(d, { recursive: true }); return d; };
// ---- aligning the trace with the video -------------------------------------------------------------------------
// Each clip starts and ends with a 160 ms white flash at a known wall-clock time. Finding that flash in the
// decoded video gives the exact offset between the trace's clock and the video's, and any drift across the clip.
import zlib from 'zlib';
import { execFileSync } from 'child_process';
import osmod from 'os';
const FF = path.join(osmod.homedir(), 'Library/Caches/ms-playwright/ffmpeg-1011/ffmpeg-mac');
export async function flash(page, log, label) {
  await page.setContent('<!doctype html><body style="margin:0;background:#fff"></body>');
  log.sync.push({ label: label + ':on', wall: Date.now() - log.t0 });
  await sleep(160);
  await page.setContent('<!doctype html><body style="margin:0;background:#000"></body>');
  log.sync.push({ label: label + ':off', wall: Date.now() - log.t0 });
  // the recorder flushes its last frames late: closing the context straight after a flash can cut it off the video
  await sleep(label === 'end' ? 900 : 240);
}
// mean brightness of every frame, by frame number (25 fps: 40 ms apart)
export function brightness(webm) {
  const tmp = fs.mkdtempSync(path.join(osmod.tmpdir(), 'bright-'));
  execFileSync(FF, ['-hide_banner', '-loglevel', 'error', '-i', webm, '-vf', 'scale=1:1,format=gray', '-fps_mode', 'passthrough', '-frame_pts', '1', path.join(tmp, '%08d.png')]);
  const out = fs.readdirSync(tmp).filter((f) => f.endsWith('.png')).sort().map((f) => {
    const b = fs.readFileSync(path.join(tmp, f)); let o = 8, idat = [];
    while (o < b.length) { const n = b.readUInt32BE(o), t = b.toString('ascii', o + 4, o + 8); if (t === 'IDAT') idat.push(b.subarray(o + 8, o + 8 + n)); o += 12 + n; }
    return [parseInt(f.slice(0, 8), 10) * 40, zlib.inflateSync(Buffer.concat(idat))[1]];
  });
  fs.rmSync(tmp, { recursive: true, force: true });
  return out;
}
// ---- GSAP for the spike: fetched, pinned, never committed ----------------------------------------------------------
// vendor/ is git-ignored. The spike needs GSAP 3.15.0's core file; this fetches exactly that from npm when it is missing,
// so the repository carries no copy of a library whose licence terms the owner has yet to read (D7 note, section 15.9).
export function ensureGsap() {
  const dest = path.join(MOTION, 'vendor', 'gsap.min.js');
  if (fs.existsSync(dest)) return dest;
  const tmp = fs.mkdtempSync(path.join(osmod.tmpdir(), 'gsap-'));
  execFileSync('npm', ['pack', 'gsap@3.15.0', '--silent'], { cwd: tmp, stdio: 'ignore' });
  const tgz = fs.readdirSync(tmp).find((f) => f.endsWith('.tgz'));
  execFileSync('tar', ['xzf', tgz, 'package/dist/gsap.min.js'], { cwd: tmp });
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.copyFileSync(path.join(tmp, 'package/dist/gsap.min.js'), dest);
  fs.rmSync(tmp, { recursive: true, force: true });
  return dest;
}
export { fs, path };
