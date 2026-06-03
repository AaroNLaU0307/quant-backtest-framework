"""ATR — Average True Range with Wilder's smoothing. Strictly causal (no look-ahead).

``docs/SPEC.md`` §2.8 standardizes on Wilder's RMA of True Range (the V2 detector used a plain SMA
of TR; V3 upgrades to Wilder). ATR is NaN until ``period`` TRs exist; the seed is the SMA of the
first ``period`` TRs, then ``ATR[i] = (ATR[i-1]*(period-1) + TR[i]) / period``.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def true_range(df: pd.DataFrame) -> pd.Series:
    """True Range: max(H-L, |H-prevClose|, |L-prevClose|). Row 0 = H-L (no prior close)."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    tr.name = "tr"
    return tr


def atr_wilder(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder's ATR over ``period`` bars (NaN before the seed at index ``period-1``)."""
    if period < 1:
        raise ValueError("period must be >= 1")
    tr = true_range(df).to_numpy(dtype=float)
    n = len(tr)
    out = np.full(n, np.nan)
    if n >= period:
        out[period - 1] = float(np.mean(tr[:period]))
        inv = 1.0 / period
        for i in range(period, n):
            out[i] = (out[i - 1] * (period - 1) + tr[i]) * inv
    return pd.Series(out, index=df.index, name=f"atr{period}")
