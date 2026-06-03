"""Deterministic per-config performance metrics (``docs/SPEC.md`` §8).

Two groups:
* :func:`trade_stats` — from the realized-R series: N, win rate, expectancy, profit factor, payoff
  ratio, average win/loss, max consecutive losses.
* :func:`equity_stats` — from the equity curve (resampled to business days): total return, CAGR,
  annualized volatility, Sharpe, Sortino, Calmar, max drawdown (% + duration), Ulcer index.

Bootstrap CIs, Monte-Carlo, DSR/PSR, etc. live in ``robustness/`` — this module is point estimates
only. Sharpe/Sortino are annualized with ``periods_per_year`` (252 business days by default).
"""
from __future__ import annotations

import math
from typing import Dict, Sequence

import numpy as np
import pandas as pd


def trade_stats(r: Sequence[float]) -> Dict[str, float]:
    """Per-trade statistics from a sequence of realized R multiples."""
    arr = np.asarray(list(r), dtype=float)
    n = arr.size
    if n == 0:
        return {"n_trades": 0, "win_rate": float("nan"), "expectancy_R": float("nan"),
                "sum_R": 0.0, "profit_factor": float("nan"), "payoff_ratio": float("nan"),
                "avg_win_R": float("nan"), "avg_loss_R": float("nan"), "max_consec_losses": 0}
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    gross_win = float(wins.sum())
    gross_loss = float(-losses.sum())          # positive magnitude
    avg_win = float(wins.mean()) if wins.size else 0.0
    avg_loss = float(losses.mean()) if losses.size else 0.0   # negative

    mcl = cur = 0
    for x in arr:
        if x < 0:
            cur += 1
            mcl = max(mcl, cur)
        else:
            cur = 0

    return {
        "n_trades": int(n),
        "win_rate": float(wins.size / n),
        "expectancy_R": float(arr.mean()),
        "sum_R": float(arr.sum()),
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else float("inf"),
        "payoff_ratio": (avg_win / abs(avg_loss)) if avg_loss != 0 else float("nan"),
        "avg_win_R": avg_win,
        "avg_loss_R": avg_loss,
        "max_consec_losses": int(mcl),
    }


def equity_stats(equity_curve: pd.Series, periods_per_year: int = 252) -> Dict[str, float]:
    """Return/risk statistics from an equity curve (resampled to business days)."""
    ec = equity_curve.dropna()
    nan = float("nan")
    if len(ec) < 2:
        return {"total_return": 0.0, "cagr": nan, "ann_vol": nan, "sharpe": nan,
                "sortino": nan, "calmar": nan, "max_drawdown_pct": 0.0,
                "max_dd_duration_days": 0, "ulcer_index": 0.0}

    daily = ec.resample("B").last().ffill().dropna()
    rets = daily.pct_change().dropna()
    mean_r, sd = float(rets.mean()), float(rets.std(ddof=1)) if len(rets) > 1 else 0.0
    ann_vol = sd * math.sqrt(periods_per_year)
    sharpe = (mean_r / sd * math.sqrt(periods_per_year)) if sd > 0 else nan
    downside = rets[rets < 0]
    dd_dev = float(math.sqrt((downside ** 2).mean())) if len(downside) else 0.0
    sortino = (mean_r / dd_dev * math.sqrt(periods_per_year)) if dd_dev > 0 else nan

    cummax = daily.cummax()
    dd = daily / cummax - 1.0
    max_dd = float(dd.min())
    ulcer = float(math.sqrt(((dd * 100.0) ** 2).mean()))

    total_return = float(daily.iloc[-1] / daily.iloc[0] - 1.0)
    span_days = (daily.index[-1] - daily.index[0]).days
    years = span_days / 365.25 if span_days > 0 else nan
    cagr = (float(daily.iloc[-1] / daily.iloc[0]) ** (1.0 / years) - 1.0) if years and years > 0 else nan
    calmar = (cagr / abs(max_dd)) if (max_dd < 0 and not math.isnan(cagr)) else nan

    # Longest underwater stretch (calendar days).
    underwater = (daily < cummax).to_numpy()
    times = daily.index
    longest = 0
    start = None
    for i, uw in enumerate(underwater):
        if uw and start is None:
            start = times[i - 1] if i > 0 else times[i]
        elif not uw and start is not None:
            longest = max(longest, (times[i] - start).days)
            start = None
    if start is not None:
        longest = max(longest, (times[-1] - start).days)

    return {
        "total_return": total_return, "cagr": cagr, "ann_vol": ann_vol, "sharpe": sharpe,
        "sortino": sortino, "calmar": calmar, "max_drawdown_pct": max_dd,
        "max_dd_duration_days": int(longest), "ulcer_index": ulcer,
    }


def mae_mfe_summary(trades_df: pd.DataFrame) -> Dict[str, float]:
    """Summary of the per-trade MAE/MFE (in R) distributions."""
    if len(trades_df) == 0 or "mae_R" not in trades_df:
        return {"mae_R_mean": float("nan"), "mae_R_p95": float("nan"),
                "mfe_R_mean": float("nan"), "mfe_R_p95": float("nan")}
    return {
        "mae_R_mean": float(trades_df["mae_R"].mean()),
        "mae_R_p95": float(trades_df["mae_R"].quantile(0.05)),   # 5th pct (most adverse)
        "mfe_R_mean": float(trades_df["mfe_R"].mean()),
        "mfe_R_p95": float(trades_df["mfe_R"].quantile(0.95)),
    }


def summarize_backtest(result, periods_per_year: int = 252) -> Dict[str, float]:
    """Combine trade + equity + MAE/MFE stats for one backtest result."""
    df = result.trades_df
    out: Dict[str, float] = {"n_setups": result.n_setups, "final_equity": result.final_equity}
    out.update(trade_stats(df["R"].to_numpy() if len(df) else []))
    out.update(equity_stats(result.equity_curve, periods_per_year))
    out.update(mae_mfe_summary(df))
    return out
