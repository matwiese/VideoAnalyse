"""Automatisierte Tests nach SPEC Kap. 9.1 (Nr. 1, 2, 3, 5, 7, 8 für Etappe 1).

Nr. 4 (Level 2 → Level 1) und Nr. 6 (Level-3-Symmetrie) folgen in Etappe 3 bzw. 7.
"""
from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.linalg import eigh

from core.board import free_board_rhs, make_board
from core.events import Event, integrate
from core.flight import flight, simulate_rigid_flight
from core.models.level1 import (
    Level1Config,
    leg_force_parts,
    mechanical_energy,
    rhs_contact,
    simulate,
)
from core.params import make_params


def measure_period(board, z0=-0.1, n_periods=5, dt=1e-4):
    """Periode der freien Brettschwingung aus aufeinanderfolgenden Aufwärts-Nulldurchgängen."""
    up = Event("up", lambda t, y: y[0], +1)
    t, y = 0.0, [z0, 0.0]
    crossings = []
    while len(crossings) < n_periods + 1:
        r = integrate(free_board_rhs(board), t, y, dt, t + 10.0, [up], 1e-11)
        assert r.event == "up"
        crossings.append(r.t[-1])
        t, y = r.t[-1], r.y[-1]
        # einen Schritt weiter, damit derselbe Durchgang nicht erneut erkannt wird
        from core.events import rk4_step
        y = rk4_step(free_board_rhs(board), t, y, dt)
        t += dt
    return float(np.mean(np.diff(crossings)))


# ---------------------------------------------------------------------------
# Nr. 1 – Freie Brettschwingung: f = √(k/m_b)/2π auf 0,1 %
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("fulcrum,model", [(7.5, "A"), (1.0, "A"), (9.0, "A"), (5.0, "B"), (9.0, "B")])
def test_01_free_board_frequency(fulcrum, model):
    p = make_params(overrides={"board.zeta": 0.0, "board.fulcrum": fulcrum, "board.fulcrum_model": model})
    b = make_board(p)
    T = measure_period(b)
    f_num = 1.0 / T
    assert abs(f_num - b.f0) / b.f0 < 1e-3


def test_empty_board_stays_at_rest():
    """SPEC 4.2: Leeres Brett in Ruhe bleibt bei z_b = 0 (kein m_b·g-Term)."""
    b = make_board(make_params())
    r = integrate(free_board_rhs(b), 0.0, [0.0, 0.0], 1e-4, 2.0)
    assert max(abs(y[0]) for y in r.y) == 0.0


# ---------------------------------------------------------------------------
# Nr. 2 – Passiver Springer ohne Muskeln/Dämpfung: Energie konstant auf 1e-6
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("preset", ["elite_w_58", "schwer_m_85"])
def test_02_passive_energy_conservation(preset):
    p = make_params(preset, {"board.zeta": 0.0, "leg.c_leg": 0.0, "technique.start_mode": "touchdown"})
    cfg = Level1Config.from_params(p, active=False)
    res = simulate(p, cfg=cfg)
    s = res.series
    c = s["contact"]
    E = np.array([
        mechanical_energy(cfg, [zc, vc, zb, vb], True)
        for zc, vc, zb, vb in zip(s["z_c"][c], s["v_c"][c], s["z_b"][c], s["v_b"][c])
    ])
    assert "TO" in res.events
    assert np.max(np.abs(E - E[0])) / abs(E[0]) < 1e-6


def test_02b_passive_with_hurdle_energy_conservation():
    p = make_params("elite_w_58", {"board.zeta": 0.0, "leg.c_leg": 0.0})
    res = simulate(p, active=False)
    assert res.metrics["energy_balance_rel"] < 1e-6
    # passiv und verlustfrei: Absprung so schnell wie Relativ-Aufprall erlaubt, Bilanz geschlossen
    assert res.metrics["W_act"] == 0.0


