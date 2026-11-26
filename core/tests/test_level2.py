"""Tests Level 2 (SPEC 9.1 Nr. 4, Energiebilanz, Konsistenz der symbolischen Gleichungen)."""
from __future__ import annotations

import math
import os
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from core.athlete import build_anthropometry
from core.models import level2_generated as G
from core.models.level1 import simulate as sim1
from core.models.level2 import Level2Config, NQ, align_ankle, com_height_over_toe, initial_q, simulate
from core.params import make_params


def test_anthropometry_mass_and_com():
    for preset in ("elite_w_58", "elite_m_70", "jugend_w_45"):
        ps = make_params(preset)
        a = build_anthropometry(ps)
        assert a.total_mass == pytest.approx(ps["athlete.mass"], rel=2e-4)
        q = [0, 0, math.pi] + [0] * 9
        c = G.com(q, [0] * 12, a.p)
        assert 0.53 < c[1] / ps["athlete.height"] < 0.60  # Stand-KSP ≈ 0,55–0,58·H


def test_mass_matrix_symmetric_positive_definite():
    a = build_anthropometry(make_params("elite_w_58"))
    rng = np.random.default_rng(1)
    for _ in range(5):
        q = rng.uniform(-1, 1, 12)
        q[9:] *= 0.02
        M = np.array(G.mass_matrix(q, a.p)).reshape(12, 12)
        assert np.allclose(M, M.T, atol=1e-12)
        assert np.linalg.eigvalsh(M).min() > 0


def test_kane_equations_conserve_energy_in_free_flight():
    """Unabhängige Prüfung der generierten Gleichungen: ohne Momente, Kontakt und Dämpfung,
    nur Schwerkraft und Schwabbelfedern, bleibt T + V konstant (1e-8)."""
    a = build_anthropometry(make_params("elite_m_70"))
    kw = [a.wobble_k[w] for w in ("trunk", "thigh", "shank")]

    def rhs(t, y):
        q, u = y[:12], y[12:]
        Fw = [-kw[i] * q[9 + i] ** 3 for i in range(3)]
        M = np.array(G.mass_matrix(q, a.p)).reshape(12, 12)
        f = np.array(G.forcing(q, u, a.p, [0] * 6, [0] * 6, Fw))
        return np.concatenate([u, np.linalg.solve(M, f)])

    def E(y):
        ke, pe = G.energy(y[:12], y[12:], a.p)
        return ke + pe + sum(kw[i] * y[9 + i] ** 4 / 4 for i in range(3))

    y0 = np.zeros(24)
    y0[2] = math.pi
    y0[3:9] = [0.3, 0.1, 0.8, 0.6, 1.0, 0.5]
    y0[9:12] = [0.01, -0.008, 0.005]
    y0[12:24] = [0.5, 4.0, 2.0, -3, 4, 6, -5, 8, 3, 0.2, -0.3, 0.1]
    sol = solve_ivp(rhs, (0, 0.5), y0, method="DOP853", rtol=1e-11, atol=1e-12, dense_output=True)
    Es = np.array([E(sol.sol(t)) for t in np.linspace(0, 0.5, 51)])
    assert np.max(np.abs(Es - Es[0])) / abs(Es[0]) < 1e-8
    # Drehimpuls um den KSP bleibt in der Flugphase erhalten (SPEC 9.1 Nr. 5 für Mehrkörper)
    H = [sum(G.segment_momentum(sol.sol(t)[:12], sol.sol(t)[12:], a.p)) for t in np.linspace(0, 0.5, 11)]
    assert np.max(np.abs(np.array(H) - H[0])) < 1e-8 * max(1, abs(H[0]))


