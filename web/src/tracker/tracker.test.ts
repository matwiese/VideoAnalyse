import { describe, expect, it } from 'vitest';
import { buildCsv, metersPerPixel, predict, tiltAngle, toMeters, type Calibration } from './geometry';
import { matchTemplate, patch, toGray, type Gray } from './ncc';

const calib: Calibration = {
  scaleA: [100, 500], scaleB: [600, 500], scaleLength: 2.0, scaleIsHorizontal: true, origin: [400, 300], waterRight: true,
};

describe('Kalibrierung', () => {
  it('Maßstab, Ursprung und Achsrichtungen', () => {
    expect(metersPerPixel(calib)).toBeCloseTo(0.004, 12);
    expect(toMeters(calib, [400, 300])).toEqual([0, -0]);
    const [x, z] = toMeters(calib, [500, 200]); // 100 px rechts, 100 px höher
    expect(x).toBeCloseTo(0.4, 12);
    expect(z).toBeCloseTo(0.4, 12);
    const [xl] = toMeters({ ...calib, waterRight: false }, [500, 200]);
    expect(xl).toBeCloseTo(-0.4, 12);
  });

  it('korrigiert Kameraneigung, auch bei rückwärts gezogener Linie', () => {
    const th = (5 * Math.PI) / 180;
    const A: [number, number] = [100, 500];
    const B: [number, number] = [100 + 500 * Math.cos(th), 500 + 500 * Math.sin(th)];
    for (const [a, b] of [[A, B], [B, A]] as const) {
      const c = { ...calib, scaleA: a, scaleB: b };
      expect(tiltAngle(c)).toBeCloseTo(th, 12);
      // Punkt, der im geneigten Bild „waagrecht“ 100 px vom Ursprung liegt → z = 0
      const p: [number, number] = [400 + 100 * Math.cos(th), 300 + 100 * Math.sin(th)];
      const [x, z] = toMeters(c, p);
      expect(z).toBeCloseTo(0, 10);
      expect(x).toBeCloseTo(0.4, 10);
    }
  });

  it('CSV-Export im Importformat, echte Zeit aus Aufnahme-Bildrate', () => {
    const csv = buildCsv({ knee: { 10: [500, 200], 12: [510, 200] }, toe: { 10: [400, 300] } }, ['toe', 'knee', 'hip'], calib, 240, 10, 12, 2);
    const lines = csv.trim().split('\n');
    expect(lines[0]).toBe('time (s),toe X (m),toe Y (m),knee X (m),knee Y (m)');
    expect(lines[1].split(',')[0]).toBe('0.000000');
    expect(Number(lines[2].split(',')[0])).toBeCloseTo(2 / 240, 6);
    expect(lines[2].split(',')[1]).toBe(''); // Lücke bleibt leer
  });

  it('lineare Vorhersage', () => {
    expect(predict({ 8: [0, 0], 9: [2, 1] }, 10, 1)).toEqual([4, 2]);
    expect(predict({ 9: [2, 1] }, 10, 1)).toEqual([2, 1]);
    expect(predict(undefined, 10, 1)).toBeNull();
  });
});

function blobImage(w: number, h: number, cx: number, cy: number): Gray {
  const rgba = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const r2 = (x - cx) ** 2 + (y - cy) ** 2;
      const v = 40 + 200 * Math.exp(-r2 / 18) + 30 * Math.sin(x / 7) * Math.cos(y / 9);
      const i = (y * w + x) * 4;
      rgba[i] = rgba[i + 1] = rgba[i + 2] = v;
      rgba[i + 3] = 255;
    }
  }
  return toGray(rgba, w, h);
}

describe('Mustervergleich (NCC)', () => {
  it('findet einen verschobenen Marker subpixelgenau', () => {
    const a = blobImage(160, 120, 70, 60);
    const b = blobImage(160, 120, 77.4, 55.6);
    const tpl = patch(a, 70, 60, 10)!;
    const m = matchTemplate(b, tpl, 70, 60, 15)!;
    expect(m.score).toBeGreaterThan(0.9);
    expect(m.x).toBeCloseTo(77.4, 0);
    expect(m.y).toBeCloseTo(55.6, 0);
    expect(Math.abs(m.x - 77.4)).toBeLessThan(0.5);
  });

  it('liefert niedrigen Score, wenn der Marker fehlt', () => {
    const a = blobImage(160, 120, 70, 60);
    const rgba = new Uint8ClampedArray(160 * 120 * 4).fill(90);
    const empty = toGray(rgba, 160, 120);
    const tpl = patch(a, 70, 60, 10)!;
    const m = matchTemplate(empty, tpl, 70, 60, 10);
    expect(m === null || m.score < 0.3).toBe(true);
  });
});
