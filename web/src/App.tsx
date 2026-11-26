import { useRef, useState } from 'react';
import { ProfileSchema, PRESETS, type Profile } from './lib/params';
import { ChartTabs } from './panels/ChartTabs';
import { MetricsPanel } from './panels/MetricsPanel';
import { ParamPanel } from './panels/ParamPanel';
import { OptPanel } from './panels/OptPanel';
import { StudyPanel } from './panels/StudyPanel';
import { Timeline } from './panels/Timeline';
import { Scene, type CamPreset } from './scene/Scene';
import { useStore } from './store';

function download(name: string, content: BlobPart, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function exportCsv() {
  const v = useStore.getState().view;
  if (!v) return;
  const lines: string[] = [];
  if (v.level === 2 && v.l2) {
    const s = v.l2.series;
    const J = ['mtp', 'ankle', 'knee', 'hip', 'shoulder', 'elbow'];
    const head = ['t [s]', 'Fz [N]', 'Fx [N]', 'z_b [m]', 'v_b [m/s]', 'x_KSP [m]', 'z_KSP [m]', 'vx_KSP [m/s]', 'vz_KSP [m/s]',
      ...J.map((j) => `theta_${j} [rad]`), ...J.map((j) => `omega_${j} [rad/s]`), ...J.map((j) => `tau_${j} [Nm]`), ...J.map((j) => `P_${j} [W]`)];
    lines.push(head.join(';'));
    for (let i = 0; i < s.t.length; i++) {
      lines.push([s.t[i], s.Fz[i], s.Fx[i], s.z_b[i], s.v_b[i], ...s.com[i], ...s.theta[i], ...s.omega[i], ...s.tau_net[i], ...s.power[i]]
        .map((x) => Number(x).toPrecision(8)).join(';'));
    }
    download('level2_kontaktphase_1kHz.csv', lines.join('\n'), 'text/csv');
    return;
  }
  const s = v.l1!.series;
  const cols = ['t', 'z_c', 'x_c', 'v_c', 'z_b', 'x_b', 'v_b', 'F', 'act', 'E_kin', 'E_pot', 'E_board', 'E_leg', 'W_act', 'D_loss'] as const;
  const units = ['s', 'm', 'm', 'm/s', 'm', 'm', 'm/s', 'N', '-', 'J', 'J', 'J', 'J', 'J', 'J'];
  lines.push(cols.map((c, i) => `${c} [${units[i]}]`).join(';'));
  for (let i = 0; i < s.t.length; i++) lines.push(cols.map((c) => s[c][i].toPrecision(8)).join(';'));
  download('level1_zeitverlauf_1kHz.csv', lines.join('\n'), 'text/csv');
}

function exportProfile() {
  const { values, status, preset } = useStore.getState();
  const profile: Profile = { app: '3m-brett-simulator', version: 1, name: preset ? PRESETS[preset].label : 'Eigenes Profil', values, status };
  download('athletenprofil.json', JSON.stringify(profile, null, 2), 'application/json');
}

function exportPng() {
  const canvas = document.querySelector('.scene canvas') as HTMLCanvasElement | null;
  if (!canvas) return;
  canvas.toBlob((b) => b && download('szene.png', b, 'image/png'));
}

export function App() {
  const page = useStore((s) => s.page);
  const setPage = useStore((s) => s.setPage);
  const level = useStore((s) => s.level);
  const setLevel = useStore((s) => s.setLevel);
  const backend = useStore((s) => s.backend);
  const busy = useStore((s) => s.busy);
  const error = useStore((s) => s.error);
  const computeMs = useStore((s) => s.computeMs);
  const roundtripMs = useStore((s) => s.roundtripMs);
  const pinned = useStore((s) => s.pinned);
  const pin = useStore((s) => s.pin);
  const unpin = useStore((s) => s.unpin);
  const loadProfile = useStore((s) => s.loadProfile);
  const [cam, setCam] = useState<CamPreset>('side');
  const fileRef = useRef<HTMLInputElement>(null);
  const [importMsg, setImportMsg] = useState<string | null>(null);

  const onImport = async (f: File) => {
    try {
      const parsed = ProfileSchema.parse(JSON.parse(await f.text()));
      loadProfile(parsed.values, parsed.status);
      setImportMsg(`Profil „${parsed.name}“ geladen`);
    } catch (e) {
      setImportMsg(`Import fehlgeschlagen: ${e instanceof Error ? e.message.slice(0, 120) : e}`);
    }
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand"><span className="dot" />3m-Brett-Simulator <span className="sub">Anlauf · Hürde · Brettkontakt · Flug</span></div>
        <nav className="seg" aria-label="Ansicht">
          <button type="button" className={page === 'sim' ? 'active' : ''} onClick={() => setPage('sim')} aria-pressed={page === 'sim'}>Simulation</button>
          <button type="button" className={page === 'study' ? 'active' : ''} onClick={() => setPage('study')} aria-pressed={page === 'study'}>Parameterstudie</button>
          <button type="button" className={page === 'opt' ? 'active' : ''} onClick={() => setPage('opt')} aria-pressed={page === 'opt'}>Optimierung</button>
        </nav>
        <nav className="seg" aria-label="Modell-Level">
          <button type="button" className={level === 1 ? 'active' : ''} onClick={() => setLevel(1)} title="Zwei-Massen-Modell, rechnet live im Browser">Level 1</button>
          <button type="button" className={level === 2 ? 'active' : ''} onClick={() => setLevel(2)} disabled={!backend}
            title={backend ? 'Planares Mehrkörpermodell (8 Segmente, Gelenkmomente, Rotation) – rechnet im Backend, ca. 2–7 s' : 'Level 2 braucht die Vollversion: python -m api (siehe README)'}>
            Level 2{busy ? ' …' : ''}
          </button>
        </nav>
        <span className={`backend-dot ${backend ? 'on' : 'off'}`} title={backend ? 'Rechenkern verbunden (Vollversion)' : 'Ohne Rechenkern: nur Level 1 (Einzeldatei-Modus)'}>
          {backend ? 'Vollversion' : backend === false ? 'Browser-Version' : '…'}
        </span>
        <div className="actions">
          <span className={`perf mono ${roundtripMs > 50 ? 'slow' : ''}`} title="Rechenzeit im Web Worker / Antwortzeit Slider → Ergebnis (Ziel < 50 ms)">
            {computeMs.toFixed(0)} ms · {roundtripMs.toFixed(0)} ms
          </span>
          <button type="button" className="btn ghost" onClick={exportCsv}>CSV</button>
          <button type="button" className="btn ghost" onClick={exportPng}>PNG</button>
          <button type="button" className="btn ghost" onClick={exportProfile}>Profil ↓</button>
          <button type="button" className="btn ghost" onClick={() => fileRef.current?.click()}>Profil ↑</button>
          <input ref={fileRef} type="file" accept="application/json" hidden onChange={(e) => e.target.files?.[0] && onImport(e.target.files[0])} />
        </div>
      </header>
      {(error || importMsg) && (
        <div className="banner" role="status">
          {error && <span>⚠ {error}</span>}
          {importMsg && <span>{importMsg} <button type="button" className="link" onClick={() => setImportMsg(null)}>×</button></span>}
        </div>
      )}
      <main className="layout">
        <ParamPanel />
        <section className="center">
          {page === 'sim' ? (
            <>
              <div className="scene">
                <Scene preset={cam} />
                <div className="scene-ui">
                  <div className="seg small" aria-label="Kamera">
                    {(['side', 'front', 'board'] as CamPreset[]).map((c) => (
                      <button key={c} type="button" className={cam === c ? 'active' : ''} onClick={() => setCam(c)}>
                        {c === 'side' ? 'seitlich' : c === 'front' ? 'frontal' : 'Brettperspektive'}
                      </button>
                    ))}
                  </div>
                  <div className="compare">
                    <button type="button" className="btn small" onClick={pin} disabled={pinned.length >= 3} title="Aktuellen Lauf für den Vergleich fixieren (max. 3 + aktuell)">+ Lauf fixieren</button>
                    {pinned.map((p, i) => (
                      <span key={p.id} className="chip">
                        <svg width="18" height="6"><line x1="0" x2="18" y1="3" y2="3" stroke={['#D4D4D8', '#A1A1AA', '#71717A'][i]} strokeWidth="2" strokeDasharray={['6 4', '2 3', '10 3 2 3'][i]} /></svg>
                        {i + 1}: {p.label}
                        <button type="button" className="link" onClick={() => unpin(p.id)} aria-label={`Lauf ${i + 1} entfernen`}>×</button>
                      </span>
                    ))}
                  </div>
                </div>
                <div className="scene-note">{level === 2 ? 'Level 2: simulierte Segmentkette; im Flug Haltung ab TO eingefroren, Rotation ω = H/I' : 'Figur = Visualisierung des Level-1-Punktmassenmodells (KSP & Beinlänge simuliert, Gelenke/Arme illustrativ)'}</div>
              </div>
              <Timeline />
              <ChartTabs />
            </>
          ) : page === 'study' ? (
            <StudyPanel />
          ) : (
            <OptPanel />
          )}
        </section>
        <MetricsPanel />
      </main>
    </div>
  );
}
