"""Per-instrument money math + R-accounting (multi-instrument calibration): each spec verified independently."""
from __future__ import annotations

import pandas as pd
import pytest

from mtf_smc.engine.costs import CostModel
from mtf_smc.engine.fills import Bar
from mtf_smc.engine.trade import Position
from mtf_smc.reporting.explain import independent_net_and_R
from mtf_smc.risk.instrument import INSTRUMENTS, get_instrument
from mtf_smc.risk.sizing import initial_risk_money, position_size

# expected money-per-price-unit-per-lot, pip value, and a clean (entry, stop)
EXPECT = {
    "XAUUSD": (100.0, 10.0, 2000.0, 1990.0),
    "EURUSD": (100_000.0, 10.0, 1.10000, 1.09500),
    "GBPUSD": (100_000.0, 10.0, 1.30000, 1.29500),
    "GBPJPY": (833.0, 8.33, 150.000, 149.500),
    "WTIUSD": (1_000.0, 10.0, 70.00, 69.00),
}
TS0 = pd.Timestamp("2020-06-01 12:00", tz="UTC")
TS1 = pd.Timestamp("2020-06-01 13:00", tz="UTC")
NO = {"slippage_per_side": 0.0, "stop_slippage_per_side": 0.0,
      "apply_spread": False, "apply_commission": False, "apply_swap": False}


@pytest.mark.parametrize("sym", list(EXPECT))
def test_instrument_money_math_and_R(sym):
    inst = get_instrument(sym)
    mpu, pipv, entry, stop = EXPECT[sym]
    assert inst.money_per_price_unit_per_lot == pytest.approx(mpu, rel=1e-3)
    assert inst.pip_value_per_lot == pytest.approx(pipv, rel=1e-3)

    dist = entry - stop
    lots = position_size(100_000, 0.01, entry, stop, inst)
    assert lots > 0
    # sized to ~1% of equity (within lot rounding)
    assert initial_risk_money(entry, stop, lots, inst) == pytest.approx(1000.0, rel=0.03)

    # clean +3R win, no costs -> exactly +3R and net = 3 x risk
    nocost = CostModel(inst, **NO)
    pos = Position("long", entry, lots, stop, "fixed_3R", None, TS0, nocost, be_at_2R=False)
    c = pos.on_bar(Bar(entry, entry + 4 * dist, entry, entry + 3.5 * dist), TS1)
    assert c is not None and c.exit_reason == "tp"
    assert c.realized_R == pytest.approx(3.0)
    assert c.net_money == pytest.approx(3.0 * c.initial_risk_money)

    # with realistic costs, the independent fill-based recompute must match the FSM's net/R
    cost = CostModel(inst)
    pos2 = Position("long", entry, lots, stop, "fixed_3R", None, TS0, cost, be_at_2R=False)
    c2 = pos2.on_bar(Bar(entry, entry + 4 * dist, entry, entry + 3.5 * dist), TS1)
    net_i, r_i = independent_net_and_R(c2, cost)
    assert net_i == pytest.approx(c2.net_money)
    assert r_i == pytest.approx(c2.realized_R)
    assert c2.realized_R < 3.0  # costs reduce it


def test_registry_lookup():
    assert set(INSTRUMENTS) == {"XAUUSD", "EURUSD", "GBPUSD", "GBPJPY", "WTIUSD"}
    with pytest.raises(KeyError):
        get_instrument("NOPE")
