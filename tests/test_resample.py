"""Resampling: left-label, OHLC aggregation, dropped empty buckets, and session anchoring.

Intraday/M1 are UTC-binned and anchor-independent; D1/W1 honour the session anchor
(``'ny_close'`` 17:00 New York, DST-aware, by default; ``'utc'`` as the switchable alternative).
"""
from __future__ import annotations

import pandas as pd

from mtf_smc.data.resample import resample_ohlc


def _ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="UTC")


# --------------------------- intraday (anchor-independent) --------------------------- #
def test_m1_identity(m1_factory):
    m1 = m1_factory(periods=120)
    pd.testing.assert_frame_equal(resample_ohlc(m1, "M1"), m1[["open", "high", "low", "close"]])


def test_h1_aggregation(m1_factory):
    m1 = m1_factory(start="2020-01-06 00:00", periods=360)  # 6 hours
    h1 = resample_ohlc(m1, "H1")
    assert len(h1) == 6
    assert h1.index[0] == _ts("2020-01-06 00:00") and h1.index[1] == _ts("2020-01-06 01:00")
    first = m1.iloc[0:60]
    assert h1["open"].iloc[0] == first["open"].iloc[0]
    assert h1["close"].iloc[0] == first["close"].iloc[-1]
    assert h1["high"].iloc[0] == first["high"].max()
    assert h1["low"].iloc[0] == first["low"].min()


def test_m5_count(m1_factory):
    assert len(resample_ohlc(m1_factory(periods=360), "M5")) == 72


def test_empty_buckets_dropped(m1_factory):
    m1 = m1_factory(start="2020-01-06 00:00", periods=360)
    mask = ~((m1.index >= _ts("2020-01-06 02:00")) & (m1.index < _ts("2020-01-06 03:00")))
    h1 = resample_ohlc(m1[mask], "H1")
    assert _ts("2020-01-06 02:00") not in h1.index
    assert not h1.isna().any().any()
    assert len(h1) == 5


# --------------------------- D1/W1 NY-close anchor (DST-aware) --------------------------- #
def test_d1_w1_ny_close_anchor_and_dst(m1_factory):
    # 20 days from 2021-03-08 — crosses US spring-forward (Sun 2021-03-14 02:00).
    m1 = m1_factory(start="2021-03-08 00:00", periods=20 * 24 * 60)

    d1 = resample_ohlc(m1, "D1", anchor="ny_close")
    ny = d1.index.tz_convert("America/New_York")
    assert (ny.hour == 17).all() and (ny.minute == 0).all()       # every daily open is 17:00 NY
    assert {21, 22} <= set(d1.index.hour)                          # DST-aware: EDT(21:00) & EST(22:00) UTC

    w1 = resample_ohlc(m1, "W1", anchor="ny_close")
    nyw = w1.index.tz_convert("America/New_York")
    assert (nyw.hour == 17).all() and (nyw.dayofweek == 6).all()   # every weekly open is Sunday 17:00 NY


def test_utc_anchor_switch(m1_factory):
    m1 = m1_factory(start="2020-01-06 00:00", periods=60 * 24 * 10)  # 10 days from a Monday
    d1 = resample_ohlc(m1, "D1", anchor="utc")
    assert (d1.index.hour == 0).all() and (d1.index.minute == 0).all()   # UTC calendar days
    assert d1.index[0] == _ts("2020-01-06 00:00")
    w1 = resample_ohlc(m1, "W1", anchor="utc")
    assert (w1.index.dayofweek == 0).all()                                # UTC Monday weeks
    assert w1.index[0] == _ts("2020-01-06 00:00")
