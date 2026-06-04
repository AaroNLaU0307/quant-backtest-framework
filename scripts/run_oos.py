"""LOCKED OUT-OF-SAMPLE ONE-SHOT (2023-2025) -- touched once. ``docs/SPEC.md`` §1.3, §8, §10.

Evaluates the **pre-registered finalist** -- ``cascade_W1_H1_M5_fixed_3R``, selected purely by the IS
rule (N>=30, least-negative E[R]) BEFORE the OOS was unsealed -- on 2023-2025. Reported honestly
whatever it is.

**Warm-up note:** the finalist's W1 EMA(144) bias needs ~2.8 years to warm up, so a cold 3-year OOS
slice yields ~0 trades. We therefore run on the full 2015-2025 series (pre-2023 used *only* to warm
the indicators -- no OOS data ever entered IS development) and attribute results to OOS by **entry
date** (entry >= 2023-01-01). The IS-entered trades are printed too as a consistency check (they must
match the IS-only run, N=49).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from mtf_smc.config import REPO_ROOT, DataConfig, StrategyConfig
from mtf_smc.data.loader import load_full_m1
from mtf_smc.engine.backtester import run_backtest
from mtf_smc.metrics.performance import equity_stats, trade_stats
from mtf_smc.robustness.stats import bootstrap_mean_ci, mean_positive_pvalue
from mtf_smc.robustness.walkforward import walk_forward_by_year

FINALIST = StrategyConfig(entry_model="cascade", htf="W1", mtf="H1", ltf="M5", tp_mode="fixed_3R")


def _report(tag, trades, risk_pct=0.01):
    R = np.array([t.realized_R for t in trades], dtype=float)
    if R.size == 0:
        print(f"{tag}: N=0"); return {"window": tag, "n_trades": 0}
    ts = trade_stats(R)
    _, lo, hi = bootstrap_mean_ci(R)
    p = mean_positive_pvalue(R)
    exits = pd.DatetimeIndex([t.exit_ts for t in trades])
    eq = pd.Series(np.cumprod(1.0 + risk_pct * R), index=exits)  # R-based equity (rebased to 1.0)
    es = equity_stats(eq)
    print(f"{tag}: N={ts['n_trades']}  win%={ts['win_rate']:.1%}  E[R]={ts['expectancy_R']:+.3f}  "
          f"CI=[{lo:+.3f}, {hi:+.3f}]  p(mean>0)={p:.3f}  PF={ts['profit_factor']:.2f}  "
          f"Sharpe={es['sharpe']:+.2f}  maxDD={es['max_drawdown_pct']:.1%}")
    return {"window": tag, "config_id": FINALIST.config_id, "n_trades": ts["n_trades"],
            "win_rate": ts["win_rate"], "expectancy_R": ts["expectancy_R"], "ci_lo": lo, "ci_hi": hi,
            "p_value": p, "profit_factor": ts["profit_factor"], "sharpe": es["sharpe"],
            "max_drawdown_pct": es["max_drawdown_pct"]}


def main() -> None:
    print("=== LOCKED OOS ONE-SHOT (2023-2025) -- finalist chosen before unsealing ===")
    print(f"finalist: {FINALIST.config_id}\n")
    cfg = DataConfig()
    m1 = load_full_m1(cfg)  # 2015-2025; pre-2023 only warms indicators, OOS attributed by entry date
    res = run_backtest(m1, FINALIST)
    is_trades = [t for t in res.trades if t.entry_ts < cfg.oos_start]
    oos_trades = [t for t in res.trades if t.entry_ts >= cfg.oos_start]

    rows = [_report("IS 2015-2022 (consistency)", is_trades),
            _report("OOS 2023-2025", oos_trades)]
    if oos_trades:
        print("\nOOS per-year:")
        print(walk_forward_by_year(oos_trades).to_string(index=False))

    out = REPO_ROOT / "output" / "oos"
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out / "oos_finalist.csv", index=False)
    print(f"\nwrote {out / 'oos_finalist.csv'}")


if __name__ == "__main__":
    main()
