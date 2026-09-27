"""Walk-forward (per-year sequential OOS) and regime breakdowns."""
from __future__ import annotations

import json
import math

import pandas as pd
import pytest

from mtf_smc.config import StrategyConfig
from mtf_smc.engine.backtester import run_backtest
from mtf_smc.robustness.walkforward import (
    oos_period_returns,
    period_sign_test,
    regime_breakdown,
    walk_forward_by_year,
)


def test_walk_forward_and_regime(is_m1):
    res = run_backtest(is_m1.loc["2017-01-01":"2019-12-31"],
                       StrategyConfig(entry_model="direct", htf="D1", tp_mode="fixed_3R"))
    if res.n_trades < 5:
        pytest.skip("too few trades")

    wf = walk_forward_by_year(res.trades)
    assert {"window", "n_trades", "expectancy_R", "ci_lo", "ci_hi", "ci_crosses_zero"}.issubset(wf.columns)
    assert wf["n_trades"].sum() == res.n_trades                 # every trade bucketed once
    assert len(wf) >= 1

    rg = regime_breakdown(res.trades)
    assert "window" in rg.columns and len(rg) >= 1


def _windows(per_period):
    """Rows as written by scripts/run_legacy_walkforward.py: one per (symbol, calendar OOS window)."""
    rows = [{"symbol": sym, "oos_start": period, "oos_R_json": json.dumps(r)}
            for period, by_sym in per_period.items() for sym, r in by_sym.items()]
    return pd.DataFrame(rows)


def test_period_sign_test_pairs_instruments_per_calendar_period():
    # 12 periods x 2 instruments. XAU is negative in 11 periods, EUR in 8. In period 1, XAU -0.5 and
    # EUR +2.0 pool to a positive mean, so the period counts once, as positive.
    per = {f"2016-{m:02d}-01": {"XAUUSD": [-0.5] if m != 12 else [0.4],
                                "EURUSD": [2.0] if m == 1 else ([-0.2, -0.4] if m <= 9 else [0.3])}
           for m in range(1, 13)}
    df = _windows(per)
    pooled = oos_period_returns(df)
    assert list(pooled) == sorted(per) and pooled["2016-01-01"].tolist() == [-0.5, 2.0]
    out = period_sign_test(df)
    signs = [-1 if sum(v["XAUUSD"] + v["EURUSD"]) / len(v["XAUUSD"] + v["EURUSD"]) < 0 else 1
             for v in per.values()]
    n_neg = signs.count(-1)
    assert out["n_periods"] == 12 and out["n_negative"] == n_neg
    assert out["p_value"] == pytest.approx(sum(math.comb(12, k) for k in range(n_neg, 13)) / 2 ** 12)
    # 24 instrument-windows as independent coins would give a much smaller (overconfident) p
    n_neg_w = sum(sum(r) / len(r) < 0 for v in per.values() for r in v.values())
    p_windows = sum(math.comb(24, k) for k in range(n_neg_w, 25)) / 2 ** 24
    assert p_windows < out["p_value"]


def test_period_sign_test_drops_empty_and_tied_periods():
    per = {"2016-07-01": {"XAUUSD": [], "EURUSD": []},                  # no trades
           "2017-01-01": {"XAUUSD": [1.0], "EURUSD": [-1.0]},           # tie (mean 0)
           "2017-07-01": {"XAUUSD": [-1.0], "EURUSD": [-0.2]}}
    out = period_sign_test(_windows(per))
    assert out["n_periods"] == 1 and out["n_negative"] == 1 and out["p_value"] == pytest.approx(0.5)

