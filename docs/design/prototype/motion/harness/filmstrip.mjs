// D7A: a contact sheet of real frames cut from a recording.
//
//   node harness/filmstrip.mjs <clip> <fromMs> <toMs> <out.png> [--cols 4] [--scale 0.5] [--crop w:h:x:y] [--every 1]
//
// Frames are decoded from the WebM itself at its native 25 fps (40 ms apart) with Playwright's own ffmpeg, and
// laid out with a caption of their time in the clip. Nothing is slowed, interpolated or re-rendered: a frame
// here is a frame the recorder wrote. `--every 2` keeps every second frame (80 ms) for a longer window.
import { chromium, OUT, mkdir, fs, path } from './lib.mjs';
import { execFileSync } from 'child_process';
import os from 'os';

const [clip, from, to, out] = process.argv.slice(2);
const opt = (k, d) => { const i = process.argv.indexOf(`--${k}`); return i > 0 ? process.argv[i + 1] : d; };
const cols = +opt('cols', 4), scale = +opt('scale', 0.5), every = +opt('every', 1), crop = opt('crop', '');
const FF = path.join(os.homedir(), 'Library/Caches/ms-playwright/ffmpeg-1011/ffmpeg-mac');
const src = path.join(OUT, 'recordings', `${clip}.webm`);
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'strip-'));

// Playwright's ffmpeg has no fps filter: frames are decoded as written (passthrough) and named by their own
// presentation timestamp (-frame_pts, in 1/25 s), so a caption is the frame's real time in the clip.
const vf = [crop && `crop=${crop}`, `scale=iw*${scale}:-1`].filter(Boolean).join(',');
execFileSync(FF, ['-hide_banner', '-loglevel', 'error', '-copyts', '-ss', String(from / 1000), '-t', String((to - from) / 1000),
  '-i', src, '-vf', vf, '-fps_mode', 'passthrough', '-frame_pts', '1', path.join(tmp, '%08d.png')]);
const frames = fs.readdirSync(tmp).filter((f) => f.endsWith('.png')).sort().filter((_, i) => i % every === 0);
const ms = (f) => parseInt(f.slice(0, 8), 10) * 40;   // the output timebase is 1/25 s: the name is a frame number

const html = `<!doctype html><meta charset=utf-8><body style="margin:0;background:#111;color:#ddd;font:11px ui-monospace,monospace">
<div style="display:grid;grid-template-columns:repeat(${cols},auto);gap:6px;padding:6px;justify-content:start">
${frames.map((f) => `<figure style="margin:0"><img src="file://${path.join(tmp, f)}" style="display:block;border:1px solid #333"><figcaption style="padding:2px 0">${clip} &nbsp;t=${ms(f)} ms</figcaption></figure>`).join('')}
</div>`;
const page_html = path.join(tmp, 'sheet.html');
fs.writeFileSync(page_html, html);
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 400 } });
await page.goto('file://' + page_html);
await page.waitForLoadState('load');
mkdir(path.dirname(path.relative(OUT, out)) || '.');
await page.screenshot({ path: out, fullPage: true });
await browser.close();
fs.rmSync(tmp, { recursive: true, force: true });
console.log(out, frames.length, 'frames');
