/**
 * Gemeinsame Darstellungsdaten für Szene, Zeitleiste und Diagramme – unabhängig vom
 * Modell-Level. Zeitraster 1 kHz von Hürden-Lift-off (bzw. TD) bis Wasser.
 */
import type { Level2Response } from './api';
import type { Level1Result, ParamValues } from '../sim-live/level1';

export const POINTS = ['toe', 'ball', 'heel', 'ankle', 'knee', 'hip', 'shoulder', 'neck', 'vertex', 'elbow', 'wrist', 'fingertip'] as const;
export const JOINT_LABELS = ['MTP', 'Sprunggelenk', 'Knie', 'Hüfte', 'Schulter', 'Ellbogen'];
export const SEGMENT_LABELS = ['Zehen', 'Rückfuß', 'Unterschenkel', 'Oberschenkel', 'Rumpf+Kopf', 'Oberarm', 'Unterarm+Hand', 'Schwabbel Rumpf', 'Schwabbel Oberschenkel', 'Schwabbel Unterschenkel'];

export interface View {
  level: 1 | 2;
  t: Float64Array;
  events: Record<string, number>;
  com_x: Float64Array; com_z: Float64Array; v_z: Float64Array;
  z_b: Float64Array; x_b: Float64Array; v_b: Float64Array;
  F: Float64Array; Fx: Float64Array;
  /** Level 1: Beinlänge für die illustrative Figur */
  l?: Float64Array;
  /** Level 2: 12 Körperpunkte (x, z) je Frame */
  points?: Float32Array;
  metrics: Record<string, number | null>;
  warnings: string[];
  geom: { H: number; M: number; d: number; overhang: number; span: number; l_td: number; l_max: number };
  l1?: Level1Result;
  l2?: Level2Response;
  /** Index des TD-Frames im Raster */
  iTd: number;
}

export function viewFromLevel1(r: Level1Result): View {
  const s = r.series;
  const iTd = Math.max(0, Math.round(-s.t[0] * 1000));
  return {
    level: 1, t: s.t, events: r.events, com_x: s.x_c, com_z: s.z_c, v_z: s.v_c, z_b: s.z_b, x_b: s.x_b, v_b: s.v_b,
    F: s.F, Fx: new Float64Array(s.t.length), l: s.l, metrics: r.metrics, warnings: r.warnings,
    geom: { ...r.geom }, l1: r, iTd,
  };
}

export function viewFromLevel2(r: Level2Response, p: ParamValues, geom: View['geom']): View {
  const s = r.series;
  const ht = s.hurdle_t ?? [];
  const nH = ht.length;
  const nC = s.t.length;
  const nF = s.flight_t.length;
  const n = nH + nC + nF;
  const t = new Float64Array(n);
  const com_x = new Float64Array(n);
  const com_z = new Float64Array(n);
  const v_z = new Float64Array(n);
  const z_b = new Float64Array(n);
  const v_b = new Float64Array(n);
  const F = new Float64Array(n);
  const Fx = new Float64Array(n);
  const points = new Float32Array(n * 24);
  const c = p['board.horiz_coeff'] as number;
  const vx = p['technique.v_x'] as number;
  const g = p['numerics.g'] as number;
  const c0 = s.com[0];
  for (let i = 0; i < nH; i++) {
    t[i] = ht[i];
    com_z[i] = s.hurdle_com_z![i];
    com_x[i] = c0[0] + vx * ht[i];
    z_b[i] = s.hurdle_z_b![i];
    const dzc = com_z[i] - c0[1];
    const dxc = com_x[i] - c0[0];
    for (let k = 0; k < 12; k++) {
      points[i * 24 + 2 * k] = s.points[0][2 * k] + dxc;
      points[i * 24 + 2 * k + 1] = s.points[0][2 * k + 1] + dzc;
    }
  }
  for (let i = 0; i < nH; i++) v_z[i] = i > 0 ? (com_z[i] - com_z[i - 1]) * 1000 : 0;
  for (let i = 0; i < nC; i++) {
    const j = nH + i;
    t[j] = s.t[i];
    com_x[j] = s.com[i][0];
    com_z[j] = s.com[i][1];
    v_z[j] = s.com[i][3];
    z_b[j] = s.z_b[i];
    v_b[j] = s.v_b[i];
    F[j] = s.Fz[i];
    Fx[j] = s.Fx[i];
    points.set(s.points[i], j * 24);
  }
  const tTo = r.events.TO;
  const cto = s.com[nC - 1];
  for (let i = 0; i < nF; i++) {
    const j = nH + nC + i;
    t[j] = s.flight_t[i];
    com_x[j] = s.flight_com[i][0];
    com_z[j] = s.flight_com[i][1];
    v_z[j] = cto[3] - g * (t[j] - tTo);
    z_b[j] = s.flight_z_b[i];
    points.set(s.flight_points[i], j * 24);
  }
  const x_b = new Float64Array(n);
  for (let i = 0; i < n; i++) x_b[i] = -c * z_b[i] * z_b[i];
  return {
    level: 2, t, events: r.events, com_x, com_z, v_z, z_b, x_b, v_b, F, Fx, points,
    metrics: r.metrics_raw, warnings: r.warnings, geom, l2: r, iTd: nH,
  };
}

/** Index des Frames mit t ≤ time (binäre Suche; Raster ist nur nahezu äquidistant). */
export function frameAt(v: View, time: number): number {
  const t = v.t;
  let lo = 0;
  let hi = t.length - 1;
  if (time <= t[0]) return 0;
  if (time >= t[hi]) return hi;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (t[mid] <= time) lo = mid; else hi = mid;
  }
  return time - t[lo] < t[hi] - time ? lo : hi;
}
