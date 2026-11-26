/**
 * Level 1 – Zwei-Massen-Modell Springer/Brett, TypeScript-Port von core/models/level1.py
 * (SPEC Kap. 6.1). Identische Operationsfolge wie Python, damit beide auf 1e-6
 * übereinstimmen (Vitest: level1.test.ts gegen Python-Referenz).
 *
 * Einheiten SI: m, kg, s, N, J. Zeit t = 0 beim Touchdown.
 * Zustand y: [z_c, v_c, z_b, v_b, W_act, D_leg, D_board, W_board, J_z]
 */

export type ParamValues = Record<string, number | string>;

const REF_FULCRUM = 7.5;

// ---------------------------------------------------------------------------
// Brett (SPEC 4)
// ---------------------------------------------------------------------------
export interface Board {
  k_s: number; m_b: number; c_b: number; zeta: number; horiz: number; d: number;
  fulcrum: number; model: string; EI: number; span: number; overhang: number;
  omega0: number; f0: number;
}

export function stiffness(p: ParamValues, d: number, fulcrum: number, model: string) {
  const kTip = p['board.k_tip_75'] as number;
  const stepLen = p['board.fulcrum_step_length'] as number;
  const span0 = p['board.span_75'] as number;
  const a0 = p['board.overhang_75'] as number;
  const EI = (kTip * a0 * a0 * (span0 + a0)) / 3.0;
  const shift = stepLen * (fulcrum - REF_FULCRUM);
  const span = span0 - shift;
  const overhang = a0 + shift;
  let k: number;
  if (model === 'A') {
    k = kTip + (p['board.m_k'] as number) * d + (p['board.delta_k_per_step'] as number) * (REF_FULCRUM - fulcrum);
  } else {
    const a = overhang - d;
    k = (3.0 * EI) / (a * a * (span + a));
  }
  if (k <= 0) throw new Error('Brettsteifigkeit ≤ 0 – Parameter prüfen');
  return { k, EI, span, overhang };
}

export function effectiveMass(p: ParamValues, fulcrum: number, model: string): number {
  const kRef = stiffness(p, 0.0, REF_FULCRUM, model).k;
  const kF = stiffness(p, 0.0, fulcrum, model).k;
  return (p['board.m_b_75'] as number) * Math.pow(kRef / kF, p['board.mb_exponent'] as number);
}

export function makeBoard(p: ParamValues): Board {
  const d = p['technique.d_toes'] as number;
  const fulcrum = p['board.fulcrum'] as number;
  const model = p['board.fulcrum_model'] as string;
  const { k, EI, span, overhang } = stiffness(p, d, fulcrum, model);
  const m_b = effectiveMass(p, fulcrum, model);
  const zeta = p['board.zeta'] as number;
  const c_b = 2.0 * zeta * Math.sqrt(k * m_b);
  const omega0 = Math.sqrt(k / m_b);
  return { k_s: k, m_b, c_b, zeta, horiz: p['board.horiz_coeff'] as number, d, fulcrum, model, EI, span, overhang, omega0, f0: omega0 / (2 * Math.PI) };
}

/** Phasenlage [°]: 0 oben, 90 abwärts durch Ruhelage, 180 unten, 270 aufwärts. */
export function boardPhaseDeg(z: number, v: number, omega: number): number {
  const psi = (Math.atan2(-v / omega, z) * 180) / Math.PI;
  return ((psi % 360) + 360) % 360;
}

// ---------------------------------------------------------------------------
// Muskel (SPEC 5.3)
// ---------------------------------------------------------------------------
export function smoothstep5(s: number): number {
  if (s <= 0) return 0;
  if (s >= 1) return 1;
  return s * s * s * (s * (6.0 * s - 15.0) + 10.0);
}

export interface Activation { a0: number; t_on: number; t_rise: number; a_plateau: number; t_off: number; t_fall: number; a_end: number }

export function activation(A: Activation, t: number): number {
  let a = A.a0 + (A.a_plateau - A.a0) * smoothstep5((t - A.t_on) / A.t_rise);
  if (t > A.t_off) a = a + (A.a_end - a) * smoothstep5((t - A.t_off) / A.t_fall);
  return Math.min(1.0, Math.max(0.0, a));
}

