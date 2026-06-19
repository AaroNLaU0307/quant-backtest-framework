"""One-off behavioural fidelity check (M2.5): run the OLD engine on XAUUSD 2019-2021.

Runs the OLD repo's engine (smc_mtf, StrategyConfig.default()) WITHOUT writing anything into the old
folder: PYTHONDONTWRITEBYTECODE blocks .pyc, the shared M1 cache is read from MTF Analysis/data_cache
(byte-identical file), and every artifact goes to output/old_engine_compare/. Emits the signal funnel,
trade count, direction split, entry kinds, and an entries.csv for the old-vs-new overlap step.

    set SMC_LEGACY_REPO=<legacy repo root>  &&  .venv\\Scripts\\python scripts\\compare_old_engine.py
"""
from __future__ import annotations

import os
import sys

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"  # keep the old folder untouched (no bytecode writes)
sys.dont_write_bytecode = True

# Requires the LEGACY repo (the published single-instrument "Algorithmic Trading System", package
# smc_mtf/) checked out locally; point SMC_LEGACY_REPO (or argv[1]) at its root. Nothing is written there
# (bytecode disabled; the shared M1 cache is read from THIS repo's data_cache); artifacts go under this repo.
OLD = os.environ.get("SMC_LEGACY_REPO") or (sys.argv[1] if len(sys.argv) > 1 else "")
if not OLD or not os.path.isdir(os.path.join(OLD, "smc_mtf")):
    sys.exit("set SMC_LEGACY_REPO=<path to the legacy repo containing smc_mtf/> (or pass it as argv[1])")
NEW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEW_CACHE = os.path.join(NEW, "data_cache")
OUT = os.path.join(NEW, "output", "old_engine_compare")
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, OLD)

from smc_mtf.backtester import Backtester           # noqa: E402
from smc_mtf.config import StrategyConfig            # noqa: E402
from smc_mtf.data_loader import load_for_backtest    # noqa: E402
from smc_mtf.instrument import get_default_instrument  # noqa: E402

YEARS = tuple(range(2015, 2024))                     # -> hits shared cache XAUUSD_M1_UTC_2015_2023.pkl
m5, _ = load_for_backtest("", "XAUUSD", years=YEARS, cache_dir=NEW_CACHE, verbose=False)
m5 = m5.loc["2019":"2021"]                           # same window as the new legacy_smc fidelity run
print(f"OLD engine input: M5 bars {len(m5)}  range {m5.index[0]} -> {m5.index[-1]}")

res = Backtester(StrategyConfig.default()).run(m5, get_default_instrument("XAUUSD"))
tl = res.trade_log
m = res.meta

print("=== OLD ENGINE (smc_mtf, StrategyConfig.default()) on XAUUSD 2019-2021 ===")
funnel = {k: m.get(k) for k in ("n_pois", "n_pierced", "n_candidates", "n_signals", "n_filtered",
                                "n_risk_reject", "n_trades")}
print("funnel:", funnel)
if tl is not None and not tl.empty:
    tl.to_csv(os.path.join(OUT, "old_trade_log_XAUUSD_2019_2021.csv"), index=False)
    nL = int((tl["direction"] == "long").sum())
    kinds = {k: int(tl["entry_reason"].str.contains(f"_{k}+", regex=False).sum()) for k in ("MSS", "CB", "DB")}
    print(f"trades: {len(tl)} (long {nL}, short {len(tl) - nL})  "
          f"win_rate={(tl['realized_r'] > 0).mean():.3f}  meanR={tl['realized_r'].mean():+.3f}  kinds={kinds}")
    cols = ["entry_ts", "direction", "entry_price", "poi_zone_low", "poi_zone_high",
            "initial_sl_price", "exit_reason", "realized_r"]
    print(tl[cols].head(8).to_string(index=False))
    tl[["entry_ts", "direction", "entry_price"]].to_csv(os.path.join(OUT, "old_entries.csv"), index=False)
else:
    print("trades: 0 (empty trade log)")
print(f"[artifacts] {OUT}")
