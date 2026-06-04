"""Step-5 capstone: robustness on the grid survivors (IS only).

Reads output/grid/master_table.csv, picks survivors (N >= 30, top by E[R]), and for each re-runs IS
to get trades, then runs: Monte-Carlo (risk), the two-null random-entry benchmark (edge: per-trade
E[R] + per-trade Sharpe, holding matched), walk-forward (per-year), and regime breakdown. Also
surfaces a scale->breakeven ~+1R example. No OOS contact.

Usage:  .venv\\Scripts\\python scripts\\run_robustness.py
"""
from __future__ import annotations

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
pd.set_option("display.width", 200)


def _find_scale_be_example(m1, cost):
    """Run scale configs and return one trade that scaled at +2R then stopped at breakeven."""
    for cfg in (StrategyConfig(entry_model="cascade", htf="D1", mtf="H1", ltf="M15",
                               tp_mode="scale_2R_then_HTF"),
                StrategyConfig(entry_model="direct", htf="D1", tp_mode="scale_2R_then_HTF")):
        res = run_backtest(m1, cfg, cost=cost)
        for t in res.trades:
            if any(f.reason == "scale_2R" for f in t.fills) and t.exit_reason == "be_stop":
                return t
    return None


def main() -> None:
    cost = CostModel(XAUUSD)
    master = pd.read_csv(REPO_ROOT / "output" / "grid" / "master_table.csv")
    by_id = {c.config_id: c for c in enumerate_primary_grid()}
    elig = master[master["n_trades"] >= MIN_TRADES].sort_values("expectancy_R", ascending=False)
    survivors = list(elig["config_id"].head(TOP_N))
    print(f"survivors (N>={MIN_TRADES}, top {TOP_N} by E[R]): {survivors or 'NONE'}\n")

    m1 = load_is(DataConfig())
    out_dir = REPO_ROOT / "output" / "robustness"
    out_dir.mkdir(parents=True, exist_ok=True)

    for cid in survivors:
        cfg = by_id[cid]
        res = run_backtest(m1, cfg, cost=cost)
        R = [t.realized_R for t in res.trades]
        print("=" * 90)
        print(f"{cid}   N={res.n_trades}   E[R]={pd.Series(R).mean():+.3f}")

        mc = monte_carlo(R, risk_pct=cfg.risk_pct, n_runs=10_000, seed=cfg.seed)
        print(f"  MC max-DD (bootstrap)  p50={mc.maxdd_bootstrap_pct['p50']:.1%}  "
              f"p05={mc.maxdd_bootstrap_pct['p05']:.1%}   risk-of-ruin={mc.risk_of_ruin}")

        re = random_entry_benchmark(m1, cfg, res.trades, n_runs=1000, seed=cfg.seed,
                                    cost=cost, ctx=res.context)
        for name, nr in re.items():
            e, s = nr.expectancy_R, nr.sharpe_per_trade
            print(f"  random-entry [{name:<12}]  E[R] pct={e.percentile:>4.0%} "
                  f"(strat {e.strategy:+.3f} vs null {e.null_mean:+.3f})   "
                  f"Sharpe_pt pct={s.percentile:>4.0%}   "
                  f"hold med strat/null={nr.strategy_hold_bars_median:.0f}/{nr.null_hold_bars_median:.0f}")

        wf = walk_forward_by_year(res.trades)
        print(f"  walk-forward: E[R]>0 in {(wf['expectancy_R'] > 0).sum()}/{len(wf)} years; "
              f"every yearly CI crosses 0 = {bool(wf['ci_crosses_zero'].all())}")
        rg = regime_breakdown(res.trades)
        print(rg.to_string(index=False))
        wf.to_csv(out_dir / f"walkforward_{cid}.csv", index=False)

    print("\n" + "=" * 90)
    print("SCALE -> BREAKEVEN (~+1R) example:")
    t = _find_scale_be_example(m1, cost)
    print(explain_trade(t, cost) if t is not None else "  (none found in IS)")


if __name__ == "__main__":
    main()
