"""Legacy confluence-POI builder — faithfully ported from the old `smc_mtf/poi.py` POIEngine.

**OFF-BY-DEFAULT** (`docs/MERGE_PLAN.md`, M2). Imported only by `entry_model="legacy_smc"`; the
42-grid never touches it. This is the *defining* difference from this repo's lean strategy: the POI is
the **deep-Fibonacci OTE retracement band** of a BOS impulse leg, actionable only when **OB / Breaker /
FVG confluence** overlaps it (or sits within an ATR distance) and clears `min_confluence_score` — NOT
simply "the FVG."

Causal: each POI's ``created_index`` is the leg-end swing confirmation; PD-array mitigation is evaluated
on bars ``<= created_index``. Pure function (explicit params, no engine state) for testability.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd

from mtf_smc.smc.confluence import confluence_score, find_breaker, find_order_block, fvg_as_pd, is_mitigated
from mtf_smc.smc.legacy_structure import detect_bos_legs, detect_displacement_fvgs


@dataclass(frozen=True)
class LegacyPOI:
    direction: str
    zone_lower: float        # deep-Fib OTE entry band (price pierces this to arm the M5 monitor)
    zone_upper: float
    created_index: int       # leg-end confirmation (no-look-ahead gate)
    leg_low: float
    leg_high: float
    protective_level: float  # the leg's protected extreme (stop = this -/+ ATR buffer)
    confluence_score: int
    ext_be: float            # 1.618 extension (BE / partial-target anchor)
    ext_tp: float            # 4.236 extension (hybrid-Fib TP anchor)

    def contains(self, price: float) -> bool:
        return self.zone_lower <= price <= self.zone_upper


def build_confluence_pois(
    df: pd.DataFrame, direction: str, atr: pd.Series, *, swing_lookback: int = 2,
    min_retracement: float = 0.5, ob_use_wick: bool = False, fvg_min_atr_mult: float = 0.10,
    disp_atr_mult: float = 1.5, disp_body_ratio: float = 0.5, confluence_overlap_pct: float = 0.5,
    confluence_atr_dist: float = 0.5, min_confluence_score: int = 2,
    fib_ext_be: float = 1.618, fib_ext_tp: float = 4.236,
) -> List[LegacyPOI]:
    """Confluence POIs along ``direction`` from BOS impulse legs (deep-Fib OTE + PD-array confluence)."""
    legs = detect_bos_legs(df, direction, swing_lookback)
    fvgs = detect_displacement_fvgs(df, direction, atr, fvg_min_atr_mult, disp_atr_mult, disp_body_ratio)
    atr_a = atr.to_numpy()
    n = len(df)
    pois: List[LegacyPOI] = []
    for b in legs:
        created = b.confirm_index
        if created >= n:
            continue                                          # leg not yet confirmed in range
        zone = b.leg.retracement_zone(min_retracement, 1.0)   # deep-Fib OTE band (sorted low, high)

        arrays = []
        if b.origin_index >= 0:
            ob = find_order_block(df, b.origin_index, direction, ob_use_wick)
            if ob is not None:
                arrays.append(ob)
        if b.broken_index >= 0:
            br = find_breaker(df, b.broken_index, direction)
            if br is not None:
                arrays.append(br)
        for f in fvgs:
            if b.origin_index <= f.confirm_index <= created:  # FVG inside the impulse leg
                arrays.append(fvg_as_pd(f.lower, f.upper, direction, f.confirm_index))

        unmitigated = [a for a in arrays if not is_mitigated(df, a, created)]
        atr_val = float(atr_a[created]) if created < len(atr_a) else float("nan")
        score, _ = confluence_score(zone, unmitigated, atr_val,
                                    confluence_overlap_pct, confluence_atr_dist)
        if score < min_confluence_score:
            continue
        pois.append(LegacyPOI(
            direction=direction, zone_lower=zone[0], zone_upper=zone[1], created_index=created,
            leg_low=b.leg.low, leg_high=b.leg.high,
            protective_level=(b.leg.low if direction == "long" else b.leg.high),
            confluence_score=score, ext_be=b.leg.extension(fib_ext_be), ext_tp=b.leg.extension(fib_ext_tp),
        ))
    return pois
