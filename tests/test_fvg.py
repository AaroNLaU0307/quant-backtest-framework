"""FVG detection (geometric), entry-edge selection, and the optional ATR size filter."""
from __future__ import annotations

import pandas as pd

from mtf_smc.smc.fvg import detect_fvgs


def _df3(h, lo):
    c = [(hh + ll) / 2 for hh, ll in zip(h, lo)]
    idx = pd.date_range("2020-01-06", periods=len(h), freq="1min", tz="UTC")
    return pd.DataFrame({"open": c, "high": h, "low": lo, "close": c}, index=idx)


def test_bullish_fvg_zone_and_edges():
    df = _df3([10, 12, 13], [9, 11, 10.5])  # low[2]=10.5 > high[0]=10
    fvgs = detect_fvgs(df)
    assert len(fvgs) == 1
    f = fvgs[0]
    assert f.direction == "long" and f.mid_index == 1 and f.confirm_index == 2
    assert (f.lower, f.upper) == (10.0, 10.5)
    assert f.entry_price("near") == 10.5   # bullish: approached from above
    assert f.entry_price("far") == 10.0
    assert f.entry_price("mid") == 10.25


def test_bearish_fvg_zone_and_edges():
    df = _df3([10, 8, 8.5], [9, 7, 7.5])  # high[2]=8.5 < low[0]=9
    fvgs = detect_fvgs(df)
    assert len(fvgs) == 1
    f = fvgs[0]
    assert f.direction == "short"
    assert (f.lower, f.upper) == (8.5, 9.0)
    assert f.entry_price("near") == 8.5    # bearish: approached from below


def test_size_filter_drops_small_gap():
    df = _df3([10, 12, 13], [9, 11, 10.5])  # gap size 0.5
    atr = pd.Series(2.0, index=df.index)
    assert detect_fvgs(df, min_size_atr=1.0, atr=atr) == []   # 0.5 < 1.0*2.0
    assert len(detect_fvgs(df, min_size_atr=0.0)) == 1
