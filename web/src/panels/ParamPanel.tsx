/**
 * Parameter-Panel (SPEC 10.3 links): Gruppen, Slider, Status-Markierung, Quellen-Tooltip.
 * Klick auf das Status-Badge markiert einen Literatur-/Schätzwert als „Gemessen“.
 */
import { useState } from 'react';
import { GROUP_LABELS, PARAMS, PRESETS, rangeOf, type ParamSpec, type Status } from '../lib/params';
import { useStore } from '../store';

const HIDDEN = new Set(['numerics.model_level', 'board.m_k', 'board.c_k', 'board.length', 'board.width', 'board.board_mass', 'board.height_above_water', 'numerics.output_rate', 'numerics.event_tol']);
const ORDER: Record<1 | 2, string[]> = {
  1: ['athlete', 'board', 'technique', 'leg', 'activation', 'flight', 'numerics'],
  2: ['athlete', 'board', 'technique', 'posture', 'act2', 'torque', 'contact', 'rom', 'body', 'wobble', 'flight', 'numerics'],
};
const COLLAPSED_DEFAULT = new Set(['activation', 'flight', 'numerics', 'leg', 'act2', 'torque', 'contact', 'rom', 'body', 'wobble']);
const L1_ONLY = new Set(['numerics.dt', 'technique.approach_speed', 'technique.approach_steps']);
const L2_ONLY = new Set(['numerics.rtol2', 'numerics.max_step2']);

export function StatusBadge({ status, onClick, title }: { status: Status | string; onClick?: () => void; title?: string }) {
  const cls = status === 'Schätzung' ? 'badge est' : status === 'Gemessen' ? 'badge meas' : status === 'Literatur' ? 'badge lit' : 'badge';
  const short = status === 'Schätzung' ? 'S' : status === 'Gemessen' ? 'G' : status === 'Literatur' ? 'L' : status === 'Eingabe' ? 'E' : status === 'Berechnet' ? 'B' : '–';
  return (
    <button type="button" className={cls} onClick={onClick} title={title ?? status} aria-label={`Status: ${status}`} disabled={!onClick}>
      {short}
    </button>
  );
}

function hiddenFor(p: ParamSpec, mode: string, model: string, level: 1 | 2): boolean {
  if (HIDDEN.has(p.key)) return true;
  if (level === 2 && L1_ONLY.has(p.key)) return true;
  if (level === 1 && L2_ONLY.has(p.key)) return true;
  if (level === 2 && p.key === 'posture.ankle' && useStore.getState().values['posture.align'] === 'ja') return true;
  const hurdleOnly = ['technique.hurdle_height', 'technique.board_z_hurdle', 'technique.board_v_hurdle'];
  const tdOnly = ['technique.v_z_td', 'technique.board_z_td', 'technique.board_v_td'];
  if (mode === 'hurdle' && tdOnly.includes(p.key)) return true;
  if (mode !== 'hurdle' && hurdleOnly.includes(p.key)) return true;
  if (model !== 'B' && (p.key === 'board.span_75' || p.key === 'board.overhang_75')) return true;
  return false;
}

