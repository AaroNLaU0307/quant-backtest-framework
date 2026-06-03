"""Performance metrics: hand-computed cases, the eyeballed example trades, and an integration check."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from mtf_smc.config import StrategyConfig
from mtf_smc.engine.backtester import run_backtest
from mtf_smc.metrics.performance import equity_stats, summarize_backtest, trade_stats


def test_trade_stats_hand_computed():
    s = trade_stats([3, -1, -1, 2, -1, 3])
    assert s["n_trades"] == 6
    assert s["win_rate"] == pytest.approx(0.5)
    assert s["expectancy_R"] == pytest.approx(5 / 6)
    assert s["profit_factor"] == pytest.approx(8 / 3)     # gross win 8 / gross loss 3
    assert s["payoff_ratio"] == pytest.approx((8 / 3) / 1.0)
    assert s["max_consec_losses"] == 2


def test_trade_stats_no_losers_is_infinite_pf():
    s = trade_stats([1.0, 2.0, 0.5])
    assert math.isinf(s["profit_factor"])
    assert s["max_consec_losses"] == 0


def test_trade_stats_matches_eyeballed_examples():
    # The exact realized R of the four verified example trades (full stop / 3R / be_stop / scale).
    r = [-1.0302, 2.9868, -0.0194, 1.9758]
    s = trade_stats(r)
    assert s["win_rate"] == pytest.approx(0.5)
    assert s["expectancy_R"] == pytest.approx(0.97825, abs=1e-5)
    assert s["profit_factor"] == pytest.approx(4.9626 / 1.0496, abs=1e-3)
    assert s["max_consec_losses"] == 1


def test_equity_stats_drawdown_and_return():
    idx = pd.bdate_range("2020-01-01", periods=5, tz="UTC")
    ec = pd.Series([100.0, 110.0, 105.0, 108.0, 120.0], index=idx)
    s = equity_stats(ec)
    assert s["total_return"] == pytest.approx(0.20)
    assert s["max_drawdown_pct"] == pytest.approx(-5.0 / 110.0, abs=1e-6)   # 110 -> 105
    assert s["sharpe"] > 0 and s["ulcer_index"] > 0
    assert s["max_dd_duration_days"] > 0


def test_equity_stats_handles_degenerate_curve():
    ec = pd.Series([100.0], index=pd.DatetimeIndex(["2020-01-01"], tz="UTC"))
    s = equity_stats(ec)
    assert s["total_return"] == 0.0 and math.isnan(s["sharpe"])


def test_summarize_backtest_consistent_with_trades(is_m1):
    res = run_backtest(is_m1.loc["2018-01-01":"2018-09-30"],
                       StrategyConfig(entry_model="direct", htf="D1", tp_mode="fixed_3R"))
    summary = summarize_backtest(res)
    if res.n_trades:
        assert summary["expectancy_R"] == pytest.approx(res.trades_df["R"].mean())
        assert summary["n_trades"] == res.n_trades
