"""Run the 42-config primary grid on IN-SAMPLE data and write the master comparison table.

Naive O(M1) loop (no idle-bar skipping). Optionally restrict to a date slice for quick dev runs:

    python scripts/run_grid.py fresh --symbol=EURUSD     # full IS 2015-2022, discard earlier rows
    python scripts/run_grid.py --symbol=EURUSD           # resume (same code + config only)
    python scripts/run_grid.py 2018:2019                 # a slice (XAUUSD)
    python scripts/run_grid.py fresh --symbol=GBPJPY --stop-slip-mult=10   # high-slippage-on-stops

Writes output/grid/[<SYM>/]master_table.csv (XAUUSD keeps output/grid/) and prints the table sorted
by expectancy. ``--stop-slip-mult=K`` runs the SPEC §6.5 sensitivity (stop-exit slippage x K) into a
``stopslip_xK/`` subdirectory instead.
"""
from __future__ import annotations

import sys
import time

import pandas as pd

from mtf_smc.config import REPO_ROOT, DataConfig
from mtf_smc.data.loader import load_is
from mtf_smc.engine.costs import CostModel, high_slippage_on_stops
from mtf_smc.grid import apply_multiple_testing, enumerate_primary_grid, run_grid
from mtf_smc.risk.instrument import get_instrument

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)


def main() -> None:
    symbol = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--symbol=")), "XAUUSD")
    cfg = DataConfig.for_symbol(symbol)
    inst = get_instrument(symbol)
    m1 = load_is(cfg)
    slice_arg = next((a for a in sys.argv[1:] if ":" in a), None)
    if slice_arg:
        a, b = slice_arg.split(":")
        m1 = m1.loc[a:b]
    configs = enumerate_primary_grid()

    # XAUUSD keeps the original output/grid/ path (the bit-identical regression target);
    # replication instruments write to output/grid/<symbol>/.
    out_dir = REPO_ROOT / "output" / "grid" if symbol == "XAUUSD" else REPO_ROOT / "output" / "grid" / symbol
    cost = CostModel(inst)
    slip_mult = next((float(a.split("=", 1)[1]) for a in sys.argv[1:] if a.startswith("--stop-slip-mult=")), None)
    if slip_mult is not None:
        cost = high_slippage_on_stops(cost, slip_mult)
        out_dir = out_dir / f"stopslip_x{slip_mult:g}"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = out_dir / "master_raw.csv"
    prog = out_dir / "progress.log"
    if "fresh" in sys.argv:                          # clean start (else resume from master_raw.csv)
        for f in (raw, prog):
            f.unlink(missing_ok=True)

    print(f"grid [{symbol}]: {len(configs)} configs over {m1.index[0]} -> {m1.index[-1]} ({len(m1):,} M1 bars)")
    print(f"progress -> {prog}   (poll this file)\n")

    t0 = time.time()
    df = run_grid(m1, configs, instrument=inst, cost=cost,
                  verbose=True, progress_file=prog, incremental_csv=raw)
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