def test_04_level2_locked_reduces_to_level1():
    """SPEC 9.1 Nr. 4: Level 2 mit gesperrten Gelenken (und Schwabbelmassen) entspricht Level 1.
    Abbildung: ein Kontaktpunkt (Ballen) senkrecht unter dem KSP, linearer Kontakt k⊥ = k_Bein,
    keine Dämpfung, keine Muskeln, Brett ohne Neigung/Horizontalbewegung."""
    ov = {
        "technique.start_mode": "touchdown", "technique.v_z_td": 3.5, "technique.board_z_td": 0.0,
        "technique.board_v_td": 0.0, "technique.v_x": 0.0, "posture.shoulder_rate": 0.0,
        "posture.com_offset": 0.0, "posture.align": "ja", "board.zeta": 0.0, "board.horiz_coeff": 0.0,
        "contact.board_slope": "none", "numerics.rtol2": 1e-10, "numerics.max_step2": 2e-4,
    }
    p2 = make_params("elite_m_70", ov)
    cfg2 = Level2Config.from_params(p2, active=False)
    cfg2 = replace(cfg2, locked=True, linear_contact=True, contact_points=("ball",))
    q0 = initial_q(cfg2, p2, 0.0, align_ankle(cfg2, p2, 0.0))
    ball_z = G.points(q0, cfg2.anthro.p)[3]
    h = G.com(q0, [0] * NQ, cfg2.anthro.p)[1] - ball_z
    r2 = simulate(p2, cfg=cfg2, series=False)

    H = p2["athlete.height"]
    p1 = make_params("elite_m_70", {
        **{k: v for k, v in ov.items() if not k.startswith(("posture", "contact", "numerics.rtol2", "numerics.max_step2"))},
        "leg.c_leg": 0.0, "leg.k_leg_per_kg": p2["contact.k_perp"] / p2["athlete.mass"],
        "leg.l_td_ratio": h / H,
    })
    r1 = sim1(p1, active=False)
    m1, m2 = r1.metrics, r2.metrics
    for k in ("v_z_to", "t_contact", "z_b_min", "t_depression"):
        assert m2[k] == pytest.approx(m1[k], rel=2e-5), k
    assert abs(m2["v_x_to"]) < 1e-9
    assert abs(m2["H_y"]) < 1e-6


@pytest.mark.parametrize("preset", ["elite_w_58", "schwer_m_85"])
def test_level2_energy_balance(preset):
    """SPEC Kap. 7: Bilanz Muskelarbeit + Anfangsenergie = Endenergie + Verluste (< 0,5 %)."""
    r = simulate(make_params(preset), series=False)
    assert r.metrics["energy_balance_rel"] < 1e-4
    assert not r.warnings


def test_level2_plausibility_spec_9_2():
    """SPEC 9.2: Knie und Hüfte beugen nach TD noch (bis ca. 100 ms), dann Streckung;
    weicheres Fulkrum → längere Kontaktzeit."""
    r = simulate(make_params("elite_w_58"), series=False)
    m = r.metrics
    assert 0.04 < m["t_knee_flex_max"] < 0.2
    assert m["knee_angle_max_deg"] > m["knee_angle_td_deg"] + 5
    assert m["knee_angle_to_deg"] < m["knee_angle_max_deg"] - 20
    soft = simulate(make_params("elite_w_58", {"board.fulcrum": 9.0}), series=False).metrics
    stiff = simulate(make_params("elite_w_58", {"board.fulcrum": 3.0}), series=False).metrics
    assert soft["t_contact"] > stiff["t_contact"]


@pytest.mark.skipif(not os.environ.get("RUN_SLOW"), reason="Neuerzeugung dauert ~30 s (RUN_SLOW=1)")
def test_generated_code_is_up_to_date(tmp_path: Path):
    from scripts import generate_level2 as gen

    code = gen.emit(*gen.build())
    assert code == Path(G.__file__).read_text()


def test_level2_convergence():
    """SPEC 9.1 Nr. 8 sinngemäß für Level 2: engere Toleranz ändert v_z,TO um < 0,1 %."""
    a = simulate(make_params("elite_w_58", {"numerics.rtol2": 1e-6}), series=False).metrics["v_z_to"]
    b = simulate(make_params("elite_w_58", {"numerics.rtol2": 1e-8}), series=False).metrics["v_z_to"]
    assert abs(a - b) / abs(b) < 1e-3
