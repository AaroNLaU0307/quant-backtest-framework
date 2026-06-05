# SPEC — Multi-Instrument Replication (extends `SPEC.md`)

**Status:** APPROVED — per-instrument calibration (§3) and the WTIUSD anchor (§4) are signed off. The
core strategy/engine/stats (`SPEC.md`) are reused unchanged; this records **only** the multi-instrument
additions and decisions. Next: generalize the instrument layer and prove the XAUUSD result stays
**bit-identical** to the committed single-instrument master table.

---

## 1 · Data — confirmed (read directly from the source zips)
Five instruments under `…/trade log/` (HistData.com). **All confirmed `.xlsx`, 6 columns
`datetime, open, high, low, close, volume(=0)`, no header, fixed-EST source (UTC−5, no DST)** — the
same feed family as XAUUSD's XLSX, so the verified loader applies unchanged (localize EST→UTC).

| Instrument | Class | Years | Decimals | Close range (sample) | Notes |
|---|---|---|---|---|---|
| XAUUSD | metal | 2015–2025 | 2 | — | existing; OOS 2023–2025 sealed |
| EURUSD | FX major | 2015–2023 | 5 | 1.046–1.210 | pip 0.0001 |
| GBPUSD | FX major | 2015–2023 | 5 | 1.457–1.593 | pip 0.0001 |
| GBPJPY | FX cross | 2015–2023 | 3 | 174.9–195.8 | **JPY-quoted, pip 0.01** |
| WTIUSD | crude CFD | 2015–2023 | 2 | 6.50–66 | session = FX-like (below) |

- **WTIUSD April-2020 inspected:** 2020 close range $6.50–$65.58; April low **$6.495** (the genuine
  spot floor) with **zero negative/garbage prints** — the negative-WTI-*futures* event did not hit
  this spot CFD. April 2020 is a real high-volatility regime, not bad data. (A full per-instrument
  data-quality report — gaps, integrity, anchor verification, rollover scan — is produced in the
  data-layer step.)

## 2 · IS/OOS wall (preserved per instrument)
Development uses **IS = 2015–2022** (hard-sliced `< 2023-01-01`) for every instrument. New instruments'
**2023 = OOS** (verify per-instrument completeness; flag if thin). XAUUSD OOS stays 2023–2025. OOS is
touched only under the §8 conditional rule.

## 3 · Per-instrument `InstrumentSpec` calibration  ✅ SIGNED OFF
Each instrument has its **own** spec (`mtf_smc/risk/instrument.py`); **none inherit XAUUSD's numbers**.
Money math derives from `tick_value/tick_size`. Values are broker-typical retail placeholders, all
configurable and disclosed in reports.

| Instr | mpu ($/pt/lot) | pip value | tick / contract | commission/side | spread (price) | swap L / S | quote |
|---|---:|---:|---|---:|---:|---:|---|
| XAUUSD | 100 | $10 | 0.01 / 100 oz | $3.50 | 0.20 | −6 / −3 | USD |
| EURUSD | 100,000 | $10 | 0.00001 / 100k | $3.50 | 0.00006 (0.6 pip) | −0.5 / −0.1 | USD |
| GBPUSD | 100,000 | $10 | 0.00001 / 100k | $3.50 | 0.00009 (0.9 pip) | −0.7 / −0.2 | USD |
| GBPJPY | **833** | $8.33 | 0.001 / 100k | $3.50 | 0.015 (1.5 pip) | +1.0 / −3.5 | JPY |
| WTIUSD | 1,000 | $10 | 0.01 / 1,000 bbl | **$0** (spread-only) | 0.04 (4¢) | −3.0 / −1.0 | USD |

**Ratified assumptions:**
- **GBPJPY money-per-price-unit (833)** assumes a representative **USDJPY ≈ 120** ($1-yen move ≈
  100k JPY ÷ 120 ≈ $833/lot). USDJPY ranged ~100–150 over 2015–2023, so this is *representative, not
  tick-perfect* — acceptable because **R is invariant to mpu** (it cancels between win and stop); only
  the **cost-to-R ratio** carries a mild mpu dependence. Flagged in the report.
- **WTIUSD** = 1 lot ≡ **1,000 barrels** ($1 move = $1,000/lot), **spread-only** (no commission), as
  typical for retail crude CFDs.
- Commission $3.50/side ($7 round-turn) on FX/metal; spreads are mid-of-range retail-ECN values.

