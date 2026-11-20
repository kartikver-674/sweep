// D7A: does GSAP earn a place? The same arrival written in CSS (the proposal) and in GSAP 3.15.0 (the spike),
// compared on what an animation dependency can make worse: bytes, render blocking, and behaviour when the
// script is slow or never arrives.
//
//   node docs/design/prototype/motion/harness/verify-gsap.mjs
//
// Writes output/design-D7A/verify-gsap.json. Headless Chromium on this machine: the comparison is what counts.
import { chromium, serve, warmFonts, VIEWPORTS, TRACE, sleep, mkdir, MOTION, ensureGsap, fs, path } from './lib.mjs';
ensureGsap();
import zlib from 'zlib';

const out = {};
const note = (k, v) => { out[k] = v; console.log(k.padEnd(34), JSON.stringify(v)); };
const srv = { gsap: await serve('gsap', 8821), css: await serve('proposed', 8822) };
const browser = await chromium.launch();
const open = async ({ route, rate = 1 } = {}) => {
  const v = VIEWPORTS.desktop;
  const ctx = await browser.newContext({ viewport: { width: v.width, height: v.height }, deviceScaleFactor: 1, colorScheme: 'dark' });
  await warmFonts(ctx, srv.css.url); await ctx.addInitScript(TRACE);
  const page = await ctx.newPage();
  if (route) await page.route('**/vendor/gsap.min.js', route);
  if (rate > 1) { const c = await ctx.newCDPSession(page); await c.send('Emulation.setCPUThrottlingRate', { rate }); }
  return { ctx, page };
};
const go = (page, base) => page.goto(`${base}/results`, { referer: `${base}/running`, waitUntil: 'load' });
// rows' effective opacity sampled every frame for the first `ms` of the document. `dips` counts frames on which a row
// that had already appeared got LESS visible: an entrance that blinks. (The first GSAP spike did; nothing caught it
// because only the end state was checked.)
const rowsVisible = (page, ms = 2600) => page.evaluate((ms) => new Promise((res) => {
  const t0 = performance.now(); let firstAllVisible = null, minSeen = 1, dips = 0; const prev = new Map();
  const eff = (el) => { let o = 1; for (; el && el.nodeType === 1; el = el.parentElement) o *= +getComputedStyle(el).opacity; return o; };
  (function f(now) {
    const rows = [...document.querySelectorAll('.jobs tbody tr')].slice(0, 8);
    if (rows.length) {
      const os = rows.map(eff); const lo = Math.min(...os); minSeen = Math.min(minSeen, lo);
      os.forEach((o, i) => { const p = prev.get(i); if (p !== undefined && p > 0.05 && o < p - 0.02) dips++; prev.set(i, o); });
      if (lo === 1 && firstAllVisible === null) firstAllVisible = Math.round(now);
    }
    if (now - t0 < ms) requestAnimationFrame(f); else res({ firstAllVisible, minOpacitySeen: +minSeen.toFixed(2), dips });
  })(t0);
}), ms);

// ---- bytes and evaluation cost ---------------------------------------------------------------------------------
const src = fs.readFileSync(path.join(MOTION, 'vendor/gsap.min.js'));
note('gsap.min.js bytes', { raw: src.length, gzip: zlib.gzipSync(src, { level: 9 }).length, brotli: zlib.brotliCompressSync(src).length });
const evalCost = {};
for (const rate of [1, 6]) {
  const { ctx, page } = await open({ rate });
  await page.setContent('<!doctype html><title>x</title>');
  const ms = await page.evaluate((code) => { const t = []; for (let i = 0; i < 7; i++) { const t0 = performance.now(); (0, eval)(code); t.push(performance.now() - t0); delete window.gsap; } t.sort((a, b) => a - b); return t[3]; }, src.toString());
  evalCost[`${rate}x`] = +ms.toFixed(2);
  await ctx.close();
}
note('gsap parse+run, median of 7 (ms)', evalCost);

// ---- does it reproduce the arrival? -------------------------------------------------------------------------------
{
  const { ctx, page } = await open();
  await go(page, srv.gsap.url); await sleep(1600);
  const s = await page.evaluate(() => ({ gsap: typeof gsap, cls: document.documentElement.className.replace('first-paint', '').trim(),
    inline: [...document.querySelectorAll('.jobs tbody tr')].filter((r) => r.style.opacity !== '').length, min: Math.min(...[...document.querySelectorAll('.jobs tbody tr')].map((r) => +getComputedStyle(r).opacity)) }));
  note('gsap arrival reproduces', s);
  await ctx.close();
}

// ---- fault injection: what the page does when the animation script does not behave -----------------------------------
const base = {};
for (const [label, who] of [['css (proposal)', 'css'], ['gsap sync head + conditional pre-hide + failsafe (the careful version)', 'gsap']]) {
  const r = {};
  {   // F0: nothing wrong
    const { ctx, page } = await open();
    await go(page, srv[who].url); r.visible = await rowsVisible(page); await ctx.close();
  }
  {   // F1: the script is blocked
    const { ctx, page } = await open({ route: (route) => route.abort() });
    await go(page, srv[who].url); r.blocked = { ...(await rowsVisible(page)) }; await ctx.close();
  }
  {   // F2: the script takes 1.5 s
    const { ctx, page } = await open({ route: async (route) => { await sleep(1500); await route.continue(); } });
    await go(page, srv[who].url); r.slow1500 = { ...(await rowsVisible(page)) }; await ctx.close();
  }
  base[label] = r;
}
note('fault injection', base);

// F3: the integration most tutorials show: `defer` the script and pre-hide with plain CSS. The page is rewritten in
// flight so the same fixture is used; nothing else changes.
const deferred = {};
for (const [label, route] of [['defer, script fine', undefined], ['defer, script 1.5 s late', async (r) => { await sleep(1500); await r.continue(); }], ['defer, script blocked', (r) => r.abort()]]) {
  const { ctx, page } = await open({ route });
  await page.route('**/results', async (r) => {
    const resp = await r.fetch(); let html = await resp.text();
    html = html.replace('<script src="/vendor/gsap.min.js"></script>', '<script defer src="/vendor/gsap.min.js"></script>')
      .replace('<script src="/motion/motion-gsap-spike.js"></script>', `<style>.jobs tbody tr:nth-child(-n + 8){opacity:0}</style>
<script defer>document.addEventListener('DOMContentLoaded',function(){ if(!window.gsap) return; gsap.to('.jobs tbody tr:nth-child(-n + 8)',{opacity:1,duration:.14,stagger:.02}); });</script>`);
    await r.fulfill({ response: resp, body: html });
  });
  await go(page, srv.gsap.url);
  deferred[label] = { ...(await rowsVisible(page, 3000)) };
  await ctx.close();
}
note('naive integration (defer + pre-hide)', deferred);

fs.writeFileSync(path.join(mkdir(), 'verify-gsap.json'), JSON.stringify(out, null, 1));
await browser.close(); Object.values(srv).forEach((s) => s.stop());
