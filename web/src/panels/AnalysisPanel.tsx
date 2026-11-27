/** Modus B (SPEC 6.7, Etappe 6): Import gemessener Kinematik, inverse Dynamik, Matching. */
import { useEffect, useMemo, useState } from 'react';
import { LineChart } from '../charts/LineChart';
import { analyze, exampleTrc, jobStatus, startMatch, stopJob, type AnalysisResponse, type JobStatus, type MatchResult } from '../lib/api';
import { PARAM_BY_KEY } from '../lib/params';
import { JOINT_LABELS, POINTS, viewFromMeasurement } from '../lib/view';
import { useStore } from '../store';

const MULTI = ['var(--red)', '#F4F4F5', '#A1A1AA', '#71717A', '#FF4D4D', '#52525B'];
const DASH = [undefined, '6 3', '2 3', '10 3 2 3', '4 4', '1 3'];
const POINT_LABELS: Record<string, string> = {
  toe: 'Zehenspitze', ball: 'Ballen (MTP)', heel: 'Ferse', ankle: 'Sprunggelenk', knee: 'Knie', hip: 'Hüfte', shoulder: 'Schulter',
  neck: 'Hals (C7)', vertex: 'Kopf', elbow: 'Ellbogen', wrist: 'Handgelenk', fingertip: 'Fingerspitze', board_tip: 'Brettspitze',
};

interface Settings {
  horizontal: string; vertical: string; flip_horizontal: boolean; flip_vertical: boolean; unit: string;
  scale_m_per_px: number; origin: string; origin_x: number; origin_z: number; t_td: string; t_to: string;
}
const DEFAULTS: Settings = {
  horizontal: 'x', vertical: 'y', flip_horizontal: false, flip_vertical: false, unit: 'auto', scale_m_per_px: 0.002,
  origin: 'board_tip', origin_x: 0, origin_z: 0, t_td: '', t_to: '',
};

async function poll<R>(id: string, cb: (s: JobStatus<R>) => void) {
  for (;;) {
    const st = await jobStatus<R>(id);
    cb(st);
    if (st.status !== 'läuft') return st;
    await new Promise((r) => setTimeout(r, 800));
  }
}

