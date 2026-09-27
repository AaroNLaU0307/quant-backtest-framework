# MTF-SMC under Three Falsification Lenses — Unified Report

*In-sample 2015–2022 (sealed OOS 2023–2025 untouched) · XAUUSD, EURUSD, GBPUSD, GBPJPY, WTIUSD ·
realistic per-instrument costs.*

> **Re-run (2026-09-27).** Every L1–L3 number in this report is from the re-run on the corrected engine
> ([`ADDENDUM_2026-09-27.md`](ADDENDUM_2026-09-27.md) §11); the fidelity figures compare the pre-fix
> engine with the old one and were not re-run.

This report unifies two previously separate efforts — a **single-instrument repo** that walk-forward-tested
a discretionary MTF-SMC strategy, and this **multi-instrument repo** that pre-registered a 42-configuration
replication grid — onto **one engine** (`mtf_smc/`). The merged question is asked through **three complementary
lenses**, each a different way to be wrong:

| Lens | Method | Result |
|---|---|---|
| **L1 — Walk-forward OOS** | Optimize the legacy detection-threshold space on a *fixed* D1→H1→M5, roll IS18/OOS6 | **E[R] = −0.329 R**, window-block 95% CI **[−0.416, −0.228]**, 11/12 calendar periods negative (p = 0.0032) |
| **L2 — Replication grid** | 42 pre-registered configs × 5 instruments, BH-FDR + correlation-aware meta | **0 / 210** survive; best pooled **+0.004 R** (p = 0.493) |
| **L3 — Random-entry nulls** | Two random-entry controls on the XAUUSD IS survivors (XAUUSD only) | **E[R] inside the random-entry nulls' 5–95 % band (72nd–93rd percentile); net-negative** |

The lenses ask different questions: L1 optimizes *detection thresholds* on two instruments; L2 fixes the
strategy and varies the *config grid* across five instruments with multiplicity control; L3 removes the
*entry signal* and asks whether the structure beats random entries. They share one engine and one IS
period, so an engine flaw reaches all three. **None finds an edge that survives costs.**

---

## L1 — Walk-forward of the legacy strategy on the rigorous engine (the updated −0.27 R)

The single-instrument repo's headline was a walk-forward out-of-sample expectancy of **−0.27 R** (EUR+XAU,
its earlier engine). We reproduced that strategy faithfully as the off-by-default `legacy_smc` entry model
(see *Fidelity* below) and re-ran the **same rolling walk-forward** on the new engine: per instrument,
rolling **IS 18 mo / OOS 6 mo / step 6 mo**; on each IS window pick the
`{min_confluence_score} × {min_retracement}` grid point with the best IS mean-R (≥ 8-trade guardrail);
evaluate those parameters on the adjacent OOS window; verdict = **OOS only**.

**Result (pooled OOS, EUR+XAU, 24 windows, N = 438 trades; `output/legacy_walkforward/walkforward_summary.txt`):**

```
ALL pooled (EUR+XAU)  E[R] = -0.329   iid 95% CI [-0.439, -0.214]   block-bootstrap 95% CI [-0.416, -0.228]
  EURUSD              E[R] = -0.275   iid 95% CI [-0.463, -0.079]
  XAUUSD              E[R] = -0.376   iid 95% CI [-0.504, -0.239]
  calm 2016-2019      E[R] = -0.351      trend 2020-2022   E[R] = -0.302
  sign test, 12 calendar periods: 11/12 negative, one-sided p = 0.0032
  IS->OOS mean gap = +0.336            (the IS optimum overfits and collapses out-of-sample)
```

