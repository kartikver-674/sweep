// A10: the public states the design canvas never drew, in a real browser, over the production app on loopback (states-app.py: the A8 harness
// plus the controls these states need). Both themes, 1440 and 390. For each: the page's status and a phrase that proves the right state was
// reached, horizontal overflow against the CONFIGURED width (an emulated phone widens its layout viewport, so scrollWidth - innerWidth reads
// 0 for overflow there), and the contrast measure on every text node.
//
//   node docs/design/sweep-a/harness/states-a.mjs                          checks only
//   STATES_SHOTS=1 D7_OUT=output/design-A10 node docs/design/sweep-a/harness/states-a.mjs     also writes output/design-A10/states/*.png
//   STATES_ONLY=upload-,beta node ...                                      only the states whose id starts with one of these
import { launch, serveApp, visitor, sleep, mkdir, CONTRAST, fs, path, ROOT } from '../../motion-d7b/harness/lib.mjs';

const SHOTS = !!process.env.STATES_SHOTS;
const ONLY = (process.env.STATES_ONLY || '').split(',').filter(Boolean);
const shotDir = SHOTS ? mkdir('states') : null;
const A = 'a'.repeat(16);
const BOUNDARY = '----a10states';
const file = (name, who) => ({ file: { name, who } });

// [id, scenario (null: a visitor with no session), controls, request, expect {status, text}, extra (a function run on the page before measuring), viewport-only?]
const GET = (p) => ({ get: p });
const POST = (p, form = {}) => ({ post: p, form });
const UP = (name, who) => ({ post: '/resume', ...file(name, who) });
const STATES = [
  // ---- Upload ------------------------------------------------------------------------------------------------------------------------
  ['upload-refused-pdf', 'fresh', [], UP('locked.pdf', 'refuse'), { status: 400, text: 'password-protected' }],
  ['upload-scanned-pdf', 'fresh', [], UP('scan.pdf', 'blank'), { status: 400, text: 'no text' }],
  ['upload-daily-limit', 'manage1', ['limit/on'], POST('/derive'), { status: 429, text: 'limit' }],
  ['upload-rooms-full', 'fresh', ['rooms/on'], UP('resume.pdf', 'ada'), { status: 429, text: 'Too many Sweep sessions' }],
  ['upload-failed-card', 'manage3_failed', [], GET('/'), { status: 200, text: 'couldn' }],
  // ---- the door ----------------------------------------------------------------------------------------------------------------------
  ['beta-fresh', null, [], GET('/'), { status: 200, text: 'private beta' }],
  ['beta-wrong-code', null, [], POST('/beta', { code: 'nope' }), { status: 403, text: 'not right' }],
  // ---- reading (deriving.html) -------------------------------------------------------------------------------------------------------
  ['deriving-error', 'x_failed_one', [], GET(`/review?track=${A}`), { status: 502, text: 'could not read' }],
  // ---- Review ------------------------------------------------------------------------------------------------------------------------
  ['review-save-error', 'all_ready', [], POST(`/review?track=${A}`, { term: 'python' }), { status: 400, text: 'weights' }],
  // ---- /key with the worker in trouble ---------------------------------------------------------------------------------------------
  ['key-trouble-needs-key', 'c_paid_one', ['trouble/needs_key'], POST('/run'), { status: 400, text: 'not held any more' }],
  ['key-trouble-gone', 'c_paid_one', ['trouble/gone'], POST('/run'), { status: 502, text: 'no longer available' }],
  ['key-trouble-busy', 'c_paid_one', ['trouble/busy'], POST('/run'), { status: 503, text: 'no room in the queue' }],
  ['key-trouble-paid-off', 'c_paid_one', ['trouble/paid_off'], POST('/run'), { status: 503, text: 'temporarily unavailable' }],
  ['key-trouble-down', 'c_paid_one', ['trouble/down'], POST('/run'), { status: 502, text: 'not responding' }],
  // ---- Configure ---------------------------------------------------------------------------------------------------------------------
  ['configure-error-quick', 'free3', [], POST('/configure', { scope: 'india', max_age_days: '9999' }), { status: 400, text: 'Freshness' }],
  ['configure-error-deep', 'paid', [], POST('/configure', { scope: 'india', max_age_days: '9999' }), { status: 400, text: 'Freshness' }],
  ['configure-sweep-running-quick', 'p_free_one_working', [], GET('/configure'), { status: 200, text: 'View my Sweep' }],
  ['configure-sweep-running-deep', 'p_paid_one_some', [], GET('/configure'), { status: 200, text: 'View my Sweep' }],
  // ---- Confirm -----------------------------------------------------------------------------------------------------------------------
  ['confirm-error', 'c_over_one', [], POST('/run'), { status: [400, 409], text: '' }],
  ['confirm-done-some', 'c_paid_one', ['done/some'], GET('/confirm'), { status: 200, text: 'already done' }],
  ['confirm-done-all', 'c_paid_one', ['done/all'], GET('/confirm'), { status: 200, text: 'already ran today' }],
  ['confirm-late', 'c_paid_one', ['late/on'], GET('/confirm'), { status: 200, text: 'late in the day' }],
  ['confirm-sweep-running', 'p_paid_one_some', [], GET('/confirm'), { status: 200, text: 'View my Sweep' }],
  // ---- Progress, queued --------------------------------------------------------------------------------------------------------------
  ['progress-queued-1', 'x_q1', [], GET('/running'), { status: 200, text: 'queue' }],
  ['progress-queued-3', 'x_q3', [], GET('/running'), { status: 200, text: 'queue' }],
  // ---- Results (rescore is operator-only publicly: these two are unreachable there, audited with the door opened) -------------------------
  ['results-error', 'p_paid_one_done', ['public/rescore'], POST('/rescore', { hours: '9999' }), { status: 400, text: 'Hours to look back' }],
  ['results-notice', 'results', ['public/rescore'], POST('/rescore', { hours: '6' }), { status: 409, text: 'nothing to re-read' }],
  // ---- plan_error.html ---------------------------------------------------------------------------------------------------------------
  ['plan-error', 'free3', ['trouble/plan_fail'], GET('/configure'), { status: 500, text: 'could not plan' }],
  // ---- the active-run strip ----------------------------------------------------------------------------------------------------------
  ['runbar-running-upload', 'p_paid_one_some', [], GET('/'), { status: 200, text: '' }],
  ['runbar-running-review', 'p_paid_one_some', [], GET('/review'), { status: 200, text: '' }],
  ['runbar-finished-upload', 'p_paid_one_done', [], GET('/'), { status: 200, text: '' }],
  ['runbar-finished-review', 'p_paid_one_done', [], GET('/review'), { status: 200, text: '' }],
  ['runbar-reading-upload', 'x_reading', [], GET('/'), { status: 200, text: '' }],
  ['runbar-reading-review', 'x_reading', [], GET('/review'), { status: 200, text: '' }],
  // ---- the feedback dialog (viewport shots: it is a fixed layer) -------------------------------------------------------------------
  ['feedback-empty', 'fresh', [], GET('/'), { status: 200, text: '' }, 'feedback-empty', true],
  ['feedback-filled', 'fresh', [], GET('/'), { status: 200, text: '' }, 'feedback-filled', true],
  ['feedback-failed', 'fresh', [], GET('/'), { status: 200, text: '' }, 'feedback-failed', true],
  ['feedback-sent', 'fresh', [], GET('/'), { status: 200, text: '' }, 'feedback-sent', true],
  // ---- 404 (a visitor inside the door) ------------------------------------------------------------------------------------------------
  ['not-found', 'fresh', [], GET('/this-page-does-not-exist'), { status: 404, text: '' }],
  ['not-found-markup', 'fresh', [], GET('/%3Cscript%3Ex%3C/script%3E'), { status: 404, text: '' }],
];

