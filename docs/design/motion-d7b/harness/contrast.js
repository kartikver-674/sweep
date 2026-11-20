() => {
  // What the eye gets, node by node: each ancestor's background is composited over what is behind it, and each
  // ancestor's opacity then blends the whole group (its background AND everything inside it) over that same
  // backdrop. A dimmed list therefore dims its text and its own background together, which is what matters on
  // --surface and --well.
  // A7: Chromium serialises a computed color-mix() as color(srgb r g b / a) (channels 0 to 1), which the rgb() reader below missed: a text
  // colour made that way crashed the measure and a background made that way was read as no background. Both are read now.
  const parse = (s) => {
    const m = s.match(/rgba?\(([^)]+)\)/);
    if (m) { const p = m[1].split(/[ ,\/]+/).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; }
    const c = s.match(/color\(srgb ([^)]+)\)/);
    if (!c) return null;
    const p = c[1].split(/[ \/]+/).map(Number);
    return { r: p[0] * 255, g: p[1] * 255, b: p[2] * 255, a: p.length > 3 ? p[3] : 1 };
  };
  const lin = (v) => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); };
  const lum = (c) => .2126 * lin(c.r) + .7152 * lin(c.g) + .0722 * lin(c.b);
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
  const over = (fg, bg) => ({ r: fg.r * fg.a + bg.r * (1 - fg.a), g: fg.g * fg.a + bg.g * (1 - fg.a), b: fg.b * fg.a + bg.b * (1 - fg.a) });
  const mix = (x, below, op) => ({ r: x.r * op + below.r * (1 - op), g: x.g * op + below.g * (1 - op), b: x.b * op + below.b * (1 - op) });
  const GROUND = { r: 3, g: 22, b: 28 };
  const memo = new WeakMap();
  const style = (e) => { let c = memo.get(e); if (!c) { const cs = getComputedStyle(e); c = { bg: parse(cs.backgroundColor), op: parseFloat(cs.opacity), color: cs.color, fontSize: cs.fontSize, fontWeight: cs.fontWeight, visibility: cs.visibility, display: cs.display }; memo.set(e, c); } return c; };
  const colours = (el) => {
    const levels = []; for (let e = el; e; e = e.parentElement) levels.unshift(e);
    const go = (i, below) => {
      const e = levels[i], cs = style(e), c = cs.bg, op = cs.op;
      const innerBg = c && c.a > 0 ? over(c, below) : below;
      let fg, bg;
      if (i === levels.length - 1) { const f = parse(cs.color); fg = over(f, innerBg); bg = innerBg; }
      else ({ fg, bg } = go(i + 1, innerBg));
      return op < 1 ? { fg: mix(fg, below, op), bg: mix(bg, below, op) } : { fg, bg };
    };
    return go(0, GROUND);
  };
  const visible = (el) => { const r = el.getBoundingClientRect(); const cs = style(el); return r.width > 1 && r.height > 1 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  let worst = 99, worstText = '', nodes = 0; const fails = [];
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); let n;
  while ((n = w.nextNode())) {
    const t = n.textContent.trim(); if (!t) continue;
    const el = n.parentElement; if (!el || !visible(el)) continue;
    if (el.closest('[aria-hidden="true"], .visually-hidden, script, style, noscript, [hidden], dialog:not([open])')) continue;
    const { fg, bg } = colours(el); const r = ratio(fg, bg); nodes++;
    const cs = style(el), px = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight) >= 700;
    const need = (px >= 24 || (px >= 18.66 && bold)) ? 3 : 4.5;
    if (r < worst) { worst = r; worstText = t.slice(0, 40); }
    if (r < need) fails.push({ ratio: +r.toFixed(2), need, text: t.slice(0, 40) });
  }
  return { nodes, worst: +worst.toFixed(2), worstText, failCount: fails.length, fails: fails.slice(0, 12) };
}
