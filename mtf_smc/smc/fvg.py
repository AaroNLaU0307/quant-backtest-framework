"""Fair Value Gaps — 3-candle imbalance (``docs/SPEC.md`` §2.3).

Pure geometric definition (the primitive): a **bullish** FVG when ``low[c+1] > high[c-1]``, a
**bearish** FVG when ``high[c+1] < low[c-1]`` (``c`` = middle/displacement candle). Recorded as the
zone ``[lower, upper]`` and confirmed at the third candle ``c+1``. An optional ATR size filter drops
microscopic gaps; the *displacement* requirement (if any) belongs to POI formation, not here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FVG:
    direction: str       # 'long' (bullish) | 'short' (bearish)
    mid_index: int       # middle (displacement) candle
    confirm_index: int   # third candle; the FVG is known at its close
    lower: float
    upper: float

    @property
    def size(self) -> float:
        return self.upper - self.lower

    @property
    def midpoint(self) -> float:
        return 0.5 * (self.lower + self.upper)

    def entry_price(self, edge: str = "near") -> float:
        """Configurable entry edge (``docs/SPEC.md`` §2.3).

        ``'near'`` = the boundary price touches first on the retracement (bullish: the upper
        boundary, approached from above; bearish: the lower boundary), ``'mid'`` = 50%, ``'far'``
        = the opposite boundary.
        """
        if edge == "mid":
            return self.midpoint
        if self.direction == "long":
            return self.upper if edge == "near" else self.lower
        return self.lower if edge == "near" else self.upper


def detect_fvgs(
    df: pd.DataFrame,
    min_size_atr: float = 0.0,
    atr: Optional[pd.Series] = None,
) -> List[FVG]:
    """Detect all 3-candle FVGs in ``df``.

    If ``min_size_atr > 0`` and ``atr`` is supplied, gaps smaller than ``min_size_atr * ATR[c]``
    (or with NaN ATR at ``c``) are dropped. Otherwise every geometric gap is returned.
    """
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    n = len(df)
    use_filter = min_size_atr > 0 and atr is not None
    a = atr.to_numpy() if use_filter else None
    out: List[FVG] = []
    for c in range(1, n - 1):
        thr = (min_size_atr * a[c]) if use_filter else 0.0
        a_ok = (not use_filter) or (not np.isnan(a[c]))
        # bullish: gap between high[c-1] and low[c+1]
        if low[c + 1] > high[c - 1]:
            lower, upper = float(high[c - 1]), float(low[c + 1])
            if a_ok and (upper - lower) >= thr:
                out.append(FVG("long", c, c + 1, lower, upper))
        # bearish: gap between high[c+1] and low[c-1]
        if high[c + 1] < low[c - 1]:
            lower, upper = float(high[c + 1]), float(low[c - 1])
            if a_ok and (upper - lower) >= thr:
                out.append(FVG("short", c, c + 1, lower, upper))
    return out
