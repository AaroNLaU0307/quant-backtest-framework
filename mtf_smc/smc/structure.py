"""Market structure: BOS (continuation) and CHoCH (reversal). ``docs/SPEC.md`` §2.4-2.5.

A **bullish break** = the first close above the most recent *confirmed* swing high; a **bearish
break** = the first close below the most recent confirmed swing low. Whether a break is BOS or
CHoCH depends on the running structural *bias* set by the previous break:

* break agrees with bias  -> **BOS** (continuation),
* break opposes bias      -> **CHoCH** (reversal), and the bias flips.

The very first break establishes the bias and is labelled **BOS**. Everything uses closed bars and
right-confirmed swings, so detection is causal and non-repainting (proven by truncation-invariance
tests). Higher-level code maps these to the brief's roles: HTF/MTF BOS sets direction; the CHoCH
that ends a pullback inside the POI is the entry trigger.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd

from mtf_smc.smc.swings import Swing, detect_swings


@dataclass(frozen=True)
class StructureEvent:
    index: int
    timestamp: pd.Timestamp
    kind: str        # 'BOS' | 'CHoCH'
    direction: str   # 'long' (bullish break) | 'short' (bearish break)
    broken_level: float
    protective_level: float  # opposing confirmed swing (for stops); NaN if none yet
    origin_index: int = -1   # protective-swing bar = impulse-leg start (OB detection); -1 if none
    broken_index: int = -1   # broken-swing bar (breaker detection); -1 if none


def _confirmed_level_series(swings: List[Swing], n: int, k: int) -> np.ndarray:
    """Step array: at each bar, the price of the most recently *confirmed* swing (NaN before any).

    A swing at index ``j`` is first knowable at ``j + k``; we stamp its price there and forward-fill.
    """
    level = np.full(n, np.nan)
    for s in swings:
        conf = s.index + k
        if conf < n:
            level[conf] = s.price  # later (higher-index) swings overwrite -> "most recent confirmed"
    last = np.nan
    for i in range(n):
        if np.isnan(level[i]):
            level[i] = last
        else:
            last = level[i]
    return level


def _confirmed_index_series(swings: List[Swing], n: int, k: int) -> np.ndarray:
    """As :func:`_confirmed_level_series`, but carries the most-recent confirmed swing's *bar index*
    (sentinel ``-1`` before any) — kept in lockstep with the price series for OB/breaker anchoring."""
    idx = np.full(n, -1, dtype=np.int64)
    for s in swings:
        conf = s.index + k
        if conf < n:
            idx[conf] = s.index
    last = -1
    for i in range(n):
        if idx[i] < 0:
            idx[i] = last
        else:
            last = idx[i]
    return idx


def detect_structure(df: pd.DataFrame, lookback: int = 2) -> List[StructureEvent]:
    """Detect the ordered sequence of BOS/CHoCH events on ``df``."""
    sh, sl = detect_swings(df, lookback)
    n = len(df)
    k = lookback
    closes = df["close"].to_numpy()
    ts = df.index
    hi = _confirmed_level_series(sh, n, k)  # latest confirmed swing-high price per bar
    lo = _confirmed_level_series(sl, n, k)  # latest confirmed swing-low price per bar
    hi_idx = _confirmed_index_series(sh, n, k)   # ...and the swing's bar index (OB/breaker anchoring)
    lo_idx = _confirmed_index_series(sl, n, k)

    events: List[StructureEvent] = []
    bias: Optional[str] = None
    armed_high = armed_low = False
    prev_hi = prev_lo = np.nan

    for i in range(1, n):
        # Re-arm a side whenever its confirmed level changes (a new swing has formed).
        if not np.isnan(hi[i]) and hi[i] != prev_hi:
            armed_high = True
            prev_hi = hi[i]
        if not np.isnan(lo[i]) and lo[i] != prev_lo:
            armed_low = True
            prev_lo = lo[i]

        if armed_high and not np.isnan(hi[i]) and closes[i] > hi[i] and closes[i - 1] <= hi[i]:
            kind = "BOS" if bias in (None, "long") else "CHoCH"
            prot = lo[i] if not np.isnan(lo[i]) else float("nan")
            events.append(StructureEvent(i, ts[i], kind, "long", float(hi[i]), float(prot),
                                         origin_index=int(lo_idx[i]), broken_index=int(hi_idx[i])))
            bias = "long"
            armed_high = False
        elif armed_low and not np.isnan(lo[i]) and closes[i] < lo[i] and closes[i - 1] >= lo[i]:
            kind = "BOS" if bias in (None, "short") else "CHoCH"
            prot = hi[i] if not np.isnan(hi[i]) else float("nan")
            events.append(StructureEvent(i, ts[i], kind, "short", float(lo[i]), float(prot),
                                         origin_index=int(hi_idx[i]), broken_index=int(lo_idx[i])))
            bias = "short"
            armed_low = False

    return events
