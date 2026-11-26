/** Zeitleiste mit Phasenmarken P3–P7, Zeitlupe 0,05×–1×, Einzelbild (SPEC 10.3). */
import { useEffect, useRef } from 'react';
import { useStore } from '../store';

const SPEEDS = [0.05, 0.1, 0.25, 0.5, 1];

export function Timeline() {
  const result = useStore((s) => s.result);
  const time = useStore((s) => s.time);
  const playing = useStore((s) => s.playing);
  const speed = useStore((s) => s.speed);
  const setTime = useStore((s) => s.setTime);
  const setPlaying = useStore((s) => s.setPlaying);
  const setSpeed = useStore((s) => s.setSpeed);
  const raf = useRef(0);

  const t0 = result ? result.series.t[0] : 0;
  const t1 = result ? result.series.t[result.series.t.length - 1] : 1;

  useEffect(() => {
    if (!playing) return;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = ((now - last) / 1000) * useStore.getState().speed;
      last = now;
      const t = useStore.getState().time + dt;
      if (t >= t1) { setTime(t1); setPlaying(false); return; }
      setTime(t);
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [playing, t1, setTime, setPlaying]);

  if (!result) return null;
  const ev = result.events;
  const marks: { t: number; label: string; title: string }[] = [];
  if (ev.HTO !== undefined) marks.push({ t: ev.HTO, label: 'P3', title: 'Hürdenflug (Lift-off Sprungbein)' });
  marks.push({ t: 0, label: 'P4', title: 'Touchdown / Depression' });
  if (ev.LP !== undefined) marks.push({ t: ev.LP, label: 'P5', title: 'Recoil (tiefster Punkt)' });
  marks.push({ t: ev.TO, label: 'P6/7', title: 'Takeoff → Flug' });
  marks.push({ t: t1, label: 'Wasser', title: 'Eintauchen' });
  const pct = (t: number) => ((t - t0) / (t1 - t0)) * 100;
  const phase = time < 0 ? 'P3 Hürdenflug' : ev.LP !== undefined && time < ev.LP ? 'P4 Depression' : time < ev.TO ? 'P5 Recoil' : 'P7 Flug';

  return (
    <div className="timeline">
      <div className="tl-controls">
        <button type="button" className="btn" onClick={() => { if (time >= t1 - 1e-6) setTime(t0); setPlaying(!playing); }} aria-label={playing ? 'Pause' : 'Abspielen'}>
          {playing ? '❚❚' : '▶'}
        </button>
        <button type="button" className="btn ghost" onClick={() => setTime(Math.max(t0, time - 0.001))} aria-label="Ein Bild zurück">‹ 1 ms</button>
        <button type="button" className="btn ghost" onClick={() => setTime(Math.min(t1, time + 0.001))} aria-label="Ein Bild vor">1 ms ›</button>
        <label className="speed">Zeitlupe
          <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
            {SPEEDS.map((s) => <option key={s} value={s}>{s}×</option>)}
          </select>
        </label>
        <span className="mono tl-time">t = {(time * 1000).toFixed(0)} ms</span>
        <span className="tl-phase">{phase}</span>
      </div>
      <div className="tl-track">
        <input type="range" min={t0} max={t1} step={0.001} value={time} onChange={(e) => { setPlaying(false); setTime(Number(e.target.value)); }} aria-label="Zeit" />
        {marks.map((mk) => (
          <button type="button" key={mk.label} className="tl-mark" style={{ left: `${pct(mk.t)}%` }} title={`${mk.title}: ${(mk.t * 1000).toFixed(0)} ms`} onClick={() => { setPlaying(false); setTime(mk.t); }}>
            {mk.label}
          </button>
        ))}
      </div>
    </div>
  );
}
