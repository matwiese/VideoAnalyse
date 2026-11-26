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
    obj = Objective(req.objective, req.w_height, req.w_rotation, req.min_clearance)
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
# Web-App ausliefern (Einzeldatei aus web/, siehe npm run build:standalone)
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def index():
    if STATIC.exists():
        return FileResponse(STATIC)
    raise HTTPException(404, "Web-App nicht gebaut: cd web && npm run build:standalone")
