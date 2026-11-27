"""Tests Modus B (Etappe 6): Filter, Import, Ereigniserkennung, inverse Dynamik, Matching.
Grundlage sind synthetische Daten mit bekannter Wahrheit (core/synthetic.py)."""
from __future__ import annotations

import math
import os

import numpy as np
import pytest

from core.athlete import build_anthropometry
from core.filtering import butter_lowpass, residual_analysis
from core.importers import ImportSettings, guess_mapping, read_any, read_csv, read_trc, to_measurement
from core.inverse import inverse_dynamics
from core.matching import run_match_one, target_from_inverse
from core.models.level2 import Level2Config
from core.params import make_params
from core.synthetic import TRUTH_OVERRIDES, make_synthetic


@pytest.fixture(scope="module")
def synthetic():
    trc, truth = make_synthetic(rate=200, noise_m=0.003, seed=0)
    ps = make_params("elite_w_58")
    kappa = Level2Config.from_params(ps).kappa
    meas = to_measurement(read_any(trc, "x.trc"), ImportSettings(board_slope_per_m=kappa))
    inv = inverse_dynamics(meas, build_anthropometry(ps))
    return trc, truth, ps, meas, inv


def test_butterworth_zero_phase_and_attenuation():
    fs = 200.0
    t = np.arange(0, 2, 1 / fs)
    slow = np.sin(2 * math.pi * 2 * t)
    fast = 0.5 * np.sin(2 * math.pi * 40 * t)
    y = butter_lowpass(slow + fast, fs, 8.0)
    inner = slice(40, -40)
    assert np.max(np.abs(y[inner] - slow[inner])) < 0.03  # 2 Hz ungedämpft, phasenfrei; 40 Hz entfernt


def test_residual_analysis_finds_reasonable_cutoff():
    fs = 200.0
    t = np.arange(0, 3, 1 / fs)
    rng = np.random.default_rng(0)
    x = np.sin(2 * math.pi * 1.5 * t) + 0.3 * np.sin(2 * math.pi * 4 * t) + rng.normal(0, 0.01, len(t))
    r = residual_analysis(x, fs)
    assert 5.0 < r.fc_opt < 12.0
    assert r.intercept == pytest.approx(0.01, rel=0.2)  # Achsenabschnitt ≈ Rausch-RMS


def test_trc_and_csv_import_and_mapping():
    trc, _truth = make_synthetic(rate=100, noise_m=0.0)
    raw = read_trc(trc)
    assert raw.units == "mm" and raw.rate == 100
    assert "r_knee_study" in raw.markers and raw.markers["r_knee_study"].shape[1] == 3
    m = guess_mapping(list(raw.markers))
    assert m["knee"] == "r_knee_study" and m["hip"] == "RHip" and m["board_tip"] == "board_tip"
    csv_text = "Zeit (s);Knie X;Knie Y;Hüfte X;Hüfte Y\n0,00;1,0;2,0;1,1;2,5\n0,01;1,1;2,1;1,2;2,6\n"
    raw2 = read_csv(csv_text)
    assert set(raw2.markers) == {"Knie", "Hüfte"}
    assert raw2.markers["Knie"][1, 0] == pytest.approx(1.1)
    assert guess_mapping(list(raw2.markers))["knee"] == "Knie"


def test_coordinate_transform_flip_and_scale():
    text = "time,toe_x,toe_y,heel_x,heel_y,ankle_x,ankle_y,knee_x,knee_y,hip_x,hip_y,shoulder_x,shoulder_y,elbow_x,elbow_y,wrist_x,wrist_y\n" \
           "0,100,500,80,500,85,490,90,400,95,300,100,150,110,200,120,250\n0.01,100,500,80,500,85,490,90,400,95,300,100,150,110,200,120,250\n"
    raw = read_csv(text)
    st = ImportSettings(unit="px", scale_m_per_px=0.01, flip_vertical=True, origin="manual", origin_x=100, origin_z=500, t_td=0.0, t_to=0.01)
    meas = to_measurement(raw, st)
    assert meas.points["toe"][0] == pytest.approx([0.0, 0.0])
    assert meas.points["hip"][0] == pytest.approx([-0.05, 2.0])  # 200 px über der Zehe, y-Achse gespiegelt


