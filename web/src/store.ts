/**
 * App-State (Zustand). Level 1 läuft im Web Worker (neueste Anfrage gewinnt),
 * Level 2, Optimierung und Level-2-Studien im Backend (python -m api).
 */
import { create } from 'zustand';
import SimWorker from './sim-live/worker.ts?worker&inline';
import { makeBoard, type ParamValues } from './sim-live/level1';
import type { WorkerRequest, WorkerResponse } from './sim-live/worker';
import { apiAvailable, jobStatus, simulateLevel2, startOptimize, startSweep, stopJob, type JobStatus } from './lib/api';
import { PARAM_BY_KEY, PRESETS, defaultStatus, defaultValues, validateValues, type Status } from './lib/params';
import { viewFromLevel1, viewFromLevel2, type View } from './lib/view';

export interface Run { id: string; label: string; view: View; values: ParamValues }

export type StudyResult =
  | { kind: '1d'; key: string; values: number[]; out: Record<string, number[]>; ms: number }
  | { kind: '2d'; keyX: string; keyY: string; valuesX: number[]; valuesY: number[]; metric: string; grid: number[][]; ms: number };

export interface OptResult {
  best_values: Record<string, number>; best_score: number; best_metrics: Record<string, number | null>;
  baseline_metrics: Record<string, number | null>; baseline_score: number;
  history: { generation: number; best: number; mean: number }[]; evaluations: number; variables: string[];
}

interface SweepResult { key_x: string; xs: number[]; key_y: string | null; ys: number[] | null; results: Record<string, number | null>[] }

interface State {
  values: ParamValues;
  status: Record<string, Status>;
  preset: string | null;
  level: 1 | 2;
  backend: boolean | null;
  view: View | null;
  busy: boolean;
  error: string | null;
  computeMs: number;
  roundtripMs: number;
  pinned: Run[];
  time: number;
  playing: boolean;
  speed: number;
  page: 'sim' | 'study' | 'opt' | 'ana' | 'track';
  pendingAnalysis: { name: string; text: string; settings: Record<string, unknown> } | null;
  setPendingAnalysis: (p: { name: string; text: string; settings: Record<string, unknown> } | null) => void;
  study: StudyResult | null;
  studyProgress: number;
  optJob: JobStatus<OptResult> | null;
  setParam: (key: string, value: number | string) => void;
  setMany: (values: Record<string, number | string>) => void;
  toggleMeasured: (key: string) => void;
  applyPreset: (name: string) => void;
  loadProfile: (values: ParamValues, status: Record<string, Status>) => void;
  setLevel: (l: 1 | 2) => void;
  pin: () => void;
  unpin: (id: string) => void;
  setTime: (t: number) => void;
  setPlaying: (p: boolean) => void;
  setSpeed: (s: number) => void;
  setPage: (v: 'sim' | 'study' | 'opt' | 'ana' | 'track') => void;
  markMeasured: (keys: string[]) => void;
  showView: (v: View) => void;
  runSweep1d: (key: string, values: number[], metrics: string[], level: 1 | 2) => void;
  runSweep2d: (keyX: string, valuesX: number[], keyY: string, valuesY: number[], metric: string, level: 1 | 2) => void;
  runOptimize: (body: Record<string, unknown>) => Promise<void>;
  stopOptimize: () => void;
}

const worker = new SimWorker();
let reqId = 0;
let latestRun = 0;
let latestStudy = 0;
const sentAt = new Map<number, number>();
let l2Abort: AbortController | null = null;
let l2Timer: ReturnType<typeof setTimeout> | null = null;

function presetValues(name: string): ParamValues {
  return { ...defaultValues(), ...PRESETS[name].overrides };
}

function geomFor(values: ParamValues): View['geom'] {
  const b = makeBoard(values);
  const H = values['athlete.height'] as number;
  return { H, M: values['athlete.mass'] as number, d: b.d, overhang: b.overhang, span: b.span, l_td: (values['leg.l_td_ratio'] as number) * H, l_max: (values['leg.l_max_ratio'] as number) * H };
}

