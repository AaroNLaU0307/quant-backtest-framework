"""Trading-session anchors for higher-timeframe candles. ``docs/SPEC.md`` §1.2.

Gold/FX are conventionally charted on the **17:00 America/New_York close**: the daily candle opens
17:00 NY and the weekly candle opens **Sunday 17:00 NY**. This boundary observes US daylight saving
— 17:00 NY is **21:00 UTC in summer (EDT)** and **22:00 UTC in winter (EST)**.

This is deliberately *distinct* from HistData's raw source timestamps, which are a fixed EST (UTC-5,
no DST) offset handled once in the loader. Here we localize with DST-aware ``America/New_York`` purely
to place the session boundary on the (already-UTC) series.

Each helper returns, for every input UTC timestamp, the **UTC label of the session it belongs to**
(i.e. that candle's open time), so the resampler can group by it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

NY_TZ = "America/New_York"
SESSION_OPEN_HOUR = 17  # 5 pm New York

SESSION_ANCHORS = ("ny_close", "utc")


def _naive_ny(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """UTC index -> tz-naive New-York wall-clock (DST-aware conversion, then drop tz)."""
    return idx.tz_convert(NY_TZ).tz_localize(None)


def _ny_open_to_utc(open_naive: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Localize naive NY 17:00 wall-clock to America/New_York (DST-aware) and convert to UTC.

    17:00 is never in a DST gap (02:00-03:00) or overlap (01:00-02:00), so localization is
    unambiguous; the keyword args are defensive only.
    """
    return open_naive.tz_localize(
        NY_TZ, ambiguous=False, nonexistent="shift_forward"
    ).tz_convert("UTC")


def ny_daily_open_labels(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """UTC label of the 17:00-NY daily session each timestamp belongs to."""
    naive = _naive_ny(idx)
    before = (naive.hour.to_numpy() < SESSION_OPEN_HOUR).astype("int64")
    open_day = naive.normalize() - pd.to_timedelta(before, unit="D")
    return _ny_open_to_utc(open_day + pd.Timedelta(hours=SESSION_OPEN_HOUR))


def ny_weekly_open_labels(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """UTC label of the Sunday-17:00-NY trading week each timestamp belongs to."""
    naive = _naive_ny(idx)
    dow = naive.dayofweek.to_numpy()                       # Mon=0 .. Sun=6
    before = naive.hour.to_numpy() < SESSION_OPEN_HOUR
    # Days back to this week's Sunday-17:00 open: Sunday before 17:00 -> previous Sunday (7);
    # Sunday on/after 17:00 -> this Sunday (0); Mon..Sat -> dow+1.
    daysback = np.where(dow == 6, np.where(before, 7, 0), dow + 1)
    open_day = naive.normalize() - pd.to_timedelta(daysback, unit="D")
    return _ny_open_to_utc(open_day + pd.Timedelta(hours=SESSION_OPEN_HOUR))
