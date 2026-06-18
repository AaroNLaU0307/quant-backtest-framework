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
from mtf_smc.strategy.legacy_poi import build_confluence_pois
from mtf_smc.strategy.legacy_trigger import detect_legacy_triggers


def _overlap(a: Tuple[float, float], b: Tuple[float, float]) -> bool:
    return max(a[0], b[0]) <= min(a[1], b[1])


def _fib_leg(ev: StructureEvent) -> Optional[FibLeg]:
    """Impulse leg from a structure event (protective swing -> broken level)."""
    lo, hi = min(ev.protective_level, ev.broken_level), max(ev.protective_level, ev.broken_level)
    if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
        return None
    return FibLeg(ev.direction, low=lo, high=hi, low_index=0, high_index=0)


def _htf_target(htf: TFView, ts: pd.Timestamp, direction: str, entry: float,
                cfg: StrategyConfig, leg: Optional[FibLeg] = None) -> Optional[float]:
    """Frozen TP for HTF-level / scale / hybrid_fib modes; None for any fixed-R (the FSM computes those).

    ``hybrid_fib`` (ported from the old single-instrument repo, off-by-default): the **nearer** of the
    nearest opposing HTF liquidity and the impulse leg's ``fib_ext_tp`` (4.236) extension — whichever
    price is reached first. Existing modes are unchanged (HTF_level/scale -> swing), so the 42-grid is
    bit-identical.
    """
    if cfg.tp_mode.startswith("fixed_"):
        return None
    swing = htf.nearest_opposing_swing(ts, direction, beyond=entry,
                                       major=(cfg.htf_target_mode == "major_swing"))
    if cfg.tp_mode == "hybrid_fib":
        ext = leg.extension(cfg.fib_ext_tp) if leg is not None else None
        cands = [t for t in (swing, ext) if t is not None]
        if not cands:
            return None
        return min(cands) if direction == "long" else max(cands)   # nearer-to-entry target hits first
    return swing


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
            htf_target=_htf_target(htf, ts, d, entry, cfg, leg=leg), decided_ts=ts,
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


def _asia_blocked(ts: pd.Timestamp, cfg: StrategyConfig) -> bool:
    """True if ``ts`` is inside the Asia-session block (the OLD FilterParams default; docs/MERGE_PLAN.md).

    Off unless ``legacy_session_filter`` is set, and skipped for instruments granted the GBPJPY-style
    ``legacy_allow_asia_session`` exemption. Window is half-open ``[start, end)`` in UTC hours.
    """
    if not cfg.legacy_session_filter or cfg.legacy_allow_asia_session:
        return False
    h = ts.hour + ts.minute / 60.0
    return cfg.legacy_asia_start_h <= h < cfg.legacy_asia_end_h


def precompute_legacy_triggers(cfg: StrategyConfig, ctx: Dict[str, TFView]) -> Dict[str, list]:
    """The M5 ``FVG AND (MSS OR CB/DB)`` triggers per direction — the score/retracement-independent,
    expensive part of ``legacy_smc``.

    Precompute once per (instrument, window) and pass into ``generate_setups(..., legacy_triggers=...)``
    so a sweep over the detection-threshold grid does not recompute the M5 triggers for every grid point
    (the walk-forward's dominant cost). Output is identical to the inline detection in ``_legacy_smc``.
    """
    ltf = ctx[cfg.ltf]
    trig_kw = dict(
        swing_lookback=cfg.swing_lookback, structure_confirm_mode=cfg.legacy_structure_confirm_mode,
        require_fvg=True, fvg_assoc_window=cfg.fvg_assoc_window, fvg_min_atr_mult=cfg.fvg_min_atr,
        disp_atr_mult=cfg.legacy_disp_atr_mult, disp_body_ratio=cfg.legacy_disp_body_ratio,
        cbdb_lookback=cfg.legacy_cbdb_lookback, cbdb_dominant_min=cfg.legacy_cbdb_dominant_min,
    )
    return {d: detect_legacy_triggers(ltf.df, d, ltf.atr, **trig_kw) for d in ("long", "short")}