export function forceLength(l: number, lOpt: number, lMax: number): number {
  if (l >= lMax) return 0.0;
  const x = (l - lOpt) / (lMax - lOpt);
  return Math.max(0.0, 1.0 - x * x);
}

export function forceVelocity(v: number, v0: number, gamma: number, ecc: number): number {
  if (v >= v0) return 0.0;
  if (v >= 0.0) return (v0 - v) / (v0 + gamma * v);
  if (ecc <= 1.0) return 1.0;
  const s = (1.0 + gamma) / (v0 * (ecc - 1.0));
  return ecc - (ecc - 1.0) * Math.exp(s * v);
}

// ---------------------------------------------------------------------------
// Integrator mit Ereignisortung (SPEC 2, 6.4) – Port von core/events.py
// ---------------------------------------------------------------------------
type RHS = (t: number, y: number[]) => number[];
interface Ev { name: string; g: (t: number, y: number[]) => number; dir: number }

export function rk4Step(f: RHS, t: number, y: number[], h: number): number[] {
  const n = y.length;
  const k1 = f(t, y);
  const y2 = new Array<number>(n);
  for (let i = 0; i < n; i++) y2[i] = y[i] + 0.5 * h * k1[i];
  const k2 = f(t + 0.5 * h, y2);
  const y3 = new Array<number>(n);
  for (let i = 0; i < n; i++) y3[i] = y[i] + 0.5 * h * k2[i];
  const k3 = f(t + 0.5 * h, y3);
  const y4 = new Array<number>(n);
  for (let i = 0; i < n; i++) y4[i] = y[i] + h * k3[i];
  const k4 = f(t + h, y4);
  const out = new Array<number>(n);
  for (let i = 0; i < n; i++) out[i] = y[i] + (h / 6.0) * (k1[i] + 2.0 * k2[i] + 2.0 * k3[i] + k4[i]);
  return out;
}

function crossed(g0: number, g1: number, dir: number): boolean {
  if (dir < 0) return g0 > 0 && g1 <= 0;
  if (dir > 0) return g0 < 0 && g1 >= 0;
  return (g0 > 0 && g1 <= 0) || (g0 < 0 && g1 >= 0);
}

interface IntRes { t: number[]; y: number[][]; event: string | null }

export function integrate(f: RHS, t0: number, y0: number[], dt: number, tMax: number, events: Ev[], tol: number): IntRes {
  const ts = [t0];
  const ys = [y0.slice()];
  let t = t0;
  let y = y0.slice();
  let gs = events.map((e) => e.g(t, y));
  while (t < tMax - 1e-15) {
    const h = Math.min(dt, tMax - t);
    const y1 = rk4Step(f, t, y, h);
    const g1s = events.map((e) => e.g(t + h, y1));
    let hit = -1;
    let thetaHit = h;
    let yHit = y1;
    for (let i = 0; i < events.length; i++) {
      if (crossed(gs[i], g1s[i], events[i].dir)) {
        let lo = 0.0;
        let hi = h;
        let yHi = y1;
        while (hi - lo > tol) {
          const mid = 0.5 * (lo + hi);
          const yMid = rk4Step(f, t, y, mid);
          if (crossed(gs[i], events[i].g(t + mid, yMid), events[i].dir)) {
            hi = mid;
            yHi = yMid;
          } else lo = mid;
        }
        if (hit < 0 || hi < thetaHit) {
          hit = i;
          thetaHit = hi;
          yHit = yHi;
        }
      }
    }
    if (hit >= 0) {
      t = t + thetaHit;
      ts.push(t);
      ys.push(yHit);
      return { t: ts, y: ys, event: events[hit].name };
    }
    t = t + h;
    y = y1;
    gs = g1s;
    ts.push(t);
    ys.push(y);
  }
  return { t: ts, y: ys, event: null };
}

