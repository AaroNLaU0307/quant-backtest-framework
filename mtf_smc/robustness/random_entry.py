"""Random-entry benchmark — the central edge / falsification test, with TWO nulls. ``docs/SPEC.md`` §8.

Both nulls share the strategy's risk model, costs, and exit/management (each random trade is resolved
by stepping the underlying M1 bars through the **real** :class:`Position` FSM, so breakeven/scale/TP/
stop and costs are identical), and match the strategy's trade cadence (N) and stop-distance geometry
(sampled from the strategy's own stops). Only the ENTRIES are randomized:

* **unconstrained** — random entry timing **and** direction.
* **bias_matched** — keep the EMA-bias permission per bar (same regime gating as the strategy),
  randomize timing, and **ignore POI / FVG / CHoCH**.

The strategy's expectancy percentile against each null is reported. Beating *unconstrained* but not
*bias_matched* ⇒ the edge is the trend filter and the SMC structure adds nothing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from mtf_smc.config import StrategyConfig
from mtf_smc.engine.costs import CostModel
from mtf_smc.engine.fills import Bar
from mtf_smc.engine.trade import ClosedTrade, Position
from mtf_smc.risk.instrument import XAUUSD, InstrumentSpec
from mtf_smc.risk.sizing import position_size
from mtf_smc.strategy.context import TFView, build_context

_MAX_HOLD_BARS = 60 * 24 * 20  # ~20 trading days of M1 — a safety cap on a single random trade


@dataclass(frozen=True)
class NullResult:
    name: str
    n_runs: int
    strategy_expectancy_R: float
    null_mean_R: float
    null_p05_R: float
    null_p95_R: float
    percentile: float   # fraction of null runs whose E[R] is below the strategy's (1.0 = strategy best)


def _bias_per_m1(view: TFView, m1_index: pd.DatetimeIndex) -> np.ndarray:
    """Latest-closed bias-TF bias mapped onto each M1 bar (no look-ahead)."""
    pos = view.close_times.searchsorted(m1_index, side="right") - 1
    out = np.full(len(m1_index), "none", dtype=object)
    valid = pos >= 0
    out[valid] = view.bias[pos[valid]]
    return out


def _resolve_trade(o, h, l, c, index, j: int, direction: str, entry_ref: float, stop: float,
                   tp_mode: str, htf_target: Optional[float], cfg: StrategyConfig,
                   equity: float, instrument: InstrumentSpec, cost: CostModel) -> Optional[ClosedTrade]:
    """Open a market position at bar ``j`` and step the FSM to its exit (same management as the engine)."""
    fill_px = cost.entry_fill(entry_ref, direction)
    lots = position_size(equity, cfg.risk_pct, fill_px, stop, instrument)
    if lots <= 0:
        return None
    pos = Position(direction, entry_ref, lots, stop, tp_mode, htf_target, index[j], cost,
                   be_at_2R=cfg.be_at_2R, be_buffer=cfg.be_buffer, tag="rand")
    end = min(len(c), j + 1 + _MAX_HOLD_BARS)
    for k in range(j + 1, end):
        closed = pos.on_bar(Bar(o[k], h[k], l[k], c[k]), index[k])
        if closed is not None:
            return closed
    return pos.force_close(index[end - 1], c[end - 1], "end")


def random_entry_benchmark(
    m1: pd.DataFrame,
    cfg: StrategyConfig,
    strategy_trades: List[ClosedTrade],
    n_runs: int = 1000,
    seed: int = 7,
    instrument: Optional[InstrumentSpec] = None,
    cost: Optional[CostModel] = None,
    ctx: Optional[Dict[str, TFView]] = None,
) -> Dict[str, NullResult]:
    """Run both random-entry nulls and return the strategy's percentile against each."""
    instrument = instrument or XAUUSD
    cost = cost or CostModel(instrument)
    ctx = ctx or build_context(m1, cfg)

    strat_R = np.array([t.realized_R for t in strategy_trades], dtype=float)
    strat_R = strat_R[~np.isnan(strat_R)]
    stop_pool = np.array([abs(t.entry_price - t.initial_stop) for t in strategy_trades], dtype=float)
    stop_pool = stop_pool[stop_pool > 0]
    if strat_R.size == 0 or stop_pool.size == 0:
        return {}
    strategy_ER = float(strat_R.mean())
    N = int(strat_R.size)

    o = m1["open"].to_numpy(); h = m1["high"].to_numpy()
    l = m1["low"].to_numpy(); c = m1["close"].to_numpy()
    index = m1.index
    n = len(m1)
    equity = cfg.initial_equity

    htf_view = ctx[cfg.htf]
    bias_view = ctx[cfg.htf if cfg.ema_bias_tf == "htf" else cfg.mtf]
    bias_m1 = _bias_per_m1(bias_view, index)
    all_idx = np.arange(0, n - 1)
    permitted = np.flatnonzero(np.isin(bias_m1, ["long", "short"]))
    permitted = permitted[permitted < n - 1]

    rng = np.random.default_rng(seed)
    use_target = cfg.tp_mode != "fixed_3R"
    major = cfg.htf_target_mode == "major_swing"

    def one_run(mode: str) -> float:
        if mode == "unconstrained":
            js = rng.choice(all_idx, size=N, replace=True)
            dirs = rng.choice(np.array(["long", "short"]), size=N)
        else:
            if permitted.size == 0:
                return float("nan")
            js = rng.choice(permitted, size=N, replace=True)
            dirs = bias_m1[js]
        rs: List[float] = []
        for j, d in zip(js, dirs):
            j = int(j); d = str(d)
            sd = float(rng.choice(stop_pool))
            entry_ref = float(c[j])
            stop = entry_ref - sd if d == "long" else entry_ref + sd
            tgt = htf_view.nearest_opposing_swing(index[j], d, beyond=entry_ref, major=major) if use_target else None
            tr = _resolve_trade(o, h, l, c, index, j, d, entry_ref, stop, cfg.tp_mode, tgt,
                                cfg, equity, instrument, cost)
            if tr is not None and not np.isnan(tr.realized_R):
                rs.append(tr.realized_R)
        return float(np.mean(rs)) if rs else float("nan")

    results: Dict[str, NullResult] = {}
    for mode in ("unconstrained", "bias_matched"):
        ers = np.array([one_run(mode) for _ in range(n_runs)], dtype=float)
        ers = ers[~np.isnan(ers)]
        if ers.size == 0:
            continue
        results[mode] = NullResult(
            name=mode, n_runs=int(ers.size), strategy_expectancy_R=strategy_ER,
            null_mean_R=float(ers.mean()), null_p05_R=float(np.percentile(ers, 5)),
            null_p95_R=float(np.percentile(ers, 95)),
            percentile=float((ers < strategy_ER).mean()),
        )
    return results
