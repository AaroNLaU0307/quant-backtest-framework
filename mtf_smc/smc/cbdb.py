"""TK-style CB/DB break detectors — ported from the old `smc_structure.py` M5 entry-trigger layer,
translated to English, built on this repo's verified swing primitives.

**OFF-BY-DEFAULT** legacy machinery (`docs/MERGE_PLAN.md`, M2a). Not imported by the 42-config grid
path, so the grid stays bit-identical. CB/DB is the alternative structure confirmation to MSS in the
legacy entry model (`trigger = FVG AND (MSS OR CB/DB)`):

* **IB** (internal-break reference) = the most recent *confirmed* swing (long: swing low; short: swing
  high). Its body edge is the DB break level; its extreme is the protective level.
* **DB (Dominant Break):** the **first** close through the IB body edge, occurring **>= cbdb_dominant_min
  bars** after the IB — a direct trend-continuation break.
* **CB (Candle Break):** a close through the nearest left-side breakout level (a prior high above the IB
  body edge for longs), distinct from the DB level.

Causal: anchored on right-confirmed swings; breaks judged on closes (`c[i]`, `c[i-1]`); CB level read
from bars left of the IB. Everything depends only on indices ``<= i``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd

from mtf_smc.smc.swings import detect_swings, last_confirmed_swing


@dataclass(frozen=True)
class CBDBEvent:
    direction: str            # 'long' | 'short'
    index: int                # break bar
    timestamp: pd.Timestamp
    break_level: float
    protective_level: float   # the IB swing extreme (for stops)
    kind: str                 # 'cb' | 'db'
    ib_index: int             # the internal-break reference swing's bar


def detect_cbdb_events(df: pd.DataFrame, direction: str, swing_lookback: int = 2,
                       cbdb_lookback: int = 12, cbdb_dominant_min: int = 3) -> List[CBDBEvent]:
    """Ordered CB/DB events along ``direction`` (one signal per IB; DB takes precedence over CB)."""
    o = df["open"].to_numpy(); h = df["high"].to_numpy()
    lo = df["low"].to_numpy(); c = df["close"].to_numpy()
    ts = df.index
    n = len(df)
    L, W, db_min = swing_lookback, cbdb_lookback, cbdb_dominant_min
    long = direction == "long"
    sh, sl = detect_swings(df, L)

    events: List[CBDBEvent] = []
    cur_e = -1
    cur_broken = cur_emitted = False
    level = ib_ext = float("nan")
    cb_level = None

    for i in range(1, n):
        ib = last_confirmed_swing(sl if long else sh, i, L)
        if ib is None:
            continue
        e = ib.index
        if e != cur_e:                                         # new IB -> recompute level / CB level
            cur_e, cur_broken, cur_emitted, cb_level = e, False, False, None
            ib_ext = float(ib.price)
            if long:
                level = float(max(o[e], c[e]))                # IB body top (DB break level)
                for j in range(e - 1, max(-1, e - 1 - W), -1):
                    if h[j] > level:
                        cb_level = float(h[j]); break         # nearest left-side breakout level
            else:
                level = float(min(o[e], c[e]))                # IB body bottom
                for j in range(e - 1, max(-1, e - 1 - W), -1):
                    if lo[j] < level:
                        cb_level = float(lo[j]); break
        if cur_emitted:
            continue

        if long:
            if c[i] > level and c[i - 1] <= level and not cur_broken:
                cur_broken = True
                if (i - e) >= db_min:
                    events.append(CBDBEvent("long", i, ts[i], level, ib_ext, "db", e)); cur_emitted = True
                    continue
            if cb_level is not None and cb_level != level and c[i] > cb_level and c[i - 1] <= cb_level:
                events.append(CBDBEvent("long", i, ts[i], cb_level, ib_ext, "cb", e)); cur_emitted = True
        else:
            if c[i] < level and c[i - 1] >= level and not cur_broken:
                cur_broken = True
                if (i - e) >= db_min:
                    events.append(CBDBEvent("short", i, ts[i], level, ib_ext, "db", e)); cur_emitted = True
                    continue
            if cb_level is not None and cb_level != level and c[i] < cb_level and c[i - 1] >= cb_level:
                events.append(CBDBEvent("short", i, ts[i], cb_level, ib_ext, "cb", e)); cur_emitted = True

    return events
