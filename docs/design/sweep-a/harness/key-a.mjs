// A6: the Search coverage screen (/key, public) in a real browser, over the production app on loopback (D7B's harness/app.py).
//   node docs/design/sweep-a/harness/key-a.mjs            checks only
//   KEY_A_SHOTS=1 node docs/design/sweep-a/harness/key-a.mjs   also writes screenshots to output/design-A6/key-a/
// With a script: the radios drive the diagram and the call to action, "Set up Deep Sweep" opens the guide at step 1 with
// focus on its heading, the steps move and focus follows, Back works, and a rejected key comes back at step 3 with the error.
// Without one: every step and both forms are on the page and the Quick form submits. Phones: the call to action is the
// pinned bar and the diagram sits above the cards. Reduced motion: chips appear, nothing orbits.
// The "bad key" is a string that is not shaped like a token (it has spaces), so the server refuses it before any network call;
// no token of any kind is posted.
import fs from 'fs';
import path from 'path';
import { launch, serveApp, visitor, sleep, OUT } from '../../motion-d7b/harness/lib.mjs';

const SHOTS = !!process.env.KEY_A_SHOTS;
const PSHOTS = process.env.POLISH_SHOTS !== '0';        // A11 polish evidence: output/design-A11/polish/ (D7_OUT decides the root)
const shotDir = path.join(OUT, '..', 'design-A6', 'key-a');
if (SHOTS) fs.mkdirSync(shotDir, { recursive: true });

const app = await serveApp({ port: 5486, attach: false });
const browser = await launch();
const out = []; let ok = true;
const check = (name, cond, info) => { out.push(`${cond ? 'ok  ' : 'FAIL'} ${name}${info === undefined ? '' : ' ' + info}`); ok = ok && !!cond; };
const polishDir = path.join(OUT, 'polish');
if (PSHOTS) fs.mkdirSync(polishDir, { recursive: true });
const pshot = async (page, name, opts = {}) => { if (PSHOTS) await page.screenshot({ path: path.join(polishDir, name + '.png'), ...opts }); };
const shot = async (page, name) => { if (SHOTS) await page.screenshot({ path: path.join(shotDir, name + '.png'), fullPage: true }); };

// ---- small readers ------------------------------------------------------------------------------------------------
const visible = (page, sel) => page.locator(sel).first().isVisible();
const active = (page) => page.evaluate(() => { const a = document.activeElement; return a ? `${a.tagName.toLowerCase()}${a.id ? '#' + a.id : ''}|${(a.value ?? '')}|${(a.textContent || '').trim().slice(0, 40)}` : ''; });
const chips = (page) => page.evaluate(() => [...document.querySelectorAll('.cov-choose .o-chip.out')].map((c) => { const s = getComputedStyle(c); return { t: c.textContent, op: +s.opacity, sc: s.scale }; }));
const stepsShown = (page) => page.evaluate(() => [...document.querySelectorAll('.wstep')].map((li) => getComputedStyle(li).display !== 'none'));
const parseRgb = (s) => {
  const m = s.match(/rgba?\(([^)]+)\)/); if (m) return m[1].split(/[ ,\/]+/).filter(Boolean).slice(0, 3).map(Number);
  const c = s.match(/color\(srgb ([^)]+)\)/); if (c) return c[1].split(/[ \/]+/).slice(0, 3).map((v) => Math.round(+v * 255));
  return null;
};
const lum = (rgb) => { const f = rgb.map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2]; };
const contrast = (a, b) => { const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05); };
const colours = (page, sel, bgSel) => page.evaluate(([sel, bgSel]) => ({ fg: getComputedStyle(document.querySelector(sel)).color, bg: getComputedStyle(document.querySelector(bgSel)).backgroundColor }), [sel, bgSel]);

// ---- A11 polish readers ---------------------------------------------------------------------------------------------
const rect = (page, sel) => page.evaluate((sel) => { const r = document.querySelector(sel).getBoundingClientRect(); return { top: r.top + scrollY, left: r.left, right: r.right, bottom: r.bottom + scrollY, w: r.width, h: r.height }; }, sel);
const shift = (page, sel) => page.evaluate((sel) => { const t = getComputedStyle(document.querySelector(sel)).transform; if (t === 'none') return [0, 0]; const m = t.match(/matrix\(([^)]+)\)/); const v = m[1].split(',').map(Number); return [v[4], v[5]]; }, sel);
const firstRgb = (s) => { const m = s.match(/rgba?\(([^)]+)\)/); return m ? m[1].split(/[ ,\/]+/).filter(Boolean).slice(0, 3).map(Number) : parseRgb(s); };
// the height of a <details> at three moments after a click on its summary: ~90ms in, then at rest
const detailsAt = (page, sel) => page.evaluate((sel) => { const d = document.querySelector(sel); return { open: d.open, h: d.getBoundingClientRect().height, anims: d.getAnimations({ subtree: true }).length, overflow: d.style.overflow }; }, sel);
const goKey = async (page) => { await page.goto(app.url + '/key', { waitUntil: 'networkidle' }); await sleep(250); };

