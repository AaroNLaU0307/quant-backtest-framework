"""BOS / CHoCH structure machine on a crafted up-then-reverse path."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from mtf_smc.smc.structure import detect_structure


def _df_from_close(closes):
    h = [c + 0.5 for c in closes]
    lo = [c - 0.5 for c in closes]
    idx = pd.date_range("2020-01-06", periods=len(closes), freq="1min", tz="UTC")
    return pd.DataFrame({"open": closes, "high": h, "low": lo, "close": closes}, index=idx)


def test_bos_then_choch():
    # Up-move makes higher highs (bullish BOS), then a lower-low break flips to CHoCH short.
    df = _df_from_close([100, 101, 100.5, 102, 101.5, 100, 101, 99])
    events = detect_structure(df, lookback=1)
    assert len(events) == 2

    bos = events[0]
    assert bos.kind == "BOS" and bos.direction == "long" and bos.index == 3
    assert bos.broken_level == pytest.approx(101.5)

    choch = events[1]
    assert choch.kind == "CHoCH" and choch.direction == "short" and choch.index == 7
    assert choch.broken_level == pytest.approx(99.5)
    assert math.isfinite(choch.protective_level)   # opposing confirmed swing high
