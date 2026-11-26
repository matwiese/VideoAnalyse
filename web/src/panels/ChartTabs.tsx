/** Tabs unter der Szene (SPEC 10.3): Zeitverläufe inkl. Vergleich fixierter Läufe. */
import { useState } from 'react';
import { LineChart, type LineSeries } from '../charts/LineChart';
import { JOINT_LABELS, SEGMENT_LABELS, type View } from '../lib/view';
import { useStore } from '../store';

const GREYS = ['#D4D4D8', '#A1A1AA', '#71717A'];
const DASHES = ['6 4', '2 3', '10 3 2 3'];
const MULTI = ['var(--red)', '#F4F4F5', '#A1A1AA', '#71717A', '#FF4D4D', '#52525B', '#D4D4D8', '#3F3F46', '#E4E4E7', '#27272A'];
const MULTI_DASH = [undefined, '6 3', '2 3', '10 3 2 3', '4 4', '1 3', '8 2', '3 6', '12 4', '2 8'];

type TabKey = 'force' | 'board' | 'com' | 'energy' | 'joints' | 'moments' | 'sankey' | 'momentum';
const TABS: { key: TabKey; label: string; level?: number }[] = [
  { key: 'force', label: 'Kraft-Zeit' },
  { key: 'board', label: 'Brettweg/-geschw.' },
  { key: 'com', label: 'KSP' },
  { key: 'energy', label: 'Energie' },
  { key: 'joints', label: 'Gelenkwinkel', level: 2 },
  { key: 'moments', label: 'Gelenkmomente/-leistung', level: 2 },
  { key: 'sankey', label: 'Energiefluss', level: 2 },
  { key: 'momentum', label: 'Drehimpuls je Segment', level: 2 },
];

const col = (rows: number[][], j: number, f = 1) => rows.map((r) => (r[j] ?? NaN) * f);

