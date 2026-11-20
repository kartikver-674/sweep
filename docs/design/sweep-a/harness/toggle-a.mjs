// A1: the theme switch in a real browser — system default, click, remembered across a reload, keyboard, back to system.
//   node docs/design/sweep-a/harness/toggle-a.mjs
import { launch, serveApp, visitor, sleep } from '../../motion-d7b/harness/lib.mjs';
const app = await serveApp({ port: 5477, attach: false });
const browser = await launch();
const out = []; let ok = true;
const check = (name, cond, info) => { out.push(`${cond ? 'ok  ' : 'FAIL'} ${name} ${info ?? ''}`); ok = ok && cond; };
for (const scheme of ['light', 'dark']) {
  process.env.D7_SCHEME = scheme;
  for (const vp of ['desktop', 'mobile']) {
    const { ctx, page } = await visitor(browser, app, 'fresh', { vp, trace: false });
    await page.goto(app.url + '/', { waitUntil: 'networkidle' }); await sleep(400);
    const st = () => page.evaluate(() => ({ attr: document.documentElement.getAttribute('data-theme'), cs: getComputedStyle(document.documentElement).colorScheme,
      bg: getComputedStyle(document.body).backgroundColor, pressed: document.querySelector('[data-theme-toggle]').getAttribute('aria-pressed'),
      stored: localStorage.getItem('sweep-theme'), box: (() => { const r = document.querySelector('[data-theme-toggle]').getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; })() }));
    const other = scheme === 'dark' ? 'light' : 'dark';
    let s = await st();
    check(`${scheme}/${vp} starts on the system theme`, s.attr === null && s.cs === scheme && s.pressed === String(scheme === 'dark'), JSON.stringify(s));
    check(`${scheme}/${vp} target is at least 44x44`, s.box[0] >= 44 && s.box[1] >= 44, JSON.stringify(s.box));
    await page.click('[data-theme-toggle]'); await sleep(200); s = await st();
    check(`${scheme}/${vp} click switches to ${other} and remembers it`, s.attr === other && s.cs === other && s.stored === other, JSON.stringify(s));
    await page.reload({ waitUntil: 'networkidle' }); await sleep(300); s = await st();
    check(`${scheme}/${vp} reload keeps ${other}`, s.attr === other && s.cs === other, JSON.stringify(s));
    await page.focus('[data-theme-toggle]'); await page.keyboard.press('Enter'); await sleep(200); s = await st();
    check(`${scheme}/${vp} Enter goes back to the system theme and forgets the choice`, s.attr === null && s.cs === scheme && s.stored === null, JSON.stringify(s));
    await ctx.close();
  }
}
console.log(out.join('\n')); await browser.close(); app.stop();  // stop the app.py it spawned, or it holds the port
process.exit(ok ? 0 : 1);
