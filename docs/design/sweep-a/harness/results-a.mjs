// A9: Results (public) in a real browser, over the production app on loopback (the D7B/D7C harness scenarios: s1, s1_19, m_all,
// m_19, m_240, m_long, m_failed ...).
//   node docs/design/sweep-a/harness/results-a.mjs                       checks only
//   RESULTS_A_SHOTS=1 node docs/design/sweep-a/harness/results-a.mjs     also writes screenshots to output/design-A9/results-a/
// Cards at 1440 and 390 in both themes (a table that is one sticker card per job, no band on a score); "Why it matched" opens by click
// and by Enter and Space, holds every term, and a click in it does not open the listing (window.open is stubbed by the harness's trace)
// while a click on the card's free area still does; Apply still opens its own tab; "Top of the pile" on the first card of the first
// section only, and gone once another sort is chosen; the tabs, Filter and sort and Export still work; the arrival motion still runs
// (eight rows, three on a phone) and reduced motion has none; no horizontal overflow at 390/768/1024/1440, measured against the width
// the visitor was given; and the phone Apply target is at least what HEAD's was (HEAD served from a git export, D7B_REPO).
import fs from 'fs';
import path from 'path';
import { execFileSync } from 'child_process';
import os from 'os';
import { launch, serveApp, visitor, arrive, M, count, sleep, ROOT, OUT } from '../../motion-d7b/harness/lib.mjs';

const SHOTS = !!process.env.RESULTS_A_SHOTS;
const shotDir = path.join(ROOT, 'output', 'design-A9', 'results-a');
if (SHOTS) fs.mkdirSync(shotDir, { recursive: true });

const app = await serveApp({ port: 5497 });
process.on('exit', () => app.stop());       // a crash must not leave the server holding the port
const browser = await launch();
const out = []; let ok = true;
const check = (name, cond, info) => { out.push(`${cond ? 'ok  ' : 'FAIL'} ${name}${info === undefined ? '' : ' ' + info}`); ok = ok && !!cond; };
const polishDir = path.join(OUT, 'polish');
fs.mkdirSync(polishDir, { recursive: true });
const pshot = async (page, name) => { if (process.env.POLISH_SHOTS !== '0') await page.screenshot({ path: path.join(polishDir, name + '.png') }); };
const shot = async (page, name, full = false) => { if (SHOTS) await page.screenshot({ path: path.join(shotDir, name + '.png'), fullPage: full }); };
const open = (scenario, o = {}) => visitor(browser, app, scenario, { trace: true, ...o });
const go = async (page, p = '/results', wait = 500) => { await page.goto(app.url + p, { waitUntil: 'networkidle' }); await sleep(wait); };
// Against the viewport the visitor was given, not `innerWidth` (A8: an emulated phone widens its layout viewport to fit overflowing content).
const overflow = (page) => page.evaluate((w) => document.documentElement.scrollWidth - w, page.viewportSize().width);
const text = (loc) => loc.first().textContent().then((t) => t.replace(/\s+/g, ' ').trim());
const opened = (page) => page.evaluate(() => window.__m.opened.slice());
const A = 'a'.repeat(16);

// ---- HEAD's phone Apply target, measured once ------------------------------------------------------------------
let head = null;
{
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'a9-head-'));
  const tar = execFileSync('git', ['archive', 'HEAD'], { cwd: ROOT, maxBuffer: 1 << 28 });
  execFileSync('tar', ['-x', '-C', dir], { input: tar });
  const old = await serveApp({ port: 5498, repo: dir });
  const { ctx, page } = await visitor(browser, old, 's1_19', { vp: 'mobile' });
  await page.goto(old.url + '/results', { waitUntil: 'networkidle' }); await sleep(400);
  head = await page.evaluate(() => { const r = document.querySelector('a.apply').getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height) }; });
  await ctx.close(); old.stop(); fs.rmSync(dir, { recursive: true, force: true });
}
console.log('HEAD phone Apply target:', JSON.stringify(head));

