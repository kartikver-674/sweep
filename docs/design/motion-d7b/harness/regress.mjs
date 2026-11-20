// D7B: the screens at rest, before and after, captured the same way, at the same hour, from two trees of the same application.
//
//   git archive 7b1ea25 | tar -x -C /tmp/d7b-before          # the parent: the D6 application, exported (no branch, no worktree)
//   node docs/design/motion-d7b/harness/regress.mjs --side before --repo /tmp/d7b-before
//   node docs/design/motion-d7b/harness/regress.mjs --side after
//   node docs/design/motion-d7b/harness/regress.mjs --compare
//
// Every state the D6 regression set covered (Upload, Review, Configure, Key, Confirm, Progress, Results; one résumé and three; public and the
// operator console), plus the states D7 adds (an arrival's rest state, a long list, a dim that has settled, an over-credit Configure). Full-page
// PNGs at 1440 and 390 with CSS animations and transitions finished (Playwright `animations: disabled`), so the comparison is of composition:
// spacing, type, colour and layout. The expected difference is none. `--compare` reports, per state, identical or how many pixels differ and where.
import { launch, argv, serveApp, serveLocal, visitor, sleep, mkdir, OUT, TRACK, fs, path } from './lib.mjs';
import { diff } from './png.mjs';

const side = argv('side', '');
const onlyStates = String(argv('only', '')).split(',').filter(Boolean);
const wantState = (n) => !onlyStates.length || onlyStates.some((o) => n.includes(o));
const ADJ = "summary:has-text('Adjust what Sweep looks for')";
// A5 took the Adjust disclosure away on public pages: the years chip opens the experience editor and a skill chip opens its tuner. So the
// 'review-editor' state clicks the old summary where the tree has one (every tree before A5), and otherwise opens both of those.
const EDITORS = ['button.xp-chip', 'button.tune-chip:not(.tune-add)'];
const A = TRACK.a;

// [name, scenario, path, action]    the public app (harness/app.py)
const PUBLIC = [
  ['review-expanded', 'all_ready', '/review'], ['review-editor', 'all_ready', '/review', { click: ADJ, fallback: EDITORS }], ['review-all-reviewed', 'all_reviewed', '/review'],
  ['review-failed', 'failed', '/review'], ['upload-empty', 'fresh', '/'], ['upload-manage-mixed', 'manage3_mixed', '/'],
  ['configure-free', 'free3', '/configure'], ['configure-paid', 'paid', '/configure'], ['configure-paid-edge', 'edge', '/configure'],
  ['results', 'results', '/results'], ['results-view', 'results', `/results?track=${A}`], ['key', 'reviewed3', '/key'],
  ['confirm-paid', 'c_paid_one', '/confirm'], ['confirm-free', 'c_free_one', '/confirm'], ['confirm-over-multi', 'c_over_multi', '/confirm'],
  ['progress-paid-done', 'p_paid_one_done', '/running'], ['progress-free-working', 'p_free_one_working', '/running'],
  ['progress-free-failed', 'p_free_one_failed', '/running'], ['progress-paid-one-some', 'p_paid_one_some', '/running'],
  ['progress-paid-one-some-tiles', 'p_paid_one_some', '/running', { click: 'details.searches > summary' }],
  ['progress-paid-multi-some', 'p_paid_multi_some', '/running'], ['progress-paid-one-failed', 'p_paid_one_failed', '/running'],
  // Results, the D6 set
  ['m-all', 'm_all', '/results'], ['m-all-resumeA', 'm_all', `/results?track=${A}`], ['m-all-resumeB', 'm_all', `/results?track=${TRACK.b}`], ['m-all-resumeC', 'm_all', `/results?track=${TRACK.c}`],
  ['m-all-filters', 'm_all', '/results', { click: 'button.tool-toggle:has-text("Filter and sort")' }], ['m-all-filtered', 'm_all', '/results?min=40&sort=recent'],
  ['m-all-export', 'm_all', '/results', { click: 'button.tool-toggle:has-text("Export")' }], ['m-long', 'm_long', '/results'], ['m-nopay', 'm_nopay', '/results'],
  ['m-norec', 'm_norec', '/results'], ['m-two', 'm_two', '/results'], ['m-empty', 'm_empty', '/results'], ['m-emptyview', 'm_emptyview', `/results?track=${TRACK.c}`],
  ['m-nomatch', 'm_all', '/results?min=999'], ['m-failed', 'm_failed', '/results'], ['s1', 's1', '/results'],
  ['s1-filters', 's1', '/results', { click: 'button.tool-toggle:has-text("Filter and sort")' }], ['s1-export', 's1', '/results', { click: 'button.tool-toggle:has-text("Export")' }],
  ['s1-empty', 's1_empty', '/results'], ['s1-nomatch', 's1', '/results?q=zzzz'], ['s1-failed', 's1_failed', '/results'],
  // D7 additions
  ['m-19', 'm_19', '/results'], ['m-240-all', 'm_240', '/results?full=1'], ['s1-19', 's1_19', '/results'],
];
// [name, app index, path, action]   the operator console (harness/local.py)
const CONSOLE = [
  ['console-configure', 0, '/configure'], ['console-configure-over', 1, '/configure'], ['console-results', 2, '/results'],
  ['console-results-filters', 2, '/results', { click: 'button.tool-toggle:has-text("Filter and sort")' }], ['console-results-export', 2, '/results', { click: 'button.tool-toggle:has-text("Export")' }],
  ['console-running', 3, '/running', { css: '.meter-facts { visibility: hidden }', wait: 4000 }],
];

