"""Primary parameter grid: enumeration + a context-cached runner. ``docs/SPEC.md`` §4.

The **42** primary configs: cascade (2 htf x 2 mtf x 3 ltf x 3 tp = 36) + direct/``htf_only``
(2 htf x 3 tp = 6).

Performance note: configs that share identical detection (same ``context_key``) **reuse one built
context**. This is safe caching of *identical detector output* — NOT idle-bar skipping. Every config
still runs the full bar-by-bar :func:`mtf_smc.engine.backtester.simulate` over the whole M1 series,
so trade logs are exactly what the naive loop produces.
"""
from __future__ import annotations

import csv
import gc
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from mtf_smc.config import StrategyConfig
from mtf_smc.engine.backtester import BacktestResult, simulate
from mtf_smc.engine.costs import CostModel
from mtf_smc.metrics.performance import summarize_backtest
from mtf_smc.risk.instrument import XAUUSD, InstrumentSpec
from mtf_smc.robustness.stats import (
    benjamini_hochberg, bootstrap_mean_ci, deflated_sharpe_ratio, drop_one_expectancy,
    mean_positive_pvalue, probabilistic_sharpe_ratio, sharpe_inputs_from_equity,
)
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


def _row_for(cfg: StrategyConfig, res: BacktestResult) -> Dict:
    row = {
        "config_id": cfg.config_id, "entry_model": cfg.entry_model, "htf": cfg.htf,
        "mtf": cfg.mtf if cfg.entry_model == "cascade" else "-",
        "ltf": cfg.ltf if cfg.entry_model == "cascade" else "-", "tp_mode": cfg.tp_mode,
    }
    row.update(summarize_backtest(res))
    row.update(_inference(res))
    return row


