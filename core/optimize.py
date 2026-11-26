"""Optimierung der Aktivierungs-Timings (Modus A, SPEC 6.6) und Parameterstudien (Modus C).

Verfahren: CMA-ES (Hansen) im normierten Raum [0, 1]^n, Grenzen durch Spiegelung,
Auswertung parallel in einem Prozess-Pool.
Zielfunktionen: max. Flughöhe, max. Rotationspotenzial (Level 2) oder gewichtete Kombination;
Mindest-Freigang als Nebenbedingung (Strafterm).
Robustheit (Kong, Yeadon & King 2006): jede Lösung wird zusätzlich mit zufälligen
Onset-Störungen von ±10 ms simuliert; der mittlere Leistungsverlust fließt als Strafterm ein.
"""
from __future__ import annotations

import math
import os
from concurrent.futures import Executor, ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from .params import ParamSet, load_defaults

# ---------------------------------------------------------------------------
# Variablen
# ---------------------------------------------------------------------------

L1_VARS = ["activation.a0", "activation.t_on", "activation.t_rise", "activation.t_off", "activation.t_fall", "activation.a_end"]
L2_DEFAULT_GENS = ["mtp_neg", "ankle_neg", "knee_neg", "hip_neg", "hip_pos", "shoulder_pos"]


def default_variables(level: int, gens: list[str] | None = None) -> list[str]:
    if level == 1:
        return list(L1_VARS)
    out = []
    for g in gens or L2_DEFAULT_GENS:
        out += [f"act2.{g}_a0", f"act2.{g}_on", f"act2.{g}_rise", f"act2.{g}_ap"]
    return out


def onset_keys(variables: list[str]) -> list[str]:
    return [v for v in variables if v.endswith("_on") or v.endswith(".t_on")]


# ---------------------------------------------------------------------------
# Bewertung (läuft im Worker-Prozess)
# ---------------------------------------------------------------------------

METRIC_KEYS = ["h_max_board", "rotation_potential", "x_board_plane", "x_body_board_plane", "v_z_to", "v_x_to",
               "H_y", "t_contact", "F_peak_bw", "v_b_td", "z_b_min", "F_active_peak_bw", "knee_omega_to", "knee_angle_to_deg", "hip_torque_peak", "energy_balance_rel"]


def run_one(level: int, values: dict[str, Any]) -> dict[str, Any]:
    """Eine Simulation; gibt ausgewählte Kennwerte zurück (NaN bei Fehlschlag)."""
    ps = load_defaults().with_overrides(values)
    try:
        if level == 1:
            from .models.level1 import simulate as s1
            r = s1(ps)
        else:
            from .models.level2 import simulate as s2
            r = s2(ps, series=False)
        out = {k: (float(r.metrics[k]) if r.metrics.get(k) is not None else float("nan")) for k in METRIC_KEYS}
        out["ok"] = not any("Takeoff" in w or "Integrator" in w for w in r.warnings)
        return out
    except Exception as exc:  # noqa: BLE001 – Optimierer soll robust weiterlaufen
        return {k: float("nan") for k in METRIC_KEYS} | {"ok": False, "error": str(exc)}


@dataclass
class Objective:
    kind: str = "height"  # height | rotation | combined
    w_height: float = 1.0
    w_rotation: float = 0.0
    min_clearance: float = 0.5  # m, Körper vor der Brettspitze beim Passieren der Brettebene
    h_ref: float = 1.5
    rot_ref: float = 50.0

    def score(self, m: dict[str, Any], level: int) -> float:
        """Zu MAXIMIERENDER Wert (ohne Robustheitsterm)."""
        if not m.get("ok") or not np.isfinite(m.get("h_max_board", np.nan)):
            return -10.0
        h = m["h_max_board"] / self.h_ref
        rot = (m.get("rotation_potential") or 0.0) / self.rot_ref if level == 2 else 0.0
        if self.kind == "height":
            s = h
        elif self.kind == "rotation":
            s = rot + 0.05 * h  # Höhe als schwache Nebenwirkung, damit Sprünge nicht flach werden
        else:
            s = self.w_height * h + self.w_rotation * rot
        clr = m.get("x_body_board_plane") if level == 2 else m.get("x_board_plane")
        if clr is not None and np.isfinite(clr) and clr < self.min_clearance:
            s -= 10.0 * (self.min_clearance - clr) ** 2 + 0.5 * (self.min_clearance - clr)
        return float(s)