**Robustness of the negative.** Trades within a window are correlated, so the trade-level bootstrap CI
above is *optimistically narrow*. The headline interval is the **block bootstrap by window** (resampling
whole windows): **[−0.416, −0.228]** — still excluding zero. (One instrument's OOS windows do not
overlap — the step equals the OOS length — only its IS windows do.) **20 of 24 windows are negative**
(median window −0.325), but XAUUSD and EURUSD roll the same 12 calendar periods, so those are not 24
independent signs; the sign test on the 12 calendar periods (both instruments' trades pooled per period)
gives **11/12 negative, one-sided p = 0.0032**. The IS-best parameters drift toward the *loosest* filter
(`score = 1`, 15 of 24 windows) and then fail OOS — the textbook overfit signature, quantified by the
**+0.34 R IS→OOS gap**.

**Old → new.** The earlier-engine −0.27 R becomes **−0.329 R** on the unified engine
(DST-anchored NY-close D1/W1, intrabar-M1 fills, per-fill cost attribution, Wilder ATR), with the two
look-ahead paths corrected on 2026-09-27 (the L1 target is the nearest D1 swing; before the fix this
figure was −0.339 R). Same sign, same verdict — *no robust edge* — with a confidence interval that
excludes zero.

> **Span note.** The new walk-forward lives entirely inside the sealed-wall IS span **2015–2022**; the old
> run rolled into 2023 (it had no sealed OOS). The updated number is therefore on a slightly shorter span,
> stated rather than silently substituted.

### Fidelity — `legacy_smc` *is* the old strategy (verified behaviourally, not just structurally)

The L1 number is only meaningful if `legacy_smc` reproduces the old strategy. This was proven by running
the **old engine** on the **byte-identical M1 cache** (outputs redirected out of the read-only old folder,
bytecode disabled) and comparing, on XAUUSD 2019–2021:

- **Entries:** H1 deep-Fib-OTE **confluence POIs** 334 (old) vs 323 (new); **86 % post-warmup entry
  overlap**, matched trades landing on the same M5 bar within a few dollars. This rules out the subtle
  detection-threshold drift that would otherwise invalidate the reproduction.
- **Exits:** the old strategy takes **no scale-out** (confirmed in `trade_manager.py`); its hybrid-Fib TP
  targets the **nearest D1 swing-liquidity**, reproduced exactly by `htf_target_mode="nearest_swing"`
  (lookback 2 = the old `swings(htf)`). On matched trades the realized **R agrees in sign 16/18**, with
  near-identical stops.
- **Triggers** are the old `FVG AND (MSS OR CB/DB)`; **session filter** blocks the Asia window per the old
  default. The whole legacy stack is off-by-default, so the 42-config grid stays **bit-identical**
  (MD5 `08616bc4…`, `max |Δ| = 0`).

---

## L2 — Pre-registered multi-instrument replication

Unchanged by the merge: **0 / 42** configurations are positive-and-significant on even one instrument
after within-instrument BH-FDR; **0 / 42** on two or more; **0 / 210** (config × instrument) cells survive
the cross-instrument BH-FDR; best correlation-aware random-effects pooled expectancy **+0.004 R**
(one-sided p = 0.493). Five instruments are deflated to an **effective 3.45 independent** by the
cross-instrument correlation matrix. Full write-up: [`REPORT_MULTI_ASSET.md`](REPORT_MULTI_ASSET.md);
tables: [`REPLICATION.md`](REPLICATION.md).

## L3 — Random-entry nulls

Run on XAUUSD only, on the three least-negative IS survivors: two random-entry controls (unconstrained
and bias-matched; 1000 nulls each; matched trade count, stop distances and holding times). The strategy's
per-trade E[R] is *less negative* than the null mean — +0.088 R (`cascade_D1_H4_M15_fixed_3R`), +0.142 R
(`cascade_W1_H1_M5_fixed_3R`) and +0.112 R (`cascade_D1_H4_M5_fixed_3R`) over the bias-matched null, an
upper bound because the holding-time match is imperfect — but on E[R] it sits at the **72nd–91st
percentile** of the bias-matched null (76th–93rd of the unconstrained), inside each null's 5–95 % band
(on per-trade Sharpe one config, `cascade_D1_H4_M5_fixed_3R`, reaches the 96th percentile of both nulls,
uncorrected). So on expectancy the entries are **not distinguishable from random entries**, and the
strategy stays net-negative
(`output/robustness/random_entry.csv`). See [`REPORT.md`](REPORT.md) §6 and `docs/SPEC.md` §8.

---

## What the merge produced

- **One canonical engine, `mtf_smc/`.** The old strategy now lives as the off-by-default `legacy_smc`
  entry model plus ported machinery (confluence scoring, CB/DB, displacement-FVG, BOS-legs, session
  filter), each additive and behind a flag so the verified grid path is untouched.
- **`smc_mtf/` is retired.** The old package is superseded by `mtf_smc/`; its strategy is reproduced
  faithfully as `legacy_smc`, and its earlier-engine numbers (the −0.27 R walk-forward) are archived as
  **earlier-engine footnotes**, replaced by the unified-engine L1 figure above. The old repo is preserved
  read-only as historical provenance; nothing from it is carried forward as live code.

### Portfolio overlay (M2c) — implemented, off-default, deferred

Portfolio-risk overlay implemented (`scripts/run_portfolio.py`, off-default): one-position-per-symbol,
concurrent + correlation-group risk caps, daily + consecutive-loss circuit breakers, faithful to the old
`RiskParams`. Full-IS run deferred — it exceeds reap-safe chunking, and as a risk overlay on a
per-trade-negative strategy its effect is variance/drawdown reduction, not edge creation (mathematically
predetermined). **Listed as future work.**

---

## Conclusion

Three complementary falsification lenses — a detection-threshold **walk-forward** (−0.329 R, block CI
excludes zero, 11/12 calendar periods negative), a multiple-testing-corrected **multi-instrument
replication** (0/210), and a **random-entry** control (XAUUSD: inside the random-entry band, net-negative)
— all point to the same verdict: **the MTF-SMC strategy carries no replicable, out-of-sample edge.** These
results are from the re-run on the engine corrected on 2026-09-27. The
locked OOS (2023–2025) stays sealed; by the pre-registered rule nothing earned a look.
