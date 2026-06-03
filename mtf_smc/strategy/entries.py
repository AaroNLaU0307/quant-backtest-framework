"""Entry models A (cascade) and B (direct POI) -> ``TradeSetup`` lists. ``docs/SPEC.md`` §3.

Both produce resting limit orders (entry price = a chosen FVG/POI edge) with an initial stop, a
frozen TP target for the HTF-level/scale modes, an expiry, and an invalidation level. Everything is
read *as-of* the trigger time from :class:`mtf_smc.strategy.context.TFView`, so no future bar leaks
into a setup.

Cascade (A): HTF bias + an unmitigated HTF POI the price is sitting in -> an MTF BOS/CHoCH-with-FVG
whose discount/premium leg overlaps that POI and currently holds price (the pullback) -> an LTF
CHoCH-with-FVG trigger; limit at the LTF FVG edge, stop = LTF protective swing ± ATR.

Direct (B): place a passive limit at an HTF POI (optionally requiring an MTF shift), stop beyond the
POI ± ATR. No LTF confirmation.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from mtf_smc.config import StrategyConfig
from mtf_smc.engine.trade import TradeSetup
from mtf_smc.indicators.fib import FibLeg
from mtf_smc.smc.structure import StructureEvent
from mtf_smc.strategy.context import TFView, build_context


def _overlap(a: Tuple[float, float], b: Tuple[float, float]) -> bool:
    return max(a[0], b[0]) <= min(a[1], b[1])


def _fib_leg(ev: StructureEvent) -> Optional[FibLeg]:
    """Impulse leg from a structure event (protective swing -> broken level)."""
    lo, hi = min(ev.protective_level, ev.broken_level), max(ev.protective_level, ev.broken_level)
    if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
        return None
    return FibLeg(ev.direction, low=lo, high=hi, low_index=0, high_index=0)


def _htf_target(htf: TFView, ts: pd.Timestamp, direction: str, entry: float,
                cfg: StrategyConfig) -> Optional[float]:
    """Frozen TP for HTF-level / scale modes: nearest opposing confirmed HTF swing beyond entry."""
    if cfg.tp_mode == "fixed_3R":
        return None
    return htf.nearest_opposing_swing(ts, direction, beyond=entry,
                                      major=(cfg.htf_target_mode == "major_swing"))


def _cascade(cfg: StrategyConfig, ctx: Dict[str, TFView]) -> List[TradeSetup]:
    ltf, htf, mtf = ctx[cfg.ltf], ctx[cfg.htf], ctx[cfg.mtf]
    bias_view = htf if cfg.ema_bias_tf == "htf" else mtf
    setups: List[TradeSetup] = []
    for ev in ltf.structure:
        d = ev.direction
        fvg = ltf.assoc_fvg(ev.index, d, cfg.fvg_assoc_window)
        if fvg is None:                                            # LTF trigger needs an FVG
            continue
        ts = ltf.close_time(ev.index)
        if cfg.ema_filter and bias_view.bias_asof(ts) != d:        # HTF bias gate
            continue
        price = float(ltf.df["close"].iloc[ev.index])
        poi = htf.latest_poi_containing(ts, d, price)              # price sitting in an HTF POI
        if poi is None:
            continue
        mtf_ev = mtf.latest_structure_with_fvg(ts, d)              # MTF BOS/CHoCH + FVG
        if mtf_ev is None:
            continue
        leg = _fib_leg(mtf_ev)
        if leg is None or not leg.in_entry_zone(price, cfg.fib_threshold):   # pullback into discount
            continue
        band = leg.retracement_zone(cfg.fib_threshold, 1.0)
        if not _overlap(band, (poi.lower, poi.upper)):             # discount overlaps the POI
            continue
        atr_ltf = ltf.atr.iloc[ev.index]
        if not np.isfinite(atr_ltf) or not np.isfinite(ev.protective_level):
            continue
        entry = float(fvg.entry_price(cfg.entry_edge))
        buf = cfg.atr_mult * float(atr_ltf)
        stop = ev.protective_level - buf if d == "long" else ev.protective_level + buf
        if (d == "long" and stop >= entry) or (d == "short" and stop <= entry):
            continue
        setups.append(TradeSetup(
            direction=d, entry=entry, initial_stop=float(stop), tp_mode=cfg.tp_mode,
            htf_target=_htf_target(htf, ts, d, entry, cfg), decided_ts=ts,
            expiry_ts=ts + cfg.entry_expiry_bars * ltf.dur,
            invalidation=float(poi.lower if d == "long" else poi.upper),
            tag=f"cascade_{ev.kind}",
        ))
    return setups


def _direct(cfg: StrategyConfig, ctx: Dict[str, TFView]) -> List[TradeSetup]:
    htf = ctx[cfg.htf]
    mtf = ctx.get(cfg.mtf)
    bias_view = htf if cfg.ema_bias_tf == "htf" else (mtf or htf)
    setups: List[TradeSetup] = []
    for poi in htf.pois:
        d = poi.direction
        ts = htf.close_time(poi.event_index)
        if cfg.ema_filter and bias_view.bias_asof(ts) != d:
            continue
        if cfg.direct_poi_source == "requires_mtf_shift":
            if mtf is None or mtf.latest_structure_with_fvg(ts, d) is None:
                continue
        atr_htf = htf.atr.iloc[poi.event_index]
        if not np.isfinite(atr_htf):
            continue
        entry = float(poi.fvg.entry_price(cfg.entry_edge))
        buf = cfg.atr_mult * float(atr_htf)
        stop = poi.lower - buf if d == "long" else poi.upper + buf
        if (d == "long" and stop >= entry) or (d == "short" and stop <= entry):
            continue
        setups.append(TradeSetup(
            direction=d, entry=entry, initial_stop=float(stop), tp_mode=cfg.tp_mode,
            htf_target=_htf_target(htf, ts, d, entry, cfg), decided_ts=ts,
            expiry_ts=ts + cfg.entry_expiry_bars * htf.dur,
            invalidation=float(poi.lower if d == "long" else poi.upper), tag="direct",
        ))
    return setups


def generate_setups(
    m1: pd.DataFrame, cfg: StrategyConfig, ctx: Optional[Dict[str, TFView]] = None
) -> Tuple[List[TradeSetup], Dict[str, TFView]]:
    """Build all entry setups for ``cfg`` (sorted by decision time)."""
    ctx = ctx or build_context(m1, cfg)
    if cfg.entry_model == "cascade":
        setups = _cascade(cfg, ctx)
    elif cfg.entry_model == "direct":
        setups = _direct(cfg, ctx)
    else:
        raise ValueError(f"Unknown entry_model {cfg.entry_model!r}")
    setups.sort(key=lambda s: s.decided_ts)
    return setups, ctx
