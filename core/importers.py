"""Import gemessener Kinematik (Modus B, SPEC 6.7 / Etappe 6).

Unterstützt:
- TRC (OpenCap, Motion-Capture-Systeme): Kopfzeilen mit DataRate/Units, Markernamen, X/Y/Z-Spalten.
- CSV „breit“ (Kinovea-Export u. a.): eine Zeitspalte und je Marker Spalten <Name>_x/_y(/_z)
  bzw. „<Name> X“; Trennzeichen , ; oder Tab, Dezimalkomma wird erkannt.

Die Rohdaten werden in das Simulationskoordinatensystem überführt (SPEC Kap. 3: x Richtung Wasser,
z nach oben, Ursprung unbelastete Brettspitze, Meter). Dazu dienen ImportSettings: welche Achse
horizontal/vertikal ist, Vorzeichen, Einheit bzw. Maßstab (z. B. m/px) und Ursprung.
"""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field

import numpy as np

from .params import DATA_DIR

UNIT_TO_M = {"m": 1.0, "cm": 0.01, "mm": 0.001}


@dataclass
class RawData:
    t: np.ndarray  # s
    markers: dict[str, np.ndarray]  # Name → (N, 2|3) in Originaleinheit
    units: str = "m"
    rate: float | None = None
    fmt: str = "csv"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9äöüß]", "", s.lower())


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def read_trc(text: str) -> RawData:
    lines = text.splitlines()
    if len(lines) < 6:
        raise ValueError("TRC-Datei zu kurz")
    keys = lines[1].split("\t")
    vals = lines[2].split("\t")
    meta = {k.strip(): v.strip() for k, v in zip(keys, vals)}
    units = meta.get("Units", "m").lower()
    rate = float(meta.get("DataRate", meta.get("CameraRate", "0")) or 0) or None
    names_row = lines[3].split("\t")
    names = [n.strip() for n in names_row[2:] if n.strip()]
    data = []
    for ln in lines[5:]:
        if not ln.strip():
            continue
        parts = ln.split("\t")
        row = [float(p) if p.strip() not in ("", "NaN", "nan") else np.nan for p in parts]
        data.append(row)
    width = 2 + 3 * len(names)
    arr = np.array([r[:width] + [np.nan] * (width - len(r[:width])) for r in data])
    t = arr[:, 1]
    markers = {n: arr[:, 2 + 3 * i: 5 + 3 * i] for i, n in enumerate(names)}
    return RawData(t=t, markers=markers, units=units, rate=rate, fmt="trc")


_COORD = re.compile(r"^(?P<name>.+?)[\s_.:\-]*(?P<ax>[xyz])\s*(\((?P<unit>[^)]*)\))?$", re.I)


