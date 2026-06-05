"""Per-instrument R-accounting hand check (multi-instrument calibration): one +3R trade per instrument through the real FSM,
with the full cost breakdown and an INDEPENDENT recompute from fills. A correct XAUUSD spec does NOT
imply a correct GBPJPY/WTI spec, so each is verified separately.
"""
from __future__ import annotations

import pandas as pd

from mtf_smc.engine.costs import CostModel
from mtf_smc.engine.fills import Bar
from mtf_smc.engine.trade import Position
from mtf_smc.reporting.explain import explain_trade
from mtf_smc.risk.instrument import INSTRUMENTS
from mtf_smc.risk.sizing import position_size

# (entry, stop) with a clean, round stop distance per instrument.
CASES = {
    "XAUUSD": (2000.0, 1990.0),    # 10.00 distance
    "EURUSD": (1.10000, 1.09500),  # 0.00500 (50 pip)
    "GBPUSD": (1.30000, 1.29500),  # 0.00500 (50 pip)
    "GBPJPY": (150.000, 149.500),  # 0.500 (50 pip)
    "WTIUSD": (70.00, 69.00),      # 1.00 distance
}
TS0 = pd.Timestamp("2020-06-01 12:00", tz="UTC")
TS1 = pd.Timestamp("2020-06-01 13:00", tz="UTC")


def main() -> None:
    for sym, (entry, stop) in CASES.items():
        inst = INSTRUMENTS[sym]
        cost = CostModel(inst)
        dist = entry - stop
        lots = position_size(100_000, 0.01, entry, stop, inst)
        pos = Position("long", entry, lots, stop, "fixed_3R", None, TS0, cost, be_at_2R=False)
        closed = pos.on_bar(Bar(entry, entry + 4 * dist, entry, entry + 3.5 * dist), TS1)
        print("=" * 92)
        print(f"{sym}  quote={inst.quote_currency}  mpu=${inst.money_per_price_unit_per_lot:g}/pt/lot  "
              f"pip=${inst.pip_value_per_lot:g}/lot  spread={inst.base_spread_price:g}  "
              f"comm/side=${inst.commission_per_lot_per_side:g}")
        print(explain_trade(closed, cost))
        stop_pos = Position("long", entry, lots, stop, "fixed_3R", None, TS0, cost, be_at_2R=False)
        stopped = stop_pos.on_bar(Bar(entry, entry, stop, stop), TS1)   # clean -1R stop-out
        print(f"  [-1R stop-out] R={stopped.realized_R:+.4f}  "
              f"slippage=${stopped.cost_slippage:,.2f} "
              f"({stopped.cost_slippage / stopped.initial_risk_money:.3f}R)  "
              f"reason={stopped.exit_reason}")
        print()


if __name__ == "__main__":
    main()
