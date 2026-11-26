"""FastAPI-Schicht (SPEC Kap. 10.1). Start: uvicorn api.main:app --reload

Level 1 läuft zusätzlich im Browser (Web Worker); die API ist die Referenz und
die Grundlage für Level 2/3, Optimierung und Parameterstudien (Etappen 3–7).
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

from core.models.level1 import resample, simulate
from core.params import load_defaults, load_presets, make_params
from core.report import load_metric_info, metric_rows

app = FastAPI(title="3m-Brett-Simulator", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


class SimRequest(BaseModel):
    preset: str | None = None
    overrides: dict[str, Any] = {}
    series: bool = True


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
    try:
        p = make_params(req.preset, req.overrides)
    except (KeyError, ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    res = simulate(p)
    out: dict[str, Any] = {
        "level": 1,
        "events": res.events,
        "metrics": metric_rows(res.metrics, p),
        "warnings": res.warnings,
    }
    if req.series:
        out["series"] = {k: v.tolist() for k, v in resample(res, p).items()}
    return out
