"""Truncation-invariance of the :class:`TFView` as-of lookups (the composite decision path).

For a lookup made at time ``ts``, the answer computed from the full M1 series must equal the answer
computed from only the M1 bars that had closed by ``ts`` (``m1.index < ts``). The prefix may end in a
partial higher-timeframe bar; a causal lookup never reads it. Checked at many cut points on a seeded
synthetic walk, for the take-profit target (ordinary and major swings), the HTF bias, the POI lookup
and the structure-with-FVG lookup.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mtf_smc.config import StrategyConfig
from mtf_smc.strategy.context import build_tf_view

CFG = StrategyConfig()          # swing_lookback=2, major_swing_lookback=5 (the grid defaults)


def _m1_walk(days: int = 6, seed: int = 11) -> pd.DataFrame:
    """Seeded M1 random walk, 24/7 in June (no DST switch), valid OHLC."""
    n = days * 1440
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0.0, 0.04, n))
    open_ = np.r_[100.0, close[:-1]]
    high = np.maximum(open_, close) + np.abs(rng.normal(0.0, 0.015, n))
    low = np.minimum(open_, close) - np.abs(rng.normal(0.0, 0.015, n))
    idx = pd.date_range("2021-06-07", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=idx)


M1 = _m1_walk()


def _cuts(tf_minutes: int, n: int = 40):
    """Cut times on and between higher-TF bar boundaries (skip the first day: detector warm-up)."""
    lo, hi = 1440, len(M1) - 1
    pos = np.linspace(lo, hi, n).astype(int)
    pos = np.unique(np.r_[pos, (pos // tf_minutes) * tf_minutes])
    return [M1.index[p] for p in pos if lo <= p <= hi]


@pytest.mark.parametrize("tf", ["H1", "M15"])
def test_nearest_opposing_swing_truncation_invariant(tf):
    full = build_tf_view(M1, tf, CFG)
    lo, hi = float(M1["low"].min()), float(M1["high"].max())
    n_found = 0
    for ts in _cuts(60 if tf == "H1" else 15):
        pre = build_tf_view(M1[M1.index < ts], tf, CFG)
        pos = full.latest_closed_pos(ts)
        last_close = float(full.df["close"].iloc[pos])
        levels = [last_close, *np.linspace(lo, hi, 9)]
        for major in (False, True):
            for d in ("long", "short"):
                for beyond in levels:
                    a = full.nearest_opposing_swing(ts, d, beyond, major=major)
                    b = pre.nearest_opposing_swing(ts, d, beyond, major=major)
                    assert a == b, (tf, str(ts), d, beyond, major, a, b)
                    n_found += a is not None
    assert n_found > 100          # the lookups are not trivially empty


def test_swing_not_usable_before_its_confirmation_bar_closes():
    # Hand-built H1 bars (60 identical M1 bars each): a lone swing high at bar 3 (k = 2) is
    # confirmed by bars 4 and 5, so it is knowable from the close of bar 5 and not before.
    highs = [101, 102, 103, 110, 104, 103, 102, 101]
    rows = [(h - 1.0, h, h - 2.0, h - 0.5) for h in highs]
    idx = pd.date_range("2021-06-07", periods=60 * len(rows), freq="1min", tz="UTC")
    a = np.repeat(np.array(rows, dtype=float), 60, axis=0)
    m1 = pd.DataFrame({"open": a[:, 0], "high": a[:, 1], "low": a[:, 2], "close": a[:, 3]}, index=idx)
    cfg = StrategyConfig(swing_lookback=2)
    view = build_tf_view(m1, "H1", cfg)
    assert [s.index for s in view.swings_high] == [3]

    def close_of(j: int) -> pd.Timestamp:
        return view.df.index[j] + view.dur

    assert view.nearest_opposing_swing(close_of(4), "long", 105.0) is None             # bar 5 open
    assert view.nearest_opposing_swing(close_of(5), "long", 105.0) == 110.0            # confirmed
    pre = build_tf_view(m1[m1.index < close_of(4)], "H1", cfg)
    assert pre.nearest_opposing_swing(close_of(4), "long", 105.0) is None


@pytest.mark.parametrize("tf", ["H1", "M15"])
def test_bias_poi_and_structure_lookups_truncation_invariant(tf):
    full = build_tf_view(M1, tf, CFG)
    lo, hi = float(M1["low"].min()), float(M1["high"].max())
    for ts in _cuts(60 if tf == "H1" else 15, n=25):
        pre = build_tf_view(M1[M1.index < ts], tf, CFG)
        assert full.latest_closed_pos(ts) == pre.latest_closed_pos(ts)
        assert full.bias_asof(ts) == pre.bias_asof(ts)
        for d in ("long", "short"):
            ea, eb = full.latest_structure_with_fvg(ts, d), pre.latest_structure_with_fvg(ts, d)
            assert (ea is None) == (eb is None)
            if ea is not None:
                assert (ea.index, ea.kind, ea.broken_level, ea.protective_level) == \
                       (eb.index, eb.kind, eb.broken_level, eb.protective_level)
            for price in np.linspace(lo, hi, 7):
                pa, pb = full.latest_poi_containing(ts, d, price), pre.latest_poi_containing(ts, d, price)
                assert (pa is None) == (pb is None)
                if pa is not None:
                    assert (pa.event_index, pa.lower, pa.upper) == (pb.event_index, pb.lower, pb.upper)
