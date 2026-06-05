"""Trade lifecycle: pending setup -> open position -> closed trade, with exact, *attributed* R.

Per-M1-bar management policy (intrabar, conservative — ``docs/SPEC.md`` §3.4, §6.3-6.4):

1. **Stop first** (worst-case same-bar tie-break): if the bar's range reaches the current stop, the
   remaining position closes at the stop — even if the bar also reached a favourable level.
2. **+2R event** (once): scale out 50% at +2R (``scale_2R_then_HTF``) and/or move the stop to
   breakeven (``be_at_2R``).
3. **Take-profit**: if the bar reaches the TP, the remainder closes there.

**Cost attribution.** PnL is computed at *mid* (reference) prices and costs are subtracted as
explicit line items: spread (half-spread crossed on entry and every exit), slippage (only on
stop/market-stop exits), commission (per side per lot), and swap (per-night placeholder). This is
algebraically identical to using the cost-adjusted fill prices, but lets every trade show *where*
the money went. R is always measured against the **initial** risk money (1R = |entry_fill - stop| x
value x lots), so partials, breakeven, and costs net out exactly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd

from mtf_smc.engine.costs import CostModel
from mtf_smc.engine.fills import Bar, stop_hit, tp_hit

_STOP_REASONS = ("stop", "be_stop")


@dataclass(frozen=True)
class TradeSetup:
    """A pending limit order produced by an entry model."""

    direction: str                      # 'long' | 'short'
    entry: float                        # limit price (chosen FVG / POI edge), a reference/mid level
    initial_stop: float
    tp_mode: str
    htf_target: Optional[float]         # frozen at setup for HTF_level / scale modes
    decided_ts: pd.Timestamp
    expiry_ts: pd.Timestamp
    invalidation: Optional[float] = None
    tag: str = ""


@dataclass(frozen=True)
class Fill:
    ts: pd.Timestamp
    price: float                        # cost-adjusted fill price (for the human-readable log)
    ref: float                          # the reference/mid level the fill was taken at
    lots: float
    reason: str                         # 'entry' | 'scale_2R' | 'tp' | 'stop' | 'be_stop' | 'end'


@dataclass(frozen=True)
class ClosedTrade:
    direction: str
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry_ref: float                    # reference entry (limit level)
    entry_price: float                  # actual entry fill (ref + half-spread)
    lots: float
    initial_stop: float
    r_unit: float                       # 1R in price (|entry_fill - initial_stop|)
    initial_risk_money: float
    gross_money: float                  # mid-price PnL (before costs)
    cost_spread: float                  # >= 0
    cost_slippage: float                # >= 0
    cost_commission: float              # >= 0
    cost_swap: float                    # signed (<= 0 for XAUUSD)
    net_money: float
    realized_R: float
    exit_reason: str
    mae_R: float
    mfe_R: float
    tp_mode: str
    tag: str
    fills: List[Fill] = field(default_factory=list)


class Position:
    """A live position. Feed it consecutive M1 bars via :meth:`on_bar` until it returns a trade."""

    def __init__(
        self,
        direction: str,
        entry_price: float,             # reference/limit price; the fill adds half-spread
        lots: float,
        initial_stop: float,
        tp_mode: str,
        htf_target: Optional[float],
        entry_ts: pd.Timestamp,
        cost: CostModel,
        be_at_2R: bool = True,
        be_buffer: Optional[float] = None,   # None -> per-instrument InstrumentSpec.be_buffer_price
        tag: str = "",
    ) -> None:
        if direction not in ("long", "short"):
            raise ValueError(direction)
        self.direction = direction
        self.sgn = 1.0 if direction == "long" else -1.0
        self.cost = cost
        self.inst = cost.instrument
        self.mpu = self.inst.money_per_price_unit_per_lot
        self.entry_ref = float(entry_price)
        self.entry = float(cost.entry_fill(entry_price, direction))   # actual fill
        self.lots_total = float(lots)
        self.remaining = float(lots)
        self.initial_stop = float(initial_stop)
        self.stop = float(initial_stop)
        self.R_unit = abs(self.entry - self.initial_stop)
        self.tp_mode = tp_mode
        self.htf_target = htf_target
        self.entry_ts = entry_ts
        self.be_at_2R = be_at_2R
        self.be_buffer = self.inst.be_buffer_price if be_buffer is None else float(be_buffer)
        self.tag = tag
        self.initial_risk_money = self.R_unit * self.mpu * self.lots_total
        self.gross_mid = 0.0
        self.cost_spread = cost.half_spread * self.mpu * self.lots_total   # entry-side spread
        self.cost_slippage = 0.0
        self.cost_commission = cost.commission_one_side(self.lots_total)   # entry-side commission
        self.twoR_done = False
        self.scaled = False
        self.be_done = False
        self.mfe_R = 0.0
        self.mae_R = 0.0
        self.fills: List[Fill] = [Fill(entry_ts, self.entry, self.entry_ref, self.lots_total, "entry")]

    # ------------------------------------------------------------------ #
    def _profit(self, price: float) -> float:
        return (price - self.entry) * self.sgn

    def _two_r_price(self) -> float:
        return self.entry + self.sgn * 2.0 * self.R_unit

    def _tp_target(self) -> Optional[float]:
        if self.tp_mode == "fixed_3R":
            return self.entry + self.sgn * 3.0 * self.R_unit
        return self.htf_target

    def _book(self, lots_p: float, exit_ref: float, ts: pd.Timestamp, reason: str) -> None:
        self.gross_mid += (exit_ref - self.entry_ref) * self.sgn * self.mpu * lots_p
        self.cost_spread += self.cost.half_spread * self.mpu * lots_p
        if reason in _STOP_REASONS:
            self.cost_slippage += self.cost.eff_stop_slippage * self.mpu * lots_p
        self.cost_commission += self.cost.commission_one_side(lots_p)
        fill_px = (self.cost.stop_fill(exit_ref, self.direction) if reason in _STOP_REASONS
                   else self.cost.tp_fill(exit_ref, self.direction))
        self.remaining = round(self.remaining - lots_p, 8)
        self.fills.append(Fill(ts, fill_px, exit_ref, lots_p, reason))

    def _finalize(self, exit_ts: pd.Timestamp, exit_reason: str) -> ClosedTrade:
        nights = max(0, (exit_ts.normalize() - self.entry_ts.normalize()).days)
        cost_swap = self.cost.swap(self.lots_total, self.direction, nights)  # signed
        net = self.gross_mid - self.cost_spread - self.cost_slippage - self.cost_commission + cost_swap
        realized_R = net / self.initial_risk_money if self.initial_risk_money > 0 else float("nan")
        return ClosedTrade(
            direction=self.direction, entry_ts=self.entry_ts, exit_ts=exit_ts,
            entry_ref=self.entry_ref, entry_price=self.entry, lots=self.lots_total,
            initial_stop=self.initial_stop, r_unit=self.R_unit,
            initial_risk_money=self.initial_risk_money, gross_money=self.gross_mid,
            cost_spread=self.cost_spread, cost_slippage=self.cost_slippage,
            cost_commission=self.cost_commission, cost_swap=cost_swap, net_money=net,
            realized_R=realized_R, exit_reason=exit_reason, mae_R=self.mae_R, mfe_R=self.mfe_R,
            tp_mode=self.tp_mode, tag=self.tag, fills=list(self.fills),
        )

    # ------------------------------------------------------------------ #
    def on_bar(self, bar: Bar, ts: pd.Timestamp) -> Optional[ClosedTrade]:
        """Advance one M1 bar. Returns a ``ClosedTrade`` when fully closed, else ``None``."""
        if self.R_unit <= 0:
            return self._finalize(ts, "invalid")
        fav = bar.high if self.direction == "long" else bar.low
        adv = bar.low if self.direction == "long" else bar.high
        self.mfe_R = max(self.mfe_R, self._profit(fav) / self.R_unit)
        self.mae_R = min(self.mae_R, self._profit(adv) / self.R_unit)

        # 1) stop (worst-case tie-break)
        if stop_hit(bar, self.direction, self.stop):
            reason = "be_stop" if self.be_done else "stop"
            self._book(self.remaining, self.stop, ts, reason)
            return self._finalize(ts, reason)

        # 2) +2R event: scale-out and/or breakeven
        if not self.twoR_done and self._profit(fav) >= 2.0 * self.R_unit - 1e-9:
            self.twoR_done = True
            if self.tp_mode == "scale_2R_then_HTF" and not self.scaled:
                half = self.inst.round_lot(self.lots_total * 0.5)
                if 0 < half < self.remaining:
                    self._book(half, self._two_r_price(), ts, "scale_2R")
                    self.scaled = True
            if self.be_at_2R:
                self.stop = self.entry + self.sgn * self.be_buffer
                self.be_done = True

        # 3) take-profit
        tp = self._tp_target()
        if tp is not None and tp_hit(bar, self.direction, tp):
            self._book(self.remaining, tp, ts, "tp")
            return self._finalize(ts, "tp")

        return None

    def force_close(self, ts: pd.Timestamp, price: float, reason: str = "end") -> ClosedTrade:
        """Close the remainder at ``price`` (end-of-data mark-out); charges spread+commission, no slippage."""
        self._book(self.remaining, float(price), ts, reason)
        return self._finalize(ts, reason)
