"""Monte-Carlo (risk) and inference (CIs, p-values, drop-1, PSR, DSR, BH-FDR)."""
from __future__ import annotations

import numpy as np
import pytest

from mtf_smc.robustness.montecarlo import equity_path, max_drawdown, monte_carlo
from mtf_smc.robustness.stats import (
    benjamini_hochberg, bootstrap_mean_ci, deflated_sharpe_ratio, drop_one_expectancy,
    expected_max_sharpe, mean_positive_pvalue, probabilistic_sharpe_ratio,
    ttest_mean_positive_pvalue,
)


# ----------------------------- Monte-Carlo ----------------------------- #
def test_equity_path_and_drawdown():
    assert max_drawdown(equity_path(np.array([1.0, 1.0, -1.0]), 0.1)) == pytest.approx(-0.1)


def test_reshuffle_terminal_is_order_invariant():
    r = np.array([3.0, -1.0, 2.0, -1.0, 0.5])
    base = equity_path(r, 0.01)[-1]
    for _ in range(5):
        assert equity_path(np.random.default_rng(_).permutation(r), 0.01)[-1] == pytest.approx(base)


def test_monte_carlo_distributions_sane():
    r = [3, -1, -1, 2, -1, 3, -1, -1, 1, -1] * 5
    mc = monte_carlo(r, risk_pct=0.01, n_runs=500, seed=1)
    assert mc.n_runs == 500
    for d in (mc.maxdd_reshuffle_pct, mc.maxdd_bootstrap_pct):
        assert d["p05"] <= d["p50"] <= d["p95"] <= 0.0
    assert all(0.0 <= v <= 1.0 for v in mc.risk_of_ruin.values())


# ----------------------------- inference ----------------------------- #
def test_bootstrap_ci_brackets_mean():
    mean, lo, hi = bootstrap_mean_ci([3, -1, -1, 2], n_boot=3000, seed=1)
    assert mean == pytest.approx(0.75)
    assert lo < mean < hi


def test_pvalues_direction():
    assert mean_positive_pvalue([3, 3, 2, 3, 2], n_boot=3000, seed=1) < 0.05
    assert 0.3 < mean_positive_pvalue([1, -1, 1, -1, 1, -1], n_boot=3000, seed=1) < 0.7
    assert ttest_mean_positive_pvalue([3, 3, 2, 3, 2]) < 0.05


def test_drop_one_expectancy():
    d = drop_one_expectancy([3, -1, -1, 2, -1])
    assert d["full"] == pytest.approx(0.4)
    assert d["drop_best"] == pytest.approx(-0.25)
    assert d["delta"] == pytest.approx(0.65)


def test_psr_and_dsr():
    assert probabilistic_sharpe_ratio(0.0, 100, 0.0, 3.0) == pytest.approx(0.5)
    assert probabilistic_sharpe_ratio(0.2, 1000, 0.0, 3.0) > 0.9
    # expected-max grows with the number of trials
    assert expected_max_sharpe(1.0, 50) > expected_max_sharpe(1.0, 5) > 0
    # deflation: DSR over 42 trials is below the naive PSR
    psr = probabilistic_sharpe_ratio(0.15, 500, 0.0, 3.0)
    dsr = deflated_sharpe_ratio(0.15, 500, 0.0, 3.0, n_trials=42, sr_variance=0.01)
    assert dsr < psr


def test_benjamini_hochberg():
    reject, crit = benjamini_hochberg([0.001, 0.01, 0.04, 0.2, 0.5], alpha=0.05)
    assert reject.tolist() == [True, True, False, False, False]
    assert crit == pytest.approx(0.01)
