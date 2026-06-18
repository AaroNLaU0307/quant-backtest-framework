"""L1 walk-forward (merge M3): the OLD strategy's rolling WF, reproduced on the NEW engine — fast + observable.

Faithful to the old ``run_walkforward.py``: per instrument, rolling IS(18mo)/OOS(6mo)/step(6mo) windows;
on each IS window pick the detection-threshold grid point
``{legacy_min_confluence_score} x {legacy_min_retracement}`` that maximises IS mean-R (>= MIN_IS_TRADES
guardrail), then evaluate those params on the adjacent OOS window. Runs the ``legacy_d1h1m5()`` preset
(D1->H1->M5, nearest_swing hybrid-Fib TP, Asia session filter, 0.5% risk) on the new engine.

IS/OOS WALL: the rolling WF lives entirely inside the new repo's IS data (2015-2022 via ``load_is``); the
sealed 2023-2025 OOS is NOT touched. The old WF rolled into 2023 (no sealed wall), so the updated number
is on a slightly shorter span — disclosed in the report.

PERFORMANCE: the M5 ``FVG AND (MSS OR CB/DB)`` triggers are the dominant cost and are score/retracement
INDEPENDENT, so they are precomputed once per (window-span) and reused across the 9 grid points
(``precompute_legacy_triggers``). The context (resampling/swings/ATR/EMA) is likewise built once per span.

OBSERVABILITY: every window AND every grid cell flushes one line to ``progress.txt`` (immediately, fsync'd)
so a hang/death is visible within one cell (~seconds), not hours. Poll that file directly. Each window is
wrapped so a single failure logs a traceback and is skipped rather than killing the whole run. Resumable:
one row per (symbol, window) appended to walkforward_windows.csv; re-running skips finished windows.

    .venv\\Scripts\\python scripts\\run_legacy_walkforward.py     # tail -f output/legacy_walkforward/progress.txt
"""
from __future__ import annotations

import json
import os
import time
import traceback
from dataclasses import replace
from itertools import product

import numpy as np
import pandas as pd

from mtf_smc.config import DataConfig, StrategyConfig
from mtf_smc.data.loader import load_is
from mtf_smc.engine.backtester import simulate
from mtf_smc.engine.costs import CostModel
from mtf_smc.risk.instrument import get_instrument
from mtf_smc.strategy.context import build_context
from mtf_smc.strategy.entries import generate_setups, precompute_legacy_triggers

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "output", "legacy_walkforward")
WIN_CSV = os.path.join(OUT, "walkforward_windows.csv")
PROGRESS = os.path.join(OUT, "progress.txt")

SYMBOLS = ("XAUUSD", "EURUSD")
IS_MONTHS, OOS_MONTHS, STEP_MONTHS = 18, 6, 6
MIN_IS_TRADES = 8
GRID = {"legacy_min_confluence_score": [1, 2, 3], "legacy_min_retracement": [0.5, 0.618, 0.786]}


