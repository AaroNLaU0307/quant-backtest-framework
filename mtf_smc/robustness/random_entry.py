"""Random-entry benchmark — the central edge / falsification test, with TWO nulls. ``docs/SPEC.md`` §8.

**Edge metric is per-trade** — ``E[R]`` and **per-trade Sharpe = mean(R)/std(R)** — *not* the daily
mark-to-market ×√252 Sharpe. Daily Sharpe is sensitive to trade frequency and holding time, which the
randomized-timing nulls do not share with the strategy; using it would confound "entry quality" with
"how often / how long you're in". (Daily Sharpe stays the convention for the within-grid DSR/PSR/BH-FDR,
where configs are homogeneous.)

**Moments held fixed vs randomized** (stated explicitly so the comparison is not cadence-confounded):

| held fixed | randomized |
|---|---|
| N (number of trades) | entry timing / location |
| stop-distance distribution (sampled from the strategy's stops) | entry direction (*unconstrained* only) |
| holding-time distribution (each null trade's horizon is bootstrapped from the strategy's holds; the trade is force-closed at that horizon if its managed exit has not already triggered) | |
| management + costs (the real Position FSM: breakeven/scale/TP/stop) | |
| per-bar EMA-bias permission + direction (*bias_matched* only) | structural timing; POI / FVG / CHoCH are ignored |

Beating *unconstrained* but **not** *bias_matched* ⇒ the edge is the trend filter, not the SMC structure.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from mtf_smc.config import StrategyConfig
from mtf_smc.engine.costs import CostModel
from mtf_smc.engine.fills import Bar
from mtf_smc.engine.trade import ClosedTrade, Position
from mtf_smc.risk.instrument import XAUUSD, InstrumentSpec
from mtf_smc.risk.sizing import position_size
from mtf_smc.strategy.context import TFView, build_context

_SAFETY_CAP_BARS = 60 * 24 * 30  # absolute upper bound on a single trade's horizon (~30 trading days)


@dataclass(frozen=True)
class MetricNull:
    """One edge metric's strategy value and its position in the null distribution."""
    metric: str                 # 'expectancy_R' | 'sharpe_per_trade'
    strategy: float
    null_mean: float
    null_p05: float
    null_p95: float
    percentile: float           # fraction of null runs strictly below the strategy (1.0 = strategy best)


@dataclass(frozen=True)
class NullResult:
    name: str                   # 'unconstrained' | 'bias_matched'
    n_runs: int
    expectancy_R: MetricNull
    sharpe_per_trade: MetricNull
    strategy_hold_bars_median: float
    null_hold_bars_median: float


def _per_trade_sharpe(r: np.ndarray) -> float:
    if r.size < 2:
        return float("nan")
    sd = float(r.std(ddof=1))
    return float(r.mean() / sd) if sd > 0 else float("nan")


def _bias_per_m1(view: TFView, m1_index: pd.DatetimeIndex) -> np.ndarray:
    """Latest-closed bias-TF bias mapped onto each M1 bar (no look-ahead)."""
    pos = view.close_times.searchsorted(m1_index, side="right") - 1
    out = np.full(len(m1_index), "none", dtype=object)
    valid = pos >= 0
    out[valid] = view.bias[pos[valid]]
    return out


def _resolve_trade(o, h, l, c, index, j: int, direction: str, entry_ref: float, stop: float,
                   tp_mode: str, htf_target: Optional[float], cfg: StrategyConfig, equity: float,
                   instrument: InstrumentSpec, cost: CostModel,
                   max_hold: int) -> Optional[Tuple[ClosedTrade, int]]:
    """Open at bar ``j`` and step the real FSM to its exit or the bootstrapped ``max_hold`` horizon."""
    fill_px = cost.entry_fill(entry_ref, direction)
    lots = position_size(equity, cfg.risk_pct, fill_px, stop, instrument)
    if lots <= 0:
        return None
    pos = Position(direction, entry_ref, lots, stop, tp_mode, htf_target, index[j], cost,
                   be_at_2R=cfg.be_at_2R, be_trigger_R=cfg.be_trigger_R, tag="rand")
    end = min(len(c), j + 1 + min(max_hold, _SAFETY_CAP_BARS))
    for k in range(j + 1, end):
        closed = pos.on_bar(Bar(o[k], h[k], l[k], c[k]), index[k])
        if closed is not None:
            return closed, k - j
    return pos.force_close(index[end - 1], c[end - 1], "horizon"), end - 1 - j


