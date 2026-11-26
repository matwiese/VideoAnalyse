/** Tabs unter der Szene (SPEC 10.3): Zeitverläufe inkl. Vergleich fixierter Läufe. */
import { useState } from 'react';
import { LineChart, type LineSeries } from '../charts/LineChart';
import type { Level1Result } from '../sim-live/level1';
import { useStore } from '../store';

const GREYS = ['#D4D4D8', '#A1A1AA', '#71717A'];
const DASHES = ['6 4', '2 3', '10 3 2 3'];

type TabKey = 'force' | 'board' | 'com' | 'energy' | 'joints' | 'moments' | 'sankey' | 'momentum';
const TABS: { key: TabKey; label: string; level?: number }[] = [
  { key: 'force', label: 'Kraft-Zeit' },
  { key: 'board', label: 'Brettweg/-geschw.' },
  { key: 'com', label: 'KSP' },
  { key: 'energy', label: 'Energie' },
  { key: 'joints', label: 'Gelenkwinkel', level: 2 },
  { key: 'moments', label: 'Gelenkmomente/-leistung', level: 2 },
  { key: 'sankey', label: 'Energiefluss (Sankey)', level: 2 },
  { key: 'momentum', label: 'Drehimpuls je Segment', level: 2 },
];

function contactSlice(r: Level1Result, padBefore = 0.05, padAfter = 0.1): [number, number] {
  return [-padBefore, r.events.TO + padAfter];
}

export function ChartTabs() {
  const [tab, setTab] = useState<TabKey>('force');
  const [range, setRange] = useState<'contact' | 'all'>('contact');
  const result = useStore((s) => s.result);
  const pinned = useStore((s) => s.pinned);
  const time = useStore((s) => s.time);
  const setTime = useStore((s) => s.setTime);
  const setPlaying = useStore((s) => s.setPlaying);
  if (!result) return null;
  const s = result.series;
  const BW = result.geom.M * 9.81;
  const xDomain: [number, number] = range === 'contact' ? contactSlice(result) : [s.t[0], s.t[s.t.length - 1]];
  const marks = [{ x: 0, label: 'TD' }, ...(result.events.LP !== undefined ? [{ x: result.events.LP, label: 'LP' }] : []), { x: result.events.TO, label: 'TO' }];
  if (result.events.HTO !== undefined) marks.unshift({ x: result.events.HTO, label: 'Hürde' });

  const comp = (f: (r: Level1Result) => { x: ArrayLike<number>; y: ArrayLike<number> }, name: string): LineSeries[] =>
    pinned.map((p, i) => ({ name: `${name} · Lauf ${i + 1}`, ...f(p.result), color: GREYS[i], dash: DASHES[i], width: 1.3 }));

  let chart: JSX.Element | null = null;
  const scrub = (x: number) => { setPlaying(false); setTime(Math.min(Math.max(x, s.t[0]), s.t[s.t.length - 1])); };
  const common = { cursor: time, marks, onScrub: scrub, xDomain, xLabel: 't [s] (0 = Touchdown)' };
  if (tab === 'force') {
    const toBW = (r: Level1Result) => ({ x: r.series.t, y: Array.from(r.series.F, (v) => v / (r.geom.M * 9.81)) });
    chart = (
      <LineChart {...common} yLabel="F_z Brett [BW]" yLabelRight="Aktivierung a(t)"
        series={[
          { name: 'F_z Brett → Springer', x: s.t, y: Array.from(s.F, (v) => v / BW) },
          ...comp(toBW, 'F_z'),
          { name: 'Aktivierung (rechte Achse)', x: s.t, y: s.act, color: '#A1A1AA', dash: '4 3', width: 1.2, axis: 'right' },
        ]} />
    );
  } else if (tab === 'board') {
    chart = (
      <LineChart {...common} yLabel="z_b [m]" yLabelRight="ż_b [m/s]"
        series={[
          { name: 'z_b Brettspitze', x: s.t, y: s.z_b },
          ...comp((r) => ({ x: r.series.t, y: r.series.z_b }), 'z_b'),
          { name: 'ż_b (rechte Achse)', x: s.t, y: s.v_b, color: '#A1A1AA', dash: '4 3', width: 1.2, axis: 'right' },
        ]} />
    );
  } else if (tab === 'com') {
    chart = (
      <LineChart {...common} yLabel="z_KSP [m]" yLabelRight="v_z [m/s]"
        series={[
          { name: 'z KSP', x: s.t, y: s.z_c },
          ...comp((r) => ({ x: r.series.t, y: r.series.z_c }), 'z KSP'),
          { name: 'v_z KSP (rechte Achse)', x: s.t, y: s.v_c, color: '#A1A1AA', dash: '4 3', width: 1.2, axis: 'right' },
        ]} />
    );
  } else if (tab === 'energy') {
    const rel = (a: Float64Array) => Array.from(a, (v) => v);
    chart = (
      <LineChart {...common} yLabel="Energie [J]"
        series={[
          { name: 'Brett-Federenergie ½k_s z_b²', x: s.t, y: rel(s.E_board) },
          { name: 'E_kin (Springer + Brett)', x: s.t, y: rel(s.E_kin), color: '#F4F4F5', width: 1.3 },
          { name: 'E_pot Springer (rel. Start)', x: s.t, y: Array.from(s.E_pot, (v) => v - s.E_pot[0]), color: '#A1A1AA', dash: '6 4', width: 1.3 },
          { name: 'Beinfeder', x: s.t, y: rel(s.E_leg), color: '#71717A', dash: '2 3', width: 1.3 },
          { name: 'Muskelarbeit kumuliert', x: s.t, y: rel(s.W_act), color: '#FF4D4D', dash: '8 3', width: 1.3 },
          { name: 'Verluste kumuliert', x: s.t, y: Array.from(s.D_loss, (v) => -v), color: '#52525B', dash: '1 3', width: 1.3 },
        ]} />
    );
  } else {
    chart = (
      <div className="placeholder">
        <strong>{TABS.find((t) => t.key === tab)?.label}</strong> benötigt das planare Mehrkörpermodell (Level 2, Etappe 3):
        8 Segmente, Gelenk-Drehmomentgeneratoren und Schwabbelmassen, symbolisch mit SymPy erzeugt.
      </div>
    );
  }

  return (
    <div className="tabs">
      <div className="tab-bar" role="tablist">
        {TABS.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} className={`tab ${tab === t.key ? 'active' : ''} ${t.level ? 'later' : ''}`} onClick={() => setTab(t.key)}>
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
