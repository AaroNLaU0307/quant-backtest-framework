"""End-to-end prefix invariance on a synthetic fixture (no licensed data; runs in CI).

Running detection + the event loop on ``m1[m1.index < cut]`` must reproduce, exactly, every setup
decided by ``cut`` (entry, stop, take-profit target, expiry, invalidation) and every trade the full run
resolved inside the prefix. If deleting the future changed any of them, some step read a bar that had
not closed yet. Covers both entry models of the grid, the legacy model, and every take-profit mode.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from mtf_smc.config import StrategyConfig
from mtf_smc.engine.backtester import simulate
from mtf_smc.engine.costs import CostModel
from mtf_smc.risk.instrument import XAUUSD
from mtf_smc.strategy.entries import generate_setups

ONE_MIN = pd.Timedelta(minutes=1)
CONFIGS = [
    StrategyConfig(entry_model="direct", htf="H1", tp_mode="fixed_3R"),
    StrategyConfig(entry_model="direct", htf="H1", tp_mode="HTF_level"),
    StrategyConfig(entry_model="direct", htf="H1", tp_mode="scale_2R_then_HTF",
                   htf_target_mode="nearest_swing"),
    StrategyConfig(entry_model="cascade", htf="H1", mtf="M15", ltf="M5", tp_mode="HTF_level"),
    StrategyConfig(entry_model="cascade", htf="H4", mtf="H1", ltf="M5", tp_mode="scale_2R_then_HTF",
                   ema_filter=False),
    replace(StrategyConfig.legacy_d1h1m5(), htf="H4", mtf="H1", ltf="M5", legacy_session_filter=False),
]


def _run(m1: pd.DataFrame, cfg: StrategyConfig):
    setups, _ = generate_setups(m1, cfg)
    trades, _, _ = simulate(m1, setups, cfg, XAUUSD, CostModel(XAUUSD))
    return setups, trades


def _decided_by(setups, cut):
    return [(s.decided_ts, s.direction, s.entry, s.initial_stop, s.htf_target, s.expiry_ts,
             s.invalidation, s.tag) for s in setups if s.decided_ts <= cut]


def _resolved_by(trades, last):
    return sorted((t.entry_ts, t.exit_ts, t.direction, t.exit_reason, round(t.realized_R, 9))
                  for t in trades if t.exit_reason != "end" and t.exit_ts <= last)


@pytest.mark.parametrize("cfg", CONFIGS, ids=lambda c: f"{c.config_id}-{c.htf_target_mode}")
def test_engine_prefix_invariant(cfg, regime_m1):
    m1 = regime_m1
    full_setups, full_trades = _run(m1, cfg)
    assert full_setups
    # Fixed cuts (mid-bar on every TF), plus cuts just after some decisions: a setup decided at t must
    # not change when everything after t is deleted (where an unconfirmed-swing TP target would show).
    fixed = [m1.index[int(len(m1) * f) + 17] for f in (0.5, 0.8)]
    picks = np.linspace(0, len(full_setups) - 1, 3).astype(int)
    cuts = fixed + [full_setups[i].decided_ts + ONE_MIN for i in picks]
    n_trades_checked = 0
    for cut in cuts:
        prefix_m1 = m1[m1.index < cut]
        setups, trades = _run(prefix_m1, cfg)
        assert _decided_by(setups, cut) == _decided_by(full_setups, cut), (cfg.config_id, str(cut))
        last = prefix_m1.index[-1]
        got = _resolved_by(trades, last)
        assert got == _resolved_by(full_trades, last), (cfg.config_id, str(cut))
        n_trades_checked += len(got)
    assert n_trades_checked > 0
