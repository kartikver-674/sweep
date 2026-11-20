// D7A: record the complete prototype sequence in a real browser, at normal speed.
//
//   node docs/design/prototype/motion/harness/record.mjs [--only name,name]
//
// Each clip is one continuous Playwright recording (real time, 25 fps VP8 WebM: Playwright's recorder). The
// sequence is the same for every variant so a clip can be compared with its baseline:
//
//   arrive on Results from the Running screen  ->  each résumé tab and back to All Jobs  ->  three tabs
//   pressed 70 ms apart (an interruption)  ->  Filter and sort, Export, close  ->  Apply filters  ->  Back
//
// A second, slow-server clip holds every /results answer for 700 ms. A cursor and a press ring are drawn into
// the recording (lib.mjs CURSOR) so a viewer can see what is pressed; measurement runs (verify.mjs) do not.
import { chromium, serve, warmFonts, VIEWPORTS, TRACK, TRACE, CURSOR, press, sleep, metrics, mkdir, flash, brightness, ensureGsap, fs, path } from './lib.mjs';
ensureGsap();

const only = (process.argv.find((a) => a === '--only') && process.argv[process.argv.indexOf('--only') + 1] || '').split(',').filter(Boolean);

const CLIPS = [];
for (const vp of ['desktop', 'mobile']) {
  CLIPS.push({ name: `baseline-${vp}-normal`, variant: 'baseline', vp, reduced: false });
  CLIPS.push({ name: `proposed-${vp}-normal`, variant: 'proposed', vp, reduced: false });
  CLIPS.push({ name: `proposed-${vp}-reduced`, variant: 'proposed', vp, reduced: true });
}
CLIPS.push({ name: 'baseline-desktop-reduced', variant: 'baseline', vp: 'desktop', reduced: true });
CLIPS.push({ name: 'proposed-desktop-slow-server', variant: 'proposed', vp: 'desktop', reduced: false, slow: true });
CLIPS.push({ name: 'baseline-desktop-slow-server', variant: 'baseline', vp: 'desktop', reduced: false, slow: true });
CLIPS.push({ name: 'proposed-vt-desktop-normal', variant: 'proposed-vt', vp: 'desktop', reduced: false });
CLIPS.push({ name: 'gsap-desktop-normal', variant: 'gsap', vp: 'desktop', reduced: false });
CLIPS.push({ name: 'proposed-mobile-slow-server', variant: 'proposed', vp: 'mobile', reduced: false, slow: true });

const TABS = ['All Jobs', 'Backend Engineer', 'Full Stack Web Developer', 'Platform Engineer'];

async function sequence(page, base, touch, log, slow) {
  const tab = (t) => page.locator('nav.views a', { hasText: t }).first();
  const hold = (ms) => sleep(ms);
  const step = async (label, fn) => { log.steps.push({ label, tMs: Date.now() - log.t0 }); await fn(); };
  const press_ = async (loc, o) => { const t = await press(page, loc, { touch, ...o }); log.clicks.push({ step: log.steps.at(-1).label, tMs: t - log.t0 }); };
  const after = async (ms) => { await page.waitForLoadState('load').catch(() => {}); await hold(ms); };

  await flash(page, log, 'start');
  await hold(300);
  await step('arrive from the Running screen', async () => {
    await page.goto(`${base}/results`, { referer: `${base}/running`, waitUntil: 'load' });
    await hold(1900);
  });
  log.pages.push({ at: 'arrival', m: await metrics(page) });

  if (slow) {
    for (const t of ['Backend Engineer', 'Platform Engineer']) {
      await step(`tab (slow server): ${t}`, async () => { await press_(tab(t)); await after(2100); });
      log.pages.push({ at: `slow:${t}`, m: await metrics(page) });
    }
    await flash(page, log, 'end');
    return;
  }

  for (const t of TABS.slice(1).concat(TABS[0])) {
    await step(`tab: ${t}`, async () => { await press_(tab(t)); await after(1350); });
    log.pages.push({ at: `tab:${t}`, m: await metrics(page) });
  }

  await step('interruption: three tabs pressed 70 ms apart', async () => {
    const xy = {};
    for (const t of TABS.slice(1)) { const b = await tab(t).boundingBox(); xy[t] = [b.x + b.width / 2, b.y + b.height / 2]; }
    const go = async (t) => { const [x, y] = xy[t]; if (touch) await page.touchscreen.tap(x, y); else { await page.mouse.move(x, y); await page.mouse.click(x, y); } };
    await go('Backend Engineer'); await hold(70);
    await go('Full Stack Web Developer'); await hold(70);
    await go('Platform Engineer');
    await after(1700);
  });
  log.pages.push({ at: 'after-interruption', m: await metrics(page), url: page.url() });

  await step('Filter and sort: open', async () => { await press_(page.locator('button.tool-toggle', { hasText: 'Filter and sort' })); await hold(1200); });
  await step('Export: open (Filter closes)', async () => { await press_(page.locator('button.tool-toggle', { hasText: 'Export' })); await hold(1200); });
  await step('Export: close', async () => { await press_(page.locator('button.tool-toggle', { hasText: 'Export' })); await hold(900); });
  await step('Filter and sort: open, Apply filters', async () => {
    await press_(page.locator('button.tool-toggle', { hasText: 'Filter and sort' })); await hold(700);
    await press_(page.locator('.tool-panel form button[type=submit]'));
    await after(1500);
  });
  log.pages.push({ at: 'after-filter-apply', m: await metrics(page) });
  await step('Back', async () => { await page.goBack().catch(() => {}); await hold(1500); });
  log.pages.push({ at: 'after-back', m: await metrics(page).catch(() => null) });
  await flash(page, log, 'end');
}

