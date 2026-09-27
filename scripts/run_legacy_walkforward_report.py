"""L1 walk-forward report (merge M3/M4): pooled OOS E[R] + bootstrap CI, the updated analog of -0.27R.

Reads output/legacy_walkforward/walkforward_windows.csv (from run_legacy_walkforward.py) and reproduces the
old run_walkforward_report.py verdict on the NEW engine: pooled OOS E[R] with 95% bootstrap CI, per-instrument
and per-regime breakdowns, the IS->OOS mean-R gap (overfit tell), and the IS-best parameter drift.

Inference units. Trades inside one OOS window are correlated, so the headline CI is the **block
bootstrap over windows** (whole windows resampled); the iid trade-level CI is shown only as the
optimistic reference. One instrument's OOS windows do not overlap (step = OOS length; the IS windows
do), but XAUUSD and EURUSD roll the **same 12 calendar periods**, so their 24 windows are not 24
independent signs: the sign test runs on the 12 calendar periods, each period's trades pooled across
both instruments.

    python scripts/run_legacy_walkforward_report.py
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from mtf_smc.provenance import PROVENANCE_COLUMNS, git_commit
from mtf_smc.robustness.stats import block_bootstrap_mean_ci, bootstrap_mean_ci
from mtf_smc.robustness.walkforward import period_sign_test

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "output", "legacy_walkforward")


def _window_arrays(rows: pd.DataFrame) -> list:
    """Per-window OOS R arrays (each window is one correlated block); malformed rows raise."""
    return [np.asarray(json.loads(s), dtype=float) for s in rows["oos_R_json"]]


def _R(rows: pd.DataFrame) -> np.ndarray:
    arrs = _window_arrays(rows)
    return np.concatenate(arrs) if arrs else np.array([])


def _agg(rows: pd.DataFrame, label: str) -> str:
    R = _R(rows)
    if len(R) == 0:
        return f"  {label:34s}: OOS no trades"
    mean, lo, hi = bootstrap_mean_ci(R)
    return f"  {label:34s}: OOS_N={len(R):3d}  E[R]={mean:+.3f}  iid trade-level 95%CI=[{lo:+.3f},{hi:+.3f}]"


def _check_pairing(df: pd.DataFrame) -> None:
    """Every instrument must cover the same calendar OOS periods (the sign test pairs them)."""
    periods = {sym: set(g["oos_start"].astype(str)) for sym, g in df.groupby("symbol")}
    union = set().union(*periods.values())
    missing = {sym: sorted(union - p) for sym, p in periods.items() if union - p}
    if missing:
        raise ValueError(f"walk-forward windows missing for some calendar periods: {missing}")


def main() -> None:
    df = pd.read_csv(os.path.join(OUT, "walkforward_windows.csv"), dtype={c: str for c in PROVENANCE_COLUMNS})
    _check_pairing(df)
    df["oos_r_num"] = pd.to_numeric(df["oos_r"], errors="coerce")
    df["is_r_num"] = pd.to_numeric(df["is_r"], errors="coerce")
    pair = df[df["oos_r_num"].notna() & df["is_r_num"].notna()]
    gap = float((pair["is_r_num"] - pair["oos_r_num"]).mean()) if len(pair) else float("nan")
    is2020 = df[df["oos_start"] < "2020-01-01"]
    is2023 = df[df["oos_start"] >= "2020-01-01"]

    R_all = _R(df)
    blocks = [a for a in _window_arrays(df) if a.size]
    blo, bhi = block_bootstrap_mean_ci(blocks)
    nmean = float(R_all.mean()) if len(R_all) else float("nan")
    st = period_sign_test(df)
    wr = df["oos_r_num"].dropna().to_numpy()
    n_w, n_neg = len(wr), int((wr < 0).sum())
    codes = sorted(set(df["code_hash"].dropna())) if "code_hash" in df else ["(none recorded)"]

    L = ["=" * 82,
         "L1 walk-forward OOS summary (verdict = OOS only; new engine, legacy_smc)", "=" * 82,
         f"  provenance: windows code_hash={','.join(codes)}  report git_commit={git_commit()}",
         (f"  ALL pooled (EUR+XAU): OOS_N={len(R_all)}  E[R]={nmean:+.3f}  "
          f"95% CI, block bootstrap over {len(blocks)} windows = [{blo:+.3f}, {bhi:+.3f}]"),
         (f"  sign test over {st['n_periods']} calendar OOS periods (both instruments pooled per period): "
          f"{st['n_negative']}/{st['n_periods']} negative, one-sided p = {st['p_value']:.4f}"),
         "-" * 82,
         "  breakdowns (iid trade-level CIs: optimistically narrow, trades within a window correlate):",
         _agg(df, "ALL pooled (EUR+XAU)"),
         _agg(df[df["symbol"] == "EURUSD"], "EURUSD"),
         _agg(df[df["symbol"] == "XAUUSD"], "XAUUSD"),
         _agg(is2020, "OOS in 2016-2019 (calm regime)"),
         _agg(is2023, "OOS in 2020-2022 (trend regime)"),
         (f"  per-window OOS mean-R (descriptive; XAU and EUR windows share calendar periods): "
          f"{n_neg}/{n_w} windows negative; median={np.median(wr):+.3f} mean={wr.mean():+.3f} "
          f"min={wr.min():+.3f} max={wr.max():+.3f}"),
         "-" * 82,
         f"  IS->OOS mean gap (IS_r - OOS_r) = {gap:+.3f}   (large = IS overfit)",
         f"  windows={len(df)}  with OOS trades={int((df['oos_n'] > 0).sum())}",
         "-" * 82,
         "  IS-best params per window (large drift = overfit signal):"]
    for _, r in df.iterrows():
        oos = r["oos_r"] if str(r["oos_r"]) not in ("", "nan") else "-"
        L.append(f"     {r['symbol']} {r['oos_start']}: best={r['best']}  IS_r={r['is_r']}->OOS_r={oos} (N{r['oos_n']})")

    if len(R_all):
        if bhi < 0:
            v = "(A) no robust edge - OOS significantly negative (block-bootstrap CI below 0)."
        elif blo < 0 < bhi:
            v = "(A/C) no provable edge - OOS block-bootstrap CI crosses 0, indistinguishable from zero."
        else:
            v = "(B) OOS significantly positive - potential edge, needs further validation."
        L += ["-" * 82, f"  VERDICT: {v}",
              ("  [old earlier-engine walk-forward, for reference: pooled OOS E[R] = -0.27 over EUR+XAU "
               "2015-2023; this updated run is on the sealed-wall IS span 2015-2022]")]
    report = "\n".join(L)
    print(report)
    with open(os.path.join(OUT, "walkforward_summary.txt"), "w", encoding="utf-8") as fh:
        fh.write(report + "\n")


if __name__ == "__main__":
    main()
