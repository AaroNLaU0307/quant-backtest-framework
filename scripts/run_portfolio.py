"""M2c portfolio loop (merge; OFF-default, separate from the single-instrument analyses).

Reproduces the OLD repo's portfolio risk overlay (smc_mtf/portfolio.py + risk.py) on the new engine: runs
the faithful ``legacy_d1h1m5()`` strategy per instrument, then applies the portfolio gates on the
time-sorted combined trade stream — one position per symbol, concurrent-risk cap (max_portfolio_risk),
correlation-group same-direction cap (max_corr_group_risk), daily-loss and consecutive-loss circuit
breakers (reset daily). Fixed-fractional 0.5% sizing on realized balance.

The gates only decide WHICH trades are taken and at what size; a taken trade's R is portfolio-independent
(entry/stop/TP are per-instrument), so this overlay on cached per-instrument trades is faithful. Two
documented approximations vs the old live engine: (1) at a risk cap the marginal trade is sized DOWN to
the remaining budget (old behaviour) and dropped only if zero budget remains; (2) closes are realized at
the next entry event, so the daily-loss attribution is entry-event-granular, not M5-bar-granular.

Phase 1 (per instrument, resumable) caches trades_<sym>.csv; phase 2 runs the overlay + report.
Chunk phase 1 with PF_SYMBOLS to survive background reaping, e.g. PF_SYMBOLS=XAUUSD,EURUSD .

    .venv\\Scripts\\python scripts\\run_portfolio.py          # tail output/legacy_portfolio/progress.txt
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np
import pandas as pd

from mtf_smc.config import DataConfig, StrategyConfig
from mtf_smc.data.loader import load_is
from mtf_smc.engine.backtester import simulate
from mtf_smc.engine.costs import CostModel
from mtf_smc.risk.instrument import get_instrument
from mtf_smc.strategy.context import build_context
from mtf_smc.strategy.entries import generate_setups, precompute_legacy_triggers

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "output", "legacy_portfolio")
PROGRESS = os.path.join(OUT, "progress.txt")
ALL_SYMBOLS = ("XAUUSD", "EURUSD", "GBPUSD", "GBPJPY", "WTIUSD")


@dataclass
class PortfolioConfig:
    """The OLD repo's RiskParams defaults (smc_mtf/config.py)."""
    initial_equity: float = 100_000.0
    risk_per_trade: float = 0.005
    max_portfolio_risk: float = 0.02
    max_corr_group_risk: float = 0.01
    max_daily_loss: float = 0.02
    max_consecutive_losses: int = 5
    consecutive_loss_reset_daily: bool = True
    # Old default grouped only EUR/GBP; the other instruments are ungrouped (portfolio cap only).
    correlation_groups: Dict[str, List[str]] = field(
        default_factory=lambda: {"fx_majors_eur_gbp": ["EURUSD", "GBPUSD"]})


