# MERGE_PLAN — unifying the SMC/MTF falsification repos onto one engine

**Status:** APPROVED (Stage 1 → 2 planning). Building the unified repo **locally** on branch
`merge-unify`. **Do NOT push to GitHub** — the upload is a separate final step, approved only after the
merged repo + re-run numbers are reviewed.

This repo (`MTF Analysis`, package `mtf_smc/`) is the **canonical base**. The old repo
(`Algorithmic Trading System`, package `smc_mtf/`, published as
`github.com/AaroNLaU0307/quant-backtest-framework`, 1 commit) is **retired**: its unique analyses and
its strategy/risk machinery are **ported onto this engine**, then the old package is dropped.

## Locked decisions
1. **One engine, re-run everything (option A).** All old analyses are re-run on the unified (new)
   engine; the old engine is not kept. The published walk-forward figure **OOS −0.27R [−0.36,−0.18],
   N=521 (old engine)** *will change* under the new engine (intrabar-M1 fills, per-fill cost
   attribution, NY-close anchor, Wilder ATR). The updated number is the more rigorous result and
   replaces the old one (the old is cited only as "earlier-engine result" in a history note).
2. **Canonical = `mtf_smc/` (sub-packaged), English throughout.** `smc_mtf/` retired; any kept logic is
   translated from the old (Chinese) config/code to English.
3. **Port the old strategy/risk machinery as OPTIONAL, OFF-BY-DEFAULT ablation knobs** so (a) the
   unified-engine walk-forward can faithfully reproduce the old strategy and (b) the institutional risk
   machinery is available as a feature. Off-by-default ⇒ the committed 42-config grid stays
   **bit-identical** (re-verified each phase).
4. **Three-lens narrative.** One SMC strategy, falsified independently by: **(L1)** walk-forward OOS
   (optimize-IS → test-OOS), **(L2)** multiple-testing-corrected multi-instrument replication, **(L3)**
   two-null random-entry edge benchmark.

## Source of the old code
The local `Algorithmic Trading System` working tree is **ahead of the published 1-commit repo** by a
genuine fix (spread double-count in `portfolio.py`/`positions.py`). **Port from the local working
tree.** (The fix is moot for behaviour — the new engine already charges spread once per fill,
independently verified — but logic is sourced from the corrected local version.)

## Explicitly out of scope
- **`multi_asset_tsmom/`** (separate standalone project) — NOT merged.
- **TSMOM in this repo** = `scripts/run_momentum_control.py` only. NOT folded into the SMC narrative.
  Pending your decision: keep it as a labeled *power-calibration control* for the falsification method,
  or split it out. Until you decide, it stays as-is, clearly labeled, outside the three-lens story.

## Phased execution (each phase: tested, bit-identical-checked, committed on `merge-unify`)
- **M0 — Setup.** Branch + this spec. ✅
- **M1 — Config unification.** Translate the old strategy/risk/filter/exit/exec params into the new
  typed config as **off-by-default** English fields (a `legacy`/ablation section). Add a named preset
  `StrategyConfig.legacy_d1h1m5()` = the old fixed **D1→H1→M5 @ 0.5%** setup. No behaviour change yet.
- **M2 — Strategy/risk machinery port** (the large phase; wire the M1 knobs to logic):
  - **M2a** hybrid-Fib TP (`min(4.236·leg, nearest D1 liquidity)`) as a `tp_mode`; OB/Breaker POI types;
    TK CB/DB break detectors; confluence scoring. (Single-position; bit-identical-safe off by default.)
  - **M2b** execution filters: session (Asia block + GBPJPY exception), spread, news-blackout interface.
  - **M2c** ⚠️ **Portfolio-level risk = architectural.** The new engine runs **one instrument at a time**
    (the grid); the old ran a **simultaneous multi-instrument portfolio** (correlation-group caps,
    daily/consecutive-loss circuit breakers, shared ledger). Porting this needs a new **portfolio
    backtest loop** over aligned multi-instrument bars. Flagged as the biggest single item — sequenced
    last, behind a `run_portfolio` entry point; the per-instrument grid path is untouched.
- **M3 — Analyses port.** (i) 1D/2D **parameter-sensitivity scan** on the new engine
  (`robustness/sensitivity.py` + `scripts/run_sensitivity.py`); (ii) **optimize-IS → test-OOS
  walk-forward** (`robustness/walkforward.py` gains the optimizing variant + `scripts/run_walkforward.py`).
  Optimization space = the unified parameter space (new grid axes + ported old knobs).
- **M4 — Re-run on the unified engine.** Run the old strategy preset (D1/H1/M5 @ 0.5% + machinery)
  through the new engine for: optimizing walk-forward (→ the updated OOS figure), sensitivity, stratified
  /regime. Report updated numbers honestly; archive the old −0.27R as an earlier-engine footnote.
- **M5 — Docs unification.** One README leading with the three lenses; merge SPEC + briefs; retire the
  `smc_mtf/` narrative; update reproduction commands; one honest prior-work lineage paragraph.

## Deduplicate / drop (once their unique value is ported)
Old reimplemented **engine/detectors/loader/cost-model/InstrumentSpec** — superseded by the new
(intrabar fills, per-fill cost attribution, proven no-look-ahead, Wilder, NY anchor). Drop the old flat
`smc_mtf/` package after M2–M4 confirm the ported logic runs on the new engine.

## Stop conditions
- Each phase keeps `pytest` green and the XAUUSD 42-grid **bit-identical** (MD5 / <1e-9).
- **No `git push` / GitHub upload** at any point in this stage. Final upload is a separate approval.
