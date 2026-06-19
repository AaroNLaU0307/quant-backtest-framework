"""L1 walk-forward report (merge M3/M4): pooled OOS E[R] + bootstrap CI, the updated analog of -0.27R.

Reads output/legacy_walkforward/walkforward_windows.csv (from run_legacy_walkforward.py) and reproduces the
old run_walkforward_report.py verdict on the NEW engine: pooled OOS E[R] with 95% bootstrap CI, per-instrument
and per-regime breakdowns, the IS->OOS mean-R gap (overfit tell), and the IS-best parameter drift.

    .venv\\Scripts\\python scripts\\run_legacy_walkforward_report.py
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from mtf_smc.robustness.stats import bootstrap_mean_ci

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "output", "legacy_walkforward")


def _R(rows: pd.DataFrame) -> np.ndarray:
    arrs = []
    for s in rows["oos_R_json"]:
        try:
            arrs.append(np.array(json.loads(s), dtype=float))
        except Exception:
            pass
    return np.concatenate(arrs) if arrs else np.array([])


def _agg(rows: pd.DataFrame, label: str) -> str:
    R = _R(rows)
    if len(R) == 0:
        return f"  {label:34s}: OOS no trades"
    mean, lo, hi = bootstrap_mean_ci(R)
    tag = ("  CI crosses 0 (indistinguishable from zero)" if lo < 0 < hi
           else "  significantly NEGATIVE" if hi < 0 else "  significantly POSITIVE")
    return f"  {label:34s}: OOS_N={len(R):3d}  E[R]={mean:+.3f}  95%CI=[{lo:+.3f},{hi:+.3f}]{tag}"


def main() -> None:
    df = pd.read_csv(os.path.join(OUT, "walkforward_windows.csv"))
    df["oos_r_num"] = pd.to_numeric(df["oos_r"], errors="coerce")
    df["is_r_num"] = pd.to_numeric(df["is_r"], errors="coerce")
    pair = df[df["oos_r_num"].notna() & df["is_r_num"].notna()]
    gap = float((pair["is_r_num"] - pair["oos_r_num"]).mean()) if len(pair) else float("nan")
    is2020 = df[df["oos_start"] < "2020-01-01"]
    is2023 = df[df["oos_start"] >= "2020-01-01"]

    L = ["=" * 82,
         "L1 walk-forward OOS summary (verdict = OOS only; new engine, legacy_smc)", "=" * 82,
         _agg(df, "ALL pooled (EUR+XAU)"),
         _agg(df[df["symbol"] == "EURUSD"], "EURUSD"),
         _agg(df[df["symbol"] == "XAUUSD"], "XAUUSD"),
         _agg(is2020, "OOS in 2016-2019 (calm regime)"),
         _agg(is2023, "OOS in 2020-2022 (trend regime)"),
         "-" * 82,
         f"  IS->OOS mean gap (IS_r - OOS_r) = {gap:+.3f}   (large = IS overfit)",
         f"  windows={len(df)}  with OOS trades={int((df['oos_n'] > 0).sum())}",
         "-" * 82,
         "  IS-best params per window (large drift = overfit signal):"]
    for _, r in df.iterrows():
        oos = r["oos_r"] if str(r["oos_r"]) not in ("", "nan") else "-"
        L.append(f"     {r['symbol']} {r['oos_start']}: best={r['best']}  IS_r={r['is_r']}->OOS_r={oos} (N{r['oos_n']})")

    R_all = _R(df)
    if len(R_all):
        mean, lo, hi = bootstrap_mean_ci(R_all)
        if hi < 0:
            v = "(A) no robust edge - OOS significantly negative."
        elif lo < 0 < hi:
            v = "(A/C) no provable edge - OOS CI crosses 0, indistinguishable from zero."
        else:
            v = "(B) OOS significantly positive - potential edge, needs further validation."
        L += ["-" * 82, f"  VERDICT: {v}",
              "  [old earlier-engine walk-forward, for reference: pooled OOS E[R] = -0.27 over EUR+XAU "
              "2015-2023; this updated run is on the sealed-wall IS span 2015-2022]"]
    report = "\n".join(L)
    print(report)
    with open(os.path.join(OUT, "walkforward_summary.txt"), "w", encoding="utf-8") as fh:
        fh.write(report + "\n")


if __name__ == "__main__":
    main()
