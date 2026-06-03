"""Fractal swing detection and confirmed-as-of lookup."""
from __future__ import annotations

import pandas as pd

from mtf_smc.smc.swings import detect_swings, last_confirmed_swing


def _df(h, lo):
    c = [(hh + ll) / 2 for hh, ll in zip(h, lo)]
    idx = pd.date_range("2020-01-06", periods=len(h), freq="1min", tz="UTC")
    return pd.DataFrame({"open": c, "high": h, "low": lo, "close": c}, index=idx)


def test_detect_swings_k1():
    df = _df([10, 12, 11, 13, 12], [9, 11, 8, 9, 10])
    sh, sl = detect_swings(df, lookback=1)
    assert [(s.index, s.price) for s in sh] == [(1, 12.0), (3, 13.0)]
    assert [(s.index, s.price) for s in sl] == [(2, 8.0)]


def test_unique_extreme_required():
    # A flat top (tie) must NOT register as a swing high.
    df = _df([10, 12, 12, 11, 9], [9, 8, 8, 7, 6])
    sh, _ = detect_swings(df, lookback=1)
    assert all(s.index not in (1, 2) for s in sh)


def test_last_confirmed_swing_respects_confirmation_lag():
    df = _df([10, 12, 11, 13, 12], [9, 11, 8, 9, 10])
    sh, _ = detect_swings(df, lookback=1)
    # At i=2, only the swing high at index 1 is confirmed (1 + 1 <= 2).
    assert last_confirmed_swing(sh, 2, 1).index == 1
    # At i=4, the later swing high at index 3 is now confirmed.
    assert last_confirmed_swing(sh, 4, 1).index == 3
    # At i=1, nothing is confirmed yet.
    assert last_confirmed_swing(sh, 1, 1) is None
