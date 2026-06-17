"""Merge (M2a foundation): detect_structure carries the impulse-leg bar indices (origin/broken) for
OB/breaker anchoring, without changing the existing fields (the 42-grid stays bit-identical)."""
from __future__ import annotations

import pandas as pd

from mtf_smc.smc.structure import detect_structure

# Swing high at index 2 (high 11.0), swing low at index 5 (low 8.5), then a close (11.5 at index 7)
# breaks above the swing-high level -> a long BOS whose origin = the protective low (5), broken = (2).
ROWS = [
    (9.9, 10.0, 9.5, 9.8), (9.8, 10.5, 9.8, 10.2), (10.2, 11.0, 10.0, 10.5), (10.4, 10.6, 9.5, 9.8),
    (9.8, 10.0, 9.0, 9.5), (9.5, 9.8, 8.5, 9.0), (9.0, 10.5, 9.0, 10.3), (10.3, 11.5, 10.0, 11.5),
]


def test_structure_event_carries_leg_indices():
    idx = pd.date_range("2020-01-01", periods=len(ROWS), freq="h", tz="UTC")
    df = pd.DataFrame(ROWS, columns=["open", "high", "low", "close"], index=idx)
    events = detect_structure(df, lookback=2)
    assert len(events) == 1
    e = events[0]
    assert e.kind == "BOS" and e.direction == "long" and e.index == 7
    assert e.broken_level == 11.0 and e.protective_level == 8.5
    assert e.broken_index == 2 and e.origin_index == 5      # the new leg-anchor fields
