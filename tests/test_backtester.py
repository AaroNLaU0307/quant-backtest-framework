"""Event-loop mechanics: limit fills, expiry, invalidation, stop, and one-per-direction concurrency."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mtf_smc.config import StrategyConfig
from mtf_smc.engine.backtester import simulate
from mtf_smc.engine.costs import CostModel
from mtf_smc.engine.trade import TradeSetup
from mtf_smc.risk.instrument import XAUUSD

NOCOST = CostModel(XAUUSD, slippage_per_side=0.0, stop_slippage_per_side=0.0,
                   apply_spread=False, apply_commission=False, apply_swap=False)


def _m1(rows):
    idx = pd.date_range("2020-06-01 12:00", periods=len(rows), freq="1min", tz="UTC")
    a = np.array(rows, dtype=float)
    return pd.DataFrame({"open": a[:, 0], "high": a[:, 1], "low": a[:, 2], "close": a[:, 3]}, index=idx)


def _setup(m1, direction="long", entry=100.0, stop=99.0, tp_mode="fixed_3R", htf_target=None,
           decided_i=0, expiry_i=-1, invalidation=None):
    return TradeSetup(direction, entry, stop, tp_mode, htf_target,
                      decided_ts=m1.index[decided_i], expiry_ts=m1.index[expiry_i],
                      invalidation=invalidation)


def test_fill_then_3R_win_updates_equity():
    m1 = _m1([(100, 100.2, 99.9, 100.1),     # fills long limit @100
              (100.1, 103.2, 100.0, 103.0)])  # reaches +3R (103)
    trades, eq, final = simulate(m1, [_setup(m1)], StrategyConfig(be_at_2R=True), XAUUSD, NOCOST)
    assert len(trades) == 1 and trades[0].exit_reason == "tp"
    assert trades[0].realized_R == pytest.approx(3.0)
    assert final == pytest.approx(103_000.0)        # 10 lots * +3 * $100 = +$3000 on $100k
    assert eq.iloc[-1] == pytest.approx(103_000.0)


def test_full_stop_loses_1R():
    m1 = _m1([(100, 100.2, 99.9, 100.1), (100, 100.1, 98.9, 99.0)])  # low pierces stop 99
    trades, _, final = simulate(m1, [_setup(m1)], StrategyConfig(), XAUUSD, NOCOST)
    assert len(trades) == 1 and trades[0].exit_reason == "stop"
    assert trades[0].realized_R == pytest.approx(-1.0)
    assert final == pytest.approx(99_000.0)


def test_unfilled_order_expires():
    m1 = _m1([(100, 100.5, 99.5, 100.0)] * 3)
    s = _setup(m1, entry=90.0, stop=89.0, expiry_i=1)   # never trades down to 90
    trades, _, final = simulate(m1, [s], StrategyConfig(), XAUUSD, NOCOST)
    assert trades == [] and final == pytest.approx(100_000.0)


def test_invalidation_cancels_before_fill():
    m1 = _m1([(100, 100.4, 98.9, 99.0)])   # entry 99 is in range, but close 99.0 < invalidation 99.5
    s = _setup(m1, entry=99.0, stop=98.0, invalidation=99.5)
    trades, _, _ = simulate(m1, [s], StrategyConfig(), XAUUSD, NOCOST)
    assert trades == []                    # cancelled by invalidation before filling


def test_one_position_per_direction():
    m1 = _m1([(100, 100.2, 99.9, 100.1),    # bar0: first long fills
              (100.1, 100.3, 100.0, 100.2),  # bar1: second long would activate -> ignored (one open)
              (100.2, 103.2, 100.1, 103.0)])  # bar2: first hits +3R
    s1 = _setup(m1, decided_i=0)
    s2 = _setup(m1, decided_i=1)
    trades, _, _ = simulate(m1, [s1, s2], StrategyConfig(be_at_2R=True), XAUUSD, NOCOST)
    assert len(trades) == 1                # the second was suppressed while one was open
