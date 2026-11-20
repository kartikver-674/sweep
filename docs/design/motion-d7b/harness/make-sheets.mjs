// D7B: cut the representative filmstrips from the production recordings, centred on the interaction each one is about.
//
//   node docs/design/motion-d7b/harness/make-sheets.mjs [name ...] [--dir recordings]
//
// Windows come from each clip's trace (the click times, the harness's own calls and the moments the page was seen to land tiles or show
// an ending), so a sheet starts just before the press and runs until the motion is over. Every frame is a real frame of the WebM at its
// real time in the clip (25 fps: 40 ms apart); nothing is slowed, interpolated or re-rendered. Output: output/design-D7B/frames/*.png
import { OUT, mkdir, argv, fs, path } from './lib.mjs';
import { execFileSync } from 'child_process';
import { fileURLToPath } from 'url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const dirName = argv('dir', 'recordings');
const tracesDir = dirName === 'recordings' ? 'traces' : dirName.replace('recordings', 'traces');
const trace = (clip) => JSON.parse(fs.readFileSync(path.join(OUT, tracesDir, `${clip}.json`), 'utf8'));
// the trace's clock is the recorder's wall clock; the video's starts a little apart and drifts: two flashes (start, end) give the offset
const toVideo = (clip, t) => { const tr = trace(clip); const end = tr.sync.find((x) => x.label === 'end:on').wall; return t + tr.videoStartOffsetMs + (t / end) * tr.videoDriftMs; };
const find = (clip, list, key, startsWith) => { const c = trace(clip)[list].find((c) => c[key].startsWith(startsWith)); if (!c) throw new Error(`${clip}: no ${list} entry "${startsWith}"`); return toVideo(clip, c.tMs); };
const click = (clip, s) => find(clip, 'clicks', 'step', s);
const step = (clip, s) => find(clip, 'steps', 'label', s);
const mark = (clip, s) => find(clip, 'marks', 'label', s);
const call = (clip, s) => find(clip, 'calls', 'label', s);
const frames = mkdir(dirName === 'recordings' ? 'frames' : dirName.replace('recordings', 'frames'));

const D = { crop: '1440:700:0:170', scale: 0.3, cols: 6 };            // the list area of a 1440 page
const M = { crop: '390:700:0:130', scale: 0.42, cols: 7 };            // the list area of a 390 page
const TOOLS = { crop: '1440:560:0:200', scale: 0.3, cols: 6 };
const METER = { crop: '1440:150:0:50', scale: 0.42, cols: 4 };
const ASIDE = { crop: '380:340:1050:460', scale: 0.55, cols: 6 };        // Configure's estimate panel at 1440
const FIG = { crop: '390:420:0:420', scale: 0.5, cols: 6 };           // the figure, once scrolled into view on a phone
const FULLD = { crop: '1440:760:0:60', scale: 0.27, cols: 6 };
const FULLM = { crop: '390:760:0:60', scale: 0.4, cols: 7 };

const jobs = [];
const sheet = (name, clip, from, to, o, every = 1) => jobs.push({ name, clip, from: Math.max(0, Math.round(from)), to: Math.round(to), o, every });
const has = (clip) => fs.existsSync(path.join(OUT, dirName, `${clip}.webm`)) && fs.existsSync(path.join(OUT, tracesDir, `${clip}.json`));
const guarded = (fn) => { try { fn(); } catch (e) { console.log('skip:', e.message); } };