def _log(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(PROGRESS, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass


def _instrument_trades(symbol: str) -> pd.DataFrame:
    """Per-instrument legacy_smc trades over full IS (cached, resumable)."""
    path = os.path.join(OUT, f"trades_{symbol}.csv")
    if os.path.exists(path):
        df = pd.read_csv(path, parse_dates=["entry_ts", "exit_ts"])
        _log(f"{symbol}: cached {len(df)} trades")
        return df
    t = time.time()
    cfg = StrategyConfig.legacy_d1h1m5()
    m1 = load_is(DataConfig.for_symbol(symbol))
    inst = get_instrument(symbol)
    ctx = build_context(m1, cfg)
    setups, _ = generate_setups(m1, cfg, ctx=ctx, legacy_triggers=precompute_legacy_triggers(cfg, ctx))
    trades, _, _ = simulate(m1, setups, cfg, inst, CostModel(inst))
    df = pd.DataFrame([{"symbol": symbol, "direction": tr.direction, "entry_ts": tr.entry_ts,
                        "exit_ts": tr.exit_ts, "realized_R": tr.realized_R} for tr in trades])
    df.to_csv(path, index=False)
    _log(f"{symbol}: {len(df)} trades in {time.time()-t:.0f}s -> {os.path.basename(path)}")
    return df


def overlay(trades: pd.DataFrame, pc: PortfolioConfig) -> dict:
    """Apply the portfolio gates + circuit breakers on the time-sorted trade stream."""
    def group_of(sym: str):
        for g, members in pc.correlation_groups.items():
            if sym in members:
                return g
        return None

    rows = trades.sort_values("entry_ts").to_dict("records")
    bal = pc.initial_equity
    peak, max_dd = bal, 0.0
    openp: List[dict] = []
    day = None
    day_start, realized_today, consec = bal, 0.0, 0
    admitted, equity_curve = [], []
    rej: Dict[str, int] = {}

    def close_due(now):
        nonlocal bal, realized_today, consec, peak, max_dd
        for p in sorted([p for p in openp if p["exit_ts"] <= now], key=lambda x: x["exit_ts"]):
            openp.remove(p)
            pnl = p["realized_R"] * p["risk_money"]
            bal += pnl
            realized_today += pnl
            consec = consec + 1 if pnl < 0 else (0 if pnl > 0 else consec)
            peak = max(peak, bal)
            max_dd = max(max_dd, (peak - bal) / peak if peak > 0 else 0.0)
            equity_curve.append((p["exit_ts"], bal))

    for t in rows:
        now = t["entry_ts"]
        close_due(now)
        d = now.normalize()
        if day is None or d != day:
            day = d
            day_start, realized_today = bal, 0.0
            if pc.consecutive_loss_reset_daily:
                consec = 0
        if realized_today <= -pc.max_daily_loss * day_start:
            rej["daily_loss_halt"] = rej.get("daily_loss_halt", 0) + 1; continue
        if consec >= pc.max_consecutive_losses:
            rej["consecutive_loss_halt"] = rej.get("consecutive_loss_halt", 0) + 1; continue
        if any(p["symbol"] == t["symbol"] for p in openp):
            rej["already_open"] = rej.get("already_open", 0) + 1; continue
        grp = group_of(t["symbol"])
        rem_port = pc.max_portfolio_risk * bal - sum(p["risk_money"] for p in openp)
        rem_grp = (pc.max_corr_group_risk * bal - sum(p["risk_money"] for p in openp
                   if p["group"] == grp and p["direction"] == t["direction"])) if grp else float("inf")
        risk = min(pc.risk_per_trade * bal, rem_port, rem_grp)
        if risk <= 0:
            rej["risk_cap"] = rej.get("risk_cap", 0) + 1; continue
        openp.append(dict(symbol=t["symbol"], group=grp, direction=t["direction"],
                          risk_money=risk, exit_ts=t["exit_ts"], realized_R=t["realized_R"]))
        admitted.append(t)
    close_due(pd.Timestamp.max.tz_localize("UTC"))

    eq = pd.DataFrame(equity_curve, columns=["ts", "balance"]).sort_values("ts")
    return dict(n_candidates=len(rows), n_admitted=len(admitted), rejected=rej, final_balance=bal,
                ret_pct=100.0 * (bal / pc.initial_equity - 1.0), max_dd_pct=100.0 * max_dd, equity=eq)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    syms = tuple(s for s in os.environ.get("PF_SYMBOLS", ",".join(ALL_SYMBOLS)).split(",") if s)
    _log(f"=== portfolio start; symbols={syms} ===")
    frames = [_instrument_trades(s) for s in syms]
    have = {s for s, f in zip(syms, frames)}
    missing = [s for s in ALL_SYMBOLS if s not in have and not os.path.exists(os.path.join(OUT, f"trades_{s}.csv"))]
    if missing:
        _log(f"=== phase 1 incomplete; still need {missing}; rerun with PF_SYMBOLS to continue ===")
        return
    # phase 2: load all cached, run overlay
    allt = pd.concat([pd.read_csv(os.path.join(OUT, f"trades_{s}.csv"), parse_dates=["entry_ts", "exit_ts"])
                      for s in ALL_SYMBOLS], ignore_index=True)
    pc = PortfolioConfig()
    res = overlay(allt, pc)
    res["equity"].to_csv(os.path.join(OUT, "portfolio_equity.csv"), index=False)
    raw_R = allt["realized_R"].to_numpy()
    L = ["=" * 78, "M2c portfolio overlay (legacy_smc, 5 instruments, old RiskParams; OFF-default)", "=" * 78,
         f"  instruments: {', '.join(ALL_SYMBOLS)}",
         f"  per-trade pooled (no portfolio gates): N={len(raw_R)}  E[R]={raw_R.mean():+.3f}",
         f"  candidates={res['n_candidates']}  admitted={res['n_admitted']}  "
         f"rejected={res['n_candidates']-res['n_admitted']} {res['rejected']}",
         f"  portfolio return={res['ret_pct']:+.2f}%  max_drawdown={res['max_dd_pct']:.2f}%  "
         f"final_balance={res['final_balance']:,.0f}",
         "-" * 78,
         "  Note: the portfolio risk overlay caps exposure of a per-trade-NEGATIVE strategy; it reduces",
         "  variance/drawdown but cannot create edge. Off-default; the single-instrument L1/L2 numbers stand.",
         "=" * 78]
    report = "\n".join(L)
    print(report)
    with open(os.path.join(OUT, "portfolio_summary.txt"), "w", encoding="utf-8") as fh:
        fh.write(report + "\n")
    _log("=== PORTFOLIO_COMPLETE ===")


if __name__ == "__main__":
    main()
