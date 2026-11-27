/**
 * Video-Tracker: Kalibrierung Pixel → Meter und CSV-Export (reine Funktionen, getestet).
 *
 * Bildkoordinaten: u nach rechts, v nach unten [px]. Simulationskoordinaten (SPEC Kap. 3):
 * x Richtung Wasser, z nach oben [m], Ursprung = Brettspitze in Ruhe.
 */

export type Px = [number, number];

export interface Calibration {
  /** Zwei Punkte einer Strecke bekannter Länge [px] */
  scaleA: Px | null;
  scaleB: Px | null;
  /** Länge der Strecke [m] */
  scaleLength: number;
  /** Strecke ist horizontal → Kameraneigung korrigieren */
  scaleIsHorizontal: boolean;
  /** Brettspitze in Ruhe (unbelastet) [px] = Ursprung */
  origin: Px | null;
  /** Wasser liegt im Bild rechts */
  waterRight: boolean;
}

export const DEFAULT_CALIB: Calibration = {
  scaleA: null, scaleB: null, scaleLength: 1.0, scaleIsHorizontal: false, origin: null, waterRight: true,
};

/** Maßstab [m/px] oder null, solange die Strecke fehlt. */
export function metersPerPixel(c: Calibration): number | null {
  if (!c.scaleA || !c.scaleB || !(c.scaleLength > 0)) return null;
  const d = Math.hypot(c.scaleB[0] - c.scaleA[0], c.scaleB[1] - c.scaleA[1]);
  return d > 0 ? c.scaleLength / d : null;
}

/** Kameraneigung [rad] aus der als horizontal markierten Strecke, normiert auf (−π/2, π/2]. */
export function tiltAngle(c: Calibration): number {
  if (!c.scaleIsHorizontal || !c.scaleA || !c.scaleB) return 0;
  let th = Math.atan2(c.scaleB[1] - c.scaleA[1], c.scaleB[0] - c.scaleA[0]);
  if (th > Math.PI / 2) th -= Math.PI;
  if (th <= -Math.PI / 2) th += Math.PI;
  return th;
}

/** Pixel → Simulationskoordinaten [m]. Wirft, wenn Maßstab oder Ursprung fehlen. */
export function toMeters(c: Calibration, p: Px): [number, number] {
  const s = metersPerPixel(c);
  if (s === null) throw new Error('Maßstab fehlt');
  if (!c.origin) throw new Error('Ursprung (Brettspitze in Ruhe) fehlt');
  const th = tiltAngle(c);
  const du = p[0] - c.origin[0];
  const dv = p[1] - c.origin[1];
  const u = du * Math.cos(th) + dv * Math.sin(th);
  const v = -du * Math.sin(th) + dv * Math.cos(th);
  return [s * u * (c.waterRight ? 1 : -1), -s * v];
}

/** Zeitumrechnung: Bildnummer der Datei → echte Zeit [s] (Zeitlupen-Korrektur). */
export function frameToRealTime(frame: number, captureFps: number): number {
  return frame / captureFps;
}

export type Tracks = Record<string, Record<number, Px>>;

/**
 * CSV im Import-Format der App: „time (s), <name> X (m), <name> Y (m), …“ (Y = vertikal).
 * Nur Bilder im Bereich [first, last] mit Schrittweite step; fehlende Werte bleiben leer
 * (der Import interpoliert Lücken und meldet sie).
 */
export function buildCsv(tracks: Tracks, points: string[], c: Calibration, captureFps: number, first: number, last: number, step: number): string {
  const used = points.filter((p) => tracks[p] && Object.keys(tracks[p]).length > 0);
  const head = ['time (s)', ...used.flatMap((p) => [`${p} X (m)`, `${p} Y (m)`])];
  const lines = [head.join(',')];
  for (let f = first; f <= last; f += step) {
    const row: string[] = [frameToRealTime(f - first, captureFps).toFixed(6)];
    let any = false;
    for (const p of used) {
      const px = tracks[p][f];
      if (px) {
        const [x, z] = toMeters(c, px);
        row.push(x.toFixed(5), z.toFixed(5));
        any = true;
      } else row.push('', '');
    }
    if (any) lines.push(row.join(','));
  }
  return lines.join('\n') + '\n';
}

/** Lineare Vorhersage der nächsten Position aus den letzten beiden Bildern. */
export function predict(track: Record<number, Px> | undefined, frame: number, step: number): Px | null {
  if (!track) return null;
  const a = track[frame - step];
  const b = track[frame - 2 * step];
  if (a && b) return [2 * a[0] - b[0], 2 * a[1] - b[1]];
  if (a) return [a[0], a[1]];
  return null;
}
