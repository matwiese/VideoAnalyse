/** Kennwerte (SPEC 10.3 rechts) mit Status je Wert und Energiebilanz-Selbsttest. */
import { useState } from 'react';
import { METRICS, METRIC_BY_KEY, PARAM_BY_KEY } from '../lib/params';
import { formatMetric, metricStatus } from '../lib/status';
import { useStore } from '../store';
import { StatusBadge } from './ParamPanel';

const CARDS_L1 = ['v_z_to', 'h_max_board', 'F_peak_bw', 'z_b_min', 't_contact', 'x_board_plane', 'H_y', 'rotation_potential'];
const CARDS_L2 = ['v_z_to', 'h_max_board', 'F_active_peak_bw', 'z_b_min', 't_contact', 'x_body_board_plane', 'H_y', 'rotation_potential'];
const CARD_LABEL: Record<string, string> = {
  v_z_to: 'v_z,TO', h_max_board: 'h_max über Brett', F_peak_bw: 'Peak-F', F_active_peak_bw: 'Peak-F (Hauptmax.)', z_b_min: 'max. Durchbiegung',
  t_contact: 'Kontaktzeit', x_board_plane: 'Freigang (KSP)', x_body_board_plane: 'Freigang (Körper)', H_y: 'H_y', rotation_potential: 'Rotationspotenzial',
};
const CATS = ['Brett', 'Geschwindigkeiten', 'Kräfte', 'Impuls', 'Höhen / Wege', 'Zeiten', 'Energie', 'Leistung', 'Gelenke', 'Momente', 'Rotation'];

export function MetricsPanel() {
  const view = useStore((s) => s.view);
  const values = useStore((s) => s.values);
  const status = useStore((s) => s.status);
  const pinned = useStore((s) => s.pinned);
  const level = useStore((s) => s.level);
  const busy = useStore((s) => s.busy);
  const [showAll, setShowAll] = useState(false);
  if (!view) return <aside className="panel metrics">Rechne …</aside>;
  const m = view.metrics;
  const lv = view.level;
  const bal = (m.energy_balance_rel as number) * 100;
  const balOk = bal <= 0.5;
  const cards = lv === 2 ? CARDS_L2 : CARDS_L1;
  return (
    <aside className="panel metrics" aria-label="Kennwerte">
      <div className="panel-title">
        Kennwerte
        <span className="level">{lv === 2 ? 'Level 2 · Mehrkörpermodell planar' : 'Level 1 · Zwei-Massen-Modell'}{busy ? ' · rechnet …' : ''}</span>
      </div>
      {level !== lv && <div className="warning">Anzeige noch aus Level {lv} – neues Ergebnis wird berechnet.</div>}
      <div className={`cards ${busy ? 'stale' : ''}`}>
        {cards.map((k, idx) => {
          const info = METRIC_BY_KEY[k];
          const st = metricStatus(info, values, status, lv);
          const na = st.status === 'n/a' || m[k] === null || m[k] === undefined;
          return (
            <div key={k} className={`card ${idx === 0 ? 'primary' : ''} ${na ? 'na' : ''}`}
              title={na ? 'Rotation erfordert das Mehrkörpermodell (Level 2)' : st.estimates.length ? `Beruht auf ${st.estimates.length} Schätzparametern, z. B.:\n${st.estimates.slice(0, 8).map((e) => PARAM_BY_KEY[e].label ?? e).join('\n')}` : st.status}>
              <div className="card-label">{CARD_LABEL[k]} {!na && <StatusBadge status={st.status} />}</div>
              <div className="card-value mono">{na ? '–' : formatMetric(info, m[k])}<span className="unit">{na ? 'ab Level 2' : info.unit}</span></div>
              {pinned.length > 0 && !na && (
                <div className="card-compare mono">
                  {pinned.map((p, i) => {
                    const ref = p.view.metrics[k];
                    if (ref === null || ref === undefined) return <span key={p.id}>Δ{i + 1} –</span>;
                    const dv = ((m[k] as number) - ref) * (info.scale ?? 1) * (k === 'z_b_min' ? -1 : 1);
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
      {lv === 2 && m.somersaults_tuck !== null && m.somersaults_tuck !== undefined && (
        <div className="somersaults mono" title="Mögliche Saltoanzahl bis zum Eintauchen je Körperhaltung (H_y · t_Flug / 2π I, I geschätzt)">
          Saltos: gestreckt {(m.somersaults_layout as number).toFixed(2)} · gehechtet {(m.somersaults_pike as number).toFixed(2)} · gehockt {(m.somersaults_tuck as number).toFixed(2)}
        </div>
      )}
      {view.warnings.length > 0 && <div className="warning">{view.warnings.map((w) => <div key={w}>⚠ {w}</div>)}</div>}
      <button type="button" className="btn ghost" onClick={() => setShowAll(!showAll)} aria-expanded={showAll}>
        {showAll ? 'Alle Kennwerte ausblenden' : 'Alle Kennwerte (Kap. 7)'}
      </button>
      {showAll && (
        <table className="metric-table">
          {CATS.map((cat) => {
            const rows = METRICS.filter((info) => info.cat === cat && ((info.level_min ?? 1) <= lv));
            if (!rows.length) return null;
            return (
              <tbody key={cat}>
                <tr><th colSpan={4}>{cat}</th></tr>
                {rows.map((info) => {
                  const st = metricStatus(info, values, status, lv);
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
            );
          })}
        </table>
      )}
      <div className="footnote">
        Werte mit <StatusBadge status="Schätzung" /> beruhen auf mindestens einem Schätzparameter.
        {lv === 1
          ? ' Level 1 kennt keine Rotation, keine Gelenke und keinen Armschwung; v_z,TO wird dadurch eher unterschätzt.'
          : ' Level 2: 7 Segmente + 3 Schwabbelmassen, Kontakt an Zehe/Ballen/Ferse. Kraftwerte generisch geschätzt – vor fachlicher Interpretation kalibrieren (SPEC 9.4).'}
      </div>
    </aside>
  );
}