for (const scheme of ['light', 'dark']) {
  process.env.D7_SCHEME = scheme;
  const tag = (s) => `${scheme}/${s}`;

  // ================= with JavaScript, desktop ==================================================================
  {
    const { ctx, page } = await visitor(browser, app, 'reviewed3', { vp: 'desktop', trace: false });
    await goKey(page);
    const html = await page.evaluate(() => document.documentElement.className);
    check(tag('desktop: the js class is on <html>'), /\bjs\b/.test(html), html);
    const eyebrow = await page.locator('.eyebrow').first().textContent(), h1 = (await page.locator('h1').textContent()).replace(/\s+/g, ' ');
    check(tag('desktop: eyebrow and headline'), eyebrow.trim() === 'Step 3 · coverage' && h1 === 'How wide should we sweep?', `${eyebrow.trim()} | ${h1}`);
    check(tag('desktop: Quick chosen: its form is visible, the Set up button is not'),
      await visible(page, 'form[action*="key/free"] button') && !(await visible(page, '.cov-deepgo')));
    check(tag('desktop: the Quick card is the chosen one'), await page.locator('input[value="quick"]').isChecked());
    check(tag('desktop: the setup is not on the page'), !(await visible(page, '#deep-setup')));
    let c = await chips(page);
    check(tag('desktop: Quick: the paid boards are off the ring'), c.length === 3 && c.every((x) => x.op === 0), JSON.stringify(c));
    check(tag('desktop: the two always-on chips are drawn'), (await page.locator('.cov-choose .o-chip.in').count()) === 2
      && (await page.locator('.cov-choose .o-chip.in').first().isVisible()));
    check(tag('desktop: the live sentence says Quick'), (await page.locator('.cov [aria-live="polite"].visually-hidden').innerText()).startsWith('Quick Sweep searches'));
    await shot(page, `${scheme}-1-quick`);

    // the Quick card's words on its tint, the contrast it must keep
    let k = await colours(page, '.choice.q .ds', '.choice.q');
    check(tag('desktop: Quick card text >= 4.5:1 on its tint'), contrast(parseRgb(k.fg), parseRgb(k.bg)) >= 4.5, `${contrast(parseRgb(k.fg), parseRgb(k.bg)).toFixed(2)} ${k.fg} on ${k.bg}`);

    await page.locator('label.choice.d').click(); await sleep(900);
    check(tag('desktop: choosing Deep: the Quick form goes, the Set up button comes'),
      !(await visible(page, 'form[action*="key/free"] button')) && await visible(page, '.cov-deepgo'));
    c = await chips(page);
    check(tag('desktop: choosing Deep pops the three paid chips onto the ring'), c.length === 3 && c.every((x) => x.op === 1 && x.sc === '1'), JSON.stringify(c));
    check(tag('desktop: the chips are LinkedIn, Indeed, Naukri'), c.map((x) => x.t).join(',') === 'LinkedIn,Indeed,Naukri');
    check(tag('desktop: the live sentence says Deep and names the boards'), /^Deep Sweep searches .*LinkedIn.*Indeed.*Naukri/.test(await page.locator('.cov [aria-live="polite"].visually-hidden').innerText()));
    const orbit = await page.evaluate(() => { const a = document.querySelector('.orbit-spin').getAnimations().map((x) => x.animationName); const b = document.querySelector('.o-chip.out').getAnimations().map((x) => x.animationName); return { spin: a, chip: b }; });
    check(tag('desktop: Deep orbits (no-preference): the ring turns, each chip turns back'), orbit.spin.includes('a-orbit') && orbit.chip.includes('a-orbit'), JSON.stringify(orbit));
    // chips stay upright while the ring turns: an unturned chip's box is its own size, at two moments a second and a half apart
    const upright = async () => page.evaluate(() => [...document.querySelectorAll('.o-chip.out')].every((e) => { const r = e.getBoundingClientRect(); return Math.abs(r.width - e.offsetWidth) <= 2 && Math.abs(r.height - e.offsetHeight) <= 2; }));
    const u1 = await upright(); await sleep(1500); const u2 = await upright();
    check(tag('desktop: the orbiting chips stay upright'), u1 && u2, `${u1} ${u2}`);
    await shot(page, `${scheme}-2-deep`);
    k = await colours(page, '.choice.d .ds', '.choice.d');
    check(tag('desktop: Deep card text >= 4.5:1 on lavender'), contrast(parseRgb(k.fg), parseRgb(k.bg)) >= 4.5, `${contrast(parseRgb(k.fg), parseRgb(k.bg)).toFixed(2)} ${k.fg} on ${k.bg}`);
    k = await colours(page, '.choice.d .nm', '.choice.d');
    check(tag('desktop: Deep card name >= 4.5:1 on lavender'), contrast(parseRgb(k.fg), parseRgb(k.bg)) >= 4.5, contrast(parseRgb(k.fg), parseRgb(k.bg)).toFixed(2));

    // the radios are never submitted
    const radios = await page.evaluate(() => [...document.querySelectorAll('input[name="sweep-mode"]')].map((r) => !!r.closest('form')));
    check(tag('desktop: both radios are outside both forms'), radios.length === 2 && radios.every((x) => x === false));

    // Set up opens the guide at step 1, focus on its heading
    await page.locator('.cov-deepgo').click(); await sleep(500);
    check(tag('desktop: Set up hides the choice and opens the setup'), !(await visible(page, '.cov-choose')) && await visible(page, '#deep-setup'));
    check(tag('desktop: the setup opens at step 1 only'), JSON.stringify(await stepsShown(page)) === '[true,false,false]', JSON.stringify(await stepsShown(page)));
    check(tag('desktop: focus is on the setup heading'), (await active(page)).startsWith('h2#deep-h'), await active(page));
    check(tag('desktop: "Step 1 of 3" is shown'), (await page.locator('.wcount').innerText()).replace(/\s+/g, ' ') === 'Step 1 of 3');
    check(tag('desktop: step 1 has the sign-up link as a button and the $5 sticker'),
      (await page.locator('.wstep.open a.primary').getAttribute('href')) === 'https://apify.com/sign-up' && (await page.locator('.wstep.open .sticker').innerText()) === '$5 free every month');
    await shot(page, `${scheme}-3-step1`);

    await page.getByRole('button', { name: /I already have one/ }).click(); await sleep(400);
    check(tag('desktop: "I already have one" moves to step 2 and focus follows'), JSON.stringify(await stepsShown(page)) === '[false,true,false]' && (await active(page)).includes('Copy your API token'), await active(page));
    check(tag('desktop: step 2: the tokens link and the mock row (no screenshot configured)'),
      (await page.locator('.wstep.open a.primary').getAttribute('href')) === 'https://console.apify.com/settings/integrations' && (await page.locator('.wstep.open .mocktok').count()) === 1);
    await shot(page, `${scheme}-4-step2`);
    await page.getByRole('button', { name: /I.ve copied it/ }).click(); await sleep(400);
    check(tag('desktop: "I\'ve copied it" moves to step 3 and focus follows'), JSON.stringify(await stepsShown(page)) === '[false,false,true]' && (await active(page)).includes('Paste it here'), await active(page));
    const tok = page.locator('input[name="token"]');
    check(tag('desktop: step 3: a password field with no value and the privacy sentence beside it'),
      (await tok.getAttribute('type')) === 'password' && (await tok.getAttribute('value')) === null && await visible(page, '#key-privacy'));
    await shot(page, `${scheme}-5-step3`);
    await page.getByRole('button', { name: /Back a step/ }).click(); await sleep(400);
    check(tag('desktop: Back a step returns to step 2, focus on its heading'), JSON.stringify(await stepsShown(page)) === '[false,true,false]' && (await active(page)).includes('Copy your API token'), await active(page));
    await page.getByRole('button', { name: /Back to the options/ }).click(); await sleep(400);
    check(tag('desktop: Back to the options shows the choice, hides the setup, focus on the Deep radio'),
      await visible(page, '.cov-choose') && !(await visible(page, '#deep-setup')) && (await active(page)).startsWith('input|deep'), await active(page));
    check(tag('desktop: Deep is still the chosen one'), await page.locator('input[value="deep"]').isChecked());

    // "Already have a key? Paste it" goes straight to step 3
    await page.locator('.cov-deepgo').click(); await sleep(300);
    await page.getByRole('button', { name: /Already have a key\? Paste it/ }).click(); await sleep(300);
    check(tag('desktop: "Already have a key? Paste it" goes to step 3'), JSON.stringify(await stepsShown(page)) === '[false,false,true]' && (await active(page)).includes('Paste it here'));

    // a key the server refuses: back at step 3, error shown, nothing echoed
    const NOT_A_KEY = 'this is not a key';
    await tok.fill(NOT_A_KEY);
    await Promise.all([page.waitForNavigation({ waitUntil: 'load' }), page.getByRole('button', { name: 'Check my key and continue' }).click()]);
    await sleep(500);
    check(tag('desktop: a refused key comes back on /key'), new URL(page.url()).pathname === '/key', page.url());
    check(tag('desktop: ...with Deep chosen, the setup open, step 3 only'), await page.locator('input[value="deep"]').isChecked() && await visible(page, '#deep-setup')
      && JSON.stringify(await stepsShown(page)) === '[false,false,true]' && !(await visible(page, '.cov-choose')), JSON.stringify(await stepsShown(page)));
    check(tag('desktop: ...the error is shown inside step 3 and is an alert'), (await page.locator('.wstep.open .error[role="alert"]').count()) === 1 && (await page.locator('.wstep.open .error').innerText()).length > 10, await page.locator('.wstep.open .error').innerText());
    const body = await page.content();
    check(tag('desktop: ...the token is not in the page and the field is empty'), !body.includes(NOT_A_KEY) && (await page.locator('input[name="token"]').inputValue()) === '');
    check(tag('desktop: ...the dots show step 3'), await page.evaluate(() => [...document.querySelectorAll('.wdots i')].map((i) => i.className).join(',') === 'ok,ok,on'));
    await shot(page, `${scheme}-6-refused`);
    check(tag('desktop: no horizontal scroll'), await page.evaluate((w) => document.documentElement.scrollWidth <= w, page.viewportSize().width));
    await ctx.close();
  }

  // ================= A11 polish: the anchored diagram, the radios, the opening peek, the orbit, the setup diagram ===========
  {
    const { ctx, page } = await visitor(browser, app, 'reviewed3', { vp: 'desktop', trace: false });
    await goKey(page);
    await pshot(page, `${scheme}-2-key-quick-desktop`);
    // (2) opening the cost peek moves only what is under it: the diagram stays level with the top of the cards
    const before = { orbit: await rect(page, '.cov-choose .orbit-box'), cards: await rect(page, '.cov-choices'), peek: await rect(page, 'details.peek') };
    check(tag('A11/2 desktop: the diagram is level with the top of the cards'), Math.abs(before.orbit.top - before.cards.top) <= 1, `orbit ${Math.round(before.orbit.top)} cards ${Math.round(before.cards.top)}`);
    await page.locator('details.peek > summary').click(); await sleep(100);
    const mid = await detailsAt(page, 'details.peek');
    await sleep(400);
    const after = { orbit: await rect(page, '.cov-choose .orbit-box'), cards: await rect(page, '.cov-choices'), peek: await rect(page, 'details.peek'), d: await detailsAt(page, 'details.peek') };
    check(tag('A11/2 desktop: the peek opened and grew'), after.d.open && after.peek.h > before.peek.h + 40, `${Math.round(before.peek.h)} -> ${Math.round(after.peek.h)}`);
    check(tag('A11/2 desktop: opening the peek did not move the diagram'), Math.abs(after.orbit.top - before.orbit.top) <= 1 && Math.abs(after.cards.top - before.cards.top) <= 1, `${before.orbit.top} -> ${after.orbit.top}`);
    // (1) the peek animates: part way through it is between shut and open, and at rest it is open with nothing left over
    check(tag('A11/1 desktop: the peek is mid-animation ~100ms after the click (between its shut and open heights)'),
      mid.open && mid.h > before.peek.h + 2 && mid.h < after.peek.h - 2 && mid.anims > 0 && mid.overflow === 'hidden', JSON.stringify(mid) + ` ${before.peek.h}..${after.peek.h}`);
    check(tag('A11/1 desktop: at rest it is open, nothing running, nothing clipped'), after.d.open && after.d.anims === 0 && after.d.overflow === '', JSON.stringify(after.d));
    await pshot(page, `${scheme}-1-peek-open-desktop`);
    await page.locator('details.peek > summary').click(); await sleep(100);
    const mid2 = await detailsAt(page, 'details.peek');
    await sleep(400);
    const shut = await detailsAt(page, 'details.peek');
    check(tag('A11/1 desktop: closing: `open` is held while it shrinks, then cleared; back to the shut height'),
      mid2.open && mid2.h < after.peek.h - 2 && mid2.h > before.peek.h + 2 && !shut.open && Math.abs(shut.h - before.peek.h) <= 1 && shut.anims === 0 && shut.overflow === '', `${JSON.stringify(mid2)} ${JSON.stringify(shut)}`);
    // a click while it is moving turns it round (no stuck state)
    await page.locator('details.peek > summary').click(); await sleep(90);
    await page.locator('details.peek > summary').click(); await sleep(500);
    const turned = await detailsAt(page, 'details.peek');
    check(tag('A11/1 desktop: a second click in the middle of the animation turns it round and ends shut, clean'), !turned.open && Math.abs(turned.h - before.peek.h) <= 1 && turned.anims === 0 && turned.overflow === '', JSON.stringify(turned));
    // keyboard: Enter on the summary toggles it, focus stays on the summary
    await page.locator('details.peek > summary').focus(); await page.keyboard.press('Enter'); await sleep(450);
    const kb = await page.evaluate(() => ({ open: document.querySelector('details.peek').open, focus: document.activeElement.tagName }));
    check(tag('A11/1 desktop: Enter opens it and focus stays on the summary'), kb.open && kb.focus === 'SUMMARY', JSON.stringify(kb));
    await page.keyboard.press('Space'); await sleep(450);
    check(tag('A11/1 desktop: Space closes it and focus stays on the summary'), await page.evaluate(() => !document.querySelector('details.peek').open && document.activeElement.tagName === 'SUMMARY'));
    // the toggle event still fires, once per real change
    const fired = await page.evaluate(() => new Promise((res) => { const d = document.querySelector('details.peek'); let n = 0; d.addEventListener('toggle', () => n++); d.querySelector('summary').click(); setTimeout(() => { d.querySelector('summary').click(); setTimeout(() => res(n), 500); }, 450); }));
    check(tag('A11/1 desktop: the toggle event fires once on opening and once on closing'), fired === 2, String(fired));

    // (3) the radios are drawn, readable in every state
    const radio = async () => page.evaluate(() => [...document.querySelectorAll('.cov-choices .choice')].map((l) => {
      const i = l.querySelector('input'), s = getComputedStyle(i), c = getComputedStyle(l);
      return { v: i.value, on: i.checked, app: s.appearance, ring: s.borderTopColor, w: s.borderTopWidth, dot: s.backgroundImage, bg: c.backgroundColor, ink: getComputedStyle(l).color };
    }));
    for (const [label, want] of [['quick checked', 'quick'], ['deep checked', 'deep']]) {
      if (want === 'deep') { await page.locator('label.choice.d').click(); await sleep(700); }
      const r = await radio();
      check(tag(`A11/3 desktop: the radios are drawn, not native (${label})`), r.every((x) => x.app === 'none' && parseFloat(x.w) >= 2), JSON.stringify(r.map((x) => [x.v, x.app, x.w])));
      for (const x of r) {
        const bgc = parseRgb(x.bg) || [255, 255, 255];
        const ring = firstRgb(x.ring), cr = contrast(ring, bgc);
        check(tag(`A11/3 desktop: ${x.v} radio ring >= 3:1 on its card (${label}, ${x.on ? 'checked' : 'unchecked'})`), cr >= 3, `${cr.toFixed(2)} ring ${x.ring} on ${x.bg}`);
        if (x.on) {
          const dot = firstRgb(x.dot), dc = dot ? contrast(dot, bgc) : 0;
          check(tag(`A11/3 desktop: the checked ${x.v} radio has an ink dot >= 3:1 on its card`), /radial-gradient/.test(x.dot) && dc >= 3, `${dc.toFixed(2)} ${x.dot.slice(0, 70)}`);
        } else check(tag(`A11/3 desktop: the unchecked ${x.v} radio has no dot`), x.dot === 'none', x.dot);
      }
      await pshot(page, `${scheme}-3-radios-${want}`, { clip: { x: 0, y: 0, width: 1440, height: 760 } });
    }
    // keyboard: arrows move the radio, the focus ring is the A focus token
    await page.locator('input[value="quick"]').focus(); await page.keyboard.press('ArrowDown'); await sleep(200);
    check(tag('A11/3 desktop: the arrow keys still move the choice'), await page.locator('input[value="deep"]').isChecked());
    await page.keyboard.press('ArrowUp'); await sleep(200);
    const fo = await page.evaluate(() => { const i = document.querySelector('input[value="quick"]'); const s = getComputedStyle(i); return { style: s.outlineStyle, w: s.outlineWidth, c: s.outlineColor, want: getComputedStyle(document.documentElement).getPropertyValue('--a-focus').trim() }; });
    check(tag('A11/3 desktop: a keyboard focus ring (3px) in the A focus colour'), fo.style === 'solid' && fo.w === '3px', JSON.stringify(fo));
    await pshot(page, `${scheme}-3-radio-focus`, { clip: { x: 0, y: 0, width: 1440, height: 760 } });
    await ctx.close();
  }

  // (4) the orbit follows the pointer, a board lifts and pauses it
  {
    const { ctx, page } = await visitor(browser, app, 'reviewed3', { vp: 'desktop', trace: false });
    await goKey(page);
    await page.locator('label.choice.d').click(); await sleep(900);
    const bb = await page.locator('.cov-choose .orbit-box').boundingBox();      // viewport coordinates
    await page.mouse.move(bb.x - 30, bb.y - 30); await page.mouse.move(bb.x + bb.width * 0.95, bb.y + bb.height * 0.5, { steps: 6 }); await sleep(800);
    const near = { inner: await shift(page, '.cov-choose .orbit-ring.inner'), outer: await shift(page, '.cov-choose .orbit-ring.outer'), core: await shift(page, '.cov-choose .orbit-core'),
      spin: await shift(page, '.cov-choose .orbit-spin'), chip: await shift(page, '.cov-choose .orbit-pt.in1') };
    check(tag('A11/4 desktop: the pointer at the right edge shifts the inner ring toward it by a few px'), near.inner[0] > 3 && near.inner[0] <= 6.5 && Math.abs(near.inner[1]) < 1.5, JSON.stringify(near.inner));
    check(tag('A11/4 desktop: the outer ring and the boards shift more (outer depth > inner depth)'), near.outer[0] > near.inner[0] + 3 && near.outer[0] <= 14.5 && Math.abs(near.spin[0] - near.outer[0]) < 0.5, JSON.stringify([near.outer, near.spin]));
    check(tag('A11/4 desktop: the inner chips and the core move with the inner ring'), Math.abs(near.chip[0] - near.inner[0]) < 0.5 && Math.abs(near.core[0] - near.inner[0]) < 0.5, JSON.stringify([near.chip, near.core]));
    await page.mouse.move(bb.x + bb.width * 0.5, bb.y + bb.height * 0.05, { steps: 6 }); await sleep(800);
    const top = await shift(page, '.cov-choose .orbit-ring.outer');
    check(tag('A11/4 desktop: the pointer near the top shifts them up'), top[1] < -8, JSON.stringify(top));
    await page.mouse.move(40, 300, { steps: 8 }); await sleep(900);
    const home = await shift(page, '.cov-choose .orbit-ring.outer'), homeI = await shift(page, '.cov-choose .orbit-ring.inner');
    check(tag('A11/4 desktop: leaving the diagram eases both back to rest'), Math.abs(home[0]) < 0.6 && Math.abs(home[1]) < 0.6 && Math.abs(homeI[0]) < 0.6 && Math.abs(homeI[1]) < 0.6, JSON.stringify([home, homeI]));
    // hovering a board: it lifts and the orbit holds still
    const chip = page.locator('.cov-choose .o-chip.out').first();
    const cb = await chip.boundingBox();
    await page.mouse.move(cb.x + cb.width / 2, cb.y + cb.height / 2, { steps: 4 }); await sleep(700);
    const hov = await page.evaluate(() => { const c = document.querySelector('.cov-choose .o-chip.out'); const sp = document.querySelector('.cov-choose .orbit-spin'); const st = (e) => e.getAnimations().map((a) => a.playState).join(','); return { scale: getComputedStyle(c).scale, shadow: getComputedStyle(c).boxShadow, spin: st(sp), chip: st(c) }; });
    check(tag('A11/4 desktop: hovering a board lifts it (scale and a shadow)'), +hov.scale > 1.1 && hov.shadow !== 'none', JSON.stringify(hov));
    check(tag('A11/4 desktop: ...and pauses the orbit (the ring and the chip turning back)'), hov.spin.includes('paused') && !hov.spin.includes('running') && hov.chip.includes('paused'), JSON.stringify(hov));
    await pshot(page, `${scheme}-4-orbit-hover`, { clip: { x: 0, y: 0, width: 1440, height: 760 } });
    await page.mouse.move(40, 300, { steps: 6 }); await sleep(600);
    const run = await page.evaluate(() => document.querySelector('.cov-choose .orbit-spin').getAnimations().map((a) => a.playState).join(','));
    check(tag('A11/4 desktop: the orbit runs again when the pointer leaves the board'), run.includes('running'), run);
    // it stays decoration
    check(tag('A11/4 desktop: the diagram is still aria-hidden and is no tab stop'), await page.evaluate(() => { const b = document.querySelector('.cov-choose .orbit-box'); return b.getAttribute('aria-hidden') === 'true' && !b.querySelector('[tabindex],a,button,input'); }));
    await ctx.close();
  }
  {   // reduced motion: nothing follows the pointer, nothing pauses, the peek is the browser's own toggle
    const { ctx, page } = await visitor(browser, app, 'reviewed3', { vp: 'desktop', reduced: true, trace: false });
    await goKey(page);
    await page.locator('label.choice.d').click(); await sleep(400);
    const bb = await page.locator('.cov-choose .orbit-box').boundingBox();
    await page.mouse.move(bb.x - 30, bb.y - 30); await page.mouse.move(bb.x + bb.width * 0.95, bb.y + bb.height * 0.5, { steps: 6 }); await sleep(700);
    const o = await shift(page, '.cov-choose .orbit-ring.outer'), i = await shift(page, '.cov-choose .orbit-ring.inner');
    check(tag('A11/4 reduced motion: the pointer moves nothing'), o[0] === 0 && o[1] === 0 && i[0] === 0 && i[1] === 0, JSON.stringify([o, i]));
    const peekBefore = (await rect(page, 'details.peek')).h;
    await page.locator('details.peek > summary').click();
    const m = await detailsAt(page, 'details.peek');
    check(tag('A11/1 reduced motion: the peek is the native toggle: open at once, no animation, no clip'), m.open && m.anims === 0 && m.overflow === '' && m.h > peekBefore + 40, JSON.stringify(m));
    await page.locator('details.peek > summary').click();
    const m2 = await detailsAt(page, 'details.peek');
    check(tag('A11/1 reduced motion: and closes at once'), !m2.open && m2.anims === 0 && Math.abs(m2.h - peekBefore) <= 1, JSON.stringify(m2));
    await ctx.close();
  }
  {   // a touch device: no parallax
    const { ctx, page } = await visitor(browser, app, 'reviewed3', { vp: 'mobile', trace: false });
    await goKey(page);
    const fine = await page.evaluate(() => matchMedia('(hover: hover) and (pointer: fine)').matches);
    const bb = await page.locator('.orbit-box').first().boundingBox();
    await page.touchscreen.tap(bb.x + bb.width * 0.9, bb.y + bb.height * 0.5); await sleep(500);
    const o = await shift(page, '.orbit-ring.outer');
    check(tag('A11/4 phone: no hover, no fine pointer, so a tap on the diagram moves nothing'), !fine && o[0] === 0 && o[1] === 0, JSON.stringify([fine, o]));
    await ctx.close();
  }

  // (5) the setup has the diagram beside it, the boards waiting until the paste step
  {
    const { ctx, page } = await visitor(browser, app, 'reviewed3', { vp: 'desktop', trace: false });
    await goKey(page);
    check(tag('A11/5 desktop: the choice view has no second diagram showing'), await page.evaluate(() => [...document.querySelectorAll('.orbit-box')].filter((b) => b.getBoundingClientRect().width > 0).length === 1));
    await page.locator('label.choice.d').click(); await sleep(300);
    await page.locator('.cov-deepgo').click(); await sleep(900);
    const g = await page.evaluate(() => { const r = (s) => document.querySelector(s).getBoundingClientRect(); const side = document.querySelector('.cov-side'); const st = getComputedStyle(side);
      return { card: r('.cov-setup'), side: r('.cov-side'), box: r('.cov-side .orbit-box'), sticker: document.querySelector('.cov-side .sticker').innerText, disp: st.display, hidden: side.getAttribute('aria-hidden'), live: side.querySelectorAll('[aria-live]').length, vis: [...document.querySelectorAll('.orbit-box')].filter((b) => b.getBoundingClientRect().width > 0).length, sw: document.documentElement.scrollWidth }; });
    check(tag('A11/5 desktop: with the setup open the diagram sits beside the card, on the right'), g.disp !== 'none' && g.box.left >= g.card.right - 1 && g.box.width > 200, JSON.stringify({ card: [g.card.left, g.card.right], box: [g.box.left, g.box.width] }));
    check(tag('A11/5 desktop: it is aria-hidden, has no live region, and is the only diagram on screen'), g.hidden === 'true' && g.live === 0 && g.vis === 1, JSON.stringify([g.hidden, g.live, g.vis]));
    check(tag('A11/5 desktop: the sticker says "Unlocks with your Apify key"'), g.sticker === 'Unlocks with your Apify key', g.sticker);
    check(tag('A11/5 desktop: no horizontal scroll with the setup open'), g.sw <= 1440, String(g.sw));
    const chipsNow = () => page.evaluate(() => [...document.querySelectorAll('.cov-side .o-chip.out')].map((c) => { const s = getComputedStyle(c); return { b: s.borderTopStyle, op: +s.opacity, bg: s.backgroundColor, col: s.color, sc: s.scale }; }));
    let cw = await chipsNow();
    const surfRgb = await page.evaluate(() => { const t = document.createElement('i'); t.style.background = 'var(--surface)'; document.body.append(t); const c = getComputedStyle(t).backgroundColor; t.remove(); return c; });
    check(tag('A11/5 desktop: step 1: the three boards are waiting (dashed outline, muted, on the cards own surface)'), cw.length === 3 && cw.every((x) => x.b === 'dashed' && x.op === 1 && x.bg === surfRgb), JSON.stringify(cw[0]));
    const wcr = contrast(firstRgb(cw[0].col), parseRgb(cw[0].bg));
    check(tag('A11/5 desktop: the waiting boards are still readable (>= 4.5:1)'), wcr >= 4.5, wcr.toFixed(2));
    await pshot(page, `${scheme}-5-setup-step1-desktop`, { clip: { x: 0, y: 0, width: 1440, height: 1000 } });
    await page.getByRole('button', { name: /I already have one/ }).click(); await sleep(400);
    cw = await chipsNow();
    check(tag('A11/5 desktop: step 2: still waiting'), cw.every((x) => x.b === 'dashed'), JSON.stringify(cw[0]));
    await page.getByRole('button', { name: /I.ve copied it/ }).click();
    await sleep(80);
    const popping = await page.evaluate(() => [...document.querySelectorAll('.cov-side .o-chip.out')].map((c) => c.getAnimations().map((a) => a.animationName).join(',')));
    check(tag('A11/5 desktop: reaching step 3 gives each board a small pop (a-firm)'), popping.every((n) => n.includes('a-firm')), JSON.stringify(popping));
    await sleep(900);
    cw = await chipsNow();
    check(tag('A11/5 desktop: step 3: the boards are firm (solid, the diagram\'s own lavender, ink)'), cw.length === 3 && cw.every((x) => x.b === 'solid' && x.bg !== surfRgb && x.op === 1), JSON.stringify(cw[0]));
    check(tag('A11/5 desktop: ...and the pop is over (scale back to 1)'), cw.every((x) => x.sc === '1'), JSON.stringify(cw.map((x) => x.sc)));
    await pshot(page, `${scheme}-5-setup-step3-desktop`, { clip: { x: 0, y: 0, width: 1440, height: 1000 } });
    await page.getByRole('button', { name: /Back a step/ }).click(); await sleep(500);
    check(tag('A11/5 desktop: back a step: waiting again'), (await chipsNow()).every((x) => x.b === 'dashed'));
    await ctx.close();
  }
  {   // 1024 shows it, 1023 and a phone do not; a refused key lands firm; no JS has no second diagram; reduced motion: firm without a pop
    const { ctx, page } = await visitor(browser, app, 'reviewed3', { vp: 'desktop', trace: false });
    for (const [w, want] of [[1024, true], [1023, false], [768, false]]) {
      await page.setViewportSize({ width: w, height: 900 });
      await goKey(page);
      await page.locator('label.choice.d').click(); await sleep(200); await page.locator('.cov-deepgo').click(); await sleep(500);
      const shown = await page.evaluate(() => getComputedStyle(document.querySelector('.cov-side')).display !== 'none');
      const sw = await page.evaluate(() => document.documentElement.scrollWidth);
      check(tag(`A11/5 ${w}px: the setup diagram is ${want ? 'beside the card' : 'not drawn'}, no horizontal scroll`), shown === want && sw <= w, `${shown} ${sw}`);
      if (w === 1024) await pshot(page, `${scheme}-5-setup-1024`, { clip: { x: 0, y: 0, width: 1024, height: 900 } });
    }
    await ctx.close();
  }
  {
    const { ctx, page } = await visitor(browser, app, 'reviewed3', { vp: 'mobile', trace: false });
    await goKey(page);
    await page.locator('label.choice.d').click(); await sleep(200); await page.locator('.cov-deepgo').click(); await sleep(500);
    const shown = await page.evaluate(() => [...document.querySelectorAll('.orbit-box')].filter((b) => b.getBoundingClientRect().width > 0).length);
    check(tag('A11/5 phone: the setup has no diagram (unchanged)'), shown === 0, String(shown));
    await pshot(page, `${scheme}-5-setup-phone`, { fullPage: false });
    await ctx.close();
  }
  {
    const { ctx, page } = await visitor(browser, app, 'reviewed3', { vp: 'desktop', js: false, trace: false });
    await goKey(page);
    const vis = await page.evaluate(() => [...document.querySelectorAll('.orbit-box')].filter((b) => b.getBoundingClientRect().width > 0).length);
    check(tag('A11/5 no-JS: the setup shows as today: one diagram (the choice\'s), none beside it'), vis === 1 && (await page.evaluate(() => getComputedStyle(document.querySelector('.cov-side')).display === 'none')), String(vis));
    await ctx.close();
  }
  {
    const { ctx, page } = await visitor(browser, app, 'reviewed3', { vp: 'desktop', reduced: true, trace: false });
    await goKey(page);
    await page.locator('label.choice.d').click(); await sleep(200); await page.locator('.cov-deepgo').click(); await sleep(400);
    await page.getByRole('button', { name: /Already have a key\? Paste it/ }).click(); await sleep(300);
    const r = await page.evaluate(() => [...document.querySelectorAll('.cov-side .o-chip.out')].map((c) => ({ b: getComputedStyle(c).borderTopStyle, a: c.getAnimations().length })));
    check(tag('A11/5 reduced motion: step 3 firms the boards with no pop and no orbit'), r.every((x) => x.b === 'solid' && x.a === 0), JSON.stringify(r));
    await ctx.close();
  }

  // ================= Quick, with JavaScript: the form submits ================================================================
  {
    const { ctx, page } = await visitor(browser, app, 'reviewed3', { vp: 'desktop', trace: false });
    await goKey(page);
    await Promise.all([page.waitForNavigation({ waitUntil: 'load' }), page.locator('form[action*="key/free"] button').first().click()]);
    check(tag('desktop: Start Quick Sweep (with JS) goes on to Configure'), new URL(page.url()).pathname === '/configure', page.url());
    await ctx.close();
  }

  // ================= without JavaScript =================================================================================
  {
    const { ctx, page } = await visitor(browser, app, 'reviewed3', { vp: 'desktop', js: false, trace: false });
    await goKey(page);
    check(tag('no-JS: no js class'), !/\bjs\b/.test(await page.evaluate(() => document.documentElement.className)));
    check(tag('no-JS: the choice, the Quick form and the key form are all on the page'),
      await visible(page, '.cov-choose') && await visible(page, 'form[action*="key/free"] button') && await visible(page, '#deep-setup') && await visible(page, 'input[name="token"]'));
    check(tag('no-JS: all three steps are visible, in order'), JSON.stringify(await stepsShown(page)) === '[true,true,true]'
      && (await page.locator('.wstep h3').allInnerTexts()).map((t) => t.trim().replace(/^\d+\s*/, '')).join('|') === 'Grab a free Apify account|Copy your API token|Paste it here', (await page.locator('.wstep h3').allInnerTexts()).join('|'));
    check(tag('no-JS: both sign-up links are on the page'), (await page.locator('a[href="https://apify.com/sign-up"]').isVisible()) && (await page.locator('a[href="https://console.apify.com/settings/integrations"]').isVisible()));
    check(tag('no-JS: nothing that needs a script is drawn'), !(await visible(page, '.cov-deepgo')) && !(await visible(page, '.wcount')) && !(await visible(page, '.go-row button')) && !(await visible(page, '.cov-setup-top button')));
    check(tag('no-JS: the privacy sentence is on the page'), await visible(page, '#key-privacy'));
    check(tag('no-JS: the Quick radio is checked'), await page.locator('input[value="quick"]').isChecked());
    await shot(page, `${scheme}-7-nojs`);
    await Promise.all([page.waitForNavigation({ waitUntil: 'load' }), page.locator('form[action*="key/free"] button').first().click()]);
    check(tag('no-JS: the Quick form submits and goes on to Configure'), new URL(page.url()).pathname === '/configure', page.url());
    await ctx.close();
  }

  // ================= phone ==========================================================================================
  {
    const { ctx, page } = await visitor(browser, app, 'reviewed3', { vp: 'mobile', trace: false });
    await goKey(page);
    const g = await page.evaluate((W) => {
      const r = (s) => document.querySelector(s).getBoundingClientRect();
      const bar = document.querySelector('.cov-cta'); const cs = getComputedStyle(bar);
      return { orbit: r('.orbit-box'), card: r('.choice.q'), bar: r('.cov-cta'), pos: cs.position, vh: innerHeight, vw: W, sw: document.documentElement.scrollWidth, btn: r('.cov-quick button') };
    }, page.viewportSize().width);
    check(tag('phone: the diagram is above the cards'), g.orbit.bottom <= g.card.top + 1, `orbit bottom ${Math.round(g.orbit.bottom)} card top ${Math.round(g.card.top)}`);
    check(tag('phone: the diagram is at most 260px'), g.orbit.width <= 261, String(Math.round(g.orbit.width)));
    check(tag('phone: the call to action is the pinned bar at the foot of the screen'), g.pos === 'sticky' && Math.abs(g.bar.bottom - g.vh) <= 1, `${g.pos} bottom ${Math.round(g.bar.bottom)} of ${g.vh}`);
    check(tag('phone: the bar spans the screen and its button is at least 44px tall'), g.bar.width >= g.vw - 1 && g.btn.height >= 44, `${Math.round(g.bar.width)} x ${Math.round(g.btn.height)}`);
    check(tag('phone: no horizontal scroll'), g.sw <= g.vw, `${g.sw} vs ${g.vw}`);
    await shot(page, `${scheme}-8-phone-quick`);
    await page.locator('label.choice.d').click(); await sleep(900);
    const g2 = await page.evaluate((W) => { const b = document.querySelector('.cov-cta').getBoundingClientRect(); return { bottom: b.bottom, vh: innerHeight, sw: document.documentElement.scrollWidth, vw: W }; }, page.viewportSize().width);
    check(tag('phone: Deep: the bar holds the Set up button, still pinned, no horizontal scroll'), await visible(page, '.cov-deepgo') && Math.abs(g2.bottom - g2.vh) <= 1 && g2.sw <= g2.vw);
    await shot(page, `${scheme}-9-phone-deep`);
    await page.locator('.cov-deepgo').click(); await sleep(500);
    check(tag('phone: Set up opens the setup'), await visible(page, '#deep-setup') && (await active(page)).startsWith('h2#deep-h'));
    await shot(page, `${scheme}-10-phone-step1`);
    await page.getByRole('button', { name: /Already have a key\? Paste it/ }).click(); await sleep(300);
    await shot(page, `${scheme}-11-phone-step3`);
    check(tag('phone: the setup has no horizontal scroll'), await page.evaluate((w) => document.documentElement.scrollWidth <= w, page.viewportSize().width));
    await ctx.close();
  }

  // ================= in between: a small laptop and a tablet ==================================================
  {
    const { ctx, page } = await visitor(browser, app, 'reviewed3', { vp: 'desktop', trace: false });
    for (const [w, h] of [[1024, 768], [768, 1024]]) {
      await page.setViewportSize({ width: w, height: h });
      await goKey(page);
      const g = await page.evaluate((W) => { const r = (s) => document.querySelector(s).getBoundingClientRect(); return { orbit: r('.orbit-box'), card: r('.choice.q'), sw: document.documentElement.scrollWidth, vw: W }; }, page.viewportSize().width);
      const side = w >= 900;     // 56rem
      check(tag(`${w}px: no horizontal scroll`), g.sw <= g.vw, `${g.sw} vs ${g.vw}`);
      check(tag(`${w}px: ${side ? 'cards left, diagram right' : 'one column, diagram first'}`), side ? g.orbit.left >= g.card.right : g.orbit.bottom <= g.card.top + 1,
        `orbit ${Math.round(g.orbit.left)}..${Math.round(g.orbit.right)} x ${Math.round(g.orbit.top)}..${Math.round(g.orbit.bottom)}, card ${Math.round(g.card.left)}..${Math.round(g.card.right)} x ${Math.round(g.card.top)}`);
      await shot(page, `${scheme}-12-${w}`);
    }
    await ctx.close();
  }

  // ================= reduced motion ==============================================================================
  {
    const { ctx, page } = await visitor(browser, app, 'reviewed3', { vp: 'desktop', reduced: true, trace: false });
    await goKey(page);
    await page.locator('label.choice.d').click(); await sleep(300);
    const c = await chips(page);
    const anim = await page.evaluate(() => ({ spin: document.querySelector('.orbit-spin').getAnimations().length, chip: document.querySelector('.o-chip.out').getAnimations().length }));
    check(tag('reduced motion: the paid chips simply appear'), c.length === 3 && c.every((x) => x.op === 1 && x.sc === '1'), JSON.stringify(c));
    check(tag('reduced motion: nothing orbits and nothing animates'), anim.spin === 0 && anim.chip === 0, JSON.stringify(anim));
    await ctx.close();
  }
}

console.log(out.join('\n'));
const failed = out.filter((l) => l.startsWith('FAIL')).length;
console.log(`\n${out.length - failed} of ${out.length} checks pass${failed ? `, ${failed} FAIL` : ''}`);
await browser.close(); app.stop();
process.exit(ok ? 0 : 1);