# ---------------------------------------------------------------------------
# CMA-ES (kompakt, nach Hansen 2016 „The CMA Evolution Strategy: A Tutorial“)
# ---------------------------------------------------------------------------

class CMAES:
    def __init__(self, x0: np.ndarray, sigma: float, popsize: int | None = None, seed: int = 0):
        n = len(x0)
        self.n = n
        self.rng = np.random.default_rng(seed)
        self.lam = popsize or 4 + int(3 * math.log(n))
        self.mu = self.lam // 2
        w = math.log(self.mu + 0.5) - np.log(np.arange(1, self.mu + 1))
        self.w = w / w.sum()
        self.mueff = 1.0 / (self.w ** 2).sum()
        self.cc = (4 + self.mueff / n) / (n + 4 + 2 * self.mueff / n)
        self.cs = (self.mueff + 2) / (n + self.mueff + 5)
        self.c1 = 2 / ((n + 1.3) ** 2 + self.mueff)
        self.cmu = min(1 - self.c1, 2 * (self.mueff - 2 + 1 / self.mueff) / ((n + 2) ** 2 + self.mueff))
        self.damps = 1 + 2 * max(0, math.sqrt((self.mueff - 1) / (n + 1)) - 1) + self.cs
        self.chiN = math.sqrt(n) * (1 - 1 / (4 * n) + 1 / (21 * n * n))
        self.mean = x0.astype(float).copy()
        self.sigma = sigma
        self.C = np.eye(n)
        self.pc = np.zeros(n)
        self.ps = np.zeros(n)
        self.B = np.eye(n)
        self.D = np.ones(n)
        self.gen = 0

    def ask(self) -> list[np.ndarray]:
        z = self.rng.standard_normal((self.lam, self.n))
        xs = self.mean + self.sigma * (z * self.D) @ self.B.T
        return [mirror01(x) for x in xs]

    def tell(self, xs: list[np.ndarray], fit: list[float]) -> None:
        """fit: zu MINIMIERENDE Werte."""
        idx = np.argsort(fit)
        X = np.array(xs)[idx[: self.mu]]
        old = self.mean
        self.mean = self.w @ X
        y = (self.mean - old) / self.sigma
        Cinvsqrt = self.B @ np.diag(1 / self.D) @ self.B.T
        self.ps = (1 - self.cs) * self.ps + math.sqrt(self.cs * (2 - self.cs) * self.mueff) * Cinvsqrt @ y
        self.gen += 1
        hsig = np.linalg.norm(self.ps) / math.sqrt(1 - (1 - self.cs) ** (2 * self.gen)) / self.chiN < 1.4 + 2 / (self.n + 1)
        self.pc = (1 - self.cc) * self.pc + hsig * math.sqrt(self.cc * (2 - self.cc) * self.mueff) * y
        artmp = (X - old) / self.sigma
        self.C = ((1 - self.c1 - self.cmu) * self.C + self.c1 * (np.outer(self.pc, self.pc) + (1 - hsig) * self.cc * (2 - self.cc) * self.C)
                  + self.cmu * artmp.T @ np.diag(self.w) @ artmp)
        self.sigma *= math.exp((self.cs / self.damps) * (np.linalg.norm(self.ps) / self.chiN - 1))
        self.sigma = min(self.sigma, 0.5)
        self.C = np.triu(self.C) + np.triu(self.C, 1).T
        d2, self.B = np.linalg.eigh(self.C)
        self.D = np.sqrt(np.maximum(d2, 1e-20))


def mirror01(x: np.ndarray) -> np.ndarray:
    x = np.mod(x, 2.0)
    return np.where(x > 1.0, 2.0 - x, x)


# ---------------------------------------------------------------------------
# Hauptroutine
# ---------------------------------------------------------------------------

@dataclass
class OptResult:
    best_values: dict[str, float]
    best_score: float
    best_metrics: dict[str, Any]
    baseline_metrics: dict[str, Any]
    baseline_score: float
    history: list[dict[str, float]] = field(default_factory=list)
    evaluations: int = 0
    variables: list[str] = field(default_factory=list)


def bounds_of(ps: ParamSet, key: str) -> tuple[float, float]:
    sp = ps.params[key]
    v = sp.value
    lo = sp.min if sp.min is not None else v - abs(v) * 0.5 - 0.05
    hi = sp.max if sp.max is not None else v + abs(v) * 0.5 + 0.05
    return float(lo), float(hi)


