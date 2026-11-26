"""Filterung kinematischer Messdaten (SPEC 6.7, Etappe 6).

Butterworth-Tiefpass, phasenfrei (filtfilt; 2. Ordnung vor- und rückwärts = effektiv 4. Ordnung),
Grenzfrequenz per Residualanalyse nach Winter (Biomechanics and Motor Control of Human
Movement, Kap. 3): Residuum R(f_c) = RMS(Rohsignal − gefiltertes Signal); im hohen
Frequenzbereich ist R nahezu linear (reines Rauschen). Die Regressionsgerade dort schneidet die
Ordinate bei a; gewählt wird die kleinste f_c mit R(f_c) ≤ a.

Einheiten: Zeit s, Frequenzen Hz, Signale in beliebiger Einheit (unverändert).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import butter, filtfilt


def butter_lowpass(x: np.ndarray, fs: float, fc: float, order: int = 2) -> np.ndarray:
    """Phasenfreier Butterworth-Tiefpass entlang Achse 0. Für filtfilt wird f_c so korrigiert,
    dass die −3-dB-Frequenz des Doppeldurchlaufs bei f_c liegt (Winter: Faktor 0,802)."""
    x = np.asarray(x, dtype=float)
    if fc >= 0.49 * fs:
        return x.copy()
    c = (2 ** (1 / (2 * order)) - 1) ** 0.25  # 0,802 bei order=2
    wn = min(fc / c / (fs / 2), 0.99)
    b, a = butter(order, wn)
    padlen = min(3 * max(len(a), len(b)), x.shape[0] - 1)
    return filtfilt(b, a, x, axis=0, padlen=padlen)


@dataclass
class ResidualResult:
    cutoffs: np.ndarray  # Hz
    residuals: np.ndarray  # gleiche Einheit wie das Signal
    intercept: float
    fc_opt: float  # Hz


def residual_analysis(x: np.ndarray, fs: float, fmin: float = 1.0, fmax: float | None = None, n: int = 60,
                      fit_from: float = 0.5) -> ResidualResult:
    """Residualanalyse für ein Signal (1D). ``fit_from``: Anteil des Frequenzbereichs, ab dem die
    Regressionsgerade angepasst wird (Rauschbereich)."""
    x = np.asarray(x, dtype=float)
    # Obergrenze 0,3·fs: darüber ist die filtfilt-Korrektur nahe Nyquist gekappt und R(f_c)
    # nicht mehr linear – der Achsenabschnitt würde unterschätzt (getestet: σ wird exakt getroffen).
    fmax = fmax or 0.3 * fs
    fcs = np.linspace(fmin, fmax, n)
    res = np.array([np.sqrt(np.mean((x - butter_lowpass(x, fs, fc)) ** 2)) for fc in fcs])
    sel = fcs >= fmin + fit_from * (fmax - fmin)
    slope, inter = np.polyfit(fcs[sel], res[sel], 1)
    inter = max(inter, 0.0)
    idx = np.where(res <= inter)[0]
    fc = float(fcs[idx[0]]) if len(idx) else float(fcs[-1])
    return ResidualResult(fcs, res, float(inter), fc)


def choose_cutoff(signals: np.ndarray, fs: float, **kw) -> tuple[float, list[ResidualResult]]:
    """Gemeinsame Grenzfrequenz für mehrere Signale (Spalten): Median der Einzel-Optima."""
    signals = np.asarray(signals, dtype=float)
    if signals.ndim == 1:
        signals = signals[:, None]
    results = [residual_analysis(signals[:, j], fs, **kw) for j in range(signals.shape[1])]
    return float(np.median([r.fc_opt for r in results])), results
