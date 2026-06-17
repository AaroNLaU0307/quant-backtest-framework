"""Merge (M2a): legacy M5 trigger — FVG AND (MSS OR CB/DB), with the FVG hard gate."""
from __future__ import annotations

import pandas as pd

from mtf_smc.strategy.legacy_trigger import detect_legacy_triggers

# Same path as the MSS test: a long MSS close-break at index 7 (broken 11, protective 9); this path
# contains no displacement-FVG, so the FVG gate decides whether a trigger survives.
MSS_ROWS = [
    (10.2, 10.5, 10.0, 10.2), (10.2, 10.4, 9.8, 10.0), (10.0, 10.2, 9.0, 9.5), (9.5, 10.6, 9.5, 10.0),
    (10.0, 11.0, 10.0, 10.5), (10.5, 10.8, 9.9, 10.2), (10.2, 10.9, 10.1, 10.5), (10.5, 11.5, 10.5, 11.3),
    (11.3, 11.4, 10.6, 11.0), (11.0, 11.0, 10.5, 10.8),
]


def _df():
    idx = pd.date_range("2020-01-01", periods=len(MSS_ROWS), freq="5min", tz="UTC")
    return pd.DataFrame(MSS_ROWS, columns=["open", "high", "low", "close"], index=idx)


def test_mss_trigger_without_fvg_gate():
    df = _df()
    atr = pd.Series(0.5, index=df.index)
    trig = detect_legacy_triggers(df, "long", atr, swing_lookback=2,
                                  structure_confirm_mode="mss_only", require_fvg=False)
    assert len(trig) == 1
    t = trig[0]
    assert t.break_index == 7 and t.kind == "mss"
    assert t.broken_level == 11.0 and t.protective_swing == 9.0


def test_fvg_hard_gate_blocks_when_no_displacement_fvg():
    df = _df()
    atr = pd.Series(0.5, index=df.index)
    assert detect_legacy_triggers(df, "long", atr, swing_lookback=2,
                                  structure_confirm_mode="mss_only", require_fvg=True) == []
