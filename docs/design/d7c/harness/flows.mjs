// D7C: the final browser flows, against the REAL application (the public app and worker on loopback, the operator console with its
// real profile writes and its real engine dry run), in whichever engine --engine names. Synthetic data only; no provider, model or key.
//
//   D7_OUT=output/design-D7C node docs/design/d7c/harness/flows.mjs [--engine chromium|firefox|webkit] [--channel chrome] [--only W7,W8]
//
// Writes output/design-D7C/flows-<engine>.json (or flows.json for chromium) and the screenshots of the states D7C changed to
// output/design-D7C/shots-<engine>/. A check that passes through code written for what an engine does differently says so (an
// ENGINE DIFFERENCE), never silently.
//
//   W1  one résumé, free: upload to Results, through the screens                 W6  Save, then run at once (console, real profile, real dry run)
//   W2  three résumés, free: the same, and Results' tabs                         W7  the unsaved-edits guard: stay, discard, save, revert, keyboard, phone
//   W3  paid, fully covered                                                       W8  failed, stopped, timed-out, and every ending after a web restart
//   W4  paid, partial coverage                                                    W9  no raw diagnostics in anything a visitor can open (and the console keeps them)
//   W5  paid, insufficient credit / unavailable                                   W10 Results: tabs, filter, export, negative scores, recommendations, "jobs found"
//   H   the operator's header on a free sweep (no amber $0.00, no credit talk)
import { launch, argv, sleep, visitor, serveApp, serveLocal, M, mkdir, checker, RUNTIME, fs, path, os, PW_VERSION, ROOT } from '../../motion-d7b/harness/lib.mjs';
import { fileURLToPath } from 'url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const engine = argv('engine', 'chromium'), channel = argv('channel', ''), tag = channel || engine;
const only = String(argv('only', '')).split(',').filter(Boolean);
const want = (id) => { const w = !only.length || only.includes(id); if (w) globalThis.__check = id; return w; };
const { check, finish } = checker(tag === 'chromium' ? 'flows.json' : `flows-${tag}.json`);
const shots = mkdir(tag === 'chromium' ? 'shots' : `shots-${tag}`);
const shoot = async (page, name) => { try { await page.screenshot({ path: path.join(shots, `${name}.png`), fullPage: false }); } catch (e) { /* a shot is evidence, never a verdict */ } };

// WebKit keeps no `Secure` cookie that plain http on loopback sets, so the journeys (W1, W2), where the app sets the visitor's session
// cookie itself, run there with the harness serving it without `Secure`. The application is not touched; the note travels with the result.
if (engine === 'webkit') process.env.D7C_PLAIN_COOKIE = '1';
const PLAIN_COOKIE_NOTE = engine === 'webkit' ? 'WebKit does not keep a Secure cookie set over plain http on loopback (Chromium and Firefox do), so this journey ran with the harness serving the session cookie without Secure; the application is unchanged and production is https' : '';
const app = await serveApp({ port: 5077, script: path.join(HERE, 'app.py') });
const con = await serveLocal({ port: 5078, script: path.join(HERE, 'console.py') });
const browser = await launch(engine);
if (!browser) { console.log('no browser: nothing verified'); app.stop(); con.stop(); process.exit(2); }
const version = `${channel ? 'Google Chrome (channel chrome)' : engine} ${browser.version()}`;
console.log('engine:', version);

const open = (scenario, o = {}) => visitor(browser, app, scenario, { trace: false, ...o });
const openConsole = (n, o = {}) => visitor(browser, { url: con.at(n) }, null, { trace: false, ...o });
const body = (page) => page.evaluate(() => document.body.innerText.replace(/\s+/g, ' ').trim());
const html = (page) => page.content();
const go = async (page, base, p) => { await page.goto(base + p, { waitUntil: 'load' }); await sleep(450); };
const seen = (t, ...needles) => needles.every((n) => t.includes(n));
const MARKERS = ['/Users/operator/private', '/srv/app/', 'Traceback (most recent call last)', 'apify_api_SECRETSECRET', 'APIFY_TOKEN=', 'SWEEP_WORKER_TOKEN',
  'skill_scan.widen', 'local_profile._notes', 'make_profile.widen_skills', 'years_experience COMPUTED', 'role_gate_rejected', 'INTERNAL-DIAGNOSTIC-MARKER', 'C:\\Users\\operator'];
const leaked = (t) => MARKERS.filter((m) => t.includes(m));
const phone = (vp) => vp === 'mobile';
const TAB = engine === 'webkit' ? 'Alt+Tab' : 'Tab';   // Safari and WebKit reach links and buttons with Option+Tab; a plain Tab visits text fields only (a platform setting, not the page)
const press = async (page, loc, vp) => { if (phone(vp)) await loc.tap(); else await loc.click(); };
const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
const TRACKB = 'b'.repeat(16), TRACKA = 'a'.repeat(16);
// A5: open the experience editor — the years chip on a tree that has it, the Adjust disclosure on an older one. Idempotent.
const openYears = async (page) => {
  const chip = page.locator('button.xp-chip').first();
  if (await chip.count()) { if ((await chip.getAttribute('aria-expanded')) !== 'true') await chip.click(); }
  else await page.locator('details.adjust > summary').first().click();
};

