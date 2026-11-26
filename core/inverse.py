"""Inverse Dynamik planar (Modus B, SPEC 6.7 / Etappe 6).

Ablauf: gemessene Punkte (m) → Butterworth (Residualanalyse) → generalisierte Koordinaten q des
Level-2-Modells (Winkel aus Markervektoren) → q̇, q̈ (zentrale Differenzen) →
Q = M(q) q̈ − f(q, q̇, τ=0, F=0) mit denselben, symbolisch erzeugten Gleichungen wie die
Vorwärtssimulation (Schwabbelmassen starr angenommen, da nicht messbar).

Q enthält die Gelenkmomente und die generalisierte Kontaktkraft. Aus den Basiskoordinaten
(x, z, φ_toe) folgen die resultierende Brettkraft (F_x, F_z) und der Druckpunkt (CoP) auf der
Fußsohle (Zehenspitze–Ballen–Ferse); danach τ_j = Q_j − (J_P^T F)_j.
Im Flug sollte F ≈ 0 sein – die Residualkraft dort ist ein Gütemaß der Messung.

Einheiten: SI; Winkel rad; Momente Nm (+ = +θ-Richtung, Flexion/Dorsalflexion).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .athlete import Anthropometry
from .filtering import butter_lowpass, choose_cutoff
from .importers import Measurement
from .models import level2_generated as G

NR = 9  # starre Koordinaten (ohne Schwabbelmassen)


def _ang(v: np.ndarray) -> np.ndarray:
    return np.unwrap(np.arctan2(v[:, 1], v[:, 0]))


def complete_points(pts: dict[str, np.ndarray], an: Anthropometry) -> dict[str, np.ndarray]:
    """Ergänzt optionale Punkte aus Modellgeometrie (Ballen, Hals, Scheitel, Fingerspitze)."""
    p = dict(pts)
    n = an.named
    if "ball" not in p:
        L = n["L_heel"] + n["L_toe"]
        p["ball"] = p["heel"] + (p["toe"] - p["heel"]) * (n["L_heel"] / L)
    e_tr = p["shoulder"] - p["hip"]
    e_tr = e_tr / np.linalg.norm(e_tr, axis=1, keepdims=True)
    if "neck" not in p:
        p["neck"] = p["hip"] + e_tr * n["L_tr"]
    if "vertex" not in p:
        p["vertex"] = p["neck"] + e_tr * n["L_head"]
    if "fingertip" not in p:
        e = p["wrist"] - p["elbow"]
        p["fingertip"] = p["wrist"] + e / np.linalg.norm(e, axis=1, keepdims=True) * n["L_hand"]
    return p


def points_to_q(p: dict[str, np.ndarray], an: Anthropometry) -> np.ndarray:
    """Generalisierte Koordinaten (N, 12) aus Punkten; Schwabbelmassen = 0."""
    a_f = an.named["alpha_f"]
    phi_t = _ang(p["ball"] - p["toe"])
    phi_rf = _ang(p["ankle"] - p["ball"])
    phi_sh = _ang(p["knee"] - p["ankle"])
    phi_th = _ang(p["hip"] - p["knee"])
    phi_tr = _ang(p["shoulder"] - p["hip"])
    phi_ua = _ang(p["elbow"] - p["shoulder"])
    phi_fa = _ang(p["wrist"] - p["elbow"])

    def wrap(a):  # auf (−π, π] um den ersten Wert herum, Verlauf stetig
        return a - 2 * math.pi * np.round((a[0] if np.ndim(a) else a) / (2 * math.pi))

    q = np.zeros((len(phi_t), 12))
    q[:, 0:2] = p["toe"]
    q[:, 2] = phi_t - 2 * math.pi * np.round((phi_t[0] - math.pi) / (2 * math.pi))
    q[:, 3] = wrap(phi_t - a_f - phi_rf)
    q[:, 4] = wrap(phi_rf - (math.pi / 2 - a_f) - phi_sh)
    q[:, 5] = wrap(phi_th - phi_sh)
    q[:, 6] = wrap(phi_th - phi_tr)
    q[:, 7] = wrap(phi_ua - phi_tr + math.pi)
    q[:, 8] = wrap(phi_fa - phi_ua)
    return q


def _perp(v: np.ndarray) -> np.ndarray:
    return np.array([-v[1], v[0]])


def _cross(a: np.ndarray, b: np.ndarray) -> float:
    return float(a[0] * b[1] - a[1] * b[0])


def solve_cop(F: np.ndarray, Q2: float, toe: np.ndarray, ball: np.ndarray, heel: np.ndarray):
    """Druckpunkt P auf der Sohle mit (P − toe) × F = Q2. Rückgabe (P, auf_rückfuß, Residuum)."""
    best = None
    for a, b, rear in ((toe, ball, False), (ball, heel, True)):
        d = b - a
        den = _cross(d, F)
        if abs(den) < 1e-9:
            continue
        lam = (Q2 - _cross(a - toe, F)) / den
        lam_c = min(max(lam, 0.0), 1.0)
        P = a + lam_c * d
        resid = abs(_cross(P - toe, F) - Q2)
        if best is None or resid < best[2]:
            best = (P, rear, resid)
    if best is None:
        return toe.copy(), False, abs(Q2)
    return best


@dataclass
class InverseResult:
    t: np.ndarray
    q: np.ndarray
    u: np.ndarray
    ud: np.ndarray
    F: np.ndarray  # (N, 2) Brett → Springer [N]
    cop: np.ndarray  # (N, 2)
    tau: np.ndarray  # (N, 6) Netto-Gelenkmomente [Nm]
    power: np.ndarray  # (N, 6) [W]
    com: np.ndarray  # (N, 4) x, z, vx, vz
    H_y: np.ndarray  # (N,) [kg m²/s], + = vorwärts
    points: np.ndarray  # (N, 24) gefiltert, Modellreihenfolge
    cutoff: float
    residual: dict[str, Any]
    board: np.ndarray | None
    metrics: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    q_raw: np.ndarray | None = None  # ungefiltert (für lokale Anfangswert-Fits)
    board_raw: np.ndarray | None = None


AUTO_FC_RANGE = (4.0, 12.0)  # Hz – Begrenzung der Residualanalyse (Sprunganalysen typ. 6–10 Hz)
UNCERTAIN_JOINTS = ("mtp", "ankle")  # kurze Fußsegmente → Momente stark rauschempfindlich


def inverse_dynamics(meas: Measurement, an: Anthropometry, cutoff: float | None = None,
                     board_k: float | None = None, board_m: float | None = None) -> InverseResult:
    fs = meas.rate
    pts = complete_points(meas.points, an)
    names = G.POINT_NAMES
    raw_stack = np.concatenate([pts[n] for n in names], 1)
    rr = None
    if cutoff is None:
        fc_res, res = choose_cutoff(np.concatenate([pts[n] for n in ("toe", "ankle", "knee", "hip", "shoulder", "wrist")], 1), fs)
        cutoff = float(min(max(fc_res, AUTO_FC_RANGE[0]), AUTO_FC_RANGE[1]))
        rr = {"cutoffs": res[0].cutoffs.tolist(), "residuals": [r.residuals.tolist() for r in res],
              "fc_each": [r.fc_opt for r in res], "fc_residual": fc_res, "fc_applied": cutoff,
              "note": f"Residualanalyse (Winter) ergab {fc_res:.1f} Hz; angewendet {cutoff:.1f} Hz (Begrenzung {AUTO_FC_RANGE[0]:g}–{AUTO_FC_RANGE[1]:g} Hz, da Aufprall-Transienten die Residualanalyse nach oben verschieben)."}
    filt = butter_lowpass(raw_stack, fs, cutoff)
    fp = {n: filt[:, 2 * i:2 * i + 2] for i, n in enumerate(names)}
    q = points_to_q(fp, an)
    q_raw = points_to_q(complete_points({n: pts[n] for n in names}, an), an)
    board_raw = meas.board
    dt = 1.0 / fs
    u = np.gradient(q, dt, axis=0)
    ud = np.gradient(u, dt, axis=0)
    N = len(q)
    F = np.zeros((N, 2))
    cop = np.zeros((N, 2))
    tau = np.zeros((N, 6))
    com = np.zeros((N, 4))
    H = np.zeros(N)
    model_pts = np.zeros((N, 24))
    zero6 = [0.0] * 6
    zero3 = [0.0] * 3
    for k in range(N):
        qk, uk = q[k], u[k]
        M = np.array(G.mass_matrix(qk, an.p)).reshape(12, 12)[:NR, :NR]
        f0 = np.array(G.forcing(qk, uk, an.p, zero6, zero6, zero3))[:NR]
        Q = M @ ud[k, :NR] - f0
        Fk = np.array([Q[0], Q[1]])
        mp = np.array(G.points(qk, an.p)).reshape(-1, 2)
        model_pts[k] = mp.ravel()
        toe, ball, heel = mp[0], mp[1], mp[2]
        P, rear, _res = solve_cop(Fk, Q[2], toe, ball, heel)
        tk = Q[3:9].copy()
        if rear:
            tk[0] -= float(Fk @ (-_perp(P - ball)))
        F[k], cop[k], tau[k] = Fk, P, tk
        com[k] = G.com(qk, uk, an.p)
        H[k] = -sum(G.segment_momentum(qk, uk, an.p))
    power = tau * u[:, 3:9]
    t = meas.t
    contact = (t >= meas.t_td) & (t <= meas.t_to)
    BW = an.total_mass * an.named["g"]
    warnings = list(meas.warnings) + ["MTP- und Sprunggelenkmomente sind bei Videodaten unsicher (kurze Fußsegmente verstärken Markerrauschen)."]
    flight = ~contact
    resid_flight = float(np.sqrt(np.mean(np.sum(F[flight] ** 2, 1)))) / BW if flight.any() else float("nan")
    if resid_flight > 0.5:
        warnings.append(f"Residualkraft im Flug {resid_flight:.2f} BW – Marker, Maßstab oder Körpermasse prüfen.")
    i_to = int(np.argmin(np.abs(t - meas.t_to)))
    i_td = int(np.argmin(np.abs(t - meas.t_td)))
    Fz_c = F[contact, 1]
    deg = 180 / math.pi
    m = {
        "t_contact": float(meas.t_to - meas.t_td),
        "F_peak_bw": float(Fz_c.max() / BW) if contact.any() else float("nan"),
        "impulse_z": float(np.trapezoid(F[contact, 1], t[contact])) if contact.sum() > 1 else float("nan"),
        "v_z_td": float(com[i_td, 3]), "v_z_to": float(com[i_to, 3]), "v_x_to": float(com[i_to, 2]),
        "z_c_to": float(com[i_to, 1]), "H_y": float(H[i_to]), "residual_flight_bw": resid_flight, "cutoff_hz": float(cutoff),
        "h_max_board": float(com[i_to, 1] + max(com[i_to, 3], 0) ** 2 / (2 * an.named["g"])),
    }
    for j, name in enumerate(G.JOINTS):
        m[f"{name}_angle_td_deg"] = float(q[i_td, 3 + j] * deg)
        m[f"{name}_angle_to_deg"] = float(q[i_to, 3 + j] * deg)
        m[f"{name}_angle_max_deg"] = float(q[contact, 3 + j].max() * deg) if contact.any() else float("nan")
        m[f"{name}_torque_peak"] = float(tau[contact, j][np.argmax(np.abs(tau[contact, j]))]) if contact.any() else float("nan")
        m[f"{name}_omega_to"] = float(u[i_to, 3 + j])
        m[f"{name}_work_pos"] = float(np.trapezoid(np.clip(power[contact, j], 0, None), t[contact])) if contact.sum() > 1 else float("nan")
    board = None
    if meas.board is not None:
        board = butter_lowpass(meas.board, fs, cutoff)
        m["z_b_min"] = float(board[:, 1].min())
        if board_k and board_m:
            zb = board[:, 1]
            zbdd = np.gradient(np.gradient(zb, dt), dt)
            Fb = -(board_k * zb + board_m * zbdd)  # Kraft des Springers auf das Brett, nach unten positiv → Brett auf Springer
            m["F_peak_board_bw"] = float(Fb[contact].max() / BW) if contact.any() else float("nan")
            m["board_force_rms_diff_bw"] = float(np.sqrt(np.mean((Fb[contact] - F[contact, 1]) ** 2)) / BW) if contact.any() else float("nan")
    return InverseResult(t=t, q=q, u=u, ud=ud, F=F, cop=cop, tau=tau, power=power, com=com, H_y=H, points=model_pts,
                         q_raw=q_raw, board_raw=board_raw,
                         cutoff=float(cutoff), residual=rr or {}, board=board, metrics=m, warnings=warnings)
