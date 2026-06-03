"""Instrument specification and money math for XAUUSD (broker-like tick/contract model).

Ported and trimmed to gold from the verified V2 ``instrument.py``. Money conversion goes through
``tick_size``/``tick_value`` so sizing and PnL are unambiguous::

    money_per_price_unit_per_lot = tick_value / tick_size

XAUUSD: 100 oz/lot, ``tick_size=0.01``, ``tick_value=1.0`` ⇒ a $1 price move = $100 / lot;
1 pip = $0.10. Cost/spec values are broker-typical placeholders (configurable; disclosed in every
report) — see ``docs/SPEC.md`` §6.5.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class InstrumentSpec:
    """Single-instrument metadata; all monetary math derives from tick_size/tick_value."""

    symbol: str
    pip_size: float
    tick_size: float
    tick_value: float        # account-currency value of one tick per lot
    contract_size: float     # units per lot (reference)

    min_lot: float = 0.01
    max_lot: float = 100.0
    lot_step: float = 0.01

    commission_per_lot_per_side: float = 0.0
    swap_long_per_lot: float = 0.0       # account currency per lot per night (negative = cost)
    swap_short_per_lot: float = 0.0

    base_spread_price: float = 0.20      # full spread in PRICE units (see SPEC §6.5)
    quote_currency: str = "USD"

    @property
    def money_per_price_unit_per_lot(self) -> float:
        """Account-currency value of a 1.0 price move, per lot ($100 for XAUUSD)."""
        return self.tick_value / self.tick_size

    @property
    def pip_value_per_lot(self) -> float:
        return self.pip_size * self.money_per_price_unit_per_lot

    def money_pnl(self, entry: float, exit_: float, lots: float, direction: str) -> float:
        """Directional money PnL (gross of costs). ``direction`` in {'long','short'}."""
        sign = 1.0 if direction == "long" else -1.0
        return (exit_ - entry) * sign * self.money_per_price_unit_per_lot * lots

    def commission_round_turn(self, lots: float) -> float:
        return 2.0 * self.commission_per_lot_per_side * lots

    def swap_for_nights(self, lots: float, direction: str, nights: int) -> float:
        per = self.swap_long_per_lot if direction == "long" else self.swap_short_per_lot
        return per * lots * max(0, nights)

    def round_lot(self, lots: float) -> float:
        """Round *down* to ``lot_step``, clamp to ``[min_lot, max_lot]`` (0 if below min)."""
        if lots <= 0:
            return 0.0
        stepped = round(math.floor(lots / self.lot_step + 1e-9) * self.lot_step, 8)
        if stepped < self.min_lot:
            return 0.0
        return min(stepped, self.max_lot)

    def lots_for_risk(self, risk_money: float, stop_distance_price: float) -> float:
        """Un-rounded lots so that a move of ``stop_distance_price`` equals ``risk_money``."""
        if stop_distance_price <= 0:
            return 0.0
        denom = stop_distance_price * self.money_per_price_unit_per_lot
        return risk_money / denom if denom > 0 else 0.0

    def round_to_tick(self, price: float) -> float:
        return round(price / self.tick_size) * self.tick_size


# Default XAUUSD spec (broker-typical placeholders; all configurable).
XAUUSD = InstrumentSpec(
    symbol="XAUUSD",
    pip_size=0.1, tick_size=0.01, tick_value=1.0, contract_size=100,
    commission_per_lot_per_side=3.5,   # $7 round-turn / lot
    swap_long_per_lot=-6.0, swap_short_per_lot=-3.0,
    base_spread_price=0.20,            # $0.20 full spread (half per side)
    quote_currency="USD",
)
