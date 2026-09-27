# Re-run runbook — the study after the 2026-09-27 engine fix

Every published number in this repository was produced before the engine corrections recorded in
[`docs/ADDENDUM_2026-09-27.md`](docs/ADDENDUM_2026-09-27.md) (take-profit swings used before
confirmation; fills resolved after the fill bar's close; stops ignored on the fill bar). This runbook
reproduces the whole study on the corrected engine. It is self-contained: a fresh session on a machine
with the licensed HistData M1 caches can follow it top to bottom.

Nothing in the documents changes until the outputs below exist. Never type a number into a document that
is not in one of the output files listed in §5.

## 1 · Prerequisites

**Code and Python**
- A clean checkout of `main` at or after the fix (`git status` empty, so the `git_commit` recorded on
  every row carries no `-dirty` suffix).
- Python **3.13** (CI uses 3.13; `pyproject.toml` requires `>=3.13,<3.14`).
- From the repo root (PowerShell shown; use `.venv/bin/python` on Linux/macOS):
  ```powershell
  python -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt     # every version pinned with ==
  .venv\Scripts\python -m pip install -e . --no-deps          # makes mtf_smc importable for scripts/
  ```
  All commands below are run from the repo root with that interpreter (written `python`).

**Data — M1 caches in `data_cache/` (repo root, git-ignored; never commit them)**

| Instrument | Cache file | IS bars expected (2015–2022) |
|---|---|---:|
| XAUUSD | `data_cache/XAUUSD_M1_UTC_2015_2025.pkl` (IS + sealed OOS; `load_is` cuts at 2023-01-01) | 2,826,092 |
| EURUSD | `data_cache/EURUSD_M1_UTC_2015_2023.pkl` | 2,976,123 |
| GBPUSD | `data_cache/GBPUSD_M1_UTC_2015_2023.pkl` | 2,976,281 |
| GBPJPY | `data_cache/GBPJPY_M1_UTC_2015_2023.pkl` | 2,975,101 |
| WTIUSD | `data_cache/WTIUSD_M1_UTC_2015_2023.pkl` | 2,601,784 |

The expected counts are the ones in `docs/DATA_QUALITY*.md` ("Bars (M1)").

If a cache is missing:
- EURUSD/GBPUSD/GBPJPY/WTIUSD: put the HistData zips `HISTDATA_COM_XLSX_<SYM>_M1<YEAR>.zip`
  (2015–2023) in one folder, set `SMC_RAW_ZIP_DIR` to it, run `python scripts/ingest_instruments.py`.
- XAUUSD: per-year folders `HISTDATA_COM_XLSX_XAUUSD_M1<YEAR>/` with `SMC_DATA_DIR` pointing at their
  parent (the loader builds the cache, `docs/SPEC.md` §1.5); the 2024–2025 part comes from the
  MetaTrader zips via `python scripts/ingest_oos_data.py "<zip dir>"`.

**Environment variables**: `SMC_RAW_ZIP_DIR`, `SMC_DATA_DIR` (only for rebuilding caches);
`WF_SYMBOLS`, `WF_MAX_WINDOWS` (optional: run the walk-forward in chunks, see §3 step 4).

**Verify the data** (loads each in-sample frame, prints its bar count and range, writes a content hash
per instrument to `output/data_manifest.csv`):
```
python scripts/run_all.py --stages=check
```
The bar counts must equal the table above. If they do not, stop: the data differ from the data behind
the published numbers, and that has to be recorded in the addendum before going on.

## 2 · Regression tests first

```
python -m pytest -q tests/test_lookahead_asof.py tests/test_engine_prefix_invariance.py tests/test_backtester.py tests/test_lookahead_primitives.py tests/test_backtester_integration.py tests/test_instruments_multi.py tests/test_stats_provenance.py
python -m pytest -q
```
- `test_lookahead_asof.py` — take-profit swing confirmation and every as-of lookup, truncation-invariant.
- `test_engine_prefix_invariance.py` — end-to-end prefix invariance (synthetic, all entry/TP modes).
- `test_backtester.py` — fill before close-based invalidation; stop-out on the fill bar.
- `test_backtester_integration.py` — the real-data end-to-end check (runs only with the XAUUSD cache).
- `test_instruments_multi.py` — per-instrument cost/stop-out accounting.

The full suite is 170 tests. Without the caches 9 are skipped; with the XAUUSD cache present those 9
run too. None may fail: do not start the runs on a red suite.

## 3 · Commands, in order

Everything at once (hours; every stage starts from scratch, no earlier row is reused):
```
python scripts/run_all.py
```
Or stage by stage — the same commands `run_all.py` runs:

| # | Command | Produces |
|---|---|---|
| 1 | `python scripts/run_all.py --stages=check` | `output/data_manifest.csv` |
| 2 | `python scripts/run_grid.py fresh --symbol=XAUUSD` | `output/grid/master_table.csv` (+ `master_raw.csv`, `progress.log`) |
|   | `python scripts/run_grid.py fresh --symbol=EURUSD` | `output/grid/EURUSD/master_table.csv` |
|   | `python scripts/run_grid.py fresh --symbol=GBPUSD` | `output/grid/GBPUSD/master_table.csv` |
|   | `python scripts/run_grid.py fresh --symbol=GBPJPY` | `output/grid/GBPJPY/master_table.csv` |
|   | `python scripts/run_grid.py fresh --symbol=WTIUSD` | `output/grid/WTIUSD/master_table.csv` |
| 3 | `python scripts/run_replication.py` | `output/replication/{correlation, replication_grid_ER, replication_grid_N, consistency, meta_random_effects, cross_cells, stopouts}.csv`, `output/replication/provenance.json`, regenerated `docs/REPLICATION.md` |
| 4 | `python scripts/run_legacy_walkforward.py fresh` | `output/legacy_walkforward/walkforward_windows.csv` (24 rows), `progress.txt` |
| 5 | `python scripts/run_legacy_walkforward_report.py` | `output/legacy_walkforward/walkforward_summary.txt` |
| 6 | `python scripts/run_robustness.py 1000` | `output/robustness/random_entry.csv`, `walkforward_<config>.csv`, `progress.log` |
| 7 | `python scripts/make_replication_figure.py` then `python scripts/make_figures.py` | `assets/replication_heatmap.png`; `assets/grid_expectancy_heatmap.png`, `assets/{equity_dd,rhist,mcfan}_cascade_W1_H1_M5_fixed_3R.png` |
| 8 (optional) | `python scripts/run_all.py --stages=stopslip` | high-slippage-on-stops grids (stop slippage ×10) in `output/grid/stopslip_x10/`, `output/grid/{GBPJPY,WTIUSD}/stopslip_x10/` |

Notes:
- **Order.** `run_all.py` runs the stages in the order walk-forward (4–5), random entry (6), optional
  stop-slippage (8), then replication (3) and figures (7) last: steps 3 and 7 rewrite tracked files
  (`docs/REPLICATION.md`, `assets/*.png`), and any row-stamping step run after them stamps its rows
  `-dirty`. Stage by stage, keep that order (added 2026-09-27, addendum §12).
- Grids: a grid killed mid-run resumes if restarted **without** `fresh`, but only onto rows from the
  same engine code, configuration and data span; anything else raises (restart with `fresh`). The gold
  grid was documented at about 30 minutes (`docs/REPORT.md` §10); M1-LTF cascades dominate memory.
- Walk-forward (step 4): to run in chunks, `WF_SYMBOLS=XAUUSD WF_MAX_WINDOWS=4 python scripts/run_legacy_walkforward.py`
  (first chunk with `fresh`, later chunks without); it resumes only onto rows from the same code and
  configuration. The report (step 5) refuses to run unless both instruments cover the same 12 periods.
- Step 6 (L3) reads the step-2 XAUUSD master table and refuses one produced by other engine code.
- Step 8 is the high-slippage-on-stops sensitivity pre-registered in `docs/SPEC.md` §6.5/§8 and
  `docs/SPEC_multi_instrument.md` §6. It was never run; no document may claim robustness to it unless it is.
- **Not part of the re-run:** `scripts/run_oos.py` (the XAUUSD 2023–2025 OOS was spent once, in the
  gold study; reopening it is a separate, deliberate decision), `scripts/verify_xauusd_regression.py`
  (the fix changes the XAUUSD master table on purpose), and the fidelity scripts
  (`scripts/compare_old_engine.py`, `scripts/run_legacy_fidelity.py`, `scripts/compare_new_vs_old.py`;
  they need the external old repository).

## 4 · Sanity checks on the outputs

- Every row of every master table, walk-forward window and random-entry row: one `git_commit` (no
  `-dirty`) and one `code_hash`; `run_replication.py` already refuses master tables from different
  engine code.
- 42 rows per master table; 24 walk-forward windows (12 per instrument, same `oos_start` set).
- `output/replication/stopouts.csv`: each instrument's per-config median full stop-out R. The synthetic
  check (`python scripts/verify_instruments.py`) books −1.02 to −1.04 R on a clean −1R stop; real stops
  vary, but a median far below −1 R on one instrument points to a mis-scaled cost constant.
- `python -m pytest -q` still green.

## 5 · Where each output goes

Update these sections from the named files only. The published figure each one replaces is listed so
nothing is missed (search the repo for the old value before committing).

| Output | Numbers it gives | Update |
|---|---|---|
| `output/grid/master_table.csv` (XAUUSD) | BH survivors 0/42, max DSR 0.00, best raw Sharpe +0.43, positive-estimate count (4/42), `cascade_W1_H4_M15_HTF_level` +2.0 R / N 17 / CI [−0.63, +5.27], M1-cascade E[R] ≈ −0.5 | `docs/REPORT.md` §5; `README.md` "The honest finding" |
| `output/grid/<SYM>/master_table.csv` | within-instrument BH 0/42 per instrument, max DSR | `docs/REPORT_MULTI_ASSET.md` §5 "Within-instrument"; `README.md` "The honest finding" |
| `docs/REPLICATION.md` (regenerated) and `output/replication/{replication_grid_ER, consistency, meta_random_effects, cross_cells}.csv` | 0/210 cross-instrument BH-FDR; 0/42 positive-and-significant; per-cell E[R] incl. +2.00 R XAUUSD / +1.05 R GBPJPY cells and their rows; best pooled −0.000 R and the pooled table; M1-cascade row (−0.53, −0.62, −0.59, −0.65, −0.47 R) | `README.md` (TL;DR, mermaid L2, "The honest finding", "Three lenses"); `docs/REPORT_MULTI_ASSET.md` abstract, §3.4, §5, §6; `docs/MERGE_REPORT.md` lens table + L2; `DESIGN_DECISIONS.md` first, WTI and OOS sections; `results/headline.json` |
| `output/replication/correlation.csv` | correlation matrix, N_eff 3.45 (should be unchanged: price data, no engine) | only if it differs: `docs/REPORT_MULTI_ASSET.md` §4, `DESIGN_DECISIONS.md` BH section |
| `output/replication/stopouts.csv` | real-trade stop-out medians per instrument | add beside the synthetic figures in `docs/REPORT_MULTI_ASSET.md` §3.3 and `DESIGN_DECISIONS.md` (−25 R section) |
| `assets/replication_heatmap.png` | heatmap | shown in `README.md`, `docs/REPORT_MULTI_ASSET.md` |
| `output/legacy_walkforward/walkforward_summary.txt` (+ `walkforward_windows.csv`) | pooled OOS E[R] (−0.339 R), window-block CI ([−0.436, −0.223]), iid CI ([−0.446, −0.223]), per-instrument and per-regime E[R], windows negative (21/24), **sign test on 12 calendar periods (new)**, IS→OOS gap (+0.387), N (478) | `README.md` (TL;DR, mermaid L1, "Three lenses"); `docs/MERGE_REPORT.md` lens table, L1 result block, robustness paragraph, old→new, conclusion; `DESIGN_DECISIONS.md` L1 scope + "What would it take"; `results/headline.json` |
| `output/robustness/random_entry.csv` (+ `progress.log`) | strategy vs null E[R] for both nulls, null 5th/95th percentiles, the strategy's percentile in each null (never published before); previously +0.142 R / +0.354 R over the bias-matched null | `docs/REPORT.md` §6 random-entry paragraph; `docs/MERGE_REPORT.md` lens table + L3; `README.md` L3 bullet + mermaid L3; `DESIGN_DECISIONS.md` lenses section |
| `output/robustness/walkforward_<config>.csv`, `progress.log` | Monte-Carlo drawdown, yearly/regime E[R] of the survivors | `docs/REPORT.md` §6 Monte-Carlo and walk-forward/regime paragraphs |
| `assets/grid_expectancy_heatmap.png`, `assets/*_cascade_W1_H1_M5_fixed_3R.png` | gold figures | shown in `docs/REPORT.md` §5–6 |
| `output/data_manifest.csv` | in-sample content hashes | the re-run section of the addendum |
| optional `output/grid/**/stopslip_x10/master_table.csv` | high-slippage-on-stops sensitivity | only if run: `docs/REPORT.md` §8 may then state the result, with its numbers |

## 6 · After the numbers exist

1. **Addendum.** Append `## 11 · Re-run results (<date>)` to `docs/ADDENDUM_2026-09-27.md`: the
   `git_commit` / `code_hash` of the run, the data-manifest hashes, a table of every published number
   old → new (file and section), the walk-forward sign test on the 12 periods, the L3 percentiles, the
   real-trade stop-out medians, and the verdict under the pre-registered rule of
   `docs/SPEC_multi_instrument.md` §7. If a configuration now replicates, that rule calls for a one-time
   OOS evaluation — a separate, deliberate step that is not in `run_all.py`.
2. **Documents.** Replace the old figures in every place listed in §5 (search for each old value). Drop
   the "pre-fix / pending re-run" qualifiers where a figure was replaced; turn each dated correction note
   into a one-line pointer to §11 of the addendum. `docs/REPLICATION.md` is regenerated by step 3 — do not
   hand-edit it.
3. **`results/headline.json`.** Set `verdict_detail` (drop "re-run pending" if the verdict is confirmed),
   update each stat's `display`/`value`, point the walk-forward stats at
   `output/legacy_walkforward/walkforward_summary.txt` or `walkforward_windows.csv` with provenance
   `reproduced`, and extend `tests/test_headline.py` so it recomputes them from the CSV with the repo's
   own functions (`mtf_smc.robustness.stats`, `mtf_smc.robustness.walkforward.period_sign_test`).
   Set `source_commit` to the commit that contains the CSVs.
4. **Commit the derived statistics.** `git add output assets docs README.md DESIGN_DECISIONS.md results tests`
   — `.gitignore` admits only the files listed there (master tables, replication tables and
   `provenance.json`, walk-forward windows and summary, `random_entry.csv`, `data_manifest.csv`); check
   `git status --short output/` shows nothing else. Never commit `data_cache/`, `*.pkl`, raw HistData,
   `master_raw.csv`, per-trade logs or progress logs.
5. `python -m pytest -q` green, then commit with a message that names the addendum section.