// ---------------------------------------------------------------------------
// Modell
// ---------------------------------------------------------------------------
export interface Config {
  M: number; g: number; H: number; l_td: number; l_max: number; l_opt: number;
  k_leg: number; c_leg: number; F_max: number; v0: number; gamma: number; ecc: number;
  act: Activation; board: Board; active: boolean; dt: number; tContactMax: number; tol: number;
}

export function makeConfig(p: ParamValues, active = true): Config {
  const H = p['athlete.height'] as number;
  const M = p['athlete.mass'] as number;
  const g = p['numerics.g'] as number;
  const n = (k: string) => p[k] as number;
  return {
    M, g, H,
    l_td: n('leg.l_td_ratio') * H, l_max: n('leg.l_max_ratio') * H, l_opt: n('leg.l_opt_ratio') * H,
    k_leg: n('leg.k_leg_per_kg') * M, c_leg: n('leg.c_leg'), F_max: n('leg.f_max_bw') * M * g,
    v0: n('leg.v0'), gamma: n('leg.gamma'), ecc: n('leg.ecc_factor'),
    act: {
      a0: n('activation.a0'), t_on: n('activation.t_on'), t_rise: n('activation.t_rise'), a_plateau: n('activation.a_plateau'),
      t_off: n('activation.t_off'), t_fall: n('activation.t_fall'), a_end: n('activation.a_end'),
    },
    board: makeBoard(p), active,
    dt: n('numerics.dt'), tContactMax: n('numerics.t_contact_max'), tol: n('numerics.event_tol'),
  };
}

/** [F_raw, F_spring, F_damp, F_act] in N. */
export function legForceParts(c: Config, t: number, y: number[]): [number, number, number, number] {
  const l = y[0] - y[2];
  const ldot = y[1] - y[3];
  const comp = c.l_td - l;
  const fs = comp > 0.0 ? c.k_leg * comp : 0.0;
  const fd = -c.c_leg * ldot;
  let fa = 0.0;
  if (c.active) fa = activation(c.act, t) * c.F_max * forceLength(l, c.l_opt, c.l_max) * forceVelocity(ldot, c.v0, c.gamma, c.ecc);
  return [fs + fd + fa, fs, fd, fa];
}

function rhsContact(c: Config): RHS {
  const b = c.board;
  return (t, y) => {
    const [Fraw, fs, , fa] = legForceParts(c, t, y);
    const F = Fraw > 0.0 ? Fraw : 0.0;
    const ldot = y[1] - y[3];
    return [
      y[1], F / c.M - c.g, y[3], (-b.k_s * y[2] - b.c_b * y[3] - F) / b.m_b,
      Fraw > 0.0 ? fa * ldot : 0.0,
      // geclampt (F = 0): Passivfeder entspannt lastfrei → Verlust im Bein
      Fraw > 0.0 ? c.c_leg * ldot * ldot : fs * ldot,
      b.c_b * y[3] * y[3], -F * y[3], F,
    ];
  };
}

function rhsFree(c: Config): RHS {
  const b = c.board;
  return (_t, y) => [y[1], -c.g, y[3], (-b.k_s * y[2] - b.c_b * y[3]) / b.m_b, 0, 0, b.c_b * y[3] * y[3], 0, 0];
}

export function mechanicalEnergy(c: Config, y: number[], contact: boolean): number {
  const b = c.board;
  let e = 0.5 * c.M * y[1] ** 2 + c.M * c.g * y[0] + 0.5 * b.m_b * y[3] ** 2 + 0.5 * b.k_s * y[2] ** 2;
  if (contact) {
    const comp = c.l_td - (y[0] - y[2]);
    if (comp > 0) e += 0.5 * c.k_leg * comp * comp;
  }
  return e;
}

function timeToHeight(z0: number, vz: number, zT: number, g: number): number {
  const disc = vz * vz + 2.0 * g * (z0 - zT);
  if (disc < 0) throw new Error('Zielhöhe wird nie erreicht');
  return (vz + Math.sqrt(disc)) / g;
}

function trapz(y: ArrayLike<number>, x: ArrayLike<number>): number {
  let s = 0;
  for (let i = 1; i < x.length; i++) s += 0.5 * (y[i] + y[i - 1]) * (x[i] - x[i - 1]);
  return s;
}

