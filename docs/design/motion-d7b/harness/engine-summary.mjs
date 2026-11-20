// D7B follow-up: one table from the per-engine verify JSONs, so the note quotes what the files say.
//
//   node docs/design/motion-d7b/harness/engine-summary.mjs            (reads output/design-D7B/verify-*-engines-<engine>.json)
//
// Prints the table, the engine-difference notes, anything skipped and every runtime error, and writes output/design-D7B/engines-summary.md.
import { OUT, fs, path } from './lib.mjs';

const ENGINES = ['chromium', 'chrome', 'firefox', 'webkit'];
const SCRIPTS = ['results', 'progress', 'forms'];
const read = (s, e) => { const f = path.join(OUT, `verify-${s}-engines-${e}.json`); return fs.existsSync(f) ? JSON.parse(fs.readFileSync(f, 'utf8')) : null; };

const lines = ['| Engine | Results | Progress | Forms | Checks run | Skipped | Engine-difference branches | Script errors | Console errors |', '|---|---|---|---|---|---|---|---|---|'];
const notes = [], errs = [];
for (const e of ENGINES) {
  const j = Object.fromEntries(SCRIPTS.map((s) => [s, read(s, e)]));
  if (!SCRIPTS.every((s) => j[s])) { lines.push(`| ${e} | (not run) | | | | | | | |`); continue; }
  const sum = (k) => SCRIPTS.reduce((n, s) => n + (j[s][k] || 0), 0);
  const skipped = SCRIPTS.flatMap((s) => j[s].skipped.map((x) => x.id));
  const pe = SCRIPTS.flatMap((s) => j[s].runtime.pageErrors), ce = SCRIPTS.flatMap((s) => j[s].runtime.consoleErrors);
  lines.push(`| ${j.results.engine} | ${j.results.pass}/${j.results.total} | ${j.progress.pass}/${j.progress.total} | ${j.forms.pass}/${j.forms.total} | **${sum('pass')}/${sum('total')}** | ${skipped.join(', ') || 'none'} | ${sum('engineDifferences')} | ${pe.length} | ${ce.length} |`);
  for (const s of SCRIPTS) for (const r of j[s].results) if (r.engineDifference) notes.push(`- **${e} ${r.id}**: ${r.engineDifference}`);
  for (const s of SCRIPTS) for (const x of j[s].skipped) notes.push(`- **${e} ${x.id}** skipped: ${x.reason}`);
  for (const m of [...new Set(pe)]) errs.push(`- ${e} script error: ${m}`);
  for (const m of [...new Set(ce)]) errs.push(`- ${e} console error: ${m}`);
}
const env = ENGINES.map((e) => read('results', e)).find(Boolean)?.env;
const out = [lines.join('\n'), '', env ? `Playwright ${env.playwright}, Node ${env.node}, ${env.os}` : '', '', '### Engine differences and skips', notes.join('\n') || 'none', '', '### Runtime errors', errs.join('\n') || 'none'].join('\n');
fs.writeFileSync(path.join(OUT, 'engines-summary.md'), out + '\n');
console.log(out);