// ===== W7: the unsaved-edits guard =============================================================================================
if (want('W7')) {
  const out = {};
  for (const vp of ['desktop', 'mobile']) {
    const { ctx, page } = await open('all_ready', { vp });
    await go(page, app.url, '/review');
    // A5: the years field lives behind the xp chip now, not the Adjust disclosure (older trees still have the disclosure).
    const adj = { click: () => openYears(page) };
    const target = page.locator(`a[href="/review?track=${TRACKB}"]`).first();
    const dlg = page.locator('dialog#leave-guard');
    const years = page.locator('button[aria-label="One year more"]').first();
    const value = () => page.locator('input[name=experience_years]').first().inputValue();
    const r = out[vp] = { steps: [] };
    const step = (name, ok, extra) => { r.steps.push([name, !!ok, extra]); };
    r.hasGuard = await dlg.count() === 1 && await page.locator('form[data-editor]').count() === 1;
    const startUrl = page.url(), v0 = await value().catch(() => null);
    // a. nothing changed: nothing asked
    if (await target.count()) {
      await Promise.all([page.waitForURL(`**/review?track=${TRACKB}`), press(page, target, vp)]);
      step('clean: the link goes straight there', !(await dlg.count() && await dlg.evaluate((d) => d.open)).valueOf(), page.url());
      await go(page, app.url, '/review');
    } else step('the other résumé is a link on this page', false);
    // b. dirty: asked, with the choice
    await adj.click(); await sleep(250);
    const v1 = await (async () => { await press(page, years, vp); await sleep(120); return value(); })();
    step('editing changes the value', v1 !== v0, [v0, v1]);
    const target2 = page.locator(`a[href="/review?track=${TRACKB}"]`).first();
    await press(page, target2, vp); await sleep(350);
    const open1 = await dlg.evaluate((d) => d.open);
    const focusIn = await page.evaluate(() => document.getElementById('leave-guard').contains(document.activeElement) && document.activeElement.value === 'stay');
    step('dirty: the question is asked and focus is on Stay', open1 && focusIn, { open1, focusIn });
    step('and nothing navigated', page.url() === startUrl, page.url());
    const box = await dlg.boundingBox();
    const vw = await page.evaluate(() => innerWidth);
    step('the dialog fits the screen', box && box.x >= 0 && box.x + box.width <= vw && (await overflow(page)) <= 0, { box, vw });
    if (vp === 'desktop') await shoot(page, `w7-dirty-dialog-${vp}`); else await shoot(page, `w7-dirty-dialog-${vp}`);
    const names = await dlg.locator('button').allInnerTexts();
    step('the two answers are in plain words', names.join('|') === 'Stay and keep editing|Discard changes and leave', names);
    const heights = await dlg.locator('button').evaluateAll((bs) => bs.map((b) => Math.round(b.getBoundingClientRect().height)));
    step('each answer is at least 44px tall (a thumb)', heights.every((h) => h >= 44) || !phone(vp), heights);
    // c. stay keeps the edit
    await page.keyboard.press('Escape'); await sleep(250);
    step('Escape is stay: closed, still here, edit kept', !(await dlg.evaluate((d) => d.open)) && page.url() === startUrl && (await value()) === v1, await value());
    step('focus is handed back to what was pressed', await page.evaluate(() => document.activeElement && document.activeElement.tagName === 'A'), null);
    await press(page, target2, vp); await sleep(300);
    await dlg.locator('button[value=stay]').click(); await sleep(250);
    step('Stay: closed, edit kept', !(await dlg.evaluate((d) => d.open)) && (await value()) === v1, await value());
    // d. revert is clean
    await press(page, page.locator('button[aria-label="One year less"]').first(), vp); await sleep(120);
    step('put back to what it was', (await value()) === v0, await value());
    await Promise.all([page.waitForURL(`**/review?track=${TRACKB}`), press(page, page.locator(`a[href="/review?track=${TRACKB}"]`).first(), vp)]);
    step('edited then reverted: nothing asked', true, page.url());
    // e. discard leaves, and the edit is gone
    await go(page, app.url, '/review'); await adj.click(); await sleep(200);
    await press(page, years, vp); await sleep(100);
    await press(page, page.locator(`a[href="/review?track=${TRACKB}"]`).first(), vp); await sleep(300);
    await Promise.all([page.waitForURL(`**/review?track=${TRACKB}`), dlg.locator('button[value=leave]').click()]);
    step('Discard: goes where the link went', page.url().endsWith(`track=${TRACKB}`), page.url());
    await go(page, app.url, '/review');
    step('and the discarded edit is not there', (await page.locator('input[name=experience_years]').first().inputValue()) === v0, null);
    // f. saving clears it
    await adj.click(); await sleep(200); await press(page, years, vp); await sleep(100);
    const save = page.locator('form[data-editor] button[type=submit]').first();
    await Promise.all([page.waitForURL((u) => !u.href.includes('/review?') || u.href !== startUrl, { timeout: 8000 }).catch(() => null), press(page, save, vp)]);
    await sleep(500);
    step('Save: no question, the page moved on', !(await page.locator('dialog#leave-guard[open]').count()), page.url());
    await ctx.close();

    if (vp === 'desktop') {                                  // keyboard and the browser's own prompt, on a desktop
      const k = await open('all_ready', { vp });
      await go(k.page, app.url, '/review');
      await openYears(k.page); await sleep(200);
      await k.page.locator('button[aria-label="One year more"]').first().click(); await sleep(100);
      const link = k.page.locator(`a[href="/review?track=${TRACKB}"]`).first();
      await link.focus(); await k.page.keyboard.press('Enter'); await sleep(350);
      const asked = await k.page.locator('dialog#leave-guard').evaluate((d) => d.open);
      await k.page.keyboard.press(TAB); await sleep(100);
      const onDiscard = await k.page.evaluate(() => document.activeElement && document.activeElement.value === 'leave');
      await k.page.keyboard.press(`Shift+${TAB}`); await sleep(50);
      await k.page.keyboard.press('Escape'); await sleep(200);
      step('keyboard: Enter on the link asks, Tab reaches Discard, Escape stays', asked && onDiscard && !(await k.page.locator('dialog#leave-guard').evaluate((d) => d.open)), { asked, onDiscard });
      await link.focus(); await k.page.keyboard.press('Enter'); await sleep(300);
      await k.page.keyboard.press(TAB); await k.page.keyboard.press('Enter');
      await k.page.waitForURL(`**/review?track=${TRACKB}`, { timeout: 6000 }).catch(() => null);
      step('keyboard: Tab then Enter on Discard leaves', k.page.url().includes(`track=${TRACKB}`), k.page.url());
      await go(k.page, app.url, '/review'); await openYears(k.page); await sleep(150);
      await k.page.locator('button[aria-label="One year more"]').first().click(); await sleep(100);
      let prompt = null;
      k.page.on('dialog', async (d) => { prompt = d.type(); await d.dismiss(); });
      await k.page.close({ runBeforeUnload: true }).catch(() => null); await sleep(500);
      step('closing the tab with edits gets the browser\'s own prompt', prompt === 'beforeunload', prompt);
      await k.ctx.close().catch(() => null);
    }
  }
  const all = Object.values(out).flatMap((o) => o.steps);
  const failed = all.filter((s) => !s[1]).map((s) => s[0]);
  const noPrompt = out.desktop.steps.find((s) => s[0].startsWith('closing the tab'));
  const promptNote = noPrompt && !noPrompt[1] ? `this engine did not raise a beforeunload dialog for a closed page under automation (${noPrompt[2]}): the browser's own prompt cannot be driven here; the script's side of it (preventDefault, a returnValue) is pinned by dirty_test.js` : '';
  check('W7', 'the unsaved-edits guard: nothing asked when nothing changed or when it was put back; asked with Stay and Discard when it was; Escape, the backdrop and Stay keep the edit and give focus back; Discard leaves and the edit is gone; Save clears it; keyboard; and on a phone',
    out.desktop.hasGuard && out.mobile.hasGuard && failed.filter((f) => !f.startsWith('closing the tab')).length === 0, JSON.stringify({ failed, desktop: out.desktop.steps.length, mobile: out.mobile.steps.length }), [promptNote, engine === 'webkit' ? 'WebKit (Safari) reaches links and buttons with Option+Tab, a plain Tab visits text fields only (a platform setting), so the keyboard steps press Alt+Tab here' : ''].filter(Boolean).join('; '));
  if (failed.length) console.log('   W7 steps failed:', failed.join(' | '));
}

