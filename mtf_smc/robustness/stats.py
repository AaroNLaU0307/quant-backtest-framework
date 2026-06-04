"""Inference & multiple-testing: bootstrap CIs, p-values, drop-1, PSR, DSR, BH-FDR. ``docs/SPEC.md`` §8.

PSR/DSR (Bailey & López de Prado) operate on the **per-period** Sharpe (our daily business-day MTM
convention, *not* annualized) with ``n`` = number of daily returns and the returns' skew/kurtosis.
The Deflated Sharpe feeds in the **trial count (42)** and the cross-config Sharpe variance, so the
significance bar rises with the breadth of the search.
"""
from __future__ import annotations

import math
from typing import Dict, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy import stats as sps

_EULER = 0.5772156649015329


# ----------------------------- expectancy inference ----------------------------- #
def bootstrap_mean_ci(x: Sequence[float], n_boot: int = 10_000, ci: float = 0.95,
                      seed: int = 7) -> Tuple[float, float, float]:
    """(mean, lo, hi) bootstrap confidence interval for the mean."""
    a = np.asarray(list(x), dtype=float)
    a = a[~np.isnan(a)]
    if a.size == 0:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    means = a[rng.integers(0, a.size, size=(n_boot, a.size))].mean(axis=1)
    lo, hi = np.percentile(means, [100 * (1 - ci) / 2, 100 * (1 + ci) / 2])
    return float(a.mean()), float(lo), float(hi)


def mean_positive_pvalue(x: Sequence[float], n_boot: int = 10_000, seed: int = 7) -> float:
    """One-sided bootstrap p-value for H1: mean > 0 (fraction of bootstrap means ≤ 0)."""
    a = np.asarray(list(x), dtype=float)
    a = a[~np.isnan(a)]
    if a.size < 2:
        return float("nan")
    rng = np.random.default_rng(seed)
    means = a[rng.integers(0, a.size, size=(n_boot, a.size))].mean(axis=1)
    return float((means <= 0).mean())


def ttest_mean_positive_pvalue(x: Sequence[float]) -> float:
    """One-sided t-test p-value for H1: mean > 0."""
    a = np.asarray(list(x), dtype=float)
    a = a[~np.isnan(a)]
    if a.size < 2:
        return float("nan")
    t, p_two = sps.ttest_1samp(a, 0.0)
    return float(p_two / 2 if t > 0 else 1 - p_two / 2)


def drop_one_expectancy(R: Sequence[float]) -> Dict[str, float]:
    """Expectancy with all trades vs with the single best trade removed (tail-dependence check)."""
    a = np.asarray(list(R), dtype=float)
    a = a[~np.isnan(a)]
    if a.size < 2:
        return {"full": float("nan"), "drop_best": float("nan"), "delta": float("nan")}
    full = float(a.mean())
    drop_best = float(np.delete(a, int(np.argmax(a))).mean())
    return {"full": full, "drop_best": drop_best, "delta": full - drop_best}


# ----------------------------- Sharpe-based (PSR / DSR) ----------------------------- #
def sharpe_inputs_from_equity(equity_curve: pd.Series) -> Tuple[float, int, float, float]:
    """(per-period Sharpe, n, skew, kurtosis) from a business-day MTM equity curve."""
    daily = equity_curve.dropna().resample("B").last().ffill().dropna()
    r = daily.pct_change().dropna().to_numpy()
    if r.size < 3 or r.std(ddof=1) == 0:
        return float("nan"), int(r.size), float("nan"), float("nan")
    sr = float(r.mean() / r.std(ddof=1))
    return sr, int(r.size), float(sps.skew(r)), float(sps.kurtosis(r, fisher=False))


def probabilistic_sharpe_ratio(sr: float, n: int, skew: float, kurt: float,
                               sr_benchmark: float = 0.0) -> float:
    """PSR: P(true per-period Sharpe > ``sr_benchmark``) given the estimate and higher moments."""
    if not (n and n > 1) or math.isnan(sr):
        return float("nan")
    denom = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    if denom <= 0:
        return float("nan")
    z = (sr - sr_benchmark) * math.sqrt(n - 1) / math.sqrt(denom)
    return float(sps.norm.cdf(z))


def expected_max_sharpe(sr_variance: float, n_trials: int) -> float:
    """Expected maximum of ``n_trials`` i.i.d. Sharpe estimates (the DSR benchmark)."""
    if sr_variance <= 0 or n_trials < 2:
        return 0.0
    z1 = sps.norm.ppf(1.0 - 1.0 / n_trials)
    z2 = sps.norm.ppf(1.0 - 1.0 / (n_trials * math.e))
    return float(math.sqrt(sr_variance) * ((1 - _EULER) * z1 + _EULER * z2))


def deflated_sharpe_ratio(sr: float, n: int, skew: float, kurt: float,
                          n_trials: int, sr_variance: float) -> float:
    """DSR = PSR against the expected-max-Sharpe benchmark over ``n_trials`` configurations."""
    return probabilistic_sharpe_ratio(sr, n, skew, kurt,
                                      sr_benchmark=expected_max_sharpe(sr_variance, n_trials))


# ----------------------------- multiple testing ----------------------------- #
def benjamini_hochberg(pvalues: Sequence[float], alpha: float = 0.05) -> Tuple[np.ndarray, float]:
    """Benjamini–Hochberg FDR. Returns (reject mask in original order, critical p-value)."""
    p = np.asarray(list(pvalues), dtype=float)
    m = p.size
    if m == 0:
        return np.array([], dtype=bool), 0.0
    ranked = np.sort(p)
    thresh = alpha * (np.arange(1, m + 1) / m)
    below = ranked <= thresh
    crit = float(ranked[np.max(np.nonzero(below))]) if below.any() else 0.0
    return (p <= crit), crit
