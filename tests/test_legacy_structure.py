"""Merge (M2a): legacy structure layer — BOS legs (HH/LL), MSS, displacement-FVG (off-by-default)."""
from __future__ import annotations

import pandas as pd

from mtf_smc.smc.legacy_structure import (
    detect_bos_legs, detect_displacement_fvgs, detect_mss_breaks,
)


def _df(rows, freq="h"):
    idx = pd.date_range("2020-01-01", periods=len(rows), freq=freq, tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def test_bos_leg_higher_high():
    # swing high @2 (11), swing low @4 (9), higher swing high @6 (12) -> long BOS leg 9->12
    df = _df([
        (9.9, 10.0, 9.5, 9.8), (9.8, 10.5, 9.8, 10.2), (10.2, 11.0, 10.0, 10.5), (10.5, 10.5, 9.5, 9.8),
        (9.8, 10.0, 9.0, 9.5), (9.5, 11.6, 9.5, 11.5), (10.5, 12.0, 10.5, 11.8), (11.0, 11.5, 10.8, 11.0),
        (11.0, 11.0, 10.5, 10.8),
    ])
    legs = detect_bos_legs(df, "long", swing_lookback=2)
    assert len(legs) == 1
    b = legs[0]
    assert b.direction == "long" and b.leg.low == 9.0 and b.leg.high == 12.0
    assert b.broken_level == 11.0 and b.broken_index == 2
    assert b.break_index == 5 and b.origin_index == 4 and b.confirm_index == 8


def test_mss_close_break():
    # swing low @2 (9, confirmed @4), swing high @4 (11, confirmed @6), close breaks 11 at index 7
    df = _df([
        (10.2, 10.5, 10.0, 10.2), (10.2, 10.4, 9.8, 10.0), (10.0, 10.2, 9.0, 9.5), (9.5, 10.6, 9.5, 10.0),
        (10.0, 11.0, 10.0, 10.5), (10.5, 10.8, 9.9, 10.2), (10.2, 10.9, 10.1, 10.5), (10.5, 11.5, 10.5, 11.3),
        (11.3, 11.4, 10.6, 11.0), (11.0, 11.0, 10.5, 10.8),
    ])
    breaks = detect_mss_breaks(df, "long", swing_lookback=2)
    assert breaks == [(7, 11.0, 9.0)]   # (break_index, broken_level, protective_price)


def test_displacement_fvg_gated_by_displacement():
    df = _df([(9.8, 10.0, 9.5, 9.9), (10.0, 11.0, 10.0, 10.9), (10.9, 11.2, 10.5, 11.0)])
    atr = pd.Series([0.5, 0.5, 0.5], index=df.index)
    fvgs = detect_displacement_fvgs(df, "long", atr, fvg_min_atr_mult=0.10,
                                    disp_atr_mult=1.5, disp_body_ratio=0.5)
    assert len(fvgs) == 1
    f = fvgs[0]
    assert f.disp_index == 1 and f.confirm_index == 2 and f.lower == 10.0 and f.upper == 10.5
    # too-strict displacement threshold (range 1.0 < 3*0.5) -> rejected
    assert detect_displacement_fvgs(df, "long", atr, 0.10, 3.0, 0.5) == []
