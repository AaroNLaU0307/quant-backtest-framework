# Multi-Timeframe SMC Price-Action Strategy on XAUUSD — A Falsification Study

> **Status: work in progress.** This README is a stub; the honest findings, headline statistics, and
> reproduction instructions are filled in once the grid + robustness + locked-OOS runs complete
> (see [`docs/SPEC.md`](docs/SPEC.md) §10). The conclusion is **not pre-decided** — a clean negative
> result is a valid outcome.

## Research question
Does a top-down, **multi-timeframe Smart-Money-Concepts (SMC)** price-action strategy carry a
**statistically real edge** on gold (XAUUSD), once tested honestly — across a pre-registered grid of
structural variants, with realistic costs, zero look-ahead, multiple-testing correction, a
random-entry benchmark, and a locked out-of-sample period?

## Approach (summary)
- **Data:** XAUUSD M1 (HistData, EST→UTC), resampled to W1/D1/H4/H1/M15/M5/M1. Development on
  **2015–2022**; **2023–2025 locked** out-of-sample, touched once.
- **Strategy:** HTF point-of-interest + EMA bias → MTF BOS/CHoCH with FVG → discount/premium pullback
  → LTF trigger (cascade), plus a set-and-forget direct-POI variant. Three take-profit modes.
- **Engine:** event-driven, **intrabar M1 fill resolution**, full transaction costs, **proven
  no-look-ahead** (truncation-invariance tests).
- **Inference:** bootstrap CIs, Monte-Carlo *risk* (reshuffle + bootstrap), a **random-entry edge
  benchmark**, Benjamini–Hochberg FDR + Deflated/Probabilistic Sharpe over the trial count, and
  walk-forward — then a single locked-OOS evaluation.

This is the third in a research arc: V1 (subjective SMC + walk-forward) and V2 (objective breakout +
Monte-Carlo) each found **no confirmable single-instrument edge** on XAUUSD. V3 re-tests the MTF-SMC
cascade with the full institutional apparatus those projects lacked.

## Reproduce
```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest -q
```
Data is **not committed** (size + HistData license). See [`docs/SPEC.md`](docs/SPEC.md) §1.5 for
acquisition instructions; a tiny synthetic sample drives the no-download smoke test.

## Documents
- [`docs/SPEC.md`](docs/SPEC.md) — authoritative definitions, decisions, and methodology.
- [`docs/PROJECT_BRIEF.md`](docs/PROJECT_BRIEF.md) — the original mandate.
- [`CLAUDE.md`](CLAUDE.md) — repo conventions and non-negotiables.
- `docs/REPORT.md` — academic write-up *(generated in step 7)*.

## Disclaimer
Research and educational project, **not investment advice**. Backtested results — including negative
ones — do not guarantee future behaviour.

## License
MIT (see `LICENSE`).
