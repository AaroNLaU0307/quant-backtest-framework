"""Single-config end-to-end sanity run on a small IN-SAMPLE slice (docs/SPEC.md §10 step 4).

Runs a couple of configs over ~2 years of IS data and prints setup/trade counts, a quick expectancy
summary, and the first few trades — to confirm the full detection -> setup -> intrabar-fill pipeline
works before scaling to the 42-config grid. Not a result; just a smoke check.

Usage:  .venv\\Scripts\\python scripts\\sanity_backtest.py
"""
from __future__ import annotations

import time

from mtf_smc.config import DataConfig, StrategyConfig
from mtf_smc.data.loader import load_is
from mtf_smc.engine.backtester import run_backtest


def summarize(res) -> None:
    df = res.trades_df
    print(f"  setups={res.n_setups}  trades={res.n_trades}  final_equity={res.final_equity:,.0f}")
    if res.n_trades == 0:
        return
    R = df["R"]
    wins = (R > 0).mean()
    by_reason = df["exit_reason"].value_counts().to_dict()
    print(f"  win%={wins:.1%}  E[R]={R.mean():+.3f}  sumR={R.sum():+.1f}  "
          f"maxDD_trades?  exit_reasons={by_reason}")
    cols = ["entry_ts", "exit_ts", "direction", "exit_reason", "R", "lots", "entry", "initial_stop"]
    print(df[cols].head(6).to_string(index=False))


def main() -> None:
    m1 = load_is(DataConfig())
    sl = m1.loc["2018-01-01":"2019-12-31"]
    print(f"slice: {sl.index[0]} -> {sl.index[-1]}  M1 bars={len(sl):,}\n")

    configs = [
        StrategyConfig(entry_model="direct", htf="D1", tp_mode="fixed_3R"),
        StrategyConfig(entry_model="direct", htf="D1", tp_mode="scale_2R_then_HTF"),
        StrategyConfig(entry_model="cascade", htf="D1", mtf="H1", ltf="M15", tp_mode="fixed_3R"),
    ]
    for cfg in configs:
        tag = f"{cfg.entry_model} htf={cfg.htf} mtf={cfg.mtf} ltf={cfg.ltf} tp={cfg.tp_mode}"
        t0 = time.time()
        res = run_backtest(sl, cfg)
        print(f"=== {tag}  ({time.time() - t0:.1f}s) ===")
        summarize(res)
        print()


if __name__ == "__main__":
    main()