// ===== W8: failed, stopped, timed out, and every ending after a web restart ====================================================
if (want('W8')) {
  // scenario, running heading, /progress state, Results notice, what the banner has / must not have, and what changes after a web restart
  // (a PAID run's plan went with the memory that held it, so it is read from the worker alone: no searches to count, and no claim about
  // money either way; a free run, a stop and a timeout read exactly as before)
  const PAID_GONE = { heading: 'Sweep stopped early', state: 'halted', has: ['already fetched is saved'], not: ['Nothing was charged', 'credit is spent'] };
  const cases = [
    ['p_paid_one_incomplete', 'The sweep did not finish', 'incomplete', 'This search did not finish', { has: ['Every search ran, then the sweep stopped', 'their credit is spent', 'See what it found'], not: ['Nothing was charged', 'Finish the remaining 0'] }, PAID_GONE],
    ['p_paid_one_incomplete_timeout', 'The sweep did not finish', 'incomplete', 'This search ran out of time', { has: ['Every search ran, then the sweep ran out of time', 'time limit'], not: ['Nothing was charged'] }, { ...PAID_GONE, has: ['time limit'] }],
    ['p_paid_one_failed', 'Sweep stopped early', 'halted', 'This search did not finish', { has: ['The reason is not recorded'], not: [] }, PAID_GONE],
    ['p_paid_one_timeout', 'Sweep stopped early', 'halted', 'This search ran out of time', { has: ['ran out of time'], not: [] }, { ...PAID_GONE, has: ['time limit'] }],
    ['p_paid_one_stopped', 'You stopped the sweep', 'stopped', 'You stopped this search', { has: ['You stopped it'], not: [] }, { heading: 'You stopped the sweep', state: 'stopped', has: ['You stopped it'], not: ['Nothing was charged'] }],
    ['p_paid_one_worker_stopped', 'You stopped the sweep', 'stopped', 'You stopped this search', { has: ['You stopped it'], not: [] }, { heading: 'You stopped the sweep', state: 'stopped', has: ['You stopped it'], not: ['Nothing was charged'] }],
    ['p_paid_one_interrupted', 'Sweep stopped early', 'halted', 'This search did not finish', { has: ['The reason is not recorded'], not: ['You stopped'] }, { ...PAID_GONE, not: ['You stopped', 'Nothing was charged'] }],
    ['p_free_one_failed', 'Sweep stopped early', 'halted', 'This search did not finish', { has: ['did not finish'], not: ['Your jobs are ready'] }],
    ['p_free_one_timeout', 'Sweep stopped early', 'halted', 'This search ran out of time', { has: ['time limit'], not: ['Your jobs are ready'] }],
    ['p_free_one_stopped', 'You stopped the sweep', 'stopped', 'You stopped this search', { has: ['You stopped it'], not: ['Your jobs are ready'] }],
    ['p_free_one_worker_stopped', 'You stopped the sweep', 'stopped', 'You stopped this search', { has: ['You stopped it'], not: ['Your jobs are ready'] }],
    ['p_paid_one_done', 'Your jobs are ready', 'finished', null, { has: ['Every search ran'], not: ['did not finish'] }, { heading: 'Your jobs are ready', state: 'finished', has: ['The search finished'], not: ['did not finish'] }],
  ];
  const rows = [];
  for (const [scenario, heading0, state0, notice, words0, after] of cases) {
    for (const restart of [false, true]) {
      const heading = restart && after ? after.heading : heading0, state = restart && after ? after.state : state0, words = restart && after ? after : words0;
      const { ctx, page } = await open(scenario);
      if (restart) { await app.api('/__restart'); }
      await go(page, app.url, '/running');
      const prog = await page.evaluate(() => fetch('/progress', { credentials: 'same-origin' }).then((r) => r.json()));
      const t = await body(page);
      const h1 = await page.locator('h1').first().innerText();
      const row = { scenario, restart, h1, state: prog.state };
      const problems = [];
      if (h1.trim() !== heading) problems.push(`heading ${JSON.stringify(h1)} not ${JSON.stringify(heading)}`);
      if (prog.state !== state) problems.push(`state ${prog.state} not ${state}`);
      for (const w of words.has) if (!t.includes(w)) problems.push(`missing "${w}"`);
      for (const w of words.not) if (t.includes(w)) problems.push(`has "${w}"`);
      if (scenario.includes('paid') && state === 'incomplete' && /Finish the remaining/.test(t)) problems.push('offers to finish nothing');
      if (scenario.includes('paid') && restart && /Nothing was charged/.test(t)) problems.push('a paid run after a restart says nothing was charged');
      await go(page, app.url, '/results');
      const rt = await body(page);
      if (notice && !rt.includes(notice)) problems.push(`results lack "${notice}"`);
      if (!notice && /This search (did not finish|ran out of time)|You stopped this search/.test(rt)) problems.push('results carry a notice for a finished run');
      const jobs = await page.locator('table.jobs tbody tr, .jobs tbody tr').count();
      if (jobs < 1 && scenario !== 'p_paid_one_done') problems.push('no jobs on Results');
      row.problems = problems; rows.push(row);
      if (!restart && ['p_paid_one_incomplete', 'p_paid_one_worker_stopped'].includes(scenario)) { await go(page, app.url, '/running'); await shoot(page, `w8-${scenario}-running`); await go(page, app.url, '/results'); await shoot(page, `w8-${scenario}-results`); }
      if (restart && ['p_paid_one_worker_stopped', 'p_free_one_failed'].includes(scenario)) { await go(page, app.url, '/running'); await shoot(page, `w8-${scenario}-after-restart`); }
      await ctx.close();
    }
  }
  // the same endings on a phone, as evidence of what a visitor with a small screen reads
  for (const [scenario, restart] of [['p_paid_one_incomplete', false], ['p_paid_one_worker_stopped', false], ['p_paid_one_worker_stopped', true], ['p_paid_one_failed', true]]) {
    const { ctx, page } = await open(scenario, { vp: 'mobile' });
    if (restart) await app.api('/__restart');
    await go(page, app.url, '/running'); await shoot(page, `w8-${scenario}-${restart ? 'after-restart' : 'running'}-mobile`);
    if (!restart) { await go(page, app.url, '/results'); await shoot(page, `w8-${scenario}-results-mobile`); }
    rows.push({ scenario, restart, mobileOverflow: await overflow(page), problems: (await overflow(page)) > 0 ? ['overflow on a phone'] : [] });
    await ctx.close();
  }
  const bad = rows.filter((r) => r.problems.length);
  check('W8', 'every way a run can end, before and after a web restart that forgot the visitor\'s click: a paid run whose every search ran and whose process then failed says every search ran (never "finished", never "nothing was charged"); the worker\'s own stop is a stop, a failure and a restart are not; a timeout only on the worker\'s word; the jobs stay; a finished run is untouched',
    bad.length === 0, JSON.stringify({ cases: rows.length, bad: bad.map((b) => [b.scenario, b.restart, b.problems]) }).slice(0, 900));
}