export function ChartTabs() {
  const [tab, setTab] = useState<TabKey>('force');
  const [range, setRange] = useState<'contact' | 'all'>('contact');
  const [joint, setJoint] = useState(2);
  const v = useStore((s) => s.view);
  const pinned = useStore((s) => s.pinned);
  const time = useStore((s) => s.time);
  const setTime = useStore((s) => s.setTime);
  const setPlaying = useStore((s) => s.setPlaying);
  if (!v) return null;
  const BW = v.geom.M * 9.81;
  const xDomain: [number, number] = range === 'contact' ? [-0.05, v.events.TO + 0.1] : [v.t[0], v.t[v.t.length - 1]];
  const marks = [{ x: 0, label: 'TD' }, ...(v.events.LP !== undefined ? [{ x: v.events.LP, label: 'LP' }] : []), { x: v.events.TO, label: 'TO' }];
  if (v.events.HTO !== undefined) marks.unshift({ x: v.events.HTO, label: 'Hürde' });
  const comp = (f: (r: View) => { x: ArrayLike<number>; y: ArrayLike<number> }, name: string): LineSeries[] =>
    pinned.map((p, i) => ({ name: `${name} · Lauf ${i + 1}`, ...f(p.view), color: GREYS[i], dash: DASHES[i], width: 1.3 }));
  const scrub = (x: number) => { setPlaying(false); setTime(Math.min(Math.max(x, v.t[0]), v.t[v.t.length - 1])); };
  const common = { cursor: time, marks, onScrub: scrub, xDomain, xLabel: 't [s] (0 = Touchdown)' };
  const s2 = v.l2?.series;
  const cDomain: [number, number] = [-0.01, v.events.TO + 0.01];
  const l2common = { ...common, xDomain: cDomain };
  const activeTab = TABS.find((t) => t.key === tab)!;
  let chart: JSX.Element | null = null;

  if (activeTab.level && v.level < (activeTab.level ?? 1)) {
    chart = (
      <div className="placeholder">
        <strong>{activeTab.label}</strong> benötigt das planare Mehrkörpermodell (Level 2). Oben rechts auf „Level 2“ umschalten –
        verfügbar in der Vollversion (<code>python -m api</code>, siehe README).
      </div>
    );
  } else if (tab === 'force') {
    const toBW = (r: View) => ({ x: r.t, y: Array.from(r.F, (x) => x / (r.geom.M * 9.81)) });
    const act = v.level === 1 && v.l1 ? v.l1.series.act : null;
    chart = (
      <LineChart {...common} yLabel="Kraft Brett → Springer [BW]" yLabelRight={act ? 'Aktivierung a(t)' : undefined}
        series={[
          { name: 'F_z', x: v.t, y: Array.from(v.F, (x) => x / BW) },
          ...(v.level === 2 ? [{ name: 'F_x (horizontal)', x: v.t, y: Array.from(v.Fx, (x) => x / BW), color: '#F4F4F5', dash: '6 3', width: 1.3 }] : []),
          ...comp(toBW, 'F_z'),
          ...(act ? [{ name: 'Aktivierung (rechte Achse)', x: v.t, y: act, color: '#A1A1AA', dash: '4 3', width: 1.2, axis: 'right' as const }] : []),
        ]} />
    );
  } else if (tab === 'board') {
    chart = (
      <LineChart {...common} yLabel="z_b [m]" yLabelRight="ż_b [m/s]"
        series={[
          { name: 'z_b Brettspitze', x: v.t, y: v.z_b },
          ...comp((r) => ({ x: r.t, y: r.z_b }), 'z_b'),
          { name: 'ż_b (rechte Achse)', x: v.t, y: v.v_b, color: '#A1A1AA', dash: '4 3', width: 1.2, axis: 'right' },
        ]} />
    );
  } else if (tab === 'com') {
    chart = (
      <LineChart {...common} yLabel="z KSP [m]" yLabelRight="v_z [m/s]"
        series={[
          { name: 'z KSP', x: v.t, y: v.com_z },
          ...comp((r) => ({ x: r.t, y: r.com_z }), 'z KSP'),
          { name: 'v_z KSP (rechte Achse)', x: v.t, y: v.v_z, color: '#A1A1AA', dash: '4 3', width: 1.2, axis: 'right' },
        ]} />
    );
  } else if (tab === 'energy') {
    if (v.level === 1 && v.l1) {
      const s = v.l1.series;
      chart = (
        <LineChart {...common} yLabel="Energie [J]"
          series={[
            { name: 'Brett-Federenergie ½k_s z_b²', x: s.t, y: s.E_board },
            { name: 'E_kin (Springer + Brett)', x: s.t, y: s.E_kin, color: '#F4F4F5', width: 1.3 },
            { name: 'E_pot Springer (rel. Start)', x: s.t, y: Array.from(s.E_pot, (x) => x - s.E_pot[0]), color: '#A1A1AA', dash: '6 4', width: 1.3 },
            { name: 'Beinfeder', x: s.t, y: s.E_leg, color: '#71717A', dash: '2 3', width: 1.3 },
            { name: 'Muskelarbeit kumuliert', x: s.t, y: s.W_act, color: '#FF4D4D', dash: '8 3', width: 1.3 },
            { name: 'Verluste kumuliert', x: s.t, y: Array.from(s.D_loss, (x) => -x), color: '#52525B', dash: '1 3', width: 1.3 },
          ]} />
      );
    } else if (s2) {
      const E0 = s2.E_mech[0];
      chart = (
        <LineChart {...l2common} yLabel="Energie [J] (rel. TD)"
          series={[
            { name: 'ΔE mechanisch (Springer + Brett)', x: s2.t, y: s2.E_mech.map((e) => e - E0) },
            { name: 'Muskelarbeit kumuliert', x: s2.t, y: col(s2.acc, 0), color: '#FF4D4D', dash: '8 3', width: 1.3 },
            { name: 'Passive Gelenkmomente', x: s2.t, y: col(s2.acc, 1), color: '#A1A1AA', dash: '2 3', width: 1.3 },
            { name: 'Fußkontakt (netto)', x: s2.t, y: col(s2.acc, 2), color: '#F4F4F5', dash: '6 3', width: 1.3 },
            { name: '− Schwabbeldämpfung', x: s2.t, y: col(s2.acc, 3, -1), color: '#71717A', dash: '1 3', width: 1.3 },
            { name: '− Brettdämpfung', x: s2.t, y: col(s2.acc, 4, -1), color: '#52525B', dash: '4 4', width: 1.3 },
          ]} />
      );
    }
  } else if (tab === 'joints' && s2) {
    chart = (
      <LineChart {...l2common} yLabel="Gelenkwinkel [°] (Flexion/Dorsalflexion +)"
        series={JOINT_LABELS.map((n, j) => ({ name: n, x: s2.t, y: col(s2.theta, j, 180 / Math.PI), color: MULTI[j], dash: MULTI_DASH[j], width: j === 2 ? 2 : 1.4 }))} />
    );
  } else if (tab === 'moments' && s2) {
    chart = (
      <>
        <div className="seg small joint-select" role="radiogroup" aria-label="Gelenk">
          {JOINT_LABELS.map((n, j) => <button key={n} type="button" className={joint === j ? 'active' : ''} onClick={() => setJoint(j)}>{n}</button>)}
        </div>
        <LineChart {...l2common} yLabel={`${JOINT_LABELS[joint]}: Moment [Nm]`} yLabelRight="Leistung [W]"
          series={[
            { name: 'Netto-Moment', x: s2.t, y: col(s2.tau_net, joint) },
            { name: 'aktiv', x: s2.t, y: col(s2.tau_act, joint), color: '#F4F4F5', dash: '6 3', width: 1.2 },
            { name: 'passiv (Endanschlag)', x: s2.t, y: col(s2.tau_pas, joint), color: '#71717A', dash: '2 3', width: 1.2 },
            { name: 'Leistung T·ω (rechte Achse)', x: s2.t, y: col(s2.power, joint), color: '#A1A1AA', dash: '8 3', width: 1.2, axis: 'right' },
          ]} />
      </>
    );
  } else if (tab === 'momentum' && s2) {
    const total = s2.H_seg.map((r) => r.reduce((a, b) => a + b, 0));
    chart = (
      <LineChart {...l2common} yLabel="H_y um KSP [kg m²/s] (+ = vorwärts)"
        series={[
          { name: 'Gesamt', x: s2.t, y: total, width: 2.2 },
          ...SEGMENT_LABELS.slice(0, 7).map((n, j) => ({ name: n, x: s2.t, y: col(s2.H_seg, j), color: MULTI[j + 1], dash: MULTI_DASH[j + 1], width: 1.1 })),
        ]} />
    );
  } else if (tab === 'sankey' && v.l2) {
    chart = <EnergyFlow v={v} />;
  }

  return (
    <div className="tabs">
      <div className="tab-bar" role="tablist">
        {TABS.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} className={`tab ${tab === t.key ? 'active' : ''} ${t.level && v.level < t.level ? 'later' : ''}`} onClick={() => setTab(t.key)}>
            {t.label}{t.level ? <span className="lvl">L{t.level}</span> : null}
          </button>
        ))}
        <span className="spacer" />
        <label className="range-toggle">
          <select value={range} onChange={(e) => setRange(e.target.value as 'contact' | 'all')} aria-label="Zeitbereich">
            <option value="contact">Brettkontakt</option>
            <option value="all">Hürde bis Wasser</option>
          </select>
        </label>
      </div>
      <div className="tab-body">{chart}</div>
    </div>
  );
}

