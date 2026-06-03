"""Truncation-invariance: the deliberate look-ahead tests for every fragile detector.

Recomputing any signal on the prefix ``[0..m)`` must reproduce exactly what the full-series
computation produced for those bars. If deleting future bars changed a past value, a detector is
peeking — and the test fails. (``docs/SPEC.md`` §7.)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from mtf_smc.indicators.atr import atr_wilder
from mtf_smc.indicators.ema import ema
from mtf_smc.smc.fvg import detect_fvgs
from mtf_smc.smc.structure import detect_structure
from mtf_smc.smc.swings import detect_swings

CUTS = (120, 200, 280)


def _walk(n: int = 300, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = 100 + np.cumsum(rng.normal(0, 1.0, n))
    o = base
    c = base + rng.normal(0, 0.2, n)
    h = np.maximum(o, c) + np.abs(rng.normal(0, 0.3, n))
    lo = np.minimum(o, c) - np.abs(rng.normal(0, 0.3, n))
    idx = pd.date_range("2020-01-06", periods=n, freq="5min", tz="UTC")
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=idx)


def test_atr_truncation_invariant():
    df = _walk()
    full = atr_wilder(df, 14)
    for m in CUTS:
        pre = atr_wilder(df.iloc[:m], 14)
        assert np.isclose(pre.iloc[-1], full.iloc[m - 1], equal_nan=True)


def test_ema_truncation_invariant():
    df = _walk()
    full = ema(df["close"], 55)
    for m in CUTS:
        pre = ema(df["close"].iloc[:m], 55)
        assert np.isclose(pre.iloc[-1], full.iloc[m - 1])


def test_swings_truncation_invariant():
    df = _walk()
    k = 2
    sh_f, sl_f = detect_swings(df, k)
    for m in CUTS:
        sh_p, sl_p = detect_swings(df.iloc[:m], k)
        assert [(s.index, s.price) for s in sh_p] == [(s.index, s.price) for s in sh_f if s.index <= m - 1 - k]
        assert [(s.index, s.price) for s in sl_p] == [(s.index, s.price) for s in sl_f if s.index <= m - 1 - k]


def test_fvg_truncation_invariant():
    df = _walk()
    full = detect_fvgs(df)
    for m in CUTS:
        pre = detect_fvgs(df.iloc[:m])
        exp = [(f.direction, f.mid_index, f.lower, f.upper) for f in full if f.confirm_index < m]
        assert [(f.direction, f.mid_index, f.lower, f.upper) for f in pre] == exp


def test_structure_truncation_invariant():
    df = _walk()
    k = 2
    full = detect_structure(df, k)
    for m in CUTS:
        pre = detect_structure(df.iloc[:m], k)
        exp = [(e.index, e.kind, e.direction, e.broken_level) for e in full if e.index < m]
        assert [(e.index, e.kind, e.direction, e.broken_level) for e in pre] == exp
