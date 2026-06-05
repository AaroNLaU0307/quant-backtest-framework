# Project Brief — Multi-Instrument Replication of the MTF-SMC Strategy

> The mandate for the multi-instrument replication, preserved as given (descriptive naming). It
> specifies **only the multi-instrument extension**; the strategy, detection primitives, engine,
> cost-model mechanics, and statistics are defined and verified in the core
> [`SPEC.md`](SPEC.md) / [`PROJECT_BRIEF.md`](PROJECT_BRIEF.md) and are reused unchanged.
> The calibration/decisions and methodology live in [`SPEC_multi_instrument.md`](SPEC_multi_instrument.md).

## 0 · Mission & stance

The single-instrument study found **0/42 statistically confirmable edge on XAUUSD** after the full
institutional apparatus, and its own conclusion pointed here: single-instrument structure alpha is too
thin → test whether anything survives **across multiple instruments**. This is that test.

The question changes: not "does it work on gold," but **"does any configuration show an edge that
*replicates* across independent instruments after correction?"** This is a **replication study**, still
falsification-oriented. State the pre-registered interpretation (§6) and honor it whatever the data
shows. The most likely outcome — and a valid, valuable one — is a **stronger multi-asset null**: the
handful of gold-positive configs were small-N noise and regress toward zero elsewhere. Do not tune
toward a positive result; surfacing that the noise does *not* replicate is the point.

## 1 · Build on the verified engine — reuse, do not fork

**Extend the existing repo in place.** Generalize the instrument layer to handle multiple instruments;
do **not** duplicate the engine into a new repo. The git history continues cleanly: the single-instrument
results → the multi-instrument replication. The portfolio narrative is one arc — single-instrument
falsification → cross-asset replication.

- **Reuse unchanged** (no silent re-derivation): the event-driven backtester, MTF as-of alignment +
  intrabar M1 fills, all detection primitives (swings/FVG/BOS-CHoCH/POI, Wilder ATR/EMA/Fib), the trade
  FSM (BE@2R / scale-out / frozen-at-entry HTF target), the 3 TP modes, the cost-model *mechanics*, and
  the stats/robustness layer (MC, two-null random-entry, bootstrap CIs, BH-FDR / DSR / PSR, walk-forward,
  regime).
- **New work here**: per-instrument data ingestion + **per-instrument cost/contract calibration** (§3),
  per-instrument grid runs (§4), and the **replication / meta-analysis + cross-instrument correction
  layer** (§5) — the actual contribution.
- **Regression guard**: after generalizing the instrument layer, the XAUUSD grid output must remain
  **bit-identical** to the committed master table (MD5 / <1e-9). Prove it before proceeding — the
  generalization must not perturb the existing result.

## 2 · Instruments & data

Five instruments total: XAUUSD (metal, 2015–2025, OOS 2023–2025 sealed), EURUSD (FX major, 2015–2023,
5-decimal pip 0.0001), GBPUSD (FX major, 2015–2023, 5-decimal), GBPJPY (FX cross, 2015–2023,
**JPY-quoted pip 0.01**, different tick convention), WTIUSD (crude oil CFD, 2015–2023, **not FX** — see
anchor + 2020 caveats).

**Confirm each new file's exact format, schema, and timezone before writing any code** (HistData MT-CSV
vs XLSX; fixed-EST source vs UTC). Don't assume they match XAUUSD's feed.

- Resample each to the same set (W1→M1) using the **existing NY-close DST-aware anchor** for the FX
  instruments (EURUSD/GBPUSD/GBPJPY share the FX/metals 17:00-NY trading-day convention — reuse the
  existing sessions module).
- **WTIUSD needs its own treatment — do not blindly apply the FX NY-close anchor.** Crude is a commodity
  with a different session/daily-settlement convention. Confirm the correct daily/weekly boundary for
  this feed and document it; make it config-switchable per instrument.
- **WTIUSD data-quality landmines**: explicitly inspect **April 2020** (the negative-WTI-futures event)
  for clipped/extreme/garbage prints, and any contract-rollover artifacts. Flag and document; do not let
  a bad April-2020 print silently drive results.
- **IS/OOS wall preserved**: develop on **IS = 2015–2022** (hard-sliced) for all instruments. The new
  instruments' **2023 = OOS** (verify per-instrument completeness; flag if thin). XAUUSD OOS stays
  2023–2025. OOS is touched only under §6's conditional rule.
- Per-instrument **data-quality report** (integrity, gaps, anchor verification), same as the existing
  `DATA_QUALITY.md`.

## 3 · Per-instrument cost & contract calibration — the #1 correctness item

Each instrument gets its **own `InstrumentSpec`**. **Do NOT inherit XAUUSD's numbers.** Getting this
wrong silently corrupts every R.

- Per instrument: contract size, **tick size / tick value**, **pip value**, realistic **spread**,
  **commission**, and **swap** (long/short). Document the source/assumption for each in the SPEC. JPY
  pairs and crude have different tick/pip math than 5-decimal majors — verify each.
- **Verify R accounting per instrument** with a known-PnL hand check (one constructed or real trade per
  instrument: confirm net PnL and realized R reconcile from the fills) — the same independent cross-check
  done for gold, repeated for each new instrument. A correct gold spec does **not** imply a correct
  GBPJPY or WTI spec.
- **Cost-dependence caveat to carry into interpretation**: the single-instrument finding that "M1-LTF
  cascades are killed by costs" is **cost-driven**, so it may **not** generalize — on tighter-spread
  majors (EURUSD/GBPUSD) the M1 configs could behave differently (likely still unprofitable, but the
  *degree* depends on per-instrument cost). This is itself a sub-question worth reporting, and a reason
  to run the full grid (§4) rather than assume the M1 configs are dead everywhere.