function ParamRow({ p }: { p: ParamSpec }) {
  const value = useStore((s) => s.values[p.key]);
  const status = useStore((s) => s.status[p.key]);
  const setParam = useStore((s) => s.setParam);
  const toggle = useStore((s) => s.toggleMeasured);
  const tip = `${p.label ?? p.key}\nQuelle: ${p.source}\nStatus: ${status}${p.status !== 'Eingabe' ? '\n(Klick auf Badge: als „Gemessen“ markieren)' : ''}`;
  const changed = value !== p.value;
  if (p.options) {
    return (
      <div className={`param ${status === 'Schätzung' ? 'is-est' : ''}`} title={tip}>
        <div className="param-head">
          <label htmlFor={p.key}>{p.label}</label>
          <StatusBadge status={status} />
        </div>
        <select id={p.key} value={String(value)} onChange={(e) => setParam(p.key, e.target.value)}>
          {p.options.map((o) => <option key={o} value={o}>{optionLabel(p.key, o)}</option>)}
        </select>
      </div>
    );
  }
  const [min, max, step] = rangeOf(p);
  const v = value as number;
  return (
    <div className={`param ${status === 'Schätzung' ? 'is-est' : ''}`} title={tip}>
      <div className="param-head">
        <label htmlFor={p.key}>{p.label}{changed && <span className="changed" title={`Default ${p.value}`}>•</span>}</label>
        <StatusBadge status={status} onClick={p.status !== 'Eingabe' ? () => toggle(p.key) : undefined} title={tip} />
      </div>
      <div className="param-input">
        <input type="range" id={p.key} min={min} max={max} step={step} value={v}
          onChange={(e) => setParam(p.key, Number(e.target.value))} aria-label={p.label} />
        <input type="number" className="mono" min={min} max={max} step={step} value={+v.toPrecision(6)}
          onChange={(e) => { const x = Number(e.target.value); if (Number.isFinite(x) && x >= min && x <= max) setParam(p.key, x); }} aria-label={`${p.label} Wert`} />
        <span className="unit">{p.unit}</span>
      </div>
    </div>
  );
}

function optionLabel(key: string, o: string): string {
  if (key === 'athlete.sex') return o === 'w' ? 'weiblich' : 'männlich';
  if (key === 'board.fulcrum_model') return o === 'A' ? 'A – empirisch linear' : 'B – Balkentheorie';
  if (key === 'technique.start_mode') return o === 'hurdle' ? 'Hürde (P3)' : 'Touchdown (P4)';
  if (key === 'contact.board_slope') return o === 'beam' ? 'aus Biegelinie' : 'keine Neigung';
  return o;
}

export function ParamPanel() {
  const [collapsed, setCollapsed] = useState<Set<string>>(COLLAPSED_DEFAULT);
  const mode = useStore((s) => s.values['technique.start_mode'] as string);
  const model = useStore((s) => s.values['board.fulcrum_model'] as string);
  const preset = useStore((s) => s.preset);
  const level = useStore((s) => s.level);
  useStore((s) => s.values['posture.align']);
  const applyPreset = useStore((s) => s.applyPreset);
  const toggle = (g: string) => {
    const n = new Set(collapsed);
    if (n.has(g)) n.delete(g); else n.add(g);
    setCollapsed(n);
  };
  return (
    <aside className="panel params" aria-label="Parameter">
      <div className="panel-title">Parameter</div>
      <div className="param">
        <label htmlFor="preset">Preset</label>
        <select id="preset" value={preset ?? ''} onChange={(e) => e.target.value && applyPreset(e.target.value)}>
          <option value="">– eigene Werte –</option>
          {Object.entries(PRESETS).map(([k, p]) => <option key={k} value={k}>{p.label}</option>)}
        </select>
      </div>
      <div className="legend-status">
        <StatusBadge status="Literatur" /> Literatur <StatusBadge status="Schätzung" /> Schätzung <StatusBadge status="Gemessen" /> Gemessen <StatusBadge status="Eingabe" /> Eingabe
      </div>
      {ORDER[level].map((g) => {
        const items = PARAMS.filter((p) => p.group === g && !hiddenFor(p, mode, model, level));
        const open = !collapsed.has(g);
        return (
          <section key={g} className="group">
            <button type="button" className="group-head" onClick={() => toggle(g)} aria-expanded={open}>
              <span>{GROUP_LABELS[g] ?? g}</span><span className="chev">{open ? '−' : '+'}</span>
            </button>
            {open && items.map((p) => <ParamRow key={p.key} p={p} />)}
          </section>
        );
      })}
      <section className="group">
        <button type="button" className="group-head" disabled><span>3D (Level 3)</span><span className="chev">ab Etappe 7</span></button>
      </section>
    </aside>
  );
}
