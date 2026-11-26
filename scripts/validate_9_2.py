"""Validierung SPEC 9.2 (qualitativ): Level-2-Optimierung auf Höhe vs. Rotation.

Erwartetes Muster (Cheng & Hubbard 2005, ISBS): Rotationssprünge haben geringere
Kniewinkelgeschwindigkeit und gebeugte Knie bei TO sowie mehr Hüftbeugemoment.
Aufruf: python -m scripts.validate_9_2 [Generationen] [Populationsgröße]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from core.models.level2 import simulate
from core.optimize import Objective, optimize
from core.params import make_params

OUT = Path(__file__).resolve().parent.parent / "docs" / "validation" / "data"


def main() -> None:
    gens = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    pop = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    ps = make_params("elite_w_58", {"numerics.rtol2": 1e-6})
    results = {}
    for kind in ("height", "rotation"):
        t0 = time.time()
        obj = Objective(kind, min_clearance=0.4)
        res = optimize(ps, 2, obj, generations=gens, popsize=pop, robust=True, n_perturb=1, seed=7,
                       progress=lambda d: print(kind, d, flush=True))
        full = simulate(ps.with_overrides(res.best_values), series=False).metrics
        results[kind] = {"values": res.best_values, "score": res.best_score, "baseline_score": res.baseline_score,
                         "history": res.history, "metrics": {k: v for k, v in full.items() if isinstance(v, (int, float))},
                         "seconds": time.time() - t0, "evaluations": res.evaluations}
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "opt_9_2.json").write_text(json.dumps(results, indent=1))
    print("fertig")


if __name__ == "__main__":
    main()