for (const vp of ['desktop', 'mobile']) {
  const o = vp === 'desktop' ? D : M, full = vp === 'desktop' ? FULLD : FULLM;
  let c = `results-${vp}`;
  if (has(c)) guarded(() => {
    const a = click(c, 'arrive on Results'); sheet(`01-arrival-${vp}`, c, a - 60, a + 720, o);
    const t = click(c, 'tab: Backend'); sheet(`02-tab-change-${vp}`, c, t - 80, t + 620, o);
    const i = step(c, 'interruption'); sheet(`03-interruption-${vp}`, c, i + 350, i + 1450, { ...o, scale: o.scale * 0.85 }, 2);
    if (vp === 'desktop') {
      sheet('04-tool-open-desktop', c, click(c, 'Filter and sort: open') - 80, click(c, 'Filter and sort: open') + 420, TOOLS);
      sheet('04-tool-switch-desktop', c, click(c, 'Export: open') - 80, click(c, 'Export: open') + 420, TOOLS);
      sheet('04-tool-close-desktop', c, click(c, 'Export: close') - 80, click(c, 'Export: close') + 420, TOOLS);
    }
  });
  c = `results-slow-${vp}`;
  if (has(c)) guarded(() => { const t = click(c, 'tab (slow server): Backend'); sheet(`05-slow-${vp}`, c, t - 100, t + 1350, o, 2); });
  c = `results-reduced-${vp}`;
  if (has(c)) guarded(() => {
    const a = click(c, 'arrive on Results'); sheet(`06-reduced-arrival-${vp}`, c, a - 60, a + 720, o);
    const t = click(c, 'tab: Backend'); sheet(`06-reduced-tab-${vp}`, c, t - 80, t + 620, o);
    if (vp === 'desktop') sheet('06-reduced-panel-desktop', c, click(c, 'Filter and sort: open') - 80, click(c, 'Filter and sort: open') + 420, TOOLS);
    if (vp === 'desktop') sheet('06-reduced-switch-desktop', c, click(c, 'Export: open') - 80, click(c, 'Export: open') + 420, TOOLS);   // Filter replaced by Export: one frame, never both (D7B follow-up)
  });
  c = `progress-success-${vp}`;
  if (has(c)) guarded(() => {
    const l = mark(c, 'the tiles landed'); sheet(`07-progress-tiles-${vp}`, c, l - 200, l + 800, full, 1);
    const e = mark(c, 'the ending is shown'); sheet(`07-progress-ending-${vp}`, c, e - 200, e + 1900, { ...full, scale: full.scale * 0.85 }, 2);
  });
  c = `progress-failure-${vp}`;
  if (has(c)) guarded(() => { const e = mark(c, 'the ending is shown'); sheet(`08-progress-failure-${vp}`, c, e - 200, e + 1000, full, 1); });
  c = `configure-price-${vp}`;
  if (has(c)) guarded(() => { const t = click(c, 'five more results per search (a slow answer)'); sheet(`09-configure-pending-${vp}`, c, t - 100, t + (vp === 'desktop' ? 1800 : 3000), vp === 'desktop' ? ASIDE : FIG, 2); });
  c = `configure-overcap-${vp}`;
  if (has(c)) guarded(() => { const t = click(c, 'five more results per search: over'); sheet(`10-overcap-${vp}`, c, t - 100, t + 900, vp === 'desktop' ? ASIDE : FIG, 1); });
  c = `upload-${vp}`;
  if (has(c)) guarded(() => {
    const s = step(c, 'two files accepted'); sheet(`11-upload-accept-${vp}`, c, s - 40, s + 800, { crop: vp === 'desktop' ? '1440:620:0:80' : '390:700:0:100', scale: vp === 'desktop' ? 0.3 : 0.42, cols: vp === 'desktop' ? 6 : 7 }, 1);
    if (vp === 'desktop') { const d = step(c, 'a file held over'); sheet('11-upload-dragover-desktop', c, d + 500, d + 1500, { crop: '1440:620:0:80', scale: 0.3, cols: 6 }, 1); }
  });
  c = `results-long-${vp}`;
  if (has(c)) guarded(() => { const a = click(c, 'arrive on Results'); sheet(`12-long-arrival-${vp}`, c, a - 60, a + 800, o); });
}
let c = 'console-configure-desktop';
if (has(c)) guarded(() => { const t = click(c, 'switch Indeed off (a slow answer)'); sheet('13-console-price-desktop', c, t - 100, t + 1800, METER, 2); });
c = 'console-overcap-desktop';
if (has(c)) guarded(() => { const t = click(c, 'switch Indeed on (a slow answer)'); sheet('14-console-overcap-desktop', c, t - 100, t + 1800, METER, 2); });
c = 'console-progress-desktop';
if (has(c)) guarded(() => { const e = mark(c, 'the ending is shown'); sheet('15-console-ending-desktop', c, e - 200, e + 1900, { ...FULLD, scale: 0.23 }, 2); });

const only = process.argv.slice(2).filter((a) => !a.startsWith('--') && a !== dirName);
for (const j of jobs) {
  if (only.length && !only.some((o) => j.name.includes(o))) continue;
  execFileSync('node', [path.join(HERE, 'filmstrip.mjs'), j.clip, String(j.from), String(j.to), path.join(frames, `${j.name}.png`),
    '--cols', String(j.o.cols), '--scale', String(j.o.scale), '--crop', j.o.crop, '--every', String(j.every), '--dir', dirName], { stdio: 'inherit' });
}
