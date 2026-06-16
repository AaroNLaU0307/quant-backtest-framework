"""Merge (M2a): ported OB/Breaker PD-arrays + confluence scoring (off-by-default legacy machinery)."""
from __future__ import annotations

import pandas as pd
import pytest

from mtf_smc.smc.confluence import (
    PDArray, PDKind, confluence_score, find_breaker, find_order_block, fvg_as_pd,
    is_mitigated, zone_overlap_pct,
)


def _df(rows):
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"])


def test_order_block_long_body_and_wick():
    df = _df([(10.0, 10.5, 9.0, 9.5), (9.5, 11.0, 9.4, 10.8)])   # bearish then bullish impulse
    ob = find_order_block(df, origin_index=1, direction="long", use_wick=False)
    assert ob.kind == PDKind.OB and ob.direction == "long"
    assert ob.zone == (9.0, 10.0) and ob.formed_index == 0       # [low, open]
    assert find_order_block(df, 1, "long", use_wick=True).zone == (9.0, 10.5)   # [low, high]


def test_order_block_short():
    df = _df([(10.0, 11.0, 9.5, 10.8), (10.8, 10.9, 9.0, 9.2)])  # bullish then bearish impulse
    ob = find_order_block(df, 1, "short", use_wick=False)
    assert ob.direction == "short" and ob.zone == (10.0, 11.0)   # [open, high]


def test_breaker_long():
    df = _df([(10.0, 11.0, 9.5, 10.8), (10.8, 11.5, 10.0, 11.2)])
    br = find_breaker(df, broken_index=0, direction="long")
    assert br.kind == PDKind.BREAKER and br.zone == (9.5, 10.8)  # [low, close]


def test_mitigation_is_causal():
    df = _df([(10, 10.5, 9, 9.5), (10.1, 10.5, 10.05, 10.4),
              (10.4, 11, 10.3, 10.9), (10.9, 11, 9.5, 9.8)])
    ob = PDArray(PDKind.OB, "long", 10.0, 9.0, 0)
    assert is_mitigated(df, ob, upto_index=2) is False           # bars 1-2 stay above the zone
    assert is_mitigated(df, ob, upto_index=3) is True            # bar 3 dips back in


def test_zone_overlap():
    assert zone_overlap_pct((9, 10), (9.5, 10.5)) == pytest.approx(0.5)
    assert zone_overlap_pct((9, 10), (11, 12)) == 0.0


def test_confluence_scoring():
    fib = (9.0, 10.0)
    ob = PDArray(PDKind.OB, "long", 10.5, 9.5, 0)                # overlaps fib
    far = fvg_as_pd(20.0, 21.0, "long", 1)                       # far away -> no contribution
    score, contrib = confluence_score(fib, [ob, far], atr_val=1.0, overlap_pct=0.5, atr_dist=0.5)
    assert score == 2 and contrib == [ob]                        # 1 (deep fib) + 1 kind
    br = PDArray(PDKind.BREAKER, "long", 10.2, 9.4, 0)           # also overlaps -> a 2nd kind
    score2, _ = confluence_score(fib, [ob, br], 1.0, 0.5, 0.5)
    assert score2 == 3