export interface Series {
  t: Float64Array; z_c: Float64Array; x_c: Float64Array; v_c: Float64Array; z_b: Float64Array; x_b: Float64Array;
  v_b: Float64Array; F: Float64Array; act: Float64Array; E_kin: Float64Array; E_pot: Float64Array;
  E_board: Float64Array; E_leg: Float64Array; W_act: Float64Array; D_loss: Float64Array; l: Float64Array;
}

export interface Level1Result {
  events: Record<string, number>;
  metrics: Record<string, number | null>;
  warnings: string[];
  series: Series;
  geom: { l_td: number; l_max: number; H: number; M: number; d: number; overhang: number; span: number; z_entry: number };
}

function integrateWithKinks(f: RHS, t0: number, y0: number[], c: Config, terminal: Ev[], kinks: Ev[]): IntRes {
  const ts = [t0];
  const ys = [y0.slice()];
  let t = t0;
  let y = y0.slice();
  const names = new Set(kinks.map((k) => k.name));
  for (let it = 0; it < 10000; it++) {
    const r = integrate(f, t, y, c.dt, c.tContactMax, terminal.concat(kinks), c.tol);
    for (let i = 1; i < r.t.length; i++) {
      ts.push(r.t[i]);
      ys.push(r.y[i]);
    }
    t = r.t[r.t.length - 1];
    y = r.y[r.y.length - 1];
    if (r.event === null || !names.has(r.event)) return { t: ts, y: ys, event: r.event };
  }
  return { t: ts, y: ys, event: null };
}

