"""Human-readable per-trade breakdown + an INDEPENDENT recomputation of net PnL / R.

The independent recheck recomputes net and R straight from the recorded **fill prices** (which embed
spread and slippage) plus commission and swap — a different code path than the FSM's mid-price +
line-item accounting. If the two agree, the R accounting is cross-validated (a self-written unit test
could share a conceptual bug with the FSM; this does not).
"""
from __future__ import annotations

from typing import Tuple

from mtf_smc.engine.costs import CostModel
from mtf_smc.engine.trade import ClosedTrade


def independent_net_and_R(trade: ClosedTrade, cost: CostModel) -> Tuple[float, float]:
    """Recompute (net_money, R) from fill prices + commission + swap, independent of the FSM."""
    mpu = cost.instrument.money_per_price_unit_per_lot
    sgn = 1.0 if trade.direction == "long" else -1.0
    entry_fill = trade.fills[0].price
    pnl_from_fills = sum((f.price - entry_fill) * sgn * mpu * f.lots for f in trade.fills[1:])
    nights = max(0, (trade.exit_ts.normalize() - trade.entry_ts.normalize()).days)
    commission = cost.commission_round_turn(trade.lots)
    swap = cost.swap(trade.lots, trade.direction, nights)
    net = pnl_from_fills - commission + swap
    R = net / trade.initial_risk_money if trade.initial_risk_money > 0 else float("nan")
    return net, R


def explain_trade(trade: ClosedTrade, cost: CostModel) -> str:
    mpu = cost.instrument.money_per_price_unit_per_lot
    sgn = 1.0 if trade.direction == "long" else -1.0
    two_r = trade.entry_price + sgn * 2.0 * trade.r_unit
    tp_desc = (f"{trade.entry_price + sgn * 3.0 * trade.r_unit:.3f}  (fixed 3R)"
               if trade.tp_mode == "fixed_3R" else "HTF level (frozen at entry)")

    L = []
    L.append(f"{trade.direction.upper():<5} [{trade.tag}]  {trade.entry_ts}  ->  {trade.exit_ts}"
             f"   exit={trade.exit_reason}   tp_mode={trade.tp_mode}")
    L.append(f"  ref entry        {trade.entry_ref:>12.3f}")
    L.append(f"  entry fill       {trade.entry_price:>12.3f}   (+half-spread)")
    L.append(f"  initial stop     {trade.initial_stop:>12.3f}")
    L.append(f"  R_unit (1R px)   {trade.r_unit:>12.3f}")
    L.append(f"  +2R / BE trigger {two_r:>12.3f}")
    L.append(f"  TP target        {tp_desc}")
    L.append(f"  size             {trade.lots:>12.2f} lots   (mpu=${mpu:.0f}/pt/lot;  1R=${trade.initial_risk_money:,.2f})")
    L.append(f"  MAE / MFE        {trade.mae_R:>+7.2f}R / {trade.mfe_R:>+.2f}R")
    L.append("  fills:")
    for f in trade.fills:
        sign = "+" if f.reason == "entry" else "-"
        L.append(f"    {f.reason:<9} {f.ts}   {sign}{f.lots:>6.2f} @ {f.price:>10.3f}   (ref {f.ref:.3f})")
    L.append("  PnL attribution:")
    L.append(f"    gross (mid)    {trade.gross_money:>+12,.2f}")
    L.append(f"    spread         {-trade.cost_spread:>+12,.2f}")
    L.append(f"    slippage       {-trade.cost_slippage:>+12,.2f}")
    L.append(f"    commission     {-trade.cost_commission:>+12,.2f}")
    L.append(f"    swap           {trade.cost_swap:>+12,.2f}")
    L.append(f"    {'-' * 28}")
    L.append(f"    NET            {trade.net_money:>+12,.2f}")
    L.append(f"    realized R     {trade.realized_R:>+12.4f}")
    net_i, r_i = independent_net_and_R(trade, cost)
    ok = abs(net_i - trade.net_money) < 1e-6 and abs(r_i - trade.realized_R) < 1e-9
    L.append(f"  INDEPENDENT recheck (from fills): net={net_i:+,.2f}  R={r_i:+.4f}   "
             f"[{'MATCH' if ok else 'MISMATCH'}]")
    return "\n".join(L)
