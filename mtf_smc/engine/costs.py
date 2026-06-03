"""Transaction-cost model: half-spread per side, slippage (higher on stops), commission, swap.

Raw OHLC carries no spread, so costs are *modelled* and disclosed (``docs/SPEC.md`` §6.5). Every
fill crosses the half-spread adversely; **stop / market-stop exits** additionally incur slippage
(the high-slippage-on-stops sensitivity inflates ``stop_slippage_per_side``); **limit entries and
TP fills** incur no extra slippage (they rest at a chosen price). Commission is charged round-turn;
swap accrues per night held.
"""
from __future__ import annotations

from dataclasses import dataclass

from mtf_smc.risk.instrument import InstrumentSpec


@dataclass(frozen=True)
class CostModel:
    instrument: InstrumentSpec
    slippage_per_side: float = 0.05        # price units ($) for market entries
    stop_slippage_per_side: float = 0.05   # price units ($) for stop exits (gold gaps on news)
    apply_spread: bool = True
    apply_commission: bool = True
    apply_swap: bool = True

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
        slip = self.stop_slippage_per_side
        return self.sell_fill(ref, slip) if direction == "long" else self.buy_fill(ref, slip)

    def tp_fill(self, ref: float, direction: str) -> float:
        """Take-profit (limit) fill: crosses half-spread, no extra slippage."""
        return self.sell_fill(ref) if direction == "long" else self.buy_fill(ref)

    def commission_round_turn(self, lots: float) -> float:
        return self.instrument.commission_round_turn(lots) if self.apply_commission else 0.0

    def swap(self, lots: float, direction: str, nights: int) -> float:
        return self.instrument.swap_for_nights(lots, direction, nights) if self.apply_swap else 0.0


def high_slippage_on_stops(base: CostModel, stop_slippage: float = 0.50) -> CostModel:
    """The SPEC §6.5/§8 sensitivity: only stop exits get a worse fill."""
    return CostModel(
        instrument=base.instrument,
        slippage_per_side=base.slippage_per_side,
        stop_slippage_per_side=stop_slippage,
        apply_spread=base.apply_spread,
        apply_commission=base.apply_commission,
        apply_swap=base.apply_swap,
    )
