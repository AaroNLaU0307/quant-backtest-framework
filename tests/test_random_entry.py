"""Two-null random-entry benchmark: structure, bounds, and cadence matching."""
from __future__ import annotations

import pytest

from mtf_smc.config import StrategyConfig
from mtf_smc.engine.backtester import run_backtest
from mtf_smc.robustness.random_entry import NullResult, random_entry_benchmark


def test_random_entry_benchmark_runs_both_nulls(is_m1):
    sl = is_m1.loc["2018-01-01":"2018-12-31"]
    cfg = StrategyConfig(entry_model="direct", htf="D1", tp_mode="fixed_3R")
    res = run_backtest(sl, cfg)
    if res.n_trades < 3:
        pytest.skip("too few strategy trades to benchmark")

    out = random_entry_benchmark(sl, cfg, res.trades, n_runs=25, seed=1, ctx=res.context)
    assert "unconstrained" in out and "bias_matched" in out
    for nr in out.values():
        assert isinstance(nr, NullResult)
        assert 0.0 <= nr.percentile <= 1.0           # a valid percentile
        assert nr.n_runs > 0
        assert nr.strategy_expectancy_R == pytest.approx(res.trades_df["R"].mean())
        assert nr.null_p05_R <= nr.null_mean_R <= nr.null_p95_R
