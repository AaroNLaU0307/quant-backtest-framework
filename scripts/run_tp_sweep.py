"""EXPLORATORY (NOT pre-registered): fixed reward:risk take-profit sweep with breakeven at +1R.

Sweeps tp_mode in {fixed_1R, fixed_2R, fixed_3R, fixed_5R} with be_trigger_R = 1.0 (move stop to
breakeven once the trade is up 1R) across the standard cascade + direct entry contexts, on all five
instruments. Question: does any fixed RR target, combined with a 1R breakeven, manufacture positive
expectancy out of an entry signal that has none?

This is clearly labelled **exploratory**: it does NOT enter the pre-registered 210-trial grid or the
replication conclusion. Same per-instrument costs and a within-sweep BH-FDR are applied for honesty.
M1-LTF cascades are omitted (already the established worst on every TP/instrument; their inclusion
only pushes every RR level uniformly more negative). Writes output/grid/tp_sweep/<SYM>.csv.

    .venv\\Scripts\\python scripts\\run_tp_sweep.py            # all 5 instruments
"""
from __future__ import annotations

import sys
from dataclasses import replace

import pandas as pd

from mtf_smc.config import REPO_ROOT, DataConfig
from mtf_smc.data.loader import load_is
from mtf_smc.engine.costs import CostModel
from mtf_smc.grid import apply_multiple_testing, enumerate_primary_grid, run_grid
from mtf_smc.risk.instrument import get_instrument

RRS = ["fixed_1R", "fixed_2R", "fixed_3R", "fixed_5R"]
SYMS = ["XAUUSD", "EURUSD", "GBPUSD", "GBPJPY", "WTIUSD"]


def sweep_configs():
    seen, out = set(), []
    for c in enumerate_primary_grid():
        if c.entry_model == "cascade" and c.ltf == "M1":
            continue                                   # established worst; omit for speed
        key = (c.entry_model, c.htf, c.mtf, c.ltf, c.direct_poi_source)
        if key in seen:
            continue
        seen.add(key)
        for tp in RRS:
            out.append(replace(c, tp_mode=tp, be_trigger_R=1.0))
    return out


def main() -> None:
    syms = [a for a in sys.argv[1:] if not a.startswith("--")] or SYMS
    out_dir = REPO_ROOT / "output" / "grid" / "tp_sweep"
    out_dir.mkdir(parents=True, exist_ok=True)
    cfgs = sweep_configs()
    for s in syms:
        inst = get_instrument(s)
        m1 = load_is(DataConfig.for_symbol(s))
        df = run_grid(m1, cfgs, instrument=inst, cost=CostModel(inst), verbose=True)
        df = apply_multiple_testing(df, n_trials=len(cfgs))
        df.insert(0, "rr", df["tp_mode"])
        df.to_csv(out_dir / f"{s}.csv", index=False)
        print(f"[{s}] wrote {len(df)} configs (be@1R sweep)")
    # quick aggregate across instruments
    frames = [pd.read_csv(out_dir / f"{s}.csv").assign(instrument=s) for s in syms]
    A = pd.concat(frames, ignore_index=True)
    print("\n=== expectancy by fixed RR target (be@1R), pooled over 5 instruments x entries ===")
    for tp in RRS:
        sub = A[A.tp_mode == tp]
        print(f"{tp:9} n={len(sub):3d}  mean_ER={sub.expectancy_R.mean():+.3f}  "
              f"median={sub.expectancy_R.median():+.3f}  pos={int((sub.expectancy_R>0).sum())}/{len(sub)}  "
              f"best={sub.expectancy_R.max():+.3f}  win%={sub.win_rate.mean()*100:.1f}  "
              f"BH_survivors={int(sub.bh_reject.sum())}")


if __name__ == "__main__":
    main()
