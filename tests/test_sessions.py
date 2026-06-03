"""DST-aware New-York session-anchor labels (the 17:00 boundary)."""
from __future__ import annotations

import pandas as pd

from mtf_smc.sessions import ny_daily_open_labels, ny_weekly_open_labels


def _idx_around_spring_forward() -> pd.DatetimeIndex:
    # Hourly, 2021-03-08 .. 2021-03-28 — spans US spring-forward (Sun 2021-03-14).
    return pd.date_range("2021-03-08", "2021-03-28", freq="1h", tz="UTC")


def test_daily_open_is_always_17_ny_and_dst_aware():
    labels = ny_daily_open_labels(_idx_around_spring_forward())
    ny = labels.tz_convert("America/New_York")
    assert (ny.hour == 17).all() and (ny.minute == 0).all()
    # EST (winter) opens map to 22:00 UTC, EDT (summer) to 21:00 UTC — both present across the DST line.
    hours = set(labels.hour)
    assert 22 in hours and 21 in hours


def test_weekly_open_is_sunday_17_ny():
    labels = ny_weekly_open_labels(_idx_around_spring_forward())
    ny = labels.tz_convert("America/New_York")
    assert (ny.hour == 17).all()
    assert (ny.dayofweek == 6).all()           # Sunday
    assert {21, 22} <= set(labels.hour)        # DST-aware weekly opens too


def test_fall_back_winter_uses_est_22utc():
    # A week fully in winter (EST): 17:00 NY == 22:00 UTC.
    idx = pd.date_range("2021-01-11", "2021-01-15", freq="1h", tz="UTC")  # Mon-Fri, EST
    daily = ny_daily_open_labels(idx)
    assert (daily.hour == 22).all()
