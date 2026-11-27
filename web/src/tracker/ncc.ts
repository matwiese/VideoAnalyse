/**
 * Halbautomatisches Tracking: Mustervergleich per normierter Kreuzkorrelation (NCC) auf
 * Graustufenbildern, mit Subpixel-Verfeinerung (Parabel). Reine Funktionen, getestet.
 */

export interface Gray {
  w: number;
  h: number;
  data: Float32Array; // Luminanz 0..255, zeilenweise
}

/** RGBA → Luminanz (Rec. 601). */
export function toGray(rgba: Uint8ClampedArray, w: number, h: number): Gray {
  const data = new Float32Array(w * h);
  for (let i = 0, j = 0; i < data.length; i++, j += 4) data[i] = 0.299 * rgba[j] + 0.587 * rgba[j + 1] + 0.114 * rgba[j + 2];
  return { w, h, data };
}

/** Quadratischen Ausschnitt (2·half+1) um (cx, cy) [px, ganzzahlig gerundet] kopieren; null am Rand. */
export function patch(img: Gray, cx: number, cy: number, half: number): Gray | null {
  const x0 = Math.round(cx) - half;
  const y0 = Math.round(cy) - half;
  const n = 2 * half + 1;
  if (x0 < 0 || y0 < 0 || x0 + n > img.w || y0 + n > img.h) return null;
  const data = new Float32Array(n * n);
  for (let y = 0; y < n; y++) data.set(img.data.subarray((y0 + y) * img.w + x0, (y0 + y) * img.w + x0 + n), y * n);
  return { w: n, h: n, data };
}

export interface MatchResult {
  x: number; // Bildkoordinate [px], Subpixel
  y: number;
  score: number; // NCC −1..1
}

/**
 * Sucht die Vorlage ``tpl`` im Bild ``img`` innerhalb ±search px um (px, py).
 * Gibt die beste Position (Mittelpunkt) und den NCC-Wert zurück.
 * ``distPenalty`` bevorzugt Treffer nahe der Vorhersage: Auswahl nach NCC − w·(d/search)²
 * (verhindert Springen auf gleich aussehende Nachbarmarker); zurückgegeben wird der reine NCC.
 */
export function matchTemplate(img: Gray, tpl: Gray, px: number, py: number, search: number, distPenalty = 0): MatchResult | null {
  const half = (tpl.w - 1) / 2;
  const n = tpl.w * tpl.h;
  let tMean = 0;
  for (let i = 0; i < n; i++) tMean += tpl.data[i];
  tMean /= n;
  let tVar = 0;
  const t0 = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    t0[i] = tpl.data[i] - tMean;
    tVar += t0[i] * t0[i];
  }
  if (tVar < 1e-6) return null; // strukturlose Vorlage
  const cx = Math.round(px);
  const cy = Math.round(py);
  const size = 2 * search + 1;
  const scores = new Float32Array(size * size).fill(-2);
  let best = -2;
  let bestEff = -1e9;
  let bx = 0;
  let by = 0;
  for (let dy = -search; dy <= search; dy++) {
    const y0 = cy + dy - half;
    if (y0 < 0 || y0 + tpl.h > img.h) continue;
    for (let dx = -search; dx <= search; dx++) {
      const x0 = cx + dx - half;
      if (x0 < 0 || x0 + tpl.w > img.w) continue;
      let sum = 0;
      for (let y = 0; y < tpl.h; y++) {
        const row = (y0 + y) * img.w + x0;
        for (let x = 0; x < tpl.w; x++) sum += img.data[row + x];
      }
      const mean = sum / n;
      let num = 0;
      let iVar = 0;
      for (let y = 0; y < tpl.h; y++) {
        const row = (y0 + y) * img.w + x0;
        for (let x = 0; x < tpl.w; x++) {
          const d = img.data[row + x] - mean;
          num += d * t0[y * tpl.w + x];
          iVar += d * d;
        }
      }
      const s = iVar > 1e-6 ? num / Math.sqrt(iVar * tVar) : -1;
      scores[(dy + search) * size + (dx + search)] = s;
      const eff = s - distPenalty * ((dx * dx + dy * dy) / (search * search));
      if (eff > bestEff) {
        bestEff = eff;
        best = s;
        bx = dx;
        by = dy;
      }
    }
  }
  if (best <= -2) return null;
  // Subpixel: Parabel durch Nachbarn
  const at = (dx: number, dy: number) => {
    const ix = dx + search;
    const iy = dy + search;
    if (ix < 0 || iy < 0 || ix >= size || iy >= size) return NaN;
    return scores[iy * size + ix];
  };
  const sub = (l: number, c: number, r: number) => {
    const den = l - 2 * c + r;
    return Number.isFinite(den) && Math.abs(den) > 1e-9 ? Math.max(-0.5, Math.min(0.5, (0.5 * (l - r)) / den)) : 0;
  };
  const ox = sub(at(bx - 1, by), best, at(bx + 1, by));
  const oy = sub(at(bx, by - 1), best, at(bx, by + 1));
  return { x: cx + bx + (Number.isFinite(ox) ? ox : 0), y: cy + by + (Number.isFinite(oy) ? oy : 0), score: best };
}
