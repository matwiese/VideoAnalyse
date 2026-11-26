/// <reference lib="webworker" />
/**
 * Web Worker: Level 1 live (SPEC 10.1) und Parameterstudien (1D/2D-Sweeps, SPEC 10.3).
 */
import { simulate, type Level1Result, type ParamValues } from './level1';

export type WorkerRequest =
  | { type: 'run'; id: number; params: ParamValues }
  | { type: 'sweep1d'; id: number; params: ParamValues; key: string; values: number[]; metrics: string[] }
  | { type: 'sweep2d'; id: number; params: ParamValues; keyX: string; valuesX: number[]; keyY: string; valuesY: number[]; metric: string };

export type WorkerResponse =
  | { type: 'run'; id: number; result: Level1Result; ms: number }
  | { type: 'sweep1d'; id: number; values: number[]; out: Record<string, number[]>; ms: number }
  | { type: 'sweep2d'; id: number; grid: number[][]; ms: number }
  | { type: 'progress'; id: number; done: number; total: number }
  | { type: 'error'; id: number; message: string };

const ctx = self as unknown as DedicatedWorkerGlobalScope;

function safeMetric(p: ParamValues, metric: string): number {
  try {
    const v = simulate(p, { series: false }).metrics[metric];
    return typeof v === 'number' ? v : NaN;
  } catch {
    return NaN;
  }
}

ctx.onmessage = (ev: MessageEvent<WorkerRequest>) => {
  const req = ev.data;
  const t0 = performance.now();
  try {
    if (req.type === 'run') {
      const result = simulate(req.params);
      const s = result.series;
      const buffers = Object.values(s).map((a: Float64Array) => a.buffer);
      ctx.postMessage({ type: 'run', id: req.id, result, ms: performance.now() - t0 } satisfies WorkerResponse, buffers);
    } else if (req.type === 'sweep1d') {
      const out: Record<string, number[]> = Object.fromEntries(req.metrics.map((m) => [m, [] as number[]]));
      req.values.forEach((x, i) => {
        let r: Level1Result | null = null;
        try { r = simulate({ ...req.params, [req.key]: x }, { series: false }); } catch { r = null; }
        for (const m of req.metrics) {
          const v = r?.metrics[m];
          out[m].push(typeof v === 'number' ? v : NaN);
        }
        if (i % 5 === 0) ctx.postMessage({ type: 'progress', id: req.id, done: i + 1, total: req.values.length } satisfies WorkerResponse);
      });
      ctx.postMessage({ type: 'sweep1d', id: req.id, values: req.values, out, ms: performance.now() - t0 } satisfies WorkerResponse);
    } else if (req.type === 'sweep2d') {
      const grid: number[][] = [];
      const total = req.valuesX.length * req.valuesY.length;
      let done = 0;
      for (const y of req.valuesY) {
        const row: number[] = [];
        for (const x of req.valuesX) {
          row.push(safeMetric({ ...req.params, [req.keyX]: x, [req.keyY]: y }, req.metric));
          done++;
        }
        grid.push(row);
        ctx.postMessage({ type: 'progress', id: req.id, done, total } satisfies WorkerResponse);
      }
      ctx.postMessage({ type: 'sweep2d', id: req.id, grid, ms: performance.now() - t0 } satisfies WorkerResponse);
    }
  } catch (e) {
    ctx.postMessage({ type: 'error', id: req.id, message: e instanceof Error ? e.message : String(e) } satisfies WorkerResponse);
  }
};
