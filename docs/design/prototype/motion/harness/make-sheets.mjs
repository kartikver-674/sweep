// D7A: cut the representative filmstrips from the recordings, centred on the interaction each one is about.
//
//   node docs/design/prototype/motion/harness/make-sheets.mjs
//
// Windows come from each clip's trace (the click times the recorder logged), so a sheet starts just before the
// press and runs until the motion is over. Every frame is a real frame of the WebM at its real time in the clip
// (25 fps: 40 ms apart). Output: output/design-D7A/frames/*.png
import { OUT, mkdir, fs, path } from './lib.mjs';
import { execFileSync } from 'child_process';
import { fileURLToPath } from 'url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const trace = (clip) => JSON.parse(fs.readFileSync(path.join(OUT, 'traces', `${clip}.json`), 'utf8'));
// Trace times are the recorder's wall clock; the video's clock starts a little apart and drifts. Each clip has a
// white flash at its start and end (record.mjs), so video time is the trace time plus an offset interpolated
// between the two.
const toVideo = (clip, t) => { const tr = trace(clip); const end = tr.sync.find((x) => x.label === 'end:on').wall;
  return t + tr.videoStartOffsetMs + (t / end) * tr.videoDriftMs; };
const click = (clip, startsWith) => { const c = trace(clip).clicks.find((c) => c.step.startsWith(startsWith)); return c && toVideo(clip, c.tMs); };
const step = (clip, startsWith) => { const c = trace(clip).steps.find((c) => c.label.startsWith(startsWith)); return c && toVideo(clip, c.tMs); };
const frames = mkdir('frames');

const D = { crop: '1440:700:0:170', scale: 0.3, cols: 6 };          // the list area of a 1440 page
const M = { crop: '390:700:0:130', scale: 0.42, cols: 7 };          // the list area of a 390 page
const TOOLS = { crop: '1440:560:0:200', scale: 0.3, cols: 6 };

const jobs = [];
const sheet = (name, clip, from, to, o, every = 1) => jobs.push({ name, clip, from: Math.max(0, Math.round(from)), to: Math.round(to), o, every });

for (const vp of ['desktop', 'mobile']) {
  const o = vp === 'desktop' ? D : M;
  for (const v of ['baseline', 'proposed']) {
    const c = `${v}-${vp}-normal`;
    const a = step(c, 'arrive');
    sheet(`01-arrival-${v}-${vp}`, c, a - 120, a + 520, o);
    const t = click(c, 'tab: Backend Engineer');
    sheet(`02-tab-change-${v}-${vp}`, c, t - 80, t + 620, o);
  }
  const r = `proposed-${vp}-reduced`;
  sheet(`03-reduced-arrival-${vp}`, r, step(r, 'arrive') - 120, step(r, 'arrive') + 520, o);
  sheet(`03-reduced-tab-change-${vp}`, r, click(r, 'tab: Backend Engineer') - 80, click(r, 'tab: Backend Engineer') + 620, o);
  const s = `proposed-${vp}-slow-server`;
  if (fs.existsSync(path.join(OUT, 'traces', `${s}.json`))) sheet(`04-slow-server-proposed-${vp}`, s, click(s, 'tab (slow server): Backend') - 100, click(s, 'tab (slow server): Backend') + 1250, o, 2);
}
const bs = 'baseline-desktop-slow-server';
sheet('04-slow-server-baseline-desktop', bs, click(bs, 'tab (slow server): Backend') - 100, click(bs, 'tab (slow server): Backend') + 1250, D, 2);

const p = 'proposed-desktop-normal';
const f = click(p, 'Filter and sort: open');
sheet('05-tool-panel-open-desktop', p, f - 80, f + 420, TOOLS);
const e = click(p, 'Export: open');
sheet('05-tool-panel-switch-desktop', p, e - 80, e + 420, TOOLS);
const x = click(p, 'Export: close');
sheet('05-tool-panel-close-desktop', p, x - 80, x + 420, TOOLS);
const vt = 'proposed-vt-desktop-normal';
sheet('06-alternative-view-transition-tab-desktop', vt, click(vt, 'tab: Backend Engineer') - 80, click(vt, 'tab: Backend Engineer') + 620, D);
for (const c of ['proposed-desktop-normal', 'baseline-desktop-normal', 'proposed-vt-desktop-normal']) {
  const i = step(c, 'interruption');
  sheet(`07-interruption-${c.replace('-desktop-normal', '')}`, c, i + 350, i + 1450, { ...D, scale: 0.26, cols: 7 }, 2);
}
const g = 'gsap-desktop-normal';
if (fs.existsSync(path.join(OUT, 'traces', `${g}.json`))) sheet('08-gsap-spike-arrival-desktop', g, step(g, 'arrive') - 120, step(g, 'arrive') + 520, D);

const only = process.argv.slice(2);
for (const j of jobs) {
  if (only.length && !only.some((o) => j.name.includes(o))) continue;
  if (!fs.existsSync(path.join(OUT, 'recordings', `${j.clip}.webm`))) { console.log('skip (no clip)', j.name); continue; }
  execFileSync('node', [path.join(HERE, 'filmstrip.mjs'), j.clip, String(j.from), String(j.to), path.join(frames, `${j.name}.png`),
    '--cols', String(j.o.cols), '--scale', String(j.o.scale), '--crop', j.o.crop, '--every', String(j.every)], { stdio: 'inherit' });
}