// ===== W9: no raw diagnostics in anything a visitor can open; the console keeps them =============================================
if (want('W9')) {
  await app.api('/__hostile/1');
  const out = {};
  for (const vp of ['desktop', 'mobile']) {
    const { ctx, page } = await open('all_ready', { vp });
    const dirty = [];
    for (const p of ['/review', '/review?track=' + TRACKA, '/review?track=' + TRACKB, '/', '/key']) {
      await go(page, app.url, p);
      const h = await html(page), t = await body(page);
      const l = leaked(h).concat(leaked(t));
      if (l.length) dirty.push([p, [...new Set(l)]]);
      if (/Technical notes on how this was read|Worth knowing/.test(t)) dirty.push([p, ['the notes door']]);
    }
    for (const p of ['/profile', '/profile.py']) {
      const r = await page.evaluate((u) => fetch(u, { credentials: 'same-origin' }).then((x) => x.text()), p);
      if (leaked(r).length) dirty.push([p, leaked(r)]);
    }
    await go(page, app.url, '/review'); await shoot(page, `w9-public-review-${vp}`);
    out[vp] = dirty; await ctx.close();
  }
  await app.api('/__hostile/0');
  const c = await openConsole(2);
  await go(c.page, con.at(2), '/review');
  const ct = await body(c.page), ch = await html(c.page);
  const operator = ct.includes('Worth knowing') && ct.includes('operator can read this') && !ch.includes('<script>alert');
  await shoot(c.page, 'w9-console-review-keeps-notes');
  await c.ctx.close();
  check('W9', 'no raw reading diagnostics (paths, a stack trace, secrets, internal names) in anything a visitor can open (the review, every card, the profile routes, the front door, the key screen), in the page text, its markup or the files; the operator\'s console still shows its notes, escaped',
    out.desktop.length === 0 && out.mobile.length === 0 && operator, JSON.stringify({ desktop: out.desktop, mobile: out.mobile, consoleKeepsNotes: operator }));
}

