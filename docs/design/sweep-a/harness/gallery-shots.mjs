// A2 evidence: photograph the component gallery (gallery.py writes it) at 1440 and 390, light and dark.
//   .venv/bin/python docs/design/sweep-a/harness/gallery.py && node docs/design/sweep-a/harness/gallery-shots.mjs
import { launch, ROOT, VIEWPORTS, sleep, fs, path } from '../../motion-d7b/harness/lib.mjs';
import { pathToFileURL } from 'url';

const dir = path.join(ROOT, 'output', 'design-A2', 'gallery');
const file = path.join(dir, 'gallery.html');
if (!fs.existsSync(file)) throw new Error('run gallery.py first: ' + file);
const browser = await launch();
if (!browser) process.exit(1);
for (const scheme of ['light', 'dark']) {
  for (const [vp, tag] of [['desktop', 'd'], ['mobile', 'm']]) {
    const v = VIEWPORTS[vp];
    const ctx = await browser.newContext({
      viewport: { width: v.width, height: v.height }, isMobile: v.isMobile, hasTouch: v.hasTouch,
      colorScheme: scheme, reducedMotion: 'no-preference', deviceScaleFactor: 1,
    });
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', (e) => errors.push(String(e)));
    await page.goto(pathToFileURL(file).href, { waitUntil: 'load' });
    await sleep(600);
    const out = path.join(dir, `gallery-${scheme}-${tag}.png`);
    await page.screenshot({ path: out, fullPage: true });
    console.log(out, errors.length ? 'PAGE ERRORS: ' + errors.join(' | ') : '');
    await ctx.close();
  }
}
await browser.close();
