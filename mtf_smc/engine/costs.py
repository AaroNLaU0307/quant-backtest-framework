"""Transaction-cost model: half-spread per side, slippage (higher on stops), commission, swap.

Raw OHLC carries no spread, so costs are *modelled* and disclosed (``docs/SPEC.md`` §6.5). Every
fill crosses the half-spread adversely; **stop / market-stop exits** additionally incur slippage
(the high-slippage-on-stops sensitivity inflates ``stop_slippage_per_side``); **limit entries and
TP fills** incur no extra slippage (they rest at a chosen price). Commission is charged round-turn;
swap accrues per night held.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from mtf_smc.risk.instrument import InstrumentSpec


@dataclass(frozen=True)
class CostModel:
    instrument: InstrumentSpec
    # None -> use the per-instrument value from InstrumentSpec (so cost scale follows the instrument,
    # never a gold-sized price on a 5-decimal FX pair). Explicit floats still override (e.g. 0.0).
    slippage_per_side: Optional[float] = None       # market entries (price units)
    stop_slippage_per_side: Optional[float] = None  # stop exits (price units; gaps on news)
    apply_spread: bool = True
    apply_commission: bool = True
    apply_swap: bool = True

    @property
    def eff_slippage(self) -> float:
        """Market slippage per side (price), per-instrument unless explicitly overridden."""
        return (self.instrument.base_slippage_price if self.slippage_per_side is None
                else self.slippage_per_side)

    @property
    def eff_stop_slippage(self) -> float:
        """Stop-exit slippage per side (price), per-instrument unless explicitly overridden."""
        return (self.instrument.stop_slippage_price if self.stop_slippage_per_side is None
                else self.stop_slippage_per_side)

    @property
    def half_spread(self) -> float:
        return (self.instrument.base_spread_price / 2.0) if self.apply_spread else 0.0

    def buy_fill(self, ref: float, slip: float = 0.0) -> float:
        """Price paid to buy (ask side): adverse = higher."""
        return ref + self.half_spread + slip

    def sell_fill(self, ref: float, slip: float = 0.0) -> float:
        """Price received to sell (bid side): adverse = lower."""
        return ref - self.half_spread - slip

    def entry_fill(self, ref: float, direction: str) -> float:
        """Limit-entry fill (crosses half-spread, no extra slippage)."""
        return self.buy_fill(ref) if direction == "long" else self.sell_fill(ref)

    def stop_fill(self, ref: float, direction: str) -> float:
        """Stop-exit fill (half-spread + stop slippage). Long exits by selling, short by buying."""
        slip = self.eff_stop_slippage
        return self.sell_fill(ref, slip) if direction == "long" else self.buy_fill(ref, slip)

    def tp_fill(self, ref: float, direction: str) -> float:
        """Take-profit (limit) fill: crosses half-spread, no extra slippage."""
        return self.sell_fill(ref) if direction == "long" else self.buy_fill(ref)

    def commission_round_turn(self, lots: float) -> float:
        return self.instrument.commission_round_turn(lots) if self.apply_commission else 0.0

    def commission_one_side(self, lots: float) -> float:
        """Commission for a single side (entry or one exit/partial)."""
        return self.instrument.commission_per_lot_per_side * lots if self.apply_commission else 0.0

    def swap(self, lots: float, direction: str, nights: int) -> float:
        return self.instrument.swap_for_nights(lots, direction, nights) if self.apply_swap else 0.0


def high_slippage_on_stops(base: CostModel, mult: float = 10.0) -> CostModel:
    """The SPEC §6.5/§8 sensitivity: only stop exits get a worse fill, ``mult`` x the per-instrument
    stop slippage (gold 0.05 -> 0.50 at the default 10x, and it scales correctly for every instrument
    instead of imposing a gold-sized price)."""
    return CostModel(
        instrument=base.instrument,
        slippage_per_side=base.slippage_per_side,
        stop_slippage_per_side=mult * base.eff_stop_slippage,
        apply_spread=base.apply_spread,
        apply_commission=base.apply_commission,
        apply_swap=base.apply_swap,
    )