async function poll<R>(id: string, onUpdate: (s: JobStatus<R>) => void): Promise<JobStatus<R>> {
  for (;;) {
    const st = await jobStatus<R>(id);
    onUpdate(st);
    if (st.status !== 'läuft') return st;
    await new Promise((r) => setTimeout(r, 700));
  }
}

export const useStore = create<State>((set, get) => {
  const clampTime = (v: View) => {
    const t = get().time;
    return Math.min(Math.max(t, v.t[0]), v.t[v.t.length - 1]);
  };

  const runL1 = (values: ParamValues) => {
    const id = ++reqId;
    latestRun = id;
    sentAt.set(id, performance.now());
    worker.postMessage({ type: 'run', id, params: values } satisfies WorkerRequest);
  };

  const runL2 = (values: ParamValues) => {
    if (l2Timer) clearTimeout(l2Timer);
    l2Timer = setTimeout(async () => {
      l2Abort?.abort();
      l2Abort = new AbortController();
      const t0 = performance.now();
      set({ busy: true });
      try {
        const r = await simulateLevel2(values, l2Abort.signal);
        const v = viewFromLevel2(r, values, geomFor(values));
        set({ view: v, busy: false, error: null, computeMs: r.seconds * 1000, roundtripMs: performance.now() - t0, time: clampTime(v) });
      } catch (e) {
        if ((e as Error).name === 'AbortError') return;
        set({ busy: false, error: `Level 2: ${(e as Error).message}` });
      }
    }, 350);
  };

  const run = (values: ParamValues) => {
    const errs = validateValues(values);
    if (errs.length) { set({ error: errs.join('; ') }); return; }
    if (get().level === 2) runL2(values); else runL1(values);
  };

  let pendingStudy: unknown = null;

  worker.onmessage = (ev: MessageEvent<WorkerResponse>) => {
    const msg = ev.data;
    if (msg.type === 'run') {
      if (msg.id !== latestRun || get().level !== 1) return;
      const rt = performance.now() - (sentAt.get(msg.id) ?? performance.now());
      sentAt.delete(msg.id);
      const v = viewFromLevel1(msg.result);
      set({ view: v, error: null, computeMs: msg.ms, roundtripMs: rt, time: clampTime(v) });
    } else if (msg.type === 'error') {
      if (msg.id === latestRun) set({ error: msg.message });
      if (msg.id === latestStudy) set({ studyProgress: 0 });
    } else if (msg.type === 'progress') {
      if (msg.id === latestStudy) set({ studyProgress: msg.done / msg.total });
    } else if (msg.type === 'sweep1d') {
      if (msg.id !== latestStudy) return;
      set({ study: { kind: '1d', key: (pendingStudy as { key: string }).key, values: msg.values, out: msg.out, ms: msg.ms }, studyProgress: 1 });
    } else if (msg.type === 'sweep2d') {
      if (msg.id !== latestStudy) return;
      const p = pendingStudy as { keyX: string; keyY: string; valuesX: number[]; valuesY: number[]; metric: string };
      set({ study: { kind: '2d', ...p, grid: msg.grid, ms: msg.ms }, studyProgress: 1 });
    }
  };

  const initial = presetValues('elite_w_58');
  setTimeout(() => run(initial), 0);
  apiAvailable().then((ok) => set({ backend: ok }));

  const backendSweep = async (body: Record<string, unknown>, finish: (r: SweepResult, ms: number) => void) => {
    const id = ++reqId;
    latestStudy = id;
    set({ studyProgress: 0.001 });
    const t0 = performance.now();
    try {
      const { job } = await startSweep(body);
      const st = await poll<SweepResult>(job, (s) => {
        if (latestStudy === id && s.progress.total) set({ studyProgress: Math.max(0.001, s.progress.done / s.progress.total) });
      });
      if (latestStudy !== id) return;
      if (st.status !== 'fertig' || !st.result) throw new Error(st.error ?? st.status);
      finish(st.result, performance.now() - t0);
    } catch (e) {
      set({ error: `Studie: ${(e as Error).message}`, studyProgress: 0 });
    }
  };

  return {
    values: initial,
    status: defaultStatus(),
    preset: 'elite_w_58',
    level: 1,
    backend: null,
    view: null,
    busy: false,
    error: null,
    computeMs: 0,
    roundtripMs: 0,
    pinned: [],
    time: 0,
    playing: false,
    speed: 0.25,
    page: 'sim',
    study: null,
    studyProgress: 0,
    optJob: null,
    pendingAnalysis: null,
    setPendingAnalysis: (p) => set({ pendingAnalysis: p }),
    setParam: (key, value) => {
      const values = { ...get().values, [key]: value };
      set({ values, preset: null });
      run(values);
    },
    setMany: (vals) => {
      const values = { ...get().values, ...vals };
      set({ values, preset: null });
      run(values);
    },
    toggleMeasured: (key) => {
      const cur = get().status[key];
      const orig = PARAM_BY_KEY[key].status;
      if (orig === 'Eingabe') return;
      set({ status: { ...get().status, [key]: cur === 'Gemessen' ? orig : 'Gemessen' } });
    },
    applyPreset: (name) => {
      const values = presetValues(name);
      set({ values, preset: name });
      run(values);
    },
    loadProfile: (values, status) => {
      const merged = { ...defaultValues(), ...values };
      set({ values: merged, status: { ...defaultStatus(), ...status }, preset: null });
      run(merged);
    },
    setLevel: (l) => {
      if (l === 2 && !get().backend) return;
      set({ level: l, pinned: [] });
      run(get().values);
    },
    pin: () => {
      const { view, values, pinned, preset, level } = get();
      if (!view || pinned.length >= 3) return;
      const label = `L${level} · ${preset ? PRESETS[preset].label : 'Eigene'} · F ${values['board.fulcrum']}`;
      set({ pinned: [...pinned, { id: `${Date.now()}`, label, view, values }] });
    },
    unpin: (id) => set({ pinned: get().pinned.filter((p) => p.id !== id) }),
    setTime: (t) => set({ time: t }),
    setPlaying: (p) => set({ playing: p }),
    setSpeed: (s) => set({ speed: s }),
    setPage: (v) => set({ page: v }),
    markMeasured: (keys) => set({ status: { ...get().status, ...Object.fromEntries(keys.filter((k) => PARAM_BY_KEY[k]).map((k) => [k, 'Gemessen' as Status])) } }),
    showView: (v) => set({ view: v, page: 'sim', time: 0, playing: false }),
    runSweep1d: (key, values, metrics, level) => {
      if (level === 2) {
        void backendSweep({ level: 2, overrides: get().values, key_x: key, xs: values }, (r, ms) => {
          const out = Object.fromEntries(metrics.map((m) => [m, r.results.map((x) => (x[m] ?? NaN) as number)]));
          set({ study: { kind: '1d', key, values, out, ms }, studyProgress: 1 });
        });
        return;
      }
      const id = ++reqId;
      latestStudy = id;
      pendingStudy = { key };
      set({ studyProgress: 0.001 });
      worker.postMessage({ type: 'sweep1d', id, params: get().values, key, values, metrics } satisfies WorkerRequest);
    },
    runSweep2d: (keyX, valuesX, keyY, valuesY, metric, level) => {
      if (level === 2) {
        void backendSweep({ level: 2, overrides: get().values, key_x: keyX, xs: valuesX, key_y: keyY, ys: valuesY }, (r, ms) => {
          const grid = valuesY.map((_, j) => valuesX.map((__, i) => (r.results[j * valuesX.length + i][metric] ?? NaN) as number));
          set({ study: { kind: '2d', keyX, keyY, valuesX, valuesY, metric, grid, ms }, studyProgress: 1 });
        });
        return;
      }
      const id = ++reqId;
      latestStudy = id;
      pendingStudy = { keyX, keyY, valuesX, valuesY, metric };
      set({ studyProgress: 0.001 });
      worker.postMessage({ type: 'sweep2d', id, params: get().values, keyX, valuesX, keyY, valuesY, metric } satisfies WorkerRequest);
    },
    runOptimize: async (body) => {
      try {
        const { job } = await startOptimize({ ...body, overrides: get().values });
        await poll<OptResult>(job, (s) => set({ optJob: s }));
      } catch (e) {
        set({ error: `Optimierung: ${(e as Error).message}` });
      }
    },
    stopOptimize: () => {
      const j = get().optJob;
      if (j) void stopJob(j.id);
    },
  };
});