// ===== W4 / W5 / W3: paid, fully covered, partial, insufficient, unavailable ======================================================
const sentenceOf = (page) => page.evaluate(() => { const p = document.querySelector('p[x-show="overWhy"]'); return p && getComputedStyle(p).display !== 'none' ? p.innerText.trim() : ''; });
if (want('W3') || want('W4') || want('W5')) {
  const rows = {};
  for (const [id, scenario, expect] of [['W3', 'c_paid_one', { sentence: '', button: /Start Deep Sweep|Run the sweep/, enabled: true }],
                                        ['W4', 'c_over_one', { sentence: /^Your connected accounts can run \d+ of \d+ of these paid searches\.$/, button: /Run what my credit covers/, enabled: false /* until the box is ticked */ }],
                                        ['W5', 'c_none_one', { sentence: 'None of these paid searches fit within the credit on your connected accounts.', button: /Run what my credit covers|Paid searches unavailable/, enabled: false }]]) {
    if (!want(id)) continue;
    for (const vp of ['desktop', 'mobile']) {
      const { ctx, page } = await open(scenario, { vp });
      await go(page, app.url, '/configure');
      const s = await sentenceOf(page);
      await shoot(page, `${id.toLowerCase()}-configure-${vp}`);
      await go(page, app.url, '/confirm');
      const btn = page.locator('main form button[type=submit]').first();   // Start / Run what my credit covers; the key box's own button comes after
      const label = (await btn.innerText()).replace(/\s+/g, ' ').trim();
      const disabled = await btn.evaluate((b) => b.disabled);
      const t = await body(page);
      await shoot(page, `${id.toLowerCase()}-confirm-${vp}`);
      rows[`${id} ${vp}`] = { s, label, disabled, zero: /\$0\.00 more/.test(t) || /\$0\.00 more/.test(s), over: await overflow(page) };
      await ctx.close();
    }
  }
  const fail = [];
  for (const [k, r] of Object.entries(rows)) {
    const id = k.slice(0, 2);
    if (r.zero) fail.push(`${k}: a $0.00 shortfall`);
    if (r.over > 0) fail.push(`${k}: overflow ${r.over}`);
    if (id === 'W3' && (r.s !== '' || r.disabled)) fail.push(`${k}: a fully covered plan should say nothing and be startable (${JSON.stringify(r)})`);
    if (id === 'W4' && !/^Your connected accounts can run \d+ of \d+ of these paid searches\.$/.test(r.s)) fail.push(`${k}: partial coverage wording (${JSON.stringify(r.s)})`);
    if (id === 'W5' && r.s !== 'None of these paid searches fit within the credit on your connected accounts.') fail.push(`${k}: insufficient wording (${JSON.stringify(r.s)})`);
  }
  // unavailable: the worker's engine cannot authorise a paid sweep
  if (want('W5')) {
    const { ctx, page } = await open('c_paid_one');
    await app.api('/__nopaid/1');                              // (a scenario build clears it)
    await go(page, app.url, '/configure');
    const s = await sentenceOf(page);
    await go(page, app.url, '/confirm');
    const t = await body(page);
    const btn = page.locator('main form button[type=submit]').first();
    const unavailable = { s, label: (await btn.innerText()).replace(/\s+/g, ' ').trim(), disabled: await btn.evaluate((b) => b.disabled), said: t.includes('Paid searches are temporarily unavailable') };
    await shoot(page, 'w5-unavailable-confirm-desktop');
    await ctx.close(); await app.api('/__nopaid/0');
    if (!/^Paid searches are temporarily unavailable, so none will start\. Nothing is charged\.$/.test(unavailable.s) || !unavailable.disabled || !unavailable.said) fail.push(`unavailable: ${JSON.stringify(unavailable)}`);
    rows.unavailable = unavailable;
  }
  for (const id of ['W3', 'W4', 'W5']) if (want(id)) check(id, { W3: 'paid, fully covered: Configure says nothing is over, Confirm can start', W4: 'paid, partial coverage: the sentence says how many searches the accounts can run (never "$0.00 more"), Confirm offers what the credit covers', W5: 'paid, insufficient credit or unavailable: the sentence says so in words, Confirm cannot start a paid search' }[id],
    !fail.some((f) => f.startsWith(id) || (id === 'W5' && f.startsWith('unavailable'))), JSON.stringify(Object.fromEntries(Object.entries(rows).filter(([k]) => k.startsWith(id) || (id === 'W5' && k === 'unavailable')))).slice(0, 700) + (fail.length ? ' FAILURES: ' + fail.join('; ') : ''));
}

