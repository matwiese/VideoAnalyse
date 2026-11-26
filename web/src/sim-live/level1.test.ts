/**
 * Etappe 2: TS-Port und Python-Referenz stimmen auf 1e-6 überein.
 * Referenz erzeugen: python -m scripts.export_fixtures (im Repo-Root).
 */
import { describe, expect, it } from 'vitest';
import ref from './__fixtures__/level1_reference.json';
import { simulate, type ParamValues } from './level1';

type Case = { params: ParamValues; events: Record<string, number>; metrics: Record<string, number | null> };

describe('Level 1 TypeScript ↔ Python', () => {
  for (const [name, c] of Object.entries(ref as Record<string, Case>)) {
    it(name, () => {
      const r = simulate(c.params, { series: false });
      for (const [k, v] of Object.entries(c.events)) {
        expect(Math.abs(r.events[k] - v), `event ${k}`).toBeLessThan(1e-6);
      }
      for (const [k, v] of Object.entries(c.metrics)) {
        const got = r.metrics[k] as number;
        if (v === null) {
          expect(Number.isNaN(got)).toBe(true);
          continue;
        }
        if (k === 'energy_balance_rel') {
          expect(got).toBeLessThan(1e-6);
          continue;
        }
        const tol = 1e-6 * Math.max(1, Math.abs(v));
        expect(Math.abs(got - v), `${name}: ${k} TS=${got} Py=${v}`).toBeLessThan(tol);
      }
    });
  }

  it('Serien liegen auf 1-kHz-Raster', () => {
    const c = (ref as Record<string, Case>).elite_w_58_hurdle;
    const r = simulate(c.params);
    expect(r.series.t[1] - r.series.t[0]).toBeCloseTo(1e-3, 12);
    expect(r.series.F.length).toBe(r.series.t.length);
  });
});