const app = await serveApp({ port: Number(process.env.STATES_PORT || 5611), script: path.join(ROOT, 'docs/design/sweep-a/harness/states-app.py') });
const browser = await launch();
const rows = []; let bad = 0;
const ctl = (c) => app.api(`/_x/${c}`);

// a navigation that is a POST (a form the visitor filled), so the page that comes back is the real response to it
async function navigate(page, req) {
  if (req.get) return page.goto(app.url + req.get, { waitUntil: 'networkidle', timeout: 25000 });
  const url = app.url + req.post;
  let body, type;
  if (req.file) {
    body = `--${BOUNDARY}\r\nContent-Disposition: form-data; name="resume"; filename="${req.file.name}"\r\nContent-Type: application/pdf\r\n\r\n%PDF-1.7 ${req.file.who}\r\n--${BOUNDARY}--\r\n`;
    type = `multipart/form-data; boundary=${BOUNDARY}`;
  } else { body = new URLSearchParams(req.form).toString(); type = 'application/x-www-form-urlencoded'; }
  const handler = (route) => route.continue({ method: 'POST', postData: body, headers: { ...route.request().headers(), 'content-type': type } });
  await page.route(url, handler);
  try { return await page.goto(url, { waitUntil: 'networkidle', timeout: 25000 }); } finally { await page.unroute(url, handler); }
}