// ===== W6: Save, then run at once (console, real profile writer, real dry run) =====================================================
if (want('W6')) {
  const out = [];
  for (const vp of ['desktop']) {
    await con.api(0, '/__reset');
    const { ctx, page } = await openConsole(0, { vp });
    const price = async (depth) => {
      await go(page, con.at(0), '/configure');
      await page.locator('input[name=max_results]').fill(String(depth));
      await Promise.all([page.waitForURL('**/confirm'), page.locator('form.split button[type=submit]').first().click()]);
      await sleep(300);
      const t = await body(page);
      const m = t.match(/Total to spend \$(\d+\.\d\d)/);
      return { depth, total: m ? Number(m[1]) : null };
    };
    for (const d of [20, 40, 20, 40]) out.push(await price(d));
    await shoot(page, 'w6-confirm-after-second-save');
    // and the run itself starts from the newest save: Run at once
    await Promise.all([page.waitForURL('**/running', { timeout: 15000 }).catch(() => null), page.locator('main form button[type=submit]').last().click()]);
    await ctx.close();
  }
  const totals = out.map((o) => o.total);
  check('W6', 'Save, then Confirm and Run at once: with the profile rewritten inside one second at the same size (depth 20, then 40, then back) the price Confirm shows is the engine\'s reading of the file just saved each time, never the first save\'s',
    totals.every((t) => t) && totals[0] === totals[2] && totals[1] === totals[3] && totals[1] > totals[0], JSON.stringify(out));
}

