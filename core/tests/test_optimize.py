"""Tests Optimierung (SPEC 6.6)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import numpy as np

from core.optimize import CMAES, Objective, default_variables, mirror01, optimize
from core.params import make_params


def test_cmaes_finds_minimum_of_shifted_sphere():
    target = np.array([0.2, 0.7, 0.4, 0.9])
    es = CMAES(np.full(4, 0.5), 0.2, seed=3)
    for _ in range(80):
        xs = es.ask()
        es.tell(xs, [float(((x - target) ** 2).sum()) for x in xs])
    assert np.allclose(es.mean, target, atol=1e-3)


def test_mirror_keeps_bounds():
    x = mirror01(np.array([-0.2, 1.3, 0.5, 2.4]))
    assert np.all((x >= 0) & (x <= 1))
    assert np.allclose(x, [0.2, 0.7, 0.5, 0.4])


def test_level1_optimization_improves_height_with_robustness():
    ps = make_params("elite_w_58")
    with ThreadPoolExecutor(4) as ex:
        res = optimize(ps, 1, Objective("height", min_clearance=0.3), generations=4, popsize=8, robust=True, executor=ex, seed=1)
    assert res.best_score >= res.baseline_score
    assert res.best_metrics["h_max_board"] >= res.baseline_metrics["h_max_board"] - 1e-9
    assert set(res.best_values) == set(default_variables(1))
    for k, v in res.best_values.items():
        sp = ps.params[k]
        assert sp.min - 1e-12 <= v <= sp.max + 1e-12


def test_clearance_penalty():
    o = Objective("height", min_clearance=0.5)
    good = {"ok": True, "h_max_board": 1.5, "x_board_plane": 0.8}
    bad = {"ok": True, "h_max_board": 1.5, "x_board_plane": 0.1}
    assert o.score(good, 1) > o.score(bad, 1)
