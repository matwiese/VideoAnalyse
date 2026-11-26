/** 2D-Sweep als Heatmap (SPEC 10.3), sequenzielle Skala Schwarz → Rot → Hellrot. */
import { useState } from 'react';

interface Props {
  xs: number[]; ys: number[]; grid: number[][];
  xLabel: string; yLabel: string; zLabel: string; fmt: (v: number) => string;
}

function color(t: number): string {
  // 0 → #1c1c22, 0.6 → #E10600, 1 → #FFB3B3 (Helligkeit monoton steigend)
  const stops: [number, [number, number, number]][] = [[0, [28, 28, 34]], [0.6, [225, 6, 0]], [1, [255, 179, 179]]];
  for (let i = 1; i < stops.length; i++) {
    if (t <= stops[i][0]) {
      const [a, ca] = stops[i - 1];
      const [b, cb] = stops[i];
      const u = (t - a) / (b - a);
      const c = ca.map((v, k) => Math.round(v + (cb[k] - v) * u));
      return `rgb(${c[0]},${c[1]},${c[2]})`;
    }
  }
  return 'rgb(255,179,179)';
}

export function Heatmap({ xs, ys, grid, xLabel, yLabel, zLabel, fmt }: Props) {
  const [hover, setHover] = useState<{ i: number; j: number } | null>(null);
  const flat = grid.flat().filter(Number.isFinite);
  const lo = Math.min(...flat);
  const hi = Math.max(...flat);
  const W = 640;
  const H = 360;
  const m = { l: 64, r: 90, t: 10, b: 44 };
  const cw = (W - m.l - m.r) / xs.length;
  const ch = (H - m.t - m.b) / ys.length;
  const every = (n: number) => Math.max(1, Math.ceil(n / 8));
  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={`${zLabel} über ${xLabel} und ${yLabel}`}>
        {grid.map((row, j) => row.map((v, i) => (
          <rect key={`${i}-${j}`} x={m.l + i * cw} y={H - m.b - (j + 1) * ch} width={cw + 0.5} height={ch + 0.5}
            fill={Number.isFinite(v) ? color((v - lo) / (hi - lo || 1)) : '#333'}
            stroke={hover && hover.i === i && hover.j === j ? '#F4F4F5' : 'none'}
            onPointerEnter={() => setHover({ i, j })} onPointerLeave={() => setHover(null)} />
        )))}
        {xs.map((x, i) => i % every(xs.length) === 0 && (
          <text key={`x${i}`} x={m.l + (i + 0.5) * cw} y={H - m.b + 16} textAnchor="middle" className="tick">{+x.toFixed(2)}</text>
        ))}
        {ys.map((y, j) => j % every(ys.length) === 0 && (
          <text key={`y${j}`} x={m.l - 6} y={H - m.b - (j + 0.5) * ch + 4} textAnchor="end" className="tick">{+y.toFixed(2)}</text>
        ))}
        <text x={m.l + (W - m.l - m.r) / 2} y={H - 6} textAnchor="middle" className="axis-label">{xLabel}</text>
        <text x={14} y={m.t + (H - m.t - m.b) / 2} transform={`rotate(-90 14 ${m.t + (H - m.t - m.b) / 2})`} textAnchor="middle" className="axis-label">{yLabel}</text>
        {Array.from({ length: 40 }, (_, k) => (
          <rect key={k} x={W - m.r + 20} y={m.t + (H - m.t - m.b) * (1 - (k + 1) / 40)} width={14} height={(H - m.t - m.b) / 40 + 0.5} fill={color(k / 39)} />
        ))}
        <text x={W - m.r + 38} y={m.t + 10} className="tick">{fmt(hi)}</text>
        <text x={W - m.r + 38} y={H - m.b} className="tick">{fmt(lo)}</text>
      </svg>
      <div className="legend mono">
        {hover ? `${xLabel} = ${+xs[hover.i].toFixed(3)} · ${yLabel} = ${+ys[hover.j].toFixed(3)} → ${zLabel} = ${fmt(grid[hover.j][hover.i])}` : `${zLabel} – Zelle berühren für Wert`}
      </div>
    </div>
  );
}
