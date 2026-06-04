"""Step-5 capstone: robustness on grid survivors (IS only). Monitored via output/robustness/progress.log.

The on-screen pass uses ``N_null`` random-entry nulls (default 300 = PRELIMINARY; pass an int to
change). **The REPORT version must use >= 1000** (tail percentiles are noisy at 300).

Since every config has negative E[R], the random-entry decomposition is reported as the **signed
difference strategy_E[R] - null_E[R]** for both nulls (not just a percentile): if the bias-matched
null is *less negative* than the strategy, the SMC structure (POI/FVG/CHoCH) is actively making
results worse than random entry under the same trend filter.

Usage:  .venv\\Scripts\\python scripts\\run_robustness.py [N_null]
"""
from __future__ import annotations

import sys
import time

import pandas as pd

from mtf_smc.config import REPO_ROOT, DataConfig, StrategyConfig
from mtf_smc.data.loader import load_is
from mtf_smc.engine.backtester import run_backtest
from mtf_smc.engine.costs import CostModel
from mtf_smc.grid import enumerate_primary_grid
from mtf_smc.reporting.explain import explain_trade
from mtf_smc.risk.instrument import XAUUSD
from mtf_smc.robustness.montecarlo import monte_carlo
from mtf_smc.robustness.random_entry import random_entry_benchmark
from mtf_smc.robustness.walkforward import regime_breakdown, walk_forward_by_year

MIN_TRADES = 30
TOP_N = 3


def _find_scale_be_example(m1, cost):
    for cfg in (StrategyConfig(entry_model="cascade", htf="D1", mtf="H1", ltf="M15",
                               tp_mode="scale_2R_then_HTF"),
                StrategyConfig(entry_model="direct", htf="D1", tp_mode="scale_2R_then_HTF")):
        res = run_backtest(m1, cfg, cost=cost)
        for t in res.trades:
            if any(f.reason == "scale_2R" for f in t.fills) and t.exit_reason == "be_stop":
                return t
    return None


def main() -> None:
    n_null = int(next((a for a in sys.argv[1:] if a.isdigit()), 300))
    label = "PRELIMINARY" if n_null < 1000 else "REPORT-GRADE"
    out_dir = REPO_ROOT / "output" / "robustness"
    out_dir.mkdir(parents=True, exist_ok=True)
    pf = open(out_dir / "progress.log", "w", encoding="utf-8")

    def log(msg: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {msg}"
        pf.write(line + "\n"); pf.flush()
        print(line, flush=True)

    log(f"capstone start: N_null={n_null} [{label}]")
    cost = CostModel(XAUUSD)
    master = pd.read_csv(REPO_ROOT / "output" / "grid" / "master_table.csv")
    by_id = {c.config_id: c for c in enumerate_primary_grid()}
    elig = master[master["n_trades"] >= MIN_TRADES].sort_values("expectancy_R", ascending=False)
    survivors = list(elig["config_id"].head(TOP_N))
    log(f"survivors (N>={MIN_TRADES}, top {TOP_N} by E[R]): {survivors or 'NONE'}")
    m1 = load_is(DataConfig())

    for cid in survivors:
        cfg = by_id[cid]
        t0 = time.time()
        res = run_backtest(m1, cfg, cost=cost)
        R = [t.realized_R for t in res.trades]
        log(f"=== {cid}  N={res.n_trades}  E[R]={pd.Series(R).mean():+.3f}  (backtest {time.time()-t0:.0f}s) ===")

        mc = monte_carlo(R, risk_pct=cfg.risk_pct, n_runs=10_000, seed=cfg.seed)
        log(f"  MC max-DD bootstrap p50={mc.maxdd_bootstrap_pct['p50']:.1%} "
            f"p05={mc.maxdd_bootstrap_pct['p05']:.1%}  risk-of-ruin={mc.risk_of_ruin}")

        log(f"  random-entry: resolving {n_null} nulls x 2 (this is the slow step) ...")
        t1 = time.time()
        re_res = random_entry_benchmark(m1, cfg, res.trades, n_runs=n_null, seed=cfg.seed,
                                        cost=cost, ctx=res.context)
        for name, nr in re_res.items():
            e = nr.expectancy_R
            log(f"  [{name:<12}] strat E[R]={e.strategy:+.3f}  null E[R]={e.null_mean:+.3f}  "
                f"diff(strat-null)={e.strategy - e.null_mean:+.3f}  pct={e.percentile:.0%}  "
                f"Sharpe_pt pct={nr.sharpe_per_trade.percentile:.0%}  "
                f"hold med strat/null={nr.strategy_hold_bars_median:.0f}/{nr.null_hold_bars_median:.0f}")
        bm = re_res.get("bias_matched")
        if bm is not None:
            d = bm.expectancy_R.strategy - bm.expectancy_R.null_mean
            if d < 0:
                log(f"  VERDICT: SMC structure (POI/FVG/CHoCH) is WORSE than random entry under the same "
                    f"trend filter by {-d:.3f}R/trade -- the structure SUBTRACTS value. [{label}, N_null={n_null}]")
            else:
                log(f"  VERDICT: SMC structure adds {d:+.3f}R/trade over the bias-matched null. [{label}]")
        log(f"  (random-entry took {time.time()-t1:.0f}s)")

        wf = walk_forward_by_year(res.trades)
        log(f"  walk-forward: E[R]>0 in {(wf['expectancy_R'] > 0).sum()}/{len(wf)} years; "
            f"all yearly CIs cross 0 = {bool(wf['ci_crosses_zero'].all())}")
        wf.to_csv(out_dir / f"walkforward_{cid}.csv", index=False)
        for _, row in regime_breakdown(res.trades).iterrows():
            log(f"    regime {row['window']:<18} N={int(row['n_trades']):>4} "
                f"E[R]={row['expectancy_R']:+.3f} CI=[{row['ci_lo']:+.2f},{row['ci_hi']:+.2f}]")

    log("scale->BE (~+1R) example search ...")
    t = _find_scale_be_example(m1, cost)
    if t is not None:
        log("found scale->be_stop example:")
        block = explain_trade(t, cost)
        print(block, flush=True); pf.write(block + "\n"); pf.flush()
    else:
        log("  (no scale->be_stop example found in IS)")
    log("capstone done")
    pf.close()


if __name__ == "__main__":
    main()