async function feedback(page, mode) {
  await page.locator('[data-feedback-open]').click(); await sleep(250);
  if (mode === 'feedback-empty') return;
  await page.fill('#feedback [name=email]', 'ada@example.com');
  await page.selectOption('#feedback [name=type]', 'bug');
  await page.fill('#feedback [name=subject]', 'The brush is slow');
  await page.fill('#feedback [name=feedback]', 'The desk stutters when I drag the brush on my phone.');
  if (mode === 'feedback-filled') return;
  await page.route('**/feedback', (r) => r.fulfill(mode === 'feedback-sent'
    ? { status: 200, contentType: 'application/json', body: '{"ok":true}' }
    : { status: 500, contentType: 'application/json', body: '{"ok":false}' }));
  await page.locator('[data-feedback-send]').click(); await sleep(500);
}

for (const scheme of ['light', 'dark']) {
  process.env.D7_SCHEME = scheme;
  for (const vp of ['desktop', 'mobile']) {
    for (const [id, scenario, controls, req, expect, extra, viewportOnly] of STATES) {
      if (ONLY.length && !ONLY.some((p) => id.startsWith(p))) continue;
      await ctl('reset');
      for (const c of controls) await ctl(c);
      let ctx, page;
      try {
        ({ ctx, page } = await visitor(browser, app, scenario, { vp, trace: false }));
        await page.route('**/derive*', (r) => (r.request().method() === 'GET' ? r.fulfill({ status: 200, contentType: 'application/json', body: '{"state":"idle"}' }) : r.continue()));
        const res = await navigate(page, req);
        await sleep(700);
        if (extra) await feedback(page, extra);
        await page.addStyleTag({ content: '*, *::before, *::after { animation: none !important; transition: none !important; }' }); await sleep(200);
        const status = res.status();
        const body = await page.evaluate(() => document.body.innerText.replace(/\s+/g, ' '));
        const want = [].concat(expect.status);
        const reached = want.includes(status) && body.toLowerCase().includes(expect.text.toLowerCase());
        const width = page.viewportSize().width;
        const overflow = await page.evaluate((w) => document.documentElement.scrollWidth - w, width);
        const c = await page.evaluate(`(${CONTRAST})()`);
        if (SHOTS) await page.screenshot({ path: path.join(shotDir, `${id}-${scheme}-${vp === 'desktop' ? 'd' : 'm'}.png`), fullPage: !viewportOnly });
        const failed = !reached || overflow > 0 || c.failCount > 0;
        if (failed) bad++;
        rows.push({ scheme, vp, id, status, reached, overflow, nodes: c.nodes, worst: c.worst, worstText: c.worstText, failCount: c.failCount, fails: c.fails });
        console.log(failed ? 'FAIL' : 'ok  ', scheme, vp.padEnd(7), id.padEnd(30), status, reached ? '' : `NOT REACHED (want ${want} "${expect.text}"; says: ${body.slice(0, 140)})`,
          overflow > 0 ? `OVERFLOW ${overflow}px` : '', `contrast ${c.worst}`, c.failCount ? JSON.stringify(c.fails).slice(0, 400) : '');
      } catch (err) {
        bad++; console.log('FAIL', scheme, vp, id, 'threw', String(err.message).slice(0, 200));
        rows.push({ scheme, vp, id, error: String(err.message) });
      } finally { if (ctx) await ctx.close(); }
    }
  }
}
await ctl('reset');
await browser.close(); app.stop();
fs.writeFileSync(path.join(mkdir('states'), 'states-a.json'), JSON.stringify({ when: new Date().toISOString(), rows }, null, 1));
console.log(`${rows.length - bad} of ${rows.length} state pages pass (right state reached, no overflow against the configured width, no text under AA)`);
process.exit(bad ? 1 : 0);
