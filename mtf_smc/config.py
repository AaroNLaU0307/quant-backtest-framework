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


@dataclass(frozen=True)
class StrategyConfig:
    """One typed config for a single backtest run (no magic numbers; ``docs/SPEC.md`` §3-§6).

    A single point in the parameter grid. The grid runner enumerates ``entry_model x htf x mtf x
    ltf x tp_mode``; everything else has SPEC defaults and is varied only in ablations.
    """

    # --- grid axes ---
    entry_model: str = "cascade"        # 'cascade' (A) | 'direct' (B)
    htf: str = "D1"                     # {W1, D1}
    mtf: str = "H1"                     # {H4, H1}
    ltf: str = "M15"                    # {M15, M5, M1} (cascade only)
    tp_mode: str = "fixed_3R"           # 'fixed_3R' | 'HTF_level' | 'scale_2R_then_HTF'

    # --- SMC primitives ---
    swing_lookback: int = 2
    atr_period: int = 14
    atr_mult: float = 0.5               # stop buffer in ATRs
    fib_threshold: float = 0.5          # min pullback depth (discount/premium)
    entry_edge: str = "near"            # FVG entry edge: 'near' | 'mid' | 'far'
    fvg_min_atr: float = 0.10           # drop FVGs smaller than this * ATR
    fvg_assoc_window: int = 12          # bars to associate an FVG with a structural break

    # --- bias filter & management ---
    ema_filter: bool = True
    ema_bias_tf: str = "htf"            # which TF the Vegas bias reads: 'htf' | 'mtf'
    ema_fast: int = 55
    ema_slow: int = 144
    be_at_2R: bool = True
    be_buffer: float = 0.02             # price added past entry when moving to breakeven (~2 ticks)
    risk_pct: float = 0.01              # fixed-fractional risk per trade
    entry_expiry_bars: int = 24         # LTF bars a resting limit order lives
    direct_poi_source: str = "htf_only"  # 'htf_only' | 'requires_mtf_shift' (model B)

    # --- engine ---
    tie_break: str = "stop_first"       # same-bar SL/TP resolution
    session_anchor: str = "ny_close"    # D1/W1 anchor (mirrors DataConfig)
    initial_equity: float = 100_000.0
    seed: int = 7

    @property
    def detection_tfs(self) -> tuple:
        """Distinct timeframes whose detectors this config needs (highest-first order preserved)."""
        tfs = [self.htf, self.mtf] + ([self.ltf] if self.entry_model == "cascade" else [])
        seen = []
        for t in tfs:
            if t not in seen:
                seen.append(t)
        return tuple(seen)
