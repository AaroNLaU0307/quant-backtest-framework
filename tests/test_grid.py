"""Primary-grid enumeration (exactly 42, correct composition) and a small runner smoke test."""
from __future__ import annotations

import pandas as pd

from mtf_smc.config import StrategyConfig
from mtf_smc.grid import apply_multiple_testing, enumerate_primary_grid, run_grid


def test_primary_grid_is_42_with_right_composition():
    configs = enumerate_primary_grid()
    assert len(configs) == 42
    cascade = [c for c in configs if c.entry_model == "cascade"]
    direct = [c for c in configs if c.entry_model == "direct"]
    assert len(cascade) == 36 and len(direct) == 6
    # config ids are unique
    assert len({c.config_id for c in configs}) == 42
    # cascade covers all ltf x tp; direct is htf_only
    assert {c.ltf for c in cascade} == {"M15", "M5", "M1"}
    assert {c.tp_mode for c in configs} == {"fixed_3R", "HTF_level", "scale_2R_then_HTF"}
    assert all(c.direct_poi_source == "htf_only" for c in direct)


def test_context_key_shared_across_tp_modes():
    # The three TP variants of one cascade cell must share a detection context (cache reuse).
    base = dict(entry_model="cascade", htf="D1", mtf="H1", ltf="M15")
    keys = {StrategyConfig(**base, tp_mode=tp).context_key for tp in
            ("fixed_3R", "HTF_level", "scale_2R_then_HTF")}
    assert len(keys) == 1


def test_run_grid_small_smoke(is_m1):
    sl = is_m1.loc["2018-01-01":"2018-06-30"]
    configs = [
        StrategyConfig(entry_model="direct", htf="D1", tp_mode="fixed_3R"),
        StrategyConfig(entry_model="direct", htf="D1", tp_mode="HTF_level"),
        StrategyConfig(entry_model="cascade", htf="D1", mtf="H1", ltf="M15", tp_mode="fixed_3R"),
    ]
    df = run_grid(sl, configs)
    assert len(df) == 3
    for col in ("config_id", "n_trades", "expectancy_R", "sharpe", "max_drawdown_pct", "final_equity",
                "p_value", "expectancy_ci_lo", "sr_per_period"):
        assert col in df.columns
    assert df["config_id"].is_unique


def test_apply_multiple_testing():
    df = pd.DataFrame({
        "p_value": [0.001, 0.01, 0.04, 0.2, 0.5],
        "sr_per_period": [0.10, 0.08, 0.05, 0.0, -0.02],
        "n_daily": [500, 500, 500, 500, 500],
        "ret_skew": [0.0] * 5, "ret_kurt": [3.0] * 5,
    })
    out = apply_multiple_testing(df, n_trials=5)
    assert out["bh_reject"].tolist() == [True, True, False, False, False]   # matches the BH-FDR test
    assert (out["dsr"] <= out["psr"] + 1e-9).all()                          # DSR deflates PSR
