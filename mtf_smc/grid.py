"""Primary parameter grid: enumeration + a context-cached runner. ``docs/SPEC.md`` §4.

The **42** primary configs: cascade (2 htf x 2 mtf x 3 ltf x 3 tp = 36) + direct/``htf_only``
(2 htf x 3 tp = 6).

Performance note: configs that share identical detection (same ``context_key``) **reuse one built
context**. This is safe caching of *identical detector output* — NOT idle-bar skipping. Every config
still runs the full bar-by-bar :func:`mtf_smc.engine.backtester.simulate` over the whole M1 series,
so trade logs are exactly what the naive loop produces.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd

from mtf_smc.config import StrategyConfig
from mtf_smc.engine.backtester import BacktestResult, simulate
from mtf_smc.engine.costs import CostModel
from mtf_smc.metrics.performance import summarize_backtest
from mtf_smc.risk.instrument import XAUUSD, InstrumentSpec
from mtf_smc.strategy.context import build_context
from mtf_smc.strategy.entries import generate_setups

HTFS = ["W1", "D1"]
MTFS = ["H4", "H1"]
LTFS = ["M15", "M5", "M1"]
TPS = ["fixed_3R", "HTF_level", "scale_2R_then_HTF"]


def enumerate_primary_grid() -> List[StrategyConfig]:
    """The 42 primary configurations (printed/enumerated at runtime per the brief)."""
    configs: List[StrategyConfig] = []
    for htf in HTFS:
        for mtf in MTFS:
            for ltf in LTFS:
                for tp in TPS:
                    configs.append(StrategyConfig(entry_model="cascade", htf=htf, mtf=mtf, ltf=ltf, tp_mode=tp))
    for htf in HTFS:
        for tp in TPS:
            configs.append(StrategyConfig(entry_model="direct", htf=htf, tp_mode=tp, direct_poi_source="htf_only"))
    return configs


def run_grid(
    m1: pd.DataFrame,
    configs: Optional[List[StrategyConfig]] = None,
    instrument: Optional[InstrumentSpec] = None,
    cost: Optional[CostModel] = None,
    verbose: bool = False,
) -> pd.DataFrame:
    """Run each config over ``m1`` and return one summary row per config (the master table)."""
    configs = configs or enumerate_primary_grid()
    instrument = instrument or XAUUSD
    cost = cost or CostModel(instrument)

    ctx_cache: Dict[tuple, dict] = {}
    rows: List[dict] = []
    for i, cfg in enumerate(configs):
        key = cfg.context_key
        if key not in ctx_cache:
            ctx_cache[key] = build_context(m1, cfg)
        setups, _ = generate_setups(m1, cfg, ctx=ctx_cache[key])
        trades, equity_curve, final_equity = simulate(m1, setups, cfg, instrument, cost)
        res = BacktestResult(config=cfg, trades=trades, equity_curve=equity_curve,
                             final_equity=final_equity, n_setups=len(setups))
        row = {
            "config_id": cfg.config_id, "entry_model": cfg.entry_model, "htf": cfg.htf,
            "mtf": cfg.mtf if cfg.entry_model == "cascade" else "-",
            "ltf": cfg.ltf if cfg.entry_model == "cascade" else "-", "tp_mode": cfg.tp_mode,
        }
        row.update(summarize_backtest(res))
        rows.append(row)
        if verbose:
            print(f"[{i + 1:>2}/{len(configs)}] {cfg.config_id:<28} "
                  f"setups={res.n_setups:>4} trades={row['n_trades']:>4} "
                  f"E[R]={row['expectancy_R']:>+6.3f} sharpe={row['sharpe']:>+6.2f}")
    return pd.DataFrame(rows)
