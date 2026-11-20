// D7B: the shared regression contact sheets, from output/design-D7B/regression-before and regression-after.
//
//   node docs/design/motion-d7b/harness/make-regression-sheets.mjs
//
//   contact-sheet-regression-{desktop,mobile}.png    every state, as it is now (thumbnails), each with its verdict against the parent
//   contact-sheet-before-after-{desktop,mobile}.png  one screen per stage of the product: before | after | where they differ (nothing is red)
import { engines, OUT, mkdir, fs, path, sleep } from './lib.mjs';
import { diff, diffPicture } from './png.mjs';
import os from 'os';

const before = path.join(OUT, 'regression-before'), after = path.join(OUT, 'regression-after');
const all = fs.readdirSync(after).filter((f) => f.endsWith('.png')).sort();
const verdict = Object.fromEntries(all.map((f) => [f, fs.readFileSync(path.join(after, f)).equals(fs.readFileSync(path.join(before, f))) || diff(path.join(before, f), path.join(after, f)).same]));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'reg-'));
const browser = await engines.chromium.launch();
const shot = async (html, out, width) => {
  const f = path.join(tmp, 'sheet.html'); fs.writeFileSync(f, html);
  const page = await browser.newPage({ viewport: { width, height: 600 } });
  await page.goto('file://' + f); await page.waitForLoadState('load'); await sleep(300);
  await page.screenshot({ path: path.join(OUT, out), fullPage: true }); await page.close(); console.log(out);
};
const style = '<style>body{margin:0;background:#0b0f12;color:#cfd8dc;font:12px ui-monospace,monospace}.g{display:grid;gap:10px;padding:10px;align-items:start}figure{margin:0}img{display:block;width:100%;border:2px solid #2e7d5b}figcaption{padding:3px 0;font-size:11px;word-break:break-all}.bad img{border-color:#c0392b}h1{font:600 14px ui-monospace,monospace;padding:10px 10px 0;margin:0}</style>';

for (const [tag, label, cols, thumb] of [['d', 'desktop', 6, 232], ['m', 'mobile', 10, 136]]) {
  const files = all.filter((f) => f.endsWith(`-${tag}.png`));
  const same = files.filter((f) => verdict[f]).length;
  const cells = files.map((f) => `<figure class="${verdict[f] ? '' : 'bad'}"><img src="file://${path.join(after, f)}" style="max-height:${label === 'desktop' ? 220 : 300}px;object-fit:cover;object-position:top"><figcaption>${f.replace(`-${tag}.png`, '')}${verdict[f] ? '' : ' — DIFFERS'}</figcaption></figure>`).join('');
  await shot(`${style}<h1>At rest, ${label}: ${files.length} states, ${same} pixel-identical to the parent commit (green border). Top of each page shown.</h1><div class="g" style="grid-template-columns:repeat(${cols},${thumb}px)">${cells}</div>`, `contact-sheet-regression-${label}.png`, cols * (thumb + 10) + 10);
}

const STAGES = ['upload-empty', 'upload-manage-mixed', 'review-expanded', 'configure-paid', 'confirm-paid', 'confirm-over-multi', 'progress-paid-one-some', 'progress-paid-done', 'results', 'm-all-filters', 'm-19'];
for (const [tag, label, w, maxh] of [['d', 'desktop', 420, 340], ['m', 'mobile', 200, 440]]) {
  const rows = STAGES.filter((s) => fs.existsSync(path.join(after, `${s}-${tag}.png`))).map((s) => {
    const f = `${s}-${tag}.png`, dp = path.join(tmp, `diff-${f}`); diffPicture(path.join(before, f), path.join(after, f), dp);
    const cell = (src, cap) => `<figure class="${verdict[f] ? '' : 'bad'}"><img src="file://${src}" style="max-height:${maxh}px;object-fit:cover;object-position:top"><figcaption>${cap}</figcaption></figure>`;
    return cell(path.join(before, f), `${s}: before (parent commit)`) + cell(path.join(after, f), 'after (this commit)') + cell(dp, verdict[f] ? 'difference: none' : 'difference: red');
  }).join('');
  await shot(`${style}<h1>Before | after | difference, ${label}: one screen for each stage. The difference pictures are the after state with any differing pixel in red.</h1><div class="g" style="grid-template-columns:repeat(3,${w}px)">${rows}</div>`, `contact-sheet-before-after-${label}.png`, 3 * (w + 10) + 10);
}
await browser.close(); fs.rmSync(tmp, { recursive: true, force: true });
