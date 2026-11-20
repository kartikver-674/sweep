// A1+: the contrast of every visible text node on the public screens, in both themes, at 1440 and 390.
// Reuses the D7B stack (real public app, synthetic data) and its measure (contrast.js: each node on its real
// composited backdrop and opacity). D7_SCHEME is set per pass, so the system theme decides as it does for a visitor.
//
//   D7_OUT=output/design-A1 node docs/design/sweep-a/harness/contrast-a.mjs
import { launch, serveApp, visitor, sleep, mkdir, CONTRAST, TRACK, fs, path, ROOT } from '../../motion-d7b/harness/lib.mjs';

const STATES = [
  ['upload-empty', 'fresh', '/'], ['upload-manage-mixed', 'manage3_mixed', '/'],
  ['review-expanded', 'all_ready', '/review'], ['review-all-reviewed', 'all_reviewed', '/review'], ['review-failed', 'failed', '/review'],
  ['key', 'reviewed3', '/key'],
  // A6: the Deep setup, one step at a time (an optional 4th item: buttons clicked, in order, before measuring).
  ['key-step1', 'reviewed3', '/key', ['input[value="deep"]', '.cov-deepgo']],
  ['key-step2', 'reviewed3', '/key', ['input[value="deep"]', '.cov-deepgo', '.wstep.open .go-row .secondary']],
  ['key-step3', 'reviewed3', '/key', ['input[value="deep"]', '.cov-deepgo', '.wstep.open .go-row .tertiary']],
  ['configure-free', 'free3', '/configure'], ['configure-paid', 'paid', '/configure'], ['configure-paid-edge', 'edge', '/configure'],
  ['confirm-paid', 'c_paid_one', '/confirm'], ['confirm-free', 'c_free_one', '/confirm'], ['confirm-over-multi', 'c_over_multi', '/confirm'],
  // A7: the peeks opened (Configure's two, Advanced's door, Confirm's breakdown and the add-a-key door), the over and the none-fit states.
  ['configure-paid-peeks', 'paid', '/configure', ['.summary-cost details.peek > summary', '.summary-panel > details.peek > summary', 'details.advanced > summary']],
  ['configure-over-peeks', 'c_over_one', '/configure', ['.summary-cost details.peek > summary', '.summary-panel > details.peek > summary']],
  ['configure-free-advanced', 'free3', '/configure', ['details.advanced > summary']],
  ['confirm-paid-peek', 'c_paid_one', '/confirm', ['.decide > details.peek > summary', 'details.add-key > summary']],
  ['confirm-over-multi-peek', 'c_over_multi', '/confirm', ['.decide > details.peek > summary']],
  ['confirm-none', 'c_none_one', '/confirm', ['.decide > details.peek > summary']],
  ['progress-free-working', 'p_free_one_working', '/running'], ['progress-paid-one-some', 'p_paid_one_some', '/running'],
  ['progress-paid-done', 'p_paid_one_done', '/running'], ['progress-free-failed', 'p_free_one_failed', '/running'],
  // A8: a listing opened to its skills (its chips) with the Searches peek open beside it; every kind of ending (ok, warn, part, plain, with
  // the "Finish the remaining..." panel under them); the free path's explanation opened. The rows carry matched_skills (progress-app.py).
  ['progress-paid-open', 'p_paid_one_some', '/running', ['.feed li button.lm-b', 'details.searches > summary']],
  ['progress-paid-failed', 'p_paid_one_failed', '/running'], ['progress-paid-partial', 'p_paid_one_partial', '/running'],
  ['progress-paid-stopped', 'p_paid_one_stopped', '/running'], ['progress-paid-incomplete', 'p_paid_one_incomplete', '/running'],
  ['progress-free-about', 'p_free_one_working', '/running', ['details.about > summary']],
  ['results', 'results', '/results'], ['m-all', 'm_all', '/results'], ['m-all-resumeA', 'm_all', `/results?track=${TRACK.a}`], ['m-failed', 'm_failed', '/results'],
  // A9: a card's "Why it matched" open (its term chips), the score explainer and the abroad peek open, the Filter and Export panels, one résumé,
  // the sorts that carry no stamp, and the page with nothing to show.
  ['m-all-why', 'm_all', '/results', ['details.why > summary']],
  ['m-all-peeks', 'm_all', '/results', ['details.how-scoring > summary', 'details.jobs-section > summary', 'details.jobs-section details.why > summary']],
  ['m-all-filter', 'm_all', '/results', ['button.tool-toggle:has-text("Filter and sort")']],
  ['m-all-export', 'm_all', '/results', ['button.tool-toggle:has-text("Export")']],
  ['s1-why', 's1', '/results', ['details.why > summary']], ['m-all-recent', 'm_all', '/results?sort=recent'], ['m-nomatch', 'm_all', '/results?min=999'],
];

// progress-app.py is the D7C harness with matched skills on its rows (and one more stage): every earlier state is the same state in it.
const app = await serveApp({ port: 5377, attach: false, script: path.join(ROOT, 'docs/design/sweep-a/harness/progress-app.py') });
const browser = await launch();
const rows = [];
for (const scheme of ['light', 'dark']) {
  process.env.D7_SCHEME = scheme;
  for (const vp of ['desktop', 'mobile']) {
    for (const [name, scen, p, clicks = []] of STATES) {
      const { ctx, page } = await visitor(browser, app, scen, { vp, trace: false });
      await page.route('**/derive*', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: '{"state":"idle"}' }));
      await page.goto(app.url + p, { waitUntil: 'networkidle', timeout: 25000 }); await sleep(800);
      for (const sel of clicks) { await page.locator(sel).first().click(); await sleep(150); }
      await page.addStyleTag({ content: '*, *::before, *::after { animation: none !important; transition: none !important; }' }); await sleep(200);
      const theme = await page.evaluate(() => getComputedStyle(document.documentElement).colorScheme);
      const c = await page.evaluate(`(${CONTRAST})()`);
      rows.push({ scheme, vp, name, theme, nodes: c.nodes, worst: c.worst, worstText: c.worstText, failCount: c.failCount, fails: c.fails });
      console.log(c.failCount ? 'FAIL' : 'ok  ', scheme, vp, name, `worst ${c.worst} "${c.worstText}"`, c.failCount ? JSON.stringify(c.fails) : '');
      await ctx.close();
    }
  }
}
await browser.close(); app.stop();
const out = mkdir('contrast');
fs.writeFileSync(path.join(out, 'contrast-a.json'), JSON.stringify({ when: new Date().toISOString(), rows }, null, 1));
const failing = rows.filter((r) => r.failCount);
console.log(`${rows.length - failing.length} of ${rows.length} pages have no text under AA (4.5:1, 3:1 at 24px or 18.66px bold)`);
process.exit(failing.length ? 1 : 0);