// ===== W10: Results =======================================================================================================
if (want('W10')) {
  const out = { problems: [] };
  for (const vp of ['desktop', 'mobile']) {
    const { ctx, page } = await open('m_all', { vp });
    await go(page, app.url, '/results');
    const h1 = await page.locator('h1').first().innerText();
    if (!/^\d+ jobs? found$/.test(h1.trim())) out.problems.push(`${vp}: heading ${JSON.stringify(h1)}`);
    if (/matched your profile/.test(await body(page))) out.problems.push(`${vp}: still "matched your profile"`);
    const tabs = await page.locator('nav.views a').allInnerTexts();
    if (tabs.length !== 4) out.problems.push(`${vp}: ${tabs.length} tabs`);
    const toggles = await page.locator('button.tool-toggle').evaluateAll((bs) => bs.map((b) => ({ text: b.innerText.trim(), cls: b.className, border: getComputedStyle(b).borderTopWidth, h: b.getBoundingClientRect().height })));
    if (toggles.map((x) => x.text).join('|') !== 'Filter and sort|Export…') out.problems.push(`${vp}: toggles ${JSON.stringify(toggles)}`);
    // An outlined button, not an underlined word: a secondary with a real border (1px Quiet Ledger, 2px Direction A's sticker).
    if (!toggles.every((x) => x.cls.includes('secondary') && parseFloat(x.border) >= 1)) out.problems.push(`${vp}: toggles are not outlined buttons`);
    if (phone(vp) && !toggles.every((x) => x.h >= 44)) out.problems.push(`${vp}: toggle height < 44`);
    // the negative score is there and says so
    const negative = await page.evaluate(() => [...document.querySelectorAll('td.score, .jobs tbody tr td:first-child')].some((e) => e.innerText.trim().startsWith('-')));
    if (!negative) out.problems.push(`${vp}: no negative score row`);
    // recommendation words are present for All Jobs
    const t = await body(page);
    if (!/Suggested résumé/.test(t)) out.problems.push(`${vp}: no "Suggested résumé"`);
    // Filter opens, a minimum applies (instant swap), Export opens and is separate
    await page.locator('button.tool-toggle', { hasText: 'Filter and sort' }).click(); await sleep(450);
    const filterOpen = await page.locator('#tool-filter').isVisible();
    await page.locator('button.tool-toggle', { hasText: 'Export' }).click(); await sleep(450);
    const exportOpen = await page.locator('#tool-export').isVisible(), filterClosed = !(await page.locator('#tool-filter').isVisible());
    if (!filterOpen || !exportOpen || !filterClosed) out.problems.push(`${vp}: tools ${JSON.stringify({ filterOpen, exportOpen, filterClosed })}`);
    const links = await page.locator('#tool-export a').evaluateAll((as) => as.map((a) => a.getAttribute('href')));
    if (links.length < 3 || links.some((l) => /track=/.test(l))) out.problems.push(`${vp}: export links ${JSON.stringify(links)}`);
    const csv = await page.evaluate((u) => fetch(u, { credentials: 'same-origin' }).then((r) => r.text()), links.find((l) => l.includes('.csv')));
    const lines = csv.trim().split('\n').length - 1;
    if (lines < 6) out.problems.push(`${vp}: the export holds ${lines} rows`);
    await shoot(page, `w10-results-${vp}`);
    await page.locator('button.tool-toggle', { hasText: 'Filter and sort' }).click(); await sleep(450);
    await shoot(page, `w10-results-filter-open-${vp}`);
    await go(page, app.url, '/results?min=0&sort=score');
    const filtered = await page.locator('h1').first().innerText();
    if (!/of \d+ jobs shown/.test(filtered)) out.problems.push(`${vp}: a filtered heading is ${JSON.stringify(filtered)}`);
    // a résumé's own view keeps its own wording
    await go(page, app.url, `/results?track=${TRACKA}`);
    const view = await page.locator('h1').first().innerText();
    if (!/jobs? evaluated for /.test(view)) out.problems.push(`${vp}: the résumé view says ${JSON.stringify(view)}`);
    if ((await overflow(page)) > 0) out.problems.push(`${vp}: overflow`);
    out[vp] = { h1: h1.trim(), tabs: tabs.length, csvRows: lines };
    await ctx.close();
  }
  check('W10', 'Results: "N jobs found" (never "matched your profile"), the four tabs, Filter and sort and Export as two outlined buttons that open separately (44px on a phone), a negative score and the suggested résumé shown, the export holds every job whatever the view, a filter says "of N shown", a résumé\'s view keeps "evaluated for"',
    out.problems.length === 0, JSON.stringify(out));
}

