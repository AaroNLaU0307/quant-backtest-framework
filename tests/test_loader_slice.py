"""The in-sample / out-of-sample wall is enforced structurally, not by discipline."""
from __future__ import annotations

import pandas as pd
import pytest

from mtf_smc.config import DataConfig
from mtf_smc.data.loader import load_full_m1, load_is, load_oos


def _ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="UTC")


def test_hard_is_slice_drops_oos(tmp_path, m1_factory):
    # A synthetic series straddling the 2023 boundary written to a temp cache.
    m1 = m1_factory(start="2022-12-31 23:50", periods=20)  # -> 2023-01-01 00:09
    cfg = DataConfig(data_cache_dir=tmp_path)
    cfg.data_cache_dir.mkdir(parents=True, exist_ok=True)
    m1.to_pickle(cfg.cache_pickle)

    is_df = load_is(cfg)
    assert (is_df.index < cfg.oos_start).all()
    assert is_df.index.max() < _ts("2023-01-01")

    oos_df = load_oos(cfg)
    assert (oos_df.index >= cfg.oos_start).all()

    # IS and OOS partition the full set with no overlap and no loss.
    assert len(is_df) + len(oos_df) == len(load_full_m1(cfg))
    assert is_df.index.intersection(oos_df.index).empty


def test_is_slice_on_real_seeded_cache():
    cfg = DataConfig()
    if not cfg.cache_pickle.exists():
        pytest.skip("seeded cache not present")
    is_df = load_is(cfg)
    assert is_df.index.max() < _ts("2023-01-01")      # the structural guarantee
    assert is_df.index.min() >= _ts("2015-01-01")
    assert list(is_df.columns) == ["open", "high", "low", "close"]
    assert str(is_df.index.tz) == "UTC"
    assert is_df.index.is_monotonic_increasing
