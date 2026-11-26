"""Validierung SPEC 9.2 (Fulkrum-Höhe-Beziehung): Level-2-Timing je Fulkrum optimiert (CMA-ES),
damit die Technik an das Brett angepasst ist (wie bei realen Springer:innen).
Aufruf: python -m scripts.validate_fulcrum [Generationen] [Populationsgröße]"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from core.optimize import Objective, optimize
from core.params import make_params

OUT = Path(__file__).resolve().parent.parent / "docs" / "validation" / "data" / "fulcrum_optimized.json"


def main() -> None:
    gens = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    pop = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    out = {}
    for f in (1.0, 3.0, 5.0, 7.5, 9.0):
        ps = make_params("elite_w_58", {"board.fulcrum": f})
        res = optimize(ps, 2, Objective("height", min_clearance=0.4), generations=gens, popsize=pop, robust=False, seed=11)
        out[str(f)] = {"best": res.best_metrics, "baseline": res.baseline_metrics, "values": res.best_values}
        print(f, round(res.best_metrics["h_max_board"], 3), flush=True)
        OUT.write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
