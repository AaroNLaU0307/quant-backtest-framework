"""The deliberate no-look-ahead tests for the MTF alignment layer.

These are the structural guarantee that a decision at time ``t`` cannot see a higher-timeframe
bar that has not closed by ``t`` — including a truncation-invariance check (future bars do not
change the as-of slice).
"""
from __future__ import annotations

import pandas as pd

from mtf_smc.data.resample import resample_ohlc
from mtf_smc.engine.alignment import align_shift, closed_asof, latest_closed
from mtf_smc.timeframes import tf_duration


def _ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="UTC")


def test_closed_asof_never_returns_future_bar(m1_factory):
    m1 = m1_factory(start="2020-01-06 00:00", periods=600)  # 10 hours
    h1 = resample_ohlc(m1, "H1")
    dur = tf_duration("H1")
    for ts in m1.index[::37]:
        sl = closed_asof(h1, "H1", ts)
        if not sl.empty:
            assert (sl.index + dur <= ts).all()
            assert sl.index[-1] + dur <= ts


def test_closed_asof_truncation_invariant(m1_factory):
    """Deleting future bars must not change the as-of slice (no leakage)."""
    m1 = m1_factory(periods=600)
    h1 = resample_ohlc(m1, "H1")
    ts = h1.index[5] + pd.Timedelta(minutes=30)
    full = closed_asof(h1, "H1", ts)
    truncated = closed_asof(h1.loc[:ts], "H1", ts)
    pd.testing.assert_frame_equal(full, truncated)


def test_align_shift_uses_prior_closed_bar(m1_factory):
    m1 = m1_factory(start="2020-01-06 00:00", periods=600)
    h1 = resample_ohlc(m1, "H1")
    m5 = resample_ohlc(m1, "M5")
    aligned = align_shift(h1[["close"]], m5.index, shift=1)
    # Inside the first H1 bucket [00:00,01:00): no prior closed H1 bar -> NaN.
    assert pd.isna(aligned.loc[_ts("2020-01-06 00:30"), "close"])
    # Inside the 2nd H1 bucket [01:00,02:00): sees bar [00:00,01:00) (closed exactly at 01:00).
    assert aligned.loc[_ts("2020-01-06 01:30"), "close"] == h1["close"].loc[_ts("2020-01-06 00:00")]


def test_latest_closed_picks_just_closed_bar(m1_factory):
    m1 = m1_factory(start="2020-01-06 00:00", periods=600)
    h1 = resample_ohlc(m1, "H1")
    # At exactly 03:00 the bar [02:00,03:00) has just closed and is the latest visible.
    lc = latest_closed(h1, "H1", _ts("2020-01-06 03:00"))
    assert lc is not None and lc.name == _ts("2020-01-06 02:00")
    # One minute earlier, only [01:00,02:00) has closed.
    lc2 = latest_closed(h1, "H1", _ts("2020-01-06 02:59"))
    assert lc2.name == _ts("2020-01-06 01:00")