def read_csv(text: str) -> RawData:
    sample = text[:4000]
    delim = "\t" if sample.count("\t") > sample.count(";") and sample.count("\t") > sample.count(",") else (";" if sample.count(";") >= sample.count(",") else ",")
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)]
    # Kopfzeile = erste Zeile mit überwiegend nicht-numerischen Einträgen
    def is_num(s):
        try:
            float(s.replace(",", ".") if delim != "," else s)
            return True
        except ValueError:
            return False
    hi = next(i for i, r in enumerate(rows) if sum(not is_num(c) for c in r if c.strip()) >= max(2, len(r) // 2))
    head = [h.strip() for h in rows[hi]]
    body = [r for r in rows[hi + 1:] if r and is_num(r[0])]
    conv = (lambda s: float(s.replace(",", "."))) if delim != "," else float
    arr = np.array([[conv(c) if c.strip() else np.nan for c in r[:len(head)]] + [np.nan] * (len(head) - len(r)) for r in body])
    tcol = next((i for i, h in enumerate(head) if re.match(r"^(t|time|zeit)\b", h.strip(), re.I)), 0)
    th = head[tcol].lower()
    t = arr[:, tcol] * (0.001 if "ms" in th else 1.0)
    groups: dict[str, dict[str, int]] = {}
    unit = None
    for i, h in enumerate(head):
        if i == tcol:
            continue
        m = _COORD.match(h)
        if not m:
            continue
        groups.setdefault(m.group("name").strip(), {})[m.group("ax").lower()] = i
        if m.group("unit"):
            unit = m.group("unit").strip().lower()
    markers = {}
    for name, ax in groups.items():
        cols = [ax[a] for a in ("x", "y", "z") if a in ax]
        if len(cols) >= 2:
            markers[name] = arr[:, cols]
    if not markers:
        raise ValueError("Keine Markerspalten erkannt (erwartet z. B. 'knee_x', 'knee_y' oder 'Knie X')")
    return RawData(t=t, markers=markers, units=unit if unit in UNIT_TO_M or unit == "px" else "m", fmt="csv")


def read_any(text: str, filename: str = "") -> RawData:
    if filename.lower().endswith(".trc") or text.lstrip().startswith("PathFileType"):
        return read_trc(text)
    return read_csv(text)


# ---------------------------------------------------------------------------
# Zuordnung und Transformation
# ---------------------------------------------------------------------------

def load_marker_maps() -> dict:
    with open(DATA_DIR / "marker_maps.json", encoding="utf-8") as fh:
        return json.load(fh)


def guess_mapping(names: list[str]) -> dict[str, str | None]:
    mm = load_marker_maps()
    normed = {_norm(n): n for n in names}
    out: dict[str, str | None] = {}
    for point, cands in mm["candidates"].items():
        hit = None
        for c in cands:
            if _norm(c) in normed:
                hit = normed[_norm(c)]
                break
        if hit is None:  # Teilstring (z. B. „R Knee (cm)“)
            for c in cands:
                for nn, orig in normed.items():
                    if _norm(c) and _norm(c) in nn and not (point == "hip" and "ship" in nn):
                        hit = orig
                        break
                if hit:
                    break
        out[point] = hit
    return out


@dataclass
class ImportSettings:
    horizontal: str = "x"  # Spalte der Datei, die zur Simulations-x-Achse wird
    vertical: str = "y"
    flip_horizontal: bool = False  # True, wenn die Datei-Achse vom Wasser weg zeigt
    flip_vertical: bool = False  # True bei Bildkoordinaten (y nach unten)
    unit: str = "auto"  # auto | m | cm | mm | px
    scale_m_per_px: float = 1.0  # nur bei unit = px
    origin: str = "board_tip"  # board_tip (erstes Frame) | manual
    origin_x: float = 0.0  # in Dateieinheit, bei origin = manual
    origin_z: float = 0.0
    t_td: float | None = None  # s (Dateizeit) – Touchdown
    t_to: float | None = None  # s (Dateizeit) – Takeoff
    board_slope_per_m: float = 0.0  # rad/m: Brettneigung φ_b = κ z_b (aus dem Brettmodell) für die Kontakterkennung
    mapping: dict[str, str | None] = field(default_factory=dict)


@dataclass
class Measurement:
    """Messung im Simulationssystem: Zeit s (0 = TD), Punkte in m."""

    t: np.ndarray
    points: dict[str, np.ndarray]  # Modellpunkt → (N, 2) [x, z]
    t_td: float
    t_to: float
    rate: float
    board: np.ndarray | None  # (N, 2) Brettspitze, falls getrackt
    mapping: dict[str, str | None]
    warnings: list[str]


def to_measurement(raw: RawData, s: ImportSettings) -> Measurement:
    warnings: list[str] = []
    mapping = {**guess_mapping(list(raw.markers)), **{k: v for k, v in s.mapping.items() if v is not None or k in s.mapping}}
    mm = load_marker_maps()
    missing = [p for p in mm["required"] if not mapping.get(p)]
    if missing:
        raise ValueError(f"Pflichtpunkte ohne Marker: {', '.join(missing)}")
    axis = {"x": 0, "y": 1, "z": 2}
    unit = raw.units if s.unit == "auto" else s.unit
    k = s.scale_m_per_px if unit == "px" else UNIT_TO_M.get(unit, 1.0)
    sx = -1.0 if s.flip_horizontal else 1.0
    sz = -1.0 if s.flip_vertical else 1.0

    def conv(a: np.ndarray) -> np.ndarray:
        return np.stack([sx * a[:, axis[s.horizontal]] * k, sz * a[:, axis[s.vertical]] * k], 1)

    pts = {p: conv(raw.markers[n]) for p, n in mapping.items() if n and n in raw.markers}
    board = pts.pop("board_tip", None)
    if s.origin == "board_tip" and board is not None:
        i0 = int(np.argmax(np.isfinite(board[:, 0])))
        o = board[i0].copy()
    else:
        if s.origin == "board_tip":
            warnings.append("Kein Brettspitzen-Marker – Ursprung manuell (origin_x/origin_z) verwendet.")
        o = np.array([sx * s.origin_x * k, sz * s.origin_z * k])
    pts = {p: v - o for p, v in pts.items()}
    if board is not None:
        board = board - o
    # Lücken linear füllen
    for p, v in list(pts.items()) + ([("board_tip", board)] if board is not None else []):
        for j in range(2):
            col = v[:, j]
            bad = ~np.isfinite(col)
            if bad.any() and (~bad).sum() >= 2:
                col[bad] = np.interp(np.flatnonzero(bad), np.flatnonzero(~bad), col[~bad])
                warnings.append(f"Lücken in {p} interpoliert ({int(bad.sum())} Werte)")
    dt = np.diff(raw.t)
    rate = raw.rate or float(1.0 / np.median(dt))
    if np.std(dt) > 0.05 * np.median(dt):
        warnings.append("Zeitstempel ungleichmäßig – wird als gleichabständig behandelt.")
    t_td = s.t_td if s.t_td is not None else detect_td(raw.t, pts, board, s.board_slope_per_m)
    t_to = s.t_to if s.t_to is not None else detect_to(raw.t, pts, board, t_td, s.board_slope_per_m)
    return Measurement(t=raw.t - t_td, points=pts, t_td=0.0, t_to=t_to - t_td, rate=rate, board=board,
                       mapping=mapping, warnings=warnings)


def _smooth(t: np.ndarray, x: np.ndarray, fc: float = 10.0) -> np.ndarray:
    from .filtering import butter_lowpass

    fs = 1.0 / float(np.median(np.diff(t)))
    return butter_lowpass(x, fs, fc) if len(x) > 12 else x


def _crossing(t: np.ndarray, g: np.ndarray, start: int, downward: bool) -> float | None:
    """Erster Nulldurchgang von g ab Index start (linear interpoliert)."""
    for i in range(max(start, 1), len(g)):
        if (downward and g[i - 1] > 0 >= g[i]) or (not downward and g[i - 1] <= 0 < g[i]):
            return float(t[i - 1] + (t[i] - t[i - 1]) * g[i - 1] / (g[i - 1] - g[i]))
    return None


# Abstand Zehenmarker–Brettoberfläche beim Kontakt (Markerradius/Schuh): Schätzung, überschreibbar
CONTACT_GAP = 0.0


def _gap(t, pts, board, kappa, fc: float | None = None):
    """Abstand Zehe – Brettoberfläche senkrecht unter der Zehe [m] (geneigte Brettspitze).
    fc=None: ungeglättet (TD: schnelle Annäherung, Glättung würde den Knick verschleifen)."""
    sm = (lambda x: x) if fc is None else (lambda x: _smooth(t, x, fc))
    toe = np.stack([sm(pts["toe"][:, 0]), sm(pts["toe"][:, 1])], 1)
    b = np.stack([sm(board[:, 0]), sm(board[:, 1])], 1)
    phi = kappa * b[:, 1]
    surf = b[:, 1] + (toe[:, 0] - b[:, 0]) * np.tan(phi)
    return toe[:, 1] - surf - CONTACT_GAP


def _extrapolate_zero(t: np.ndarray, g: np.ndarray, idx: np.ndarray) -> float | None:
    """Nulldurchgang eines quadratischen Fits über die Frames idx (außerhalb der Rauschzone)."""
    if len(idx) < 4:
        return None
    c = np.polyfit(t[idx], g[idx], 2)
    roots = [r.real for r in np.roots(c) if abs(r.imag) < 1e-12]
    if not roots:
        return None
    ref = t[idx].mean()
    return float(min(roots, key=lambda r: abs(r - ref)))


GAP_LO, GAP_HI, GAP_TRIGGER = 0.006, 0.15, 0.02  # m – Fitbereich und Auslöseschwelle (über Markerrauschen)


def detect_td(t: np.ndarray, pts: dict[str, np.ndarray], board: np.ndarray | None, kappa: float = 0.0) -> float:
    """Touchdown: Zehe erreicht die (geneigte) Brettoberfläche. Die Annäherung wird im Bereich
    0,6–15 cm Abstand quadratisch gefittet und auf Abstand 0 extrapoliert (robust gegen
    Markerrauschen). Ohne Brettmarker: Maximum der Vertikalbeschleunigung der Zehe."""
    if board is not None:
        g = _gap(t, pts, board, kappa)
        below = np.where(g < GAP_TRIGGER)[0]
        if len(below):
            i1 = below[0]
            i0 = i1
            while i0 > 0 and g[i0 - 1] < GAP_HI:
                i0 -= 1
            idx = np.arange(i0, i1 + 1)
            idx = idx[g[idx] > GAP_LO]
            tc = _extrapolate_zero(t, g, idx)
            if tc is not None and t[max(i0 - 1, 0)] <= tc <= t[min(i1 + 2, len(t) - 1)]:
                return tc
            return float(t[i1])
    z = _smooth(t, pts["toe"][:, 1])
    a = np.gradient(np.gradient(z, t), t)
    return float(t[int(np.argmax(a))])


def detect_to(t: np.ndarray, pts: dict[str, np.ndarray], board: np.ndarray | None, t_td: float, kappa: float = 0.0) -> float:
    """Takeoff: erste Ablösung über 2 cm (nach TD + 150 ms), Rückwärts-Extrapolation des
    quadratischen Fits auf Abstand 0."""
    start = int(np.searchsorted(t, t_td + 0.15))
    if board is not None:
        g = _gap(t, pts, board, kappa)
        above = np.where((np.arange(len(g)) >= start) & (g > GAP_TRIGGER))[0]
        if len(above):
            i0 = above[0]
            i1 = i0
            while i1 < len(g) - 1 and g[i1 + 1] < GAP_HI:
                i1 += 1
            idx = np.arange(i0 - 2, i1 + 1)
            idx = idx[(idx >= 0) & (g[idx] > GAP_LO)]
            tc = _extrapolate_zero(t, g, idx)
            if tc is not None and t[max(i0 - 4, 0)] <= tc <= t[i0]:
                return tc
            return float(t[i0 - 1])
    z = _smooth(t, pts["toe"][:, 1])
    a = np.gradient(np.gradient(z, t), t)
    cand = np.arange(start, len(t))
    return float(t[cand[int(np.argmin(a[cand]))]]) if len(cand) else float(t[-1])
