"""Print full per-trade breakdowns for one example of each exit type (for eyeballing the R math).

Runs a few configs over an IS slice, collects trades, and prints a detailed breakdown + an
independent recheck for: (a) a full stop-out, (b) a fixed_3R win, (c) a be_stop exit, and (d) a
scale_2R_then_HTF trade that scaled 50% at +2R and then exited the remainder.

Usage:  .venv\\Scripts\\python scripts\\explain_trades.py
"""
from __future__ import annotations

from typing import Callable, List, Optional

from mtf_smc.config import DataConfig, StrategyConfig
from mtf_smc.data.loader import load_is
from mtf_smc.engine.backtester import run_backtest
from mtf_smc.engine.costs import CostModel
from mtf_smc.engine.trade import ClosedTrade
from mtf_smc.reporting.explain import explain_trade
from mtf_smc.risk.instrument import XAUUSD


def _first(trades: List[ClosedTrade], pred: Callable[[ClosedTrade], bool]) -> Optional[ClosedTrade]:
    return next((t for t in trades if pred(t)), None)


def main() -> None:
    cost = CostModel(XAUUSD)
    m1 = load_is(DataConfig()).loc["2019-01-01":"2022-12-31"]
    print(f"slice {m1.index[0]} -> {m1.index[-1]}  M1 bars={len(m1):,}\n")

    configs = [
        StrategyConfig(entry_model="direct", htf="D1", tp_mode="fixed_3R"),
        StrategyConfig(entry_model="cascade", htf="D1", mtf="H1", ltf="M15", tp_mode="fixed_3R"),
        StrategyConfig(entry_model="direct", htf="D1", tp_mode="scale_2R_then_HTF"),
        StrategyConfig(entry_model="cascade", htf="D1", mtf="H1", ltf="M15", tp_mode="scale_2R_then_HTF"),
    ]
    trades: List[ClosedTrade] = []
    for cfg in configs:
        trades.extend(run_backtest(m1, cfg, cost=cost).trades)
    print(f"collected {len(trades)} trades across {len(configs)} configs\n")

    def scaled(t: ClosedTrade) -> bool:
        return any(f.reason == "scale_2R" for f in t.fills) and len(t.fills) >= 3

    examples = {
        "(a) FULL STOP-OUT": _first(trades, lambda t: t.exit_reason == "stop" and len(t.fills) == 2),
        "(b) FIXED 3R WIN": _first(trades, lambda t: t.tp_mode == "fixed_3R" and t.exit_reason == "tp"),
        "(c) BE_STOP (stopped at breakeven after +2R)": _first(trades, lambda t: t.exit_reason == "be_stop"),
        "(d) SCALE 2R THEN HTF (50% out at +2R, remainder exits)": _first(trades, scaled),
    }
    for title, t in examples.items():
        print("=" * 90)
        print(title)
        print("-" * 90)
        print(explain_trade(t, cost) if t is not None else "  (no example found in this slice)")
        print()


if __name__ == "__main__":
    main()
