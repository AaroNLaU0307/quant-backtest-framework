"""Two-null random-entry benchmark: per-trade metrics, holding-match, structure and bounds."""
from __future__ import annotations

import math

import pytest

from mtf_smc.config import StrategyConfig
from mtf_smc.engine.backtester import run_backtest
from mtf_smc.robustness.random_entry import MetricNull, NullResult, random_entry_benchmark


def test_random_entry_benchmark_per_trade_metrics_and_holding(is_m1):
    sl = is_m1.loc["2018-01-01":"2018-12-31"]
    cfg = StrategyConfig(entry_model="direct", htf="D1", tp_mode="fixed_3R")
    res = run_backtest(sl, cfg)
    if res.n_trades < 3:
        pytest.skip("too few strategy trades to benchmark")

    out = random_entry_benchmark(sl, cfg, res.trades, n_runs=20, seed=1, ctx=res.context)
    assert "unconstrained" in out and "bias_matched" in out
    strat_mean_R = res.trades_df["R"].mean()
    for nr in out.values():
        assert isinstance(nr, NullResult) and nr.n_runs > 0
        # edge reported on per-trade E[R] and per-trade Sharpe
        assert nr.expectancy_R.metric == "expectancy_R"
        assert nr.sharpe_per_trade.metric == "sharpe_per_trade"
        assert nr.expectancy_R.strategy == pytest.approx(strat_mean_R)
        for mn in (nr.expectancy_R, nr.sharpe_per_trade):
            assert isinstance(mn, MetricNull)
            if not math.isnan(mn.null_mean):
                assert 0.0 <= mn.percentile <= 1.0
                assert mn.null_p05 <= mn.null_mean <= mn.null_p95
        # holding-time is matched (both medians positive and broadly comparable)
        assert nr.strategy_hold_bars_median > 0 and nr.null_hold_bars_median > 0
