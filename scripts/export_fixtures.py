"""Erzeugt Referenzwerte für den Vitest-Vergleich TS ↔ Python (Etappe 2, Toleranz 1e-6)."""
from __future__ import annotations

import json
import math
from pathlib import Path

from core.models.level1 import simulate
from core.params import make_params

CASES = {
    "elite_w_58_hurdle": ("elite_w_58", {}),
    "elite_m_70_fulcrum3_B": ("elite_m_70", {"board.fulcrum": 3.0, "board.fulcrum_model": "B"}),
    "jugend_td_start": ("jugend_w_45", {"technique.start_mode": "touchdown", "technique.v_z_td": 3.5}),
    "schwer_soft_passive_like": ("schwer_m_85", {"board.fulcrum": 9.0, "activation.a_plateau": 0.2, "board.zeta": 0.0}),
}
KEYS = ["v_z_td", "v_b_td", "z_b_min", "v_z_to", "z_c_to", "z_b_to", "v_b_to", "F_peak", "t_depression",
        "t_contact", "h_max_board", "x_board_plane", "t_flight", "W_act", "D_leg", "D_board",
        "board_phase_td_deg", "energy_balance_rel", "board_k_s", "board_m_b"]


def main() -> None:
    out = {}
    for name, (preset, ov) in CASES.items():
        p = make_params(preset, ov)
        res = simulate(p)
        out[name] = {
            "params": p.values(),
            "events": res.events,
            "metrics": {k: (None if isinstance(res.metrics[k], float) and math.isnan(res.metrics[k]) else res.metrics[k]) for k in KEYS},
        }
    path = Path(__file__).resolve().parent.parent / "web" / "src" / "sim-live" / "__fixtures__" / "level1_reference.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"geschrieben: {path}")


if __name__ == "__main__":
    main()