def _log(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(PROGRESS, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass


def grid_combos():
    keys = list(GRID)
    return [dict(zip(keys, vals)) for vals in product(*[GRID[k] for k in keys])]


def windows(start: pd.Timestamp, end: pd.Timestamp):
    out, is_start = [], start
    while True:
        is_end = is_start + pd.DateOffset(months=IS_MONTHS)
        oos_end = is_end + pd.DateOffset(months=OOS_MONTHS)
        if oos_end > end:
            break
        out.append((is_start, is_end, oos_end))
        is_start = is_start + pd.DateOffset(months=STEP_MONTHS)
    return out


def _mean_r(trades, lo, hi):
    R = np.array([t.realized_R for t in trades if lo <= t.entry_ts < hi], dtype=float)
    return (float(R.mean()) if len(R) else float("nan")), len(R), R


def _done() -> set:
    if not os.path.exists(WIN_CSV):
        return set()
    df = pd.read_csv(WIN_CSV)
    return {(r["symbol"], str(r["oos_start"])) for _, r in df.iterrows()}


def run_window(symbol, m1, inst, cost, base, is_start, is_end, oos_end, tag) -> dict:
    is_m1 = m1.loc[(m1.index >= is_start) & (m1.index < is_end)]
    full_m1 = m1.loc[(m1.index >= is_start) & (m1.index < oos_end)]

    t = time.time()
    is_ctx = build_context(is_m1, base)
    is_trig = precompute_legacy_triggers(base, is_ctx)               # once; reused by all 9 grid points
    _log(f"{tag} IS ctx+triggers {time.time()-t:.0f}s (M5={len(is_ctx['M5'].df)})")

    best, best_r, best_n = None, -1e9, 0
    for c, combo in enumerate(grid_combos(), 1):
        t = time.time()
        cfg = replace(base, **combo)
        setups, _ = generate_setups(is_m1, cfg, ctx=is_ctx, legacy_triggers=is_trig)
        trades, _, _ = simulate(is_m1, setups, cfg, inst, cost)
        mr, nn, _ = _mean_r(trades, is_start, is_end)
        _log(f"{tag} combo {c}/9 {combo} IS_r={mr:+.3f}(N{nn}) {time.time()-t:.0f}s")
        if nn >= MIN_IS_TRADES and mr > best_r:
            best, best_r, best_n = combo, mr, nn
    if best is None:
        best, best_r, best_n = {}, float("nan"), 0

    t = time.time()
    full_ctx = build_context(full_m1, base)
    full_trig = precompute_legacy_triggers(base, full_ctx)
    cfg_best = replace(base, **best)
    setups, _ = generate_setups(full_m1, cfg_best, ctx=full_ctx, legacy_triggers=full_trig)
    trades, _, _ = simulate(full_m1, setups, cfg_best, inst, cost)
    oos_r, oos_n, oos_R = _mean_r(trades, is_end, oos_end)
    _log(f"{tag} OOS best={best} OOS_r={oos_r:+.3f}(N{oos_n}) {time.time()-t:.0f}s")

    return dict(symbol=symbol, is_start=str(is_start.date()), oos_start=str(is_end.date()),
                oos_end=str(oos_end.date()), best=json.dumps(best), is_r=round(best_r, 3), is_n=best_n,
                oos_r=round(oos_r, 3) if not np.isnan(oos_r) else "", oos_n=oos_n,
                oos_R_json=json.dumps([round(x, 4) for x in oos_R.tolist()]))


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    done = _done()
    _log(f"=== WF start; {len(done)} windows already done ===")
    base = StrategyConfig.legacy_d1h1m5()

    for symbol in SYMBOLS:
        t = time.time()
        m1 = load_is(DataConfig.for_symbol(symbol))
        inst = get_instrument(symbol)
        cost = CostModel(inst)
        wins = windows(m1.index[0].normalize(), m1.index[-1])
        _log(f"{symbol}: loaded {len(m1)} bars in {time.time()-t:.0f}s; {len(wins)} windows")
        for j, (is_start, is_end, oos_end) in enumerate(wins, 1):
            if (symbol, str(is_end.date())) in done:
                continue
            tag = f"[{symbol} {j}/{len(wins)} {is_start.date()}..{oos_end.date()}]"
            wt = time.time()
            try:
                row = run_window(symbol, m1, inst, cost, base, is_start, is_end, oos_end, tag)
            except Exception:
                _log(f"{tag} ERROR:\n{traceback.format_exc()}")
                continue
            pd.DataFrame([row]).to_csv(WIN_CSV, mode="a", header=not os.path.exists(WIN_CSV), index=False)
            _log(f"{tag} DONE in {time.time()-wt:.0f}s  -> CSV row written")

    _log("=== WF_COMPLETE ===")


if __name__ == "__main__":
    main()
