"""POI — point of interest: the FVG zone produced by the displacement that caused a BOS/CHoCH,
plus causal mitigation tracking. ``docs/SPEC.md`` §2.6.

The default POI is the qualifying **FVG inside the impulse leg** that produced a structural break,
associated to that break within ``assoc_window`` bars. A POI is **unmitigated** until price trades
back into its zone; only unmitigated POIs are actionable. Mitigation is detected causally (the first
bar at/after formation whose range intersects the zone). The impulse-leg Fib anchoring used for the
pullback zone is assembled in the strategy layer, where the swing indices are available.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from mtf_smc.smc.fvg import FVG
from mtf_smc.smc.structure import StructureEvent


@dataclass(frozen=True)
class POI:
    direction: str       # 'long' | 'short'
    kind: str            # structure kind that formed it: 'BOS' | 'CHoCH'
    event_index: int     # the structural-break bar
    fvg: FVG

    @property
    def lower(self) -> float:
        return self.fvg.lower

    @property
    def upper(self) -> float:
        return self.fvg.upper

    @property
    def formed_index(self) -> int:
        """Bar at which the POI is first knowable (its FVG's confirmation bar)."""
        return self.fvg.confirm_index

    def contains(self, price: float) -> bool:
        return self.lower <= price <= self.upper


def build_pois(
    events: List[StructureEvent],
    fvgs: List[FVG],
    assoc_window: int = 12,
) -> List[POI]:
    """Associate each structural break with the most recent same-direction FVG formed in its run-up.

    The FVG must share the break's direction and confirm within ``[event_index - assoc_window,
    event_index]``. Events with no qualifying FVG produce no POI. ``fvgs`` is assumed ascending by
    ``confirm_index`` (as returned by :func:`mtf_smc.smc.fvg.detect_fvgs`).

    Uses per-direction binary search (O(events·log F)) instead of an O(events·F) scan — identical
    result (latest same-direction FVG in the window), but feasible at M1 scale. The naive scan was a
    profiled hotspot (~315s building one M5 context); this makes it negligible.
    """
    by_dir: Dict[str, List[FVG]] = {"long": [], "short": []}
    for f in fvgs:
        by_dir.setdefault(f.direction, []).append(f)
    ci = {d: np.array([f.confirm_index for f in lst], dtype=np.int64) for d, lst in by_dir.items()}

    pois: List[POI] = []
    for e in events:
        arr = ci.get(e.direction)
        if arr is None or arr.size == 0:
            continue
        left = int(np.searchsorted(arr, e.index - assoc_window, side="left"))
        right = int(np.searchsorted(arr, e.index, side="right"))   # exclusive upper bound
        if right > left:
            pois.append(POI(e.direction, e.kind, e.index, by_dir[e.direction][right - 1]))
    return pois


def mitigation_index(df: pd.DataFrame, poi: POI, start: Optional[int] = None) -> Optional[int]:
    """First bar index at/after formation whose range intersects the POI zone, else ``None``.

    Causal: scans forward from ``start`` (default ``formed_index + 1``); a bar mitigates when
    ``high >= lower and low <= upper``.
    """
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    s = (poi.formed_index + 1) if start is None else start
    for j in range(max(s, 0), len(df)):
        if high[j] >= poi.lower and low[j] <= poi.upper:
            return j
    return None
