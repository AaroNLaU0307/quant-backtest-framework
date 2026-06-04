"""Generate report figures into assets/: grid expectancy heatmap + finalist equity/DD, R-hist, MC fan.

The finalist is the pre-registered IS pick (cascade_W1_H1_M5_fixed_3R: N>=30, least-negative E[R]).
IS only.
"""
from __future__ import annotations

import pandas as pd

from mtf_smc.config import REPO_ROOT, DataConfig, StrategyConfig
from mtf_smc.data.loader import load_is
from mtf_smc.engine.backtester import run_backtest
from mtf_smc.reporting.plots import equity_drawdown, grid_heatmap, mc_fan_chart, r_histogram

FINALIST = StrategyConfig(entry_model="cascade", htf="W1", mtf="H1", ltf="M5", tp_mode="fixed_3R")


def main() -> None:
    assets = REPO_ROOT / "assets"
    master = pd.read_csv(REPO_ROOT / "output" / "grid" / "master_table.csv")
    grid_heatmap(master, assets / "grid_expectancy_heatmap.png")

    m1 = load_is(DataConfig())
    res = run_backtest(m1, FINALIST)
    R = [t.realized_R for t in res.trades]
    tag = FINALIST.config_id
    equity_drawdown(res.equity_curve, assets / f"equity_dd_{tag}.png", title=f"{tag} (IS 2015-2022)")
    r_histogram(R, assets / f"rhist_{tag}.png", title=f"{tag}  R-multiples (N={len(R)})")
    mc_fan_chart(R, assets / f"mcfan_{tag}.png", title=f"{tag}  Monte-Carlo bootstrap (IS)")
    print(f"wrote 4 figures to {assets}")


if __name__ == "__main__":
    main()
