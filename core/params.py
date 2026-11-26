"""Parameter-Verwaltung (SPEC Kap. 8, CLAUDE.md).

Alle physikalischen Parameter liegen in ``data/parameters.json`` mit den Feldern
value, unit, source, status. Dieses Modul lädt sie, wendet Presets/Overrides an und
validiert die Wertebereiche mit Pydantic. Schlüssel sind ``"gruppe.name"``.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

Status = Literal["Literatur", "Schätzung", "Gemessen", "Eingabe"]


class ParamSpec(BaseModel):
    """Ein Parameter mit Metadaten (SPEC Kap. 8)."""

    value: Any
    unit: str
    source: str
    status: Status
    label: str | None = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: list[str] | None = None

    @model_validator(mode="after")
    def _check_range(self) -> "ParamSpec":
        if isinstance(self.value, (int, float)) and not isinstance(self.value, bool):
            if self.min is not None and self.value < self.min - 1e-12:
                raise ValueError(f"{self.label}: {self.value} < min {self.min}")
            if self.max is not None and self.value > self.max + 1e-12:
                raise ValueError(f"{self.label}: {self.value} > max {self.max}")
        if self.options is not None and self.value not in self.options:
            raise ValueError(f"{self.label}: {self.value!r} nicht in {self.options}")
        return self


class ParamSet(BaseModel):
    """Vollständiger, validierter Parametersatz: ``{"gruppe.name": ParamSpec}``."""

    params: dict[str, ParamSpec] = Field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        return self.params[key].value

    def status(self, key: str) -> Status:
        return self.params[key].status

    def values(self) -> dict[str, Any]:
        return {k: p.value for k, p in self.params.items()}

    def with_overrides(self, overrides: dict[str, Any] | None, status: Status | None = None) -> "ParamSet":
        """Neue Instanz mit überschriebenen Werten. Ein Override, der vom Default
        abweicht, erhält Status ``status`` (Default: unverändert)."""
        if not overrides:
            return self
        raw = {k: p.model_dump() for k, p in self.params.items()}
        for key, val in overrides.items():
            if key not in raw:
                raise KeyError(f"Unbekannter Parameter: {key}")
            raw[key]["value"] = val
            if status is not None:
                raw[key]["status"] = status
        return ParamSet(params={k: ParamSpec(**v) for k, v in raw.items()})


def _load_json(name: str) -> dict[str, Any]:
    with open(DATA_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


def load_defaults() -> ParamSet:
    """Lädt ``data/parameters.json`` als flachen, validierten Parametersatz."""
    raw = _load_json("parameters.json")
    flat: dict[str, ParamSpec] = {}
    for group, entries in raw.items():
        if group.startswith("_"):
            continue
        for name, spec in entries.items():
            flat[f"{group}.{name}"] = ParamSpec(**copy.deepcopy(spec))
    return ParamSet(params=flat)


def load_presets() -> dict[str, dict[str, Any]]:
    return _load_json("presets.json")["presets"]


def make_params(preset: str | None = None, overrides: dict[str, Any] | None = None) -> ParamSet:
    """Defaults → Preset → Overrides. Preset-Werte behalten den Default-Status
    (Athletendaten sind Eingaben); explizite Overrides ebenfalls."""
    ps = load_defaults()
    if preset is not None:
        ps = ps.with_overrides(load_presets()[preset]["overrides"])
    return ps.with_overrides(overrides)
