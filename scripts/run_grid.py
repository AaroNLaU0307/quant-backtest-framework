"""Run the 42-config primary grid on IN-SAMPLE data and write the master comparison table.

Naive O(M1) loop (no idle-bar skipping). Optionally restrict to a date slice for quick dev runs:

    .venv\\Scripts\\python scripts\\run_grid.py                 # full IS 2015-2022
    .venv\\Scripts\\python scripts\\run_grid.py 2018:2019       # a slice

Writes output/grid/master_table.csv and prints the table sorted by expectancy.
"""
from __future__ import annotations

import sys
import time

import pandas as pd

from mtf_smc.config import REPO_ROOT, DataConfig
from mtf_smc.data.loader import load_is
from mtf_smc.grid import apply_multiple_testing, enumerate_primary_grid, run_grid

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)


def main() -> None:
    m1 = load_is(DataConfig())
    slice_arg = next((a for a in sys.argv[1:] if ":" in a), None)
    if slice_arg:
        a, b = slice_arg.split(":")
        m1 = m1.loc[a:b]
    configs = enumerate_primary_grid()

    out_dir = REPO_ROOT / "output" / "grid"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = out_dir / "master_raw.csv"
    prog = out_dir / "progress.log"
    if "fresh" in sys.argv:                          # clean start (else resume from master_raw.csv)
        for f in (raw, prog):
            f.unlink(missing_ok=True)

    print(f"grid: {len(configs)} configs over {m1.index[0]} -> {m1.index[-1]} ({len(m1):,} M1 bars)")
    print(f"progress -> {prog}   (poll this file)\n")

    t0 = time.time()
    df = run_grid(m1, configs, verbose=True, progress_file=prog, incremental_csv=raw)
    df = apply_multiple_testing(df, n_trials=len(configs))
    print(f"\ndone in {time.time() - t0:.0f}s")

    df.to_csv(out_dir / "master_table.csv", index=False)

    cols = ["config_id", "n_trades", "win_rate", "expectancy_R", "expectancy_ci_lo",
            "expectancy_ci_hi", "p_value", "bh_reject", "sharpe", "dsr", "max_drawdown_pct"]
    shown = df[cols].sort_values("expectancy_R", ascending=False)
    print("\n=== master table (sorted by E[R]; CI/p_value/bh_reject/dsr = corrected significance) ===")
    print(shown.to_string(index=False))
    n_sig = int(df["bh_reject"].sum())
    print(f"\nconfigs surviving BH-FDR (mean R>0): {n_sig}/{len(df)}  |  "
          f"max DSR={df['dsr'].max():.3f}")
    print(f"wrote {out_dir / 'master_table.csv'}")


if __name__ == "__main__":
    main()
