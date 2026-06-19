"""Behavioural fidelity (M2.5): new legacy_smc vs OLD engine entry overlap on XAUUSD 2019-2021.

Reads output/old_engine_compare/old_trade_log_XAUUSD_2019_2021.csv (from compare_old_engine.py), runs
the new legacy_smc on the same slice, and reports entry timestamp/level overlap + a side-by-side of
matched trades (entries should coincide; exits differ by the known TP-model diff).
"""
from __future__ import annotations

import os

import pandas as pd

from mtf_smc.config import DataConfig, StrategyConfig
from mtf_smc.data.loader import load_is
from mtf_smc.engine.backtester import simulate
from mtf_smc.engine.costs import CostModel
from mtf_smc.risk.instrument import get_instrument
from mtf_smc.strategy.context import build_context
from mtf_smc.strategy.entries import generate_setups

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output", "old_engine_compare")
old = pd.read_csv(os.path.join(OUT, "old_trade_log_XAUUSD_2019_2021.csv"))
old["entry_ts"] = pd.to_datetime(old["entry_ts"], utc=True)

m1 = load_is(DataConfig.for_symbol("XAUUSD")).loc["2019":"2021"]
cfg = StrategyConfig.legacy_d1h1m5()
ctx = build_context(m1, cfg)
setups, _ = generate_setups(m1, cfg, ctx=ctx)
trades, _, _ = simulate(m1, setups, cfg, get_instrument("XAUUSD"), CostModel(get_instrument("XAUUSD")))
new = pd.DataFrame([{"entry_ts": t.entry_ts, "direction": t.direction, "entry_price": t.entry_price,
                     "realized_R": t.realized_R, "exit_reason": t.exit_reason} for t in trades])
new.to_csv(os.path.join(OUT, "new_trade_log_XAUUSD_2019_2021.csv"), index=False)

print(f"=== ENTRY OVERLAP: new legacy_smc ({len(new)}) vs OLD engine ({len(old)}) — XAUUSD 2019-2021 ===")
rows = []
for _, n in new.iterrows():
    cand = old[old["direction"] == n["direction"]].copy()
    if cand.empty:
        rows.append((n, None, None, None)); continue
    cand["dts_h"] = (cand["entry_ts"] - n["entry_ts"]).abs().dt.total_seconds() / 3600.0
    o = cand.loc[cand["dts_h"].idxmin()]
    rows.append((n, o, float(o["dts_h"]), abs(float(o["entry_price"]) - float(n["entry_price"]))))

tight = sum(1 for _, o, dh, dp in rows if o is not None and dh <= 6 and dp <= 5.0)
near = sum(1 for _, o, dh, dp in rows if o is not None and dh <= 36 and dp <= 15.0)
print(f"new trades with a TIGHT old match (|dt|<=6h, |dprice|<=$5):  {tight}/{len(new)}")
print(f"new trades with a NEAR  old match (|dt|<=36h, |dprice|<=$15): {near}/{len(new)}")
print("\nmatched pairs (new entry vs nearest same-direction old entry):")
print(f"{'new_entry_ts':25} {'dir':5} {'new_px':>9}  {'old_entry_ts':25} {'old_px':>9} {'dt_h':>6} {'dpx':>6}   newR / oldR")
for n, o, dh, dp in rows:
    if o is None:
        continue
    print(f"{str(n['entry_ts']):25} {n['direction']:5} {n['entry_price']:9.3f}  "
          f"{str(o['entry_ts']):25} {float(o['entry_price']):9.3f} {dh:6.1f} {dp:6.2f}   "
          f"{n['realized_R']:+.2f} / {float(o['realized_r']):+.2f}")
