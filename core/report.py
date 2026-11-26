"""Kennwert-Tabelle mit Statusableitung (SPEC Kap. 7, CLAUDE.md: Schätzwerte nie
stillschweigend als Fakten ausgeben).

Der Status einer Ausgabegröße ist der „schwächste“ Status ihrer Eingangsparameter:
Schätzung > Literatur > Gemessen > Eingabe. Abhängigkeiten stehen in data/metrics.json.
Dieselbe Logik ist in web/src/lib/status.ts portiert.
"""
from __future__ import annotations

import json
import math
from typing import Any

from .params import DATA_DIR, ParamSet

RANK = {"Eingabe": 0, "Gemessen": 1, "Literatur": 2, "Schätzung": 3}


def load_metric_info() -> dict[str, Any]:
    with open(DATA_DIR / "metrics.json", encoding="utf-8") as fh:
        return json.load(fh)


def resolve_deps(group: str, p: ParamSet, macros: dict[str, list[str]]) -> list[str]:
    """Expandiert eine Abhängigkeitsgruppe zu konkreten Parameterschlüsseln."""
    if group == "numerics":
        return []
    if group == "start":
        if p["technique.start_mode"] == "hurdle":
            return ["technique.hurdle_height", "technique.board_z_hurdle", "technique.board_v_hurdle"]
        return ["technique.v_z_td", "technique.board_z_td", "technique.board_v_td"]
    out: list[str] = []
    for item in macros[group]:
        if item.startswith("@"):
            out += resolve_deps(item[1:], p, macros)
        elif item.endswith(".*"):
            prefix = item[:-1]
            out += [k for k in p.params if k.startswith(prefix)]
        elif item.endswith("?"):
            key = item[:-1]
            if key == "board.mb_exponent" and p["board.fulcrum"] != 7.5:
                out.append(key)
            elif key in ("board.span_75", "board.overhang_75") and p["board.fulcrum_model"] == "B":
                out.append(key)
        else:
            out.append(item)
    return list(dict.fromkeys(out))


def metric_status(group: str, p: ParamSet, macros: dict[str, list[str]]) -> tuple[str, list[str]]:
    """(Status, Liste der Schätzparameter) einer Ausgabegröße."""
    deps = resolve_deps(group, p, macros)
    if not deps:
        return "Berechnet", []
    worst = max(deps, key=lambda k: RANK[p.status(k)])
    est = [k for k in deps if p.status(k) == "Schätzung"]
    return p.status(worst), est


def deps_for_level(group: str, level: int) -> str:
    """Level 2 nutzt eigene Abhängigkeitsgruppen (Gelenkmodell statt Bein-Aktuator)."""
    if level >= 2 and group in ("sim", "sim_flight"):
        return group.replace("sim", "sim2")
    return group


def metric_rows(metrics: dict[str, Any], p: ParamSet, level: int = 1) -> list[dict[str, Any]]:
    info = load_metric_info()
    macros = info["_meta"]["deps"]
    rows = []
    for m in info["metrics"]:
        val = metrics.get(m["key"])
        if m.get("level_min", 1) > level or val is None or (isinstance(val, float) and math.isnan(val) and m.get("level_min", 1) > 1):
            rows.append({**m, "value": None, "text": f"– (ab Level {m.get('level_min', 2)})", "status": "n/a", "estimates": []})
            continue
        v = val * m.get("scale", 1)
        if m["key"] in ("z_b_min",):
            v = abs(v)
        text = "–" if (isinstance(v, float) and math.isnan(v)) else f"{v:.{m.get('fmt', 3)}f}"
        status, est = metric_status(deps_for_level(m["deps"], level), p, macros)
        rows.append({**m, "value": v, "text": text, "status": status, "estimates": est})
    return rows


def markdown_table(rows: list[dict[str, Any]]) -> str:
    lines = ["| Kategorie | Größe | Wert | Einheit | Status |", "| --- | --- | --- | --- | --- |"]
    for r in rows:
        flag = "⚠ Schätzung" if r["status"] == "Schätzung" else r["status"]
        lines.append(f"| {r['cat']} | {r['label']} | {r['text']} | {r['unit']} | {flag} |")
    return "\n".join(lines)