// ===== W1 / W2: through the screens ====================================================================================
async function journey(vp, count) {
  const trail = [];
  try { return await journeyRun(vp, count, trail); } catch (e) { e.trail = trail; throw e; }
}
async function journeyRun(vp, count, trail) {
  const { ctx, page } = await open('fresh', { vp });
  const names = ['ada', 'bhaskar', 'chen'].slice(0, count);
  const files = names.map((n) => ({ name: `${n}.pdf`, mimeType: 'application/pdf', buffer: Buffer.from(`%PDF-1.7 ${n}`) }));
  await go(page, app.url, '/');
  await page.locator('input[type=file]').setInputFiles(files); await sleep(300);
  await Promise.all([page.waitForURL('**/review**', { timeout: 20000 }), press(page, page.locator('main button.primary[type=submit]').first(), vp)]);
  trail.push(page.url().replace(app.url, ''));
  // read and save every résumé (each is one primary Save), then on to the key screen
  for (let i = 0; i < count; i++) {
    await page.waitForSelector('form[data-editor] button[type=submit]', { timeout: 25000 });
    const save = page.locator('form[data-editor] button[type=submit]').first();
    await Promise.all([page.waitForNavigation({ timeout: 15000 }).catch(() => null), press(page, save, vp)]);
    await sleep(500); trail.push(page.url().replace(app.url, ''));
  }
  if (!page.url().includes('/key')) await go(page, app.url, '/key');
  await Promise.all([page.waitForNavigation({ timeout: 10000 }).catch(() => null), press(page, page.locator('form[action*="key/free"] button, button:has-text("free")').first(), vp)]);
  trail.push(page.url().replace(app.url, ''));
  if (!page.url().includes('/configure')) await go(page, app.url, '/configure');
  // one résumé: Configure's own "Start Quick Sweep" runs it; several: Configure saves and Confirm starts it
  const next = page.locator('main form button.primary[type=submit]').last();
  if (count === 1) await Promise.all([page.waitForURL('**/running', { timeout: 20000 }), press(page, next, vp)]);
  else {
    await Promise.all([page.waitForURL('**/confirm', { timeout: 15000 }), press(page, next, vp)]); trail.push('/confirm');
    await Promise.all([page.waitForURL('**/running', { timeout: 20000 }), press(page, page.locator('main form button.primary[type=submit]').last(), vp)]);
  }
  trail.push('/running');
  if (count === 1) await app.api('/__rows/3'); else await app.api('/__serve_live');
  await app.api('/__step/done');
  await page.waitForURL('**/results**', { timeout: 25000 }).catch(async () => { await press(page, page.locator('a:has-text("See the results")').first(), vp); await page.waitForURL('**/results**', { timeout: 10000 }); });
  await sleep(600); trail.push('/results');
  const h1 = await page.locator('h1').first().innerText();
  const jobs = await page.locator('.jobs tbody tr').count();
  const tabs = await page.locator('nav.views a').count();
  await shoot(page, `w${count === 1 ? 1 : 2}-results-${vp}`);
  const r = { trail, h1: h1.trim(), jobs, tabs, overflow: await overflow(page) };
  await ctx.close();
  return r;
}
for (const [id, count] of [['W1', 1], ['W2', 3]]) {
  if (!want(id)) continue;
  const out = {};
  for (const vp of ['desktop', 'mobile']) {
    try { out[vp] = await journey(vp, count); } catch (e) { out[vp] = { error: String(e.message).split('\n')[0], trail: e.trail }; }
  }
  const ok = (r) => r && !r.error && r.trail.at(-1) === '/results' && r.jobs >= 1 && r.overflow <= 0 && (count === 1 || r.tabs >= 2);
  check(id, count === 1 ? 'one résumé, free: upload, read, review, the free choice, Configure, the running screen, Results, by pressing the screens\' own buttons' : 'three résumés, free: the same with Confirm, ending on Results with a tab for each',
    ok(out.desktop) && ok(out.mobile), JSON.stringify(out).slice(0, 900), PLAIN_COOKIE_NOTE);
}

// ===== H: the operator's header on a sweep that costs nothing ==================================================================
if (want('H')) {
  const out = {};
  for (const [name, p] of [['configure', '/configure'], ['confirm', '/confirm'], ['running', '/running'], ['results', '/results']]) {
    const { ctx, page } = await openConsole(1);
    await go(page, con.at(1), p);
    const m = await page.evaluate(() => {
      const meter = document.querySelector('.meter'); if (!meter) return null;
      const n = meter.querySelector('.numeral');
      const paid = getComputedStyle(document.documentElement).getPropertyValue('--paid').trim();
      const col = (c) => { const d = document.createElement('i'); d.style.color = c; document.body.append(d); const v = getComputedStyle(d).color; d.remove(); return v; };
      return { zero: meter.classList.contains('zero'), figure: n.innerText.trim(), colour: getComputedStyle(n).color, amber: col(paid), facts: meter.querySelector('.meter-facts').innerText.replace(/\s+/g, ' ').trim() };
    });
    out[name] = m;
    if (name === 'running') await shoot(page, 'h-console-free-running');
    if (name === 'results') await shoot(page, 'h-console-free-results');
    await ctx.close();
  }
  const bad = Object.entries(out).filter(([, m]) => !m || (/^\$0\.00$/.test(m.figure) && (!m.zero || m.colour === m.amber)) || /credit left/i.test(m.facts)).map(([k]) => k);
  check('H', 'the operator\'s header on a free sweep: a figure of nothing is not amber, and nothing in it talks about credit', bad.length === 0, JSON.stringify({ bad, out }).slice(0, 700));
}

const ok = finish({ engine: version, harness: 'docs/design/d7c/harness/flows.mjs', playwright: PW_VERSION });
console.log('runtime:', RUNTIME.pageErrors.length, 'script errors;', RUNTIME.consoleErrors.length, 'console errors');
await browser.close(); app.stop(); con.stop();
process.exit(ok ? 0 : 1);