if (argv('compare')) {
  const b = path.join(OUT, 'regression-before'), a = path.join(OUT, 'regression-after');
  const names = fs.readdirSync(a).filter((f) => f.endsWith('.png')).sort();
  const rows = []; let same = 0;
  for (const f of names) {
    if (!fs.existsSync(path.join(b, f))) { rows.push({ file: f, same: false, note: 'missing before' }); continue; }
    const ba = fs.readFileSync(path.join(a, f)), bb = fs.readFileSync(path.join(b, f));
    const d = ba.equals(bb) ? { same: true, pixels: 0 } : diff(path.join(b, f), path.join(a, f));
    if (d.same) same++;
    rows.push({ file: f, ...d });
    if (!d.same) console.log('DIFFERS', f, JSON.stringify(d));
  }
  fs.writeFileSync(path.join(OUT, 'regression.json'), JSON.stringify({ when: new Date().toISOString(), states: names.length, identical: same, rows }, null, 1));
  console.log(`${same} of ${names.length} states are pixel-identical before and after`);
  process.exit(0);
}

// The approved D6 evidence as anchors: the same screens, by name, from output/design-D6 (captured by the D5/D6 harness, which lived outside the
// repository, at another hour and with its own data for a few states). Same size and how much of the picture differs, for each screen both sets have.
if (argv('anchors')) {
  const a = path.join(OUT, 'regression-after'); const rows = [];
  for (const f of fs.readdirSync(a).filter((x) => x.endsWith('.png')).sort()) {
    const d6 = ['regression-after', 'after'].map((d) => path.join(OUT, '..', 'design-D6', d, f)).find((x) => fs.existsSync(x));
    if (!d6) continue;
    const d = diff(d6, path.join(a, f)); const total = d.sizes.length === 1 ? d.sizes[0][0] * d.sizes[0][1] : null;
    rows.push({ file: f, d6: path.relative(OUT, d6).replace(/^\.\.\//, ''), sameSize: d.sizes.length === 1, sizes: d.sizes, identical: d.same, differingPixels: d.pixels, share: d.pixels && total ? +(d.pixels / total * 100).toFixed(3) : 0, maxChannelDelta: d.maxChannelDelta });
  }
  fs.writeFileSync(path.join(OUT, 'regression-anchors.json'), JSON.stringify({ when: new Date().toISOString(), compared: rows.length, identical: rows.filter((r) => r.identical).length, sameSize: rows.filter((r) => r.sameSize).length, rows }, null, 1));
  console.log(`${rows.length} screens are in both D6's approved set and this one: ${rows.filter((r) => r.identical).length} identical, ${rows.filter((r) => r.sameSize).length} the same size`);
  for (const r of rows.filter((x) => !x.identical)) console.log(' ', r.file, r.sameSize ? `${r.share}% differ (max delta ${r.maxChannelDelta})` : `sizes ${JSON.stringify(r.sizes)}`);
  process.exit(0);
}

if (!['before', 'after'].includes(side)) { console.log('usage: --side before|after [--repo <tree>]  |  --compare'); process.exit(2); }
const repo = argv('repo', '');
const base = side === 'before' ? 5177 : 5277;
const app = await serveApp({ port: base, repo, attach: false });
const local = await serveLocal({ port: base + 1, repo, attach: false });
const browser = await launch();
const out = mkdir(`regression-${side}`);
const ok = [], bad = [];

// A state at rest is the page with nothing in flight. `animations: disabled` finishes a finite animation but leaves the element on the
// compositor with the animation's fill applied, and text on such a layer is anti-aliased differently (a pixel of edge at most, everywhere the
// page that animates has text): so the animations and transitions are taken off both trees first, which is also what a screenshot of a
// settled page should show. Without this the parent's section and feed entrances show as "differences" of one or two levels on glyph edges.
const REST = '*, *::before, *::after { animation: none !important; transition: none !important; }';
async function shoot(page, file, vw, extra = {}) {
  await page.addStyleTag({ content: REST }); await sleep(250);
  if (extra.css) await page.addStyleTag({ content: extra.css });
  await page.evaluate(() => window.scrollTo(0, 0)); await sleep(150);
  const f = path.join(out, file);
  await page.screenshot({ path: f, fullPage: true, animations: 'disabled' });
  const w = fs.readFileSync(f).readUInt32BE(16);
  if (w !== vw) console.log('  !! PNG width', w, 'for', file);
}

for (const [vp, tag] of [['desktop', 'd'], ['mobile', 'm']]) {
  const vw = vp === 'desktop' ? 1440 : 390;
  for (const [name, scen, p, act] of PUBLIC) {
    if (!wantState(name)) continue;
    try {
      const { ctx, page } = await visitor(browser, app, scen, { vp, trace: false });
      await page.route('**/derive*', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: '{"state":"idle"}' }));
      await page.goto(app.url + p, { waitUntil: 'networkidle', timeout: 25000 }); await sleep(1000);
      if (act?.click) {
        if (act.fallback && !(await page.locator(act.click).count())) for (const sel of act.fallback) { await page.locator(sel).first().click(); await sleep(300); }
        else await page.locator(act.click).first().click();
        await sleep(450);
      }
      await shoot(page, `${name}-${tag}.png`, vw);
      await ctx.close(); ok.push(`${name}-${tag}`);
    } catch (e) { bad.push(`${name}-${tag}: ${String(e.message).split('\n')[0]}`); console.log('ERR', name, tag, String(e.message).split('\n')[0]); }
  }
  for (const [name, n, p, act] of CONSOLE) {
    if (!wantState(name)) continue;
    try {
      const { ctx, page } = await visitor(browser, { url: local.at(n) }, null, { vp, trace: false });
      await page.goto(local.at(n) + p, { waitUntil: 'load', timeout: 25000 });
      await sleep(act?.wait || 1200);
      if (act?.click) { await page.locator(act.click).first().click(); await sleep(450); }
      await shoot(page, `${name}-${tag}.png`, vw, act || {});
      await ctx.close(); ok.push(`${name}-${tag}`);
    } catch (e) { bad.push(`${name}-${tag}: ${String(e.message).split('\n')[0]}`); console.log('ERR', name, tag, String(e.message).split('\n')[0]); }
  }
}
console.log(`${side}: ${ok.length} captured, ${bad.length} failed`); bad.forEach((b) => console.log('  ', b));
await browser.close(); app.stop(); local.stop();