def _legacy_smc(cfg: StrategyConfig, ctx: Dict[str, TFView],
                legacy_triggers: Optional[Dict[str, list]] = None) -> List[TradeSetup]:
    """The OLD repo's strategy reproduced on this engine (off-by-default; docs/MERGE_PLAN.md).

    D1 bias -> H1 deep-Fib-OTE confluence POI -> price pierces the OTE band -> within a monitor window
    an M5 ``FVG AND (MSS OR CB/DB)`` trigger (with the protective inside the POI) -> entry at the M5 FVG
    edge, stop = protective -/+ ATR buffer, hybrid-Fib TP (nearer of the 4.236 leg extension and the
    nearest D1 liquidity). One setup per POI. All causal: POIs are used only from their created bar,
    the pierce/trigger are later M5 bars, and the TP is frozen at the trigger.
    """
    htf, itf, ltf = ctx[cfg.htf], ctx[cfg.mtf], ctx[cfg.ltf]
    poi_kw = dict(
        swing_lookback=cfg.swing_lookback, min_retracement=cfg.legacy_min_retracement,
        ob_use_wick=cfg.legacy_ob_use_wick, fvg_min_atr_mult=cfg.fvg_min_atr,
        disp_atr_mult=cfg.legacy_disp_atr_mult, disp_body_ratio=cfg.legacy_disp_body_ratio,
        confluence_overlap_pct=cfg.legacy_confluence_overlap_pct,
        confluence_atr_dist=cfg.legacy_confluence_atr_dist,
        min_confluence_score=cfg.legacy_min_confluence_score,
        fib_ext_be=cfg.legacy_fib_ext_be, fib_ext_tp=cfg.fib_ext_tp,
    )
    trig_kw = dict(
        swing_lookback=cfg.swing_lookback, structure_confirm_mode=cfg.legacy_structure_confirm_mode,
        require_fvg=True, fvg_assoc_window=cfg.fvg_assoc_window, fvg_min_atr_mult=cfg.fvg_min_atr,
        disp_atr_mult=cfg.legacy_disp_atr_mult, disp_body_ratio=cfg.legacy_disp_body_ratio,
        cbdb_lookback=cfg.legacy_cbdb_lookback, cbdb_dominant_min=cfg.legacy_cbdb_dominant_min,
    )
    ltf_low = ltf.df["low"].to_numpy(); ltf_high = ltf.df["high"].to_numpy()
    n_ltf = len(ltf.df)
    setups: List[TradeSetup] = []
    for direction in ("long", "short"):
        pois = build_confluence_pois(itf.df, direction, itf.atr, **poi_kw)
        triggers = (legacy_triggers.get(direction) if legacy_triggers is not None
                    else detect_legacy_triggers(ltf.df, direction, ltf.atr, **trig_kw))
        for poi in pois:
            start = ltf.latest_closed_pos(itf.close_time(poi.created_index)) + 1
            if start < 0 or start >= n_ltf:
                continue
            pierce = None                                        # first M5 bar entering the OTE band
            for j in range(start, n_ltf):
                if ltf_low[j] <= poi.zone_upper and ltf_high[j] >= poi.zone_lower:
                    pierce = j; break
            if pierce is None:
                continue
            win_end = pierce + cfg.legacy_monitor_window_ltf_bars
            for t in triggers:
                if t.break_index <= pierce or t.break_index > win_end:
                    continue
                ts = ltf.close_time(t.break_index)
                if _asia_blocked(ts, cfg):                                      # old default: Asia-session block
                    continue
                if cfg.ema_filter and htf.bias_asof(ts) != direction:           # D1 bias gate
                    continue
                if not (poi.zone_lower <= t.protective_swing <= poi.zone_upper):  # protective in POI
                    continue
                atr_t = float(ltf.atr.iloc[t.break_index])
                if not np.isfinite(atr_t):
                    continue
                entry = t.fvg_upper if direction == "long" else t.fvg_lower      # M5 FVG near edge
                buf = cfg.atr_mult * atr_t
                stop = t.protective_swing - buf if direction == "long" else t.protective_swing + buf
                if (direction == "long" and stop >= entry) or (direction == "short" and stop <= entry):
                    continue
                liq = htf.nearest_opposing_swing(ts, direction, beyond=entry,
                                                 major=(cfg.htf_target_mode == "major_swing"))
                cands = [x for x in (poi.ext_tp, liq) if x is not None]
                if not cands:
                    continue
                target = min(cands) if direction == "long" else max(cands)      # hybrid-Fib TP
                setups.append(TradeSetup(
                    direction=direction, entry=float(entry), initial_stop=float(stop),
                    tp_mode="HTF_level", htf_target=float(target), decided_ts=ts,
                    expiry_ts=ts + cfg.entry_expiry_bars * ltf.dur,
                    invalidation=float(poi.zone_lower if direction == "long" else poi.zone_upper),
                    tag=f"legacy_{t.kind}",
                ))
                break                                            # consume the POI on first valid trigger
    return setups


def generate_setups(
    m1: pd.DataFrame, cfg: StrategyConfig, ctx: Optional[Dict[str, TFView]] = None,
    legacy_triggers: Optional[Dict[str, list]] = None,
) -> Tuple[List[TradeSetup], Dict[str, TFView]]:
    """Build all entry setups for ``cfg`` (sorted by decision time).

    ``legacy_triggers`` (optional) injects precomputed ``legacy_smc`` M5 triggers (see
    ``precompute_legacy_triggers``) so a sweep over the detection grid does not recompute them; it is
    ignored for non-legacy entry models.
    """
    ctx = ctx or build_context(m1, cfg)
    if cfg.entry_model == "cascade":
        setups = _cascade(cfg, ctx)
    elif cfg.entry_model == "direct":
        setups = _direct(cfg, ctx)
    elif cfg.entry_model == "legacy_smc":
        setups = _legacy_smc(cfg, ctx, legacy_triggers=legacy_triggers)
    else:
        raise ValueError(f"Unknown entry_model {cfg.entry_model!r}")
    setups.sort(key=lambda s: s.decided_ts)
    return setups, ctx
