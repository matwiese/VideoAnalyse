/** Optimierung der Aktivierungs-Timings (Modus A, SPEC 6.6) – läuft im Backend. */
import { useState } from 'react';
import { LineChart } from '../charts/LineChart';
import { METRIC_BY_KEY, PARAM_BY_KEY } from '../lib/params';
import { useStore } from '../store';

const COMPARE = ['h_max_board', 'v_z_to', 'v_x_to', 'rotation_potential', 'H_y', 'x_body_board_plane', 'x_board_plane', 't_contact', 'F_peak_bw', 'knee_omega_to', 'knee_angle_to_deg'];

export function OptPanel() {
  const backend = useStore((s) => s.backend);
  const job = useStore((s) => s.optJob);
  const run = useStore((s) => s.runOptimize);
  const stop = useStore((s) => s.stopOptimize);
  const setMany = useStore((s) => s.setMany);
  const setLevel = useStore((s) => s.setLevel);
  const [level, setLvl] = useState<1 | 2>(2);
  const [objective, setObjective] = useState('height');
  const [wR, setWR] = useState(0.5);
  const [clear, setClear] = useState(0.5);
  const [gens, setGens] = useState(8);
  const [pop, setPop] = useState(8);
  const [robust, setRobust] = useState(true);
  const running = job?.status === 'läuft';
  const sims = (gens * pop + 1) * (robust ? 3 : 1);

  if (!backend) {
    return (
      <div className="study"><div className="placeholder" style={{ gridColumn: '1 / -1' }}>
        Die Optimierung rechnet im Python-Backend und ist nur in der <strong>Vollversion</strong> verfügbar:
        Repository herunterladen und <code>python -m api</code> starten (siehe README, Abschnitt „Vollversion“).
      </div></div>
    );
  }
  const res = job?.result;
  const p = job?.progress ?? {};
  return (
    <div className="study">
      <div className="study-form">
        <div className="seg" role="radiogroup" aria-label="Modell-Level">
          <button type="button" className={level === 1 ? 'active' : ''} onClick={() => setLvl(1)}>Level 1</button>
          <button type="button" className={level === 2 ? 'active' : ''} onClick={() => setLvl(2)}>Level 2</button>
        </div>
        <label>Zielfunktion
          <select value={objective} onChange={(e) => setObjective(e.target.value)}>
            <option value="height">max. Flughöhe</option>
            <option value="rotation" disabled={level === 1}>max. Rotationspotenzial (Level 2)</option>
            <option value="combined" disabled={level === 1}>Kombination Höhe + Rotation</option>
          </select>
        </label>
        {objective === 'combined' && <label>Gewicht Rotation (Höhe = 1) <input type="number" step={0.1} min={0} max={5} value={wR} onChange={(e) => setWR(Number(e.target.value))} /></label>}
        <label>Mindest-Freigang zur Brettspitze [m] <input type="number" step={0.05} min={0} max={2} value={clear} onChange={(e) => setClear(Number(e.target.value))} /></label>
        <label>Generationen <input type="number" min={1} max={60} value={gens} onChange={(e) => setGens(Number(e.target.value))} /></label>
        <label>Populationsgröße <input type="number" min={4} max={40} value={pop} onChange={(e) => setPop(Number(e.target.value))} /></label>
        <label className="check"><input type="checkbox" checked={robust} onChange={(e) => setRobust(e.target.checked)} /> Robustheit: ±10 ms Onset-Störung (Kong et al. 2006)</label>
        <div className="footnote">
          CMA-ES über Voraktivierung, Onset, Anstiegszeit und Plateau {level === 2 ? 'der Bein-Strecker, Hüftbeuger und Schulterflexoren' : 'des Bein-Aktuators'}.
          {' '}≈ {sims} Simulationen{level === 2 ? `, grob ${Math.round((sims * 5) / 60 / 4)}–${Math.round((sims * 7) / 60 / 2)} min je nach CPU-Kernen` : ', wenige Sekunden'}.
        </div>
        {!running
          ? <button type="button" className="btn primary" onClick={() => run({ level, objective, w_height: 1, w_rotation: wR, min_clearance: clear, generations: gens, popsize: pop, robust })}>Optimierung starten</button>
          : <button type="button" className="btn" onClick={stop}>Abbrechen (Generation {p.generation ?? 0}/{p.generations ?? gens})</button>}
        {job && <div className="mono footnote">Status: {job.status}{job.error ? ` – ${job.error}` : ''}{p.best_h !== undefined ? ` · bestes h_max ${Number(p.best_h).toFixed(3)} m` : ''}</div>}
      </div>
      <div className="study-out">
        {res ? (
          <>
            <LineChart height={180} xLabel="Generation" yLabel="Zielwert (höher = besser)" series={[
              { name: 'Bester', x: res.history.map((h) => h.generation), y: res.history.map((h) => h.best) },
              { name: 'Mittel der Generation', x: res.history.map((h) => h.generation), y: res.history.map((h) => h.mean), color: '#A1A1AA', dash: '6 4' },
            ]} />
            <table className="metric-table opt-table">
              <thead><tr><th>Kennwert</th><th className="num">Ausgang</th><th className="num">Optimiert</th><th>Einheit</th></tr></thead>
              <tbody>
                {COMPARE.filter((k) => res.best_metrics[k] !== undefined && res.best_metrics[k] !== null).map((k) => {
                  const info = METRIC_BY_KEY[k];
                  const f = (x: number | null) => (x === null || x === undefined ? '–' : (x * (info.scale ?? 1)).toFixed(info.fmt ?? 3));
                  return <tr key={k}><td>{info.label}</td><td className="mono num">{f(res.baseline_metrics[k])}</td><td className="mono num strong">{f(res.best_metrics[k])}</td><td className="unit">{info.unit}</td></tr>;
                })}
              </tbody>
            </table>
            <details>
              <summary>Optimierte Aktivierungsparameter ({res.variables.length})</summary>
              <table className="metric-table">
                <tbody>{res.variables.map((k) => <tr key={k}><td>{PARAM_BY_KEY[k].label}</td><td className="mono num">{res.best_values[k].toFixed(3)}</td><td className="unit">{PARAM_BY_KEY[k].unit}</td></tr>)}</tbody>
              </table>
            </details>
            <button type="button" className="btn primary" onClick={() => { setLevel(level); setMany(res.best_values); useStore.getState().setPage('sim'); }}>
              Optimierte Werte übernehmen und anzeigen
            </button>
            <div className="footnote">{res.evaluations} Kandidaten bewertet. Optimierte Timings bleiben Status „Schätzung“, da Kraftwerte generisch sind.</div>
          </>
        ) : (
          <div className="placeholder">Noch kein Ergebnis. Tipp: zuerst mit wenigen Generationen testen.</div>
        )}
      </div>
    </div>
  );
}
