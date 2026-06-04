"""Monte-Carlo on the realized-R sequence — characterizes RISK, not edge. ``docs/SPEC.md`` §8.

Two resamplings of the per-trade R series, with equity compounded fixed-fractionally
(``equity *= 1 + risk_pct * R``):

* **reshuffle** (order/path risk) — same trades, permuted order. Terminal equity is order-invariant
  under fixed-fractional compounding, so this isolates the **drawdown / path** distribution.
* **bootstrap** (composition risk) — resample trades with replacement; **both** terminal equity and
  drawdown vary.

Reported: terminal-equity and max-drawdown distributions (percentiles), and risk-of-ruin
(P(max DD ≥ threshold)). *(Monte-Carlo characterizes risk; the random-entry benchmark tests edge.)*
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Sequence, Tuple

import numpy as np


def equity_path(r: np.ndarray, risk_pct: float, equity0: float = 1.0) -> np.ndarray:
    """Fixed-fractional compounded equity from a per-trade R sequence."""
    return equity0 * np.cumprod(1.0 + risk_pct * r)


def max_drawdown(path: np.ndarray) -> float:
    """Max drawdown of an equity path as a (negative) fraction."""
    if path.size == 0:
        return 0.0
    peak = np.maximum.accumulate(path)
    return float((path / peak - 1.0).min())


@dataclass
class MonteCarloResult:
    n_runs: int
    risk_pct: float
    terminal_pct: Dict[str, float]          # bootstrap terminal-equity multiple percentiles
    maxdd_reshuffle_pct: Dict[str, float]    # reshuffle max-DD percentiles (path risk)
    maxdd_bootstrap_pct: Dict[str, float]
    risk_of_ruin: Dict[str, float] = field(default_factory=dict)  # P(maxDD >= threshold), bootstrap


def _pcts(x: np.ndarray) -> Dict[str, float]:
    q = np.percentile(x, [5, 25, 50, 75, 95])
    return {"p05": float(q[0]), "p25": float(q[1]), "p50": float(q[2]),
            "p75": float(q[3]), "p95": float(q[4])}


def monte_carlo(
    R: Sequence[float],
    risk_pct: float = 0.01,
    n_runs: int = 10_000,
    seed: int = 7,
    ruin_thresholds: Tuple[float, ...] = (0.20, 0.30),
) -> MonteCarloResult:
    """Run reshuffle + bootstrap Monte-Carlo on the R sequence."""
    r = np.asarray(list(R), dtype=float)
    r = r[~np.isnan(r)]
    rng = np.random.default_rng(seed)
    n = r.size
    if n == 0:
        empty = {k: float("nan") for k in ("p05", "p25", "p50", "p75", "p95")}
        return MonteCarloResult(0, risk_pct, empty, empty, empty, {})

    resh_maxdd = np.empty(n_runs)
    boot_maxdd = np.empty(n_runs)
    boot_term = np.empty(n_runs)
    for i in range(n_runs):
        resh_maxdd[i] = max_drawdown(equity_path(rng.permutation(r), risk_pct))
        sample = r[rng.integers(0, n, size=n)]
        path = equity_path(sample, risk_pct)
        boot_maxdd[i] = max_drawdown(path)
        boot_term[i] = float(path[-1])

    ruin = {f"dd_ge_{int(t * 100)}pct": float((boot_maxdd <= -t).mean()) for t in ruin_thresholds}
    return MonteCarloResult(
        n_runs=n_runs, risk_pct=risk_pct,
        terminal_pct=_pcts(boot_term),
        maxdd_reshuffle_pct=_pcts(resh_maxdd),
        maxdd_bootstrap_pct=_pcts(boot_maxdd),
        risk_of_ruin=ruin,
    )