def _holding_pool(strategy_trades: List[ClosedTrade], index: pd.DatetimeIndex) -> np.ndarray:
    """Per-trade holding in M1 bars, from naturally-exited strategy trades (exclude end-of-data marks)."""
    natural = [t for t in strategy_trades if t.exit_reason not in ("end",)]
    src = natural or strategy_trades
    epos = index.searchsorted([t.entry_ts for t in src])
    xpos = index.searchsorted([t.exit_ts for t in src])
    return np.maximum(1, xpos - epos)


def _metric_null(strategy_value: float, null_values: np.ndarray, metric: str) -> MetricNull:
    nv = null_values[~np.isnan(null_values)]
    return MetricNull(
        metric=metric, strategy=strategy_value,
        null_mean=float(nv.mean()) if nv.size else float("nan"),
        null_p05=float(np.percentile(nv, 5)) if nv.size else float("nan"),
        null_p95=float(np.percentile(nv, 95)) if nv.size else float("nan"),
        percentile=float((nv < strategy_value).mean()) if nv.size else float("nan"),
    )


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
    """Run both random-entry nulls; report per-trade E[R] and per-trade Sharpe percentiles."""
    instrument = instrument or XAUUSD
    cost = cost or CostModel(instrument)
    ctx = ctx or build_context(m1, cfg)

    strat_R = np.array([t.realized_R for t in strategy_trades], dtype=float)
    strat_R = strat_R[~np.isnan(strat_R)]
    stop_pool = np.array([abs(t.entry_price - t.initial_stop) for t in strategy_trades], dtype=float)
    stop_pool = stop_pool[stop_pool > 0]
    if strat_R.size < 2 or stop_pool.size == 0:
        return {}

    strategy_ER = float(strat_R.mean())
    strategy_sharpe = _per_trade_sharpe(strat_R)
    N = int(strat_R.size)

    o = m1["open"].to_numpy(); h = m1["high"].to_numpy()
    l = m1["low"].to_numpy(); c = m1["close"].to_numpy()
    index = m1.index
    n = len(m1)
    equity = cfg.initial_equity
    hold_pool = _holding_pool(strategy_trades, index)
    strat_hold_median = float(np.median(hold_pool))

    htf_view = ctx[cfg.htf]
    bias_view = ctx[cfg.htf if cfg.ema_bias_tf == "htf" else cfg.mtf]
    bias_m1 = _bias_per_m1(bias_view, index)
    all_idx = np.arange(0, n - 1)
    permitted = np.flatnonzero(np.isin(bias_m1, ["long", "short"]))
    permitted = permitted[permitted < n - 1]

    rng = np.random.default_rng(seed)
    use_target = cfg.tp_mode != "fixed_3R"
    major = cfg.htf_target_mode == "major_swing"

    def one_run(mode: str) -> Tuple[List[float], List[int]]:
        if mode == "unconstrained":
            js = rng.choice(all_idx, size=N, replace=True)
            dirs = rng.choice(np.array(["long", "short"]), size=N)
        else:
            if permitted.size == 0:
                return [], []
            js = rng.choice(permitted, size=N, replace=True)
            dirs = bias_m1[js]
        holds = rng.choice(hold_pool, size=N, replace=True)
        rs: List[float] = []
        hb: List[int] = []
        for j, d, hh in zip(js, dirs, holds):
            j = int(j); d = str(d)
            sd = float(rng.choice(stop_pool))
            entry_ref = float(c[j])
            stop = entry_ref - sd if d == "long" else entry_ref + sd
            tgt = htf_view.nearest_opposing_swing(index[j], d, beyond=entry_ref, major=major) if use_target else None
            res = _resolve_trade(o, h, l, c, index, j, d, entry_ref, stop, cfg.tp_mode, tgt,
                                 cfg, equity, instrument, cost, max_hold=int(hh))
            if res is not None and not np.isnan(res[0].realized_R):
                rs.append(res[0].realized_R)
                hb.append(res[1])
        return rs, hb

    results: Dict[str, NullResult] = {}
    for mode in ("unconstrained", "bias_matched"):
        run_ers: List[float] = []
        run_sharpes: List[float] = []
        all_holds: List[int] = []
        for _ in range(n_runs):
            rs, hb = one_run(mode)
            if rs:
                arr = np.asarray(rs, dtype=float)
                run_ers.append(float(arr.mean()))
                run_sharpes.append(_per_trade_sharpe(arr))
                all_holds.extend(hb)
        if not run_ers:
            continue
        results[mode] = NullResult(
            name=mode, n_runs=len(run_ers),
            expectancy_R=_metric_null(strategy_ER, np.asarray(run_ers), "expectancy_R"),
            sharpe_per_trade=_metric_null(strategy_sharpe, np.asarray(run_sharpes), "sharpe_per_trade"),
            strategy_hold_bars_median=strat_hold_median,
            null_hold_bars_median=float(np.median(all_holds)) if all_holds else float("nan"),
        )
    return results
