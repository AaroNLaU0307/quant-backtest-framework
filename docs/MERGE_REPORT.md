# MTF-SMC under Three Falsification Lenses — Unified Report

*In-sample 2015–2022 (sealed OOS 2023–2025 untouched) · XAUUSD, EURUSD, GBPUSD, GBPJPY, WTIUSD ·
proven no-look-ahead · realistic per-instrument costs.*

This report unifies two previously separate efforts — a **single-instrument repo** that walk-forward-tested
a discretionary MTF-SMC strategy, and this **multi-instrument repo** that pre-registered a 42-configuration
replication grid — onto **one engine** (`mtf_smc/`). The merged question is asked through **three disjoint
lenses**, each a different way to be wrong:

| Lens | Method | Result |
|---|---|---|
| **L1 — Walk-forward OOS** | Optimize the legacy detection-threshold space on a *fixed* D1→H1→M5, roll IS18/OOS6 | **E[R] = −0.339 R**, 95% CI **[−0.45, −0.22]**, 21/24 windows negative |
| **L2 — Replication grid** | 42 pre-registered configs × 5 instruments, BH-FDR + correlation-aware meta | **0 / 210** survive; pooled **−0.000 R** |
| **L3 — Random-entry nulls** | Two random-entry controls per instrument on IS survivors | strategy **indistinguishable from random** |

The lenses are deliberately **non-overlapping**: L1 optimizes *detection thresholds* on two instruments;
L2 fixes the strategy and varies the *config grid* across five instruments with multiplicity control; L3
removes the *entry signal* entirely. **All three return negative.** A finding that survives three
independent ways of trying to break it is a far stronger falsification than any single test.

---

## L1 — Walk-forward of the legacy strategy on the rigorous engine (the updated −0.27 R)

The single-instrument repo's headline was a walk-forward out-of-sample expectancy of **−0.27 R** (EUR+XAU,
its earlier engine). We reproduced that strategy faithfully as the off-by-default `legacy_smc` entry model
(see *Fidelity* below) and re-ran the **same rolling walk-forward** on the new engine: per instrument,
rolling **IS 18 mo / OOS 6 mo / step 6 mo**; on each IS window pick the
`{min_confluence_score} × {min_retracement}` grid point with the best IS mean-R (≥ 8-trade guardrail);
evaluate those parameters on the adjacent OOS window; verdict = **OOS only**.

**Result (pooled OOS, EUR+XAU, 24 windows, N = 478 trades):**

```
ALL pooled (EUR+XAU)  E[R] = -0.339   95% CI [-0.446, -0.223]   significantly NEGATIVE
  EURUSD              E[R] = -0.341   95% CI [-0.507, -0.162]
  XAUUSD              E[R] = -0.337   95% CI [-0.474, -0.185]
  calm 2016-2019      E[R] = -0.357      trend 2020-2022   E[R] = -0.311
  IS->OOS mean gap = +0.387            (the IS optimum overfits and collapses out-of-sample)
```

**Robustness of the negative.** Because the windows overlap and trades within a window are correlated, the
naive trade-level bootstrap CI is *optimistically narrow*. A **block bootstrap by window** (resampling
whole windows) gives essentially the same interval, **[−0.436, −0.223]** — still excluding zero. And the
conclusion does not rest on any CI at all: **21 of 24 windows are negative** (median window −0.350), a
**sign-test p = 0.0001**. The IS-best parameters drift toward the *loosest* filter (`score = 1`) and then
fail OOS — the textbook overfit signature, quantified by the **+0.39 R IS→OOS gap**.

**Old → new.** The earlier-engine −0.27 R becomes **−0.339 R** on the more rigorous engine
(DST-anchored NY-close D1/W1, intrabar-M1 fills, per-fill cost attribution, Wilder ATR). Same sign, same
verdict — *no robust edge* — now with a confidence interval that cleanly excludes zero. The honest engine
does not rescue the strategy; it confirms the null more sharply. This is the intended **"old strategy,
better engine"** outcome.

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

Unchanged and definitive: **0 / 42** configurations are positive-and-significant on even one instrument
after within-instrument BH-FDR; **0 / 42** on two or more; **0 / 210** (config × instrument) cells survive
the cross-instrument BH-FDR; best correlation-aware random-effects pooled expectancy **−0.000 R**
(one-sided p ≥ 0.50). Five instruments are deflated to an **effective 3.45 independent** by the
cross-instrument correlation matrix. Full write-up: [`REPORT_MULTI_ASSET.md`](REPORT_MULTI_ASSET.md);
tables: [`REPLICATION.md`](REPLICATION.md).

## L3 — Random-entry nulls

On the IS survivors, two random-entry controls (matched trade count / holding time) place the strategy's
expectancy **inside the random-entry distribution** — the structured entries add no edge over noise.
See [`REPORT.md`](REPORT.md) and `docs/SPEC.md` §8.

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

Three disjoint falsification lenses — a detection-threshold **walk-forward** (−0.339 R, CI excludes zero,
21/24 windows negative), a multiple-testing-corrected **multi-instrument replication** (0/210), and a
**random-entry** control (indistinguishable from noise) — all return the same verdict: **the MTF-SMC
strategy carries no replicable, out-of-sample edge.** The locked OOS (2023–2025) stays sealed; by the
pre-registered rule nothing earned a look. A negative this robust to *how* you test it is the contribution.
