"""Merge (M2b): legacy session filter — block new entries during the Asia session (old default).

The old `filters.py` blocks new FX/metal entries inside the Asia window (00:00-08:00 UTC) unless the
instrument is granted the GBPJPY-style exemption. Off-by-default here; `legacy_d1h1m5()` turns it on.
"""
from __future__ import annotations

from dataclasses import replace

import pandas as pd

from mtf_smc.config import StrategyConfig
from mtf_smc.strategy.entries import _asia_blocked


def _ts(hours: float) -> pd.Timestamp:
    return pd.Timestamp("2020-06-01", tz="UTC") + pd.Timedelta(hours=hours)


def test_session_filter_off_by_default():
    c = StrategyConfig()                         # the canonical grid config
    assert not c.legacy_session_filter
    assert not _asia_blocked(_ts(3), c)          # 03:00 UTC, but the filter is off -> not blocked


def test_legacy_preset_blocks_the_asia_window():
    c = StrategyConfig.legacy_d1h1m5()
    assert c.legacy_session_filter
    assert _asia_blocked(_ts(0), c)              # 00:00 UTC -> blocked (window start, inclusive)
    assert _asia_blocked(_ts(7.99), c)           # 07:59 UTC -> blocked
    assert not _asia_blocked(_ts(8), c)          # 08:00 UTC -> open (end exclusive)
    assert not _asia_blocked(_ts(13), c)         # NY session -> open


def test_gbpjpy_style_exemption():
    c = replace(StrategyConfig.legacy_d1h1m5(), legacy_allow_asia_session=True)
    assert not _asia_blocked(_ts(3), c)          # exempt instrument -> not blocked even inside the window
