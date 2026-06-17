"""Fidelity gate (M2.5, docs/MERGE_PLAN.md): evidence that `legacy_smc` reproduces the OLD strategy.

Runs the `legacy_d1h1m5()` preset (D1->H1->M5 @ 0.5%, hybrid-Fib TP) on a slice and reports the trade
profile + structural evidence: H1 deep-Fib-OTE confluence POIs (score gate), entries derived from an
M5 `FVG AND (MSS OR CB/DB)` trigger with the protective inside the OTE band. It does NOT run the old
engine (that would write outputs into the old read-only folder); this is the direct structural evidence.

    .venv\\Scripts\\python scripts\\run_legacy_fidelity.py XAUUSD 2019:2021
"""
from __future__ import annotations

import sys

import numpy as np

from mtf_smc.config import DataConfig, StrategyConfig
from mtf_smc.data.loader import load_is
from mtf_smc.engine.backtester import simulate
from mtf_smc.engine.costs import CostModel
from mtf_smc.risk.instrument import get_instrument
from mtf_smc.strategy.context import build_context
from mtf_smc.strategy.entries import generate_setups
from mtf_smc.strategy.legacy_poi import build_confluence_pois


def main() -> None:
    sym = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD"
    sl = sys.argv[2] if len(sys.argv) > 2 else "2019:2021"
    a, b = sl.split(":")
    m1 = load_is(DataConfig.for_symbol(sym)).loc[a:b]
    cfg = StrategyConfig.legacy_d1h1m5()
    inst = get_instrument(sym)
    ctx = build_context(m1, cfg)

    poi_kw = dict(
        swing_lookback=cfg.swing_lookback, min_retracement=cfg.legacy_min_retracement,
        ob_use_wick=cfg.legacy_ob_use_wick, fvg_min_atr_mult=cfg.fvg_min_atr,
        disp_atr_mult=cfg.legacy_disp_atr_mult, disp_body_ratio=cfg.legacy_disp_body_ratio,
        confluence_overlap_pct=cfg.legacy_confluence_overlap_pct,
        confluence_atr_dist=cfg.legacy_confluence_atr_dist,
        min_confluence_score=cfg.legacy_min_confluence_score,
        fib_ext_be=cfg.legacy_fib_ext_be, fib_ext_tp=cfg.fib_ext_tp,
    )
    pois = {d: build_confluence_pois(ctx["H1"].df, d, ctx["H1"].atr, **poi_kw) for d in ("long", "short")}
    setups, _ = generate_setups(m1, cfg, ctx=ctx)
    trades, _, _ = simulate(m1, setups, cfg, inst, CostModel(inst))

    print(f"=== FIDELITY GATE: legacy_smc on {sym} {sl}  (D1->H1->M5 @ 0.5%, hybrid-Fib TP) ===")
    scores = [p.confluence_score for d in pois for p in pois[d]]
    print(f"H1 confluence POIs: long {len(pois['long'])}, short {len(pois['short'])}  "
          f"| score gate >= {cfg.legacy_min_confluence_score} (deep-Fib OTE + >= "
          f"{cfg.legacy_min_confluence_score - 1} PD array); score dist " +
          ", ".join(f"{s}->{scores.count(s)}" for s in (1, 2, 3)))

    nL = sum(s.direction == "long" for s in setups)
    kinds = ", ".join(f"{k}:{sum(s.tag == 'legacy_' + k for s in setups)}" for k in ("mss", "cb", "db"))
    print(f"setups: {len(setups)} (long {nL}, short {len(setups) - nL}); trigger kinds -> {kinds}")
    # entry on the correct side of the OTE bound (long: at/above; short: at/below) — structural check
    ok = sum((s.direction == "long" and s.entry >= s.invalidation) or
             (s.direction == "short" and s.entry <= s.invalidation) for s in setups)
    print(f"entries on the correct side of the OTE band: {ok}/{len(setups)} "
          f"(protective-inside-OTE is enforced by the trigger gate)")

    if trades:
        R = np.array([t.realized_R for t in trades])
        tL = sum(t.direction == "long" for t in trades)
        print(f"trades: {len(trades)}  win_rate={np.mean(R > 0):.3f}  meanR={R.mean():+.3f}  "
              f"(long {tL}, short {len(trades) - tL})")
    print("sample setups (dir / entry / stop / OTE-bound / hybrid-TP / trigger):")
    for s in setups[:8]:
        print(f"  {s.direction:5} entry={s.entry:<9.5g} stop={s.initial_stop:<9.5g} "
              f"ote={s.invalidation:<9.5g} tp={s.htf_target:<9.5g} {s.tag}")


if __name__ == "__main__":
    main()
