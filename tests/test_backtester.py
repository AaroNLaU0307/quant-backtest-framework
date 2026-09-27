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


def test_fill_is_resolved_before_close_invalidation():
    # Bar 0 trades down through the long limit 2000 (intrabar) and only then closes at 1989, below
    # the invalidation 1995. The fill happened before that close was known, so the trade must exist
    # (it then stops out on bar 1); cancelling it on bar 0's close would drop a likely loser.
    m1 = _m1([(2001, 2002, 1988, 1989),
              (1989, 1990, 1980, 1982)])
    s = _setup(m1, entry=2000.0, stop=1985.0, invalidation=1995.0)
    trades, _, final = simulate(m1, [s], StrategyConfig(), XAUUSD, NOCOST)
    assert len(trades) == 1
    assert trades[0].entry_ts == m1.index[0]
    assert trades[0].exit_reason == "stop" and trades[0].realized_R == pytest.approx(-1.0)
    assert final < 100_000.0


def test_close_invalidation_cancels_untouched_order():
    # Bar 0 never reaches the limit 99 and closes below the invalidation 99.5 -> cancelled, so the
    # later touch of 99 on bar 1 must not fill.
    m1 = _m1([(100, 100.4, 99.2, 99.3),
              (99.3, 99.4, 98.9, 99.0)])
    s = _setup(m1, entry=99.0, stop=98.0, invalidation=99.5)
    trades, _, final = simulate(m1, [s], StrategyConfig(), XAUUSD, NOCOST)
    assert trades == [] and final == pytest.approx(100_000.0)


def test_stop_inside_fill_bar_is_a_stop_out():
    # Bar 0 fills the long limit 100 AND trades through the stop 99; bar 1 then rallies through the
    # 3R target (103). The fill bar's high/low order is unknown, so the conservative reading is a
    # stop-out on the fill bar, not a +3R take-profit on the next bar.
    m1 = _m1([(100.5, 100.6, 98.5, 99.5),
              (99.5, 104.0, 99.4, 103.5)])
    trades, eq, final = simulate(m1, [_setup(m1)], StrategyConfig(), XAUUSD, NOCOST)
    assert len(trades) == 1
    t = trades[0]
    assert t.exit_reason == "stop" and t.exit_ts == m1.index[0]
    assert t.realized_R == pytest.approx(-1.0)
    assert final == pytest.approx(99_000.0) and eq.iloc[-1] == pytest.approx(99_000.0)


def test_one_position_per_direction():
    m1 = _m1([(100, 100.2, 99.9, 100.1),    # bar0: first long fills
              (100.1, 100.3, 100.0, 100.2),  # bar1: second long would activate -> ignored (one open)
              (100.2, 103.2, 100.1, 103.0)])  # bar2: first hits +3R
    s1 = _setup(m1, decided_i=0)
    s2 = _setup(m1, decided_i=1)
    trades, _, _ = simulate(m1, [s1, s2], StrategyConfig(be_at_2R=True), XAUUSD, NOCOST)
    assert len(trades) == 1                # the second was suppressed while one was open
