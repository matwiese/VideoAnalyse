/**
 * Parameterdefinitionen aus data/parameters.json (gemeinsame Quelle mit Python),
 * validiert mit Zod (SPEC Kap. 8).
 */
import { z } from 'zod';
import rawParams from '@data/parameters.json';
import rawPresets from '@data/presets.json';
import rawMetrics from '@data/metrics.json';
import type { ParamValues } from '../sim-live/level1';

export const StatusSchema = z.enum(['Literatur', 'Schätzung', 'Gemessen', 'Eingabe']);
export type Status = z.infer<typeof StatusSchema>;

const ParamSpecSchema = z.object({
  value: z.union([z.number(), z.string()]),
  unit: z.string(),
  source: z.string(),
  status: StatusSchema,
  label: z.string().optional(),
  min: z.number().optional(),
  max: z.number().optional(),
  step: z.number().optional(),
  options: z.array(z.string()).optional(),
});
export type ParamSpec = z.infer<typeof ParamSpecSchema> & { key: string; group: string };

export const GROUP_LABELS: Record<string, string> = {
  athlete: 'Athlet:in',
  board: 'Brett',
  technique: 'Technik',
  leg: 'Bein / Muskel (Level 1)',
  activation: 'Aktivierung',
  flight: 'Flug / Rotation',
  numerics: 'Numerik',
};

function flatten(): ParamSpec[] {
  const out: ParamSpec[] = [];
  for (const [group, entries] of Object.entries(rawParams as Record<string, unknown>)) {
    if (group.startsWith('_')) continue;
    for (const [name, spec] of Object.entries(entries as Record<string, unknown>)) {
      const parsed = ParamSpecSchema.parse(spec);
      out.push({ ...parsed, key: `${group}.${name}`, group });
    }
  }
  return out;
}

export const PARAMS: ParamSpec[] = flatten();
export const PARAM_BY_KEY: Record<string, ParamSpec> = Object.fromEntries(PARAMS.map((p) => [p.key, p]));

export function defaultValues(): ParamValues {
  return Object.fromEntries(PARAMS.map((p) => [p.key, p.value]));
}
export function defaultStatus(): Record<string, Status> {
  return Object.fromEntries(PARAMS.map((p) => [p.key, p.status]));
}

export const PresetsSchema = z.record(z.object({ label: z.string(), overrides: z.record(z.union([z.number(), z.string()])) }));
export const PRESETS = PresetsSchema.parse((rawPresets as { presets: unknown }).presets);

/** Wertebereich eines numerischen Parameters für Slider (Fallback ±50 %). */
export function rangeOf(p: ParamSpec): [number, number, number] {
  const v = p.value as number;
  const min = p.min ?? (v === 0 ? -1 : v - Math.abs(v) * 0.5);
  const max = p.max ?? (v === 0 ? 1 : v + Math.abs(v) * 0.5);
  const step = p.step ?? niceStep((max - min) / 200);
  return [min, max, step];
}
function niceStep(x: number): number {
  const e = Math.pow(10, Math.floor(Math.log10(x)));
  const f = x / e;
  return (f < 2 ? 1 : f < 5 ? 2 : 5) * e;
}

/** Athletenprofil (JSON-Export/-Import, SPEC Kap. 8). */
export const ProfileSchema = z.object({
  app: z.literal('3m-brett-simulator'),
  version: z.number(),
  name: z.string(),
  values: z.record(z.union([z.number(), z.string()])),
  status: z.record(StatusSchema),
});
export type Profile = z.infer<typeof ProfileSchema>;

export function validateValues(values: ParamValues): string[] {
  const errs: string[] = [];
  for (const [k, v] of Object.entries(values)) {
    const p = PARAM_BY_KEY[k];
    if (!p) { errs.push(`Unbekannter Parameter ${k}`); continue; }
    if (typeof v === 'number') {
      if (p.min !== undefined && v < p.min - 1e-12) errs.push(`${p.label ?? k}: ${v} < ${p.min}`);
      if (p.max !== undefined && v > p.max + 1e-12) errs.push(`${p.label ?? k}: ${v} > ${p.max}`);
    } else if (p.options && !p.options.includes(v)) errs.push(`${p.label ?? k}: ${v}`);
  }
  return errs;
}

// --- Ausgabegrößen ---------------------------------------------------------
export interface MetricInfo {
  key: string; label: string; unit: string; cat: string; deps: string; fmt?: number; scale?: number; primary?: boolean; level_min?: number;
}
export const METRICS: MetricInfo[] = (rawMetrics as { metrics: MetricInfo[] }).metrics;
export const METRIC_DEPS: Record<string, string[]> = (rawMetrics as { _meta: { deps: Record<string, string[]> } })._meta.deps;
export const METRIC_BY_KEY: Record<string, MetricInfo> = Object.fromEntries(METRICS.map((m) => [m.key, m]));