for (const scheme of ['light', 'dark']) {
  process.env.D7_SCHEME = scheme;
  const T = (s) => `${scheme}: ${s}`;

  // ================= Cards, desktop =====================================================================================
  for (const [vp, W] of [['desktop', 1440], ['mobile', 390]]) {
    const { ctx, page } = await open('m_all', { vp });
    await go(page);
    const d = await page.evaluate((W) => {
      const rows = [...document.querySelectorAll('.jobs tbody tr')];
      const cs = (e, p) => getComputedStyle(e)[p];
      const ink = (e) => [cs(e, 'backgroundColor'), cs(e, 'color'), cs(e, 'borderTopColor'), cs(e, 'fontSize')].join('|');
      const scores = rows.map((r) => r.querySelector('td.score'));
      const bands = [...document.querySelectorAll('main *')].filter((e) => typeof e.className === 'string' && /(^|\s)(hi|mid|lo|neg|band|good|bad)(\s|$)/.test(e.className)).length;
      const thead = document.querySelector('.jobs thead').getBoundingClientRect();
      const t = document.querySelector('table.jobs');
      return { n: rows.length, flex: rows.every((r) => cs(r, 'display') === 'flex'), tableBlock: cs(t, 'display') === 'block', ariaLabel: !!t.getAttribute('aria-label'),
        theadHidden: thead.width <= 1 && thead.height <= 1, theadCells: document.querySelectorAll('.jobs thead th[scope="col"]').length,
        ink: [...new Set(scores.map(ink))].length, scoreText: scores.map((s) => s.firstChild.textContent.trim()), bands,
        radius: parseFloat(cs(rows[0], 'borderTopLeftRadius')), border: cs(rows[0], 'borderTopWidth'),
        badge: scores.slice(0, 1).map((s) => { const r = s.getBoundingClientRect(), c = rows[0].getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height), left: Math.round(r.left - c.left), fs: parseFloat(cs(s, 'fontSize')) }; })[0],
        titleLeft: (() => { const b = rows[0].querySelector('.job-line b').getBoundingClientRect(), s = scores[0].getBoundingClientRect(); return { titleAfterBadge: b.left >= s.right - 1 || b.top >= s.bottom - 1 }; })(),
        overflow: document.documentElement.scrollWidth - W };
    }, page.viewportSize().width);
    check(T(`${W}: every job is a flex card (the table, body and rows are blocks; aria-label and the visually hidden head stay)`), d.n >= 10 && d.flex && d.tableBlock && d.ariaLabel && d.theadHidden && d.theadCells >= 6, JSON.stringify({ n: d.n, flex: d.flex, tableBlock: d.tableBlock, theadHidden: d.theadHidden, cells: d.theadCells }));
    check(T(`${W}: the score is a raw number in a badge that looks the same for every score (no band), 64px or more wide and 56 tall`),
      d.ink === 1 && d.bands === 0 && d.badge.w >= 64 && d.badge.h >= 56 && d.badge.fs >= 22 && d.scoreText.every((s) => /^-?\d+$/.test(s)), JSON.stringify({ inks: d.ink, bands: d.bands, badge: d.badge, scores: d.scoreText.slice(0, 8) }));
    check(T(`${W}: sticker cards (2px line, rounded)`), d.border === '2px' && d.radius >= 20 && d.titleLeft.titleAfterBadge, JSON.stringify({ border: d.border, radius: d.radius, ...d.titleLeft }));
    check(T(`${W}: no horizontal overflow, measured against the configured width`), (await overflow(page)) <= 0 && d.overflow <= 0, JSON.stringify({ overflow: await overflow(page) }));
    await shot(page, `${scheme}-1-cards-${vp}`);

    // the recommendation: visible, caution before suggestion, never inside the peek
    const rec = await page.evaluate(() => {
      const rows = [...document.querySelectorAll('.jobs tbody tr')].filter((r) => !r.closest('details.jobs-section'));      // the collapsed abroad section is a peek of its own
      const both = rows.filter((r) => r.querySelector('.caution') && r.querySelector('.suggest'));
      const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility === 'visible'; };
      return { withBoth: both.length, order: both.every((r) => r.querySelector('.caution').compareDocumentPosition(r.querySelector('.suggest')) & Node.DOCUMENT_POSITION_FOLLOWING
          && r.querySelector('.caution').getBoundingClientRect().top < r.querySelector('.suggest').getBoundingClientRect().top),
        visible: rows.every((r) => [...r.querySelectorAll('.caution, .suggest')].every(vis)), inPeek: rows.some((r) => r.querySelector('details.why .caution, details.why .suggest')) || !!document.querySelector('details.why .caution, details.why .suggest'),
        every: rows.every((r) => !!r.querySelector('.suggest')) };
    });
    check(T(`${W}: the recommendation shows on every card, the caution above the suggestion, and none of it is inside a peek`), rec.withBoth >= 1 && rec.order && rec.visible && !rec.inPeek && rec.every, JSON.stringify(rec));

    // facts: stated ones only; the Paid word is peach (the paid token) and only on a paid board
    const facts = await page.evaluate(() => {
      const probe = document.createElement('i'); probe.style.color = 'var(--paid)'; document.body.append(probe); const paid = getComputedStyle(probe).color; probe.remove();
      const rows = [...document.querySelectorAll('.jobs tbody tr')];
      const shown = (e) => e && getComputedStyle(e).display !== 'none';
      const words = rows.map((r) => r.querySelector('.paid-word'));
      return { paidColour: words.filter(Boolean).every((w) => getComputedStyle(w).color === paid), paidRows: words.filter(Boolean).length, freeRows: rows.filter((r) => r.querySelector('td.src.free')).length,
        freeHasWord: rows.some((r) => r.querySelector('td.src.free .paid-word')),
        absentNotDrawn: rows.every((r) => ['pay', 'exp'].every((k) => { const c = r.querySelector('td.' + k); return !c || !c.classList.contains('none') || !shown(c); })),
        statedDrawn: rows.some((r) => shown(r.querySelector('td.pay:not(.none)'))), via: rows.every((r) => /^via /.test(r.querySelector('td.src').textContent.trim())),
        otherPeach: [...document.querySelectorAll('.jobs tbody *')].filter((e) => !e.matches('.paid-word') && getComputedStyle(e).color === paid).length,
        posted: rows.filter((r) => r.querySelector('.posted')).length, srcFreeClass: rows.filter((r) => r.querySelector('td.src.free')).length };
    });
    check(T(`${W}: facts are chips, only the stated ones; "via X"; the Paid word is the money colour and is the only peach on the cards`),
      facts.paidColour && facts.paidRows >= 1 && facts.freeRows >= 1 && !facts.freeHasWord && facts.absentNotDrawn && facts.statedDrawn && facts.via && facts.otherPeach === 0 && facts.posted >= 1, JSON.stringify(facts));
    await ctx.close();
  }

  // ================= Why it matched =====================================================================================
  for (const vp of ['desktop', 'mobile']) {
    const { ctx, page } = await open('m_all', { vp });
    await go(page);
    const row = page.locator('.jobs tbody tr').first();
    const why = row.locator('details.why');
    const total = await why.locator('.tag').count();
    const href = await row.getAttribute('data-href');
    check(T(`${vp}: Why it matched is shut at first, a dashed pill, with its words`), (await why.evaluate((e) => e.open)) === false && (await text(why.locator('summary'))) === 'Why it matched'
      && (await why.evaluate((e) => getComputedStyle(e).borderTopStyle)) === 'dashed' && total === 7, `terms in the markup: ${total}`);
    // click opens
    await why.locator('summary').click(); await sleep(150);
    const shownTags = await why.evaluate((e) => [...e.querySelectorAll('.tag')].filter((t) => t.getBoundingClientRect().width > 0).map((t) => t.textContent.trim()));
    check(T(`${vp}: a click opens it, and every term is shown, uncapped (7 of 7, no "+N" chip)`), (await why.evaluate((e) => e.open)) === true && shownTags.length === 7 && !(await row.locator('.tag.more').count())
      && (await text(why.locator('.why-t'))) === 'Your skills this job mentions', JSON.stringify(shownTags));
    check(T(`${vp}: opening it did not open the listing`), (await opened(page)).length === 0, JSON.stringify(await opened(page)));
    // a click in its body does not open the listing
    await why.locator('.why-t').click(); await why.locator('.tag').nth(2).click(); await sleep(100);
    check(T(`${vp}: a click inside the open peek's body (its label, a term) does not open the listing`), (await opened(page)).length === 0 && (await why.evaluate((e) => e.open)) === true, JSON.stringify(await opened(page)));
    await shot(page, `${scheme}-2-why-open-${vp}`);
    // click closes, then keyboard: Enter and Space on the summary
    await why.locator('summary').click(); await sleep(100);
    const whyMid = await why.evaluate((e) => ({ open: e.open, anims: e.getAnimations({ subtree: true }).length, overflow: e.style.overflow }));
    check(T(`${vp}: A11/1 closing is animated: part way through, \`open\` is held and the height is animating`), whyMid.open && whyMid.anims > 0 && whyMid.overflow === 'hidden', JSON.stringify(whyMid));
    await sleep(300);
    check(T(`${vp}: a second click closes it`), (await why.evaluate((e) => e.open)) === false && (await opened(page)).length === 0);
    await why.locator('summary').focus(); await page.keyboard.press('Shift+Tab'); await page.keyboard.press('Tab');       // reached by keyboard, so :focus-visible applies
    check(T(`${vp}: the summary is natively focusable (no tabindex in main) with the shared focus ring`),
      (await page.evaluate(() => document.querySelectorAll('main [tabindex]').length)) === 0 && (await why.locator('summary').evaluate((e) => document.activeElement === e && getComputedStyle(e).outlineStyle === 'solid')));
    await page.keyboard.press('Enter'); await sleep(350);
    const afterEnter = await why.evaluate((e) => e.open);
    await page.keyboard.press('Enter'); await sleep(350);
    const afterEnter2 = await why.evaluate((e) => e.open);
    await page.keyboard.press('Space'); await sleep(350);
    const afterSpace = await why.evaluate((e) => e.open);
    await page.keyboard.press('Space'); await sleep(350);
    check(T(`${vp}: Enter opens it and closes it, Space opens it and closes it; none of it opens the listing`),
      afterEnter === true && afterEnter2 === false && afterSpace === true && (await why.evaluate((e) => e.open)) === false && (await opened(page)).length === 0, JSON.stringify({ afterEnter, afterEnter2, afterSpace }));
    // A11/1: the score explainer and the abroad section (when there is one) animate the same way, end open, and the page does not move sideways
    for (const [sel, name] of [['details.how-scoring', 'the score explainer'], ['details.jobs-section', 'the abroad section']]) {
      const d = page.locator(sel).first();
      if (!(await d.count())) continue;
      const h0 = await d.evaluate((e) => e.getBoundingClientRect().height);
      await d.locator('summary').first().click(); await sleep(100);
      const mid = await d.evaluate((e) => ({ open: e.open, h: e.getBoundingClientRect().height, anims: e.getAnimations({ subtree: true }).length }));
      await sleep(400);
      const end = await d.evaluate((e) => ({ open: e.open, h: e.getBoundingClientRect().height, anims: e.getAnimations({ subtree: true }).length, overflow: e.style.overflow }));
      check(T(`${vp}: A11/1 ${name} opens with a height animation and ends open, clean`), mid.open && mid.anims > 0 && mid.h > h0 + 1 && mid.h < end.h - 1 && end.open && end.anims === 0 && end.overflow === '' && end.h > h0 + 20, JSON.stringify({ h0, mid, end }));
      if (vp === 'desktop') await pshot(page, `${scheme}-1-peek-${sel.split('.')[1]}-open-${vp}`);
      await d.locator('summary').first().click(); await sleep(450);
    }
    // the card's free area still opens the listing
    await page.evaluate(() => scrollTo(0, 0)); await row.scrollIntoViewIfNeeded(); await sleep(100);
    const box = await row.boundingBox();
    await page.mouse.click(box.x + 8, box.y + box.height - 8); await sleep(150);
    const o1 = await opened(page);
    check(T(`${vp}: a click on the card's free area still opens the listing (${href})`), o1.length === 1 && o1[0] === href, JSON.stringify(o1));
    await row.locator('.co').click(); await sleep(100);
    check(T(`${vp}: so does a click on the company line`), (await opened(page)).length === 2);
    // Apply opens its own tab and is not counted twice
    const popup = ctx.waitForEvent('page', { timeout: 5000 }).catch(() => null);
    await row.locator('a.apply').click(); const p2 = await popup; if (p2) await p2.close().catch(() => {});
    check(T(`${vp}: Apply opens the listing in its own tab, once`), !!p2 && (await opened(page)).length === 2, `${p2 ? p2.url() : 'no tab'}`);
    // a card with no skills has no peek and an empty cell
    const none = await page.evaluate(() => { const c = [...document.querySelectorAll('td.skills')]; return { total: c.length, empty: c.filter((x) => !x.children.length).length, emptyHidden: c.filter((x) => !x.children.length).every((x) => getComputedStyle(x).display === 'none') }; });
    check(T(`${vp}: a card with no matched skills has an empty cell and no peek`), none.empty === 0 || none.emptyHidden, JSON.stringify(none));
    await ctx.close();
  }

  // ================= Top of the pile ====================================================================================
  {
    const { ctx, page } = await open('m_all', { vp: 'desktop' });
    await go(page);
    const t = await page.evaluate(() => {
      const st = [...document.querySelectorAll('.stamp')];
      const first = document.querySelector('#results-body > section.jobs-section:first-child .jobs tbody tr:first-child');
      return { n: st.length, text: st.map((s) => s.textContent.trim()), inFirst: st.every((s) => first.contains(s)), sections: [...document.querySelectorAll('#results-body > .jobs-section')].map((s) => s.tagName), firstH2: document.querySelector('#results-body h2').textContent.trim() };
    });
    check(T('Top of the pile: one stamp, on the first card of the first section (not the collapsed abroad one)'), t.n === 1 && t.text[0] === 'Top of the pile' && t.inFirst && t.sections[0] === 'SECTION', JSON.stringify(t));
    const place = await page.evaluate(() => { const s = document.querySelector('.stamp').getBoundingClientRect(), c = document.querySelector('.jobs tbody tr').getBoundingClientRect(), a = document.querySelector('a.apply').getBoundingClientRect();
      return { onTopEdge: s.top < c.top + 4 && s.bottom > c.top, clearOfApply: s.right <= a.left + 1 || s.bottom <= a.top + 1 }; });
    check(T('Top of the pile: sits on the card\'s top edge and clear of Apply'), place.onTopEdge && place.clearOfApply, JSON.stringify(place));
    await shot(page, `${scheme}-3-top-of-the-pile`);
    // choose another sort through the form
    await page.locator('button.tool-toggle', { hasText: 'Filter and sort' }).click(); await sleep(450);
    await page.locator('select[name=sort]').selectOption('recent');
    await page.locator('.tool-panel form button[type=submit]').click(); await page.waitForURL(/sort=recent/); await sleep(500);
    check(T('Top of the pile: gone after choosing another sort'), (await page.locator('.stamp').count()) === 0 && /Newest first/.test(await text(page.locator('.bar .count'))), `${await text(page.locator('.bar .count'))}`);
    // and back to best match: the stamp returns
    await page.goto(app.url + '/results?sort=score', { waitUntil: 'networkidle' });
    check(T('Top of the pile: back with Best match'), (await page.locator('.stamp').count()) === 1);
    // a track view: the first card of that view
    await go(page, `/results?track=${A}`);
    check(T('Top of the pile: also on the first card of a résumé\'s own view'), (await page.locator('.stamp').count()) === 1 && (await page.evaluate(() => document.querySelector('.stamp').closest('tr') === document.querySelector('.jobs tbody tr'))));
    await ctx.close();
  }

  // ================= Tabs, tools, sections, the explainer, the tip ===================================================
  {
    const { ctx, page } = await open('m_all', { vp: 'desktop' });
    await go(page);
    const tabs = await page.evaluate(() => [...document.querySelectorAll('nav.views a')].map((a) => ({ cur: a.getAttribute('aria-current'), weight: +getComputedStyle(a).fontWeight, bg: getComputedStyle(a).backgroundColor, h: Math.round(a.getBoundingClientRect().height), border: getComputedStyle(a).borderTopWidth, text: a.textContent.replace(/\s+/g, ' ').trim() })));
    const cur = tabs.filter((t) => t.cur === 'page');
    check(T('tabs: sticker pills, the current one filled, heavier and aria-current (not colour alone), every tab 44px or taller'),
      tabs.length === 4 && cur.length === 1 && cur[0].weight >= 800 && tabs.filter((t) => t.cur !== 'page').every((t) => t.bg !== cur[0].bg && t.weight < cur[0].weight) && tabs.every((t) => t.h >= 44 && t.border === '2px'), JSON.stringify(tabs));
    await shot(page, `${scheme}-4-tabs`);
    await page.locator('nav.views a').nth(1).click(); await page.waitForURL(/track=a/); await sleep(300);
    check(T('tabs: a tab is still a link, and the current mark moves'), (await page.locator('nav.views a[aria-current="page"]').count()) === 1 && /track=a/.test(page.url()) && (await page.evaluate(() => document.querySelectorAll('.jobs tbody tr').length)) >= 1);
    await go(page);
    // tools
    const f = page.locator('button.tool-toggle', { hasText: 'Filter and sort' }), e = page.locator('button.tool-toggle', { hasText: 'Export' });
    await f.click(); await sleep(450);
    const fo = await page.evaluate(() => { const p = document.getElementById('tool-filter'); const f = p.querySelector('form'); const cs = getComputedStyle(f);
      return { shown: getComputedStyle(p).display !== 'none', border: cs.borderTopWidth, radius: cs.borderTopLeftRadius, shadow: cs.boxShadow !== 'none', fields: [...f.querySelectorAll('input, select')].map((x) => x.name), submit: f.querySelector('button[type=submit]').textContent.trim(), exp: document.querySelector('button.tool-toggle').getAttribute('aria-expanded') }; });
    check(T('Filter and sort: opens a sticker panel with the same fields and the same submit'), fo.shown && fo.border === '2px' && fo.shadow && fo.exp === 'true' && fo.fields.join() === 'track,min,source,q,sort' || fo.fields.join() === 'min,source,q,sort' && fo.submit === 'Apply filters', JSON.stringify(fo));
    await shot(page, `${scheme}-5-filter-open`);
    await e.click(); await sleep(700);
    const ex = await page.evaluate(() => ({ filterHidden: getComputedStyle(document.getElementById('tool-filter')).display === 'none', links: [...document.querySelectorAll('#tool-export .exports a')].map((a) => a.textContent.trim() + ' ' + a.getAttribute('href')), label: document.querySelector('#tool-export .exports .label').textContent.replace(/\s+/g, ' ').trim(), border: getComputedStyle(document.querySelector('#tool-export .exports')).borderTopWidth }));
    check(T('Export: opens in place of the filters, four links with their labels, the count label, a sticker panel'), ex.filterHidden && ex.links.length === 4 && /^Excel \/export\.xlsx/.test(ex.links[0]) && /^Web page \/export\.html/.test(ex.links[3]) && /^Export All Jobs: \d+ listings$/.test(ex.label) && ex.border === '2px', JSON.stringify(ex));
    await shot(page, `${scheme}-5-export-open`);
    // the explainer
    const ex2 = await page.evaluate(() => { const d = document.querySelector('details.how-scoring'); return { open: d.open, summary: d.querySelector('summary').textContent.trim(), cls: d.className, scale: !!d.querySelector('.scale[aria-hidden="true"]') }; });
    check(T('explainer: a peek, shut first, its summary and class unchanged'), ex2.open === false && ex2.summary === 'How match scores work' && ex2.cls === 'notes how-scoring' && ex2.scale);
    await page.locator('details.how-scoring summary').click(); await sleep(200);
    const pic = await page.evaluate(() => { const s = document.querySelector('.scale'), r = s.getBoundingClientRect(), z = document.querySelector('.scale-zero').getBoundingClientRect(), l = document.querySelector('.scale-l').getBoundingClientRect(), rr = document.querySelector('.scale-r').getBoundingClientRect();
      return { visible: r.width > 100 && r.height > 10, words: [l, rr].length && [document.querySelector('.scale-l').textContent, document.querySelector('.scale-r').textContent], order: l.right <= z.left + 1 && z.right <= rr.left + 1, digits: /\d/.test(s.textContent), p: document.querySelector('details.how-scoring p').textContent.replace(/\s+/g, ' ').trim() }; });
    check(T('explainer: the picture is a line with a zero mark between "below zero" and "more of your résumé"; no digits, no scale'), pic.visible && pic.words[0] === 'below zero' && pic.words[1] === 'more of your résumé' && pic.order && !pic.digits && /It is a raw score, not a percentage, and it can be negative\.$/.test(pic.p), JSON.stringify(pic));
    await shot(page, `${scheme}-6-explainer-open`);
    // the tip
    const tip = await page.evaluate(() => ({ n: document.querySelectorAll('.tip').length, say: document.querySelector('.tip-say').textContent.trim(), beforeBody: !!(document.querySelector('.tip').compareDocumentPosition(document.getElementById('results-body')) & Node.DOCUMENT_POSITION_FOLLOWING), x: !document.querySelector('.tip-x').hidden }));
    check(T('tip: once, above the first section, with its dismiss button revealed'), tip.n === 1 && tip.say === 'Open “Why it matched” to see which of your skills a job mentions.' && tip.beforeBody && tip.x, JSON.stringify(tip));
    await page.locator('.tip-x').click(); await sleep(200);
    check(T('tip: dismisses'), (await page.locator('.tip:visible').count()) === 0);
    await ctx.close();
  }

  // ================= The abroad section, the ending banner, no results ===============================================
  {
    const { ctx, page } = await open('m_all', { vp: 'desktop' });
    await go(page);
    const ab = page.locator('details.jobs-section');
    const n = await ab.count();
    if (n) {
      const was = await ab.evaluate((e) => ({ open: e.open, style: getComputedStyle(e).borderTopStyle, h2: e.querySelector('summary h2').textContent.trim(), chip: e.querySelector('.head-note b').textContent.trim() }));
      await ab.locator(':scope > summary').click(); await sleep(250);
      const now = await ab.evaluate((e) => ({ open: e.open, style: getComputedStyle(e).borderTopStyle, rows: e.querySelectorAll('tbody tr').length, stamp: e.querySelectorAll('.stamp').length }));
      check(T('the abroad section is a peek: dashed shut, a sticker open, its cards inside, no stamp'), !was.open && was.style === 'dashed' && now.open && now.style === 'solid' && now.rows >= 1 && now.stamp === 0, JSON.stringify({ was, now }));
      await shot(page, `${scheme}-7-abroad-open`, true);
    } else check(T('the abroad section'), false, 'no abroad section in m_all');
    await ctx.close();
  }
  for (const [sc, q, what] of [['m_failed', '', 'an ending banner'], ['s1', '?q=zzzz', 'no results'], ['m_all', '?min=999', 'no results (a filter)']]) {
    const { ctx, page } = await open(sc, { vp: 'desktop' });
    await go(page, '/results' + q);
    const b = await page.evaluate(() => { const e = document.querySelector('.banner, .no-results'); if (!e) return null; const cs = getComputedStyle(e); return { cls: e.className, border: cs.borderTopWidth, radius: parseFloat(cs.borderTopLeftRadius), shadow: cs.boxShadow !== 'none', text: e.textContent.replace(/\s+/g, ' ').trim().slice(0, 90) }; });
    check(T(`${what}: a sticker card`), !!b && b.border === '2px' && b.radius >= 20 && b.shadow, JSON.stringify(b));
    await shot(page, `${scheme}-8-${sc}${q ? '-nomatch' : ''}`);
    await ctx.close();
  }
}

