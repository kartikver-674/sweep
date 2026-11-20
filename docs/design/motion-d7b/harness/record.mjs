// D7B: record the PRODUCTION application in a real browser, at normal speed.
//
//   node docs/design/motion-d7b/harness/record.mjs [--only name,name] [--engine chromium] [--channel chrome]
//
// Each clip is one continuous Playwright recording (real time, 25 fps VP8 WebM). The real Render app and worker (harness/app.py) and
// the operator console (harness/local.py) are served over loopback with synthetic data; nothing is slowed, and a cursor and a press ring
// are drawn into the recording (lib.mjs CURSOR) so a viewer can see what is pressed. Every clip starts and ends with a 160 ms white
// flash, which is how its trace (click times, steps, the server's own calls) is aligned with the video's clock.
//
// Clips, for 1440 and 390 unless the interaction is the same on both:
//   results             arrive from the Running screen, the tabs, an interruption, Filter and sort, Export, Apply filters, Back
//   results-slow        the same server held 700 ms: the list dims after 160 ms and settles when the new one arrives
//   results-reduced     results with prefers-reduced-motion: reduce
//   results-long        240 jobs: the arrival, Show all, scroll, a tab
//   progress-success    a worker run: tiles finish, a listing arrives, the ending, about 400 ms, Results
//   progress-failure    a worker run that fails: the ending, and nowhere to go
//   configure-price     a slow answer: the old figure stays at .85, then the new one is written
//   configure-overcap   the estimate crosses the key's credit, and comes back
//   upload              a file held over the drop zone, files accepted, one removed, a wrong file named
//   console-configure / console-overcap / console-progress   the operator console's meter and Running screen
import { launch, argv, serveApp, serveLocal, visitor, press, glide, sleep, mkdir, flash, brightness, warmFonts, TRACK, fs, path, os } from './lib.mjs';

const only = String(argv('only', '')).split(',').filter(Boolean);
const engine = argv('engine', 'chromium');
const channel = argv('channel', '');
// every engine gets its own folder (recordings, recordings-chrome, recordings-firefox, recordings-webkit): one engine's clips never replace another's
const suffix = channel ? `-${channel}` : engine !== 'chromium' ? `-${engine}` : '';
const app = await serveApp({ port: 5077 });
const local = await serveLocal({ port: 5078 });
const dir = mkdir('recordings' + suffix), traces = mkdir('traces' + suffix);
const browser = await launch(engine);
if (!browser) process.exit(2);
const TABS = { all: 'All Jobs', a: 'Backend Engineer', b: 'MERN Stack Developer', c: 'Applied AI Engineer' };
const tmpPdf = (() => { const d = fs.mkdtempSync(path.join(os.tmpdir(), 'clip-pdfs-')); return (n) => { const f = path.join(d, n); fs.writeFileSync(f, '%PDF-1.7 synthetic\n'); return f; }; })();

// ---- the clip toolkit ------------------------------------------------------------------------------------------------
function toolkit(page, base, touch, log) {
  const step = async (label, fn) => { log.steps.push({ label, tMs: Date.now() - log.t0 }); await fn(); };
  // a control below the fold is scrolled to first (the visitor scrolls), then pressed where it is: `press` aims at the box the page reports
  const press_ = async (loc, o) => { await loc.scrollIntoViewIfNeeded().catch(() => {}); await sleep(200); const t = await press(page, loc, { touch, ...o }); log.clicks.push({ step: log.steps.at(-1).label, tMs: t - log.t0 }); };
  const after = async (ms) => { await page.waitForLoadState('load').catch(() => {}); await sleep(ms); };
  const tab = (t) => page.locator('nav.views a', { hasText: t }).first();
  const tool = (t) => page.locator('button.tool-toggle', { hasText: t });
  const call = async (label, fn) => { log.calls.push({ label, tMs: Date.now() - log.t0 }); return fn(); };     // what the harness told the server, and when
  const mark = (label) => (log.marks ||= []).push({ label, tMs: Date.now() - log.t0 });                       // what the page was seen to do, and when
  const bannerShown = () => page.waitForFunction(() => [...document.querySelectorAll('.banner')].some((b) => getComputedStyle(b).display !== 'none'), null, { timeout: 20000 });
  // On a phone the results stepper (under Advanced) and the estimate are far apart. So the stepper is focused, the estimate is brought into
  // view, and the stepper is operated from the keyboard: what a person would do to watch the figure while changing the setting.
  const stepper = async (aria, touch_) => {
    const b = page.locator(`button[aria-label="${aria}"]`);
    if (!touch_) return press_(b);
    await b.focus(); await page.locator('.headline-figure').scrollIntoViewIfNeeded(); await sleep(700);
    log.clicks.push({ step: log.steps.at(-1).label, tMs: Date.now() - log.t0 }); await page.keyboard.press('Enter');
  };
  return { step, press_, after, tab, tool, call, mark, bannerShown, stepper, hold: sleep };
}

