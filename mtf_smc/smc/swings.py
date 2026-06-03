"""Fractal swing highs/lows with right-confirmation (no repaint). ``docs/SPEC.md`` §2.1.

A swing needs ``lookback`` closed bars on *each* side to confirm, so it is knowable only at
``swing.index + lookback`` — any consumer must respect that via :func:`last_confirmed_swing`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import pandas as pd


@dataclass(frozen=True)
class Swing:
    index: int
    timestamp: pd.Timestamp
    price: float
    kind: str  # 'high' | 'low'


def detect_swings(df: pd.DataFrame, lookback: int = 2) -> Tuple[List[Swing], List[Swing]]:
    """Detect fractal swings.

    Bar ``i`` is a swing high iff ``H[i]`` is the **unique** maximum of ``H[i-k .. i+k]`` (swing
    low symmetric on lows). Returns ``(swing_highs, swing_lows)``, each in ascending index order.
    """
    if lookback < 1:
        raise ValueError("lookback must be >= 1")
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    ts = df.index
    n = len(df)
    k = lookback
    sh: List[Swing] = []
    sl: List[Swing] = []
    for i in range(k, n - k):
        wh = highs[i - k : i + k + 1]
        wl = lows[i - k : i + k + 1]
        if highs[i] == wh.max() and (wh == highs[i]).sum() == 1:
            sh.append(Swing(i, ts[i], float(highs[i]), "high"))
        if lows[i] == wl.min() and (wl == lows[i]).sum() == 1:
            sl.append(Swing(i, ts[i], float(lows[i]), "low"))
    return sh, sl


def last_confirmed_swing(swings: List[Swing], i: int, lookback: int) -> Optional[Swing]:
    """The most recent swing confirmed as of bar ``i`` (i.e. ``swing.index + lookback <= i``).

    Relies on ``swings`` being in ascending index order (as returned by :func:`detect_swings`).
    """
    res: Optional[Swing] = None
    for s in swings:
        if s.index + lookback <= i:
            res = s
        else:
            break
    return res