// ================= Motion: the arrival still runs on cards, reduced motion has none ========================================
process.env.D7_SCHEME = 'light';
for (const [vp, want] of [['desktop', 8], ['mobile', 3]]) {
  const { ctx, page } = await open('m_19', { vp });
  await arrive(page, app); await sleep(1500);
  const m = await M(page);
  check(`motion: the arrival writes in ${want} cards on a ${vp}, nothing else on the list`, count(m, 'write-in') === want && [...new Set(m.anim.map((a) => a[0]))].filter((n) => n !== 'write-in' && n !== 'a-bob').length === 0, JSON.stringify([...new Set(m.anim.map((a) => a[0]))]));
  await ctx.close();
}
{
  const { ctx, page } = await open('m_19', { vp: 'desktop' });
  await go(page);
  await page.locator('details.why summary').first().click(); await sleep(500);
  const names = (await M(page)).anim.map((a) => a[0]);
  check('motion: opening a peek pops its body in (a-pop, no-preference)', names.includes('a-pop'), JSON.stringify(names));
  await ctx.close();
}
{
  const { ctx, page } = await open('m_19', { vp: 'desktop', reduced: true });
  await arrive(page, app); await sleep(1200);
  await page.locator('details.why summary').first().click(); await sleep(500);
  const m = await M(page);
  const names = [...new Set(m.anim.map((a) => a[0]))];
  check('reduced motion: no arrival, no pop, no animation on the page at all (the peek simply opens)', names.filter((n) => n !== 'a-bob').length === 0 && (await page.locator('details.why').first().evaluate((e) => e.open)), JSON.stringify(names));
  await ctx.close();
}

