"""Matching Simulation ↔ Messung (Modus B, SPEC 6.7, Methode nach Kong, Yeadon & King).

Die Level-2-Vorwärtssimulation startet im gemessenen Touchdown-Zustand (Gelenkwinkel,
Winkelgeschwindigkeiten, KSP-Geschwindigkeit, Brettzustand). Ein CMA-ES variiert
subjektspezifische Parameter (T_max der Strecker, Aktivierungs-Timings), bis der Score minimal ist:

    Score = gewichtetes RMS der prozentualen Abweichungen in
            Gelenkwinkeln (1° ≙ 1 %), Rumpforientierung (1° ≙ 1 %), linearem Impuls bei TO,
            Drehimpuls bei TO und Kontaktdauer.

Ergebnis: subjektspezifische Kraft- und Timingparameter (Status „Gemessen“ im Sinne von
„aus Messung geschätzt“), mit denen Modus A realistischere Prognosen liefert (SPEC 9.4).
"""
from __future__ import annotations

import math
import os
from concurrent.futures import Executor, ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from .inverse import InverseResult
from .models import level2_generated as G
from .models.level2 import IDX_VB, IDX_ZB, N_STATE, NQ, Level2Config, board_frame, simulate
from .optimize import CMAES, bounds_of
from .params import ParamSet, load_defaults

MATCH_JOINTS = [1, 2, 3, 4]  # ankle, knee, hip, shoulder (MTP und Ellbogen sind bei Video unsicher/unwichtig)
DEFAULT_GENS = ["ankle_neg", "knee_neg", "hip_neg", "shoulder_pos", "mtp_neg"]
N_NORM = 51


# Anfangsbedingungen innerhalb der Messunsicherheit (Kong, Yeadon & King): Offsets auf den TD-Zustand
INIT_VARS = {
    "init.ankle_dq": (4, -0.05, 0.05), "init.knee_dq": (5, -0.05, 0.05), "init.hip_dq": (6, -0.05, 0.05),
    "init.ankle_du": (16, -1.5, 1.5), "init.knee_du": (17, -1.5, 1.5), "init.hip_du": (18, -1.5, 1.5),
    "init.shoulder_du": (19, -2.0, 2.0),
}


def default_match_variables(with_init: bool = True) -> list[str]:
    v = [f"torque.{g}_tmax" for g in DEFAULT_GENS]
    v += [f"act2.{g}_on" for g in DEFAULT_GENS[:4]]
    v += [f"act2.{g}_rise" for g in DEFAULT_GENS[:3]]
    if with_init:
        v += list(INIT_VARS)
    return v


def split_values(values: dict[str, Any]) -> tuple[dict[str, Any], dict[str, float]]:
    return {k: v for k, v in values.items() if not k.startswith("init.")}, {k: v for k, v in values.items() if k.startswith("init.")}


@dataclass
class Target:
    """Vergleichsgrößen aus der Messung (alles SI, Winkel rad)."""

    theta: np.ndarray  # (N_NORM, 4) Gelenkwinkel über normierte Kontaktzeit
    trunk: np.ndarray  # (N_NORM,) absoluter Rumpfwinkel φ_tr
    t_contact: float
    v_to: np.ndarray  # (2,) KSP-Geschwindigkeit bei TO
    H_to: float
    y_td: list[float]  # Startzustand für die Simulation


def _norm_curve(t: np.ndarray, y: np.ndarray, t0: float, t1: float) -> np.ndarray:
    s = np.linspace(t0, t1, N_NORM)
    return np.stack([np.interp(s, t, y[:, j]) for j in range(y.shape[1])], 1) if y.ndim == 2 else np.interp(s, t, y)


