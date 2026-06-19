# Multi-Timeframe SMC Price-Action — A Multi-Instrument Falsification Study

An institutional-grade, **falsification-oriented** backtest asking one question honestly: does a
top-down, multi-timeframe **Smart-Money-Concepts (SMC)** price-action strategy carry a *statistically
real* edge that **replicates across independent instruments**? It pairs a paranoid, zero-look-ahead
event-driven engine with the full inference toolbox — per-instrument cost calibration, Benjamini–Hochberg
FDR + Deflated Sharpe, cross-instrument correlation + correlation-aware random-effects meta-analysis, and
a once-only locked out-of-sample gate — and the discipline to trust a negative result.

`Python` · `pandas/numpy/scipy` · event-driven backtester · intrabar M1 fills · **5 instruments × 42
configs = 210 trials** · BH-FDR/DSR · correlation-aware meta-analysis · 141 unit tests

## The honest finding
**No replicable edge.** Across **42 pre-registered configurations** on five instruments (XAUUSD, EURUSD,
GBPUSD, GBPJPY, WTIUSD), IS 2015–2022, with realistic per-instrument costs and proven no-look-ahead:

- **0 / 42** configurations survive Benjamini–Hochberg FDR on **any** instrument; **0 / 42** are
  positive-and-significant on even one instrument, **0 / 42** on two or more.
- **0 / 210** (config × instrument) cells survive the cross-instrument BH-FDR.
- The best **correlation-aware** random-effects pooled expectancy is **−0.000 R** (one-sided p ≥ 0.50).
- The eye-catching cells — **+2.0 R on gold**, **+1.0 R on GBPJPY** — are each positive on a *single*
  instrument and significant on **none**: small-sample noise that regresses to zero across assets.

By the pre-registered rule, nothing earned an out-of-sample look, so **the locked OOS stays sealed.**

![Replication heatmap](assets/replication_heatmap.png)

> A "+2 R on gold, it works!" headline is exactly what this study is built to *not* fall for. A negative
> that **replicates as a non-result across FX majors, an FX cross, a metal, and crude — after correction**
> is a *stronger, more credible* falsification than any single-instrument result.

## Three lenses, one verdict
This repo now unifies a previously separate single-instrument **walk-forward** study onto the same engine,
so the strategy is falsified three independent, non-overlapping ways — and all three agree:

- **Walk-forward OOS** — optimize the legacy detection thresholds on a fixed D1→H1→M5, roll IS18/OOS6:
  pooled **E[R] = −0.339 R**, 95% CI **[−0.45, −0.22]**, **21/24 windows negative** (sign-test p = 0.0001).
  This reproduces the old published strategy's **−0.27 R** on a more rigorous engine (on the sealed-wall IS
  span 2015–2022; the old rolled into 2023) — same verdict, sharper.
- **Replication grid** (this study) — **0 / 210** config×instrument cells survive cross-instrument BH-FDR.
- **Random-entry nulls** — the structured entries are statistically indistinguishable from random.

The full three-lens write-up — including the behavioural **fidelity** proof that the reproduced strategy
*is* the old one (86 % entry overlap, matched-pair R 16/18) — is in
**[`docs/MERGE_REPORT.md`](docs/MERGE_REPORT.md)**.

## What's on display (engineering & rigor)
- **Proven** zero look-ahead — truncation-invariance tests on every detector + an end-to-end engine test;
  MTF data right-aligned to the DST-aware NY-close.
- **Per-instrument cost calibration as the #1 correctness item** — each instrument's own tick/pip/spread/
  commission/swap; R-accounting hand-verified by an independent fill-based recompute. A **gold-scaled
  slippage bug** (impossible −25 R on EURUSD) was **caught by monitoring, not a passing test**, then fixed
  and locked behind a strengthened stop-out check and a **systematic absolute-price-constant audit** of
  the whole signal/fill/cost path.
- **Bit-identical reuse** — the XAUUSD master table is reproduced to the digit (identical MD5, `max |Δ| =
  0`) after every change, proving the multi-instrument generalization never perturbed the verified engine.
- **Correlation-aware statistics** — a cross-instrument correlation matrix and an **effective number of
  independent instruments (3.45 / 5)**; pooled significance is deflated accordingly. Five instruments are
  never treated as five independent votes.

## Read more
- **[`docs/MERGE_REPORT.md`](docs/MERGE_REPORT.md)** — the unified **three-lens** report (walk-forward
  −0.339 R, replication 0/210, random-entry) + the legacy-strategy fidelity evidence and what the merge did.
- **[`docs/REPORT_MULTI_ASSET.md`](docs/REPORT_MULTI_ASSET.md)** — the full multi-instrument write-up
  (design, methods, the bug + audit, correlation, results, conclusion).
- [`docs/REPLICATION.md`](docs/REPLICATION.md) — the replication grid + meta-analysis tables.
- [`docs/SPEC_multi_instrument.md`](docs/SPEC_multi_instrument.md) — per-instrument calibration, anchor,
  and methodology. [`docs/SPEC.md`](docs/SPEC.md) — the core strategy/engine spec.
- [`docs/REPORT.md`](docs/REPORT.md) — the precursor single-instrument (gold) study;
  `docs/DATA_QUALITY_<SYM>.md` — per-instrument integrity, gaps, and bad-print scans.

## Reproduce
```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest -q                            # 141 tests
.venv\Scripts\python scripts\ingest_instruments.py           # build per-instrument M1 caches
.venv\Scripts\python scripts\run_grid.py fresh --symbol=EURUSD   # L2: 42-config IS grid (per instrument)
.venv\Scripts\python scripts\run_replication.py              # L2: replication grid + correlation + meta
.venv\Scripts\python scripts\make_replication_figure.py      # the heatmap above
.venv\Scripts\python scripts\run_legacy_walkforward.py       # L1: walk-forward (legacy_smc; chunked, resumable)
.venv\Scripts\python scripts\run_legacy_walkforward_report.py   # L1: pooled OOS -0.339 R + CI + per-window
```
Data is **not committed** (size + HistData licence). See [`docs/SPEC.md`](docs/SPEC.md) §1.5 and
`docs/SPEC_multi_instrument.md` §1 for acquisition; a tiny synthetic sample drives the no-download tests.

## Part of a research arc
A broader falsification effort spans **two paradigms in separate repositories**, reaching the same verdict
from different directions. **This repository is the MTF-SMC study** — it falsifies the approach three
disjoint ways (the walk-forward, multi-instrument replication, and random-entry lenses above; the old
single-instrument *subjective*-SMC strategy is reproduced here as **L1**, an internal lens, not a separate
study). A **separate** repository tackles an **objective Donchian breakout** and finds no confirmable edge
under Monte-Carlo. The throughline across both: single-instrument trend/structure alpha is too thin to
confirm and does not replicate across markets — which is *why* professional trend-following is multi-asset
and diversified.

## Limitations & disclaimer
Modelled (not historical) spread/slippage; SMC discretion operationalized into one specific rule-set;
representative retail cost placeholders; WTI's thin 2017 / short 2023; deep cascades are trade-starved by
construction. **Research and educational only — not investment advice.** The strategy was found to have no
replicable edge and must not be traded.

## License
MIT (see [`LICENSE`](LICENSE)).
