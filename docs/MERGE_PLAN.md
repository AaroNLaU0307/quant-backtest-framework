# MERGE_PLAN — unifying the SMC/MTF falsification repos onto one engine

**Status:** COMPLETE (M1–M5 done; M2c portfolio overlay implemented but full-IS run deferred — see
[`MERGE_REPORT.md`](MERGE_REPORT.md)). Built **locally** on branch `merge-unify`. Outcome: L1 walk-forward
**−0.339 R** [−0.45, −0.22] (the updated −0.27 R), L2 replication **0/210**, L3 random-entry null — unified
in [`MERGE_REPORT.md`](MERGE_REPORT.md). **Not pushed** — the upload is a separate final step, pending
review of the merged repo + re-run numbers + the unified README.

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
4. **Three-lens narrative — distinct questions, no overlap.** One SMC strategy, falsified independently
   by: **(L1)** walk-forward OOS = the *overfitting* test, optimizing over the **continuous old
   detection-threshold space** on fixed D1->H1->M5; **(L2)** *multiple-testing-corrected multi-instrument
   replication* over the **pre-registered 42-config grid**; **(L3)** *two-null random-entry* edge
   benchmark. The lenses stay disjoint: WF is **never** run as an optimizer over the pre-registered
   42-grid (those are L2's confirmatory, BH-FDR-corrected set; optimizing over them and picking winners
   would violate the pre-registration and blur L1 into L2).

## Source of the old code
The local `Algorithmic Trading System` working tree is **ahead of the published 1-commit repo** by a
genuine fix (spread double-count in `portfolio.py`/`positions.py`). **Port from the local working
tree.** (The fix is moot for behaviour — the new engine already charges spread once per fill,
independently verified — but logic is sourced from the corrected local version.)

## Explicitly out of scope
- **`multi_asset_tsmom/`** (separate standalone project) — NOT merged.
- **TSMOM in this repo** = `scripts/run_momentum_control.py`, **kept** but labeled strictly as a
  *power-calibration control* for the falsification method (it shows the framework detects a weak
  positive on a known-effective strategy, so the "SMC = no edge" verdict is not an artifact of an
  over-strict harness). It is **not** a TSMOM strategy, stays distinct from the separate
  `multi_asset_tsmom/` project, and stays outside the three-lens SMC narrative.

## Phased execution — RE-ORDERED: the updated walk-forward number lands BEFORE the portfolio loop
**Rationale:** the L1 walk-forward is a *single-instrument overfitting test*; it needs only the detection
layer + filters, **not** the multi-instrument portfolio loop (portfolio-layer risk is irrelevant to it).
So M2c is deferred to last, off the three-lens critical path. Each step: tested, bit-identical-checked,
committed on `merge-unify`.

**Done:** **M0** (branch + spec) · **M1** (`StrategyConfig.legacy_d1h1m5()` preset) · **M2a-hybrid**
(hybrid-Fib TP, bit-identical-verified). **Resume order:**

1. **M2a (cont.) — detection layer** (off-by-default, each bit-identical-checked): OB/Breaker POI types;
   TK-style CB/DB break detectors; confluence scoring. *(hybrid-Fib TP already done.)*
2. **M2b — execution filters:** session (Asia block + GBPJPY exception), spread, news-blackout interface.
   The legacy entry model (`legacy_smc`: D1 bias + H1 deep-Fib-OTE confluence POI + M5
   `FVG AND (MSS OR CB/DB)` trigger + hybrid-Fib TP) is assembled here, off the default `entry_model`.
2.5. **⛔ FIDELITY CHECKPOINT (before M3/M4).** Run `legacy_smc` on a small slice and surface a trade log
   showing it behaves like the OLD strategy (sane trade count; entries landing in the OTE/confluence
   zones). **Do NOT run the full walk-forward until the legacy strategy is confirmed faithful** — the
   single-config sanity step before scaling. A faithful −0.27R reproduction is only meaningful if the
   ported strategy genuinely *is* the old one.
3. **M3 — analyses:** 1D/2D parameter-sensitivity scan (`robustness/sensitivity.py` +
   `scripts/run_sensitivity.py`); the **L1 optimize-IS -> test-OOS walk-forward**
   (`robustness/walkforward.py` optimizing variant + `scripts/run_walkforward.py`), optimizing **only**
   over the old detection-threshold space on fixed D1->H1->M5 (decision 4: never over the 42-grid).
4. **M4 — re-run** the old preset (D1/H1/M5 @ 0.5% + machinery) through the unified engine → the
   **updated OOS walk-forward figure that replaces -0.27R**, plus the sensitivity scan + stratified/regime.
   ⛔ **CHECKPOINT — STOP and surface BOTH (i) the updated WF number AND (ii) old-vs-new fidelity evidence
   (trade counts / entry overlap on a common slice) for review before building further.** The number must
   stay **materially negative**; the fidelity evidence must show "same strategy, better engine," not a
   slightly different strategy. Archive old -0.27R as an earlier-engine footnote.
5. **M2c — portfolio loop (LAST, optional, off the critical path):** a separate `run_portfolio` path —
   simultaneous multi-instrument, correlation-group caps, daily/consecutive-loss circuit breakers, shared
   ledger. Architectural; the per-instrument grid path stays untouched.
6. **M5 — docs unification:** one README leading with the three lenses; merge SPEC + briefs; retire the
   `smc_mtf/` narrative; reproduction commands; one honest prior-work lineage paragraph.

## Deduplicate / drop (once their unique value is ported)
Old reimplemented **engine/detectors/loader/cost-model/InstrumentSpec** — superseded by the new
(intrabar fills, per-fill cost attribution, proven no-look-ahead, Wilder, NY anchor). Drop the old flat
`smc_mtf/` package in **M5**, once the ported logic is confirmed on the new engine.

## Stop conditions
- Each phase keeps `pytest` green and the XAUUSD 42-grid **bit-identical** (MD5 / <1e-9).
- **No `git push` / GitHub upload** at any point in this stage. Final upload is a separate approval.