const resultsSequence = async ({ page, app: a, log, touch, reduced }) => {
  const k = toolkit(page, a.url, touch, log);
  await flash(page, log, 'start'); await sleep(300);
  await k.step('the Running screen', async () => { await page.goto(`${a.url}/running`, { waitUntil: 'load' }); await sleep(1500); });
  await k.step('arrive on Results', async () => { await k.press_(page.locator('a', { hasText: 'See the results' }).first()); await k.after(1900); });
  for (const t of [TABS.a, TABS.b, TABS.c, TABS.all]) await k.step(`tab: ${t}`, async () => { await k.press_(k.tab(t)); await k.after(1350); });
  await k.step('interruption: three tabs pressed 70 ms apart', async () => {
    const xy = {}; for (const t of [TABS.a, TABS.b, TABS.c]) { const b = await k.tab(t).boundingBox(); xy[t] = [b.x + b.width / 2, b.y + b.height / 2]; }
    const go = async (t) => { const [x, y] = xy[t]; if (touch) await page.touchscreen.tap(x, y); else { await page.mouse.move(x, y); await page.mouse.click(x, y); } };
    await go(TABS.a); await sleep(70); await go(TABS.b); await sleep(70); await go(TABS.c); await k.after(1700);
  });
  await k.step('Filter and sort: open', async () => { await k.press_(k.tool('Filter and sort')); await sleep(1200); });
  await k.step('Export: open (Filter closes)', async () => { await k.press_(k.tool('Export')); await sleep(1200); });
  await k.step('Export: close', async () => { await k.press_(k.tool('Export')); await sleep(900); });
  await k.step('Filter and sort: open, Apply filters', async () => { await k.press_(k.tool('Filter and sort')); await sleep(700); await k.press_(page.locator('.tool-panel form button[type=submit]')); await k.after(1500); });
  await k.step('Back', async () => { await page.goBack().catch(() => {}); await sleep(1500); });
  await flash(page, log, 'end');
};

const slowSequence = async ({ page, app: a, log, touch }) => {
  const k = toolkit(page, a.url, touch, log);
  await flash(page, log, 'start'); await sleep(300);
  await k.step('the Running screen', async () => { await page.goto(`${a.url}/running`, { waitUntil: 'load' }); await sleep(1500); });
  await k.step('arrive on Results', async () => { await k.press_(page.locator('a', { hasText: 'See the results' }).first()); await k.after(1900); });
  await k.call('hold every Results answer 700 ms', () => a.api('/__latency/results/700'));
  for (const t of [TABS.a, TABS.c]) await k.step(`tab (slow server): ${t}`, async () => { await k.press_(k.tab(t)); await k.after(2300); });
  await k.call('release', () => a.api('/__latency/results/0'));
  await k.step('tab (quick again): All Jobs', async () => { await k.press_(k.tab(TABS.all)); await k.after(1500); });
  await flash(page, log, 'end');
};

const longSequence = async ({ page, app: a, log, touch }) => {
  const k = toolkit(page, a.url, touch, log);
  await flash(page, log, 'start'); await sleep(300);
  await k.step('the Running screen', async () => { await page.goto(`${a.url}/running`, { waitUntil: 'load' }); await sleep(1500); });
  await k.step('arrive on Results', async () => { await k.press_(page.locator('a', { hasText: 'See the results' }).first()); await k.after(2000); });
  await k.step('Show all 240', async () => { await k.press_(page.locator('a', { hasText: /^Show\s+all/ }).first()); await k.after(2200); });
  await k.step('scroll down the list', async () => { for (let i = 0; i < 12; i++) { await page.mouse.wheel(0, 380); await sleep(110); } await sleep(700); });
  await k.step('scroll back up', async () => { for (let i = 0; i < 12; i++) { await page.mouse.wheel(0, -380); await sleep(70); } await sleep(700); });
  await k.step(`tab: ${TABS.b}`, async () => { await k.press_(k.tab(TABS.b)); await k.after(1800); });
  await flash(page, log, 'end');
};

