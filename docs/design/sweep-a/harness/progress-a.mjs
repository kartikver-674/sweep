// A8: Progress (public) in a real browser, over the production app on loopback (the D7C harness with matched skills on its rows:
// docs/design/sweep-a/harness/progress-app.py).
//   node docs/design/sweep-a/harness/progress-a.mjs                         checks only
//   PROGRESS_A_SHOTS=1 node docs/design/sweep-a/harness/progress-a.mjs     also writes screenshots to output/design-A8/progress-a/
// Paid, running: the eyebrow and the figure on the right; the brush sits at the end of the fill (within 2px, at every frame while it
// moves) and moves with it; "Now: board · city" names the board and the city of the tile that is running and changes when the next
// tile runs; a listing that arrives after the page did has `.fresh`, drops in (no-preference) and does nothing under reduced motion;
// a listing with skills opens on a click and on Enter and Space, `aria-expanded` follows, one is open at a time, the chips are the row's
// skills (six at most, trimmed); one with none is not a button; the tip dismisses; the Searches peek opens and its aside counts. Every
// ending shows its banner with the words it had at HEAD, and a finished run still goes to the results for a visitor who waited. Free:
// the brush rides the indeterminate bar, the passes carry a marker each, the quiet Stop. 390 / 768 / 1440 without overflow, both themes.
import fs from 'fs';
import path from 'path';
import { launch, serveApp, visitor, sleep, ROOT, OUT } from '../../motion-d7b/harness/lib.mjs';

const SHOTS = !!process.env.PROGRESS_A_SHOTS;
const shotDir = path.join(ROOT, 'output', 'design-A8', 'progress-a');
if (SHOTS) fs.mkdirSync(shotDir, { recursive: true });

const app = await serveApp({ port: 5493, script: path.join(ROOT, 'docs/design/sweep-a/harness/progress-app.py') });
const browser = await launch();
const out = []; let ok = true;
const check = (name, cond, info) => { out.push(`${cond ? 'ok  ' : 'FAIL'} ${name}${info === undefined ? '' : ' ' + info}`); ok = ok && !!cond; };
const polishDir = path.join(OUT, 'polish');
fs.mkdirSync(polishDir, { recursive: true });
const pshot = async (page, name, opts = {}) => { if (process.env.POLISH_SHOTS !== '0') await page.screenshot({ path: path.join(polishDir, name + '.png'), ...opts }); };
const shot = async (page, name) => { if (SHOTS) await page.screenshot({ path: path.join(shotDir, name + '.png'), fullPage: true }); };

const open = (scenario, o = {}) => visitor(browser, app, scenario, { trace: true, ...o });
const go = async (page, p = '/running', wait = 700) => { await page.goto(app.url + p, { waitUntil: 'networkidle' }); await sleep(wait); };
const text = (page, sel) => page.locator(sel).first().textContent().then((t) => t.replace(/\s+/g, ' ').trim());
const visible = (page, sel) => page.locator(sel).first().isVisible();
// Against the viewport the visitor was given, not `innerWidth`: an emulated phone widens its layout viewport to fit overflowing content, which
// hides the overflow from a measure that reads innerWidth (the first build of the brush overhung the page by 18px at 390 and read as 0).
const overflow = (page) => page.evaluate((w) => document.documentElement.scrollWidth - w, page.viewportSize().width);
const progress = (page) => page.evaluate(() => fetch('/progress', { credentials: 'same-origin' }).then((r) => r.json()));
const anims = (page) => page.evaluate(() => (window.__m ? window.__m.anim.map((a) => a[0]) : []));
const BOARDS = { linkedin: 'LinkedIn', indeed: 'Indeed', naukri: 'Naukri' };
const where = (t) => t.label.split(' @ ').pop();
const firstOpen = (p) => p.tiles.find((t) => t.state !== 'done');
const waitFor = (page, fn, arg, ms = 12000) => page.waitForFunction(fn, arg, { timeout: ms });

// What each ending said at HEAD (6e6719d... 33eb49d): the banner's heading, and the page's h1.
const ENDINGS = [
  // [scenario, the h1, the banner's own heading, a phrase of its sentence]
  ['p_paid_one_stopped', 'You stopped the sweep', 'You stopped it', 'searches did not run. Everything already fetched is saved.'],
  ['p_paid_one_out_of_credit', 'Sweep stopped early', 'The credit ran out', 'Every key on file is spent, so the sweep stopped at'],
  ['p_paid_one_refused', 'Your search did not start', 'Your Apify credit changed', 'could no longer safely cover the full plan'],
  ['p_paid_one_partial', 'Part of your search ran', 'The part your credit covers ran', 'paid searches ran, as you chose.'],
  ['p_paid_one_failed', 'Sweep stopped early', 'The reason is not recorded', 'and the reason is not recorded — the credit is not spent.'],
  ['p_paid_one_timeout', 'Sweep stopped early', 'The sweep ran out of time', 'because the sweep reached its time limit.'],
  ['p_paid_one_incomplete', 'The sweep did not finish', 'Every search ran, then the sweep stopped', 'All 120 searches ran, so their credit is spent.'],
  ['p_paid_one_done', 'Your jobs are ready', 'Every search ran', 'All 120 of them. Nothing was left outstanding.'],
];

