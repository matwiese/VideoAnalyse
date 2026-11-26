"""Synthetische Messdaten für Etappe 6 (bis echte Videodaten vorliegen).

Ein Level-2-Sprung mit bekannten („wahren“) Parametern wird mit Videofrequenz abgetastet,
mit Markerrauschen versehen und als TRC (OpenCap-ähnliche Markernamen, mm) geschrieben.
Damit lassen sich Import, Filterung, inverse Dynamik und Matching gegen eine bekannte
Wahrheit prüfen. Status der Daten: synthetisch – keine Messung!
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from .models import level2_generated as G
from .models.level2 import simulate
from .params import ParamSet, make_params

TRUTH_OVERRIDES: dict[str, Any] = {
    # „Athletin“ mit anderem Kraftprofil als die generischen Defaults
    "torque.knee_neg_tmax": 560.0 * 1.15,
    "torque.hip_neg_tmax": 560.0 * 0.85,
    "torque.ankle_neg_tmax": 450.0 * 1.10,
}

OPENCAP_NAMES = {
    "toe": "r_toe_study", "ball": "r_5meta_study", "heel": "r_calc_study", "ankle": "r_ankle_study",
    "knee": "r_knee_study", "hip": "RHip", "shoulder": "r_shoulder_study", "neck": "C7_study",
    "vertex": "Head", "elbow": "r_lelbow_study", "wrist": "r_lwrist_study", "fingertip": "r_finger",
}


def full_timeline(res, an_p, rate: float = 1000.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Zeit (s), Punkte (N, 24) und Brettspitze (N, 2) von der Hürde bis kurz vor dem Wasser.
    Vor TD: TD-Haltung mit linear fortgesetztem Armschwung (konsistente Winkelgeschwindigkeit),
    KSP auf der ballistischen Hürdenbahn."""
    s = res.series
    t_parts, p_parts, b_parts = [], [], []
    c0 = s["com"][0]
    if "hurdle_t" in s:
        ht = s["hurdle_t"]
        p0 = s["points"][0]
        q0 = np.zeros(12)
        q0[0], q0[1] = p0[0], p0[1]
        q0[2] = math.atan2(p0[3] - p0[1], p0[2] - p0[0]) % (2 * math.pi)
        q0[3:9] = s["theta"][0]
        w0 = s["omega"][0]
        P = np.empty((len(ht), 24))
        for k, tk in enumerate(ht):
            q = q0.copy()
            q[3:9] = q0[3:9] + w0 * tk
            pts = np.array(G.points(q, an_p))
            c = G.com(q, np.zeros(12), an_p)
            pts[0::2] += c0[0] + c0[2] * tk - c[0]
            pts[1::2] += s["hurdle_com_z"][k] - c[1]
            P[k] = pts
        t_parts.append(ht)
        p_parts.append(P)
        b_parts.append(s["hurdle_z_b"])
    t_parts.append(s["t"])
    p_parts.append(s["points"])
    b_parts.append(s["z_b"])
    t_parts.append(s["flight_t"])
    p_parts.append(s["flight_points"])
    b_parts.append(s["flight_z_b"])
    t = np.concatenate(t_parts)
    P = np.concatenate(p_parts)
    zb = np.concatenate(b_parts)
    return t, P, zb


def make_synthetic(ps: ParamSet | None = None, rate: float = 200.0, noise_m: float = 0.003, seed: int = 0,
                   t_before: float = 0.15, t_after: float = 0.35):
    """Simuliert und tastet ab. Rückgabe: (trc_text, truth: dict)."""
    ps = ps or make_params("elite_w_58", TRUTH_OVERRIDES)
    from .athlete import build_anthropometry

    res = simulate(ps)
    t, P, zb = full_timeline(res, build_anthropometry(ps).p)
    c = ps["board.horiz_coeff"]
    tg = np.arange(math.ceil(-t_before * rate), math.floor((res.events["TO"] + t_after) * rate) + 1) / rate
    Pg = np.stack([np.interp(tg, t, P[:, j]) for j in range(24)], 1)
    zbg = np.interp(tg, t, zb)
    rng = np.random.default_rng(seed)
    Pg_noisy = Pg + rng.normal(0, noise_m, Pg.shape)
    board = np.stack([-c * zbg ** 2, zbg], 1) + rng.normal(0, noise_m, (len(tg), 2))
    # TRC: X nach vorn (Wasser), Y nach oben, Z lateral; Einheit mm; Datei-Zeit beginnt bei 0
    names = [OPENCAP_NAMES[n] for n in G.POINT_NAMES] + ["board_tip"]
    tt = tg - tg[0]
    lines = [
        "PathFileType\t4\t(X/Y/Z)\tsynthetic_dive.trc",
        "DataRate\tCameraRate\tNumFrames\tNumMarkers\tUnits\tOrigDataRate\tOrigDataStartFrame\tOrigNumFrames",
        f"{rate:g}\t{rate:g}\t{len(tg)}\t{len(names)}\tmm\t{rate:g}\t1\t{len(tg)}",
        "Frame#\tTime\t" + "\t\t\t".join(names) + "\t\t\t",
        "\t\t" + "\t".join(f"X{i + 1}\tY{i + 1}\tZ{i + 1}" for i in range(len(names))),
    ]
    for k in range(len(tg)):
        vals = []
        for j in range(12):
            vals += [Pg_noisy[k, 2 * j] * 1000, Pg_noisy[k, 2 * j + 1] * 1000, 0.0]
        vals += [board[k, 0] * 1000, board[k, 1] * 1000, 0.0]
        lines.append(f"{k + 1}\t{tt[k]:.5f}\t" + "\t".join(f"{v:.3f}" for v in vals))
    truth = {
        "status": "synthetisch – erzeugt mit core/synthetic.py, keine Messung",
        "overrides": TRUTH_OVERRIDES, "preset": "elite_w_58", "rate": rate, "noise_m": noise_m,
        "t_td_file": float(-tg[0]), "t_to_file": float(res.events["TO"] - tg[0]),
        "metrics": {k: (float(v) if isinstance(v, (int, float, np.floating)) and v is not None else None) for k, v in res.metrics.items()},
        "series": {"t": (tg - 0).tolist(), "points_true": Pg.tolist()},
        "contact_series": {"t": res.series["t"].tolist(), "Fz": res.series["Fz"].tolist(), "Fx": res.series["Fx"].tolist(),
                           "tau_net": res.series["tau_net"].tolist(), "theta": res.series["theta"].tolist()},
    }
    return "\n".join(lines) + "\n", truth
