"""Position sizing, R accounting, and XAUUSD money math."""
from __future__ import annotations

import pytest

from mtf_smc.risk.instrument import XAUUSD, InstrumentSpec
from mtf_smc.risk.sizing import initial_risk_money, position_size, r_multiple


def test_xauusd_money_per_price_unit():
    assert XAUUSD.money_per_price_unit_per_lot == pytest.approx(100.0)  # $1 move = $100/lot
    assert XAUUSD.pip_value_per_lot == pytest.approx(10.0)              # 1 pip ($0.10) = $10/lot


def test_position_size_matches_one_percent_risk():
    # $10k equity, 1% risk = $100; stop 5.0 away -> 100 / (5 * 100) = 0.2 lots.
    lots = position_size(10_000, 0.01, entry=2000.0, stop=1995.0, instrument=XAUUSD)
    assert lots == pytest.approx(0.2)
    # And that size loses exactly the risk budget at the stop.
    assert initial_risk_money(2000.0, 1995.0, lots, XAUUSD) == pytest.approx(100.0)


def test_r_multiple_accounting():
    risk = initial_risk_money(2000.0, 1995.0, 0.2, XAUUSD)        # $100
    win_money = XAUUSD.money_pnl(2000.0, 2015.0, 0.2, "long")      # +15 * 100 * 0.2 = $300
    assert r_multiple(win_money, risk) == pytest.approx(3.0)
    loss_money = XAUUSD.money_pnl(2000.0, 1995.0, 0.2, "long")     # -$100
    assert r_multiple(loss_money, risk) == pytest.approx(-1.0)


def test_round_lot_clamps_below_min_to_zero():
    spec = InstrumentSpec("X", pip_size=0.1, tick_size=0.01, tick_value=1.0, contract_size=100,
                          min_lot=0.01, lot_step=0.01)
    assert spec.round_lot(0.004) == 0.0          # below min
    assert spec.round_lot(0.237) == pytest.approx(0.23)  # floored to step


def test_costs_commission_and_swap():
    assert XAUUSD.commission_round_turn(0.2) == pytest.approx(1.4)          # 2 * 3.5 * 0.2
    assert XAUUSD.swap_for_nights(0.2, "long", 3) == pytest.approx(-3.6)    # -6 * 0.2 * 3
    assert XAUUSD.swap_for_nights(0.2, "short", 0) == pytest.approx(0.0)


def test_position_size_rejects_bad_inputs():
    assert position_size(10_000, 0.01, 2000.0, 2000.0, XAUUSD) == 0.0   # zero stop distance
    assert position_size(0, 0.01, 2000.0, 1995.0, XAUUSD) == 0.0        # no equity
