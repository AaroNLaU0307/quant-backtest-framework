"""Per-timeframe analysis context consumed by the entry models.

For each timeframe a config needs, we resample M1 (honouring the session anchor) and run the tested,
causal detectors once: Wilder ATR, Vegas bias, swings, FVGs, BOS/CHoCH structure, and POIs. The
:class:`TFView` then answers *as-of* questions — "what is known at time ``ts``?" — using each bar's
close time (``bar_start + duration``), so callers never see an in-progress higher-TF bar.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from mtf_smc.config import StrategyConfig
from mtf_smc.data.resample import resample_ohlc
from mtf_smc.indicators.atr import atr_wilder
from mtf_smc.indicators.ema import vegas_bias
from mtf_smc.smc.fvg import FVG, detect_fvgs
from mtf_smc.smc.poi import POI, build_pois
from mtf_smc.smc.structure import StructureEvent, detect_structure
from mtf_smc.smc.swings import Swing, detect_swings
from mtf_smc.timeframes import tf_duration


@dataclass
class TFView:
    tf: str
    df: pd.DataFrame
    dur: pd.Timedelta
    close_times: pd.DatetimeIndex          # df.index + dur (each bar's nominal close)
    atr: pd.Series
    bias: np.ndarray                       # per-bar 'long'/'short'/'none'
    swings_high: List[Swing]
    swings_low: List[Swing]
    fvgs: List[FVG]
    structure: List[StructureEvent]
    pois: List[POI]

    # ------------------------------------------------------------------ #
    def latest_closed_pos(self, ts: pd.Timestamp) -> int:
        """Index of the most recent bar fully closed at ``ts`` (-1 if none)."""
        return int(self.close_times.searchsorted(ts, side="right")) - 1

    def close_time(self, idx: int) -> pd.Timestamp:
        return self.df.index[idx] + self.dur

    def bias_asof(self, ts: pd.Timestamp) -> str:
        pos = self.latest_closed_pos(ts)
        return self.bias[pos] if pos >= 0 else "none"

    def latest_poi_containing(self, ts: pd.Timestamp, direction: str, price: float) -> Optional[POI]:
        """Most recent same-direction POI, knowable by ``ts``, whose zone currently holds ``price``."""
        out: Optional[POI] = None
        for poi in self.pois:
            if poi.direction != direction:
                continue
            if self.close_time(poi.event_index) > ts:
                break  # POIs are in ascending event order; nothing later is knowable yet
            if poi.lower <= price <= poi.upper:
                out = poi
        return out

    def latest_structure_with_fvg(self, ts: pd.Timestamp, direction: str) -> Optional[StructureEvent]:
        """Most recent same-direction BOS/CHoCH knowable by ``ts`` that has an associated FVG."""
        out: Optional[StructureEvent] = None
        for ev in self.structure:
            if self.close_time(ev.index) > ts:
                break
            if ev.direction == direction and _assoc_fvg(self.fvgs, ev.index, direction, 12) is not None:
                out = ev
        return out

    def nearest_opposing_swing(self, ts: pd.Timestamp, direction: str, beyond: float) -> Optional[float]:
        """Nearest confirmed swing in the profit direction beyond ``beyond`` (frozen TP target)."""
        swings = self.swings_high if direction == "long" else self.swings_low
        best: Optional[float] = None
        for s in swings:
            if self.df.index[s.index] + self.dur > ts:
                break
            if direction == "long" and s.price > beyond:
                best = s.price if best is None else min(best, s.price)
            elif direction == "short" and s.price < beyond:
                best = s.price if best is None else max(best, s.price)
        return best


def _assoc_fvg(fvgs: List[FVG], event_index: int, direction: str, window: int) -> Optional[FVG]:
    """Latest same-direction FVG confirming within ``[event_index - window, event_index]``."""
    chosen: Optional[FVG] = None
    for f in fvgs:
        if f.direction != direction:
            continue
        if event_index - window <= f.confirm_index <= event_index:
            chosen = f
    return chosen


def build_tf_view(m1: pd.DataFrame, tf: str, cfg: StrategyConfig) -> TFView:
    df = resample_ohlc(m1, tf, anchor=cfg.session_anchor)
    atr = atr_wilder(df, cfg.atr_period)
    bias = vegas_bias(df["close"], cfg.ema_fast, cfg.ema_slow).to_numpy()
    sh, sl = detect_swings(df, cfg.swing_lookback)
    fvgs = detect_fvgs(df, cfg.fvg_min_atr, atr)
    structure = detect_structure(df, cfg.swing_lookback)
    pois = build_pois(structure, fvgs, cfg.fvg_assoc_window)
    return TFView(
        tf=tf, df=df, dur=tf_duration(tf), close_times=df.index + tf_duration(tf),
        atr=atr, bias=bias, swings_high=sh, swings_low=sl, fvgs=fvgs,
        structure=structure, pois=pois,
    )


def build_context(m1: pd.DataFrame, cfg: StrategyConfig) -> Dict[str, TFView]:
    """Build a :class:`TFView` for each timeframe this config needs."""
    return {tf: build_tf_view(m1, tf, cfg) for tf in cfg.detection_tfs}
