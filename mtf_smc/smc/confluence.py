"""Order-Block / Breaker PD-arrays + confluence scoring — ported from the published single-instrument
repo's POI engine (`smc_mtf/poi.py`, sourced from its local working tree), translated to English.

**OFF-BY-DEFAULT ablation machinery** for reproducing the old strategy on this engine
(`docs/MERGE_PLAN.md`, phase M2a). The pre-registered 42-config grid uses the lean FVG-POI
(`smc/poi.py`) and never imports this module, so the grid stays bit-identical. Used only by the
legacy entry path built in later M2 increments.

A *PD array* is a price band of institutional interest: an **order block** (last opposing-close candle
before the impulse), a **breaker** (an opposing OB flipped trend-ward by the break), or an **FVG**. The
old strategy's POI is the deep-Fibonacci (OTE) retracement band; PD arrays that overlap it (or sit
within an ATR distance of it) supply *confluence* — the POI is actionable only at a minimum score.
All detection is causal: a PD array is usable only from its formation bar onward, and mitigation is
evaluated on closed bars up to a given index.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd


class PDKind(str, Enum):
    OB = "ob"
    BREAKER = "breaker"
    FVG = "fvg"


@dataclass(frozen=True)
class PDArray:
    kind: PDKind
    direction: str          # 'long' | 'short'
    upper: float
    lower: float
    formed_index: int       # bar at which it is first knowable

    @property
    def midpoint(self) -> float:
        return 0.5 * (self.upper + self.lower)

    @property
    def zone(self) -> Tuple[float, float]:
        return (self.lower, self.upper)


def find_order_block(df: pd.DataFrame, origin_index: int, direction: str,
                     use_wick: bool = False) -> Optional[PDArray]:
    """Last opposing-close candle before the impulse origin.

    Long  -> last bearish candle, zone ``[low, open]`` (``[low, high]`` if ``use_wick``).
    Short -> last bullish candle, zone ``[open, high]`` (``[low, high]`` if ``use_wick``).
    """
    o = df["open"].to_numpy(); h = df["high"].to_numpy()
    lo = df["low"].to_numpy(); c = df["close"].to_numpy()
    start = min(origin_index, len(df) - 1)
    for j in range(start, -1, -1):
        if direction == "long" and c[j] < o[j]:                       # bearish candle
            upper = float(h[j]) if use_wick else float(o[j])
            return PDArray(PDKind.OB, "long", upper, float(lo[j]), j)
        if direction == "short" and c[j] > o[j]:                      # bullish candle
            lower = float(lo[j]) if use_wick else float(o[j])
            return PDArray(PDKind.OB, "short", float(h[j]), lower, j)
    return None


def find_breaker(df: pd.DataFrame, broken_index: int, direction: str) -> Optional[PDArray]:
    """Opposing order block near the broken level, flipped trend-ward by the break (a failed OB).

    Long breaker = the bullish candle at the broken high (failed supply) -> demand ``[low, close]``;
    short breaker = the bearish candle at the broken low (failed demand) -> supply ``[close, high]``.
    """
    o = df["open"].to_numpy(); h = df["high"].to_numpy()
    lo = df["low"].to_numpy(); c = df["close"].to_numpy()
    start = min(broken_index, len(df) - 1)
    for j in range(start, -1, -1):
        if direction == "long" and c[j] > o[j]:
            return PDArray(PDKind.BREAKER, "long", float(max(o[j], c[j])), float(lo[j]), j)
        if direction == "short" and c[j] < o[j]:
            return PDArray(PDKind.BREAKER, "short", float(h[j]), float(min(o[j], c[j])), j)
    return None


def fvg_as_pd(lower: float, upper: float, direction: str, confirm_index: int) -> PDArray:
    """Wrap an FVG zone as a PD array so it can contribute to the confluence score."""
    return PDArray(PDKind.FVG, direction, float(upper), float(lower), int(confirm_index))


def is_mitigated(df: pd.DataFrame, pd_array: PDArray, upto_index: int) -> bool:
    """Did any bar in ``(formed_index, upto_index]`` trade back into the PD array's zone? (causal)."""
    lo_i = pd_array.formed_index + 1
    hi_i = min(upto_index, len(df) - 1)
    if lo_i > hi_i:
        return False
    seg = df.iloc[lo_i:hi_i + 1]
    inter = (seg["low"].to_numpy() <= pd_array.upper) & (seg["high"].to_numpy() >= pd_array.lower)
    return bool(inter.any())


def zone_overlap_pct(z1: Tuple[float, float], z2: Tuple[float, float]) -> float:
    """Overlap length / narrower-zone width (0 if disjoint or zero-width)."""
    lo1, hi1 = min(z1), max(z1)
    lo2, hi2 = min(z2), max(z2)
    inter = max(0.0, min(hi1, hi2) - max(lo1, lo2))
    w = min(hi1 - lo1, hi2 - lo2)
    return inter / w if w > 0 else 0.0


def confluence_score(fib_zone: Tuple[float, float], pd_arrays: List[PDArray], atr_val: float,
                     overlap_pct: float, atr_dist: float) -> Tuple[int, List[PDArray]]:
    """Score the deep-Fib zone against (unmitigated) PD arrays.

    A factor contributes if it overlaps the fib zone by ``>= overlap_pct`` OR its midpoint is within
    ``atr_dist * ATR`` of the fib-zone midpoint. ``score = min(3, 1 + #distinct contributing kinds)``
    (the deep Fib itself counts as 1). Returns ``(score, contributing_arrays)``.
    """
    fmid = 0.5 * (fib_zone[0] + fib_zone[1])
    dist_thresh = atr_dist * atr_val if np.isfinite(atr_val) else None
    kinds: set = set()
    contributing: List[PDArray] = []
    for a in pd_arrays:
        near = dist_thresh is not None and abs(fmid - a.midpoint) <= dist_thresh
        if zone_overlap_pct(fib_zone, a.zone) >= overlap_pct or near:
            kinds.add(a.kind)
            contributing.append(a)
    return min(3, 1 + len(kinds)), contributing
