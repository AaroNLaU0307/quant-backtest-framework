"""Legacy M5 entry trigger — `FVG AND (MSS OR CB/DB)` — ported from the old `detect_mss_events`.

**OFF-BY-DEFAULT** (`docs/MERGE_PLAN.md`, M2). Imported only by `entry_model="legacy_smc"`. The
mandatory gate is a displacement-FVG; structure confirmation is MSS and/or a TK CB/DB break
(`structure_confirm_mode` ∈ {any, mss_only, cbdb_only}). On ties the MSS is preferred; one trigger per
bar. An optional ``poi_zone`` requires the protective level to sit inside the pierced POI.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from mtf_smc.smc.cbdb import detect_cbdb_events
from mtf_smc.smc.legacy_structure import detect_displacement_fvgs, detect_mss_breaks


@dataclass(frozen=True)
class LegacyTrigger:
    direction: str
    break_index: int
    broken_level: float
    protective_swing: float
    fvg_lower: float
    fvg_upper: float
    fvg_confirm_index: int
    kind: str                # 'mss' | 'cb' | 'db'


def detect_legacy_triggers(
    df: pd.DataFrame, direction: str, atr: pd.Series, *, swing_lookback: int = 2,
    structure_confirm_mode: str = "any", require_fvg: bool = True, fvg_assoc_window: int = 12,
    fvg_min_atr_mult: float = 0.10, disp_atr_mult: float = 1.5, disp_body_ratio: float = 0.5,
    cbdb_lookback: int = 12, cbdb_dominant_min: int = 3,
    poi_zone: Optional[Tuple[float, float]] = None,
) -> List[LegacyTrigger]:
    """Ordered entry triggers along ``direction`` (`FVG AND (MSS OR CB/DB)`)."""
    fvgs = detect_displacement_fvgs(df, direction, atr, fvg_min_atr_mult, disp_atr_mult, disp_body_ratio)
    atr_a = atr.to_numpy()
    n = len(df)

    struct_breaks: List[Tuple[int, float, float, str]] = []
    if structure_confirm_mode in ("any", "mss_only"):
        for (i, broken, prot) in detect_mss_breaks(df, direction, swing_lookback, atr):
            struct_breaks.append((i, broken, prot, "mss"))
    if structure_confirm_mode in ("any", "cbdb_only"):
        for ev in detect_cbdb_events(df, direction, swing_lookback, cbdb_lookback, cbdb_dominant_min):
            struct_breaks.append((ev.index, ev.break_level, ev.protective_level, ev.kind))
    struct_breaks.sort(key=lambda x: (x[0], 0 if x[3] == "mss" else 1))   # MSS preferred on ties

    def assoc_fvg(i: int):
        cand = None
        for f in fvgs:                                        # ordered by confirm_index -> nearest kept
            if (i - fvg_assoc_window) <= f.confirm_index <= i:
                cand = f
        return cand

    out: List[LegacyTrigger] = []
    seen: set = set()
    for (i, broken, prot, kind) in struct_breaks:
        if i in seen or i >= n or np.isnan(atr_a[i]):
            continue
        f = assoc_fvg(i)
        if require_fvg and f is None:                         # FVG is the hard gate
            continue
        if poi_zone is not None:
            lo, hi = min(poi_zone), max(poi_zone)
            if not (lo <= prot <= hi):
                continue
        seen.add(i)
        out.append(LegacyTrigger(
            direction, i, broken, prot,
            f.lower if f else float("nan"), f.upper if f else float("nan"),
            f.confirm_index if f else -1, kind,
        ))
    return out