def target_from_inverse(inv: InverseResult, ps: ParamSet, t_to: float, zb_td: float | None = None, vb_td: float | None = None) -> Target:
    """Vergleichsdaten und Startzustand aus der inversen Analyse."""
    c = (inv.t >= 0) & (inv.t <= t_to)
    tc = inv.t[c]
    theta = _norm_curve(tc, inv.q[c][:, [3 + j for j in MATCH_JOINTS]], 0.0, t_to)
    from .athlete import build_anthropometry

    an = build_anthropometry(ps)
    trunk_all = np.array([G.segment_angles(q, an.p)[4] for q in inv.q])
    trunk = _norm_curve(tc, trunk_all[c], 0.0, t_to)
    i_to = int(np.argmin(np.abs(inv.t - t_to)))
    q_td, u_td = pre_td_fit(inv.t, inv.q_raw if inv.q_raw is not None else inv.q)
    if inv.board_raw is not None and (zb_td is None or vb_td is None):
        bz, bv = pre_td_fit(inv.t, inv.board_raw[:, 1:2])
        zb_td = float(bz[0]) if zb_td is None else zb_td
        vb_td = float(bv[0]) if vb_td is None else vb_td
    zb_td = 0.0 if zb_td is None else zb_td
    vb_td = 0.0 if vb_td is None else vb_td
    # Startzustand: gemessene Gelenkwinkel/-geschwindigkeiten; Zehen flach auf dem Brett (δ = 0)
    cfg = Level2Config.from_params(ps)
    bf = board_frame(cfg, zb_td, 0.0)
    q0 = q_td.copy()
    u0 = u_td.copy()
    # Zehenspitze auf die Brettoberfläche projizieren (gemessenes x beibehalten)
    toe_x = float(q_td[0])
    q0[1] = bf.tip[1] + (toe_x - bf.tip[0]) * math.tan(bf.phi)
    # Zehen flach und ruhend auf dem Brett; Rückfuß (und alles darüber) behält die gemessene
    # Orientierung und Drehrate – der MTP-Winkel gleicht aus (φ_rf = φ_toe − α_f − θ_MTP).
    a_f = an.named["alpha_f"]
    phi_rf, dphi_rf = q_td[2] - a_f - q_td[3], u_td[2] - u_td[3]
    q0[2] = math.pi + bf.phi
    q0[3] = q0[2] - a_f - phi_rf
    u0[2] = 0.0
    u0[3] = -dphi_rf
    q0[9:] = 0.0
    u0[9:] = 0.0
    # KSP-Geschwindigkeit wie gemessen: KSP-Position je Frame (mittelt über alle Segmente),
    # dann Fit vor TD – deutlich rauschärmer als über die Kette der Winkelraten
    qr = inv.q_raw if inv.q_raw is not None else inv.q
    cv_meas = ballistic_com_velocity(inv.t, qr, an, ps["numerics.g"])
    cv_model = np.array(G.com(q0, u0, an.p)[2:4])
    u0[0] += cv_meas[0] - cv_model[0]
    u0[1] += cv_meas[1] - cv_model[1]
    y0 = np.zeros(N_STATE)
    y0[:NQ], y0[NQ:2 * NQ], y0[IDX_ZB], y0[IDX_VB] = q0, u0, zb_td, vb_td
    return Target(theta=theta, trunk=trunk, t_contact=float(t_to), v_to=inv.com[i_to, 2:4].copy(), H_to=float(inv.H_y[i_to]), y_td=y0.tolist())


PRE_TD_WINDOW = 0.08  # s – Fit-Fenster für Anfangswerte (glatte Flugphase vor TD)


def pre_td_fit(t: np.ndarray, Y: np.ndarray, window: float = PRE_TD_WINDOW, deg: int = 2):
    """Wert und Ableitung bei t = 0 aus einem Polynom über [−window, 0) (je Spalte).
    Vermeidet, dass der Filter Kontakt-Dynamik in den Anfangszustand verschmiert."""
    sel = (t >= -window) & (t <= 1e-9)
    if sel.sum() < deg + 2:
        sel = np.argsort(np.abs(t))[: deg + 3]
    ts = t[sel]
    val = np.empty(Y.shape[1])
    der = np.empty(Y.shape[1])
    for j in range(Y.shape[1]):
        c = np.polyfit(ts, Y[sel, j], deg)
        val[j] = np.polyval(c, 0.0)
        der[j] = np.polyval(np.polyder(c), 0.0)
    return val, der


