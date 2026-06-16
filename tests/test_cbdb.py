"""Merge (M2a): TK-style CB/DB break detection (off-by-default legacy trigger)."""
from __future__ import annotations

import pandas as pd

from mtf_smc.smc.cbdb import detect_cbdb_events

# open, high, low, close — a confirmed swing low at index 3 (low 8.0, body top 8.5), then a first
# close (9.0 at index 6) through the body top, 3 bars later => a Dominant Break.
ROWS = [
    (10.2, 10.5, 10.0, 10.1), (10.0, 10.2, 9.5, 9.6), (9.6, 9.8, 9.0, 9.1), (8.5, 9.0, 8.0, 8.3),
    (8.4, 9.3, 8.4, 9.2), (9.2, 9.5, 8.6, 8.4), (8.4, 9.5, 8.3, 9.0), (9.0, 10.0, 8.9, 9.8),
]


def _df():
    idx = pd.date_range("2020-01-01", periods=len(ROWS), freq="5min", tz="UTC")
    return pd.DataFrame(ROWS, columns=["open", "high", "low", "close"], index=idx)


def test_dominant_break_detected():
    ev = detect_cbdb_events(_df(), "long", swing_lookback=2, cbdb_lookback=12, cbdb_dominant_min=3)
    assert len(ev) == 1
    e = ev[0]
    assert e.kind == "db" and e.index == 6 and e.ib_index == 3
    assert e.break_level == 8.5 and e.protective_level == 8.0


def test_dominant_min_gap_suppresses_db():
    # gap (6-3)=3 < 10 -> no DB; the left-side CB level (9.8) is never closed through in this window
    ev = detect_cbdb_events(_df(), "long", swing_lookback=2, cbdb_lookback=12, cbdb_dominant_min=10)
    assert ev == []
