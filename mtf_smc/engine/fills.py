"""Intrabar fill-resolution primitives (stepping M1 within higher-TF bars). ``docs/SPEC.md`` §6.3-6.4.

We never assume the order of a bar's high/low. A resting limit fills only if an M1 bar trades
*through* its level. When a single bar would hit both stop and take-profit, a conservative tie-break
(default ``'stop_first'`` / worst case) decides; the optimistic ``'tp_first'`` variant is reported
as a sensitivity. These are pure primitives; the trade FSM and event loop compose them over the M1
path of each higher-TF bar.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class Bar:
    open: float
    high: float
    low: float
    close: float


def limit_filled_on_bar(bar: Bar, limit_price: float) -> bool:
    """A resting limit at ``limit_price`` fills iff the bar trades through it."""
    return bar.low <= limit_price <= bar.high


def stop_hit(bar: Bar, direction: str, stop: float) -> bool:
    """Long stop (below) hit when low reaches it; short stop (above) when high reaches it."""
    return bar.low <= stop if direction == "long" else bar.high >= stop


def tp_hit(bar: Bar, direction: str, tp: float) -> bool:
    """Long TP (above) hit when high reaches it; short TP (below) when low reaches it."""
    return bar.high >= tp if direction == "long" else bar.low <= tp


def resolve_exit_on_bar(
    bar: Bar,
    direction: str,
    stop: Optional[float],
    tp: Optional[float],
    tie_break: str = "stop_first",
) -> Optional[Tuple[str, float]]:
    """Resolve a possible exit on one bar.

    Returns ``(reason, level)`` with ``reason`` in ``{'stop', 'tp'}``, or ``None`` if neither is
    touched. If both are touched within the bar, ``tie_break`` decides (default worst-case stop).
    """
    s = stop is not None and stop_hit(bar, direction, stop)
    t = tp is not None and tp_hit(bar, direction, tp)
    if s and t:
        return ("stop", stop) if tie_break == "stop_first" else ("tp", tp)
    if s:
        return ("stop", stop)
    if t:
        return ("tp", tp)
    return None
