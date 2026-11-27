/**
 * Video-Tracker (Etappe 6b): Körperpunkte direkt im Browser aus einem lokalen Video verfolgen.
 * Das Video wird NICHT hochgeladen – der Browser liest die Datei per Object-URL von der Festplatte,
 * deshalb funktionieren auch sehr große Dateien (mehrere GB).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useStore } from '../store';
import { DEFAULT_CALIB, buildCsv, metersPerPixel, predict, tiltAngle, type Calibration, type Px, type Tracks } from './geometry';
import { matchTemplate, patch, toGray, type Gray } from './ncc';

const POINTS: { id: string; label: string; required: boolean; color: string }[] = [
  { id: 'board_tip', label: 'Brettspitze', required: false, color: '#F59E0B' },
  { id: 'toe', label: 'Zehenspitze', required: true, color: '#E10600' },
  { id: 'ball', label: 'Ballen (MTP)', required: false, color: '#FF4D4D' },
  { id: 'heel', label: 'Ferse', required: true, color: '#FF4D4D' },
  { id: 'ankle', label: 'Sprunggelenk', required: true, color: '#E10600' },
  { id: 'knee', label: 'Knie', required: true, color: '#E10600' },
  { id: 'hip', label: 'Hüfte (Trochanter)', required: true, color: '#E10600' },
  { id: 'shoulder', label: 'Schulter', required: true, color: '#F4F4F5' },
  { id: 'vertex', label: 'Kopf (Scheitel)', required: false, color: '#F4F4F5' },
  { id: 'elbow', label: 'Ellbogen', required: true, color: '#A1A1AA' },
  { id: 'wrist', label: 'Handgelenk', required: true, color: '#A1A1AA' },
];
const SKELETON: [string, string][] = [
  ['toe', 'ball'], ['ball', 'heel'], ['heel', 'ankle'], ['ball', 'ankle'], ['ankle', 'knee'], ['knee', 'hip'], ['hip', 'shoulder'],
  ['shoulder', 'vertex'], ['shoulder', 'elbow'], ['elbow', 'wrist'],
];

type Tool = 'track' | 'scaleA' | 'scaleB' | 'origin';

interface Project {
  fileFps: number; captureFps: number; first: number; last: number; step: number; calib: Calibration; tracks: Tracks;
}

const storageKey = (f: File) => `tracker:v1:${f.name}:${f.size}`;

function loadProject(f: File): Project | null {
  try {
    const s = localStorage.getItem(storageKey(f));
    return s ? (JSON.parse(s) as Project) : null;
  } catch {
    return null;
  }
}

function saveProject(f: File, p: Project) {
  try {
    localStorage.setItem(storageKey(f), JSON.stringify(p));
  } catch {
    /* Speicher voll oder gesperrt – Projekt per Export sichern */
  }
}

