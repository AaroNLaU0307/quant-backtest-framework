"""Smoke-check the SMC primitives on real IN-SAMPLE data (counts only, no assertions).

Confirms the detectors run on real H4/H1/D1 series and produce sane magnitudes. Uses load_is, so
it never touches the locked OOS.

Usage:  .venv\\Scripts\\python scripts\\smoke_primitives.py
"""
from __future__ import annotations

from mtf_smc.config import DataConfig
from mtf_smc.data.loader import load_is
from mtf_smc.data.resample import resample_ohlc
from mtf_smc.indicators.atr import atr_wilder
from mtf_smc.indicators.ema import vegas_bias
from mtf_smc.smc.fvg import detect_fvgs
from mtf_smc.smc.poi import build_pois
from mtf_smc.smc.structure import detect_structure
from mtf_smc.smc.swings import detect_swings


def main() -> None:
    cfg = DataConfig()
    m1 = load_is(cfg, verbose=True)
    print(f"session anchor (D1/W1) = {cfg.session_anchor}")
    print(f"{'tf':>3} | {'bars':>7} | {'sw H/L':>11} | {'fvgs':>6} | {'BOS/CHoCH':>10} | "
          f"{'pois':>5} | bias L/S/none")
    for tf in ("W1", "D1", "H4", "H1"):
        df = resample_ohlc(m1, tf, anchor=cfg.session_anchor)
        atr = atr_wilder(df, 14)
        sh, sl = detect_swings(df, 2)
        fvgs = detect_fvgs(df, min_size_atr=0.10, atr=atr)
        ev = detect_structure(df, 2)
        pois = build_pois(ev, fvgs, assoc_window=12)
        bias = vegas_bias(df["close"])
        bos = sum(e.kind == "BOS" for e in ev)
        choch = sum(e.kind == "CHoCH" for e in ev)
        nl = int((bias == "long").sum()); ns = int((bias == "short").sum()); nn = int((bias == "none").sum())
        print(f"{tf:>3} | {len(df):>7} | {len(sh):>5}/{len(sl):<5} | {len(fvgs):>6} | "
              f"{bos:>4}/{choch:<5} | {len(pois):>5} | {nl}/{ns}/{nn}")


if __name__ == "__main__":
    main()
