"""EMA and the EMA(55)/EMA(144) "Vegas" directional-bias filter (``docs/SPEC.md`` §2.7).

EMAs use ``adjust=False`` so they are a strict causal recursion (truncation-invariant). The bias
is computed on a *closed-bar* close series supplied by the caller (typically the HTF close).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential moving average (recursive, causal)."""
    return series.ewm(span=span, adjust=False).mean()


def vegas_bias(close: pd.Series, fast: int = 55, slow: int = 144) -> pd.Series:
    """Per-bar directional bias.

    ``'long'`` when close is above *both* EMAs, ``'short'`` when below both, else ``'none'``
    (price inside the tunnel ⇒ no trade). Never trade against this bias (the EMA filter only ever
    *removes* trades).
    """
    ef = ema(close, fast)
    es = ema(close, slow)
    bias = np.where(
        (close > ef) & (close > es), "long",
        np.where((close < ef) & (close < es), "short", "none"),
    )
    return pd.Series(bias, index=close.index, name="bias")
