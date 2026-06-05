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
    base_slippage_price: float = 0.05    # market slippage per side, PRICE units (gold default; ~0.5 pip)
    stop_slippage_price: float = 0.05    # stop-exit slippage per side, PRICE units (gold gaps on news)
    be_buffer_price: float = 0.02        # breakeven-stop buffer past entry, PRICE units (~2 ticks)
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

# --------------------------------------------------------------------------- #
# Multi-instrument specs (broker-typical retail placeholders; documented in docs/SPEC_multi_instrument.md §3).
# Each derives money math from tick_value/tick_size; costs are configurable and disclosed in reports.
# NOTE: every R is mostly invariant to the exact money-per-price-unit (it cancels between win and
# stop) -- only the cost-to-R ratio depends on it -- which is why JPY-pair / commodity money math
# need only be representative, not tick-perfect.
# --------------------------------------------------------------------------- #

# EUR/USD -- 5-decimal major: 100k/lot, pip 0.0001 = $10/lot, $1 move = $100k/lot.
EURUSD = InstrumentSpec(
    symbol="EURUSD",
    pip_size=0.0001, tick_size=0.00001, tick_value=1.0, contract_size=100_000,
    commission_per_lot_per_side=3.5,   # $7 round-turn / lot (ECN)
    swap_long_per_lot=-0.5, swap_short_per_lot=-0.1,
    base_spread_price=0.00006,         # ~0.6 pip
    base_slippage_price=0.00005, stop_slippage_price=0.00005,  # 0.5 pip per side
    be_buffer_price=0.00002,           # ~2 ticks
    quote_currency="USD",
)

# GBP/USD -- 5-decimal major (slightly wider spread than EUR/USD).
GBPUSD = InstrumentSpec(
    symbol="GBPUSD",
    pip_size=0.0001, tick_size=0.00001, tick_value=1.0, contract_size=100_000,
    commission_per_lot_per_side=3.5,
    swap_long_per_lot=-0.7, swap_short_per_lot=-0.2,
    base_spread_price=0.00009,         # ~0.9 pip
    base_slippage_price=0.00005, stop_slippage_price=0.00005,  # 0.5 pip per side
    be_buffer_price=0.00002,           # ~2 ticks
    quote_currency="USD",
)

# GBP/JPY -- 3-decimal JPY cross: pip 0.01; $1-yen move ~= 100k JPY / USDJPY(~120) ~= $833/lot.
# tick_value 0.833 with tick_size 0.001 => money-per-price-unit ~= 833 (pip ~= $8.3/lot). Representative
# fixed USDJPY (it ranged ~100-150 over 2015-2023); R is mpu-invariant except in the cost ratio.
GBPJPY = InstrumentSpec(
    symbol="GBPJPY",
    pip_size=0.01, tick_size=0.001, tick_value=0.833, contract_size=100_000,
    commission_per_lot_per_side=3.5,
    swap_long_per_lot=1.0, swap_short_per_lot=-3.5,   # GBP>JPY rates => positive long carry
    base_spread_price=0.015,           # ~1.5 pip
    base_slippage_price=0.005, stop_slippage_price=0.005,  # 0.5 pip per side
    be_buffer_price=0.002,             # ~2 ticks
    quote_currency="JPY",
)

# WTI crude CFD -- 2-decimal: 1 lot = 1,000 barrels; $1 move = $1,000/lot; tick 0.01 = $10/lot.
# Spread-only (no commission), typical for retail crude CFDs.
WTIUSD = InstrumentSpec(
    symbol="WTIUSD",
    pip_size=0.01, tick_size=0.01, tick_value=10.0, contract_size=1_000,
    commission_per_lot_per_side=0.0,
    swap_long_per_lot=-3.0, swap_short_per_lot=-1.0,  # CFD overnight financing (placeholder)
    base_spread_price=0.04,            # ~4 cents
    base_slippage_price=0.005, stop_slippage_price=0.005,  # 0.5 pip (half-cent) per side
    be_buffer_price=0.02,              # ~2 ticks
    quote_currency="USD",
)

INSTRUMENTS = {s.symbol: s for s in (XAUUSD, EURUSD, GBPUSD, GBPJPY, WTIUSD)}


def get_instrument(symbol: str) -> InstrumentSpec:
    if symbol not in INSTRUMENTS:
        raise KeyError(f"No InstrumentSpec for {symbol!r}; have {sorted(INSTRUMENTS)}")
    return INSTRUMENTS[symbol]