// ================= No overflow at 390 / 768 / 1024 / 1440, with everything open ===============================================
for (const [sc, label] of [['m_19', '19 jobs'], ['s1_19', 'one résumé'], ['m_long', 'long names'], ['m_240', '240 jobs, Show all']]) {
  for (const w of [390, 768, 1024, 1440]) {
    const { ctx, page } = await open(sc, { vp: w <= 390 ? 'mobile' : 'desktop' });
    if (w > 390) await page.setViewportSize({ width: w, height: 900 });
    await go(page, sc === 'm_240' ? '/results?full=1' : '/results', 400);
    for (const s of await page.locator('details.why > summary').all()) { await s.click({ timeout: 1000 }).catch(() => {}); if ((await page.locator('details.why[open]').count()) >= 6) break; }
    await page.locator('details.how-scoring summary').click();
    const ab = page.locator('details.jobs-section > summary'); if (await ab.count()) await ab.first().click();
    await page.locator('button.tool-toggle', { hasText: 'Filter and sort' }).click(); await sleep(450);
    check(`no overflow at ${w}, ${label}, with peeks, the explainer, the filter panel and the abroad section open`, (await overflow(page)) <= 0, `${await overflow(page)}`);
    if (sc === 'm_19' && (w === 768 || w === 1024)) await shot(page, `${w}-open`);
    await ctx.close();
  }
}