function download(name: string, content: BlobPart, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function TrackerPanel() {
  const backend = useStore((s) => s.backend);
  const setPage = useStore((s) => s.setPage);
  const setPendingAnalysis = useStore((s) => s.setPendingAnalysis);

  const videoRef = useRef<HTMLVideoElement>(null);
  const viewRef = useRef<HTMLCanvasElement>(null);
  const loupeRef = useRef<HTMLCanvasElement>(null);
  const offRef = useRef<HTMLCanvasElement | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const templates = useRef<Record<string, { frame: number; tpl: Gray }>>({});
  const stopRef = useRef(false);
  const loadedRef = useRef<Project | null>(null); // beim Öffnen gelesener Stand (vor dem ersten Autospeichern)

  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [dims, setDims] = useState<{ w: number; h: number; duration: number } | null>(null);
  const [fileFps, setFileFps] = useState(30);
  const [fpsDetected, setFpsDetected] = useState<number | null>(null);
  const [captureFps, setCaptureFps] = useState(30);
  const [frame, setFrame] = useState(0);
  const [first, setFirst] = useState(0);
  const [last, setLast] = useState(0);
  const [step, setStep] = useState(1);
  const [calib, setCalib] = useState<Calibration>(DEFAULT_CALIB);
  const [tracks, setTracks] = useState<Tracks>({});
  const [tool, setTool] = useState<Tool>('track');
  const [active, setActive] = useState('toe');
  const [advance, setAdvance] = useState<'frame' | 'point'>('frame');
  const [suggest, setSuggest] = useState<{ x: number; y: number; score: number } | null>(null);
  const [threshold, setThreshold] = useState(0.8);
  const [patchHalf, setPatchHalf] = useState(12);
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [scale, setScale] = useState(1);
  const [hover, setHover] = useState<Px | null>(null);
  const [error, setError] = useState<string | null>(null);

  const nFrames = dims ? Math.max(1, Math.floor(dims.duration * fileFps)) : 0;

  // ---------------------------------------------------------------- Datei öffnen
  const openFile = (f: File) => {
    if (url) URL.revokeObjectURL(url);
    setFile(f);
    setUrl(URL.createObjectURL(f));
    setDims(null);
    setError(null);
    setMsg(null);
    templates.current = {};
    const p = loadProject(f);
    loadedRef.current = p;
    if (p) {
      setFileFps(p.fileFps); setCaptureFps(p.captureFps); setFirst(p.first); setLast(p.last); setStep(p.step); setCalib(p.calib); setTracks(p.tracks);
      setMsg('Gespeicherter Tracking-Stand für diese Datei geladen.');
    } else {
      setCalib(DEFAULT_CALIB); setTracks({}); setStep(1);
    }
  };

  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);

  // Bildrate der Datei messen (requestVideoFrameCallback liefert die Medienzeit je Bild)
  const detectFps = useCallback(async (v: HTMLVideoElement): Promise<number | null> => {
    const rvfc = (v as HTMLVideoElement & { requestVideoFrameCallback?: (cb: (now: number, m: { mediaTime: number }) => void) => number }).requestVideoFrameCallback;
    if (!rvfc) return null;
    const times: number[] = [];
    v.muted = true;
    await new Promise<void>((resolve) => {
      const cb = (_n: number, m: { mediaTime: number }) => {
        times.push(m.mediaTime);
        if (times.length < 25) rvfc.call(v, cb); else resolve();
      };
      rvfc.call(v, cb);
      v.play().catch(() => resolve());
      setTimeout(resolve, 4000);
    });
    v.pause();
    const d = times.slice(1).map((t, i) => t - times[i]).filter((x) => x > 1e-5).sort((a, b) => a - b);
    if (d.length < 5) return null;
    const fps = 1 / d[Math.floor(d.length / 2)];
    const common = [24, 25, 29.97, 30, 48, 50, 59.94, 60, 100, 119.88, 120, 200, 239.76, 240, 250, 480, 500, 960, 1000];
    const near = common.reduce((a, c) => (Math.abs(c - fps) < Math.abs(a - fps) ? c : a), common[0]);
    return Math.abs(near - fps) / near < 0.02 ? near : Math.round(fps * 100) / 100;
  }, []);

  const onLoaded = async () => {
    const v = videoRef.current!;
    setDims({ w: v.videoWidth, h: v.videoHeight, duration: v.duration });
    const off = document.createElement('canvas');
    off.width = v.videoWidth;
    off.height = v.videoHeight;
    offRef.current = off;
    const fps = await detectFps(v);
    const p = loadedRef.current;
    if (fps) {
      setFpsDetected(fps);
      if (!p) { setFileFps(fps); setCaptureFps(fps); }
    }
    const n = Math.floor(v.duration * (p?.fileFps ?? fps ?? 30));
    if (!p) { setFirst(0); setLast(Math.max(0, n - 1)); }
    await seek(p?.first ?? 0, p?.fileFps ?? fps ?? 30);
  };

  // ---------------------------------------------------------------- Bild anspringen
  const seekId = useRef(0);
  const seekChain = useRef<Promise<void>>(Promise.resolve());
  /** Springt bildgenau zu Bild n. Sprünge werden nacheinander ausgeführt; nur der neueste
   *  aktualisiert Anzeige und Zustand (keine Überholvorgänge bei schnellem Bedienen). */
  const seek = useCallback((n: number, fpsOverride?: number): Promise<boolean> => {
    const id = ++seekId.current;
    const run = async () => {
      const v = videoRef.current;
      if (!v || !offRef.current || id !== seekId.current) return;
      const fps = fpsOverride ?? fileFps;
      const t = Math.min((n + 0.5) / fps, Math.max(0, v.duration - 1e-3));
      if (Math.abs(v.currentTime - t) > 1e-4) {
        await new Promise<void>((resolve) => {
          const done = () => { v.removeEventListener('seeked', done); resolve(); };
          v.addEventListener('seeked', done);
          v.currentTime = t;
          setTimeout(done, 3000);
        });
      }
      if (id !== seekId.current) return;
      offRef.current.getContext('2d', { willReadFrequently: true })!.drawImage(v, 0, 0);
      setFrame(n);
    };
    const p = seekChain.current.then(run);
    seekChain.current = p.catch(() => undefined);
    return p.then(() => id === seekId.current);
  }, [fileFps]);

  /** Bedienung durch den Menschen: laufende Automatik zuerst stoppen. */
  const userSeek = (n: number) => { stopRef.current = true; return seek(n); };

  const grayAround = (cx: number, cy: number, r: number): { g: Gray; x0: number; y0: number } | null => {
    const off = offRef.current;
    if (!off) return null;
    const x0 = Math.max(0, Math.round(cx) - r);
    const y0 = Math.max(0, Math.round(cy) - r);
    const w = Math.min(off.width - x0, 2 * r + 1);
    const h = Math.min(off.height - y0, 2 * r + 1);
    if (w <= 0 || h <= 0) return null;
    const img = off.getContext('2d', { willReadFrequently: true })!.getImageData(x0, y0, w, h);
    return { g: toGray(img.data, w, h), x0, y0 };
  };

  const storeTemplate = (pt: string, f: number, p: Px) => {
    const reg = grayAround(p[0], p[1], patchHalf + 1);
    if (!reg) return;
    const tp = patch(reg.g, p[0] - reg.x0, p[1] - reg.y0, patchHalf);
    if (tp) templates.current[pt] = { frame: f, tpl: tp };
  };

  const suggestFor = (pt: string, f: number, tr: Tracks): { x: number; y: number; score: number } | null => {
    const tm = templates.current[pt];
    const pred = predict(tr[pt], f, step);
    if (!tm || !pred) return null;
    // Suchradius aus der Bewegung der letzten Bilder (+ Reserve), begrenzt
    const a = tr[pt]?.[f - step];
    const b = tr[pt]?.[f - 2 * step];
    const speed = a && b ? Math.hypot(a[0] - b[0], a[1] - b[1]) : patchHalf;
    const search = Math.round(Math.min(Math.max(8, 0.8 * speed + 6), 3 * patchHalf));
    const reg = grayAround(pred[0], pred[1], search + patchHalf + 2);
    if (!reg) return null;
    const m = matchTemplate(reg.g, tm.tpl, pred[0] - reg.x0, pred[1] - reg.y0, search, 0.35);
    if (!m) return null;
    const res = { x: m.x + reg.x0, y: m.y + reg.y0, score: m.score };
    // Sprung weit weg von der Vorhersage → als unsicher markieren (Automatik hält an)
    if (Math.hypot(res.x - pred[0], res.y - pred[1]) > 0.75 * search + 2) res.score = Math.min(res.score, threshold - 0.01);
    return res;
  };

  // Vorschlag berechnen, wenn das Bild wechselt
  useEffect(() => {
    if (!dims || tool !== 'track' || running) { setSuggest(null); return; }
    if (tracks[active]?.[frame]) { setSuggest(null); return; }
    setSuggest(suggestFor(active, frame, tracks));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frame, active, tool, dims, running]);

  // ---------------------------------------------------------------- Zeichnen
  const draw = useCallback(() => {
    const cv = viewRef.current;
    const off = offRef.current;
    if (!cv || !off || !dims) return;
    const wrap = wrapRef.current!;
    const maxW = wrap.clientWidth;
    const maxH = Math.max(260, window.innerHeight * 0.62);
    const s = Math.min(maxW / dims.w, maxH / dims.h);
    setScale(s);
    const dpr = window.devicePixelRatio || 1;
    cv.width = Math.round(dims.w * s * dpr);
    cv.height = Math.round(dims.h * s * dpr);
    cv.style.width = `${dims.w * s}px`;
    cv.style.height = `${dims.h * s}px`;
    const ctx = cv.getContext('2d')!;
    ctx.setTransform(dpr * s, 0, 0, dpr * s, 0, 0);
    ctx.drawImage(off, 0, 0);
    const lw = 1.5 / s;
    // Kalibrierung
    if (calib.scaleA && calib.scaleB) {
      ctx.strokeStyle = '#F59E0B'; ctx.lineWidth = lw; ctx.setLineDash([6 / s, 4 / s]);
      ctx.beginPath(); ctx.moveTo(...calib.scaleA); ctx.lineTo(...calib.scaleB); ctx.stroke(); ctx.setLineDash([]);
    }
    for (const p of [calib.scaleA, calib.scaleB]) if (p) { ctx.fillStyle = '#F59E0B'; ctx.beginPath(); ctx.arc(p[0], p[1], 3 / s, 0, 7); ctx.fill(); }
    if (calib.origin) {
      const [ox, oy] = calib.origin; const r = 10 / s;
      ctx.strokeStyle = '#22C55E'; ctx.lineWidth = lw;
      ctx.beginPath(); ctx.moveTo(ox - r, oy); ctx.lineTo(ox + r, oy); ctx.moveTo(ox, oy - r); ctx.lineTo(ox, oy + r); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(ox, oy); ctx.lineTo(ox + (calib.waterRight ? 40 : -40) / s, oy); ctx.stroke();
    }
    // Spur des aktiven Punkts
    const tr = tracks[active];
    if (tr) {
      ctx.strokeStyle = 'rgba(225,6,0,0.6)'; ctx.lineWidth = lw; ctx.beginPath();
      let pen = false;
      for (let f = frame - 30 * step; f <= frame; f += step) {
        const p = tr[f];
        if (!p) { pen = false; continue; }
        if (pen) ctx.lineTo(p[0], p[1]); else ctx.moveTo(p[0], p[1]);
        pen = true;
      }
      ctx.stroke();
    }
    // Strichfigur
    ctx.strokeStyle = 'rgba(244,244,245,0.85)'; ctx.lineWidth = 2 / s;
    for (const [a, b] of SKELETON) {
      const pa = tracks[a]?.[frame]; const pb = tracks[b]?.[frame];
      if (pa && pb) { ctx.beginPath(); ctx.moveTo(...pa); ctx.lineTo(...pb); ctx.stroke(); }
    }
    for (const pt of POINTS) {
      const p = tracks[pt.id]?.[frame];
      if (!p) continue;
      const isA = pt.id === active;
      ctx.fillStyle = pt.color; ctx.strokeStyle = '#0B0B0D'; ctx.lineWidth = 1 / s;
      ctx.beginPath(); ctx.arc(p[0], p[1], (isA ? 5 : 3.5) / s, 0, 7); ctx.fill(); ctx.stroke();
      if (isA) { ctx.strokeStyle = '#F4F4F5'; ctx.beginPath(); ctx.arc(p[0], p[1], 9 / s, 0, 7); ctx.stroke(); }
    }
    if (suggest) {
      ctx.strokeStyle = suggest.score >= threshold ? '#22C55E' : '#F59E0B'; ctx.lineWidth = lw; ctx.setLineDash([3 / s, 3 / s]);
      ctx.beginPath(); ctx.arc(suggest.x, suggest.y, 8 / s, 0, 7); ctx.stroke(); ctx.setLineDash([]);
    }
  }, [dims, calib, tracks, active, frame, step, suggest, threshold]);

  useEffect(() => { draw(); }, [draw]);
  useEffect(() => {
    const on = () => draw();
    window.addEventListener('resize', on);
    return () => window.removeEventListener('resize', on);
  }, [draw]);

  // Lupe
  useEffect(() => {
    const lp = loupeRef.current;
    const off = offRef.current;
    if (!lp || !off || !hover) return;
    const ctx = lp.getContext('2d')!;
    const Z = 4;
    const size = lp.width;
    ctx.imageSmoothingEnabled = false;
    ctx.fillStyle = '#0B0B0D'; ctx.fillRect(0, 0, size, size);
    ctx.drawImage(off, hover[0] - size / Z / 2, hover[1] - size / Z / 2, size / Z, size / Z, 0, 0, size, size);
    ctx.strokeStyle = '#E10600'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(size / 2, 0); ctx.lineTo(size / 2, size); ctx.moveTo(0, size / 2); ctx.lineTo(size, size / 2); ctx.stroke();
  }, [hover, frame]);

  // Projekt speichern
  useEffect(() => {
    if (file && dims && last > first) saveProject(file, { fileFps, captureFps, first, last, step, calib, tracks });
  }, [file, dims, fileFps, captureFps, first, last, step, calib, tracks]);

  // ---------------------------------------------------------------- Interaktion
  const toImage = (e: React.MouseEvent): Px => {
    const r = viewRef.current!.getBoundingClientRect();
    return [(e.clientX - r.left) / scale, (e.clientY - r.top) / scale];
  };

  const setPoint = (pt: string, f: number, p: Px) => {
    setTracks((tr) => ({ ...tr, [pt]: { ...(tr[pt] ?? {}), [f]: p } }));
    storeTemplate(pt, f, p);
  };

  const goNext = async (pt: string) => {
    if (advance === 'point') {
      const ids = POINTS.map((p) => p.id);
      const i = ids.indexOf(pt);
      if (i < ids.length - 1) { setActive(ids[i + 1]); return; }
      setActive(ids[0]);
    }
    if (frame + step <= last) await seek(frame + step);
  };

  const onClick = async (e: React.MouseEvent) => {
    if (!dims || running) return;
    const p = toImage(e);
    if (tool === 'scaleA') { setCalib({ ...calib, scaleA: p }); setTool('scaleB'); return; }
    if (tool === 'scaleB') { setCalib({ ...calib, scaleB: p }); setTool('track'); return; }
    if (tool === 'origin') { setCalib({ ...calib, origin: p }); setTool('track'); return; }
    setPoint(active, frame, p);
    await goNext(active);
  };

  const acceptSuggestion = async () => {
    if (!suggest) return;
    setPoint(active, frame, [suggest.x, suggest.y]);
    await goNext(active);
  };

  const autoTrack = async () => {
    // Start beim zuletzt gesetzten Punkt ≤ aktuellem Bild (nach einem Klick ist das Bild schon weitergesprungen)
    const own = tracks[active] ?? {};
    const f0 = Object.keys(own).map(Number).filter((x) => x <= frame && x >= first).sort((a, b) => b - a)[0];
    if (f0 === undefined) { setMsg('Erst den Punkt in einem Bild anklicken, dann automatisch weiterverfolgen.'); return; }
    if (templates.current[active]?.frame !== f0) {
      await seek(f0);
      storeTemplate(active, f0, own[f0]);
    }
    stopRef.current = false;
    setRunning(true);
    setMsg(null);
    let f = f0;
    let tr = tracks;
    let n = 0;
    while (!stopRef.current && f + step <= last) {
      const ok = await seek(f + step);
      if (!ok || stopRef.current) break;
      f += step;
      const s = suggestFor(active, f, tr);
      if (!s || s.score < threshold) {
        setMsg(`Automatik angehalten bei Bild ${f}: ${s ? `Übereinstimmung ${s.score.toFixed(2)} < ${threshold}` : 'Punkt nicht gefunden'} – bitte anklicken.`);
        setSuggest(s);
        break;
      }
      const p: Px = [s.x, s.y];
      tr = { ...tr, [active]: { ...(tr[active] ?? {}), [f]: p } };
      setTracks(tr);
      storeTemplate(active, f, p);
      n++;
    }
    if (!stopRef.current && f + step > last) setMsg(`Automatik bis zum Bereichsende: ${n} Bilder verfolgt. Bitte stichprobenartig prüfen.`);
    setRunning(false);
  };

  useEffect(() => {
    const onKey = async (e: KeyboardEvent) => {
      if (!dims || running || (e.target as HTMLElement).tagName === 'INPUT' || (e.target as HTMLElement).tagName === 'SELECT') return;
      const k = e.shiftKey ? 10 * step : step;
      if (e.key === 'ArrowRight') { e.preventDefault(); await userSeek(Math.min(frame + k, nFrames - 1)); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); await userSeek(Math.max(frame - k, 0)); }
      else if (e.key === 'Enter') { e.preventDefault(); await acceptSuggestion(); }
      else if (e.key === 'Delete' || e.key === 'Backspace') {
        setTracks((tr) => { const c = { ...(tr[active] ?? {}) }; delete c[frame]; return { ...tr, [active]: c }; });
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  // ---------------------------------------------------------------- Auswertung
  const mpp = metersPerPixel(calib);
  const inRange = useMemo(() => {
    const out: Record<string, number> = {};
    const total = Math.floor((last - first) / step) + 1;
    for (const p of POINTS) {
      let c = 0;
      const t = tracks[p.id] ?? {};
      for (let f = first; f <= last; f += step) if (t[f]) c++;
      out[p.id] = c;
    }
    out._total = total;
    return out;
  }, [tracks, first, last, step]);
  const missingReq = POINTS.filter((p) => p.required && inRange[p.id] === 0).map((p) => p.label);
  const ready = mpp !== null && calib.origin !== null && missingReq.length === 0;

  const csv = () => buildCsv(tracks, POINTS.map((p) => p.id), calib, captureFps, first, last, step);
  const exportCsv = () => download(`${file?.name ?? 'tracking'}.csv`, csv(), 'text/csv');
  const toAnalysis = () => {
    setPendingAnalysis({
      name: `${file?.name ?? 'tracking'}.csv`, text: csv(),
      settings: { horizontal: 'x', vertical: 'y', flip_horizontal: false, flip_vertical: false, unit: 'm', origin: 'manual', origin_x: 0, origin_z: 0 },
    });
    setPage('ana');
  };
  const exportProject = () => download(`${file?.name ?? 'tracking'}.tracker.json`, JSON.stringify({ fileFps, captureFps, first, last, step, calib, tracks }), 'application/json');
  const importProject = async (f: File) => {
    try {
      const p = JSON.parse(await f.text()) as Project;
      setFileFps(p.fileFps); setCaptureFps(p.captureFps); setFirst(p.first); setLast(p.last); setStep(p.step); setCalib(p.calib); setTracks(p.tracks);
      setMsg('Tracking-Projekt geladen.');
    } catch (e) {
      setMsg(`Projekt nicht lesbar: ${(e as Error).message}`);
    }
  };

  const timeScale = fileFps / captureFps;

  return (
    <div className="tracker">
      <div className="study-form tracker-side">
        <div className="footnote">Video bleibt auf deinem Rechner (kein Upload) – auch sehr große Dateien funktionieren. Formate: was dein Browser abspielt (MP4/H.264 überall; HEVC/.mov v. a. Safari/Edge).</div>
        <label>Video öffnen<input type="file" accept="video/*,.mov,.mp4,.m4v,.avi,.mkv" onChange={(e) => e.target.files?.[0] && openFile(e.target.files[0])} /></label>
        {file && <div className="mono footnote">{file.name} · {(file.size / 1e9).toFixed(2)} GB{dims ? ` · ${dims.w}×${dims.h} · ${dims.duration.toFixed(1)} s` : ' · lädt …'}</div>}
        {error && <div className="warning">⚠ {error}</div>}
        {dims && <>
          <details open>
            <summary>1 · Bildrate (Zeitlupe!)</summary>
            <div className="grid2">
              <label>Bildrate der Datei [Bilder/s]<input type="number" step={0.01} value={fileFps} onChange={(e) => setFileFps(Number(e.target.value) || 30)} /></label>
              <label>Echte Aufnahme-Bildrate [Bilder/s]<input type="number" step={0.01} value={captureFps} onChange={(e) => setCaptureFps(Number(e.target.value) || fileFps)} /></label>
            </div>
            <div className="footnote">{fpsDetected ? `Gemessen: ${fpsDetected} Bilder/s in der Datei. ` : 'Bildrate der Datei nicht messbar – bitte eintragen. '}
              {timeScale !== 1 ? <strong>Zeitlupe: 1 s Video = {(1 / timeScale).toFixed(3)} s echte Zeit.</strong> : 'Bei Handy-Zeitlupen (z. B. 240 Bilder/s, als 30 Bilder/s gespeichert) hier die echte Aufnahmerate eintragen.'}</div>
          </details>
          <details open>
            <summary>2 · Bereich</summary>
            <div className="grid2">
              <label>Erstes Bild<input type="number" value={first} onChange={(e) => setFirst(Math.max(0, Number(e.target.value)))} /></label>
              <label>Letztes Bild<input type="number" value={last} onChange={(e) => setLast(Math.min(nFrames - 1, Number(e.target.value)))} /></label>
            </div>
            <div className="row-btns">
              <button type="button" className="btn small" onClick={() => setFirst(frame)}>Aktuelles = Start</button>
              <button type="button" className="btn small" onClick={() => setLast(frame)}>Aktuelles = Ende</button>
            </div>
            <label>Jedes n-te Bild tracken<select value={step} onChange={(e) => setStep(Number(e.target.value))}>{[1, 2, 3, 4, 5, 8].map((s) => <option key={s} value={s}>{s} (→ {(captureFps / s).toFixed(0)} Hz echt)</option>)}</select></label>
            <div className="footnote">Bereich: Hürden-Lift-off bis ~0,3 s nach dem Absprung. Echt ≥ 200 Hz empfohlen.</div>
          </details>
          <details open>
            <summary>3 · Kalibrierung</summary>
            <div className="row-btns">
              <button type="button" className={`btn small ${tool === 'scaleA' || tool === 'scaleB' ? 'primary' : ''}`} onClick={() => setTool('scaleA')}>Maßstab: 2 Punkte klicken</button>
              <button type="button" className={`btn small ${tool === 'origin' ? 'primary' : ''}`} onClick={() => setTool('origin')}>Brettspitze in Ruhe klicken</button>
            </div>
            <div className="grid2">
              <label>Länge der Strecke [m]<input type="number" step={0.001} value={calib.scaleLength} onChange={(e) => setCalib({ ...calib, scaleLength: Number(e.target.value) })} /></label>
              <label>Wasser im Bild<select value={calib.waterRight ? 'r' : 'l'} onChange={(e) => setCalib({ ...calib, waterRight: e.target.value === 'r' })}><option value="r">rechts</option><option value="l">links</option></select></label>
            </div>
            <label className="check"><input type="checkbox" checked={calib.scaleIsHorizontal} onChange={(e) => setCalib({ ...calib, scaleIsHorizontal: e.target.checked })} /> Strecke ist waagrecht (Kameraneigung korrigieren)</label>
            <div className="mono footnote">
              Maßstab: {mpp ? `${(mpp * 1000).toFixed(2)} mm/px` : '–'} · Neigung: {(tiltAngle(calib) * 180 / Math.PI).toFixed(2)}° · Ursprung: {calib.origin ? 'gesetzt' : '–'}
            </div>
            <div className="footnote">Maßstab z. B. über einen Meterstab in der Brettebene oder die Brettlänge (4,88 m), falls ganz sichtbar. „Brettspitze in Ruhe“ in einem Bild, in dem niemand auf dem Brett ist.</div>
          </details>
          <details open>
            <summary>4 · Punkte verfolgen</summary>
            <div className="point-list">
              {POINTS.map((p) => (
                <button type="button" key={p.id} className={`point ${active === p.id ? 'active' : ''}`} onClick={() => { stopRef.current = true; setActive(p.id); setTool('track'); }}>
                  <span className="dot" style={{ background: p.color }} />{p.label}{p.required ? ' *' : ''}
                  <span className="mono cnt">{inRange[p.id]}/{inRange._total}</span>
                </button>
              ))}
            </div>
            <label>Nach Klick<select value={advance} onChange={(e) => setAdvance(e.target.value as 'frame' | 'point')}><option value="frame">nächstes Bild (Punkt für Punkt)</option><option value="point">nächster Punkt (Bild für Bild)</option></select></label>
            <div className="row-btns">
              {!running
                ? <button type="button" className="btn small primary" onClick={autoTrack} title="Verfolgt den aktiven Punkt automatisch per Bildvergleich, bis die Übereinstimmung unter die Schwelle fällt">Automatisch weiter ▶</button>
                : <button type="button" className="btn small" onClick={() => { stopRef.current = true; }}>Stopp</button>}
              <button type="button" className="btn small" onClick={acceptSuggestion} disabled={!suggest}>Vorschlag übernehmen (Enter)</button>
            </div>
            <div className="grid2">
              <label>Schwelle Übereinstimmung<input type="number" step={0.05} min={0.3} max={0.99} value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} /></label>
              <label>Mustergröße [px]<input type="number" min={5} max={40} value={patchHalf} onChange={(e) => { setPatchHalf(Number(e.target.value)); templates.current = {}; }} /></label>
            </div>
            <div className="footnote">Tasten: ← → Bild (Shift: ×10), Enter = Vorschlag übernehmen, Entf = Punkt im Bild löschen. Klebepunkte auf der Haut verbessern die Automatik deutlich.</div>
          </details>
          <details open>
            <summary>5 · Export</summary>
            {!ready && <div className="warning">Noch offen: {[mpp === null ? 'Maßstab' : null, calib.origin ? null : 'Brettspitze in Ruhe', ...missingReq].filter(Boolean).join(', ')}</div>}
            <div className="row-btns">
              <button type="button" className="btn small primary" disabled={!ready || !backend} onClick={toAnalysis} title={backend ? '' : 'Analyse nur in der Vollversion'}>An Analyse übergeben</button>
              <button type="button" className="btn small" disabled={!ready} onClick={exportCsv}>CSV speichern</button>
            </div>
            <div className="row-btns">
              <button type="button" className="btn small ghost" onClick={exportProject}>Projekt sichern</button>
              <label className="btn small ghost file-btn">Projekt laden<input type="file" accept=".json" hidden onChange={(e) => e.target.files?.[0] && importProject(e.target.files[0])} /></label>
            </div>
            <div className="footnote">Der Tracking-Stand wird automatisch im Browser gespeichert (je Datei). „Projekt sichern“ für Backup/Weitergabe.</div>
          </details>
        </>}
      </div>

      <div className="tracker-main" ref={wrapRef}>
        {!url && <div className="placeholder">Video öffnen, um zu beginnen. Ablauf: Bildrate → Bereich → Kalibrierung → Punkte → Export.</div>}
        {url && (
          <>
            <video ref={videoRef} src={url} preload="auto" muted playsInline style={{ display: 'none' }}
              onLoadedMetadata={onLoaded}
              onError={() => setError('Video lässt sich in diesem Browser nicht abspielen (oft HEVC/.mov in Chrome/Firefox). Lösung: in Safari/Edge öffnen oder nach H.264 umwandeln, z. B. ffmpeg -i in.mov -c:v libx264 -crf 18 -an out.mp4')} />
            <div className="tracker-canvas">
              <canvas ref={viewRef} className={tool === 'track' ? 'cur-track' : 'cur-calib'} onClick={onClick}
                onMouseMove={(e) => setHover(toImage(e))} onMouseLeave={() => setHover(null)} />
              {hover && <canvas ref={loupeRef} width={160} height={160} className="loupe" />}
            </div>
            {dims && (
              <div className="timeline tracker-tl">
                <div className="tl-controls">
                  <button type="button" className="btn ghost" onClick={() => userSeek(Math.max(0, frame - 10 * step))}>«</button>
                  <button type="button" className="btn ghost" onClick={() => userSeek(Math.max(0, frame - step))}>‹</button>
                  <button type="button" className="btn ghost" onClick={() => userSeek(Math.min(nFrames - 1, frame + step))}>›</button>
                  <button type="button" className="btn ghost" onClick={() => userSeek(Math.min(nFrames - 1, frame + 10 * step))}>»</button>
                  <span className="mono tl-time">Bild {frame} / {nFrames - 1} · t = {((frame - first) / captureFps * 1000).toFixed(0)} ms (echt, ab Start)</span>
                  <span className="tl-phase">{tool === 'scaleA' ? 'Maßstab: Punkt 1 klicken' : tool === 'scaleB' ? 'Maßstab: Punkt 2 klicken' : tool === 'origin' ? 'Brettspitze in Ruhe klicken' : `Aktiv: ${POINTS.find((p) => p.id === active)?.label}`}</span>
                  {suggest && <span className="mono footnote">Vorschlag: Übereinstimmung {suggest.score.toFixed(2)}</span>}
                </div>
                <input type="range" min={0} max={nFrames - 1} value={frame} onChange={(e) => userSeek(Number(e.target.value))} aria-label="Bild" />
              </div>
            )}
            {msg && <div className="warning">{msg}</div>}
          </>
        )}
      </div>
    </div>
  );
}
