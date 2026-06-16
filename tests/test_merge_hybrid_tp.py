"""Merge (M2a): hybrid-Fib TP picks the nearer of HTF liquidity and the 4.236 leg extension,
and leaves the existing tp_modes (the 42-grid path) byte-unchanged."""
from __future__ import annotations

import pandas as pd

from mtf_smc.config import StrategyConfig
from mtf_smc.indicators.fib import FibLeg
from mtf_smc.strategy.entries import _htf_target

TS = pd.Timestamp("2020-06-01 12:00", tz="UTC")
LEG = FibLeg("long", low=1990.0, high=2010.0, low_index=0, high_index=0)   # range 20; 4.236 ext = 2074.72


class _StubHTF:
    def __init__(self, swing): self._swing = swing
    def nearest_opposing_swing(self, ts, direction, beyond, major): return self._swing


def test_hybrid_fib_takes_nearer_liquidity():
    # swing 2050 < ext 2074.72 -> liquidity is hit first (nearer) for a long
    t = _htf_target(_StubHTF(2050.0), TS, "long", 2000.0, StrategyConfig(tp_mode="hybrid_fib"), leg=LEG)
    assert t == 2050.0


def test_hybrid_fib_takes_nearer_extension():
    # swing 2090 > ext 2074.72 -> the 4.236 extension is nearer
    t = _htf_target(_StubHTF(2090.0), TS, "long", 2000.0, StrategyConfig(tp_mode="hybrid_fib"), leg=LEG)
    assert abs(t - (1990.0 + 4.236 * 20.0)) < 1e-9


def test_existing_modes_unchanged_bit_identical_path():
    assert _htf_target(_StubHTF(2050.0), TS, "long", 2000.0, StrategyConfig(tp_mode="HTF_level")) == 2050.0
    for fixed in ("fixed_3R", "fixed_1R", "fixed_5R"):
        assert _htf_target(_StubHTF(2050.0), TS, "long", 2000.0, StrategyConfig(tp_mode=fixed)) is None
