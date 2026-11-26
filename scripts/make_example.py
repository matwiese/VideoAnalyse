"""Erzeugt den synthetischen Beispieldatensatz für Modus B (bis echte Videodaten vorliegen).
Aufruf: python -m scripts.make_example"""
from __future__ import annotations

import json
from pathlib import Path

from core.synthetic import make_synthetic

OUT = Path(__file__).resolve().parent.parent / "data" / "examples"


def main() -> None:
    trc, truth = make_synthetic(rate=200, noise_m=0.003, seed=0)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "synthetic_elite_w58_200Hz.trc").write_text(trc)
    slim = {k: v for k, v in truth.items() if k not in ("series", "contact_series")}
    (OUT / "synthetic_elite_w58_truth.json").write_text(json.dumps(slim, indent=1, ensure_ascii=False))
    print("geschrieben:", OUT)


if __name__ == "__main__":
    main()