for (const scheme of ['light', 'dark']) {
  process.env.D7_SCHEME = scheme;
  const T = (s) => `${scheme}/${s}`;

  // ================= Paid, running, desktop ===========================================================================
  {
    const { ctx, page } = await open('p_paid_one_some', { vp: 'desktop' });
    await go(page);
    const p0 = await progress(page);
    const tickBefore = await text(page, '.ticker');
    check(T('paid: eyebrow, headline, the figure on the right of them'),
      (await text(page, 'main .eyebrow')) === 'Step 3 · Deep Sweep' && (await text(page, 'main h1')) === 'Sweep is searching for you'
      && await page.evaluate(() => { const h = document.querySelector('main h1').getBoundingClientRect(), f = document.querySelector('.headline-figure.found').getBoundingClientRect();
        return f.left > h.left + 300 && f.top < h.bottom && f.width > 60; }));
    check(T('paid: the brush is decoration, set by the same number as the fill, no Jinja in a style attribute'),
      await page.evaluate(() => { const r = document.querySelector('.activity-track > .rider'); return !!r && r.getAttribute('aria-hidden') === 'true' && !!r.querySelector('svg')
        && r.previousElementSibling.classList.contains('activity-fill') && !document.querySelector('.activity-track').getAttribute('aria-hidden'); }));

    // the brush at the fill's end, and with it while it moves: every frame for the whole time a poll takes to land
    await page.evaluate(() => {
      window.__r = [];
      const fill = document.querySelector('.activity-fill'), rider = document.querySelector('.activity-track > .rider');
      (function tick() { window.__r.push([Math.round(performance.now()), fill.getBoundingClientRect().right, rider.getBoundingClientRect().left]); requestAnimationFrame(tick); })();
    });
    await sleep(300);
    const at0 = await page.evaluate(() => window.__r.at(-1));
    check(T('paid: at rest the brush sits at the end of the fill (within 2px)'), Math.abs(at0[1] - at0[2]) <= 2, JSON.stringify(at0));
    await app.api('/__ledger/14'); await app.api('/__rows/5');
    await waitFor(page, () => document.querySelectorAll('.cell.done').length >= 0 && window.__r.some((f) => f[1] - window.__r[0][1] > 20), null, 15000);
    await sleep(900);
    const frames = await page.evaluate(() => window.__r);
    const moved = frames.at(-1)[1] - frames[0][1];
    const worst = Math.max(...frames.map((f) => Math.abs(f[1] - f[2])));
    check(T('paid: the brush moves with the fill, never more than 2px from its end, at any frame'), moved > 20 && worst <= 2, `moved ${moved.toFixed(1)}px, worst ${worst.toFixed(2)}px over ${frames.length} frames`);
    const mid = frames.filter((f) => f[1] > frames[0][1] + 2 && f[1] < frames.at(-1)[1] - 2).length;
    check(T('paid: it travels (the fill and the brush pass through places between, not a jump)'), mid >= 3, `${mid} frames between`);
    const names = await anims(page);
    check(T('paid: the brush bobs while the search is live (a-bob on the drawing, not on the anchor that carries `left`)'),
      names.includes('a-bob') && await page.evaluate(() => getComputedStyle(document.querySelector('.activity-track > .rider svg')).animationName === 'a-bob'
        && getComputedStyle(document.querySelector('.activity-track > .rider')).animationName === 'none'));

    // the ticker
    const p1 = await progress(page);
    const t1 = firstOpen(p1);
    const want1 = `Now: ${BOARDS[t1.site] || t1.site} · ${where(t1)}`;
    check(T('paid: the ticker names the board and the city of the tile that is running'), (await text(page, '.ticker')) === want1 && !!(await page.locator('.ticker').isVisible()), `${await text(page, '.ticker')} / ${want1}`);
    check(T('paid: the ticker is not a live region'), await page.evaluate(() => { const t = document.querySelector('.ticker'); return !t.closest('[aria-live]') && !t.hasAttribute('role') && !t.querySelector('[aria-live]'); }));
    const t0 = firstOpen(p0);
    check(T('paid: it changed when the next tile ran'), tickBefore === `Now: ${BOARDS[t0.site]} · ${where(t0)}` && tickBefore !== want1, `${tickBefore} -> ${want1}`);
    await app.api('/__ledger/60');                                              // the first LinkedIn tile: the board changes too
    await waitFor(page, () => /LinkedIn/.test(document.querySelector('.ticker').textContent), null, 15000);
    const p2 = await progress(page); const t2 = firstOpen(p2);
    check(T('paid: when the board changes the ticker follows (Indeed to LinkedIn)'), (await text(page, '.ticker')) === `Now: LinkedIn · ${where(t2)}` && t2.site === 'linkedin', await text(page, '.ticker'));
    await shot(page, `${scheme}-1-paid-running`);

    // the arrivals: new listings after the page did
    const live = await page.evaluate(() => ({ fresh: document.querySelectorAll('.feed li.fresh').length, n: document.querySelectorAll('.feed li').length }));
    check(T('paid: the feed has what was fetched, and a poll that changes nothing adds no marker'), live.n === 5, JSON.stringify(live));
    check(T('paid: a listing that arrived after the page did dropped in (a-drop on the card, D7B\'s write-in on its parts)'), names.concat(await anims(page)).includes('a-drop') && (await anims(page)).includes('write-in'), JSON.stringify([...new Set(await anims(page))]));
    check(T('paid: its marker is gone 400 ms later'), await page.evaluate(() => document.querySelectorAll('.feed li.fresh').length) === 0);

    // the interaction. Rows by title: a listing that arrives goes on top, so positions move.
    const lis = page.locator('.feed li');
    const row = (title) => lis.filter({ hasText: title });
    const btn = (title) => row(title).locator('button.lm-b');
    const chips = (title) => row(title).locator('.lm-why .tag').allTextContents();
    const REACT = 'React Native Developer', MOBILE = 'Mobile Engineer', PLAIN = 'Senior Backend Engineer', FULL = 'Full Stack Developer', PLATFORM = 'Platform Engineer';
    check(T('paid: a listing with skills is a button; one without is not (it is today\'s plain row)'),
      (await btn(REACT).count()) === 1 && (await btn(MOBILE).count()) === 1 && (await btn(FULL).count()) === 1 && (await btn(PLATFORM).count()) === 1
      && (await btn(PLAIN).count()) === 0 && (await row(PLAIN).locator('b').textContent()).trim() === PLAIN && (await row(PLAIN).locator('.feed-score').textContent()).trim() === '31');
    check(T('paid: every one starts shut'), (await btn(REACT).getAttribute('aria-expanded')) === 'false' && !(await row(REACT).locator('.lm-why').isVisible()));
    await shot(page, `${scheme}-2-feed-shut`);
    await btn(REACT).click(); await sleep(150);
    check(T('paid: a click opens it, aria-expanded follows, the chips are the row\'s skills'),
      (await btn(REACT).getAttribute('aria-expanded')) === 'true' && (await row(REACT).locator('.lm-why').isVisible()) && JSON.stringify(await chips(REACT)) === JSON.stringify(['react native', 'typescript', 'redux'])
      && (await text(page, '.lm-why-t')) === 'Your skills this listing mentions');
    await shot(page, `${scheme}-3-feed-open`);
    await btn(MOBILE).click(); await sleep(150);
    check(T('paid: opening another shuts the first (one at a time); a long list shows six, trimmed, no blanks'),
      (await btn(REACT).getAttribute('aria-expanded')) === 'false' && !(await row(REACT).locator('.lm-why').isVisible()) && (await btn(MOBILE).getAttribute('aria-expanded')) === 'true'
      && JSON.stringify(await chips(MOBILE)) === JSON.stringify(['react', 'node.js', 'typescript', 'a', 'b', 'c']));
    await btn(MOBILE).click(); await sleep(150);
    check(T('paid: the same button shuts it'), (await btn(MOBILE).getAttribute('aria-expanded')) === 'false');
    await btn(FULL).focus(); await page.keyboard.press('Enter'); await sleep(150);
    const enter = (await btn(FULL).getAttribute('aria-expanded')) === 'true' && JSON.stringify(await chips(FULL)) === JSON.stringify(['python', 'django']);
    await page.keyboard.press('Space'); await sleep(150);
    const space = (await btn(FULL).getAttribute('aria-expanded')) === 'false';
    await page.keyboard.press('Space'); await sleep(150);
    check(T('paid: Enter and Space open and shut it from the keyboard'), enter && space && (await btn(FULL).getAttribute('aria-expanded')) === 'true');
    check(T('paid: a plain row stays plain after the others open (no panel, no button)'), (await row(PLAIN).locator('.lm-why').count()) === 0 && (await row(PLAIN).locator('button').count()) === 0);
    check(T('paid: a poll while one is open does not close it (the open one lives in the feed\'s own scope)'), await (async () => { await sleep(4600); return (await btn(FULL).getAttribute('aria-expanded')) === 'true'; })());

    // the tip
    check(T('paid: one tip, above the feed, with the words'), (await page.locator('.tip').count()) === 1 && (await text(page, '.tip .tip-say')) === 'Tap a match to see which of your skills it mentions.'
      && await page.evaluate(() => { const t = document.querySelector('.tip'), f = document.querySelector('.feed'); return !!(t.compareDocumentPosition(f) & Node.DOCUMENT_POSITION_FOLLOWING) && t.getClientRects().length > 0; }));
    await page.locator('.tip .tip-x').click(); await sleep(150);
    check(T('paid: the tip dismisses, and stays dismissed for the tab'), (await page.locator('.tip').isHidden()) && (await page.evaluate(() => sessionStorage.getItem('sweep-tips'))) === '["progress-tap"]');

    // the grid behind a peek: A11 polish, open by default (server-rendered `open`), and it still closes
    const peek = page.locator('details.searches');
    check(T('paid: A11/8 the Searches peek is open by default: a sticker with the grid and its legend, and the aside counts'),
      (await peek.evaluate((d) => d.open && getComputedStyle(d).borderTopStyle === 'solid')) && (await text(page, 'details.searches > summary .peek-aside')) === `${p2.done} of ${p2.planned} done`
      && (await page.locator('details.searches .cell').first().isVisible()) && (await page.locator('details.searches > summary > .meta').isVisible()));
    check(T('paid: A11/8 it is the server that opened it (the attribute is in the HTML, before any script)'), (await (await fetch(app.url + '/running', { headers: { cookie: 'session=' + (await ctx.cookies()).find((c) => c.name === 'session').value } })).text()).includes('<details class="pane searches" open>'));
    // a tile's sticker tooltip: its full search, from data-label, beside the title
    const tile = page.locator('details.searches .cell').nth(7);
    const lab = await tile.evaluate((e) => ({ title: e.getAttribute('title'), data: e.getAttribute('data-label') }));
    check(T('paid: A11/8 each tile carries its full search as data-label and keeps its title'), !!lab.title && lab.title === lab.data && / @ /.test(lab.data), JSON.stringify(lab));
    check(T('paid: A11/8 no tooltip until a tile is hovered'), (await tile.evaluate((e) => getComputedStyle(e, '::after').content)) === 'none');
    await tile.hover(); await sleep(200);
    const tip = await tile.evaluate((e) => { const s = getComputedStyle(e, '::after'), r = e.getBoundingClientRect(); return { content: s.content, bg: s.backgroundColor, border: s.borderTopWidth, shadow: s.boxShadow !== 'none', pos: s.position, w: parseFloat(s.width), events: s.pointerEvents, top: s.bottom, cellTop: r.top }; });
    check(T('paid: A11/8 hovering a tile shows a sticker tooltip with its full search (keywords @ location)'), tip.content === `"${lab.data}"` && tip.border === '2px' && tip.shadow && tip.pos === 'absolute' && tip.events === 'none' && tip.w > 60, JSON.stringify(tip));
    await pshot(page, `${scheme}-8-grid-tooltip`, { clip: { x: 0, y: Math.max(0, (await tile.boundingBox()).y - 260), width: 1000, height: 420 } });
    const onScreen = await tile.evaluate((e) => { const a = getComputedStyle(e, '::after'); return document.documentElement.scrollWidth <= innerWidth; });
    check(T('paid: A11/8 the tooltip does not widen the page'), onScreen);
    await page.mouse.move(5, 5); await sleep(100);
    check(T('paid: A11/8 and it is gone when the pointer leaves'), (await tile.evaluate((e) => getComputedStyle(e, '::after').content)) === 'none');
    await pshot(page, `${scheme}-8-grid-open-desktop`);
    // it still closes (and opens again), the legend only while it is open
    await peek.locator('summary').click(); await sleep(450);
    check(T('paid: it still closes: shut, dashed, the tiles and the legend out of sight'),
      !(await peek.evaluate((d) => d.open)) && (await peek.evaluate((d) => getComputedStyle(d).borderTopStyle)) === 'dashed' && !(await page.locator('details.searches .cell').first().isVisible())
      && !(await page.locator('details.searches > summary > .meta').isVisible()));
    await peek.locator('summary').click(); await sleep(450);
    const cells = await page.evaluate(() => ({ n: document.querySelectorAll('.cell').length, done: document.querySelectorAll('.cell.done').length, running: document.querySelectorAll('.cell.running').length,
      bg: getComputedStyle(document.querySelector('.cell.done')).backgroundColor, ring: getComputedStyle(document.querySelector('.cell.running')).borderTopWidth }));
    check(T('paid: opened it is a sticker with the grid and its legend; done tiles are lavender, one is a ring'),
      (await peek.evaluate((d) => d.open && getComputedStyle(d).borderTopStyle === 'solid')) && cells.n === 120 && cells.done === p2.done && cells.running === 1 && cells.ring === '2px'
      && (await page.locator('details.searches > summary > .meta').isVisible()), JSON.stringify(cells));
    await shot(page, `${scheme}-4-searches-open`);
    await app.api('/__ledger/70');
    await waitFor(page, () => document.querySelectorAll('.cell.done').length >= 70, null, 15000);
    await sleep(450);                                       // the last batch's pops have ended (260ms) and taken their class off
    const popped = await page.evaluate(() => ({ done: document.querySelectorAll('.cell.done').length, pop: document.querySelectorAll('.cell.pop').length, popNotDone: document.querySelectorAll('.cell.pop:not(.done)').length,
      names: window.__m.anim.filter((a) => a[0] === 'a-tile-pop').length, colour: window.__m.trans.filter((t) => t[0] === 'background-color' && /cell/.test(t[1])).length }));
    check(T('paid: A11/8 every tile that finished in view popped once (the class is gone after; each one also changed colour; one that finished while the panel was shut did neither), and none that was done at load did'), popped.names >= 30 && popped.names <= popped.done - p0.done && popped.names === popped.colour && popped.pop === 0, JSON.stringify({ ...popped, p0done: p0.done }));
    check(T('paid: A11/8 the colour change is still D7B\'s transition (background-color on the cells), the pop is only a transform'), popped.colour >= popped.names && await page.evaluate(() => getComputedStyle(document.querySelector('.cell.done')).transitionProperty.includes('background-color')), JSON.stringify(popped));
    check(T('paid: the aside counts (a poll later)'), (await text(page, 'details.searches > summary .peek-aside')) === '70 of 120 done', await text(page, 'details.searches > summary .peek-aside'));
    check(T('paid: the Stop form is a quiet link with its own words, and is still the form\'s submit'),
      await page.evaluate(() => { const b = document.querySelector('form[action$="/stop"] button'), cs = getComputedStyle(b);
        return b.type === 'submit' && b.textContent.trim() === 'Stop the sweep' && cs.borderTopWidth === '0px' && cs.textDecorationLine === 'underline' && cs.boxShadow === 'none' && b.getBoundingClientRect().height >= 44; }));
    check(T('paid: no overflow at 1440'), (await overflow(page)) <= 0);
    await ctx.close();
  }

  // ================= Paid, running, reduced motion =====================================================================
  {
    const { ctx, page } = await open('p_paid_one_some', { vp: 'desktop', reduced: true });
    await go(page);
    await page.evaluate(() => { window.__m.anim.length = 0; window.__m.trans.length = 0; });
    await app.api('/__ledger/20'); await app.api('/__rows/5');
    await waitFor(page, () => document.querySelectorAll('.feed li').length >= 5, null, 15000);
    await sleep(700);
    const names = await anims(page);
    const s = await page.evaluate(() => { const fill = document.querySelector('.activity-fill').getBoundingClientRect(), r = document.querySelector('.activity-track > .rider').getBoundingClientRect();
      return { gap: Math.abs(fill.right - r.left), svg: getComputedStyle(document.querySelector('.activity-track > .rider svg')).animationName, riderT: getComputedStyle(document.querySelector('.activity-track > .rider')).transitionDuration,
        fresh: document.querySelectorAll('.feed li.fresh').length, liAnim: getComputedStyle(document.querySelector('.feed li')).animationName, liTrans: getComputedStyle(document.querySelector('.feed li')).transitionDuration }; });
    check(T('reduced: the brush is a static marker at the end of the fill (no bob, no transition)'), s.gap <= 2 && s.svg === 'none' && s.riderT === '0s', JSON.stringify(s));
    check(T('reduced: a listing arrives and simply appears (no drop-in, no write-in)'), !names.includes('a-drop') && !names.includes('write-in') && s.liAnim === 'none' && s.liTrans === '0s', JSON.stringify([...new Set(names)]));
    const rp = await page.evaluate(() => ({ done: document.querySelectorAll('.cell.done').length, anim: getComputedStyle(document.querySelector('.cell.done')).animationName, open: document.querySelector('details.searches').open }));
    check(T('reduced: A11/8 tiles that finish do not pop (no animation on them), and the peek is still open by default'), rp.done >= 10 && rp.anim === 'none' && !names.includes('a-tile-pop') && rp.open, JSON.stringify({ rp, names: [...new Set(names)] }));
    await page.locator('details.searches > summary').click(); await sleep(60);
    check(T('reduced: A11/1 the Searches peek closes natively, at once, no clip'), await page.evaluate(() => { const d = document.querySelector('details.searches'); return !d.open && d.style.overflow === '' && d.getAnimations({ subtree: true }).length === 0; }));
    await page.locator('.feed li button.lm-b').first().click(); await sleep(100);
    check(T('reduced: a listing still opens, without the pop'), (await page.locator('.feed li .lm-why').first().isVisible()) && (await page.evaluate(() => getComputedStyle(document.querySelector('.lm-why')).animationName)) === 'none');
    await ctx.close();
  }

  // ================= An item made before the deploy ======================================================================
  {
    // the same page and polls with `skills` taken out of every item, as an item the page was handed before this deploy would be: plain
    // rows, no button, and nothing thrown (a feed that throws shows no listing at all)
    const { ctx, page } = await open('p_paid_one_some', { vp: 'desktop' });
    const strip = async (route) => { const r = await route.fetch(); await route.fulfill({ response: r, body: (await r.text()).replace(/"skills":\s*\[[^\]]*\],?\s*/g, '') }); };
    await page.route('**/running', strip); await page.route('**/progress', strip);
    await go(page);
    await app.api('/__rows/5');
    await waitFor(page, () => document.querySelectorAll('.feed li').length >= 5, null, 15000);
    await sleep(500);
    const st = await page.evaluate(() => ({ n: document.querySelectorAll('.feed li').length, buttons: document.querySelectorAll('.feed li button').length, titles: [...document.querySelectorAll('.feed li b')].map((b) => b.textContent.trim()),
      scores: document.querySelectorAll('.feed li .feed-score').length, tip: !!document.querySelector('.tip') && document.querySelector('.tip').getClientRects().length > 0, errors: window.__m.errors }));
    check(T('stale items: every one is a plain row (title, company, score), none is a button, the tip is not offered, nothing is thrown'),
      st.n === 5 && st.buttons === 0 && st.titles.length === 5 && st.scores === 5 && !st.tip && st.errors.length === 0, JSON.stringify(st));
    await ctx.close();
  }

  // ================= Every ending ======================================================================================
  for (const [scenario, h1, bannerB, phrase] of ENDINGS.filter((e) => e[0] !== 'p_paid_one_done')) {
    // a page opened after the fact
    const { ctx, page } = await open(scenario, { vp: 'desktop' });
    await go(page, '/running', 900);
    const shown = await page.evaluate(() => [...document.querySelectorAll('.run-a .banner')].filter((b) => getComputedStyle(b).display !== 'none').map((b) => ({ b: b.querySelector('b').textContent.replace(/\s+/g, ' ').trim(), all: b.textContent.replace(/\s+/g, ' ') })));
    const klass = await page.evaluate(() => document.querySelector('.activity').className);
    check(T(`ending ${scenario.slice(11)}: h1 "${h1}", one banner "${bannerB}" with its sentence`),
      (await text(page, 'main h1')) === h1 && shown.length === 1 && shown[0].b === bannerB && shown[0].all.includes(phrase), JSON.stringify(shown).slice(0, 220));
    const bs = await page.evaluate(() => { const b = [...document.querySelectorAll('.run-a .banner')].find((x) => getComputedStyle(x).display !== 'none'); const cs = getComputedStyle(b);
      return { border: cs.borderTopWidth, radius: cs.borderTopLeftRadius, shadow: cs.boxShadow !== 'none' }; });
    check(T(`ending ${scenario.slice(11)}: a sticker banner (2px edge, round, a hard shadow) and the track says stopped (off)`), bs.border === '2px' && parseFloat(bs.radius) >= 20 && bs.shadow && /off|part/.test(klass) || /off/.test(klass), JSON.stringify({ bs, klass }));
    check(T(`ending ${scenario.slice(11)}: no overflow at 1440`), (await overflow(page)) <= 0);
    if (scenario === 'p_paid_one_failed' || scenario === 'p_paid_one_incomplete') await shot(page, `${scheme}-5-${scenario.slice(11)}`);
    await ctx.close();
  }
  {
    // a visitor who waited: the ending fades in, then the page goes to the results, as before
    const { ctx, page } = await open('p_paid_one_some', { vp: 'desktop' });
    await go(page);
    await app.api('/__step/done');
    await page.waitForURL(/\/results/, { timeout: 16000 });
    check(T('ending finished: a visitor who waited is taken to the results'), /\/results/.test(page.url()));
    await ctx.close();
    const b = await open('p_paid_one_done', { vp: 'desktop' });
    await go(b.page, '/running', 900);
    const fin = await b.page.evaluate(() => ({ url: location.pathname, h1: document.querySelector('h1').textContent.trim(),
      banner: [...document.querySelectorAll('.run-a .banner')].filter((x) => getComputedStyle(x).display !== 'none').map((x) => x.querySelector('b').textContent.trim()),
      klass: document.querySelector('.activity').className, fillBg: getComputedStyle(document.querySelector('.activity-fill')).backgroundImage }));
    check(T('ending finished: opened after the fact it stays (nobody was waiting): "Your jobs are ready", "Every search ran", a citrus track'),
      fin.url === '/running' && fin.h1 === 'Your jobs are ready' && fin.banner.join() === 'Every search ran' && /done/.test(fin.klass) && /rgb\(228, 242, 92\)/.test(fin.fillBg), JSON.stringify(fin).slice(0, 260));
    await shot(b.page, `${scheme}-5-finished`);
    await b.ctx.close();
  }

  // ================= The free path =====================================================================================
  {
    const { ctx, page } = await open('p_free_one_working', { vp: 'desktop' });
    await go(page);
    check(T('free: eyebrow "Step 3 · Quick Sweep" over the same headline'), (await text(page, 'main .eyebrow')) === 'Step 3 · Quick Sweep' && (await text(page, 'main h1')) === 'Sweep is searching for you');
    // A11/9: the brush sweeps the whole track and paints behind it, the paint fades at the right end, and it starts again
    const sweepRun = (ms) => page.evaluate((ms) => new Promise((res) => {
      // pre-merge polish: the span is the track's full width; the paint is its ::before, shown by a clip-path (its width is what is left of the clip), and the rider's right edge is the brush
      const paintOf = (span) => { const W = span.getBoundingClientRect().width, v = /inset\(\s*\S+\s+(\S+)/.exec(getComputedStyle(span, '::before').clipPath)[1]; return W - (v.endsWith('%') ? parseFloat(v) / 100 * W : parseFloat(v)); };
      const bar = document.querySelector('.working-bar'), span = bar.querySelector('span'), rider = span.querySelector('.rider'), a = [];
      const t0 = performance.now();
      (function tick() { const b = bar.getBoundingClientRect(), s = span.getBoundingClientRect(), w = paintOf(span); a.push({ t: performance.now() - t0, w, left: s.left - b.left, right: s.left - b.left + w, brush: rider.getBoundingClientRect().right - b.left, op: +getComputedStyle(span).opacity, track: bar.clientWidth });
        if (performance.now() - t0 < ms) requestAnimationFrame(tick); else res(a); })();
    }), ms);
    const fr = await sweepRun(6200);
    const W = fr[0].track, ws = fr.map((f) => f.w);
    const resets = fr.filter((f, i) => i && f.w < fr[i - 1].w - W * 0.5).length;
    check(T('free: A11/9 the paint starts at the left edge and fills the whole track (the brush crosses it end to end)'), Math.min(...ws) < 6 && Math.max(...ws) >= W - 3 && fr.every((f) => Math.abs(f.left) <= 2), `min ${Math.min(...ws).toFixed(1)} max ${Math.max(...ws).toFixed(1)} of ${W}, left drift ${Math.max(...fr.map((f) => Math.abs(f.left))).toFixed(1)}`);
    check(T('free: A11/9 the brush is on the end of the paint at every frame (within 2px) and moves left to right'), fr.every((f) => Math.abs(f.right - f.brush) <= 2) && fr.filter((f, i) => i && f.op === 1 && fr[i - 1].op === 1 && f.w >= fr[i - 1].w - 0.5).length > fr.length * 0.6, `worst ${Math.max(...fr.map((f) => Math.abs(f.right - f.brush))).toFixed(2)}px`);
    const t = (pred) => { const f = fr.find(pred); return f ? f.t : null; };
    const first = fr.findIndex((f, i) => i && f.w > W * 0.02 && fr[i - 1].w <= W * 0.02);
    const from = fr[first].t, to = fr.slice(first).find((f) => f.w >= W * 0.98).t;
    check(T('free: A11/9 the crossing takes about 2.4s'), to - from > 1900 && to - from < 2800, `${(to - from).toFixed(0)}ms (2% to 98%)`);
    const midW = fr.filter((f) => f.t > from + (to - from) * 0.45 && f.t < from + (to - from) * 0.55).map((f) => f.w / W);
    check(T('free: A11/9 ease in and out: half way across at half the time, slower at the ends'), Math.abs(midW.reduce((x, y) => x + y, 0) / midW.length - 0.5) < 0.12 && (fr.find((f) => f.t >= from + 300).w / W) < 0.2, JSON.stringify(midW.slice(0, 2)));
    const full = fr.slice(first).findIndex((f) => f.w >= W * 0.98), fade = fr.slice(first + full).find((f) => f.op < 0.05);
    check(T('free: A11/9 at the right end the paint fades out over about half a second'), !!fade && fade.t - fr[first + full].t > 250 && fade.t - fr[first + full].t < 800, fade ? `${(fade.t - fr[first + full].t).toFixed(0)}ms from full to gone` : 'never faded');
    check(T('free: A11/9 then it starts again from the left (looped)'), resets >= 1 && fr.some((f, i) => i && f.op > 0.9 && f.w < W * 0.05 && fr[i - 1].op < 0.2), `${resets} restart(s) in 6.2s`);
    await pshot(page, `${scheme}-9-free-bar-desktop-a`, { clip: { x: 0, y: 150, width: 1440, height: 420 } });
    await sleep(900);
    await pshot(page, `${scheme}-9-free-bar-desktop-b`, { clip: { x: 0, y: 150, width: 1440, height: 420 } });
    check(T('free: the bar is decoration with the brush aria-hidden, and the rider bobs'), await page.evaluate(() => { const r = document.querySelector('.working-bar .rider'); return r.getAttribute('aria-hidden') === 'true' && getComputedStyle(r.querySelector('svg')).animationName === 'a-bob'; }));
    const marks = await page.evaluate(() => [...document.querySelectorAll('ol.stages li')].map((li) => ({ cls: li.className, mark: getComputedStyle(li, '::before').content.replace(/"/g, ''), anim: getComputedStyle(li, '::before').animationName })));
    check(T('free: the passes carry a marker each (a tick behind, a counted number for the one under way and each to come), and none of them pulses'),
      // a number is a CSS counter (the computed `content` is the counter() call, not its text; the screenshots show the digits)
      JSON.stringify(marks.map((m) => m.mark)) === JSON.stringify(['✓', 'counter(pass)', 'counter(pass)', 'counter(pass)']) && marks.map((m) => m.cls.split(' ')[0]).join() === 'done,now,next,next'
      && marks.every((m) => m.anim === 'none'), JSON.stringify(marks));
    check(T('free: the explanation is a peek (dashed shut), and opens'), await (async () => {
      const d = page.locator('details.about'); const shut = await d.evaluate((e) => !e.open && getComputedStyle(e).borderTopStyle === 'dashed');
      await d.locator('summary').click(); await sleep(300);
      return shut && (await d.evaluate((e) => e.open && getComputedStyle(e).borderTopStyle === 'solid')) && (await d.locator('.about-body .panel').count()) === 3 && (await d.locator('.about-body .panel').first().isVisible());
    })());
    check(T('free: the Stop form is the quiet link here too'), await page.evaluate(() => { const b = document.querySelector('form[action$="/stop"] button'); return getComputedStyle(b).textDecorationLine === 'underline' && getComputedStyle(b).borderTopWidth === '0px'; }));
    await shot(page, `${scheme}-6-free-running`);
    check(T('free: no overflow at 1440'), (await overflow(page)) <= 0);
    await ctx.close();
    const r = await open('p_free_one_working', { vp: 'desktop', reduced: true });
    await go(r.page);
    const st2 = await r.page.evaluate(() => new Promise((res) => { const paintOf = (span) => { const W = span.getBoundingClientRect().width, v = /inset\(\s*\S+\s+(\S+)/.exec(getComputedStyle(span, '::before').clipPath)[1]; return W - (v.endsWith('%') ? parseFloat(v) / 100 * W : parseFloat(v)); }; const bar = document.querySelector('.working-bar'), span = bar.querySelector('span'), rider = span.querySelector('.rider'); const f = () => ({ w: paintOf(span), brush: rider.getBoundingClientRect().right - bar.getBoundingClientRect().left, right: span.getBoundingClientRect().left - bar.getBoundingClientRect().left + paintOf(span) });
      const a = f(); setTimeout(() => res({ a, b: f(), track: bar.clientWidth, anim: getComputedStyle(span).animationName, paintAnim: getComputedStyle(span, '::before').animationName, riderAnim: getComputedStyle(rider).animationName, op: getComputedStyle(span).opacity, svg: getComputedStyle(rider.querySelector('svg')).animationName }), 1500); }));
    check(T('free, reduced: A11/9 static half-painted stripes with the brush resting at their end, nothing moves'), st2.anim === 'none' && st2.paintAnim === 'none' && st2.riderAnim === 'none' && Math.abs(st2.a.w / st2.track - 0.5) < 0.03 && st2.a.w === st2.b.w && st2.a.brush === st2.b.brush && Math.abs(st2.a.right - st2.a.brush) <= 2 && st2.op === '1' && st2.svg === 'none', JSON.stringify(st2));
    await pshot(r.page, `${scheme}-9-free-bar-reduced`, { clip: { x: 0, y: 150, width: 1440, height: 420 } });
    await r.ctx.close();
    // the paid page's free pass (every paid search done, the free boards still going) has the same bar
    const f = await open('p_paid_one_some', { vp: 'desktop' });
    await go(f.page);
    await app.api('/__ledger/120');
    await waitFor(f.page, () => { const b = document.querySelector('.activity .working-bar'); return b && b.getClientRects().length > 0; }, null, 15000);
    const fp = await f.page.evaluate(() => new Promise((res) => { const paintOf = (span) => { const W = span.getBoundingClientRect().width, v = /inset\(\s*\S+\s+(\S+)/.exec(getComputedStyle(span, '::before').clipPath)[1]; return W - (v.endsWith('%') ? parseFloat(v) / 100 * W : parseFloat(v)); }; const bar = document.querySelector('.activity .working-bar'), span = bar.querySelector('span'), a = []; const t0 = performance.now();
      (function tick() { a.push([paintOf(span), span.querySelector('.rider').getBoundingClientRect().right - bar.getBoundingClientRect().left, span.getBoundingClientRect().left - bar.getBoundingClientRect().left + paintOf(span)]); if (performance.now() - t0 < 3200) requestAnimationFrame(tick); else res({ a, track: bar.clientWidth }); })(); }));
    check(T('paid page, free pass: A11/9 the same sweep (the paint crosses the track, the brush on its end)'), Math.min(...fp.a.map((x) => x[0])) < 8 && Math.max(...fp.a.map((x) => x[0])) >= fp.track - 3 && fp.a.every((x) => Math.abs(x[1] - x[2]) <= 2), `${Math.min(...fp.a.map((x) => x[0])).toFixed(0)}..${Math.max(...fp.a.map((x) => x[0])).toFixed(0)} of ${fp.track}`);
    await pshot(f.page, `${scheme}-9-free-pass-on-paid-page`, { clip: { x: 0, y: 150, width: 1440, height: 420 } });
    await f.ctx.close();
  }

  // ================= Phones and widths ==================================================================================
  for (const [scenario, label] of [['p_paid_one_some', 'paid running'], ['p_paid_one_done', 'paid finished'], ['p_paid_one_failed', 'paid halted'], ['p_free_one_working', 'free running']]) {
    for (const vp of ['mobile']) {
      const { ctx, page } = await open(scenario, { vp });
      await go(page);
      if (scenario === 'p_paid_one_some') {
        await page.locator('.feed li button.lm-b').first().click(); await sleep(250);
        await page.locator('details.searches summary').click(); await sleep(300);
      }
      const d = await page.evaluate((W) => { const h = document.querySelector('main h1').getBoundingClientRect(), f = document.querySelector('.headline-figure.found');
        return { overflow: document.documentElement.scrollWidth - W, innerWidth, foundUnder: f && getComputedStyle(f).display !== 'none' ? f.getBoundingClientRect().top >= h.bottom - 1 : null,
          sticky: [...document.querySelectorAll('*')].filter((e) => getComputedStyle(e).position === 'sticky' || getComputedStyle(e).position === 'fixed').map((e) => e.tagName.toLowerCase() + '.' + e.className).filter((s) => !/header|brand|theme|feedback|dialog/.test(s)) }; }, page.viewportSize().width);
      // and on every frame for four seconds: the free pass's brush goes to and fro along the bar, so it is at both ends within one pass
      const worstFrame = await page.evaluate((W) => new Promise((res) => { let m = 0; const t0 = performance.now();
        (function tick() { m = Math.max(m, document.documentElement.scrollWidth - W); if (performance.now() - t0 < 4200) requestAnimationFrame(tick); else res(m); })(); }), page.viewportSize().width);
      check(T(`phone, ${label}: no overflow at 390 (at rest and on every frame of four seconds), the figure (if any) under the headline, nothing pinned`),
        d.overflow <= 0 && worstFrame <= 0 && d.foundUnder !== false && d.sticky.length === 0, JSON.stringify({ ...d, worstFrame }));
      if (scenario === 'p_paid_one_some') await shot(page, `${scheme}-7-paid-phone`);
      if (scenario === 'p_free_one_working') await shot(page, `${scheme}-7-free-phone`);
      await ctx.close();
    }
  }
  for (const w of [768, 1024]) {
    const { ctx, page } = await open('p_paid_one_some', { vp: 'desktop' });
    await page.setViewportSize({ width: w, height: 900 });
    await go(page, '/running', 500);
    check(T(`no overflow at ${w}`), (await overflow(page)) <= 0);
    await ctx.close();
  }
}

console.log(out.join('\n'));
const fails = out.filter((l) => l.startsWith('FAIL')).length;
console.log(`\n${out.length - fails} of ${out.length} checks pass`);
app.stop(); await browser.close();
process.exit(ok ? 0 : 1);
