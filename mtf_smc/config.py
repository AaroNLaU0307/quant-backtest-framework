"""Typed configuration for the data layer — foundation of the config-driven tree.

Only data/timeframe settings live here for now; the strategy/engine/robustness config is added
in later steps. No magic numbers leak into logic: values come from here or from YAML (``configs/``).

The in-sample / out-of-sample wall is enforced *structurally* (see
:func:`mtf_smc.data.loader.load_is`), not by discipline: development always loads
``[is_start, oos_start)`` and physically never sees ``>= oos_start`` rows.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

# Repo root = parent of the package dir (mtf_smc/config.py -> mtf_smc -> root).
REPO_ROOT: Path = Path(__file__).resolve().parents[1]


def _utc(ts: str) -> pd.Timestamp:
    return pd.Timestamp(ts, tz="UTC")


@dataclass(frozen=True)
class DataConfig:
    """Data acquisition + in-sample / out-of-sample boundaries (all tz-aware UTC)."""

    symbol: str = "XAUUSD"
    data_tz: str = "UTC"
    # Higher-TF (D1/W1) session anchor: 'ny_close' (17:00 America/New_York, DST-aware) or 'utc'.
    session_anchor: str = "ny_close"

    data_cache_dir: Path = REPO_ROOT / "data_cache"
    raw_data_dir: Optional[Path] = None  # set to SMC_DATA_DIR to rebuild from HistData .xlsx
    cache_pickle_name: str = "XAUUSD_M1_UTC_2015_2023.pkl"

    # Windows are half-open [start, end). is end == oos start == the hard slice boundary.
    is_start: pd.Timestamp = field(default_factory=lambda: _utc("2015-01-01"))
    oos_start: pd.Timestamp = field(default_factory=lambda: _utc("2023-01-01"))
    oos_end: pd.Timestamp = field(default_factory=lambda: _utc("2026-01-01"))  # covers 2023-2025

    output_dir: Path = REPO_ROOT / "output"
    seed: int = 7

    @property
    def cache_pickle(self) -> Path:
        """Path to the cached UTC M1 pickle the loader prefers."""
        return self.data_cache_dir / self.cache_pickle_name

    @classmethod
    def from_env(cls) -> "DataConfig":
        """Build a config, picking up ``SMC_DATA_DIR`` for raw HistData rebuilds if set."""
        raw = os.environ.get("SMC_DATA_DIR")
        return cls(raw_data_dir=Path(raw) if raw else None)
