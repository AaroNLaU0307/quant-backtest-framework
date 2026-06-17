"""Merge (M2a): legacy confluence-POI builder — POI is the deep-Fib OTE band, gated by confluence."""
from __future__ import annotations

import pandas as pd

from mtf_smc.strategy.legacy_poi import build_confluence_pois

# Same path as test_legacy_structure: a long BOS impulse leg 9 -> 12 (origin@4, broken@2, confirm@8).
BOS_ROWS = [
    (9.9, 10.0, 9.5, 9.8), (9.8, 10.5, 9.8, 10.2), (10.2, 11.0, 10.0, 10.5), (10.5, 10.5, 9.5, 9.8),
    (9.8, 10.0, 9.0, 9.5), (9.5, 11.6, 9.5, 11.5), (10.5, 12.0, 10.5, 11.8), (11.0, 11.5, 10.8, 11.0),
    (11.0, 11.0, 10.5, 10.8),
]


def _df():
    idx = pd.date_range("2020-01-01", periods=len(BOS_ROWS), freq="h", tz="UTC")
    return pd.DataFrame(BOS_ROWS, columns=["open", "high", "low", "close"], index=idx)


def test_poi_is_the_deep_fib_ote_band():
    df = _df()
    atr = pd.Series(0.3, index=df.index)
    pois = build_confluence_pois(df, "long", atr, swing_lookback=2, min_confluence_score=1)
    assert len(pois) == 1
    p = pois[0]
    assert p.zone_lower == 9.0 and p.zone_upper == 10.5     # OTE = leg[9,12] retraced over [0.5, 1.0]
    assert p.leg_low == 9.0 and p.leg_high == 12.0 and p.protective_level == 9.0
    assert p.created_index == 8
    assert abs(p.ext_tp - (9.0 + 4.236 * 3.0)) < 1e-9       # the 4.236 hybrid-TP anchor
    assert p.contains(10.0) and not p.contains(11.0)


def test_confluence_gate_blocks_unreachable_score():
    df = _df()
    atr = pd.Series(0.3, index=df.index)
    # max score is 3 (deep-Fib + up to 2 PD kinds); requiring 4 can never pass
    assert build_confluence_pois(df, "long", atr, swing_lookback=2, min_confluence_score=4) == []