FLIGHT_WINDOW = 0.15  # s vor TD für die ballistische KSP-Anpassung


def ballistic_com_velocity(t: np.ndarray, q: np.ndarray, an, g: float, window: float = FLIGHT_WINDOW) -> np.ndarray:
    """KSP-Geschwindigkeit bei TD aus der Flugphase davor: x(t) = a + b t, z(t) = c + d t − ½ g t²
    (Kleinste Quadrate, g bekannt). Viel robuster als freie Polynome am Fensterrand."""
    sel = (t >= -window) & (t <= -1e-9)
    if sel.sum() < 4:
        sel = (t <= 1e-9)
    ts = t[sel]
    cp = np.array([G.com(qk, np.zeros(12), an.p)[:2] for qk in q[sel]])
    A = np.stack([np.ones_like(ts), ts], 1)
    bx = np.linalg.lstsq(A, cp[:, 0], rcond=None)[0]
    bz = np.linalg.lstsq(A, cp[:, 1] + 0.5 * g * ts ** 2, rcond=None)[0]
    return np.array([bx[1], bz[1]])


def components(sim_series: dict[str, Any], sim_metrics: dict[str, Any], tgt: Target, an_p) -> dict[str, float]:
    """Prozentuale Abweichungen je Komponente."""
    t = sim_series["t"]
    t_to = sim_metrics["t_contact"]
    th = _norm_curve(t, sim_series["theta"][:, MATCH_JOINTS], 0.0, t_to)
    trunk = _norm_curve(t, np.array([G.segment_angles(q, an_p)[4] for q in sim_series["q"]]), 0.0, t_to)
    deg = 180 / math.pi
    vz = max(abs(tgt.v_to[1]), 1.0)
    return {
        "Gelenkwinkel": float(np.sqrt(np.mean(((th - tgt.theta) * deg) ** 2))),
        "Rumpforientierung": float(np.sqrt(np.mean(((trunk - tgt.trunk) * deg) ** 2))),
        "Linearimpuls TO": float(np.hypot(sim_metrics["v_x_to"] - tgt.v_to[0], sim_metrics["v_z_to"] - tgt.v_to[1]) / vz * 100),
        "Drehimpuls TO": float(abs(sim_metrics["H_y"] - tgt.H_to) / max(abs(tgt.H_to), 10.0) * 100),
        "Kontaktdauer": float(abs(t_to - tgt.t_contact) / tgt.t_contact * 100),
    }


WEIGHTS = {"Gelenkwinkel": 1.0, "Rumpforientierung": 1.0, "Linearimpuls TO": 1.0, "Drehimpuls TO": 1.0, "Kontaktdauer": 1.0}


def score_of(comp: dict[str, float]) -> float:
    w = np.array([WEIGHTS[k] for k in comp])
    c = np.array(list(comp.values()))
    return float(np.sqrt(np.sum(w * c ** 2) / np.sum(w)))


def run_match_one(values: dict[str, Any], tgt: Target) -> dict[str, Any]:
    """Eine Simulation ab gemessenem TD-Zustand und Bewertung (läuft im Worker-Prozess)."""
    pv, init = split_values(values)
    ps = load_defaults().with_overrides(pv)
    try:
        cfg = Level2Config.from_params(ps)
        y0 = np.array(tgt.y_td)
        for k, dv in init.items():
            y0[INIT_VARS[k][0]] += dv
        r = simulate(ps, cfg=cfg, series=True, y_td_override=y0)
        if r.warnings and any("Takeoff" in w or "Integrator" in w for w in r.warnings):
            return {"score": 1e3, "components": {}, "ok": False}
        ser = {"t": r.series["t"], "theta": r.series["theta"], "q": _q_from_series(r)}
        comp = components(ser, r.metrics, tgt, cfg.anthro.p)
        return {"score": score_of(comp), "components": comp, "ok": True,
                "metrics": {k: r.metrics[k] for k in ("v_z_to", "v_x_to", "H_y", "t_contact", "h_max_board")},
                "theta": _norm_curve(r.series["t"], r.series["theta"], 0.0, r.metrics["t_contact"]).tolist()}
    except Exception as exc:  # noqa: BLE001
        return {"score": 1e3, "components": {}, "ok": False, "error": str(exc)}


