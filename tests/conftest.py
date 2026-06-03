"""Shared test fixtures: deterministic synthetic M1 OHLC (no data download needed)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def make_m1(start: str = "2020-01-06 00:00", periods: int = 360, tz: str = "UTC",
            base: float = 100.0, step: float = 0.1) -> pd.DataFrame:
    """A valid, monotonic synthetic M1 frame.

    ``open`` ramps by ``step`` each minute; ``close = open + 0.05``; wicks ±0.02 — guaranteeing
    ``low <= open/close <= high`` so it passes integrity checks and gives predictable aggregates.
    Default start is a Monday (good for weekly-anchor tests).
    """
    idx = pd.date_range(start=start, periods=periods, freq="1min", tz=tz)
    o = base + np.arange(periods) * step
    c = o + 0.05
    h = np.maximum(o, c) + 0.02
    lo = np.minimum(o, c) - 0.02
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=idx)


@pytest.fixture
def m1_factory():
    """Return the :func:`make_m1` builder so tests can request custom windows."""
    return make_m1


@pytest.fixture
def synth_m1():
    """A default 6-hour synthetic M1 frame."""
    return make_m1()


@pytest.fixture(scope="session")
def is_m1():
    """Real in-sample M1 from the seeded cache (skips if the cache is absent)."""
    from mtf_smc.config import DataConfig
    from mtf_smc.data.loader import load_is

    cfg = DataConfig()
    if not cfg.cache_pickle.exists():
        pytest.skip("seeded cache not present")
    return load_is(cfg)
