// A small PNG reader (8-bit, non-interlaced, colour type 2 or 6: what Playwright writes) and a pixel diff.
import zlib from 'zlib';
import fs from 'fs';

export function decode(file) {
  const b = fs.readFileSync(file);
  let o = 8, w = 0, h = 0, ct = 0; const idat = [];
  while (o < b.length) {
    const n = b.readUInt32BE(o), t = b.toString('ascii', o + 4, o + 8);
    if (t === 'IHDR') { w = b.readUInt32BE(o + 8); h = b.readUInt32BE(o + 12); ct = b[o + 17]; if (b[o + 16] !== 8 || b[o + 20] !== 0) throw new Error('unsupported PNG'); }
    if (t === 'IDAT') idat.push(b.subarray(o + 8, o + 8 + n));
    o += 12 + n;
  }
  const bpp = ct === 6 ? 4 : 3, stride = w * bpp;
  const raw = zlib.inflateSync(Buffer.concat(idat)), out = Buffer.alloc(w * h * 4);
  let prev = Buffer.alloc(stride);
  for (let y = 0; y < h; y++) {
    const f = raw[y * (stride + 1)], line = Buffer.from(raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1)));
    for (let i = 0; i < stride; i++) {
      const a = i >= bpp ? line[i - bpp] : 0, up = prev[i], c = i >= bpp ? prev[i - bpp] : 0;
      let x = line[i];
      if (f === 1) x += a; else if (f === 2) x += up; else if (f === 3) x += (a + up) >> 1;
      else if (f === 4) { const p = a + up - c, pa = Math.abs(p - a), pb = Math.abs(p - up), pc = Math.abs(p - c); x += (pa <= pb && pa <= pc) ? a : (pb <= pc ? up : c); }
      line[i] = x & 255;
    }
    for (let x = 0; x < w; x++) { out[(y * w + x) * 4] = line[x * bpp]; out[(y * w + x) * 4 + 1] = line[x * bpp + 1]; out[(y * w + x) * 4 + 2] = line[x * bpp + 2]; out[(y * w + x) * 4 + 3] = bpp === 4 ? line[x * bpp + 3] : 255; }
    prev = line;
  }
  return { w, h, data: out };
}

// how many pixels differ, where, and by how much at most
export function diff(fa, fb) {
  const a = decode(fa), b = decode(fb);
  if (a.w !== b.w || a.h !== b.h) return { same: false, sizes: [[a.w, a.h], [b.w, b.h]], pixels: null };
  let n = 0, max = 0, x0 = a.w, y0 = a.h, x1 = -1, y1 = -1;
  for (let y = 0; y < a.h; y++) for (let x = 0; x < a.w; x++) {
    const i = (y * a.w + x) * 4; const d = Math.max(Math.abs(a.data[i] - b.data[i]), Math.abs(a.data[i + 1] - b.data[i + 1]), Math.abs(a.data[i + 2] - b.data[i + 2]));
    if (d) { n++; max = Math.max(max, d); x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  }
  return { same: n === 0, sizes: [[a.w, a.h]], pixels: n, maxChannelDelta: max, bbox: n ? [x0, y0, x1, y1] : null };
}

// A PNG writer (8-bit RGBA, no filtering) and a diff picture: the "after" state dimmed, every differing pixel in red.
export function encode(file, w, h, rgba) {
  const crcT = new Int32Array(256).map((_, n) => { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c; });
  const crc = (buf) => { let c = -1; for (const x of buf) c = crcT[(c ^ x) & 255] ^ (c >>> 8); return (c ^ -1) >>> 0; };
  const chunk = (t, d) => { const b = Buffer.alloc(12 + d.length); b.writeUInt32BE(d.length, 0); b.write(t, 4, 'ascii'); d.copy(b, 8); b.writeUInt32BE(crc(b.subarray(4, 8 + d.length)), 8 + d.length); return b; };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 6;
  const raw = Buffer.alloc((w * 4 + 1) * h);
  for (let y = 0; y < h; y++) { raw[y * (w * 4 + 1)] = 0; rgba.copy(raw, y * (w * 4 + 1) + 1, y * w * 4, (y + 1) * w * 4); }
  fs.writeFileSync(file, Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]));
}
export function diffPicture(fa, fb, out, cropTo = null) {
  const a = decode(fa), b = decode(fb); if (a.w !== b.w || a.h !== b.h) return false;
  const d = Buffer.alloc(a.w * a.h * 4);
  for (let i = 0; i < a.w * a.h; i++) { const o = i * 4; const same = a.data[o] === b.data[o] && a.data[o + 1] === b.data[o + 1] && a.data[o + 2] === b.data[o + 2];
    d[o] = same ? b.data[o] * 0.35 : 255; d[o + 1] = same ? b.data[o + 1] * 0.35 : 40; d[o + 2] = same ? b.data[o + 2] * 0.35 : 40; d[o + 3] = 255; }
  encode(out, a.w, a.h, d); return true;
}
