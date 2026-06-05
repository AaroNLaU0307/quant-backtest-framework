# CLAUDE.md — repo conventions (MTF-SMC multi-instrument backtest)

Concise working agreement for this repo. The **authoritative strategy/methodology definitions live in
[`docs/SPEC.md`](docs/SPEC.md)** — read it before changing detection, fills, or stats. The original
mandate is [`docs/PROJECT_BRIEF.md`](docs/PROJECT_BRIEF.md); the multi-instrument replication is
specified in [`docs/SPEC_multi_instrument.md`](docs/SPEC_multi_instrument.md) and
[`docs/PROJECT_BRIEF_multi_instrument.md`](docs/PROJECT_BRIEF_multi_instrument.md).

## What this project is
A falsification-oriented, research-grade backtest of a multi-timeframe SMC price-action strategy —
first on XAUUSD, then replicated across EURUSD/GBPUSD/GBPJPY/WTIUSD. **We do not tune toward
profitability.** A clean negative result is a valid outcome. Favor
correctness, statistical honesty, and reproducibility over flattering numbers.

## Non-negotiables (a change that violates these is wrong, however good the equity curve looks)
1. **No look-ahead / no repaint.** At decision time `t`, only bars closed `≤ t` on every timeframe are
   visible. All detection uses closed candles. Every fragile signal gets a **truncation-invariance
   test** (recompute on prefix `[0..i]` ⇒ identical history). See `docs/SPEC.md` §6–7.
2. **Costs always modelled** — spread, commission, slippage (and swap unless disabled) on entries,
   exits, and scale-outs. Raw OHLC has no spread; the modelling assumption is disclosed in reports.
3. **Determinism** — fixed RNG seeds; identical input + config ⇒ identical output. Each run writes a
   config + seed snapshot.
4. **Config-driven, no magic numbers** — every parameter from `docs/SPEC.md` lives in the typed config
   tree / YAML, never hard-coded inline.
5. **IS/OOS wall** — all development uses IS (2015–2022). The locked OOS (2023–2025) is touched once,
   at the end, for finalists only. Do not peek.

## Stack & layout
- Python 3.11+ (developed on 3.13), `pandas`/`numpy`, `pytest`, `matplotlib`. Pin in
  `requirements.txt` (and/or `pyproject.toml`).
- Package layout per `docs/SPEC.md` §9: `data/ indicators/ smc/ strategy/ engine/ risk/ metrics/
  robustness/ reporting/ config/ tests/ notebooks/ docs/`.
- **English** throughout — docs, comments, identifiers (this is a public portfolio repo).
- Type hints + docstrings on public functions/classes. Single responsibility per module.

## Testing
- `python -m pytest -q` must pass before anything is called done.
- Always test the fragile pieces: FVG detection, swing/BOS/CHoCH detection, no-look-ahead alignment,
  intrabar fill ordering (incl. same-bar SL/TP tie-break), R/BE/scale-out accounting.
- Prefer constructed/synthetic bar sequences with asserted outcomes over data-dependent tests.

## Data
- **Never commit licensed data.** `data_cache/`, raw HistData folders, and large artifacts are
  git-ignored. Ship the loader, the schema, and a tiny synthetic sample only.
- Raw source = HistData.com per-year M1 `.xlsx` (no header; `datetime,open,high,low,close,volume=0`;
  **fixed EST UTC−5, no DST** → converted to UTC). Point `SMC_DATA_DIR` at the folder of per-year
  `HISTDATA_COM_XLSX_XAUUSD_M1<YEAR>/` dirs. See `docs/SPEC.md` §1.5.

## Reuse
Verified pieces are ported from `../Algorithmic Trading System - V2` (loader EST→UTC, `shift(1)` MTF
alignment + `closed_asof`, swing/FVG/CHoCH primitives, `InstrumentSpec`, `fib`) **with fresh tests**.
Re-derive nothing silently; if you adapt ported logic, note what changed and re-test it.

## Workflow
- This is `win32` / PowerShell; use the `.venv` interpreter for Python.
- Not a git repo yet — initialize when scaffolding code (after SPEC sign-off); keep a clean, legible
  commit history. Commit/push only when asked.
- Run order and definition of done: `docs/SPEC.md` §10.