def optimize(
    ps: ParamSet,
    level: int,
    objective: Objective,
    variables: list[str] | None = None,
    generations: int = 12,
    popsize: int | None = None,
    robust: bool = True,
    n_perturb: int = 2,
    perturb_s: float = 0.010,
    seed: int = 0,
    executor: Executor | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> OptResult:
    variables = variables or default_variables(level)
    base = ps.values()
    lo = np.array([bounds_of(ps, k)[0] for k in variables])
    hi = np.array([bounds_of(ps, k)[1] for k in variables])
    x0 = np.clip((np.array([base[k] for k in variables], dtype=float) - lo) / (hi - lo), 0, 1)
    rng = np.random.default_rng(seed + 1)
    on_idx = [variables.index(k) for k in onset_keys(variables)]
    perturbations = [rng.uniform(-perturb_s, perturb_s, len(on_idx)) for _ in range(n_perturb)] if robust else []

    own = executor is None
    ex = executor or ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2)))

    def to_values(xn: np.ndarray, shift: np.ndarray | None = None) -> dict[str, Any]:
        v = lo + xn * (hi - lo)
        if shift is not None:
            v = v.copy()
            for k, i in enumerate(on_idx):
                v[i] = min(max(v[i] + shift[k], lo[i]), hi[i])
        return {**base, **{k: float(x) for k, x in zip(variables, v)}}

    def evaluate(batch: list[np.ndarray]) -> list[tuple[float, dict[str, Any]]]:
        jobs = []
        for xn in batch:
            jobs.append(ex.submit(run_one, level, to_values(xn)))
            for sh in perturbations:
                jobs.append(ex.submit(run_one, level, to_values(xn, sh)))
        res = [j.result() for j in jobs]
        out = []
        k = 1 + len(perturbations)
        for i in range(len(batch)):
            ms = res[i * k:(i + 1) * k]
            s_nom = objective.score(ms[0], level)
            if perturbations:
                s_pert = [objective.score(m, level) for m in ms[1:]]
                loss = float(np.mean([max(0.0, s_nom - s) for s in s_pert]))
                s = s_nom - loss
            else:
                s = s_nom
            out.append((s, ms[0]))
        return out

    try:
        (s0, m0), = evaluate([x0])
        es = CMAES(x0, sigma=0.15, popsize=popsize, seed=seed)
        best = (s0, x0, m0)
        history = [{"generation": 0, "best": s0, "mean": s0}]
        evals = 1
        if progress:
            progress({"generation": 0, "generations": generations, "best_score": s0, "best_h": m0.get("h_max_board")})
        for gen in range(1, generations + 1):
            if should_stop and should_stop():
                break
            xs = es.ask()
            scored = evaluate(xs)
            evals += len(xs)
            es.tell(xs, [-s for s, _ in scored])
            i = int(np.argmax([s for s, _ in scored]))
            if scored[i][0] > best[0]:
                best = (scored[i][0], xs[i], scored[i][1])
            history.append({"generation": gen, "best": best[0], "mean": float(np.mean([s for s, _ in scored])), "sigma": es.sigma})
            if progress:
                progress({"generation": gen, "generations": generations, "best_score": best[0],
                          "best_h": best[2].get("h_max_board"), "best_rot": best[2].get("rotation_potential")})
    finally:
        if own:
            ex.shutdown()
    bv = to_values(best[1])
    return OptResult(
        best_values={k: bv[k] for k in variables}, best_score=best[0], best_metrics=best[2],
        baseline_metrics=m0, baseline_score=s0, history=history, evaluations=evals, variables=variables,
    )


# ---------------------------------------------------------------------------
# Parameterstudien im Backend (Level 2)
# ---------------------------------------------------------------------------

def sweep(ps: ParamSet, level: int, key_x: str, xs: list[float], key_y: str | None = None, ys: list[float] | None = None,
          executor: Executor | None = None, progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    base = ps.values()
    own = executor is None
    ex = executor or ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2)))
    try:
        grid = [(x, y) for y in (ys or [None]) for x in xs]
        futs = [ex.submit(run_one, level, {**base, key_x: x, **({key_y: y} if key_y else {})}) for x, y in grid]
        res = []
        for i, f in enumerate(futs):
            res.append(f.result())
            if progress:
                progress({"done": i + 1, "total": len(futs)})
    finally:
        if own:
            ex.shutdown()
    return {"key_x": key_x, "xs": xs, "key_y": key_y, "ys": ys, "results": res}