## 4 · Grid — run the full 42 on every instrument

Run the **complete 42-config grid on each instrument** — winners *and* losers, no pre-filtering.

- **Do not restrict to the configs that looked good on XAUUSD.** Selecting configs by their gold
  performance and only re-testing those is exactly the data-snooping trap this whole project guards
  against. (Restricting by a *performance-independent* criterion such as "N<30 on gold" would be
  defensible, but the optimized engine handles all 42 cheaply, so run everything.)
- Reuse the **optimized engine** (bit-identical `build_pois` binary-search + inert-bar fast-path already
  in place).
- **Observable, resumable runner** — per-config progress line flushed to a pollable file, one context in
  memory at a time, incremental CSV + resume. The earlier silent background deaths must not recur across
  5 instruments.
- Output a **per-instrument master table** (same columns as before), each with corrected significance
  computed *within* that instrument.

## 5 · Replication & meta-analysis — the new analytical core

**Estimate per instrument, then assess consistency. Never collapse correlated instruments into one
naive N.**

- **Replication table**: for each of the 42 configs, report **per-instrument E[R] side by side** (config
  × instrument grid), with N, CI, and significance per cell.
- **Replication / consistency test**: for each config, in how many *independent* instruments is it
  positive, and positive *and* individually significant? Report count and direction.
- **Cross-instrument correlation — mandatory before any pooling.** Estimate correlation across
  instruments (returns and/or trade-overlap). EURUSD/GBPUSD/GBPJPY share USD/GBP factors; WTIUSD more
  independent; XAUUSD USD-linked. Report the correlation matrix and an **effective number of independent
  instruments** (well below 5).
- **If pooling at all, correlation-aware** — random-effects meta-analysis, or block-bootstrap resampling
  instruments as correlated blocks, or at minimum the conservative consistency count. **Never a naive
  pooled t-test treating 5×17 trades as 85 independent obs.**
- **Cross-(config × instrument) multiple-testing correction**: BH-FDR (and DSR where applicable) across
  the full set of (config, instrument) trials; state the corrected threshold.
- **Two-null random-entry per instrument**: carry forward the unconstrained + bias-matched decomposition
  (per-trade E[R] / per-trade Sharpe, holding-matched, cap-with-management). **If any config survives
  in-sample replication, additionally run a high-spread / high-slippage sensitivity on GBPJPY and WTIUSD**
  specifically (they gap harder on news than the majors).

## 6 · Pre-registered interpretation — lock this BEFORE running

- **"Edge" = consistently positive AND individually significant across multiple *independent*
  instruments, surviving the cross-instrument correction.** A single-instrument win is not edge.
- A config positive on XAUUSD but regressing to ~0/negative elsewhere = **confirmed noise** (the expected
  outcome). State it plainly.
- **If nothing replicates**: a **stronger, multi-asset falsification** than the single-instrument result
  — more valuable. Frame it that way.
- **Conditional OOS one-shot**: *only if* a config survives IS multi-instrument replication + correction,
  evaluate it **once** on OOS (XAUUSD 2023–2025; new instruments' 2023). If nothing survives IS, do not
  touch OOS.

## 7 · Reporting

Per-instrument master tables + a master replication grid (config × instrument E[R], consistency flags,
corrected significance) + cross-instrument correlation matrix + meta-analysis. Plots: replication
heatmap, per-instrument equity/DD for any survivor, correlation matrix.
**`docs/REPORT_MULTI_ASSET.md`**, titled **"Multi-Instrument Replication of an MTF-SMC Strategy across
FX, Metals and Crude"**: abstract, replication question, per-instrument cost/anchor assumptions,
replication result, limitations, honest conclusion — with one honest paragraph of prior-work lineage.
Update `README`. Per-instrument YAML specs, fixed seeds, data instructions, no licensed data committed.

## 8 · Process

1. **Confirm each new file's schema/timezone, and calibrate + verify each `InstrumentSpec` (costs,
   tick/pip, R-accounting hand check)** — record in SPEC. **Pause for sign-off** on the per-instrument
   calibration and the WTIUSD anchor decision before the heavy runs.
2. Generalize the instrument layer; **prove XAUUSD stays bit-identical** to the committed master table.
3. Build + validate each instrument's data layer (resampling, anchor, quality report) on IS.
4. Run the full 42-config grid per instrument (monitored, resumable); produce per-instrument tables.
5. Build the **replication / meta-analysis + cross-instrument correction** layer; produce the
   replication grid and correlation matrix.
6. Run two-null random-entry per instrument on any IS survivors.
7. **Conditional OOS** per §6.
8. Write `REPORT_MULTI_ASSET.md` + update `README`.

**Definition of done**: full 42×5 grid with per-instrument and cross-instrument-corrected significance,
the replication grid + correlation matrix + correlation-aware meta-analysis, two-null decomposition on
survivors, the conditional OOS resolved, all tests (incl. the bit-identical XAUUSD regression) passing,
and an honest multi-asset write-up.

## 9 · Carried-over non-negotiables (from the core CLAUDE.md — still binding)

No look-ahead / no repaint (truncation-invariance tests) · costs always modelled per instrument ·
determinism (fixed seeds, snapshot config) · config-driven, no magic numbers · IS/OOS wall ·
**observable, resumable runs** (no silent background deaths) · any optimization gated behind a
bit-identical test · English throughout · commit/push only when asked.
