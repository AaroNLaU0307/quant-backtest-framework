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


# Cache span per instrument: XAUUSD carries the sealed 2023-2025 OOS in its full-series pickle;
# the replication instruments span 2015-2023 (their 2023 is OOS). Used by ``DataConfig.for_symbol``.
_CACHE_SPAN: dict = {"XAUUSD": "2015_2025"}


@dataclass(frozen=True)
class DataConfig:
    """Data acquisition + in-sample / out-of-sample boundaries (all tz-aware UTC)."""

    symbol: str = "XAUUSD"
    data_tz: str = "UTC"
    # Higher-TF (D1/W1) session anchor: 'ny_close' (17:00 America/New_York, DST-aware) or 'utc'.
    session_anchor: str = "ny_close"

    data_cache_dir: Path = REPO_ROOT / "data_cache"
    raw_data_dir: Optional[Path] = None  # set to SMC_DATA_DIR to rebuild from HistData .xlsx
    cache_pickle_name: str = "XAUUSD_M1_UTC_2015_2025.pkl"  # full series; load_is hard-slices to <2023

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

    @classmethod
    def for_symbol(cls, symbol: str = "XAUUSD", **overrides) -> "DataConfig":
        """Per-instrument data config (cache name derived from ``symbol``).

        XAUUSD keeps the existing extended cache (full series to 2025, OOS 2023-2025); the other
        instruments span 2015-2023 (2023 = their OOS). ``for_symbol("XAUUSD")`` is byte-for-byte the
        same data config as ``DataConfig()`` / ``from_env()`` — the seam is purely additive, so the
        XAUUSD path is unperturbed. ``SMC_DATA_DIR`` is honoured for raw rebuilds; the session anchor
        (``ny_close``) and IS/OOS boundaries are shared (see ``docs/SPEC_multi_instrument.md`` §2,§4).
        """
        span = _CACHE_SPAN.get(symbol, "2015_2023")
        raw = os.environ.get("SMC_DATA_DIR")
        kw: dict = dict(
            symbol=symbol,
            cache_pickle_name=f"{symbol}_M1_UTC_{span}.pkl",
            raw_data_dir=Path(raw) if raw else None,
        )
        kw.update(overrides)
        return cls(**kw)


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

    # HTF_level / scale TP target: which opposing HTF swing to aim for.
    htf_target_mode: str = "major_swing"   # 'major_swing' (significant key level, high R:R) | 'nearest_swing'
    major_swing_lookback: int = 5          # larger fractal => fewer, more significant HTF swings
    fib_ext_tp: float = 4.236              # hybrid_fib TP: impulse-leg extension target (ported; off-grid)

    # --- Legacy SMC machinery (off-by-default; ported; read only by entry_model="legacy_smc") ---
    legacy_min_retracement: float = 0.5        # deep-Fib OTE entry band: [min_ret, 1.0] of the leg
    legacy_ob_use_wick: bool = False           # OB zone = body (False) | wick (True)
    legacy_disp_atr_mult: float = 1.5          # displacement: range >= mult*ATR
    legacy_disp_body_ratio: float = 0.5        # displacement: body/range >= ratio
    legacy_confluence_overlap_pct: float = 0.5
    legacy_confluence_atr_dist: float = 0.5
    legacy_min_confluence_score: int = 2       # deep-Fib + >= 1 PD array
    legacy_fib_ext_be: float = 1.618           # 1.618 extension (BE / partial-target anchor)
    legacy_structure_confirm_mode: str = "any"  # 'any' | 'mss_only' | 'cbdb_only'
    legacy_cbdb_lookback: int = 12
    legacy_cbdb_dominant_min: int = 3
    legacy_monitor_window_ltf_bars: int = 96   # LTF bars to wait for a trigger after POI pierce
    # Session filter (old FilterParams default: ON for FX/metals — block new entries in the Asia session;
    # GBPJPY-style exemption via legacy_allow_asia_session). Off-by-default; legacy_d1h1m5() turns it on.
    legacy_session_filter: bool = False
    legacy_allow_asia_session: bool = False
    legacy_asia_start_h: float = 0.0           # Asia block window in UTC hours, half-open [start, end)
    legacy_asia_end_h: float = 8.0

    # --- bias filter & management ---
    ema_filter: bool = True
    ema_bias_tf: str = "htf"            # which TF the Vegas bias reads: 'htf' | 'mtf'
    ema_fast: int = 55
    ema_slow: int = 144
    be_at_2R: bool = True
    be_trigger_R: float = 2.0           # move stop to breakeven once price reaches +be_trigger_R (2R default)
    be_buffer: float = 0.02             # legacy/unused; BE buffer is per-instrument (InstrumentSpec.be_buffer_price)
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
        if self.entry_model in ("cascade", "legacy_smc"):
            tfs = [self.htf, self.mtf, self.ltf]
        else:  # direct: HTF always; MTF only when the POI must be backed by an MTF shift
            tfs = [self.htf] + ([self.mtf] if self.direct_poi_source == "requires_mtf_shift" else [])
        seen: list = []
        for t in tfs:
            if t not in seen:
                seen.append(t)
        return tuple(seen)

    @property
    def context_key(self) -> tuple:
        """Identifies configs that share identical detection (so context can be cached/reused).

        Excludes parameters that only affect setup geometry or trade management (tp_mode,
        htf_target_mode, fib_threshold, entry_edge, be_*, risk, expiry, tie_break) — those are cheap
        to re-evaluate and never change the detector outputs.
        """
        return (
            self.entry_model, self.htf, self.mtf, self.ltf, self.direct_poi_source,
            self.swing_lookback, self.major_swing_lookback, self.atr_period,
            self.fvg_min_atr, self.fvg_assoc_window, self.ema_fast, self.ema_slow,
            self.ema_bias_tf, self.session_anchor,
        )

    @property
    def config_id(self) -> str:
        if self.entry_model == "cascade":
            return f"cascade_{self.htf}_{self.mtf}_{self.ltf}_{self.tp_mode}"
        if self.entry_model == "legacy_smc":
            return f"legacy_{self.htf}_{self.mtf}_{self.ltf}_{self.tp_mode}"
        return f"direct_{self.htf}_{self.tp_mode}"

    @classmethod
    def legacy_d1h1m5(cls) -> "StrategyConfig":
        """The published single-instrument repo's strategy, reproduced on THIS engine.

        Part of the merge (docs/MERGE_PLAN.md): the unified engine running the OLD strategy — a D1->H1->M5
        ``legacy_smc`` cascade at 0.5% risk (D1 bias -> H1 deep-Fib-OTE confluence POI -> M5
        ``FVG AND (MSS OR CB/DB)`` trigger), hybrid-Fib TP onto the nearest D1 swing-liquidity
        (``nearest_swing`` = the old's nearest-unswept-D1-liquidity target at swing-lookback 2), and the old
        default session filter ON (block new entries during the Asia session). The old exit takes no partial
        scale-out (verified in the old ``trade_manager.py``); fidelity to entries AND exits was checked
        behaviourally against the old engine (86% post-warmup entry overlap; matched-pair R aligned 16/18).
        The remaining ported machinery (portfolio risk + circuit breakers, alternative confirm modes) stays
        as off-by-default ablation knobs; this preset enables exactly what the old default turned on.
        """
        return cls(entry_model="legacy_smc", htf="D1", mtf="H1", ltf="M5",
                   tp_mode="hybrid_fib", htf_target_mode="nearest_swing", risk_pct=0.005,
                   legacy_session_filter=True)
