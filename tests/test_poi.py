"""POI association to structure events and causal mitigation tracking."""
from __future__ import annotations

import pandas as pd

from mtf_smc.smc.fvg import FVG
from mtf_smc.smc.poi import build_pois, mitigation_index
from mtf_smc.smc.structure import StructureEvent


def _event(index, direction, kind="BOS"):
    ts = pd.Timestamp("2020-01-06", tz="UTC")
    return StructureEvent(index, ts, kind, direction, broken_level=10.0, protective_level=9.0)


def test_build_pois_associates_same_direction_fvg_in_window():
    fvgs = [
        FVG("long", mid_index=1, confirm_index=2, lower=10.0, upper=10.5),
        FVG("short", mid_index=3, confirm_index=4, lower=8.0, upper=8.5),
    ]
    events = [_event(5, "long")]
    pois = build_pois(events, fvgs, assoc_window=12)
    assert len(pois) == 1
    assert pois[0].direction == "long" and pois[0].fvg.confirm_index == 2
    assert (pois[0].lower, pois[0].upper) == (10.0, 10.5)


def test_build_pois_rejects_out_of_window_or_wrong_direction():
    fvgs = [FVG("long", mid_index=1, confirm_index=2, lower=10.0, upper=10.5)]
    # event too far ahead of the FVG (window excludes it), and a wrong-direction event
    assert build_pois([_event(50, "long")], fvgs, assoc_window=12) == []
    assert build_pois([_event(5, "short")], fvgs, assoc_window=12) == []


def _df(lows, highs):
    c = [11.5] * len(lows)
    idx = pd.date_range("2020-01-06", periods=len(lows), freq="1min", tz="UTC")
    # keep close inside [low, high]
    c = [min(max(11.5, lo), hi) for lo, hi in zip(lows, highs)]
    return pd.DataFrame({"open": c, "high": highs, "low": lows, "close": c}, index=idx)


def test_mitigation_index_first_intersection_and_causal():
    poi = POI_long()
    lows = [11, 11, 11, 11, 11, 11, 11, 10.2, 11, 11]   # only bar 7 dips into [10, 10.5]
    highs = [12] * 10
    df = _df(lows, highs)
    assert mitigation_index(df, poi) == 7
    # Causal: not visible before bar 7; identical once bar 7 is included.
    assert mitigation_index(df.iloc[:7], poi) is None
    assert mitigation_index(df.iloc[:8], poi) == 7


def POI_long():
    from mtf_smc.smc.poi import POI
    return POI("long", "BOS", event_index=5, fvg=FVG("long", 1, 2, lower=10.0, upper=10.5))
