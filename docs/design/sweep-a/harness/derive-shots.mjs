// A4 evidence: photograph derive-pages.py's pages, light and dark, 1440 and 390.  node docs/design/sweep-a/harness/derive-shots.mjs
import { launch, ROOT, fs, path } from '../../motion-d7b/harness/lib.mjs';
import { pathToFileURL } from 'url';
const dir = path.join(ROOT, 'output', 'design-A4', 'derive');
const browser = await launch();
for (const name of ['working', 'waiting', 'failed']) for (const scheme of ['light', 'dark']) for (const [tag, w, h] of [['d', 1440, 900], ['m', 390, 844]]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme, reducedMotion: 'reduce' });
  const page = await ctx.newPage();
  await page.goto(pathToFileURL(path.join(dir, `derive-${name}.html`)).href, { waitUntil: 'load' }); await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(dir, `derive-${name}-${scheme}-${tag}.png`), fullPage: true });
  await ctx.close();
}
await browser.close(); console.log('shots in', dir);
