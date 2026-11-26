"""Kennwert-Tabelle Level 1 (SPEC 11.3): python -m scripts.report_level1 [preset] [Fulkrum]"""
from __future__ import annotations

import sys

from core.models.level1 import simulate
from core.params import load_presets, make_params
from core.report import markdown_table, metric_rows


def main() -> None:
    preset = sys.argv[1] if len(sys.argv) > 1 else "elite_w_58"
    fulcrum = float(sys.argv[2]) if len(sys.argv) > 2 else 7.5
    p = make_params(preset, {"board.fulcrum": fulcrum})
    res = simulate(p)
    print(f"# Level 1 – {load_presets()[preset]['label']}, Fulkrum {fulcrum}\n")
    print(markdown_table(metric_rows(res.metrics, p)))
    if res.warnings:
        print("\nWarnungen: " + "; ".join(res.warnings))


if __name__ == "__main__":
    main()