export function simulate(p: ParamValues, opts: { active?: boolean; series?: boolean } = {}): Level1Result {
  const c = makeConfig(p, opts.active ?? true);
  const b = c.board;
  const warnings: string[] = [];
  const segT: number[][] = [];
  const segY: number[][][] = [];
  const segC: boolean[] = [];
  const marks: Record<string, number> = {};
  const hurdle = p['technique.start_mode'] === 'hurdle';
  let yTd: number[];
  let y0first: number[];

  if (hurdle) {
    const zb = p['technique.board_z_hurdle'] as number;
    const vb = p['technique.board_v_hurdle'] as number;
    const vUp = Math.sqrt(2.0 * c.g * (p['technique.hurdle_height'] as number));
    const y0 = [zb + c.l_max, vUp, zb, vb, 0, 0, 0, 0, 0];
    y0first = y0;
    const r = integrate(rhsFree(c), 0.0, y0, c.dt, 5.0, [{ name: 'TD', g: (_t, y) => y[0] - y[2] - c.l_td, dir: -1 }], c.tol);
    if (r.event !== 'TD') throw new Error('Kein Touchdown nach Hürde gefunden');
    const tTd = r.t[r.t.length - 1];
    segT.push(r.t.map((t) => t - tTd));
    segY.push(r.y);
    segC.push(false);
    marks.HTO = -tTd;
    yTd = r.y[r.y.length - 1].slice();
  } else {
    const zb = p['technique.board_z_td'] as number;
    yTd = [zb + c.l_td, -Math.abs(p['technique.v_z_td'] as number), zb, p['technique.board_v_td'] as number, 0, 0, 0, 0, 0];
    y0first = yTd;
  }
  const E0 = mechanicalEnergy(c, y0first, false);

  marks.TD = 0.0;
  const lpEv: Ev = { name: 'LP', g: (_t, y) => y[3], dir: +1 };
  const toEv: Ev = { name: 'TO', g: (t, y) => legForceParts(c, t, y)[0], dir: -1 };
  const fc = rhsContact(c);
  // Knicke im Kraftgesetz als nicht-terminale Ereignisse (wie Python integrate_with_kinks)
  const kinks: Ev[] = [
    { name: 'KINK_F', g: (t, y) => legForceParts(c, t, y)[0], dir: 0 },
    { name: 'KINK_L', g: (_t, y) => c.l_td - (y[0] - y[2]), dir: 0 },
  ];
  let r = integrateWithKinks(fc, 0.0, yTd, c, [lpEv], kinks);
  segT.push(r.t);
  segY.push(r.y);
  segC.push(true);
  if (r.event === 'LP') {
    marks.LP = r.t[r.t.length - 1];
    const r2 = integrateWithKinks(fc, r.t[r.t.length - 1], r.y[r.y.length - 1], c, [toEv], kinks.slice(1));
    segT.push(r2.t.slice(1));
    segY.push(r2.y.slice(1));
    segC.push(true);
    r = r2;
  } else warnings.push('Kein tiefster Brettpunkt innerhalb der maximalen Kontaktzeit.');
  if (r.event !== 'TO') warnings.push(`Kein Takeoff innerhalb ${c.tContactMax} s Kontaktzeit.`);
  const tTo = r.t[r.t.length - 1];
  const yTo = r.y[r.y.length - 1].slice();
  marks.TO = tTo;

  // Rohreihen
  const T: number[] = [];
  const Y: number[][] = [];
  const C: boolean[] = [];
  for (let s = 0; s < segT.length; s++) {
    for (let i = 0; i < segT[s].length; i++) {
      T.push(segT[s][i]);
      Y.push(segY[s][i]);
      C.push(segC[s]);
    }
  }
  const N = T.length;
  const Fc = new Float64Array(N);
  for (let i = 0; i < N; i++) Fc[i] = C[i] ? Math.max(0.0, legForceParts(c, T[i], Y[i])[0]) : 0.0;

  // Flug
  const g = c.g;
  const vx = p['technique.v_x'] as number;
  const xTo = -b.d + vx * tTo;
  const zEntry = -(p['board.height_above_water'] as number) + (p['technique.entry_offset_ratio'] as number) * c.H;
  const vzTo = yTo[1];
  const zTo = yTo[0];
  const tApex = Math.max(vzTo, 0) / g;
  const zApex = zTo + Math.max(vzTo, 0) ** 2 / (2 * g);
  const tWater = timeToHeight(zTo, vzTo, zEntry, g);
  const tBp = zApex >= 0 ? timeToHeight(zTo, vzTo, 0.0, g) : 0.0;
  const rPost = integrate(rhsFree(c), tTo, yTo, c.dt, tTo + tWater, [], c.tol);

  // Energiebilanz
  const ETo = mechanicalEnergy(c, yTo, true);
  const [Wact, Dleg, Dboard] = [yTo[4], yTo[5], yTo[6]];
  const Eref = Math.max(Math.abs(E0), Math.abs(ETo), 0.5 * c.M * yTo[1] ** 2, 1.0);
  const balRel = Math.abs(ETo - E0 - (Wact - Dleg - Dboard)) / Eref;
  if (balRel > 0.005) warnings.push(`Energiebilanz-Abweichung ${(balRel * 100).toFixed(2)} % > 0,5 %`);

  // Kennwerte (Kontaktabschnitt)
  const i0 = C.indexOf(true);
  const tc = T.slice(i0);
  const Fcc = Array.from(Fc.subarray(i0));
  const Yc = Y.slice(i0);
  const hasLp = 'LP' in marks;
  const tLp = hasLp ? marks.LP : NaN;
  const mask = (pred: (i: number) => boolean, f: (i: number) => number) => tc.map((_, i) => (pred(i) ? f(i) : 0.0));
  const Wdep = hasLp ? trapz(mask((i) => tc[i] <= tLp, (i) => -Fcc[i] * Yc[i][3]), tc) : NaN;
  const Wrec = hasLp ? trapz(mask((i) => tc[i] > tLp, (i) => Fcc[i] * Yc[i][3]), tc) : NaN;
  const Jdep = hasLp ? trapz(mask((i) => tc[i] <= tLp, (i) => Fcc[i]), tc) : NaN;
  const Jrec = hasLp ? trapz(mask((i) => tc[i] > tLp, (i) => Fcc[i]), tc) : NaN;
  let rfd = -Infinity;
  for (let i = 1; i < tc.length; i++) {
    if (tc[i] > 0 && tc[i] <= 0.05) rfd = Math.max(rfd, (Fcc[i] - Fcc[i - 1]) / Math.max(tc[i] - tc[i - 1], 1e-12));
  }
  let iPk = 0;
  let zbMin = Infinity;
  let vbMin = Infinity;
  let powPk = -Infinity;
  let iLp = 0;
  for (let i = 0; i < tc.length; i++) {
    if (Fcc[i] > Fcc[iPk]) iPk = i;
    zbMin = Math.min(zbMin, Yc[i][2]);
    vbMin = Math.min(vbMin, Yc[i][3]);
    powPk = Math.max(powPk, Fcc[i] * (Yc[i][1] - Yc[i][3]));
    if (Math.abs(tc[i] - tLp) < Math.abs(tc[iLp] - tLp)) iLp = i;
  }
  const yLp = hasLp ? Yc[iLp] : Yc[Yc.length - 1];
  const BW = c.M * g;
  const H = c.H;

  const metrics: Record<string, number | null> = {
    board_k_s: b.k_s, board_m_b: b.m_b, board_f0: b.f0, board_f_loaded: Math.sqrt(b.k_s / (b.m_b + c.M)) / (2 * Math.PI),
    board_phase_td_deg: hurdle || yTd[2] !== 0 || yTd[3] !== 0 ? boardPhaseDeg(yTd[2], yTd[3], b.omega0) : NaN,
    hurdle_flight_time: hurdle ? -marks.HTO : null,
    v_z_td: yTd[1], v_x_td: vx, z_b_td: yTd[2], v_b_td: yTd[3], v_rel_td: yTd[1] - yTd[3],
    z_b_min: zbMin, v_b_min: vbMin, v_z_lp: yLp[1], z_c_lp: yLp[0],
    v_z_to: yTo[1], v_x_to: vx, z_c_to: yTo[0], z_b_to: yTo[2], v_b_to: yTo[3],
    takeoff_angle_deg: (Math.atan2(yTo[1], vx) * 180) / Math.PI,
    F_peak: Fcc[iPk], F_peak_bw: Fcc[iPk] / BW, t_F_peak: tc[iPk],
    F_mean_bw: trapz(Fcc, tc) / Math.max(tTo, 1e-9) / BW,
    board_spring_force_max: b.k_s * -zbMin, rfd_max: rfd,
    impulse_z: yTo[8], impulse_dep: Jdep, impulse_rec: Jrec,
    t_depression: tLp, t_recoil: tTo - tLp, t_contact: tTo, t_flight: tWater, t_apex: tApex,
    h_max_board: zApex, h_max_water: zApex + (p['board.height_above_water'] as number), h_rise: zApex - zTo,
    x_board_plane: xTo + vx * tBp, x_water: xTo + vx * tWater, z_entry: zEntry,
    E_kin_to: 0.5 * c.M * (yTo[1] ** 2 + vx ** 2), E_board_max: 0.5 * b.k_s * zbMin ** 2,
    W_act: Wact, W_act_per_kg: Wact / c.M, D_leg: Dleg, D_board: Dboard,
    W_athlete_to_board: Wdep, W_board_to_athlete: Wrec, board_efficiency: Wdep > 0 ? Wrec / Wdep : NaN,
    energy_balance_rel: balRel, leg_power_peak: powPk, leg_power_peak_per_kg: powPk / c.M,
    H_y: null, rotation_potential: null,
  };

  const series = opts.series === false ? emptySeries() : resample(c, p, T, Y, C, Fc, rPost, marks, metrics);
  return {
    events: marks, metrics, warnings, series,
    geom: { l_td: c.l_td, l_max: c.l_max, H, M: c.M, d: b.d, overhang: b.overhang, span: b.span, z_entry: zEntry },
  };
}

