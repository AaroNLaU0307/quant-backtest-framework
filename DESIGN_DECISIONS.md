# Design decisions & known objections

*A short briefing, not an essay — the strongest objections to this study, answered with the repo's own
evidence: plainly, with the number attached, caveats included. Grounded only in what
[`docs/MERGE_REPORT.md`](docs/MERGE_REPORT.md) and [`docs/REPORT_MULTI_ASSET.md`](docs/REPORT_MULTI_ASSET.md)
already show; nothing here is a new claim.*

---

## "The +2.0 R on gold and +1.0 R on GBPJPY look real — why call this a null result?"

Because neither survives the test the study was designed to apply: **is it positive on more than one
independent instrument, and significant on any?** `cascade_W1_H4_M15_HTF_level` (+2.00 R gold) is positive
on only one other instrument (GBP +0.14) and **negative on the remaining three** (EUR −0.54, JPY −0.54,
WTI −0.33); `cascade_W1_H4_M5_HTF_level` (+1.05 R GBPJPY) is **negative on all four of the others** (XAU
−0.14, EUR −0.62, GBP −0.19, WTI −0.16). Neither is significant on the instrument where it looks best, let
alone elsewhere. This is the textbook small-*N* mirage — exactly the pattern a single-instrument backtest
cannot catch, and exactly why the study was designed around replication rather than a single headline cell.
[`docs/REPORT_MULTI_ASSET.md`](docs/REPORT_MULTI_ASSET.md) §5.

## "Why three separate falsification lenses instead of one definitive test?"

Because each is a **different way to be wrong**, and they don't overlap: **L1** (walk-forward) optimizes
*detection thresholds* on a fixed timeframe cascade; **L2** (replication grid) fixes the strategy and
varies the *config × instrument* grid with multiplicity control; **L3** (random-entry) removes the *entry
signal* entirely and asks whether structure adds anything over noise. A strategy could pass any one of
these by luck. All three returning negative — a CI-excluding-zero walk-forward loss, a 0/210 replication
grid, and indistinguishability from random entries — is a much harder coincidence to explain away than one
failed test. [`docs/MERGE_REPORT.md`](docs/MERGE_REPORT.md) states this design choice up front.

## "L1 only covers EUR+XAU, but L2 covers five instruments — isn't that an inconsistent scope?"

Deliberately, not accidentally. L1 exists to **reproduce a specific pre-existing claim** — the earlier
single-instrument repo's walk-forward result, which was only ever tested on EUR+XAU with its own earlier
engine — faithfully, on the new engine, to see if a better engine rescues it (it doesn't: −0.27 R becomes
**−0.339 R**, same verdict, sharper CI). L2 is the **fresh, pre-registered** multi-instrument design built
for this study specifically to test replication. Different questions, different scopes, both stated
explicitly rather than silently mismatched. [`docs/MERGE_REPORT.md`](docs/MERGE_REPORT.md) §L1.

## "How do you know `legacy_smc` really reproduces the old strategy, and isn't just something similar?"

Verified behaviourally against the actual old engine, not asserted structurally: run on the **same
byte-identical M1 cache**, the old and new engines land **86% of post-warmup entries** on the same M5 bar
within a few dollars, and matched trades agree in **realized-R sign 16/18**. That is not 100% — the study
says 86%, not "identical" — but it's high enough to rule out the detection-threshold drift that would
otherwise make the L1 comparison meaningless, and the gap is disclosed rather than rounded up.
[`docs/MERGE_REPORT.md`](docs/MERGE_REPORT.md) *Fidelity* section.

## "A gold-calibrated constant produced an impossible −25 R on EURUSD — how do you know there isn't another bug like it hiding somewhere?"

