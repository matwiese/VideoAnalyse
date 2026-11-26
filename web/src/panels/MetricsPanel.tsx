/** Kennwerte (SPEC 10.3 rechts) mit Status je Wert und Energiebilanz-Selbsttest. */
import { useState } from 'react';
import { METRICS, METRIC_BY_KEY, PARAM_BY_KEY } from '../lib/params';
import { formatMetric, metricStatus } from '../lib/status';
import { useStore } from '../store';
import { StatusBadge } from './ParamPanel';

const CARDS = ['v_z_to', 'h_max_board', 'F_peak_bw', 'z_b_min', 't_contact', 'x_board_plane', 'H_y', 'rotation_potential'];
const CARD_LABEL: Record<string, string> = {
  v_z_to: 'v_z,TO', h_max_board: 'h_max über Brett', F_peak_bw: 'Peak-F', z_b_min: 'max. Durchbiegung',
  t_contact: 'Kontaktzeit', x_board_plane: 'Freigang', H_y: 'H_y', rotation_potential: 'Rotationspotenzial',
};

export function MetricsPanel() {
  const result = useStore((s) => s.result);
  const values = useStore((s) => s.values);
  const status = useStore((s) => s.status);
  const pinned = useStore((s) => s.pinned);
  const [showAll, setShowAll] = useState(false);
  if (!result) return <aside className="panel metrics">Rechne …</aside>;
  const m = result.metrics;
  const bal = (m.energy_balance_rel as number) * 100;
  const balOk = bal <= 0.5;
  return (
    <aside className="panel metrics" aria-label="Kennwerte">
      <div className="panel-title">Kennwerte <span className="level">Level 1 · Zwei-Massen-Modell</span></div>
      <div className="cards">
        {CARDS.map((k, idx) => {
          const info = METRIC_BY_KEY[k];
          const st = metricStatus(info, values, status);
          const na = st.status === 'n/a';
          return (
            <div key={k} className={`card ${idx === 0 ? 'primary' : ''} ${na ? 'na' : ''}`}
              title={na ? 'Rotation erfordert das Mehrkörpermodell (Level 2, Etappe 3)' : st.estimates.length ? `Beruht auf Schätzparametern:\n${st.estimates.map((e) => PARAM_BY_KEY[e].label ?? e).join('\n')}` : st.status}>
              <div className="card-label">{CARD_LABEL[k]} {!na && <StatusBadge status={st.status} />}</div>
              <div className="card-value mono">{na ? '–' : formatMetric(info, m[k])}<span className="unit">{na ? 'ab Level 2' : info.unit}</span></div>
              {pinned.length > 0 && !na && (
                <div className="card-compare mono">
                  {pinned.map((p, i) => {
                    const dv = ((m[k] as number) - (p.result.metrics[k] as number)) * (info.scale ?? 1) * (k === 'z_b_min' ? -1 : 1);
                    return <span key={p.id}>Δ{i + 1} {dv >= 0 ? '+' : ''}{dv.toFixed(info.fmt ?? 3)}</span>;
                  })}
                </div>
              )}
            </div>
          );
        })}
        <div className={`card ${balOk ? '' : 'warn'}`} title="Muskelarbeit + Anfangsenergie = Endenergie + Dämpfungsverluste (SPEC Kap. 7)">
          <div className="card-label">Energiebilanz</div>
          <div className="card-value mono">{balOk ? 'OK' : 'Warnung'}<span className="unit">{bal.toExponential(1)} %</span></div>
        </div>
      </div>
      {result.warnings.length > 0 && <div className="warning">{result.warnings.map((w) => <div key={w}>⚠ {w}</div>)}</div>}
      <button type="button" className="btn ghost" onClick={() => setShowAll(!showAll)} aria-expanded={showAll}>
        {showAll ? 'Alle Kennwerte ausblenden' : 'Alle Kennwerte (Kap. 7)'}
      </button>
      {showAll && (
        <table className="metric-table">
          <tbody>
            {METRICS.map((info) => {
              const st = metricStatus(info, values, status);
              return (
                <tr key={info.key + info.unit}>
                  <td>{info.label}</td>
                  <td className="mono num">{formatMetric(info, m[info.key])}</td>
                  <td className="unit">{info.unit}</td>
                  <td><StatusBadge status={st.status} title={st.estimates.length ? `Schätzparameter: ${st.estimates.length}` : st.status} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      <div className="footnote">
        Werte mit <StatusBadge status="Schätzung" /> beruhen auf mindestens einem Schätzparameter (Kraft-, Bein- oder Hürdenwerte).
        Level 1 kennt keine Rotation, keine Gelenke und keinen Armschwung; v_z,TO wird dadurch eher unterschätzt.
      </div>
    </aside>
  );
}
