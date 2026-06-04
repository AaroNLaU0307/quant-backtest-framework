"""OHLC normalization: sorting, de-duplication, tz handling, and integrity rejection."""
from __future__ import annotations

import pandas as pd
import pytest

from mtf_smc.data.loader import normalize_ohlc


def test_normalize_sorts_and_dedups():
    idx = pd.DatetimeIndex(
        ["2020-01-01 00:02", "2020-01-01 00:00", "2020-01-01 00:01", "2020-01-01 00:01"],
        tz="UTC",
    )
    df = pd.DataFrame({"open": [1, 2, 3, 4], "high": [1, 2, 3, 4],
                       "low": [1, 2, 3, 4], "close": [1, 2, 3, 4]}, index=idx)
    out = normalize_ohlc(df)
    assert out.index.is_monotonic_increasing
    assert not out.index.duplicated().any()
    assert len(out) == 3


def test_normalize_localizes_naive_index():
    idx = pd.date_range("2020-01-01", periods=3, freq="1min")  # tz-naive
    df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}, index=idx)
    out = normalize_ohlc(df, data_tz="UTC")
    assert str(out.index.tz) == "UTC"


def test_normalize_rejects_inconsistent_ohlc():
    idx = pd.date_range("2020-01-01", periods=2, freq="1min", tz="UTC")
    df = pd.DataFrame({"open": [1.0, 1.0], "high": [0.5, 1.0],  # high < low/open
                       "low": [1.0, 1.0], "close": [1.0, 1.0]}, index=idx)
    with pytest.raises(ValueError):
        normalize_ohlc(df)


def test_normalize_requires_all_ohlc_columns():
    idx = pd.date_range("2020-01-01", periods=2, freq="1min", tz="UTC")
    df = pd.DataFrame({"open": [1.0, 1.0], "high": [1.0, 1.0], "close": [1.0, 1.0]}, index=idx)
    with pytest.raises(ValueError):
        normalize_ohlc(df)


def test_read_mt_csv_parses_and_localizes_est():
    import io

    from mtf_smc.data.loader import EST_FIXED, read_mt_csv

    data = ("2024.01.01,18:00,2062.598,2064.525,2062.405,2064.235,0\n"
            "2024.01.01,18:01,2063.795,2064.135,2063.435,2064.125,0\n")
    df = read_mt_csv(io.StringIO(data))
    assert list(df.columns) == ["open", "high", "low", "close"]
    assert df.index[0] == pd.Timestamp("2024-01-01 18:00")        # naive EST wall-clock
    assert df["high"].iloc[0] == 2064.525
    utc = df.index.tz_localize(EST_FIXED).tz_convert("UTC")        # 18:00 EST == 23:00 UTC
    assert utc[0] == pd.Timestamp("2024-01-01 23:00", tz="UTC")