export function AnalysisPanel() {
  const backend = useStore((s) => s.backend);
  const values = useStore((s) => s.values);
  const setMany = useStore((s) => s.setMany);
  const markMeasured = useStore((s) => s.markMeasured);
  const showView = useStore((s) => s.showView);
  const [file, setFile] = useState<{ name: string; text: string; note?: string } | null>(null);
  const [st, setSt] = useState<Settings>(DEFAULTS);
  const [cutoff, setCutoff] = useState('');
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [res, setRes] = useState<AnalysisResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [job, setJob] = useState<JobStatus<MatchResult> | null>(null);
  const [gens, setGens] = useState(10);
  const [pop, setPop] = useState(10);
  const [withInit, setWithInit] = useState(true);

  const pending = useStore((s) => s.pendingAnalysis);
  const setPending = useStore((s) => s.setPendingAnalysis);
  useEffect(() => {
    if (!pending) return;
    setFile({ name: pending.name, text: pending.text, note: 'aus dem Video-Tracker (Meter, Ursprung Brettspitze in Ruhe)' });
    setSt({ ...DEFAULTS, ...(pending.settings as Partial<Settings>) });
    setMapping({});
    setRes(null);
    setPending(null);
  }, [pending, setPending]);

  const athlete = useMemo(() => Object.fromEntries(Object.entries(values).filter(([k]) => !k.startsWith('numerics.model_level'))), [values]);

  if (!backend) {
    return <div className="study"><div className="placeholder" style={{ gridColumn: '1 / -1' }}>
      Die Analyse realer Sprünge (Modus B) rechnet im Python-Backend und ist nur in der <strong>Vollversion</strong> verfügbar (Start-Skript, siehe README).
    </div></div>;
  }

  const run = async () => {
    if (!file) return;
    setBusy(true);
    setErr(null);
    try {
      const settings: Record<string, unknown> = { ...st, t_td: st.t_td === '' ? null : Number(st.t_td), t_to: st.t_to === '' ? null : Number(st.t_to), mapping };
      const r = await analyze({ text: file.text, filename: file.name, overrides: athlete, settings, cutoff: cutoff === '' ? null : Number(cutoff) });
      setRes(r);
      setMapping(r.mapping);
      setJob(null);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onFile = async (f: File) => setFile({ name: f.name, text: await f.text() });
  const loadExample = async () => {
    const ex = await exampleTrc();
    setFile({ name: ex.filename, text: ex.text, note: ex.note });
    setSt(DEFAULTS);
    setMapping({});
  };

  const runMatch = async () => {
    if (!res) return;
    try {
      const { job: id } = await startMatch({ analysis_id: res.id, overrides: athlete, generations: gens, popsize: pop, with_init: withInit });
      await poll<MatchResult>(id, setJob);
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const applyMatch = () => {
    const r = job?.result;
    if (!r) return;
    const vals = Object.fromEntries(Object.entries(r.best_values).filter(([k]) => !k.startsWith('init.')));
    setMany(vals);
    markMeasured(Object.keys(vals));
  };

  const s = res?.series;
  const BW = (values['athlete.mass'] as number) * 9.81;
  const marks = res ? [{ x: 0, label: 'TD' }, { x: res.t_to, label: 'TO' }] : [];
  const m = res?.metrics;

  return (
    <div className="study analysis">
      <div className="study-form">
        <div className="footnote">Gemessene Kinematik (TRC aus OpenCap/Motion Capture oder CSV, z. B. Kinovea) → Filterung → inverse Dynamik → Matching (SPEC 6.7). Körpergröße/-masse/Geschlecht aus dem Parameter-Panel.</div>
        <label>Datei (.trc, .csv)
          <input type="file" accept=".trc,.csv,.txt" onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
        </label>
        <button type="button" className="btn ghost" onClick={loadExample}>Beispieldatensatz laden (synthetisch)</button>
        {file && <div className="mono footnote">Datei: {file.name}{file.note ? ` – ${file.note}` : ''}</div>}
        <details>
          <summary>Koordinaten & Einheiten</summary>
          <div className="grid2">
            <label>Achse → horizontal (Richtung Wasser)<select value={st.horizontal} onChange={(e) => setSt({ ...st, horizontal: e.target.value })}>{['x', 'y', 'z'].map((a) => <option key={a}>{a}</option>)}</select></label>
            <label>Achse → vertikal<select value={st.vertical} onChange={(e) => setSt({ ...st, vertical: e.target.value })}>{['x', 'y', 'z'].map((a) => <option key={a}>{a}</option>)}</select></label>
            <label className="check"><input type="checkbox" checked={st.flip_horizontal} onChange={(e) => setSt({ ...st, flip_horizontal: e.target.checked })} /> horizontal spiegeln</label>
            <label className="check"><input type="checkbox" checked={st.flip_vertical} onChange={(e) => setSt({ ...st, flip_vertical: e.target.checked })} /> vertikal spiegeln (Bild-y nach unten)</label>
            <label>Einheit<select value={st.unit} onChange={(e) => setSt({ ...st, unit: e.target.value })}>{['auto', 'm', 'cm', 'mm', 'px'].map((a) => <option key={a}>{a}</option>)}</select></label>
            {st.unit === 'px' && <label>Maßstab [m/px]<input type="number" step={0.0001} value={st.scale_m_per_px} onChange={(e) => setSt({ ...st, scale_m_per_px: Number(e.target.value) })} /></label>}
            <label>Ursprung<select value={st.origin} onChange={(e) => setSt({ ...st, origin: e.target.value })}><option value="board_tip">Brettspitzen-Marker (1. Bild)</option><option value="manual">manuell</option></select></label>
            {st.origin === 'manual' && <>
              <label>Ursprung horizontal [Dateieinheit]<input type="number" value={st.origin_x} onChange={(e) => setSt({ ...st, origin_x: Number(e.target.value) })} /></label>
              <label>Ursprung vertikal [Dateieinheit]<input type="number" value={st.origin_z} onChange={(e) => setSt({ ...st, origin_z: Number(e.target.value) })} /></label>
            </>}
          </div>
        </details>
        <details>
          <summary>Ereignisse & Filter</summary>
          <div className="grid2">
            <label>TD [s, Dateizeit] (leer = automatisch)<input type="number" step={0.001} value={st.t_td} onChange={(e) => setSt({ ...st, t_td: e.target.value })} /></label>
            <label>TO [s, Dateizeit] (leer = automatisch)<input type="number" step={0.001} value={st.t_to} onChange={(e) => setSt({ ...st, t_to: e.target.value })} /></label>
            <label>Grenzfrequenz [Hz] (leer = Residualanalyse)<input type="number" step={0.5} value={cutoff} onChange={(e) => setCutoff(e.target.value)} /></label>
          </div>
        </details>
        {res && (
          <details open={Object.values(res.mapping).some((v) => v === null)}>
            <summary>Markerzuordnung ({res.markers.length} Marker in der Datei)</summary>
            <table className="metric-table"><tbody>
              {[...POINTS, 'board_tip'].map((pt) => (
                <tr key={pt}><td>{POINT_LABELS[pt]}{res.required.includes(pt) ? ' *' : ''}</td><td>
                  <select value={mapping[pt] ?? ''} onChange={(e) => setMapping({ ...mapping, [pt]: e.target.value || null })}>
                    <option value="">– {res.required.includes(pt) ? 'fehlt!' : 'aus Modell ergänzen'} –</option>
                    {res.markers.map((n) => <option key={n} value={n}>{n}</option>)}
                  </select></td></tr>
              ))}
            </tbody></table>
          </details>
        )}
        <button type="button" className="btn primary" onClick={run} disabled={!file || busy}>{busy ? 'Analysiere …' : res ? 'Neu analysieren' : 'Analysieren'}</button>
        {err && <div className="warning">⚠ {err}</div>}
        {res && <>
          <hr className="sep" />
          <div className="panel-title">Matching (Kong/Yeadon/King)</div>
          <div className="footnote">Simulation startet im gemessenen TD-Zustand; CMA-ES schätzt T_max der Strecker, Aktivierungs-Timings{withInit ? ' und kleine Anfangswert-Korrekturen' : ''}. Ziel laut SPEC: RMS &lt; 10 %.</div>
          <label>Generationen <input type="number" min={1} max={60} value={gens} onChange={(e) => setGens(Number(e.target.value))} /></label>
          <label>Populationsgröße <input type="number" min={4} max={40} value={pop} onChange={(e) => setPop(Number(e.target.value))} /></label>
          <label className="check"><input type="checkbox" checked={withInit} onChange={(e) => setWithInit(e.target.checked)} /> Anfangsbedingungen innerhalb der Messunsicherheit anpassen</label>
          {job?.status === 'läuft'
            ? <button type="button" className="btn" onClick={() => stopJob(job.id)}>Abbrechen (Gen. {job.progress.generation ?? 0}/{job.progress.generations ?? gens}, Score {Number(job.progress.score ?? NaN).toFixed(1)} %)</button>
            : <button type="button" className="btn primary" onClick={runMatch}>Matching starten (~{Math.round(((gens * pop + 1) * 5) / 60 / 4)}–{Math.round(((gens * pop + 1) * 7) / 60 / 2)} min)</button>}
        </>}
      </div>

      <div className="study-out">
        {!res && <div className="placeholder">Noch keine Analyse. Ohne eigenes Video: „Beispieldatensatz laden“ → „Analysieren“.</div>}
        {res && s && m && <>
          {res.warnings.length > 0 && <div className="warning">{res.warnings.map((w) => <div key={w}>⚠ {w}</div>)}</div>}
          <div className="cards cards4">
            {[
              ['Kontaktzeit', m.t_contact, 's', 3], ['Peak F_z', m.F_peak_bw, 'BW', 2], ['v_z,TO', m.v_z_to, 'm/s', 2], ['v_x,TO', m.v_x_to, 'm/s', 2],
              ['H_y bei TO', m.H_y, 'kg m²/s', 1], ['h_max (aus TO)', m.h_max_board, 'm', 2], ['Grenzfrequenz', res.cutoff, 'Hz', 1], ['Residualkraft Flug', m.residual_flight_bw, 'BW', 2],
            ].map(([l, v, u, f]) => (
              <div key={l as string} className={`card ${l === 'Residualkraft Flug' && (v as number) > 0.5 ? 'warn' : ''}`}>
                <div className="card-label">{l as string}</div>
                <div className="card-value mono">{Number.isFinite(v as number) ? (v as number).toFixed(f as number) : '–'}<span className="unit">{u as string}</span></div>
              </div>
            ))}
          </div>
          <button type="button" className="btn ghost" onClick={() => showView(viewFromMeasurement(res, values))}>Messung im 3D-Viewer abspielen</button>
          {res.residual?.cutoffs && (
            <LineChart height={170} xLabel="Grenzfrequenz [Hz]" yLabel="Residuum [m]" xDomain={[3, res.residual.cutoffs[res.residual.cutoffs.length - 1]]} marks={[{ x: res.cutoff, label: `angewendet ${res.cutoff.toFixed(1)} Hz` }]}
              series={res.residual.residuals.map((r, i) => ({ name: ['Zehe', 'Sprunggelenk', 'Knie', 'Hüfte', 'Schulter', 'Handgelenk'][Math.floor(i / 2)] + (i % 2 ? ' z' : ' x'), x: res.residual!.cutoffs, y: r, color: MULTI[Math.floor(i / 2)], dash: i % 2 ? '4 3' : DASH[Math.floor(i / 2)], width: 1.1 }))} />
          )}
          {res.residual?.note && <div className="footnote">{res.residual.note}</div>}
          <LineChart height={200} xLabel="t [s] (0 = Touchdown)" yLabel="Brettkraft [BW] (inverse Dynamik)" marks={marks} xDomain={[-0.1, res.t_to + 0.1]}
            series={[
              { name: 'F_z', x: s.t, y: s.F.map((f) => f[1] / BW) },
              { name: 'F_x', x: s.t, y: s.F.map((f) => f[0] / BW), color: '#F4F4F5', dash: '6 3', width: 1.3 },
            ]} />
          <LineChart height={200} xLabel="t [s]" yLabel="Gelenkwinkel [°]" marks={marks} xDomain={[-0.1, res.t_to + 0.1]}
            series={JOINT_LABELS.map((n, j) => ({ name: n, x: s.t, y: s.theta_deg.map((r) => r[j]), color: MULTI[j], dash: DASH[j], width: j === 2 ? 2 : 1.3 }))} />
          <LineChart height={200} xLabel="t [s]" yLabel="Netto-Gelenkmoment [Nm]" marks={marks} xDomain={[-0.02, res.t_to + 0.02]}
            series={JOINT_LABELS.map((n, j) => {
              const unsure = res.uncertain_joints.includes(['mtp', 'ankle', 'knee', 'hip', 'shoulder', 'elbow'][j]);
              return { name: n + (unsure ? ' (unsicher)' : ''), x: s.t, y: s.tau.map((r) => r[j]), color: MULTI[j], dash: unsure ? '1 4' : DASH[j], width: unsure ? 1 : 1.5 };
            })} />
          {job?.result && <MatchView r={job.result} onApply={applyMatch} />}
          {job?.status === 'fehler' && <div className="warning">Matching fehlgeschlagen: {job.error}</div>}
        </>}
      </div>
    </div>
  );
}

function MatchView({ r, onApply }: { r: MatchResult; onApply: () => void }) {
  const x = Array.from({ length: r.target_theta.length }, (_, i) => i / (r.target_theta.length - 1));
  const ok = r.score < 10;
  return (
    <div className="match">
      <div className="panel-title">Matching-Ergebnis</div>
      <div className={`card ${ok ? 'primary' : 'warn'}`}>
        <div className="card-label">Score (gewichtetes RMS)</div>
        <div className="card-value mono">{r.score.toFixed(1)}<span className="unit">% (Start {r.baseline_score.toFixed(1)} %) {ok ? '✓ < 10 %' : '– Ziel < 10 % nicht erreicht'}</span></div>
      </div>
      <table className="metric-table">
        <thead><tr><th>Komponente</th><th className="num">Start</th><th className="num">Ergebnis</th></tr></thead>
        <tbody>{Object.keys(r.components).map((k) => <tr key={k}><td>{k}</td><td className="mono num">{r.baseline_components[k]?.toFixed(1)} %</td><td className="mono num strong">{r.components[k].toFixed(1)} %</td></tr>)}</tbody>
      </table>
      <LineChart height={190} xLabel="normierte Kontaktzeit" yLabel="Gelenkwinkel [°]"
        series={[1, 2].flatMap((j, i) => [
          { name: `${['Sprunggelenk', 'Knie', 'Hüfte', 'Schulter'][j]} Messung`, x, y: r.target_theta.map((t) => (t[j] * 180) / Math.PI), color: i ? '#F4F4F5' : 'var(--red)', width: 2 },
          { name: `${['Sprunggelenk', 'Knie', 'Hüfte', 'Schulter'][j]} Simulation`, x, y: r.sim_theta.map((t) => (t[j + 1] * 180) / Math.PI), color: i ? '#A1A1AA' : '#FF4D4D', dash: '6 3', width: 1.4 },
        ])} />
      <div className="panel-title">Subjektspezifische Kraftparameter</div>
      <table className="metric-table"><tbody>
        {Object.entries(r.factors).map(([k, f]) => (
          <tr key={k}><td>{PARAM_BY_KEY[k]?.label ?? k}</td><td className="mono num">{r.best_values[k].toFixed(0)} Nm</td><td className="mono num strong">×{f.toFixed(2)}</td><td className="unit">vs. generisch</td></tr>
        ))}
      </tbody></table>
      <button type="button" className="btn primary" onClick={onApply}>Als Athletenprofil übernehmen (Status „Gemessen“)</button>
      <div className="footnote">{r.evaluations} Simulationen. Übernommene Werte gelten für diese Athletin/diesen Athleten und dieses Brett; mit mehreren Sprüngen bestätigen (SPEC 9: mind. 5 Sprünge &lt; 10 %). Aus „Profil ↓“ als JSON speichern.</div>
    </div>
  );
}

