"""FastAPI-Schicht (SPEC Kap. 10.1).

Start der Vollversion (Web-App + Backend auf einem Port):  python -m api
Entwicklung:  uvicorn api.main:app --reload  (Web separat mit npm run dev, Proxy /api)

Level 1 läuft zusätzlich im Browser (Web Worker). Level 2, Optimierung und Level-2-Studien
laufen hier; lange Rechnungen als Hintergrund-Jobs mit Fortschrittsabfrage.
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError

from core.models.level1 import resample, simulate
from core.models.level2 import simulate as simulate2
from core.athlete import build_anthropometry
from core.importers import ImportSettings, load_marker_maps, read_any, to_measurement
from core.inverse import UNCERTAIN_JOINTS, inverse_dynamics
from core.matching import default_match_variables, match
from core.models.level2 import Level2Config
from core.optimize import Objective, default_variables, optimize, sweep
from core.params import load_defaults, load_presets, make_params
from core.report import load_metric_info, metric_rows

app = FastAPI(title="3m-Brett-Simulator", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])

STATIC = Path(__file__).resolve().parent / "static" / "index.html"
_pool: ProcessPoolExecutor | None = None
_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def pool() -> ProcessPoolExecutor:
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2)))
    return _pool


def jsonable(x: Any) -> Any:
    if isinstance(x, np.ndarray):
        return np.where(np.isfinite(x), x, None).tolist() if x.dtype.kind == "f" else x.tolist()
    if isinstance(x, (np.floating, float)):
        return float(x) if np.isfinite(x) else None
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, dict):
        return {k: jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    return x


class SimRequest(BaseModel):
    preset: str | None = None
    overrides: dict[str, Any] = {}
    series: bool = True


class OptRequest(BaseModel):
    level: int = Field(2, ge=1, le=2)
    overrides: dict[str, Any] = {}
    objective: str = "height"
    w_height: float = 1.0
    w_rotation: float = 0.0
    min_clearance: float = 0.5
    min_H: float | None = None
    generations: int = Field(8, ge=1, le=60)
    popsize: int = Field(8, ge=4, le=40)
    robust: bool = True
    variables: list[str] | None = None


class SweepRequest(BaseModel):
    level: int = Field(2, ge=1, le=2)
    overrides: dict[str, Any] = {}
    key_x: str
    xs: list[float]
    key_y: str | None = None
    ys: list[float] | None = None


def params_or_422(preset: str | None, overrides: dict[str, Any]):
    try:
        return make_params(preset, overrides)
    except (KeyError, ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "levels": [1, 2], "cpus": os.cpu_count(), "version": app.version}


@app.get("/api/params")
def params() -> dict[str, Any]:
    return {k: v.model_dump() for k, v in load_defaults().params.items()}


@app.get("/api/presets")
def presets() -> dict[str, Any]:
    return load_presets()


@app.get("/api/metrics-info")
def metrics_info() -> dict[str, Any]:
    return load_metric_info()


@app.post("/api/simulate/level1")
def simulate_level1(req: SimRequest) -> dict[str, Any]:
    p = params_or_422(req.preset, req.overrides)
    res = simulate(p)
    out: dict[str, Any] = {"level": 1, "events": res.events, "metrics": metric_rows(res.metrics, p, 1), "warnings": res.warnings}
    if req.series:
        out["series"] = {k: v.tolist() for k, v in resample(res, p).items()}
    return jsonable(out)


@app.post("/api/simulate/level2")
def simulate_level2(req: SimRequest) -> dict[str, Any]:
    p = params_or_422(req.preset, req.overrides)
    t0 = time.time()
    try:
        res = simulate2(p, series=req.series)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Simulation fehlgeschlagen: {exc}") from exc
    return jsonable({
        "level": 2, "events": res.events, "metrics_raw": res.metrics, "metrics": metric_rows(res.metrics, p, 2),
        "warnings": res.warnings, "series": res.series, "seconds": time.time() - t0,
    })


# ---------------------------------------------------------------------------
# Hintergrund-Jobs
# ---------------------------------------------------------------------------

def _start_job(kind: str, fn) -> str:
    jid = uuid.uuid4().hex[:12]
    job = {"id": jid, "kind": kind, "status": "läuft", "progress": {}, "result": None, "error": None, "stop": False, "started": time.time()}
    with _lock:
        _jobs[jid] = job

    def runner():
        try:
            job["result"] = fn(job)
            job["status"] = "abgebrochen" if job["stop"] else "fertig"
        except Exception as exc:  # noqa: BLE001
            job["status"] = "fehler"
            job["error"] = str(exc)
        job["finished"] = time.time()

    threading.Thread(target=runner, daemon=True).start()
    return jid


@app.post("/api/optimize")
def start_optimize(req: OptRequest) -> dict[str, Any]:
    p = params_or_422(None, req.overrides)
    obj = Objective(req.objective, req.w_height, req.w_rotation, req.min_clearance, req.min_H)
    variables = req.variables or default_variables(req.level)
    for v in variables:
        if v not in p.params:
            raise HTTPException(422, f"Unbekannte Variable {v}")

    def fn(job):
        res = optimize(p, req.level, obj, variables, generations=req.generations, popsize=req.popsize, robust=req.robust,
                       executor=pool(), progress=lambda d: job.__setitem__("progress", d), should_stop=lambda: job["stop"])
        return jsonable({"best_values": res.best_values, "best_score": res.best_score, "best_metrics": res.best_metrics,
                         "baseline_metrics": res.baseline_metrics, "baseline_score": res.baseline_score,
                         "history": res.history, "evaluations": res.evaluations, "variables": res.variables})

    return {"job": _start_job("optimize", fn), "variables": variables}


@app.post("/api/sweep")
def start_sweep(req: SweepRequest) -> dict[str, Any]:
    p = params_or_422(None, req.overrides)
    for k in [req.key_x] + ([req.key_y] if req.key_y else []):
        if k not in p.params:
            raise HTTPException(422, f"Unbekannter Parameter {k}")
    if len(req.xs) * len(req.ys or [1]) > 900:
        raise HTTPException(422, "Zu viele Stützstellen (max. 900)")

    def fn(job):
        return jsonable(sweep(p, req.level, req.key_x, req.xs, req.key_y, req.ys, executor=pool(),
                              progress=lambda d: job.__setitem__("progress", d)))

    return {"job": _start_job("sweep", fn)}


@app.get("/api/jobs/{jid}")
def job_status(jid: str) -> dict[str, Any]:
    job = _jobs.get(jid)
    if not job:
        raise HTTPException(404, "Job unbekannt")
    return {k: v for k, v in job.items() if k != "stop"}


@app.delete("/api/jobs/{jid}")
def job_stop(jid: str) -> dict[str, Any]:
    job = _jobs.get(jid)
    if not job:
        raise HTTPException(404, "Job unbekannt")
    job["stop"] = True
    return {"ok": True}


# ---------------------------------------------------------------------------
# Modus B: Import, inverse Dynamik, Matching (SPEC 6.7, Etappe 6)
# ---------------------------------------------------------------------------

_analyses: dict[str, dict[str, Any]] = {}
EXAMPLE = Path(__file__).resolve().parent.parent / "data" / "examples" / "synthetic_elite_w58_200Hz.trc"


class AnalyzeRequest(BaseModel):
    text: str
    filename: str = ""
    overrides: dict[str, Any] = {}
    settings: dict[str, Any] = {}
    cutoff: float | None = None


class MatchRequest(BaseModel):
    analysis_id: str
    overrides: dict[str, Any] = {}
    generations: int = Field(10, ge=1, le=60)
    popsize: int = Field(10, ge=4, le=40)
    with_init: bool = True


@app.get("/api/example/trc")
def example_trc() -> dict[str, Any]:
    if not EXAMPLE.exists():
        raise HTTPException(404, "Beispieldatensatz fehlt: python -m scripts.make_example")
    return {"filename": EXAMPLE.name, "text": EXAMPLE.read_text(),
            "note": "Synthetische Daten (Level-2-Simulation mit bekannten Parametern, 3 mm Rauschen, 200 Hz) – keine Messung."}


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest) -> dict[str, Any]:
    p = params_or_422(None, req.overrides)
    try:
        raw = read_any(req.text, req.filename)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"Datei nicht lesbar: {exc}") from exc
    settings = {**req.settings}
    settings.setdefault("board_slope_per_m", Level2Config.from_params(p).kappa)
    try:
        st = ImportSettings(**settings)
        meas = to_measurement(raw, st)
        inv = inverse_dynamics(meas, build_anthropometry(p), cutoff=req.cutoff,
                               board_k=Level2Config.from_params(p).board.k_s, board_m=Level2Config.from_params(p).board.m_b)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    aid = uuid.uuid4().hex[:12]
    _analyses[aid] = {"inv": inv, "meas": meas, "overrides": req.overrides}
    if len(_analyses) > 20:
        _analyses.pop(next(iter(_analyses)))
    deg = 180 / np.pi
    return jsonable({
        "id": aid, "markers": list(raw.markers), "mapping": meas.mapping, "required": load_marker_maps()["required"],
        "rate": meas.rate, "t_to": meas.t_to, "t_td_file": float(-meas.t[0]) if len(meas.t) else 0.0,
        "residual": inv.residual, "cutoff": inv.cutoff, "metrics": inv.metrics, "warnings": inv.warnings,
        "uncertain_joints": list(UNCERTAIN_JOINTS), "status": "Gemessen (aus Video/Datei, inverse Dynamik)",
        "series": {
            "t": inv.t, "points": inv.points, "F": inv.F, "cop": inv.cop, "tau": inv.tau, "power": inv.power,
            "theta_deg": inv.q[:, 3:9] * deg, "omega": inv.u[:, 3:9], "com": inv.com, "H_y": inv.H_y,
            "board": inv.board if inv.board is not None else None,
        },
    })


@app.post("/api/match")
def start_match(req: MatchRequest) -> dict[str, Any]:
    a = _analyses.get(req.analysis_id)
    if not a:
        raise HTTPException(404, "Analyse unbekannt – bitte erneut analysieren")
    p = params_or_422(None, {**a["overrides"], **req.overrides})
    variables = default_match_variables(req.with_init)

    def fn(job):
        res = match(a["inv"], p, a["meas"].t_to, variables, generations=req.generations, popsize=req.popsize,
                    executor=pool(), progress=lambda d: job.__setitem__("progress", d), should_stop=lambda: job["stop"])
        return jsonable({"best_values": res.best_values, "score": res.score, "components": res.components,
                         "baseline_score": res.baseline_score, "baseline_components": res.baseline_components,
                         "factors": res.factors, "sim_metrics": res.sim_metrics, "sim_theta": res.sim_theta,
                         "target_theta": res.target_theta, "history": res.history, "evaluations": res.evaluations})

    return {"job": _start_job("match", fn), "variables": variables}


@app.get("/api/marker-maps")
def marker_maps() -> dict[str, Any]:
    return load_marker_maps()


# ---------------------------------------------------------------------------
# Web-App ausliefern (Einzeldatei aus web/, siehe npm run build:standalone)
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def index():
    if STATIC.exists():
        return FileResponse(STATIC)
    raise HTTPException(404, "Web-App nicht gebaut: cd web && npm run build:standalone")