def run_grid(
    m1: pd.DataFrame,
    configs: Optional[List[StrategyConfig]] = None,
    instrument: Optional[InstrumentSpec] = None,
    cost: Optional[CostModel] = None,
    verbose: bool = False,
    progress_file: Optional[Path] = None,
    incremental_csv: Optional[Path] = None,
) -> pd.DataFrame:
    """Run each config over ``m1``; return one summary row per config (the master table).

    Memory-safe and observable for the long full-IS run:
    * **one context in memory at a time** — configs are processed grouped by ``context_key``; the
      shared (possibly multi-million-object M1) context is built, used for its TP variants, then
      ``del`` + ``gc`` before the next group. (Caching all contexts caused the OOM that killed the
      earlier runs on the first M1-LTF cascade.)
    * **flushed progress** — a timestamped line per context-build and per config to ``progress_file``,
      so a hang/death is visible within one config (minutes), not hours.
    * **incremental + resume** — each completed row is appended to ``incremental_csv`` (flushed);
      configs already present there are skipped, so a death loses only the in-flight config.
    """
    configs = configs or enumerate_primary_grid()
    instrument = instrument or XAUUSD
    cost = cost or CostModel(instrument)

    done_ids: set = set()
    existing_rows: List[dict] = []
    if incremental_csv is not None and Path(incremental_csv).exists():
        prev = pd.read_csv(incremental_csv)
        done_ids = set(prev["config_id"])
        existing_rows = prev.to_dict("records")

    pf = open(progress_file, "a", encoding="utf-8") if progress_file is not None else None

    def log(msg: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {msg}"
        if pf is not None:
            pf.write(line + "\n"); pf.flush()
        if verbose:
            print(line, flush=True)

    groups: Dict[tuple, List[StrategyConfig]] = {}
    order: List[tuple] = []
    for cfg in configs:
        k = cfg.context_key
        if k not in groups:
            groups[k] = []; order.append(k)
        groups[k].append(cfg)

    writer = None
    csv_fh = None
    new_rows: List[dict] = []
    total = len(configs)
    done = len(done_ids)
    log(f"grid start: {total} configs, {done} already complete, {len(order)} contexts")

    for k in order:
        members = [c for c in groups[k] if c.config_id not in done_ids]
        if not members:
            continue
        cfg0 = members[0]
        t0 = time.time()
        ctx = build_context(m1, cfg0)
        log(f"[ctx] {cfg0.entry_model} tfs={'/'.join(cfg0.detection_tfs)} built in {time.time() - t0:.1f}s")
        for cfg in members:
            tc = time.time()
            setups, _ = generate_setups(m1, cfg, ctx=ctx)
            trades, equity_curve, final_equity = simulate(m1, setups, cfg, instrument, cost)
            res = BacktestResult(config=cfg, trades=trades, equity_curve=equity_curve,
                                 final_equity=final_equity, n_setups=len(setups))
            row = _row_for(cfg, res)
            new_rows.append(row)
            done += 1
            if incremental_csv is not None:
                if writer is None:
                    new_file = not Path(incremental_csv).exists()
                    csv_fh = open(incremental_csv, "a", newline="", encoding="utf-8")
                    writer = csv.DictWriter(csv_fh, fieldnames=list(row.keys()))
                    if new_file:
                        writer.writeheader()
                writer.writerow(row); csv_fh.flush()
            log(f"[{done:>2}/{total}] {cfg.config_id:<30} setups={len(setups):>5} "
                f"trades={row['n_trades']:>4} E[R]={row['expectancy_R']:>+6.3f} ({time.time() - tc:.1f}s)")
        del ctx
        gc.collect()

    if csv_fh is not None:
        csv_fh.close()
    log("grid done")
    if pf is not None:
        pf.close()
    return pd.DataFrame(existing_rows + new_rows)


def _inference(res: BacktestResult, n_boot: int = 5000) -> Dict[str, float]:
    """Per-config inference inputs: expectancy CI, p-value, drop-1, and daily-Sharpe moments."""
    nan = float("nan")
    df = res.trades_df
    if res.n_trades < 2:
        return {"expectancy_ci_lo": nan, "expectancy_ci_hi": nan, "p_value": nan,
                "drop_best_R": nan, "drop_best_delta": nan,
                "sr_per_period": nan, "n_daily": 0, "ret_skew": nan, "ret_kurt": nan}
    R = df["R"].to_numpy()
    _, lo, hi = bootstrap_mean_ci(R, n_boot=n_boot, seed=res.config.seed)
    d1 = drop_one_expectancy(R)
    sr_pp, n_daily, skew, kurt = sharpe_inputs_from_equity(res.equity_curve)
    return {"expectancy_ci_lo": lo, "expectancy_ci_hi": hi,
            "p_value": mean_positive_pvalue(R, n_boot=n_boot, seed=res.config.seed),
            "drop_best_R": d1["drop_best"], "drop_best_delta": d1["delta"],
            "sr_per_period": sr_pp, "n_daily": n_daily, "ret_skew": skew, "ret_kurt": kurt}


def apply_multiple_testing(df: pd.DataFrame, n_trials: Optional[int] = None,
                           alpha: float = 0.05) -> pd.DataFrame:
    """Add BH-FDR (reject/critical-p) and PSR/DSR columns across the grid (``docs/SPEC.md`` §8).

    DSR deflates each config's PSR by the expected-max Sharpe over ``n_trials`` configs, using the
    cross-config variance of the per-period Sharpe — so the bar rises with the breadth of the search.
    """
    out = df.copy()
    n_trials = n_trials or len(out)
    reject, crit = benjamini_hochberg(out["p_value"].fillna(1.0).to_numpy(), alpha)
    out["bh_reject"] = reject
    out["bh_crit_p"] = crit
    sr = out["sr_per_period"].to_numpy()
    sr_var = float(np.nanvar(sr, ddof=1)) if np.isfinite(sr).sum() > 1 else 0.0
    out["psr"] = [probabilistic_sharpe_ratio(s, int(nn) if np.isfinite(nn) else 0, sk, ku)
                  for s, nn, sk, ku in zip(out["sr_per_period"], out["n_daily"],
                                           out["ret_skew"], out["ret_kurt"])]
    out["dsr"] = [deflated_sharpe_ratio(s, int(nn) if np.isfinite(nn) else 0, sk, ku, n_trials, sr_var)
                  for s, nn, sk, ku in zip(out["sr_per_period"], out["n_daily"],
                                           out["ret_skew"], out["ret_kurt"])]
    return out