const progressSuccess = async ({ page, app: a, log, touch }) => {
  const k = toolkit(page, a.url, touch, log);
  await flash(page, log, 'start'); await sleep(300);
  await k.step('the Running screen, part-way', async () => { await page.goto(`${a.url}/running`, { waitUntil: 'load' }); await sleep(2200); });
  await k.step('open the Searches panel', async () => { await k.press_(page.locator('details.searches > summary')); await sleep(1200); });
  const done0 = await page.evaluate(() => document.querySelectorAll('.cell.done').length);
  await k.step('searches finish and a listing arrives (the harness tells the worker)', async () => {
    await k.call('ledger: 14 searches done', () => a.api('/__ledger/14')); await k.call('one more listing', () => a.api('/__rows/5'));
    await page.waitForFunction((d) => document.querySelectorAll('.cell.done').length > d, done0, { timeout: 15000 }); k.mark('the tiles landed'); await sleep(2600);
  });
  await k.step('the worker finishes the run', async () => {
    await k.call('release the engine: the run is done', () => a.api('/__step/done'));
    await k.bannerShown(); k.mark('the ending is shown');
    await page.waitForURL(/\/results/, { timeout: 20000 }); k.mark('Results'); await sleep(2600);
  });
  await flash(page, log, 'end');
};

const progressFailure = async ({ page, app: a, log, touch }) => {
  const k = toolkit(page, a.url, touch, log);
  await flash(page, log, 'start'); await sleep(300);
  await k.step('the Running screen, part-way', async () => { await page.goto(`${a.url}/running`, { waitUntil: 'load' }); await sleep(2200); });
  await k.step('the worker fails the run', async () => {
    await k.call('the engine exits with an error', () => a.api('/__step/failed'));
    await k.bannerShown(); k.mark('the ending is shown'); await sleep(3800);
  });
  await flash(page, log, 'end');
};

const configurePrice = async ({ page, app: a, log, touch }) => {
  const k = toolkit(page, a.url, touch, log);
  const slow = touch ? 2600 : 1100, wait = touch ? 4300 : 2700;
  await flash(page, log, 'start'); await sleep(300);
  await k.step('Configure', async () => { await page.goto(`${a.url}/configure`, { waitUntil: 'load' }); await sleep(1800); });
  await k.step('open Advanced', async () => { await k.press_(page.locator('details.advanced > summary')); await sleep(1000); });
  await k.call(`hold every estimate ${slow} ms`, () => a.api(`/__latency/estimate/${slow}`));
  await k.step('five more results per search (a slow answer)', async () => { await k.stepper('Five more results per search', touch); await sleep(wait); });
  await k.step('five more again (a slow answer)', async () => { await k.stepper('Five more results per search', touch); await sleep(wait); });
  await k.call('release', () => a.api('/__latency/estimate/0'));
  await k.step('five fewer (a quick answer)', async () => { await k.stepper('Five fewer results per search', touch); await sleep(1800); });
  await k.step('five fewer (a quick answer)', async () => { await k.stepper('Five fewer results per search', touch); await sleep(1800); });
  await flash(page, log, 'end');
};

const configureOvercap = async ({ page, app: a, log, touch }) => {
  const k = toolkit(page, a.url, touch, log);
  await flash(page, log, 'start'); await sleep(300);
  await k.step('Configure, with a little credit to spare', async () => { await page.goto(`${a.url}/configure`, { waitUntil: 'load' }); await sleep(2000); });
  await k.step('open Advanced', async () => { await k.press_(page.locator('details.advanced > summary')); await sleep(1000); });
  await k.step('five more results per search: over the credit', async () => { await k.stepper('Five more results per search', touch); await sleep(2600); });
  await k.step('five fewer: back under', async () => { await k.stepper('Five fewer results per search', touch); await sleep(2600); });
  await k.step('five more: over again', async () => { await k.stepper('Five more results per search', touch); await sleep(2800); });
  await flash(page, log, 'end');
};

