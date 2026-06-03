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
from mtf_smc.grid import enumerate_primary_grid, run_grid

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)


def main() -> None:
    m1 = load_is(DataConfig())
    if len(sys.argv) > 1 and ":" in sys.argv[1]:
        a, b = sys.argv[1].split(":")
        m1 = m1.loc[a:b]
    configs = enumerate_primary_grid()
    print(f"grid: {len(configs)} configs over {m1.index[0]} -> {m1.index[-1]} ({len(m1):,} M1 bars)\n")

    t0 = time.time()
    df = run_grid(m1, configs, verbose=True)
    print(f"\ndone in {time.time() - t0:.0f}s")

    out_dir = REPO_ROOT / "output" / "grid"
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "master_table.csv", index=False)

    cols = ["config_id", "n_trades", "win_rate", "expectancy_R", "profit_factor",
            "sharpe", "max_drawdown_pct", "final_equity"]
    shown = df[cols].sort_values("expectancy_R", ascending=False)
    print("\n=== master table (sorted by E[R]) ===")
    print(shown.to_string(index=False))
    print(f"\nwrote {out_dir / 'master_table.csv'}")


if __name__ == "__main__":
    main()
