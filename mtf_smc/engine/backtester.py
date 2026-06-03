"""Event-driven backtester: one config over M1, with intrabar fills and ≤1 position per direction.

A single forward pass over the M1 series. Per bar, in order:
  1. **Manage** open positions (opened on earlier bars) via :meth:`Position.on_bar`.
  2. **Activate** setups whose decision time is this bar (place a resting limit, subject to the
     one-per-direction concurrency rule).
  3. **Resolve pending orders**: cancel on expiry/invalidation; otherwise fill if the bar trades
     through the limit (sizing off *current* equity), opening a position managed from the next bar.

Detection/setup generation is precomputed and causal (see :mod:`mtf_smc.strategy`); :func:`simulate`
is the pure event loop (unit-tested with hand-made setups), and :func:`run_backtest` wires detection
to it. ``docs/SPEC.md`` §3-§6.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from mtf_smc.config import StrategyConfig
from mtf_smc.engine.costs import CostModel
from mtf_smc.engine.fills import Bar
from mtf_smc.engine.trade import ClosedTrade, Position, TradeSetup
from mtf_smc.risk.instrument import XAUUSD, InstrumentSpec
from mtf_smc.risk.sizing import position_size
from mtf_smc.strategy.entries import generate_setups


def trades_to_frame(trades: List[ClosedTrade]) -> pd.DataFrame:
    """Flatten closed trades into a tidy DataFrame (one row per trade)."""
    rows = [{
        "entry_ts": t.entry_ts, "exit_ts": t.exit_ts, "direction": t.direction,
        "tag": t.tag, "tp_mode": t.tp_mode, "lots": t.lots,
        "entry_ref": t.entry_ref, "entry": t.entry_price, "initial_stop": t.initial_stop,
        "exit_reason": t.exit_reason, "R": t.realized_R,
        "net_money": t.net_money, "gross_money": t.gross_money,
        "spread": t.cost_spread, "slippage": t.cost_slippage,
        "commission": t.cost_commission, "swap": t.cost_swap,
        "mae_R": t.mae_R, "mfe_R": t.mfe_R,
    } for t in trades]
    return pd.DataFrame(rows)


@dataclass
class BacktestResult:
    config: StrategyConfig
    trades: List[ClosedTrade]
    equity_curve: pd.Series
    final_equity: float
    n_setups: int
    context: Dict = field(default_factory=dict)

    @property
    def n_trades(self) -> int:
        return len(self.trades)

    @property
    def trades_df(self) -> pd.DataFrame:
        return trades_to_frame(self.trades)


def simulate(
    m1: pd.DataFrame,
    setups: List[TradeSetup],
    cfg: StrategyConfig,
    instrument: InstrumentSpec,
    cost: CostModel,
) -> Tuple[List[ClosedTrade], pd.Series, float]:
    """Pure event loop: feed precomputed setups over M1 -> (trades, equity_curve, final_equity)."""
    setups = sorted(setups, key=lambda s: s.decided_ts)
    o = m1["open"].to_numpy(); h = m1["high"].to_numpy()
    lo = m1["low"].to_numpy(); c = m1["close"].to_numpy()
    idx = m1.index
    n = len(m1)

    decided_pos = (idx.searchsorted([s.decided_ts for s in setups], side="left")
                   if setups else np.array([], dtype=int))

    equity = float(cfg.initial_equity)
    trades: List[ClosedTrade] = []
    eq_ts: List[pd.Timestamp] = [idx[0]] if n else []
    eq_val: List[float] = [equity] if n else []

    open_pos: Dict[str, Position] = {}
    pending: Dict[str, TradeSetup] = {}
    si = 0

    for i in range(n):
        bar = Bar(o[i], h[i], lo[i], c[i])
        ts = idx[i]

        # 1) manage open positions (opened on earlier bars)
        for d in list(open_pos.keys()):
            closed = open_pos[d].on_bar(bar, ts)
            if closed is not None:
                equity += closed.net_money
                trades.append(closed)
                eq_ts.append(ts); eq_val.append(equity)
                del open_pos[d]

        # 2) activate setups decided on this bar (one live order per direction)
        while si < len(setups) and decided_pos[si] == i:
            s = setups[si]; si += 1
            if s.direction not in open_pos and s.direction not in pending:
                pending[s.direction] = s

        # 3) resolve pending orders
        for d in list(pending.keys()):
            s = pending[d]
            if ts > s.expiry_ts:
                del pending[d]; continue
            if s.invalidation is not None and (
                (d == "long" and c[i] < s.invalidation) or (d == "short" and c[i] > s.invalidation)
            ):
                del pending[d]; continue
            if d in open_pos:
                continue
            if lo[i] <= s.entry <= h[i]:                       # limit traded through
                fill_px = cost.entry_fill(s.entry, d)          # for sizing (1R = |fill - stop|)
                lots = position_size(equity, cfg.risk_pct, fill_px, s.initial_stop, instrument)
                if lots <= 0:
                    del pending[d]; continue
                open_pos[d] = Position(
                    d, s.entry, lots, s.initial_stop, s.tp_mode, s.htf_target, ts, cost,
                    be_at_2R=cfg.be_at_2R, be_buffer=cfg.be_buffer, tag=s.tag,
                )
                del pending[d]

    # Mark out anything still open at end-of-data.
    if n:
        for d in list(open_pos.keys()):
            closed = open_pos[d].force_close(idx[-1], c[-1], reason="end")
            equity += closed.net_money
            trades.append(closed)
            eq_ts.append(idx[-1]); eq_val.append(equity)

    equity_curve = pd.Series(eq_val, index=pd.DatetimeIndex(eq_ts), name="equity")
    trades.sort(key=lambda t: t.exit_ts)
    return trades, equity_curve, equity


def run_backtest(
    m1: pd.DataFrame,
    cfg: StrategyConfig,
    instrument: Optional[InstrumentSpec] = None,
    cost: Optional[CostModel] = None,
) -> BacktestResult:
    """Detect setups for ``cfg`` and run the event loop over ``m1``."""
    instrument = instrument or XAUUSD
    cost = cost or CostModel(instrument)
    setups, ctx = generate_setups(m1, cfg)
    trades, equity_curve, final_equity = simulate(m1, setups, cfg, instrument, cost)
    return BacktestResult(config=cfg, trades=trades, equity_curve=equity_curve,
                          final_equity=final_equity, n_setups=len(setups), context=ctx)