const uploadSequence = async ({ page, app: a, log, touch }) => {
  const k = toolkit(page, a.url, touch, log);
  await flash(page, log, 'start'); await sleep(300);
  await k.step('Upload', async () => { await page.goto(`${a.url}/`, { waitUntil: 'load' }); await sleep(1800); });
  if (!touch) {
    await k.step('a file held over the drop zone', async () => { const b = await page.locator('label.drop').boundingBox(); await glide(page, b.x + b.width / 2, b.y + b.height / 2, 500); await sleep(400);
      await page.locator('label.drop').dispatchEvent('dragover'); await sleep(1200); await page.locator('label.drop').dispatchEvent('dragleave'); await sleep(900); });
  }
  await k.step('two files accepted', async () => { await page.locator('input[type=file]').setInputFiles([tmpPdf('ada_backend_resume.pdf'), tmpPdf('bhaskar_fullstack_resume.pdf')]); await sleep(2000); });
  await k.step('a third file added', async () => { await page.locator('input[type=file]').setInputFiles([tmpPdf('ada_backend_resume.pdf'), tmpPdf('bhaskar_fullstack_resume.pdf'), tmpPdf('chen_platform_resume.pdf')]); await sleep(2000); });
  await k.step('one removed', async () => { await k.press_(page.locator('.picked-row button').nth(1)); await sleep(1500); });
  await k.step('a file that is not a PDF', async () => { const f = tmpPdf('notes.txt'); await page.locator('input[type=file]').setInputFiles([f]); await sleep(2500); });
  await flash(page, log, 'end');
};

const consoleConfigure = async ({ page, log, touch }, n, label) => {
  const base = local.at(n);
  const k = toolkit(page, base, touch, log);
  const toggle = async () => { await k.press_(page.locator('label.choice', { has: page.locator('input[name=site_indeed]') })); };
  await flash(page, log, 'start'); await sleep(300);
  await k.step(`the console's Configure (${label})`, async () => { await page.goto(`${base}/configure`, { waitUntil: 'load' }); await sleep(2000); });
  await k.call('hold every estimate 1.1 s', () => local.api(n, '/__latency/1100'));
  await k.step('switch Indeed off (a slow answer)', async () => { await toggle(); await sleep(2800); });
  await k.step('switch Indeed on (a slow answer)', async () => { await toggle(); await sleep(2800); });
  await k.call('release', () => local.api(n, '/__latency/0'));
  await k.step('switch Indeed off (a quick answer)', async () => { await toggle(); await sleep(2000); });
  await k.step('switch Indeed on (a quick answer)', async () => { await toggle(); await sleep(2200); });
  await flash(page, log, 'end');
};

const consoleProgress = async ({ page, log, touch }) => {
  const base = local.at(3);
  const k = toolkit(page, base, touch, log);
  await local.api(3, '/__reset');
  await flash(page, log, 'start'); await sleep(300);
  await k.step('the console Running screen, part-way', async () => { await page.goto(`${base}/running`, { waitUntil: 'load' }); await sleep(2500); });
  const d0 = await page.evaluate(() => document.querySelectorAll('.cell.done').length);
  await k.step('searches finish and a listing arrives', async () => { await k.call('14 searches done', () => local.api(3, '/__done/14')); await k.call('6 listings', () => local.api(3, '/__rows/6'));
    await page.waitForFunction((d) => document.querySelectorAll('.cell.done').length > d, d0, { timeout: 20000 }); k.mark('the tiles landed'); await sleep(2800); });
  await k.step('the run ends', async () => { await k.call('the engine exits cleanly', () => local.api(3, '/__finish')); await k.bannerShown(); k.mark('the ending is shown'); await page.waitForURL(/\/results/, { timeout: 20000 }); k.mark('Results'); await sleep(2600); });
  await flash(page, log, 'end');
};

// ---- the matrix ---------------------------------------------------------------------------------------------------
const CLIPS = [];
const both = (name, run, scenario, o = {}) => ['desktop', 'mobile'].forEach((vp) => CLIPS.push({ name: `${name}-${vp}`, vp, run, scenario, ...o }));
both('results', resultsSequence, 'm_19');
both('results-slow', slowSequence, 'm_19');
both('results-reduced', resultsSequence, 'm_19', { reduced: true });
both('results-long', longSequence, 'm_240');
both('progress-success', progressSuccess, 'p_paid_one_some');
both('progress-failure', progressFailure, 'p_paid_one_some');
both('configure-price', configurePrice, 'paid');
both('configure-overcap', configureOvercap, 'edge');
both('upload', uploadSequence, 'fresh');
CLIPS.push({ name: 'console-configure-desktop', vp: 'desktop', run: (c) => consoleConfigure(c, 0, 'credit cap $8.41'), local: true });
CLIPS.push({ name: 'console-overcap-desktop', vp: 'desktop', run: (c) => consoleConfigure(c, 1, 'estimate over the $2.00 cap'), local: true });
CLIPS.push({ name: 'console-progress-desktop', vp: 'desktop', run: consoleProgress, local: true });
CLIPS.push({ name: 'console-overcap-mobile', vp: 'mobile', run: (c) => consoleConfigure(c, 1, 'estimate over the $2.00 cap'), local: true });

