"""Multi-instrument replication & correlation-aware meta-analysis (docs/SPEC_multi_instrument.md §6).

Estimate **per instrument**, then assess **consistency across independent instruments**. Never
collapse correlated instruments into one naive N: pooled significance is deflated by the effective
number of independent instruments (from the cross-instrument return correlation), and the primary
evidence is the conservative consistency count, not a pooled mean.
"""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd

from mtf_smc.robustness.stats import benjamini_hochberg

SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "GBPJPY", "WTIUSD"]
_Z = 1.959963984540054   # 97.5th percentile of N(0,1)


# --------------------------------------------------------------------------- #
# Cross-instrument correlation -> effective number of independent instruments
# --------------------------------------------------------------------------- #
def return_correlation(rets: Dict[str, pd.Series]) -> Tuple[pd.DataFrame, float, np.ndarray]:
    """Correlation of returns on common dates + effective # independent instruments.

    ``N_eff`` = participation ratio ``(Σλ)^2 / Σλ^2`` of the correlation eigenvalues (=1 when all
    instruments are identical, =k when k are mutually independent). Returns ``(corr, n_eff, eig)``.
    """
    R = pd.concat(rets, axis=1).dropna()
    C = R.corr()
    ev = np.linalg.eigvalsh(C.to_numpy())
    ev = np.sort(ev[ev > 1e-12])[::-1]
    n_eff = float((ev.sum() ** 2) / np.square(ev).sum())
    return C, n_eff, ev


# --------------------------------------------------------------------------- #
# Replication grid (config x instrument)
# --------------------------------------------------------------------------- #
def _se_from_ci(ci_lo: np.ndarray, ci_hi: np.ndarray) -> np.ndarray:
    """Approx SE of E[R] from a 95% (percentile bootstrap) CI."""
    return (np.asarray(ci_hi, float) - np.asarray(ci_lo, float)) / (2.0 * _Z)


def grid(tables: Dict[str, pd.DataFrame], value: str = "expectancy_R") -> pd.DataFrame:
    """``config_id`` x instrument grid of ``value`` (column order = ``tables`` order)."""
    return pd.DataFrame({sym: df.set_index("config_id")[value] for sym, df in tables.items()})


def significance_grid(tables: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Per cell: positive **and** individually significant *within* that instrument (BH-reject)."""
    out = {}
    for sym, df in tables.items():
        d = df.set_index("config_id")
        out[sym] = (d["expectancy_R"] > 0) & d["bh_reject"].astype(bool)
    return pd.DataFrame(out)


def consistency(tables: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Per config: # instruments positive, # positive-and-significant (the replication evidence)."""
    er = grid(tables, "expectancy_R")
    sig = significance_grid(tables)
    out = pd.DataFrame(index=er.index)
    out["n_pos"] = (er > 0).sum(axis=1)
    out["n_pos_sig"] = sig.sum(axis=1)
    out["mean_ER"] = er.mean(axis=1)          # descriptive ONLY (not pooled significance)
    out["min_ER"] = er.min(axis=1)
    out["max_ER"] = er.max(axis=1)
    return out.sort_values(["n_pos_sig", "n_pos", "mean_ER"], ascending=False)


# --------------------------------------------------------------------------- #
# Correlation-aware random-effects meta-analysis (per config)
# --------------------------------------------------------------------------- #
def random_effects(y: np.ndarray, se: np.ndarray, var_inflation: float = 1.0) -> dict:
    """DerSimonian-Laird random-effects pool of one config's per-instrument E[R].

    ``var_inflation`` = N / N_eff inflates the pooled variance so the pool is **correlation-aware**
    (the instruments are not independent studies). Returns pooled E[R], SE, 95% CI, z, one-sided
    p (E[R] > 0), Q-heterogeneity and I^2.
    """
    y = np.asarray(y, float)
    se = np.asarray(se, float)
    m = np.isfinite(y) & np.isfinite(se) & (se > 0)
    y, se = y[m], se[m]
    k = int(len(y))
    nan = float("nan")
    if k < 2:
        return dict(k=k, pooled=nan, se=nan, ci_lo=nan, ci_hi=nan, z=nan, p_one_sided=nan, Q=nan, I2=nan)
    w = 1.0 / se ** 2
    fixed = np.sum(w * y) / np.sum(w)
    Q = float(np.sum(w * (y - fixed) ** 2))
    dfree = k - 1
    C = np.sum(w) - np.sum(w ** 2) / np.sum(w)
    tau2 = max(0.0, (Q - dfree) / C) if C > 0 else 0.0
    wr = 1.0 / (se ** 2 + tau2)
    pooled = float(np.sum(wr * y) / np.sum(wr))
    se_pool = float(np.sqrt(var_inflation / np.sum(wr)))
    z = pooled / se_pool if se_pool > 0 else nan
    # one-sided p that the true pooled E[R] > 0 (upper tail)
    from math import erf, sqrt
    p_one = 0.5 * (1.0 - erf(z / sqrt(2.0))) if np.isfinite(z) else nan
    I2 = max(0.0, (Q - dfree) / Q) * 100.0 if Q > 0 else 0.0
    return dict(k=k, pooled=pooled, se=se_pool, ci_lo=pooled - _Z * se_pool,
                ci_hi=pooled + _Z * se_pool, z=z, p_one_sided=p_one, Q=Q, I2=I2)


def meta_table(tables: Dict[str, pd.DataFrame], var_inflation: float = 1.0) -> pd.DataFrame:
    """Random-effects pooled E[R] (correlation-aware) for every config."""
    er = grid(tables, "expectancy_R")
    lo = grid(tables, "expectancy_ci_lo")
    hi = grid(tables, "expectancy_ci_hi")
    rows = []
    for cid in er.index:
        se = _se_from_ci(lo.loc[cid].to_numpy(), hi.loc[cid].to_numpy())
        r = random_effects(er.loc[cid].to_numpy(), se, var_inflation)
        r["config_id"] = cid
        rows.append(r)
    out = pd.DataFrame(rows).set_index("config_id")
    return out.sort_values("pooled", ascending=False)


# --------------------------------------------------------------------------- #
# Cross-(config x instrument) BH-FDR over the full trial set
# --------------------------------------------------------------------------- #
def cross_bh_fdr(tables: Dict[str, pd.DataFrame], alpha: float = 0.05) -> Tuple[pd.DataFrame, int, float]:
    """BH-FDR over ALL (config, instrument) cells (the correct trial count = configs x instruments).

    Returns the long cell table with a global reject flag, the number rejected, and the BH critical p.
    """
    frames = []
    for sym, df in tables.items():
        d = df[["config_id", "n_trades", "expectancy_R", "p_value"]].copy()
        d.insert(1, "instrument", sym)
        frames.append(d)
    cells = pd.concat(frames, ignore_index=True)
    p = cells["p_value"].fillna(1.0).to_numpy()
    reject, crit = benjamini_hochberg(p, alpha)
    cells["bh_reject_global"] = reject
    cells["bh_crit_p"] = crit
    return cells, int(reject.sum()), float(crit)