/** Energiefluss TD → TO als Balken (vereinfachte Sankey-Darstellung). */
function EnergyFlow({ v }: { v: View }) {
  const m = v.metrics;
  const s = v.l2!.series;
  const acc = s.acc[s.acc.length - 1];
  const items: { label: string; value: number; kind: 'in' | 'out' }[] = [
    { label: 'Muskelarbeit (netto, alle Gelenke)', value: acc[0], kind: 'in' },
    { label: 'Passive Gelenkmomente', value: acc[1], kind: acc[1] >= 0 ? 'in' : 'out' },
    { label: 'Fußkontakt netto (Dämpfung/Speicher)', value: acc[2], kind: acc[2] >= 0 ? 'in' : 'out' },
    { label: 'Schwabbelmassen-Dämpfung', value: -acc[3], kind: 'out' },
    { label: 'Brettdämpfung', value: -acc[4], kind: 'out' },
    { label: 'Springer → Brett (Depression)', value: (m.W_athlete_to_board as number) ?? 0, kind: 'out' },
    { label: 'Brett → Springer (Recoil)', value: (m.W_board_to_athlete as number) ?? 0, kind: 'in' },
  ];
  const max = Math.max(...items.map((i) => Math.abs(i.value)), 1);
  return (
    <div className="eflow">
      {items.map((i) => (
        <div key={i.label} className="eflow-row">
          <span className="eflow-label">{i.label}</span>
          <span className="eflow-bar"><span className={i.kind} style={{ width: `${(Math.abs(i.value) / max) * 100}%` }} /></span>
          <span className="mono eflow-val">{i.value >= 0 ? '+' : ''}{i.value.toFixed(0)} J</span>
        </div>
      ))}
      <div className="footnote">Bilanz TD → TO. Brett-Energieübertrag ist Teil der mechanischen Energie (nicht zusätzlich in der Bilanz). Bilanzfehler {((m.energy_balance_rel as number) * 100).toExponential(1)} %.</div>
    </div>
  );
}
