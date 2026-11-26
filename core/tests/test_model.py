"""Ergänzende Tests: Brettmodell, Parameter, Ereignisse, Energiebilanz, Plausibilität (SPEC 4, 7, 9.2)."""
from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from core.board import board_phase_deg, effective_mass, make_board, stiffness
from core.models.level1 import Level1Config, leg_force_parts, simulate
from core.muscles import Activation, force_length, force_velocity
from core.params import load_defaults, make_params


def test_all_parameters_have_source_and_status():
    ps = load_defaults()
    for key, spec in ps.params.items():
        assert spec.source, key
        assert spec.status in {"Literatur", "Schätzung", "Gemessen", "Eingabe"}, key
        assert spec.unit, key


def test_out_of_range_rejected():
    with pytest.raises(ValueError):
        make_params(overrides={"board.fulcrum": 12.0})


def test_board_reference_values():
    p = make_params()
    b = make_board(p, d=0.0)
    assert b.k_s == pytest.approx(5446.0)
    assert b.m_b == pytest.approx(8.87)
    assert b.f0 == pytest.approx(math.sqrt(5446 / 8.87) / (2 * math.pi))


@pytest.mark.parametrize("model", ["A", "B"])
def test_fulcrum_softer_means_less_stiff_more_mass(model):
    p = make_params()
    ks = [stiffness(p, 0.0, F, model)[0] for F in (1, 3, 5, 7.5, 9)]
    assert all(a > b for a, b in zip(ks, ks[1:]))
    ms = [effective_mass(p, F, model) for F in (1, 5, 9)]
    assert ms[0] < ms[1] < ms[2]


def test_variant_b_consistent_with_variant_a():
    """SPEC 4.3 Prüfrechnung: eine Stufe ≈ 5 % ≈ 250–300 N/m."""
    p = make_params()
    k75 = stiffness(p, 0.0, 7.5, "B")[0]
    k85 = stiffness(p, 0.0, 8.5, "B")[0]
    assert 230 < k75 - k85 < 320
    assert 0.04 < (k75 - k85) / k75 < 0.06


def test_board_phase_convention():
    w = 10.0
    assert board_phase_deg(1.0, 0.0, w) == pytest.approx(0.0)
    assert board_phase_deg(0.0, -1.0, w) == pytest.approx(90.0)
    assert board_phase_deg(-1.0, 0.0, w) == pytest.approx(180.0)
    assert board_phase_deg(0.0, 1.0, w) == pytest.approx(270.0)


def test_muscle_functions():
    assert force_velocity(0.0, 4.0, 0.5, 1.5) == 1.0
    assert force_velocity(4.0, 4.0, 0.5, 1.5) == 0.0
    assert force_velocity(-50.0, 4.0, 0.5, 1.5) == pytest.approx(1.5, abs=1e-6)
    # C¹-Stetigkeit in v = 0
    e = 1e-7
    d_left = (force_velocity(0.0, 4, 0.5, 1.5) - force_velocity(-e, 4, 0.5, 1.5)) / e
    d_right = (force_velocity(e, 4, 0.5, 1.5) - force_velocity(0.0, 4, 0.5, 1.5)) / e
    assert d_left == pytest.approx(d_right, rel=1e-4)
    assert force_length(1.0, 0.8, 1.0) == 0.0
    assert force_length(0.8, 0.8, 1.0) == 1.0
    a = Activation(0.2, 0.0, 0.1, 1.0, 0.5, 0.1, 0.3)
    assert a(-1) == pytest.approx(0.2) and a(0.3) == pytest.approx(1.0) and a(1.0) == pytest.approx(0.3)


def test_event_localisation_precision():
    """SPEC Kap. 2: Ereignisse < 0,1 ms genau – hier Event-Funktion am Ereignis ≈ 0."""
    p = make_params("elite_w_58")
    cfg = Level1Config.from_params(p)
    res = simulate(p, cfg=cfg)
    s = res.series
    i_td = list(s["t"]).index(0.0)
    l_td = s["z_c"][i_td] - s["z_b"][i_td]
    assert abs(l_td - cfg.l_td) < 1e-7  # |v_rel|·1e-8 s
    assert abs(s["v_b"][list(s["t"]).index(res.events["LP"])]) < 1e-6
    y_to = [s["z_c"][-1], s["v_c"][-1], s["z_b"][-1], s["v_b"][-1]]
    F_to = leg_force_parts(cfg, res.events["TO"], y_to + [0] * 5)[0]
    assert abs(F_to) < 1e-2  # N, bei dF/dt ~ 1e5 N/s und tol 1e-8 s


@settings(max_examples=15, deadline=None)
@given(
    mass=st.floats(40, 95), height=st.floats(1.45, 1.95), fulcrum=st.sampled_from([1.0, 3.0, 5.0, 7.5, 9.0]),
    hurdle=st.floats(0.4, 1.1), model=st.sampled_from(["A", "B"]),
)
def test_energy_balance_property(mass, height, fulcrum, hurdle, model):
    """SPEC Kap. 7: Energiebilanz-Abweichung < 0,5 % (Knicke werden als Ereignisse geortet → ~1e-12)."""
    p = make_params(overrides={
        "athlete.mass": mass, "athlete.height": height, "board.fulcrum": fulcrum,
        "technique.hurdle_height": hurdle, "board.fulcrum_model": model,
    })
    res = simulate(p)
    assert res.metrics["energy_balance_rel"] < 1e-6  # SPEC-Grenze 5e-3
    assert res.metrics["t_contact"] > 0.2


def test_plausibility_softer_fulcrum():
    """SPEC 9.2 (Jones & Miller 1996): weicheres Fulkrum → längere Kontaktdauer,
    tiefere Brettdurchbiegung."""
    r_stiff = simulate(make_params("elite_w_58", {"board.fulcrum": 3.0, "technique.start_mode": "touchdown"}))
    r_soft = simulate(make_params("elite_w_58", {"board.fulcrum": 9.0, "technique.start_mode": "touchdown"}))
    assert r_soft.metrics["t_contact"] > r_stiff.metrics["t_contact"]
    assert r_soft.metrics["z_b_min"] < r_stiff.metrics["z_b_min"]
