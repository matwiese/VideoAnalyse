/** Parameterstudien (Modus C, SPEC 10.3): 1D-Sweep als Linie, 2D-Sweep als Heatmap. */
import { useMemo, useState } from 'react';
import { Heatmap } from '../charts/Heatmap';
import { LineChart } from '../charts/LineChart';
import { METRICS, METRIC_BY_KEY, PARAMS, PARAM_BY_KEY, rangeOf } from '../lib/params';
import { useStore } from '../store';

const SWEEPABLE = PARAMS.filter((p) => !p.options && !p.key.startsWith('numerics.') && p.min !== undefined && p.max !== undefined);
const OUTPUTS = METRICS.filter((m) => !m.level_min && m.key !== 'energy_balance_rel');

function linspace(a: number, b: number, n: number): number[] {
  return Array.from({ length: n }, (_, i) => +(a + ((b - a) * i) / (n - 1)).toPrecision(8));
}

function scaled(key: string, v: number): number {
  const m = METRIC_BY_KEY[key];
  return v * (m.scale ?? 1) * (key === 'z_b_min' ? -1 : 1);
}

export function StudyPanel() {
  const values = useStore((s) => s.values);
  const study = useStore((s) => s.study);
  const progress = useStore((s) => s.studyProgress);
  const run1 = useStore((s) => s.runSweep1d);
  const run2 = useStore((s) => s.runSweep2d);
  const [mode, setMode] = useState<'1d' | '2d'>('2d');
  const [kx, setKx] = useState('board.fulcrum');
  const [ky, setKy] = useState('athlete.mass');
  const [n, setN] = useState(17);
  const [metric, setMetric] = useState('h_max_board');
  const [metrics1d, setMetrics1d] = useState<string[]>(['h_max_board', 'v_z_to']);
  const px = PARAM_BY_KEY[kx];
  const py = PARAM_BY_KEY[ky];
  const [xmin, xmax] = rangeOf(px);
  const [ymin, ymax] = rangeOf(py);
  const [rx, setRx] = useState<[number, number] | null>(null);
  const [ry, setRy] = useState<[number, number] | null>(null);
  const xr = rx ?? [xmin, xmax];
  const yr = ry ?? [ymin, ymax];
  const busy = progress > 0 && progress < 1;

  const start = () => {
    if (mode === '1d') run1(kx, linspace(xr[0], xr[1], n), metrics1d);
    else run2(kx, linspace(xr[0], xr[1], n), ky, linspace(yr[0], yr[1], n), metric);
  };

  const chart = useMemo(() => {
    if (!study) return null;
    if (study.kind === '1d') {
      const p = PARAM_BY_KEY[study.key];
      return (
        <>
          {Object.entries(study.out).map(([mk, ys], i) => {
            const info = METRIC_BY_KEY[mk];
            return (
              <LineChart key={mk} height={200} xLabel={`${p.label} [${p.unit}]`} yLabel={`${info.label} [${info.unit}]`}
                series={[{ name: info.label, x: study.values, y: ys.map((v) => scaled(mk, v)), color: i === 0 ? 'var(--red)' : '#D4D4D8', dash: i === 0 ? undefined : '6 4' }]}
                cursor={values[study.key] as number} marks={[]} />
            );
          })}
          <div className="footnote mono">{study.values.length} Simulationen in {study.ms.toFixed(0)} ms</div>
        </>
      );
    }
    const info = METRIC_BY_KEY[study.metric];
    return (
      <>
        <Heatmap xs={study.valuesX} ys={study.valuesY} grid={study.grid.map((r) => r.map((v) => scaled(study.metric, v)))}
          xLabel={`${PARAM_BY_KEY[study.keyX].label} [${PARAM_BY_KEY[study.keyX].unit}]`}
          yLabel={`${PARAM_BY_KEY[study.keyY].label} [${PARAM_BY_KEY[study.keyY].unit}]`}
          zLabel={`${info.label} [${info.unit}]`} fmt={(v) => v.toFixed(info.fmt ?? 3)} />
        <div className="footnote mono">{study.valuesX.length * study.valuesY.length} Simulationen in {study.ms.toFixed(0)} ms</div>
      </>
    );
  }, [study, values]);

  const paramSelect = (val: string, set: (k: string) => void, reset: () => void, id: string) => (
    <select id={id} value={val} onChange={(e) => { set(e.target.value); reset(); }}>
      {SWEEPABLE.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
    </select>
  );

  return (
    <div className="study">
      <div className="study-form">
        <div className="seg" role="radiogroup" aria-label="Sweep-Art">
          <button type="button" className={mode === '1d' ? 'active' : ''} onClick={() => setMode('1d')} aria-pressed={mode === '1d'}>1D-Sweep</button>
          <button type="button" className={mode === '2d' ? 'active' : ''} onClick={() => setMode('2d')} aria-pressed={mode === '2d'}>2D-Heatmap</button>
        </div>
        <label>X-Parameter {paramSelect(kx, setKx, () => setRx(null), 'kx')}</label>
        <label className="pair">von <input type="number" value={xr[0]} onChange={(e) => setRx([Number(e.target.value), xr[1]])} /> bis <input type="number" value={xr[1]} onChange={(e) => setRx([xr[0], Number(e.target.value)])} /> {px.unit}</label>
        {mode === '2d' && <>
          <label>Y-Parameter {paramSelect(ky, setKy, () => setRy(null), 'ky')}</label>
          <label className="pair">von <input type="number" value={yr[0]} onChange={(e) => setRy([Number(e.target.value), yr[1]])} /> bis <input type="number" value={yr[1]} onChange={(e) => setRy([yr[0], Number(e.target.value)])} /> {py.unit}</label>
          <label>Zielgröße
            <select value={metric} onChange={(e) => setMetric(e.target.value)}>
              {OUTPUTS.map((m) => <option key={m.key + m.unit} value={m.key}>{m.label} [{m.unit}]</option>)}
            </select>
          </label>
        </>}
        {mode === '1d' && (
          <fieldset className="multi">
            <legend>Zielgrößen</legend>
            {['h_max_board', 'v_z_to', 'F_peak_bw', 'z_b_min', 't_contact', 'x_board_plane', 'W_act'].map((k) => (
              <label key={k} className="check">
                <input type="checkbox" checked={metrics1d.includes(k)} onChange={(e) => setMetrics1d(e.target.checked ? [...metrics1d, k] : metrics1d.filter((x) => x !== k))} />
                {METRIC_BY_KEY[k].label}
              </label>
            ))}
          </fieldset>
        )}
        <label>Stützstellen je Achse <input type="number" min={3} max={41} value={n} onChange={(e) => setN(Math.min(41, Math.max(3, Number(e.target.value))))} /></label>
        <button type="button" className="btn primary" onClick={start} disabled={busy}>{busy ? `Rechne … ${(progress * 100).toFixed(0)} %` : 'Studie starten'}</button>
        <div className="footnote">Alle übrigen Parameter wie im linken Panel. Level 1 im Web Worker; Ergebnisse tragen den Status der Eingangsparameter (meist Schätzung).</div>
      </div>
      <div className="study-out">{chart ?? <div className="placeholder">Noch keine Studie. Beispiel: Fulkrum × Körpermasse → max. Flughöhe.</div>}</div>
    </div>
  );
}
