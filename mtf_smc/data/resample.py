"""Resample M1 OHLC to higher timeframes with a documented, no-look-ahead-friendly convention.

Each bar is indexed by its **start (open) time**; aggregation ``open=first, high=max, low=min,
close=last``; **no interpolation / no forward-fill**; empty buckets (weekends/holidays) are dropped.

**Session anchor** (``docs/SPEC.md`` §1.2) — applies to **D1 and W1 only**:

* ``'ny_close'`` (default): the gold/FX convention — daily candle opens **17:00 America/New_York**,
  weekly candle opens **Sunday 17:00 NY**, DST-aware (21:00 UTC summer / 22:00 UTC winter). See
  :mod:`mtf_smc.sessions`.
* ``'utc'``: daily = UTC calendar day (00:00), weekly = UTC Monday — the alternative, kept for
  comparison.

Intraday timeframes (H4/H1/M15/M5) are always UTC-binned (anchored to the UTC start-of-day) and are
unaffected by the anchor. Because a bar aggregates only data within its own span, resampling is
*causal*; the "don't read an in-progress bar" guarantee is enforced at consumption time by
:mod:`mtf_smc.engine.alignment`.
"""
from __future__ import annotations

from typing import Dict, Sequence

import pandas as pd

from mtf_smc.sessions import SESSION_ANCHORS, ny_daily_open_labels, ny_weekly_open_labels
from mtf_smc.timeframes import TIMEFRAMES, is_valid_tf, tf_to_pandas_freq

OHLC = ["open", "high", "low", "close"]
_AGG = {"open": "first", "high": "max", "low": "min", "close": "last"}
DEFAULT_ANCHOR = "ny_close"


def _utc_bins(m1: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Fixed-frequency UTC bins (intraday + UTC-anchored D1), left-labelled."""
    return (
        m1[OHLC]
        .resample(tf_to_pandas_freq(tf), label="left", closed="left")
        .agg(_AGG)
        .dropna(how="any", subset=OHLC)
    )


def _group_labels(m1: pd.DataFrame, labels: pd.DatetimeIndex) -> pd.DataFrame:
    """Group OHLC by a per-bar session-open label (used for session-anchored D1/W1)."""
    res = m1[OHLC].groupby(labels, sort=True).agg(_AGG)
    res.index = pd.DatetimeIndex(res.index, name=None)
    return res[OHLC]


def _weekly_utc_monday(m1: pd.DataFrame) -> pd.DataFrame:
    """UTC-anchored weekly bars (Monday 00:00 UTC) for ``anchor='utc'``."""
    idx = m1.index
    week_start = idx.normalize() - pd.to_timedelta(idx.dayofweek, unit="D")
    return _group_labels(m1, week_start)


def resample_ohlc(m1: pd.DataFrame, tf: str, anchor: str = DEFAULT_ANCHOR) -> pd.DataFrame:
    """Resample a UTC M1 OHLC frame to timeframe ``tf`` (bar-start index, OHLC columns)."""
    if not is_valid_tf(tf):
        raise KeyError(f"Unknown timeframe {tf!r}.")
    if anchor not in SESSION_ANCHORS:
        raise ValueError(f"Unknown anchor {anchor!r}; valid: {SESSION_ANCHORS}")
    missing = [c for c in OHLC if c not in m1.columns]
    if missing:
        raise ValueError(f"M1 frame missing columns: {missing}")

    if tf == "M1":
        return m1[OHLC].copy()

    if tf in ("D1", "W1"):
        if anchor == "ny_close":
            labels = ny_daily_open_labels(m1.index) if tf == "D1" else ny_weekly_open_labels(m1.index)
            return _group_labels(m1, labels)
        # anchor == 'utc'
        return _weekly_utc_monday(m1) if tf == "W1" else _utc_bins(m1, tf)

    # Intraday: UTC fixed bins, anchor-independent.
    return _utc_bins(m1, tf)


def resample_all(
    m1: pd.DataFrame, tfs: Sequence[str] = TIMEFRAMES, anchor: str = DEFAULT_ANCHOR
) -> Dict[str, pd.DataFrame]:
    """Resample ``m1`` to every timeframe in ``tfs`` -> ``{tf: DataFrame}``."""
    return {tf: resample_ohlc(m1, tf, anchor=anchor) for tf in tfs}
