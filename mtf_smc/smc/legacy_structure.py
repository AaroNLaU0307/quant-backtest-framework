"""Legacy SMC structure layer — faithfully ported from the OLD repo's local working tree
(`smc_mtf/structure.py` `detect_bos` + `smc_structure.py` MSS / displacement-FVG), translated to
English, built on this repo's verified swing primitives.

**OFF-BY-DEFAULT** (`docs/MERGE_PLAN.md`, M2). Imported only by `entry_model="legacy_smc"`; the
pre-registered 42-grid never touches it, so the grid stays bit-identical. These reproduce the OLD
strategy's *exact* structure rules, which differ from this repo's lean detectors:

* **BOS legs** — a higher-high (long) / lower-low (short) between **consecutive confirmed swings** marks
  trend continuation; the impulse leg runs from the nearest opposing swing before the new extreme to
  that extreme (for Fib/OB anchoring). This is a swing-*structure* break, NOT a close-of-level break.
* **MSS** — the first close through the latest confirmed opposing swing extreme (long: close above the
  latest confirmed swing high), protective = latest confirmed same-direction swing; deduped by reference.
* **Displacement-FVG** — a 3-candle gap whose middle candle is a *displacement* (range ≥ `disp_atr_mult`·ATR
  and body/range ≥ `disp_body_ratio`) and whose gap ≥ `fvg_min_atr_mult`·ATR. (Stricter than the lean FVG.)

All causal: swings are right-confirmed; breaks judged on closes; everything depends on indices ``<= i``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from mtf_smc.indicators.fib import FibLeg
from mtf_smc.smc.swings import Swing, detect_swings, last_confirmed_swing


# --------------------------------------------------------------------------- #
# BOS legs (impulse-leg anchoring for the confluence POI)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BOSLeg:
    direction: str
    leg: FibLeg
    broken_level: float
    broken_index: int        # prior same-side swing bar (breaker re-scan)
    break_index: int         # first close through the prior extreme
    confirm_index: int       # leg-end swing confirmation (no-look-ahead gate)
    origin_index: int        # impulse start bar (OB re-scan)


def _latest_before(swings: List[Swing], idx: int) -> Optional[Swing]:
    res: Optional[Swing] = None
    for s in swings:
        if s.index < idx:
            res = s
        else:
            break
    return res


def _first_close_break(closes: np.ndarray, prev: Swing, cur: Swing, direction: str) -> int:
    lo, hi = prev.index + 1, min(cur.index, len(closes) - 1)
    for i in range(lo, hi + 1):
        if direction == "long" and closes[i] > prev.price:
            return i
        if direction == "short" and closes[i] < prev.price:
            return i
    return cur.index                                          # fallback: the new extreme's own bar


def detect_bos_legs(df: pd.DataFrame, direction: str, swing_lookback: int = 2) -> List[BOSLeg]:
    """Continuation BOS legs along ``direction`` (HH for long, LL for short)."""
    sh, sl = detect_swings(df, swing_lookback)
    closes = df["close"].to_numpy()
    L = swing_lookback
    primary, opposite = (sh, sl) if direction == "long" else (sl, sh)
    out: List[BOSLeg] = []
    for k in range(1, len(primary)):
        prev, cur = primary[k - 1], primary[k]
        broke = cur.price > prev.price if direction == "long" else cur.price < prev.price
        if not broke:
            continue
        origin = _latest_before(opposite, cur.index)          # nearest opposing swing before the extreme
        if origin is None:
            continue
        bi = _first_close_break(closes, prev, cur, direction)
        if direction == "long":
            leg = FibLeg("long", low=origin.price, high=cur.price,
                         low_index=origin.index, high_index=cur.index)
        else:
            leg = FibLeg("short", low=cur.price, high=origin.price,
                         low_index=cur.index, high_index=origin.index)
        if leg.range <= 0:
            continue
        out.append(BOSLeg(direction, leg, prev.price, prev.index, bi, cur.index + L, origin.index))
    return out


# --------------------------------------------------------------------------- #
# MSS (M5 structure confirmation #1)
# --------------------------------------------------------------------------- #
def detect_mss_breaks(df: pd.DataFrame, direction: str, swing_lookback: int = 2,
                      atr: Optional[pd.Series] = None) -> List[Tuple[int, float, float]]:
    """First close-break of the latest confirmed opposing swing extreme; deduped by reference swing.

    Returns ``(break_index, broken_level, protective_price)`` tuples. If ``atr`` is given, bars where
    ATR is NaN are skipped (matches the old detector's warm-up behaviour).
    """
    sh, sl = detect_swings(df, swing_lookback)
    closes = df["close"].to_numpy()
    n = len(df)
    L = swing_lookback
    out: List[Tuple[int, float, float]] = []
    last_ref = -1
    for i in range(1, n):
        if atr is not None and np.isnan(atr.iloc[i]):
            continue
        if direction == "long":
            ref = last_confirmed_swing(sh, i, L)
            if ref is None or ref.index == last_ref:
                continue
            if closes[i] > ref.price and closes[i - 1] <= ref.price:
                prot = last_confirmed_swing(sl, i, L)
                if prot is None:
                    continue
                out.append((i, ref.price, prot.price)); last_ref = ref.index
        else:
            ref = last_confirmed_swing(sl, i, L)
            if ref is None or ref.index == last_ref:
                continue
            if closes[i] < ref.price and closes[i - 1] >= ref.price:
                prot = last_confirmed_swing(sh, i, L)
                if prot is None:
                    continue
                out.append((i, ref.price, prot.price)); last_ref = ref.index
    return out


# --------------------------------------------------------------------------- #
# Displacement-FVG (the legacy POI factor + M5 entry zone)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DisplacementFVG:
    direction: str
    disp_index: int          # middle (displacement) candle
    confirm_index: int       # third candle (gap confirmed at its close)
    upper: float
    lower: float


def _is_displacement(o, h, lo, c, atr_a, i, disp_atr_mult: float, disp_body_ratio: float) -> bool:
    a = atr_a[i]
    if np.isnan(a) or a <= 0:
        return False
    rng = h[i] - lo[i]
    if rng <= 0:
        return False
    return (rng >= disp_atr_mult * a) and (abs(c[i] - o[i]) / rng >= disp_body_ratio)


def detect_displacement_fvgs(df: pd.DataFrame, direction: str, atr: pd.Series,
                             fvg_min_atr_mult: float = 0.10, disp_atr_mult: float = 1.5,
                             disp_body_ratio: float = 0.5) -> List[DisplacementFVG]:
    """3-candle FVGs whose middle candle is a displacement and whose gap clears the size filter."""
    o = df["open"].to_numpy(); h = df["high"].to_numpy()
    lo = df["low"].to_numpy(); c = df["close"].to_numpy()
    atr_a = atr.to_numpy()
    n = len(df)
    out: List[DisplacementFVG] = []
    for mid in range(1, n - 1):
        a = atr_a[mid]
        if np.isnan(a):
            continue
        if direction == "long" and lo[mid + 1] > h[mid - 1]:
            if (lo[mid + 1] - h[mid - 1]) >= fvg_min_atr_mult * a and \
                    _is_displacement(o, h, lo, c, atr_a, mid, disp_atr_mult, disp_body_ratio):
                out.append(DisplacementFVG("long", mid, mid + 1, float(lo[mid + 1]), float(h[mid - 1])))
        if direction == "short" and h[mid + 1] < lo[mid - 1]:
            if (lo[mid - 1] - h[mid + 1]) >= fvg_min_atr_mult * a and \
                    _is_displacement(o, h, lo, c, atr_a, mid, disp_atr_mult, disp_body_ratio):
                out.append(DisplacementFVG("short", mid, mid + 1, float(lo[mid - 1]), float(h[mid + 1])))
    return out
