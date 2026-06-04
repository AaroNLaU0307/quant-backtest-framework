"""Walk-forward (per-year sequential OOS) and regime breakdowns."""
from __future__ import annotations

from mtf_smc.config import StrategyConfig
from mtf_smc.engine.backtester import run_backtest
from mtf_smc.robustness.walkforward import regime_breakdown, walk_forward_by_year


def test_walk_forward_and_regime(is_m1):
    res = run_backtest(is_m1.loc["2017-01-01":"2019-12-31"],
                       StrategyConfig(entry_model="direct", htf="D1", tp_mode="fixed_3R"))
    if res.n_trades < 5:
        import pytest
        pytest.skip("too few trades")

    wf = walk_forward_by_year(res.trades)
    assert {"window", "n_trades", "expectancy_R", "ci_lo", "ci_hi", "ci_crosses_zero"}.issubset(wf.columns)
    assert wf["n_trades"].sum() == res.n_trades                 # every trade bucketed once
    assert len(wf) >= 1

    rg = regime_breakdown(res.trades)
    assert "window" in rg.columns and len(rg) >= 1
