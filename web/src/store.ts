/**
 * App-State (Zustand). Simulationen laufen im Web Worker; neueste Anfrage gewinnt.
 */
import { create } from 'zustand';
import type { Level1Result, ParamValues } from './sim-live/level1';
import type { WorkerRequest, WorkerResponse } from './sim-live/worker';
import { PARAM_BY_KEY, PRESETS, defaultStatus, defaultValues, validateValues, type Status } from './lib/params';

export interface Run { id: string; label: string; result: Level1Result; values: ParamValues }

export type StudyResult =
  | { kind: '1d'; key: string; values: number[]; out: Record<string, number[]>; ms: number }
  | { kind: '2d'; keyX: string; keyY: string; valuesX: number[]; valuesY: number[]; metric: string; grid: number[][]; ms: number };

interface State {
  values: ParamValues;
  status: Record<string, Status>;
  preset: string | null;
  result: Level1Result | null;
  error: string | null;
  computeMs: number;
  roundtripMs: number;
  pinned: Run[];
  time: number;
  playing: boolean;
  speed: number;
  view: 'sim' | 'study';
  study: StudyResult | null;
  studyProgress: number;
  setParam: (key: string, value: number | string) => void;
  toggleMeasured: (key: string) => void;
  applyPreset: (name: string) => void;
  loadProfile: (values: ParamValues, status: Record<string, Status>) => void;
  reset: () => void;
  pin: () => void;
  unpin: (id: string) => void;
  setTime: (t: number) => void;
  setPlaying: (p: boolean) => void;
  setSpeed: (s: number) => void;
  setView: (v: 'sim' | 'study') => void;
  runSweep1d: (key: string, values: number[], metrics: string[]) => void;
  runSweep2d: (keyX: string, valuesX: number[], keyY: string, valuesY: number[], metric: string) => void;
}

const worker = new Worker(new URL('./sim-live/worker.ts', import.meta.url), { type: 'module' });
let reqId = 0;
let latestRun = 0;
let latestStudy = 0;
const sentAt = new Map<number, number>();

function presetValues(name: string): ParamValues {
  return { ...defaultValues(), ...PRESETS[name].overrides };
}

export const useStore = create<State>((set, get) => {
  const run = (values: ParamValues) => {
    const errs = validateValues(values);
    if (errs.length) { set({ error: errs.join('; ') }); return; }
    const id = ++reqId;
    latestRun = id;
    sentAt.set(id, performance.now());
    worker.postMessage({ type: 'run', id, params: values } satisfies WorkerRequest);
  };

  worker.onmessage = (ev: MessageEvent<WorkerResponse>) => {
    const msg = ev.data;
    if (msg.type === 'run') {
      if (msg.id !== latestRun) return;
      const rt = performance.now() - (sentAt.get(msg.id) ?? performance.now());
      sentAt.delete(msg.id);
      const r = msg.result;
      const t = get().time;
      const tMin = r.series.t[0];
      const tMax = r.series.t[r.series.t.length - 1];
      set({ result: r, error: null, computeMs: msg.ms, roundtripMs: rt, time: Math.min(Math.max(t, tMin), tMax) });
    } else if (msg.type === 'error') {
      if (msg.id === latestRun) set({ error: msg.message });
      if (msg.id === latestStudy) set({ studyProgress: 0 });
    } else if (msg.type === 'progress') {
      if (msg.id === latestStudy) set({ studyProgress: msg.done / msg.total });
    } else if (msg.type === 'sweep1d') {
      if (msg.id !== latestStudy) return;
      const pending = pendingStudy as { key: string };
      set({ study: { kind: '1d', key: pending.key, values: msg.values, out: msg.out, ms: msg.ms }, studyProgress: 1 });
    } else if (msg.type === 'sweep2d') {
      if (msg.id !== latestStudy) return;
      const p = pendingStudy as { keyX: string; keyY: string; valuesX: number[]; valuesY: number[]; metric: string };
      set({ study: { kind: '2d', ...p, grid: msg.grid, ms: msg.ms }, studyProgress: 1 });
    }
  };

  let pendingStudy: unknown = null;
  const initial = presetValues('elite_w_58');
  setTimeout(() => run(initial), 0);

  return {
    values: initial,
    status: defaultStatus(),
    preset: 'elite_w_58',
    result: null,
    error: null,
    computeMs: 0,
    roundtripMs: 0,
    pinned: [],
    time: 0,
    playing: false,
    speed: 0.25,
    view: 'sim',
    study: null,
    studyProgress: 0,
    setParam: (key, value) => {
      const values = { ...get().values, [key]: value };
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
    reset: () => get().applyPreset('elite_w_58'),
    pin: () => {
      const { result, values, pinned, preset } = get();
      if (!result || pinned.length >= 3) return;
      const label = `${preset ? PRESETS[preset].label : 'Eigene'} · F ${values['board.fulcrum']}`;
      set({ pinned: [...pinned, { id: `${Date.now()}`, label, result, values }] });
    },
    unpin: (id) => set({ pinned: get().pinned.filter((p) => p.id !== id) }),
    setTime: (t) => set({ time: t }),
    setPlaying: (p) => set({ playing: p }),
    setSpeed: (s) => set({ speed: s }),
    setView: (v) => set({ view: v }),
    runSweep1d: (key, values, metrics) => {
      const id = ++reqId;
      latestStudy = id;
      pendingStudy = { key };
      set({ studyProgress: 0.001 });
      worker.postMessage({ type: 'sweep1d', id, params: get().values, key, values, metrics } satisfies WorkerRequest);
    },
    runSweep2d: (keyX, valuesX, keyY, valuesY, metric) => {
      const id = ++reqId;
      latestStudy = id;
      pendingStudy = { keyX, keyY, valuesX, valuesY, metric };
      set({ studyProgress: 0.001 });
      worker.postMessage({ type: 'sweep2d', id, params: get().values, keyX, valuesX, keyY, valuesY, metric } satisfies WorkerRequest);
    },
  };
});
