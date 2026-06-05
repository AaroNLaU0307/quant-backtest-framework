"""Multi-instrument replication + correlation-aware meta-analysis (synthetic; no licensed data)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mtf_smc.robustness import replication as rep


def _tbl(er, p, bh, cids=None):
    cids = cids or [f"c{i}" for i in range(len(er))]
    return pd.DataFrame({
        "config_id": cids, "expectancy_R": er,
        "expectancy_ci_lo": [e - 0.2 for e in er], "expectancy_ci_hi": [e + 0.2 for e in er],
        "p_value": p, "n_trades": [50] * len(er), "bh_reject": bh,
    })


def test_effective_n_independent_vs_identical():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2020-01-01", periods=600, freq="D")
    indep = {f"s{i}": pd.Series(rng.standard_normal(600), index=idx) for i in range(3)}
    _, neff, _ = rep.return_correlation(indep)
    assert 2.6 < neff <= 3.0                       # ~3 independent

    base = pd.Series(rng.standard_normal(600), index=idx)
    ident = {f"s{i}": base.copy() for i in range(3)}
    _, neff2, _ = rep.return_correlation(ident)
    assert neff2 == pytest.approx(1.0, abs=0.05)    # collapses to 1


def test_grid_and_consistency_counts():
    tables = {"A": _tbl([0.5, -0.1], [0.01, 0.6], [True, False]),
              "B": _tbl([0.4, -0.2], [0.20, 0.7], [False, False])}
    g = rep.grid(tables)
    assert g.loc["c0", "A"] == 0.5 and g.loc["c1", "B"] == -0.2
    cons = rep.consistency(tables)
    assert cons.loc["c0", "n_pos"] == 2            # positive on both instruments
    assert cons.loc["c0", "n_pos_sig"] == 1        # significant (BH) only on A
    assert cons.loc["c1", "n_pos"] == 0


def test_random_effects_correlation_inflation():
    y, se = np.array([0.1, 0.1]), np.array([0.1, 0.1])
    a = rep.random_effects(y, se, var_inflation=1.0)
    b = rep.random_effects(y, se, var_inflation=4.0)
    assert a["pooled"] == pytest.approx(0.1)
    assert b["se"] == pytest.approx(2.0 * a["se"])  # sqrt(4) inflation
    assert b["ci_hi"] - b["ci_lo"] > a["ci_hi"] - a["ci_lo"]


def test_cross_bh_fdr_trial_count():
    tables = {"A": _tbl([0.5, 0.1], [0.001, 0.5], [True, False]),
              "B": _tbl([0.4, 0.0], [0.600, 0.9], [False, False])}
    cells, n_rej, crit = rep.cross_bh_fdr(tables)
    assert len(cells) == 4                          # 2 configs x 2 instruments = correct trial count
    assert set(cells["instrument"]) == {"A", "B"}
    assert 0 <= n_rej <= 4