function emptySeries(): Series {
  const e = new Float64Array(0);
  return { t: e, z_c: e, x_c: e, v_c: e, z_b: e, x_b: e, v_b: e, F: e, act: e, E_kin: e, E_pot: e, E_board: e, E_leg: e, W_act: e, D_loss: e, l: e };
}

/** Lineare Interpolation auf sortiertem Gitter (wie numpy.interp). */
function interp(xq: Float64Array, x: number[], y: number[]): Float64Array {
  const out = new Float64Array(xq.length);
  let j = 0;
  for (let i = 0; i < xq.length; i++) {
    const q = xq[i];
    if (q <= x[0]) { out[i] = y[0]; continue; }
    if (q >= x[x.length - 1]) { out[i] = y[y.length - 1]; continue; }
    while (j < x.length - 2 && x[j + 1] < q) j++;
    while (j > 0 && x[j] > q) j--;
    const dx = x[j + 1] - x[j];
    out[i] = dx > 0 ? y[j] + ((y[j + 1] - y[j]) * (q - x[j])) / dx : y[j + 1];
  }
  return out;
}

function resample(
  c: Config, p: ParamValues, T: number[], Y: number[][], C: boolean[], Fc: Float64Array,
  rPost: IntRes, marks: Record<string, number>, m: Record<string, number | null>,
): Series {
  const rate = p['numerics.output_rate'] as number;
  const tTo = marks.TO;
  const tEnd = tTo + (m.t_flight as number);
  const k0 = Math.ceil(T[0] * rate);
  const k1 = Math.floor(tEnd * rate);
  const n = k1 - k0 + 1;
  const t = new Float64Array(n);
  for (let i = 0; i < n; i++) t[i] = (k0 + i) / rate;
  const col = (j: number) => Y.map((y) => y[j]);
  const zc = interp(t, T, col(0));
  const vc = interp(t, T, col(1));
  const F = interp(t, T, Array.from(Fc));
  const Wact = interp(t, T, col(4));
  const Dl = interp(t, T, Col2(Y, 5, 6));
  const actRaw = T.map((tt, i) => (C[i] && c.active ? activation(c.act, tt) : 0));
  const act = interp(t, T, actRaw);
  const Tb = T.concat(rPost.t.slice(1));
  const zb = interp(t, Tb, col(2).concat(rPost.y.slice(1).map((y) => y[2])));
  const vb = interp(t, Tb, col(3).concat(rPost.y.slice(1).map((y) => y[3])));
  const vx = p['technique.v_x'] as number;
  const d = p['technique.d_toes'] as number;
  const zTo = m.z_c_to as number;
  const vzTo = m.v_z_to as number;
  const g = c.g;
  const xc = new Float64Array(n);
  const xb = new Float64Array(n);
  const Ek = new Float64Array(n);
  const Ep = new Float64Array(n);
  const Eb = new Float64Array(n);
  const El = new Float64Array(n);
  const l = new Float64Array(n);
  const Wfin = m.W_act as number;
  const Dfin = (m.D_leg as number) + (m.D_board as number);
  for (let i = 0; i < n; i++) {
    xc[i] = -d + vx * t[i];
    if (t[i] > tTo) {
      const tf = t[i] - tTo;
      zc[i] = zTo + vzTo * tf - 0.5 * g * tf * tf;
      vc[i] = vzTo - g * tf;
      F[i] = 0;
      act[i] = 0;
      Wact[i] = Wfin;
      Dl[i] = Dfin; // Bilanz endet bei TO
    }
    xb[i] = -c.board.horiz * zb[i] * zb[i];
    Ek[i] = 0.5 * c.M * vc[i] * vc[i] + 0.5 * c.board.m_b * vb[i] * vb[i];
    Ep[i] = c.M * g * zc[i];
    Eb[i] = 0.5 * c.board.k_s * zb[i] * zb[i];
    l[i] = zc[i] - zb[i];
    const comp = c.l_td - l[i];
    El[i] = t[i] >= 0 && t[i] <= tTo && comp > 0 ? 0.5 * c.k_leg * comp * comp : 0;
  }
  return { t, z_c: zc, x_c: xc, v_c: vc, z_b: zb, x_b: xb, v_b: vb, F, act, E_kin: Ek, E_pot: Ep, E_board: Eb, E_leg: El, W_act: Wact, D_loss: Dl, l };
}

function Col2(Y: number[][], a: number, b: number): number[] {
  return Y.map((y) => y[a] + y[b]);
}