def _q_from_series(r) -> np.ndarray:
    """Rekonstruiert q (nur für Rumpfwinkel nötig) aus den Gelenkwinkeln + Zehenwinkel ≈ Brett."""
    th = r.series["theta"]
    pts = r.series["points"]
    n = len(th)
    q = np.zeros((n, 12))
    q[:, 3:9] = th
    q[:, 2] = np.unwrap(np.arctan2(pts[:, 3] - pts[:, 1], pts[:, 2] - pts[:, 0]))
    return q


@dataclass
class MatchResult:
    best_values: dict[str, float]
    score: float
    components: dict[str, float]
    baseline_score: float
    baseline_components: dict[str, float]
    factors: dict[str, float]  # Verhältnis zu Default
    sim_metrics: dict[str, Any]
    sim_theta: list
    target_theta: list
    history: list[dict[str, float]] = field(default_factory=list)
    evaluations: int = 0


def match(inv: InverseResult, ps: ParamSet, t_to: float, variables: list[str] | None = None, generations: int = 8,
          popsize: int = 10, seed: int = 0, executor: Executor | None = None,
          progress: Callable[[dict[str, Any]], None] | None = None, should_stop: Callable[[], bool] | None = None) -> MatchResult:
    variables = variables or default_match_variables()
    tgt = target_from_inverse(inv, ps, t_to)
    base = {**ps.values(), **{k: 0.0 for k in INIT_VARS}}
    lo = np.array([INIT_VARS[k][1] if k in INIT_VARS else bounds_of(ps, k)[0] for k in variables])
    hi = np.array([INIT_VARS[k][2] if k in INIT_VARS else bounds_of(ps, k)[1] for k in variables])
    x0 = np.clip((np.array([base[k] for k in variables], float) - lo) / (hi - lo), 0, 1)
    own = executor is None
    ex = executor or ProcessPoolExecutor(max_workers=max(1, os.cpu_count() or 2))

    def vals(xn):
        return {**base, **{k: float(v) for k, v in zip(variables, lo + xn * (hi - lo))}}

    try:
        r0 = ex.submit(run_match_one, vals(x0), tgt).result()
        best = (r0["score"], x0, r0)
        es = CMAES(x0, 0.12, popsize=popsize, seed=seed)
        history = [{"generation": 0, "best": r0["score"]}]
        evals = 1
        if progress:
            progress({"generation": 0, "generations": generations, "score": r0["score"]})
        for gen in range(1, generations + 1):
            if should_stop and should_stop():
                break
            xs = es.ask()
            rs = [f.result() for f in [ex.submit(run_match_one, vals(x), tgt) for x in xs]]
            evals += len(xs)
            es.tell(xs, [r["score"] for r in rs])
            i = int(np.argmin([r["score"] for r in rs]))
            if rs[i]["score"] < best[0]:
                best = (rs[i]["score"], xs[i], rs[i])
            history.append({"generation": gen, "best": best[0]})
            if progress:
                progress({"generation": gen, "generations": generations, "score": best[0]})
    finally:
        if own:
            ex.shutdown()
    bv = vals(best[1])
    defaults = load_defaults().values()
    return MatchResult(
        best_values={k: bv[k] for k in variables}, score=best[0], components=best[2]["components"],
        baseline_score=r0["score"], baseline_components=r0["components"],
        factors={k: bv[k] / defaults[k] for k in variables if k.endswith("_tmax") and defaults.get(k)},
        sim_metrics=best[2].get("metrics", {}), sim_theta=best[2].get("theta", []),
        target_theta=tgt.theta.tolist(),
        history=history, evaluations=evals,
    )