The bug itself was caught by **watching an implausible output**, not by a passing test — the original
sign-off check only ever exercised a winning trade, which never touches the stop path. Once found, the
response wasn't just a patch: every numeric constant in the detection → indicator → fill/FSM → cost/risk
path was enumerated and classified as scale-invariant (ATR/pip/tick/R-relative) or absolute-price
(must come from `InstrumentSpec`). The two offenders (`stop_slippage`, the breakeven buffer) were the
**only** absolute-price constants found in the whole path. The fix is verified **dynamically, not just by
inspection**: the median real stop-out is **−1.02 to −1.04 R on all five instruments**, GBPJPY and WTIUSD
included, and every instrument now runs a dedicated −1R stop-out assertion in addition to the original
winning-trade check. [`docs/REPORT_MULTI_ASSET.md`](docs/REPORT_MULTI_ASSET.md) §3.2–3.3.

## "Why BH-FDR plus a correlation-based effective-*N* deflation, instead of Bonferroni across all 210 trials?"

Because five instruments are demonstrably **not** five independent observations: GBPUSD–GBPJPY correlate
at **0.68**, EURUSD–GBPUSD at **0.59** — they share USD/GBP factors. Treating them as five independent
votes and applying a standard correction would have understated how correlated the "replication" evidence
really is. The **effective number of independent instruments is 3.45 of 5** (participation ratio of the
correlation eigenvalues), so pooled variance is inflated ×1.45 before any significance claim — the
opposite direction of a p-hacking shortcut, and disclosed as the pre-registered method rather than picked
after seeing results. [`docs/REPORT_MULTI_ASSET.md`](docs/REPORT_MULTI_ASSET.md) §4.

## "Why leave the sealed 2023–2025 OOS sealed — isn't that avoiding the real test?"

The pre-registered rule is the opposite of avoidance: the OOS unseals **once, only for a configuration
that survives IS replication and correction first**. Nothing did — 0/42 within-instrument, 0/210 across
the full grid. Opening the OOS anyway, with no surviving candidate to confirm, would be looking for a
result to justify rather than testing one — the exact behaviour the pre-registration exists to prevent.
(XAUUSD's OOS window had also already been spent once, in the prior single-instrument study, which is a
second, independent reason not to revisit it here.) [`docs/REPORT_MULTI_ASSET.md`](docs/REPORT_MULTI_ASSET.md) §1.

## "What would it concretely take for you to revisit this strategy?"

Two things, both currently far from met: (1) a configuration **positive-and-significant on at least two
independent instruments** after the cross-instrument BH-FDR correction — the current count is **0 of
210**; (2) the L1 walk-forward flipping from **E[R] = −0.339 R, 95% CI [−0.45, −0.22], 21/24 windows
negative (sign-test p = 0.0001)** to a CI that excludes zero on the *positive* side. Only after both would
a single, one-time OOS unsealing be warranted. Nothing here is close, and no partial version of either
condition (e.g. one instrument, one window) is being treated as sufficient.

## "Isn't WTIUSD's thin 2017 (a real 9-day data gap) and the 2020 negative-oil event reason to discount its null result?"

Both are disclosed, investigated, and don't move the conclusion. The **217-hour Feb-2017 gap** is real
(a HistData source gap, not a processing bug) and does reduce WTI's effective early-IS sample — stated as
a limitation, not smoothed over. The **April-2020 negative-oil event** was inspected directly: the spot
CFD feed floors at **$6.495 with zero negative or garbage prints** — a genuine high-volatility regime,
confirmed real by cross-checking against the other known 2019–2020 WTI shocks (Abqaiq, the March-2020 OPEC
crash), not a data artifact requiring a patch. And the result the caveats might threaten doesn't need
saving: WTI's M1-cascade expectancy (**−0.47 R**) sits squarely alongside the other four instruments'
(**−0.53, −0.62, −0.59, −0.65 R**) — the null is uniform, not WTI-dependent.
[`docs/REPORT_MULTI_ASSET.md`](docs/REPORT_MULTI_ASSET.md) §2, §3.4.

---

*This document makes no claims the rest of the repo doesn't already make. If a question above sends you
looking for the underlying number and it isn't where this doc says it is, that's a bug in this doc, not a
new finding.*