# ---------------------------------------------------------------------------
# Nr. 3 – Level 1 vs. analytische Lösung des gekoppelten Zwei-Massen-Schwingers
# ---------------------------------------------------------------------------
def test_03_level1_vs_analytic_two_mass():
    p = make_params("elite_w_58", {"board.zeta": 0.0, "leg.c_leg": 0.0})
    cfg = Level1Config.from_params(p, active=False)
    M, mb, ks, kl, g = cfg.M, cfg.board.m_b, cfg.board.k_s, cfg.k_leg, cfg.g
    # statisches Gleichgewicht
    zb_eq = -M * g / ks
    zc_eq = zb_eq + cfg.l_td - M * g / kl
    u0 = np.array([0.004, -0.010])  # kleine Auslenkung, Bein bleibt komprimiert
    v0 = np.array([0.05, 0.02])
    y0 = [zc_eq + u0[0], v0[0], zb_eq + u0[1], v0[1], 0, 0, 0, 0, 0]
    T_end = 2.0
    r = integrate(rhs_contact(cfg), 0.0, y0, 1e-4, T_end)
    # analytisch: Modalzerlegung (M ü + K u = 0)
    Mm = np.diag([M, mb])
    K = np.array([[kl, -kl], [-kl, kl + ks]])
    w2, Phi = eigh(K, Mm)  # Φᵀ M Φ = I
    w = np.sqrt(w2)
    q0 = Phi.T @ Mm @ u0
    qd0 = Phi.T @ Mm @ v0
    t = np.asarray(r.t)
    q = q0[None, :] * np.cos(np.outer(t, w)) + (qd0 / w)[None, :] * np.sin(np.outer(t, w))
    u = q @ Phi.T
    num = np.array([[y[0] - zc_eq, y[2] - zb_eq] for y in r.y])
    amp = np.max(np.abs(u))
    assert np.max(np.abs(num - u)) / amp < 1e-6
    # Kontakt blieb erhalten (Feder immer komprimiert)
    assert all(leg_force_parts(cfg, 0.0, y)[1] > 0 for y in r.y)


# ---------------------------------------------------------------------------
# Nr. 5 – Flugphase: Drehimpuls um KSP konstant auf 1e-9, Bahn parabolisch
# ---------------------------------------------------------------------------
def test_05_flight_angular_momentum_and_parabola():
    g = 9.81
    H = 45.0  # kg m²/s
    I = lambda t: 14.0 - 10.0 * math.sin(min(t, 0.6) / 0.6 * math.pi / 2) ** 2  # gestreckt → gehockt
    dI = lambda t: (-10.0 * math.sin(math.pi * t / 0.6) * (math.pi / 1.2)) if t < 0.6 else 0.0
    t, Y = simulate_rigid_flight((0.1, 1.2, 0.5, 4.8, 0.0), H, I, dI, g, 1.6)
    Hs = np.array([I(ti) * w for ti, w in zip(t, Y[5])])
    assert np.max(np.abs(Hs - H)) / H < 1e-9
    z_exact = 1.2 + 4.8 * t - 0.5 * g * t * t
    x_exact = 0.1 + 0.5 * t
    assert np.max(np.abs(Y[1] - z_exact)) < 1e-9
    assert np.max(np.abs(Y[0] - x_exact)) < 1e-9


def test_05b_analytic_flight_formulas():
    g = 9.81
    fr = flight(1.0, 5.0, 0.0, 0.5, g, -3.0, H_y=40.0, inertias={"gehockt": 4.0})
    assert math.isclose(fr.z_apex, 1.0 + 25.0 / (2 * g), rel_tol=1e-12)
    t_w = (5.0 + math.sqrt(25.0 + 2 * g * 4.0)) / g
    assert math.isclose(fr.t_water, t_w, rel_tol=1e-12)
    z_at = 1.0 + 5.0 * t_w - 0.5 * g * t_w ** 2
    assert math.isclose(z_at, -3.0, abs_tol=1e-12)
    assert math.isclose(fr.rotation_potential, 40.0 * t_w)
    assert math.isclose(fr.somersaults["gehockt"], 40.0 * t_w / (2 * math.pi * 4.0))


# ---------------------------------------------------------------------------
# Nr. 7 – Skalierung: doppelte Masse bei gleicher Steifigkeit → f × 1/√2
# ---------------------------------------------------------------------------
def test_07_mass_scaling():
    from dataclasses import replace

    b1 = make_board(make_params(overrides={"board.zeta": 0.0}))
    b2 = replace(b1, m_b=2 * b1.m_b)  # außerhalb des UI-Bereichs ±50 %, daher direkt
    assert b1.k_s == b2.k_s
    f1 = 1 / measure_period(b1)
    f2 = 1 / measure_period(b2)
    assert abs(f2 / f1 - 1 / math.sqrt(2)) < 1e-4
    # auch für das belastete Brett √(k/(m_b+M))
    assert math.isclose(b2.f_loaded(2 * 62.0) / b1.f_loaded(62.0), 1 / math.sqrt(2), rel_tol=1e-12)


# ---------------------------------------------------------------------------
# Nr. 8 – Konvergenz: halbe Schrittweite ändert v_z,TO um < 0,1 %
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("preset", ["elite_w_58", "elite_m_70"])
def test_08_convergence(preset):
    v1 = simulate(make_params(preset)).metrics["v_z_to"]
    v2 = simulate(make_params(preset, {"numerics.dt": 5e-5})).metrics["v_z_to"]
    assert abs(v1 - v2) / abs(v2) < 1e-3
