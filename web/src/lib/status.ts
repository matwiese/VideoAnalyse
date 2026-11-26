/**
 * Statusableitung der Ausgabegrößen – Port von core/report.py.
 * Status = schwächster Status der Eingangsparameter: Schätzung > Literatur > Gemessen > Eingabe.
 */
import type { ParamValues } from '../sim-live/level1';
import { METRIC_DEPS, PARAMS, type MetricInfo, type Status } from './params';

const RANK: Record<Status, number> = { Eingabe: 0, Gemessen: 1, Literatur: 2, 'Schätzung': 3 };

export function resolveDeps(group: string, v: ParamValues): string[] {
  if (group === 'numerics') return [];
  if (group === 'start') {
    return v['technique.start_mode'] === 'hurdle'
      ? ['technique.hurdle_height', 'technique.board_z_hurdle', 'technique.board_v_hurdle']
      : ['technique.v_z_td', 'technique.board_z_td', 'technique.board_v_td'];
  }
  const out: string[] = [];
  for (const item of METRIC_DEPS[group] ?? []) {
    if (item.startsWith('@')) out.push(...resolveDeps(item.slice(1), v));
    else if (item.endsWith('.*')) {
      const prefix = item.slice(0, -1);
      out.push(...PARAMS.filter((p) => p.key.startsWith(prefix)).map((p) => p.key));
    } else if (item.endsWith('?')) {
      const key = item.slice(0, -1);
      if (key === 'board.mb_exponent' && v['board.fulcrum'] !== 7.5) out.push(key);
      if ((key === 'board.span_75' || key === 'board.overhang_75') && v['board.fulcrum_model'] === 'B') out.push(key);
    } else out.push(item);
  }
  return Array.from(new Set(out));
}

export type MetricStatus = Status | 'Berechnet' | 'n/a';

/** Level 2 nutzt eigene Abhängigkeitsgruppen (wie core/report.py deps_for_level). */
export function depsForLevel(group: string, level: number): string {
  return level >= 2 && (group === 'sim' || group === 'sim_flight') ? group.replace('sim', 'sim2') : group;
}

export function metricStatus(m: MetricInfo, v: ParamValues, st: Record<string, Status>, level = 1): { status: MetricStatus; estimates: string[] } {
  if ((m.level_min ?? 1) > level) return { status: 'n/a', estimates: [] };
  const deps = resolveDeps(depsForLevel(m.deps, level), v);
  if (deps.length === 0) return { status: 'Berechnet', estimates: [] };
  let worst: Status = 'Eingabe';
  for (const k of deps) if (RANK[st[k]] > RANK[worst]) worst = st[k];
  return { status: worst, estimates: deps.filter((k) => st[k] === 'Schätzung') };
}

export function formatMetric(m: MetricInfo, raw: number | null | undefined): string {
  if (raw === null || raw === undefined) return `– (ab Level ${m.level_min ?? 2})`;
  let x = raw * (m.scale ?? 1);
  if (m.key === 'z_b_min') x = Math.abs(x);
  if (!Number.isFinite(x)) return '–';
  return x.toLocaleString('de-DE', { minimumFractionDigits: m.fmt ?? 3, maximumFractionDigits: m.fmt ?? 3 });
}
