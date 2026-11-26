/**
 * Schlanker SVG-Liniendiagramm-Baustein (Zeitverläufe, 1D-Sweeps).
 * Rot nur für die Hauptkurve; weitere Kurven in Graustufen mit Linienstil (SPEC 10.4).
 */
import { useMemo, useRef, useState } from 'react';

export interface LineSeries {
  name: string;
  x: ArrayLike<number>;
  y: ArrayLike<number>;
  color?: string;
  dash?: string;
  width?: number;
  axis?: 'left' | 'right';
}

interface Props {
  series: LineSeries[];
  height?: number;
  xLabel: string;
  yLabel: string;
  yLabelRight?: string;
  cursor?: number;
  marks?: { x: number; label: string }[];
  onScrub?: (x: number) => void;
  xDomain?: [number, number];
}

function ticks(min: number, max: number, n = 5): number[] {
  const span = max - min || 1;
  const step0 = span / n;
  const e = Math.pow(10, Math.floor(Math.log10(step0)));
  const f = step0 / e;
  const step = (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * e;
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(Math.abs(v) < step * 1e-6 ? 0 : v);
  return out;
}

function extent(list: LineSeries[], key: 'x' | 'y'): [number, number] {
  let lo = Infinity;
  let hi = -Infinity;
  for (const s of list) for (let i = 0; i < s[key].length; i++) {
    const v = s[key][i];
    if (Number.isFinite(v)) { if (v < lo) lo = v; if (v > hi) hi = v; }
  }
  if (!Number.isFinite(lo)) return [0, 1];
  if (lo === hi) return [lo - 1, hi + 1];
  return [lo, hi];
}

const fmt = (v: number) => {
  const a = Math.abs(v);
  if (a >= 1000) return v.toFixed(0);
  if (a >= 10) return v.toFixed(0);
  if (a >= 1) return v.toFixed(1);
  return v.toFixed(2);
};

export function LineChart({ series, height = 220, xLabel, yLabel, yLabelRight, cursor, marks, onScrub, xDomain }: Props) {
  const ref = useRef<SVGSVGElement>(null);
  const [w, setW] = useState(640);
  const W = w;
  const H = height;
  const m = { l: 52, r: yLabelRight ? 52 : 14, t: 12, b: 34 };
  const left = series.filter((s) => s.axis !== 'right');
  const right = series.filter((s) => s.axis === 'right');
  const [x0, x1] = xDomain ?? extent(series, 'x');
  const [yl0, yl1] = extent(left, 'y');
  const [yr0, yr1] = right.length ? extent(right, 'y') : [0, 1];
  const padL = (yl1 - yl0) * 0.06;
  const padR = (yr1 - yr0) * 0.06;
  const sx = (x: number) => m.l + ((x - x0) / (x1 - x0 || 1)) * (W - m.l - m.r);
  const syL = (y: number) => H - m.b - ((y - (yl0 - padL)) / (yl1 - yl0 + 2 * padL || 1)) * (H - m.t - m.b);
  const syR = (y: number) => H - m.b - ((y - (yr0 - padR)) / (yr1 - yr0 + 2 * padR || 1)) * (H - m.t - m.b);

  const paths = useMemo(() => series.map((s) => {
    const sy = s.axis === 'right' ? syR : syL;
    const n = s.x.length;
    const stride = Math.max(1, Math.floor(n / 1200));
    let d = '';
    let pen = false;
    for (let i = 0; i < n; i += stride) {
      const xv = s.x[i];
      const yv = s.y[i];
      if (!Number.isFinite(yv) || xv < x0 || xv > x1) { pen = false; continue; }
      d += `${pen ? 'L' : 'M'}${sx(xv).toFixed(1)},${sy(yv).toFixed(1)}`;
      pen = true;
    }
    return d;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [series, W, H, x0, x1, yl0, yl1, yr0, yr1]);

  const measure = (el: SVGSVGElement | null) => {
    (ref as React.MutableRefObject<SVGSVGElement | null>).current = el;
    if (el) {
      const cw = el.parentElement?.clientWidth ?? 640;
      if (Math.abs(cw - w) > 4) setW(cw);
    }
  };

  const scrub = (e: React.PointerEvent<SVGSVGElement>) => {
    if (!onScrub || !ref.current || (e.type === 'pointermove' && e.buttons !== 1)) return;
    const r = ref.current.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    onScrub(x0 + ((px - m.l) / (W - m.l - m.r)) * (x1 - x0));
  };

  return (
    <div className="chart">
      <svg ref={measure} viewBox={`0 0 ${W} ${H}`} width="100%" height={H} onPointerDown={scrub} onPointerMove={scrub} role="img" aria-label={`${yLabel} über ${xLabel}`}>
        {ticks(yl0 - padL, yl1 + padL).map((t) => (
          <g key={`yl${t}`}>
            <line x1={m.l} x2={W - m.r} y1={syL(t)} y2={syL(t)} className="grid" />
            <text x={m.l - 6} y={syL(t) + 4} textAnchor="end" className="tick">{fmt(t)}</text>
          </g>
        ))}
        {right.length > 0 && ticks(yr0 - padR, yr1 + padR).map((t) => (
          <text key={`yr${t}`} x={W - m.r + 6} y={syR(t) + 4} className="tick">{fmt(t)}</text>
        ))}
        {ticks(x0, x1, 8).map((t) => (
          <g key={`x${t}`}>
            <line x1={sx(t)} x2={sx(t)} y1={H - m.b} y2={H - m.b + 4} className="axis" />
            <text x={sx(t)} y={H - m.b + 16} textAnchor="middle" className="tick">{fmt(t)}</text>
          </g>
        ))}
        <line x1={m.l} x2={W - m.r} y1={H - m.b} y2={H - m.b} className="axis" />
        {marks?.filter((mk) => mk.x >= x0 && mk.x <= x1).map((mk) => (
          <g key={mk.label}>
            <line x1={sx(mk.x)} x2={sx(mk.x)} y1={m.t} y2={H - m.b} className="mark" />
            <text x={sx(mk.x) + 3} y={m.t + 10} className="mark-label">{mk.label}</text>
          </g>
        ))}
        {series.map((s, i) => (
          <path key={s.name + i} d={paths[i]} fill="none" stroke={s.color ?? 'var(--red)'} strokeWidth={s.width ?? 1.8} strokeDasharray={s.dash} vectorEffect="non-scaling-stroke" />
        ))}
        {cursor !== undefined && cursor >= x0 && cursor <= x1 && (
          <line x1={sx(cursor)} x2={sx(cursor)} y1={m.t} y2={H - m.b} className="cursor" />
        )}
        <text x={14} y={m.t + (H - m.t - m.b) / 2} transform={`rotate(-90 14 ${m.t + (H - m.t - m.b) / 2})`} textAnchor="middle" className="axis-label">{yLabel}</text>
        {yLabelRight && <text x={W - 10} y={m.t + (H - m.t - m.b) / 2} transform={`rotate(90 ${W - 10} ${m.t + (H - m.t - m.b) / 2})`} textAnchor="middle" className="axis-label">{yLabelRight}</text>}
        <text x={W - m.r} y={H - 4} textAnchor="end" className="axis-label">{xLabel}</text>
      </svg>
      <div className="legend">
        {series.map((s, i) => (
          <span key={s.name + i} className="legend-item">
            <svg width="22" height="8"><line x1="0" x2="22" y1="4" y2="4" stroke={s.color ?? 'var(--red)'} strokeWidth={2} strokeDasharray={s.dash} /></svg>
            {s.name}
          </span>
        ))}
      </div>
    </div>
  );
}