// ================= The phone Apply target is at least HEAD's ==========================================================
{
  const { ctx, page } = await open('s1_19', { vp: 'mobile' });
  await go(page);
  await page.locator('a.apply').first().scrollIntoViewIfNeeded(); await sleep(200);
  const a = await page.evaluate(() => { const l = document.querySelector('a.apply'), r = l.getBoundingClientRect(); const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const hit = (x, y) => { const e = document.elementFromPoint(x, y); return !!e && (e === l || l.contains(e)); };
    return { w: Math.round(r.width), h: Math.round(r.height), centre: hit(cx, cy), corners: [hit(r.left + 16, cy), hit(r.right - 16, cy), hit(cx, r.top + 4), hit(cx, r.bottom - 4)], href: l.getAttribute('href'), target: l.getAttribute('target'), rel: l.getAttribute('rel'),
      hidden: l.querySelector('.visually-hidden').textContent, arrow: l.querySelector('.go').getAttribute('aria-hidden') }; });
  check('phone: the Apply target is at least HEAD\'s in both directions, the whole of it answers, and the link is the page\'s own', a.w >= head.w && a.h >= head.h && a.h >= 44 && a.centre && a.corners.every(Boolean) && a.target === '_blank' && a.rel === 'noopener' && /^ to .+ at .+$/.test(a.hidden) && a.arrow === 'true', JSON.stringify({ mine: a, head }));
  await ctx.close();
}

console.log(out.join('\n'));
const fails = out.filter((l) => l.startsWith('FAIL')).length;
console.log(`\n${out.length - fails} of ${out.length} checks pass`);
app.stop(); await browser.close();
process.exit(ok ? 0 : 1);
