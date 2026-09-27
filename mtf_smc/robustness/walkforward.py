"""Walk-forward (sequential OOS consistency) and regime breakdowns. ``docs/SPEC.md`` §8.

With **fixed, un-optimized** parameters, walk-forward reduces to *sequential out-of-sample
consistency*: bucket the realized trades by time window and report each window's expectancy + CI.
The same machinery does the **regime** breakdown (named date ranges, e.g. range / COVID / bull). We
bucket the trades a config already produced over IS rather than re-detecting per fold, which avoids
indicator-warmup discontinuities and is exact for fixed params.
"""
from __future__ import annotations

import json
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

from mtf_smc.engine.trade import ClosedTrade
from mtf_smc.metrics.performance import trade_stats
from mtf_smc.robustness.stats import bootstrap_mean_ci, sign_test_pvalue

# Default IS regimes (2015-2022) per the brief.
DEFAULT_IS_REGIMES: Dict[str, Tuple[str, str]] = {
    "2015-2018 range": ("2015-01-01", "2018-12-31"),
    "2019-2020 COVID": ("2019-01-01", "2020-12-31"),
    "2021-2022 bull": ("2021-01-01", "2022-12-31"),
}


def _row(label, rs: np.ndarray, n_boot: int, seed: int) -> Dict[str, float]:
    st = trade_stats(rs)
    _, lo, hi = bootstrap_mean_ci(rs, n_boot=n_boot, seed=seed)
    return {"window": label, "n_trades": st["n_trades"], "expectancy_R": st["expectancy_R"],
            "ci_lo": lo, "ci_hi": hi, "win_rate": st["win_rate"], "sum_R": st["sum_R"],
            "ci_crosses_zero": bool(lo <= 0 <= hi)}


def _r_by_entry(trades: Sequence[ClosedTrade]) -> pd.Series:
    return pd.Series([t.realized_R for t in trades],
                     index=pd.DatetimeIndex([t.entry_ts for t in trades]))


def walk_forward_by_year(trades: Sequence[ClosedTrade], n_boot: int = 5000, seed: int = 7) -> pd.DataFrame:
    """Per-calendar-year expectancy + CI (sequential-OOS consistency for fixed params)."""
    if not trades:
        return pd.DataFrame()
    R = _r_by_entry(trades)
    rows: List[dict] = [_row(int(yr), grp.to_numpy(), n_boot, seed)
                        for yr, grp in R.groupby(R.index.year)]
    return pd.DataFrame(rows)


def regime_breakdown(trades: Sequence[ClosedTrade],
                     regimes: Dict[str, Tuple[str, str]] = None,
                     n_boot: int = 5000, seed: int = 7) -> pd.DataFrame:
    """Expectancy + CI within named date-range regimes."""
    regimes = regimes or DEFAULT_IS_REGIMES
    if not trades:
        return pd.DataFrame()
    R = _r_by_entry(trades)
    rows: List[dict] = []
    for name, (a, b) in regimes.items():
        rs = R.loc[a:b].to_numpy()
        if rs.size:
            rows.append(_row(name, rs, n_boot, seed))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# L1 rolling walk-forward (scripts/run_legacy_walkforward.py): inference over calendar periods
# --------------------------------------------------------------------------- #
def oos_period_returns(windows: pd.DataFrame) -> dict[str, np.ndarray]:
    """Pool each calendar OOS period's trade R across instruments, keyed (and sorted) by ``oos_start``.

    ``windows`` holds one row per (instrument, window) with ``oos_start`` and ``oos_R_json`` (the JSON
    list of that window's OOS trade R). Every instrument rolls the same calendar windows, so the
    rows of one period are not independent of each other; pooling them gives one unit per period.
    """
    pooled: dict[str, list[np.ndarray]] = {}
    for period, blob in zip(windows["oos_start"].astype(str), windows["oos_R_json"]):
        pooled.setdefault(period, []).append(np.asarray(json.loads(blob), dtype=float))
    return {p: np.concatenate(pooled[p]) for p in sorted(pooled)}


def period_sign_test(windows: pd.DataFrame) -> dict[str, float]:
    """One-sided sign test over calendar OOS periods (not over instrument-windows).

    Each period contributes one sign: that of the mean OOS R of all instruments' trades in the
    period. Periods without trades, and exact-zero means (ties), are dropped. Returns
    ``{"n_periods", "n_negative", "p_value"}`` with p = P(>= n_negative | fair coin).
    """
    means = np.array([r.mean() for r in oos_period_returns(windows).values() if r.size])
    signed = means[means != 0]
    n, n_neg = int(signed.size), int((signed < 0).sum())
    return {"n_periods": n, "n_negative": n_neg, "p_value": sign_test_pvalue(n_neg, n)}
