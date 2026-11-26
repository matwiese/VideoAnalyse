/** Backend-Anbindung (FastAPI, python -m api). Im Einzeldatei-Modus (file://) nicht verfügbar. */
import type { ParamValues } from '../sim-live/level1';

export interface Level2Series {
  t: number[]; Fz: number[]; Fx: number[]; F_points: number[][]; z_b: number[]; v_b: number[];
  com: number[][]; theta: number[][]; omega: number[][]; tau_act: number[][]; tau_pas: number[][]; tau_net: number[][];
  power: number[][]; act: number[][]; points: number[][]; H_seg: number[][]; E_mech: number[]; wobble: number[][]; acc: number[][];
  flight_t: number[]; flight_points: number[][]; flight_com: number[][]; flight_z_b: number[];
  hurdle_t?: number[]; hurdle_com_z?: number[]; hurdle_z_b?: number[]; hurdle_offset?: number[];
}

export interface Level2Response {
  level: 2;
  events: Record<string, number>;
  metrics_raw: Record<string, number | null>;
  warnings: string[];
  series: Level2Series;
  seconds: number;
}

export interface JobStatus<R = unknown> {
  id: string; kind: string; status: 'läuft' | 'fertig' | 'fehler' | 'abgebrochen';
  progress: Record<string, number>; result: R | null; error: string | null; started: number; finished?: number;
}

const BASE = '';

export async function apiAvailable(): Promise<boolean> {
  if (location.protocol === 'file:') return false;
  try {
    const r = await fetch(`${BASE}/api/health`, { signal: AbortSignal.timeout(1500) });
    return r.ok;
  } catch {
    return false;
  }
}

async function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal });
  if (!r.ok) throw new Error(`${r.status}: ${(await r.text()).slice(0, 300)}`);
  return r.json() as Promise<T>;
}

export function simulateLevel2(values: ParamValues, signal?: AbortSignal) {
  return post<Level2Response>('/api/simulate/level2', { overrides: values, series: true }, signal);
}

export function startOptimize(body: Record<string, unknown>) {
  return post<{ job: string; variables: string[] }>('/api/optimize', body);
}

export function startSweep(body: Record<string, unknown>) {
  return post<{ job: string }>('/api/sweep', body);
}

export async function jobStatus<R>(id: string): Promise<JobStatus<R>> {
  const r = await fetch(`${BASE}/api/jobs/${id}`);
  if (!r.ok) throw new Error(`Job ${id}: ${r.status}`);
  return r.json();
}

export async function stopJob(id: string) {
  await fetch(`${BASE}/api/jobs/${id}`, { method: 'DELETE' });
}

// --- Modus B -------------------------------------------------------------------
export interface AnalysisResponse {
  id: string; markers: string[]; mapping: Record<string, string | null>; required: string[]; rate: number; t_to: number; t_td_file: number;
  residual: { cutoffs: number[]; residuals: number[][]; fc_each: number[]; fc_residual: number; fc_applied: number; note: string } | Record<string, never>;
  cutoff: number; metrics: Record<string, number>; warnings: string[]; uncertain_joints: string[]; status: string;
  series: { t: number[]; points: number[][]; F: number[][]; cop: number[][]; tau: number[][]; power: number[][]; theta_deg: number[][];
    omega: number[][]; com: number[][]; H_y: number[]; board: number[][] | null };
}

export interface MatchResult {
  best_values: Record<string, number>; score: number; components: Record<string, number>; baseline_score: number;
  baseline_components: Record<string, number>; factors: Record<string, number>; sim_metrics: Record<string, number>;
  sim_theta: number[][]; target_theta: number[][]; history: { generation: number; best: number }[]; evaluations: number;
}

export function analyze(body: Record<string, unknown>) {
  return post<AnalysisResponse>('/api/analyze', body);
}

export async function exampleTrc(): Promise<{ filename: string; text: string; note: string }> {
  const r = await fetch(`${BASE}/api/example/trc`);
  if (!r.ok) throw new Error(`Beispiel: ${r.status}`);
  return r.json();
}

export function startMatch(body: Record<string, unknown>) {
  return post<{ job: string; variables: string[] }>('/api/match', body);
}