async function recordClip(clip) {
  // The page trace (lib.mjs TRACE) samples layout on every frame from the first one. Firefox then paints a page before its stylesheet has applied, and the take shows a
  // white frame at some navigations that a visitor never sees (measured: none with the trace off, on this tree and on the parent). The recorder does not read the trace, so
  // Firefox and WebKit are recorded without it; Chromium's clips were made with it and show no such frame.
  const v = await visitor(browser, clip.local ? { url: local.at(0) } : app, clip.local ? null : clip.scenario, { vp: clip.vp, reduced: !!clip.reduced, cursor: true, trace: engine === 'chromium', video: path.join(dir, '.tmp') });
  const { ctx, page } = v;
  if (clip.local) await warmFonts(ctx, local.at(0)); else await warmFonts(ctx, app.url);
  const log = { clip: clip.name, engine: `${channel || engine} ${browser.version()}`, viewport: clip.vp, reducedMotion: !!clip.reduced, scenario: clip.scenario || null, fps: 25,
    t0: Date.now(), steps: [], clicks: [], calls: [], marks: [], sync: [] };
  const errors = []; page.on('pageerror', (e) => errors.push(String(e)));
  // which navigation the page itself made, and when: Progress goes to Results on its own
  page.on('framenavigated', (f) => { if (f === page.mainFrame()) (log.navigations ||= []).push({ url: f.url().replace(/^http:\/\/127\.0\.0\.1:\d+/, ''), tMs: Date.now() - log.t0 }); });
  await clip.run({ page, app, log, touch: clip.vp === 'mobile', reduced: !!clip.reduced });
  log.errors = errors;
  await ctx.close();
  await page.video().saveAs(path.join(dir, `${clip.name}.webm`));
  const br = brightness(path.join(dir, `${clip.name}.webm`));
  const bright = br.filter(([, x]) => x > 200).map(([t]) => t);
  const runs = []; for (const t of bright) { if (runs.length && t - runs.at(-1).at(-1) <= 40) runs.at(-1).push(t); else runs.push([t]); }
  if (runs.length !== 2) throw new Error(`expected two sync flashes in ${clip.name}, found ${runs.length}`);
  const on = (l) => log.sync.find((x) => x.label === l).wall;
  log.videoStartOffsetMs = runs[0][0] - on('start:on'); log.videoEndOffsetMs = runs[1][0] - on('end:on'); log.videoDriftMs = log.videoEndOffsetMs - log.videoStartOffsetMs;
  // Chromium's recorder holds the video to within 100 ms of wall time over a take. Firefox's and WebKit's are about a second off, and that is a roughly constant offset
  // (it does not grow with the length of the take): every trace keeps its measured drift, the filmstrips correct for it linearly, and a timing is never read off a clip,
  // only off the checks.
  const maxDrift = engine === 'chromium' ? 400 : 2000;
  if (Math.abs(log.videoDriftMs) > maxDrift) throw new Error(`implausible clock drift ${log.videoDriftMs} ms in ${clip.name}`);
  log.flashRuns = runs.map((r) => [r[0], r.at(-1)]); log.videoMs = br.at(-1)[0] + 40;
  fs.writeFileSync(path.join(traces, `${clip.name}.json`), JSON.stringify(log, null, 1));
  console.log('recorded', clip.name, `${((Date.now() - log.t0) / 1000).toFixed(1)}s`, `drift ${log.videoDriftMs} ms`, errors.length ? `ERRORS ${errors}` : '');
}

for (const clip of CLIPS) {
  if (only.length && !only.includes(clip.name)) continue;
  for (let attempt = 1; ; attempt++) {            // a clip whose flashes are not both found, or whose harness step failed, is recorded again
    try {
      await app.api('/__latency/all/0'); await app.api('/__latency/results/0'); await app.api('/__latency/estimate/0');
      for (const n of [0, 1, 2, 3]) await local.api(n, '/__latency/0').catch(() => {});
      await recordClip(clip); break;
    } catch (e) { console.log(`retry ${clip.name} (${attempt}): ${String(e.message).split('\n')[0]}`); if (attempt >= 3) throw e; }
  }
}
fs.rmSync(path.join(dir, '.tmp'), { recursive: true, force: true });
await browser.close(); app.stop(); local.stop();