**Verified:** `scripts/verify_instruments.py` + `tests/test_instruments_multi.py` run one +3R trade per
instrument through the real FSM — clean +3R is exactly 3R, and the **independent fill-based recompute
matches the FSM net/R for every instrument** (no double-charge; JPY/crude tick math reconciles). A 3R
win nets ≈ +2.97–2.98R after costs on majors; cost-to-R rises with tighter stops (relevant to the
M1-cascade cost-dependence sub-question — §3 of the brief).

## 4 · Session anchors per instrument  ✅ SIGNED OFF (WTIUSD)
- **FX/metals (XAUUSD, EURUSD, GBPUSD, GBPJPY):** reuse the existing **`ny_close`** anchor — D1 opens
  17:00 America/New_York (DST-aware), W1 opens Sunday 17:00 NY. These share the FX/metals trading-day
  convention. Intraday stays UTC-binned.
- **WTIUSD — `ny_close`, justified (not blindly inherited):** the HistData WTIUSD CFD trades the
  **same Sunday-18:00-ET → Friday-17:00-ET session** as FX/metals, with a ~17:00 ET daily break
  (verified: first bar Sun 18:00 EST, last Fri 16:58). So the 17:00-NY daily/weekly boundary **matches
  this feed's actual session**. The alternative — the CME WTI **14:30 ET settlement** — would impose a
  boundary the continuous spot CFD does not observe. **Decision: `ny_close` for WTIUSD too,
  config-switchable per instrument** (`utc` / a future `cme_settlement` available).

## 5 · Grid — full 42 on every instrument
Run the **complete 42-config grid on each of the 5 instruments** (winners and losers; no pre-filtering
by gold performance — that would reintroduce selection bias). Reuse the optimized, **observable +
resumable** runner (per-config flushed `progress.log`, one context in memory at a time, incremental
CSV + resume). Per-instrument master table with significance computed **within** that instrument.
**Regression guard:** after generalizing the instrument layer, the XAUUSD master table must stay
**bit-identical** to the committed single-instrument result (MD5 / <1e-9) — proven before any
multi-instrument run.

## 6 · Replication & meta-analysis (the new analytical core)
- **Replication grid:** config × instrument table of E[R] (+ N, CI, within-instrument significance).
- **Consistency count:** per config, # instruments where it is positive, and positive *and*
  individually significant. Consistency across **independent** instruments is the evidence — not a
  pooled mean.
- **Cross-instrument correlation matrix** (returns / trade-overlap) + an **effective number of
  independent instruments** (EURUSD/GBPUSD/GBPJPY are USD/GBP-correlated; WTIUSD more independent;
  XAUUSD USD-linked → effective N well below 5). **Mandatory before any pooling.**
- **Correlation-aware pooling only** (random-effects meta-analysis, or block-bootstrap resampling
  instruments as correlated blocks, or the conservative consistency count). **Never** a naive pooled
  t-test treating 5×N trades as 5N independent observations.
- **Cross-(config × instrument) BH-FDR + DSR** over the full trial set, with the correct trial count;
  state the corrected threshold.
- **Two-null random-entry per instrument** (unconstrained + bias-matched; per-trade E[R] / per-trade
  Sharpe; holding-matched cap-with-management) on any in-sample survivors. If any survivor exists,
  additionally run a **high-spread / high-slippage sensitivity on GBPJPY and WTIUSD** specifically
  (they gap harder on news than the majors).

## 7 · Pre-registered interpretation — LOCKED before the runs
- **"Edge" = consistently positive AND individually significant across multiple *independent*
  instruments, surviving the cross-instrument correction.** A single-instrument win is **not** edge.
- A config positive on XAUUSD but ~0/negative elsewhere = **confirmed noise** (the expected outcome).
- **Nothing replicating = a stronger multi-asset falsification** than the single-instrument result —
  the valuable outcome.
- **Conditional OOS one-shot:** *only if* a config survives IS multi-instrument replication +
  correction, evaluate it **once** on OOS (XAUUSD 2023–2025; new instruments' 2023). Otherwise OOS is
  not touched. Report honestly whatever it shows.

## 8 · Reporting
Per-instrument master tables + a master replication grid + cross-instrument correlation matrix +
correlation-aware meta-analysis + the conditional OOS. The write-up
(`docs/REPORT_MULTI_ASSET.md`) is titled **"Multi-Instrument Replication of an MTF-SMC Strategy across
FX, Metals and Crude"**, with one honest paragraph of prior-work lineage (the earlier single-instrument
falsifications that motivated this replication test) — no version labels in the project's structure.