const dir = mkdir('recordings');
const traces = mkdir('traces');
const servers = {};
const port = { baseline: 8781, proposed: 8782, gsap: 8783, 'proposed-vt': 8784 };
const slowPort = { baseline: 8791, proposed: 8792 };

async function recordClip(clip) {
  const key = clip.slow ? `${clip.variant}-slow` : clip.variant;
  if (!servers[key]) servers[key] = await serve(clip.variant, clip.slow ? slowPort[clip.variant] : port[clip.variant], clip.slow ? 700 : 0);
  const vp = VIEWPORTS[clip.vp];
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: vp.width, height: vp.height }, isMobile: vp.isMobile, hasTouch: vp.hasTouch, deviceScaleFactor: 1,
    reducedMotion: clip.reduced ? 'reduce' : 'no-preference', colorScheme: 'dark',
    recordVideo: { dir: path.join(dir, '.tmp'), size: { width: vp.width, height: vp.height } },
  });
  await warmFonts(ctx, servers[key].url);
  await ctx.addInitScript(TRACE);
  await ctx.addInitScript(CURSOR);
  const page = await ctx.newPage();
  const log = { clip: clip.name, variant: clip.variant, viewport: clip.vp, reducedMotion: clip.reduced, slowServerMs: clip.slow ? 700 : 0,
    fps: 25, t0: Date.now(), steps: [], clicks: [], pages: [], sync: [] };
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await sequence(page, servers[key].url, vp.hasTouch, log, clip.slow);
  log.errors = errors;
  await ctx.close();
  await page.video().saveAs(path.join(dir, `${clip.name}.webm`));
  await browser.close();
  // where the two flashes are in the video, against where the trace says they were
  const br = brightness(path.join(dir, `${clip.name}.webm`));
  const bright = br.filter(([, v]) => v > 200).map(([t]) => t);
  const runs = []; for (const t of bright) { if (runs.length && t - runs.at(-1).at(-1) <= 40) runs.at(-1).push(t); else runs.push([t]); }
  if (runs.length !== 2) throw new Error(`expected two sync flashes in ${clip.name}, found ${runs.length}`);
  const on = (l) => log.sync.find((x) => x.label === l).wall;
  log.videoStartOffsetMs = runs[0][0] - on('start:on');                 // video time = trace time + offset
  log.videoEndOffsetMs = runs[1][0] - on('end:on');
  log.videoDriftMs = log.videoEndOffsetMs - log.videoStartOffsetMs;
  if (Math.abs(log.videoDriftMs) > 400) throw new Error(`implausible clock drift ${log.videoDriftMs} ms in ${clip.name}`);
  log.flashRuns = runs.map((r) => [r[0], r.at(-1)]);
  fs.writeFileSync(path.join(traces, `${clip.name}.json`), JSON.stringify(log, null, 1));
  console.log('recorded', clip.name, `${((Date.now() - log.t0) / 1000).toFixed(1)}s`, `drift ${log.videoDriftMs} ms`, errors.length ? `ERRORS ${errors}` : '');
}

for (const clip of CLIPS) {
  if (only.length && !only.includes(clip.name)) continue;
  for (let attempt = 1; ; attempt++) {           // a clip whose flashes are not both found is recorded again
    try { await recordClip(clip); break; } catch (e) { console.log(`retry ${clip.name} (${attempt}): ${e.message}`); if (attempt >= 3) throw e; }
  }
}
fs.rmSync(path.join(dir, '.tmp'), { recursive: true, force: true });
Object.values(servers).forEach((s) => s.stop());
