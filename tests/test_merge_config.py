"""Merge (M1): the legacy single-instrument preset is constructable and runs on the unified engine."""
from __future__ import annotations

from mtf_smc.config import StrategyConfig


def test_legacy_d1h1m5_preset():
    c = StrategyConfig.legacy_d1h1m5()
    assert (c.htf, c.mtf, c.ltf) == ("D1", "H1", "M5")
    assert c.risk_pct == 0.005                      # the old repo's 0.5% sizing
    assert c.entry_model == "cascade"
    assert c.detection_tfs == ("D1", "H1", "M5")
    assert c.config_id == "cascade_D1_H1_M5_HTF_level"


def test_legacy_preset_does_not_perturb_the_default():
    # off-by-default merge work must not change the canonical default config used by the 42-grid
    d = StrategyConfig()
    assert (d.htf, d.mtf, d.ltf, d.risk_pct) == ("D1", "H1", "M15", 0.01)
