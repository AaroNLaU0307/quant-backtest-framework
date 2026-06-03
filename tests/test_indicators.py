"""ATR (Wilder), EMA/Vegas bias, and Fibonacci-leg math."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mtf_smc.indicators.atr import atr_wilder, true_range
from mtf_smc.indicators.ema import ema, vegas_bias
from mtf_smc.indicators.fib import FibLeg


def _df(h, lo, c):
    idx = pd.date_range("2020-01-06", periods=len(h), freq="1min", tz="UTC")
    return pd.DataFrame({"open": c, "high": h, "low": lo, "close": c}, index=idx)


def test_true_range_first_bar_is_high_low():
    df = _df([10, 11], [8, 9], [9, 10])
    tr = true_range(df)
    assert tr.iloc[0] == 2.0  # no prior close -> H-L


def test_atr_wilder_known_values():
    df = _df([10, 11, 12, 14, 13], [8, 9, 10, 12, 11], [9, 10, 11, 13, 12])
    atr = atr_wilder(df, period=3)
    assert np.isnan(atr.iloc[0]) and np.isnan(atr.iloc[1])
    assert atr.iloc[2] == pytest.approx(2.0)            # seed = mean(2,2,2)
    assert atr.iloc[3] == pytest.approx(7.0 / 3.0)       # (2*2 + 3)/3
    assert atr.iloc[4] == pytest.approx((7.0 / 3.0 * 2 + 2) / 3)


def test_ema_constant_series():
    s = pd.Series([5.0] * 6)
    assert (ema(s, 3) == 5.0).all()


def test_vegas_bias_long_short_none():
    ramp = pd.Series(np.arange(1, 41, dtype=float))
    assert vegas_bias(ramp).iloc[-1] == "long"
    drop = pd.Series(np.arange(40, 0, -1, dtype=float))
    assert vegas_bias(drop).iloc[-1] == "short"
    flat = pd.Series([5.0] * 40)
    assert (vegas_bias(flat) == "none").all()


def test_fib_long_zone_and_extension():
    leg = FibLeg("long", low=100.0, high=110.0, low_index=0, high_index=10)
    assert leg.retracement(0.5) == pytest.approx(105.0)
    assert leg.retracement(0.618) == pytest.approx(103.82)
    assert leg.depth(105.0) == pytest.approx(0.5)
    assert leg.normalized_pos(105.0) == pytest.approx(0.5)
    assert leg.in_entry_zone(105.0, 0.5) is True
    assert leg.in_entry_zone(106.0, 0.5) is False     # only 0.4 deep
    assert leg.in_entry_zone(103.0, 0.618) is True    # 0.7 deep
    assert leg.extension(1.618) == pytest.approx(116.18)


def test_fib_short_zone_and_extension():
    leg = FibLeg("short", low=100.0, high=110.0, low_index=10, high_index=0)
    assert leg.retracement(0.5) == pytest.approx(105.0)
    assert leg.depth(105.0) == pytest.approx(0.5)
    assert leg.in_entry_zone(105.0, 0.5) is True
    assert leg.in_entry_zone(104.0, 0.5) is False
    assert leg.extension(1.618) == pytest.approx(93.82)
