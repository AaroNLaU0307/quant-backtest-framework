"""Intrabar fill primitives and the transaction-cost model."""
from __future__ import annotations

import pytest

from mtf_smc.engine.costs import CostModel, high_slippage_on_stops
from mtf_smc.engine.fills import Bar, limit_filled_on_bar, resolve_exit_on_bar, stop_hit, tp_hit
from mtf_smc.risk.instrument import XAUUSD


# ----------------------------- fills ----------------------------- #
def test_limit_fills_only_when_traded_through():
    bar = Bar(open=2000, high=2002, low=1998, close=2001)
    assert limit_filled_on_bar(bar, 1999.0) is True
    assert limit_filled_on_bar(bar, 1997.0) is False   # below the bar's range


def test_stop_and_tp_hit_directional():
    bar = Bar(2000, 2005, 1995, 2001)
    assert stop_hit(bar, "long", 1996.0) is True        # low reached the long stop
    assert stop_hit(bar, "long", 1994.0) is False
    assert tp_hit(bar, "long", 2004.0) is True
    assert stop_hit(bar, "short", 2004.0) is True       # high reached the short stop
    assert tp_hit(bar, "short", 1996.0) is True


def test_same_bar_tie_break_defaults_to_stop():
    # A long where the bar straddles both stop (1995) and tp (2005).
    bar = Bar(2000, 2006, 1994, 2000)
    assert resolve_exit_on_bar(bar, "long", stop=1995, tp=2005) == ("stop", 1995)
    assert resolve_exit_on_bar(bar, "long", stop=1995, tp=2005, tie_break="tp_first") == ("tp", 2005)


def test_resolve_exit_single_and_none():
    bar = Bar(2000, 2006, 1999, 2004)
    assert resolve_exit_on_bar(bar, "long", stop=1995, tp=2005) == ("tp", 2005)   # only tp
    assert resolve_exit_on_bar(bar, "long", stop=1995, tp=2010) is None           # neither


# ----------------------------- costs ----------------------------- #
def test_cost_fills_cross_spread_and_slippage():
    cm = CostModel(XAUUSD)                       # half-spread = 0.10, stop slip = 0.05
    assert cm.entry_fill(2000.0, "long") == pytest.approx(2000.10)
    assert cm.entry_fill(2000.0, "short") == pytest.approx(1999.90)
    assert cm.stop_fill(1995.0, "long") == pytest.approx(1994.85)   # 1995 - 0.10 - 0.05
    assert cm.tp_fill(2010.0, "long") == pytest.approx(2009.90)     # limit: half-spread only


def test_high_slippage_on_stops_variant():
    cm = high_slippage_on_stops(CostModel(XAUUSD), stop_slippage=0.50)
    assert cm.stop_fill(1995.0, "long") == pytest.approx(1994.40)   # 1995 - 0.10 - 0.50
    assert cm.entry_fill(2000.0, "long") == pytest.approx(2000.10)  # entries unchanged


def test_commission_and_swap_toggles():
    cm = CostModel(XAUUSD)
    assert cm.commission_round_turn(0.2) == pytest.approx(1.4)
    assert cm.swap(0.2, "long", 3) == pytest.approx(-3.6)
    off = CostModel(XAUUSD, apply_commission=False, apply_swap=False)
    assert off.commission_round_turn(0.2) == 0.0
    assert off.swap(0.2, "long", 3) == 0.0
