"""Position sizing (fixed-fractional risk) and R-multiple accounting. ``docs/SPEC.md`` §5.

Risk is a fixed fraction of *current* equity per trade (default 1%). Lots are derived from the
stop distance and the instrument's money-per-price-unit, rounded down to the lot step. R is always
measured against the **initial** risk money so realized R is exact across breakeven, scale-outs, and
partial fills.
"""
from __future__ import annotations

from mtf_smc.risk.instrument import InstrumentSpec


def position_size(
    equity: float,
    risk_pct: float,
    entry: float,
    stop: float,
    instrument: InstrumentSpec,
) -> float:
    """Lots sized so that hitting ``stop`` from ``entry`` loses ~``risk_pct`` of ``equity``.

    Returns 0.0 if the stop is non-positive distance or the size rounds below ``min_lot``.
    """
    stop_distance = abs(entry - stop)
    if stop_distance <= 0 or equity <= 0 or risk_pct <= 0:
        return 0.0
    raw = instrument.lots_for_risk(equity * risk_pct, stop_distance)
    return instrument.round_lot(raw)


def initial_risk_money(entry: float, stop: float, lots: float, instrument: InstrumentSpec) -> float:
    """Money lost if ``stop`` is hit from ``entry`` at ``lots`` (the 1R denominator)."""
    return abs(entry - stop) * instrument.money_per_price_unit_per_lot * lots


def r_multiple(realized_money_pnl: float, risk_money: float) -> float:
    """Realized R = net money PnL / initial risk money (NaN if risk is zero)."""
    return realized_money_pnl / risk_money if risk_money > 0 else float("nan")
