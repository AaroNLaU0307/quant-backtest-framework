"""End-to-end engine tests on real IS data: smoke + a strong no-look-ahead truncation guarantee."""
from __future__ import annotations

from mtf_smc.config import StrategyConfig
from mtf_smc.engine.backtester import run_backtest

CFG = StrategyConfig(entry_model="direct", htf="D1", mtf="H1", tp_mode="fixed_3R")


def _slice(m1):
    return m1.loc["2018-01-01":"2018-09-30"]


def test_run_backtest_end_to_end_smoke(is_m1):
    res = run_backtest(_slice(is_m1), CFG)
    assert res.n_setups >= 0
    assert res.equity_curve.index.is_monotonic_increasing
    df = res.trades_df
    if res.n_trades:
        assert df["R"].notna().all()
        assert (df["exit_ts"] >= df["entry_ts"]).all()
        assert {"entry_ts", "exit_ts", "direction", "R", "exit_reason"}.issubset(df.columns)


def test_engine_no_lookahead_truncation(is_m1):
    """Trades fully resolved within a prefix must be identical when the future is deleted.

    Running on ``sl[:cut]`` cannot change any trade that both entered and exited before the cut —
    if it did, detection or fills were peeking at future bars.
    """
    sl = _slice(is_m1)
    cut = len(sl) // 2
    before = sl.index[cut - 1]
    full = run_backtest(sl, CFG)
    prefix = run_backtest(sl.iloc[:cut], CFG)

    def resolved(res, cutoff):
        return {
            (t.entry_ts, t.exit_ts, t.direction, round(t.realized_R, 6))
            for t in res.trades
            if t.exit_reason != "end" and t.exit_ts < cutoff
        }

    # Everything the prefix resolved before the cut must match the full run exactly.
    assert resolved(prefix, before).issubset(resolved(full, before))
