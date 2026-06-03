"""Trade lifecycle FSM: R accounting through stop / 3R / scale-out / breakeven, costs, tie-break."""
from __future__ import annotations

import pandas as pd
import pytest

from mtf_smc.engine.costs import CostModel
from mtf_smc.engine.fills import Bar
from mtf_smc.engine.trade import Position
from mtf_smc.risk.instrument import XAUUSD

TS0 = pd.Timestamp("2020-01-06 12:00", tz="UTC")
TS1 = pd.Timestamp("2020-01-06 13:00", tz="UTC")
TS2 = pd.Timestamp("2020-01-06 14:00", tz="UTC")

NOCOST = CostModel(XAUUSD, slippage_per_side=0.0, stop_slippage_per_side=0.0,
                   apply_spread=False, apply_commission=False, apply_swap=False)


def _long(tp_mode="fixed_3R", lots=1.0, htf_target=None, be=False, cost=NOCOST):
    return Position("long", entry_price=2000.0, lots=lots, initial_stop=1990.0,
                    tp_mode=tp_mode, htf_target=htf_target, entry_ts=TS0, cost=cost,
                    be_at_2R=be, be_buffer=0.0)


def test_fixed_3R_win_is_plus_3R():
    pos = _long()
    closed = pos.on_bar(Bar(2000, 2030, 2000, 2025), TS1)   # high reaches 3R (2030)
    assert closed is not None
    assert closed.exit_reason == "tp"
    assert closed.realized_R == pytest.approx(3.0)
    assert closed.mfe_R == pytest.approx(3.0)


def test_full_stop_is_minus_1R():
    pos = _long()
    closed = pos.on_bar(Bar(2000, 2001, 1990, 1992), TS1)   # low reaches the stop
    assert closed is not None and closed.exit_reason == "stop"
    assert closed.realized_R == pytest.approx(-1.0)


def test_breakeven_caps_a_reversal_near_zero():
    pos = _long(be=True)                                    # be_buffer = 0 -> exact breakeven
    assert pos.on_bar(Bar(2000, 2020, 2005, 2018), TS1) is None   # touches +2R -> stop to BE
    assert pos.be_done is True and pos.stop == pytest.approx(2000.0)
    closed = pos.on_bar(Bar(2010, 2012, 1999, 2000), TS2)   # reverses into BE stop
    assert closed is not None and closed.exit_reason == "be_stop"
    assert closed.realized_R == pytest.approx(0.0)


def test_scale_2R_then_htf_averages_to_3R():
    pos = _long(tp_mode="scale_2R_then_HTF", lots=2.0, htf_target=2040.0)  # remainder target = 4R
    assert pos.on_bar(Bar(2000, 2020, 2005, 2018), TS1) is None  # 50% out at +2R, BE armed
    assert pos.scaled is True and pos.remaining == pytest.approx(1.0)
    closed = pos.on_bar(Bar(2030, 2040, 2030, 2039), TS2)        # remainder hits HTF target (+4R)
    assert closed is not None and closed.exit_reason == "tp"
    assert closed.realized_R == pytest.approx(3.0)              # (2R on half + 4R on half) / 1R
    assert len(closed.fills) == 3                               # entry, scale_2R, tp


def test_same_bar_stop_wins_tie_break():
    pos = _long()
    # One bar spans both the stop (1990) and the 3R target (2030): worst case = stop.
    closed = pos.on_bar(Bar(2000, 2031, 1989, 2000), TS1)
    assert closed is not None and closed.exit_reason == "stop"
    assert closed.realized_R == pytest.approx(-1.0)


def test_costs_reduce_realized_R():
    pos = _long(cost=CostModel(XAUUSD))   # default spread/commission on
    closed = pos.on_bar(Bar(2000, 2030, 2000, 2025), TS1)
    # gross 3R minus half-spread on the exit and round-turn commission -> just under 3R.
    assert closed.realized_R == pytest.approx(2.983, abs=1e-3)
    assert closed.net_money < closed.gross_money       # commission subtracted
    assert closed.cost_commission == pytest.approx(7.0)  # 3.5/side * 1 lot * 2 sides


def test_short_3R_win():
    pos = Position("short", entry_price=2000.0, lots=1.0, initial_stop=2010.0,
                   tp_mode="fixed_3R", htf_target=None, entry_ts=TS0, cost=NOCOST)
    closed = pos.on_bar(Bar(2000, 2000, 1970, 1975), TS1)   # low reaches 3R (1970)
    assert closed is not None and closed.exit_reason == "tp"
    assert closed.realized_R == pytest.approx(3.0)
