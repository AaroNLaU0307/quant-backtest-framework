"""Generalized fixed-RR targets + the configurable breakeven trigger (be_trigger_R)."""
from __future__ import annotations

import pandas as pd
import pytest

from mtf_smc.engine.costs import CostModel
from mtf_smc.engine.fills import Bar
from mtf_smc.engine.trade import Position
from mtf_smc.risk.instrument import XAUUSD

TS0 = pd.Timestamp("2020-06-01 12:00", tz="UTC")
TS1 = pd.Timestamp("2020-06-01 13:00", tz="UTC")
NOCOST = dict(slippage_per_side=0.0, stop_slippage_per_side=0.0,
              apply_spread=False, apply_commission=False, apply_swap=False)


def _pos(tp_mode: str, be_trigger_R: float) -> Position:
    cost = CostModel(XAUUSD, **NOCOST)            # long 2000 / stop 1990 -> R_unit = 10
    return Position("long", 2000.0, 1.0, 1990.0, tp_mode, None, TS0, cost,
                    be_at_2R=True, be_buffer=0.0, be_trigger_R=be_trigger_R)


@pytest.mark.parametrize("mult", [1, 2, 3, 5])
def test_fixed_rr_targets_parse(mult):
    assert _pos(f"fixed_{mult}R", 2.0)._tp_target() == pytest.approx(2000.0 + mult * 10.0)


def test_be_at_1R_saves_a_reversal_to_breakeven():
    # be@1R: tag +1R (2010) then reverse to entry -> exit ~0 (be_stop), not -1R.
    p = _pos("fixed_3R", 1.0)
    assert p.on_bar(Bar(2000, 2010, 2000, 2005), TS0) is None and p.be_done
    c = p.on_bar(Bar(2005, 2006, 1999, 2000), TS1)
    assert c is not None and c.exit_reason == "be_stop"
    assert c.realized_R == pytest.approx(0.0, abs=1e-9)


def test_be_at_2R_default_not_armed_at_1R():
    # default be@2R: tag +1.5R then fall to the original stop -> full -1R (BE never armed).
    p = _pos("fixed_3R", 2.0)
    assert p.on_bar(Bar(2000, 2015, 2000, 2010), TS0) is None and not p.be_done
    c = p.on_bar(Bar(2010, 2010, 1990, 1990), TS1)
    assert c is not None and c.exit_reason == "stop"
    assert c.realized_R == pytest.approx(-1.0, abs=1e-9)