def test_event_detection_within_one_frame(synthetic):
    _trc, truth, _ps, meas, _inv = synthetic
    td_err = (-meas.t[0]) - truth["t_td_file"]
    to_err = meas.t_to - (truth["t_to_file"] - truth["t_td_file"])
    assert abs(td_err) < 0.005  # < 1 Bild bei 200 Hz
    assert abs(to_err) < 0.015


def test_inverse_dynamics_noise_free_matches_truth_in_smooth_phase():
    """Ohne Rauschen und Filter, starre Schwabbelmassen: inverse Dynamik reproduziert die
    Brettkraft der Simulation im glatten Teil des Kontakts (Algebra-Prüfung; Aufprall und
    Endanschläge sind numerisch nicht differenzierbar und ausgenommen)."""
    rigid = {**TRUTH_OVERRIDES, "wobble.trunk_k": 1e12, "wobble.thigh_k": 1e13, "wobble.shank_k": 1e13, "wobble.scale_k_with_mass": "nein"}
    trc, truth = make_synthetic(ps=make_params("elite_w_58", rigid), rate=1000, noise_m=0.0)
    ps = make_params("elite_w_58")
    meas = to_measurement(read_any(trc, "x.trc"), ImportSettings(t_td=truth["t_td_file"], t_to=truth["t_to_file"]))
    inv = inverse_dynamics(meas, build_anthropometry(ps), cutoff=400.0)
    cs = truth["contact_series"]
    tc = np.array(cs["t"])
    sel = (tc > 0.17) & (tc < 0.30)
    Fz = np.array(cs["Fz"])[sel]
    Fi = np.interp(tc[sel], inv.t, inv.F[:, 1])
    assert np.sqrt(np.mean((Fi - Fz) ** 2)) / np.mean(Fz) < 0.05
    th = np.array(cs["theta"])
    qi = np.interp(tc, inv.t, inv.q[:, 5])
    assert np.max(np.abs(qi - th[:, 2])) < 1e-3  # Kniewinkel exakt rekonstruiert
    assert inv.metrics["H_y"] == pytest.approx(truth["metrics"]["H_y"], rel=0.05)


def test_inverse_with_noise_is_usable(synthetic):
    _trc, truth, _ps, _meas, inv = synthetic
    m = inv.metrics
    assert 4.0 <= inv.cutoff <= 12.0
    assert m["v_z_to"] == pytest.approx(truth["metrics"]["v_z_to"], abs=0.25)
    assert m["residual_flight_bw"] < 1.5
    assert any("unsicher" in w for w in inv.warnings)


def test_matching_score_prefers_true_parameters(synthetic):
    _trc, _truth, ps, meas, inv = synthetic
    tgt = target_from_inverse(inv, ps, meas.t_to)
    s_true = run_match_one(make_params("elite_w_58", TRUTH_OVERRIDES).values(), tgt)
    s_def = run_match_one(ps.values(), tgt)
    assert s_true["ok"] and s_def["ok"]
    assert s_true["score"] < s_def["score"]
    assert s_true["components"]["Kontaktdauer"] < 5.0


@pytest.mark.skipif(not os.environ.get("RUN_SLOW"), reason="Matching dauert einige Minuten (RUN_SLOW=1)")
def test_matching_reaches_spec_threshold(synthetic):
    from core.matching import match

    _trc, _truth, ps, meas, inv = synthetic
    res = match(inv, ps, meas.t_to, generations=12, popsize=12)
    assert res.score < 10.0  # SPEC 11.2 Etappe 6: Matching-RMS < 10 % an Testdaten


def test_q_from_series_branch_near_pi():
    """Regression: Zehenwinkel knapp über π (Brett nach oben geneigt) darf die absoluten
    Winkel nicht um 2π verschieben (Rumpforientierung im Matching)."""
    from types import SimpleNamespace

    from core.matching import _q_from_series

    eps = 0.01
    toe = np.array([0.0, 0.0])
    ball = toe + 0.06 * np.array([math.cos(math.pi + eps), math.sin(math.pi + eps)])
    pts = np.tile(np.r_[toe, ball, np.zeros(20)], (3, 1))
    r = SimpleNamespace(series={"theta": np.zeros((3, 6)), "points": pts})
    q = _q_from_series(r)
    assert q[0, 2] == pytest.approx(math.pi + eps, abs=1e-9)
