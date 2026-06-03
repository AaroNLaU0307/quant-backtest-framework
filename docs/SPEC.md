# SPEC — Multi-Timeframe SMC Strategy Backtest on XAUUSD (V3)

**Status:** DRAFT — awaiting confirmation (Process §8.1 of the brief).
**Authority:** This document governs implementation. Where it differs from
[`PROJECT_BRIEF.md`](PROJECT_BRIEF.md), the difference is intentional and the reason is recorded here.
**Audience:** quant-research reviewers. English throughout (docs, comments, identifiers).

Every definition below is meant to be **concrete and unit-testable**. The validity of the whole
study rests on these definitions, so each `🔧 DECISION` block states the default chosen and, where
the SMC literature is genuinely ambiguous, the alternative left as an ablation knob. `❓ CONFIRM`
flags points I specifically want your sign-off on before heavy coding.

---

## 0 · Mission, stance, and lineage

Build a reproducible, **falsification-oriented** backtest that asks one question honestly: *does a
top-down, multi-timeframe SMC price-action strategy carry a statistically real edge on XAUUSD?* A
clean negative result is a valid, valuable outcome. We never tune toward profitability.

**Lineage (this is effectively V3 of a research arc):**

| | Paradigm | Verdict tool | Result |
|---|---|---|---|
| V1 (separate repo) | Subjective SMC price-action | Walk-forward OOS | No robust edge (OOS E[R] negative) |
| V2 (`…/Algorithmic Trading System - V2`) | Objective Donchian breakout | Monte-Carlo + controlled experiments | No confirmable edge (all CIs cross 0) |
| **V3 (this project)** | **Structured MTF-SMC cascade grid** | **Grid + BH-FDR/DSR/PSR + random-entry falsification + locked OOS** | *To be determined — honestly* |

V3's contribution over V1/V2: a **pre-registered grid** of structural variants tested with
**multiple-testing correction**, a **random-entry benchmark** as the central edge test, **intrabar
M1 fill resolution**, and a **locked 2023–2025 OOS** touched exactly once.

**Hygiene lessons carried forward from the prior engine (these were real bugs that manufactured
phantom profit — we guard against them by design):**
- A **take-profit look-ahead**: a "nearest-liquidity" TP recomputed every bar drifted to the wrong
  side of entry and booked losses as TP wins. → The `HTF_level` TP here is **fixed at entry from
  already-confirmed structure** (§6.3, §7.4).
- A **circuit-breaker with no reset** silently truncated multi-year runs. → No silent equity guards
  in V3; any halt logic is explicit, tested, and logged (§6.4).
- **Point estimates lie / returns are tail-driven.** → Every headline carries a bootstrap CI and a
  **drop-1 (jackknife) sensitivity** (§8).

---

## 1 · Data

### 1.1 Confirmed schema & timezone (verified by loading the cached pickle)
- **Instrument:** XAUUSD (gold), M1 OHLC. No reliable volume (HistData volume ≡ 0; dropped).
- **Available history on disk:** `2015-01-01 23:01` → `2023-12-29 21:57` **UTC**, 3,134,844 M1 bars,
  columns `open, high, low, close` as `float64`, tz-aware UTC `DatetimeIndex`.
- **Source & timezone provenance:** HistData.com per-year M1 `.xlsx` (no header, 6 cols:
  `datetime, open, high, low, close, volume=0`). HistData timestamps are **fixed EST (UTC−5, no
  DST)**; the verified loader localizes to fixed UTC−5 then converts to **UTC**. All internal logic
  is UTC. The raw `.xlsx` source folders are **not currently on disk** — only the converted UTC
  pickles remain (see §1.5 re-acquisition).
- **Bar timestamp convention:** index = **bar OPEN (start) time**. A bar labelled `T` on timeframe
  `TF` spans `[T, T + TF)` and is **closed/known only at `T + TF`**. This drives no-look-ahead (§7.1).

### 1.2 Timeframes
Resample M1 → **W1, D1, H4, H1, M15, M5, M1** with `label='left', closed='left'`, agg
`open=first, high=max, low=min, close=last`; **no interpolation, no ffill** of price; empty buckets
(weekends/holidays) dropped so the index stays monotonic. (Ported from the verified V2 loader.)
- 🔧 **DECISION — D1/W1 session anchor (implemented & verified):** default **`ny_close`**, the
  gold/FX convention. The **daily** candle opens **17:00 America/New_York**; the **weekly** candle
  opens **Sunday 17:00 NY**. The boundary is **DST-aware** (17:00 NY = 21:00 UTC in summer/EDT,
  22:00 UTC in winter/EST), implemented in `mtf_smc/sessions.py`. This is deliberately *distinct*
  from HistData's fixed-EST **source** timestamps (handled once in the loader, no DST) — only the
  session **anchor** observes DST. Verified on IS data: first W1 bar `2014-12-28 22:00Z` (Sun 17:00
  EST), first D1 bar `2015-01-01 22:00Z`. **Intraday (H4/H1/M15/M5) stays UTC-binned** and
  anchor-independent (session-aligning H4 is a possible future option). The anchor is
  **config-switchable to `utc`** (UTC calendar day / UTC Monday week), documented and unit-tested
  (incl. a DST-transition week). `closed_asof` uses each bar's actual next-bar-start as its close,
  so the no-look-ahead as-of slice is exact even across DST-shortened/-lengthened sessions.

### 1.3 In-sample / out-of-sample split (LOCKED)
- **In-sample / development (IS):** `2015-01-01 → 2022-12-31`. *All* grid search, ablation,
  walk-forward, Monte-Carlo, and parameter choices use **only** IS.
- **Locked OOS:** `2023-01-01 → 2025-12-31`. Touched **exactly once**, at the very end, for the
  finalist config(s) only. Defined **by date**, so it auto-extends as 2024–2025 data is added.
- Per your decision, you will **add HistData M1 for 2024–2025** (and ideally re-pull 2023). Until
  then I build and run everything on IS = 2015–2022 and keep OOS sealed. The IS loader
  **hard-slices to `≤ 2022-12-31`** so 2023+ rows cannot physically enter development — enforced
  structurally (unit-tested), not by discipline. **Currently OOS would be
  2023 only**, and 2023 is ~12% thin (308,752 bars vs ~353k/yr) — a caveat I will state wherever
  OOS appears. With 2024–2025 added, OOS becomes the full intended 3-year window.

### 1.4 Data-quality report (built in §Process step 2)
Detect and document, without silently patching: intrabar gaps (>5 min), session gaps (>1 h),
weekend/holiday gaps (>24 h), the max gap, per-year bar counts (flagging the 2023 shortfall),
duplicate/zero/`high<low` integrity violations, and any visible price discontinuities (e.g.,
rollover-like jumps). Output: `data/quality_report.{md,csv}` + a bars-per-year/gap plot.

### 1.5 Data acquisition instructions (for 2024–2025, and reproducibility)
- Download per-year XLSX from HistData.com: "XAUUSD" → M1 → each year 2024, 2025 (and 2023 re-pull).
- Extract so the tree contains `HISTDATA_COM_XLSX_XAUUSD_M1<YEAR>/DAT_XLSX_XAUUSD_M1_<YEAR>.xlsx`.
- Point `SMC_DATA_DIR` (env var) at the folder holding those per-year directories; the loader
  converts EST→UTC, dedupes, caches to `data_cache/XAUUSD_M1_UTC_<first>_<last>.pkl`.
- **Licensed data is never committed.** The repo ships the loader, this schema, and a **tiny
  synthetic sample** for smoke tests. A `run_demo` on synthetic data needs no download.
- 🔧 **DECISION (confirmed):** seed V3's `data_cache/` by copying the V2
  `XAUUSD_M1_UTC_2015_2023.pkl` so IS work starts immediately. **The IS loader hard-slices the series
  to `≤ 2022-12-31`** before any development use, so 2023 OOS rows cannot leak in — a structural
  guarantee, unit-tested, not reliant on discipline. The full (unsliced) series loads only in the
  final locked-OOS harness.

---

## 2 · SMC primitives — precise, testable definitions

Notation: bars indexed by `i` in close-time order on a given timeframe; `O/H/L/C[i]`. "Confirmed
as of `i`" means usable in a decision taken at the close of bar `i` (no future bars referenced).

### 2.1 Swing high / low (fractal)
- Bar `i` is a **swing high** iff `H[i]` is the **unique** maximum of `H[i-k … i+k]`; **swing low**
  symmetrically on `L`. `k = swing_lookback`.
- A swing is **confirmed only at bar `i+k`** (needs `k` closed bars to its right). Any logic
  referencing a swing must satisfy `swing.index + k ≤ current_i`. (Ported `_latest_confirmed_swing`.)
- 🔧 **DECISION:** `k = 2` default; ablation `k ∈ {2, 3}`. "Unique extreme" (ties don't count) to
  avoid double-marking flat tops.

### 2.2 Dealing range, equilibrium, discount/premium, Fibonacci (anchor pinned to kill ambiguity)
For an **impulse leg** with protected extreme `P` and impulse extreme `X` (long: `P=`leg low,
`X=`leg high; short: `P=`leg high, `X=`leg low), range `R = |X − P|`:
- **Normalized position** of any price `p`: `pos = (p − P) / (X − P)` ⇒ `pos=0` at `P`, `pos=1` at `X`.
- **Equilibrium** = `0.5`. **Discount** = `pos ∈ [0, 0.5]` (cheap; longs buy here). **Premium** =
  `pos ∈ [0.5, 1]` (shorts sell here). This matches the brief's "discount 0–0.5 (longs)".
- **Retracement depth** `r = 1 − pos` measured from the impulse extreme `X` (the OTE convention in
  the ported `fib.py`): long `retr(r) = X_high − r·R`; short `retr(r) = X_low + r·R`. So a **deeper**
  fib threshold (0.618, 0.705) = **smaller `pos`** (closer to `P`).
- **Fib threshold** `t`: entry requires the pullback to reach at least depth `t`, i.e.
  **`pos ≤ 1 − t`**. `t=0.5` ⇒ `pos ≤ 0.5` (into discount/premium). `t=0.618` ⇒ `pos ≤ 0.382`.
- **Extensions** (TP/targets) project from the same leg: long `ext(e)=P + e·R`; short `ext(e)=P − e·R`.
- 🔧 **DECISION:** `fib_threshold = 0.5` default; ablation `{0.5, 0.618}` (0.705 available). The
  relevant leg in the cascade is the **MTF impulse leg that produced the BOS/CHoCH** (§3), and the
  pullback zone must **overlap the POI**.

### 2.3 FVG (fair value gap) — 3-candle imbalance
- Middle (displacement) candle index `c`. **Bullish FVG:** `L[c+1] > H[c-1]` ⇒ zone
  `[lower=H[c-1], upper=L[c+1]]`. **Bearish FVG:** `H[c+1] < L[c-1]` ⇒ zone
  `[lower=H[c+1], upper=L[c-1]]`. (Exactly the brief's inequalities; ported `detect_fvgs`.)
- **Confirmed** at bar `c+1`'s close (the third candle). Boundaries recorded; `midpoint=(upper+lower)/2`.
- **Entry edge ("前沿")** = the boundary price touches **first** on the retracement: for a **bullish**
  FVG (price falls into it from above) that is the **upper** boundary; for a **bearish** FVG, the
  **lower** boundary.
- 🔧 **DECISION — entry edge:** `entry_edge = near` default (the first-touched boundary above);
  ablation `{near, mid(50%), far}`. A small **size filter** `fvg_min_atr = 0.10·ATR` drops
  microscopic gaps (ablation `{0.0, 0.10, 0.25}`). The pure geometric FVG (no displacement gate) is
  the primitive; the *displacement* requirement lives in **POI formation** (§2.6), not in the FVG
  definition itself.

### 2.4 BOS (break of structure — continuation)
- A **close** beyond the last confirmed swing **in the prevailing direction**: long-trend BOS =
  `C[i] > ` (last confirmed swing high) with `C[i-1] ≤` it; short-trend symmetric on swing lows.
  Used on HTF/MTF to confirm trend and **anchor the impulse leg** (the leg from the prior opposing
  confirmed swing to the breaking bar's extreme).

### 2.5 CHoCH (change of character — reversal / pullback-resumption trigger)
- The **first close that breaks structure against the prevailing local direction**. Operationally
  (ported `_mss_structural_breaks`): the first `C[i]` to close through the most recent confirmed
  opposing swing, with `C[i-1]` on the other side, deduped per reference swing.
- **Convention (disambiguates BOS vs CHoCH):** *HTF/MTF use **BOS** to set direction; the entry
  trigger inside the POI uses **CHoCH** (the close that ends the pullback and resumes the HTF-bias
  direction).* The two are not interchanged. The reusable detector returns a generic structural
  break; V3 labels it BOS vs CHoCH from the prevailing-direction context.

### 2.6 POI (point of interest)
- The **FVG / order block / supply-demand zone produced by the displacement that caused the
  BOS/CHoCH.** V3 default POI = the qualifying **FVG inside the impulse leg** that produced the
  structural break (associated to the break within `fvg_assoc_window` bars). Order-block variant
  (last opposing candle before the impulse; zone `[open, low]` long / `[high, open]` short,
  `ob_use_wick` optional) is available but **off by default** to keep the primary grid lean.
- **Mitigation tracking:** a POI is **unmitigated** until price trades back into its zone; only
  unmitigated POIs are actionable. The engine tracks mitigation causally.
- 🔧 **DECISION:** primary grid uses the **FVG-POI**; OB-POI and confluence scoring are ablations.

### 2.7 EMA bias filter (Vegas tunnel)
- EMA(55) & EMA(144) on the **bias timeframe** (default = HTF). Long-only when bias-TF
  `close > EMA55 and close > EMA144`; short-only when `close < both`; **between the bands ⇒ no
  trade**. Never trade against HTF bias.
- 🔧 **DECISION:** `ema_filter = on` default, read on **HTF**; ablation `{on, off}` and
  `{HTF, MTF}` for which TF it reads. EMAs computed on **closed** bars only.

### 2.8 ATR
- 🔧 **DECISION:** `ATR(14)` using **Wilder's RMA of True Range** (standard). *Note:* the ported
  detector used an SMA-of-TR; V3 standardizes on Wilder and unit-tests the recursion as strictly
  causal. Used for: FVG size filter, stop buffer, displacement scaling, regime classification.

---

## 3 · Entry logic

### 3.1 Model A — full cascade
1. **HTF POI** on {W1 | D1}: a key S/R / supply-demand zone (FVG-POI per §2.6); EMA bias must permit
   the direction.
2. **MTF confirmation** on {H4 | H1}: a **BOS/CHoCH in the HTF-bias direction that contains an FVG**;
   this defines the **impulse leg** for the Fib zone.
3. **Pullback** into the `pos ≤ 1 − fib_threshold` (discount/premium) zone of that impulse leg, where
   the zone **overlaps the HTF POI**.
4. **LTF trigger** on {M15 | M5 | M1}: a **CHoCH (close-through) in the HTF-bias direction with a
   qualifying FVG**. On confirmation, place a **limit at the entry edge of the LTF FVG** (§2.3).
5. **Stop:** LTF recent swing high/low **± `atr_mult·ATR`** buffer.

### 3.2 Model B — direct POI (set-and-forget)
- Locate the POI via steps 1–3, then place a **passive limit at the HTF/MTF POI**; **stop at the HTF
  swing ± `atr_mult·ATR`**. No LTF confirmation.
- 🔧 **DECISION (the brief's open question):** implement **both** as flag `direct_poi_source`:
  `htf_only` (POI from HTF zone + EMA bias) **and** `requires_mtf_shift` (POI must be backed by an
  MTF BOS/CHoCH). **Primary grid uses `htf_only`** ⇒ direct = 2 htf × 3 tp = **6** configs;
  `requires_mtf_shift` (which would add the ×2 mtf → 12) is an **ablation**, not a primary trial, to
  keep the multiple-testing count at the brief's headline **42**.

### 3.3 Take-profit modes
- (a) **`fixed_3R`** — exit at entry ± 3·(initial risk).
- (b) **`HTF_level`** — an **opposing HTF key level**, from **already-confirmed structure and FIXED
  at entry**. 🔧 **DECISION — `htf_target_mode`:** default **`major_swing`** = the nearest opposing
  **significant** HTF swing beyond entry, where "significant" = a larger-fractal swing
  (`major_swing_lookback`, default 5) — i.e. a genuine key level / liquidity pool with high R:R (the
  intended behaviour). Ablation **`nearest_swing`** = the nearest ordinary confirmed swing (often
  close to entry, low R:R). Either way the level is **frozen at entry, never recomputed from future
  bars** (this was the V2 look-ahead bug; §7.4). If no qualifying level exists, the trade rides to
  its stop/breakeven (no fixed TP).
- (c) **`scale_2R_then_HTF`** — close 50% at +2R, run the remainder to the `HTF_level`.

### 3.4 Management
- **Risk = 1%** of current equity per trade (§5).
- **Breakeven at +2R** (move stop to entry + `be_buffer`): `be_at_2R = on` default; ablation `{on,off}`.
- **Order expiry / invalidation:** cancel the resting limit if a bar **closes beyond the far side of
  the POI** (invalidation) **or** after `entry_expiry_bars` LTF bars unfilled. 🔧 `entry_expiry_bars
  = 24` (LTF) default.
- **Concurrency:** at most **one open position per direction**; while one is open, new same-direction
  signals are ignored (no pyramiding). 🔧 Also cap total simultaneous risk at one position per
  direction (≤ 2 open total). No portfolio/correlation caps (single instrument).

---

## 4 · Parameter grid

Primary cross-product (enumerated and printed at runtime):

| Param | Values |
|---|---|
| `entry_model` | cascade, direct |
| `htf` | W1, D1 |
| `mtf` | H4, H1 (cascade; direct: see §3.2) |
| `ltf` | M15, M5, M1 (cascade only) |
| `tp` | 3R, HTF_level, scale_2R_then_HTF |

- cascade: 2×2×3×3 = **36** · direct (`htf_only`): 2×3 = **6** · **primary total = 42**.
- **Number of trials = 42** is fed explicitly into DSR / BH-FDR (§5).
- **Secondary / ablation** (run **only** on the strongest primary survivors; **not** counted as
  significance trials): `ema_filter {on,off}`, `fib_threshold {0.5,0.618}`, `be_at_2R {on,off}`,
  `atr_mult {0.5,1.0,1.5}`, `swing_lookback k`, `entry_edge`, `direct_poi_source`,
  `htf_target_mode {major_swing, nearest_swing}`, FVG/OB-POI.
- Everything is **YAML-driven**; a config snapshot + seed is written per run.

---

## 5 · Risk & R accounting

- **Position size:** `lots = (equity × 0.01) / (stop_distance_price × money_per_price_unit_per_lot)`,
  rounded down to `lot_step`, clamped `[min_lot, max_lot]`; reject if below `min_lot` or if the stop
  is implausibly tight. **XAUUSD spec:** 100 oz/lot, `tick_size=0.01`, `tick_value=1.0` ⇒
  `money_per_price_unit_per_lot = 100` (a $1 move = $100/lot). 1 pip = $0.10. (Ported `InstrumentSpec`.)
- **R accounting:** `R = initial_risk = |entry − initial_stop| × size_value`. Realized R = money
  PnL (net of costs) / initial-risk money. BE/scale-out/partial fills tracked so realized R is exact
  (unit-tested). `final_sl_price` and exit reason logged per trade for human verification.

---

## 6 · Backtest engine — correctness first

### 6.1 Event-driven, bar-by-bar
At decision time `t`, only bars **closed at or before `t`** are visible on **every** timeframe.
Never read a still-forming HTF/MTF bar. Detection (swings, FVG, BOS/CHoCH, Fib, EMA, ATR) uses
closed candles only.

### 6.2 MTF alignment (no look-ahead core, ported)
Two complementary guarantees (from `data_handler.py`):
- **`align_to_ltf`**: HTF columns `shift(1)` then `reindex(ltf.index).ffill()` — LTF bar `t` sees the
  HTF bar *before* the current one.
- **`closed_asof(frame, tf, t)`**: returns HTF bars with `bar_start + tf_duration ≤ t` — only fully
  closed HTF structure at LTF time `t`. The event loop uses this as-of slice.

### 6.3 Intrabar resolution with M1
The base series is M1. Decisions are made on closed bars of each TF; **fills are resolved by stepping
through the underlying M1 bars** within the relevant period — for limit entries, SL, TP, BE moves,
and scale-outs. We **do not** assume the order of a bar's high/low. (For `ltf=M1`, the LTF bar *is*
the M1 bar.) A **limit fills only if some M1 bar trades through the level** (`low ≤ level ≤ high`),
filled at the level ± slippage; otherwise it expires per §3.4. `HTF_level` TP targets are frozen at
entry (§3.3b).

### 6.4 Same-bar SL/TP tie-break & halts
- 🔧 **DECISION:** when both SL and TP lie within one M1 bar's range, assume **SL hit first**
  (worst case). The optimistic (TP-first) variant is reported as a **sensitivity** check.
- **No silent equity guards.** There is no auto-reset circuit breaker that can truncate a run; any
  stop-trading logic, if added, is explicit, logged, and tested.

### 6.5 Costs (applied to entries, exits, and scale-outs)
- 🔧 **DECISION — XAUUSD defaults (broker-typical placeholders; OHLC carries no spread, so this is
  modelled and disclosed in every report):** **spread = $0.20** (half-spread $0.10 per side),
  **commission = $7 / round-turn / lot** ($3.5/side), **slippage = $0.05 per side**. All configurable.
- 🔧 **DECISION (confirmed) — overnight swap included:** financing is modelled (default from
  `InstrumentSpec`: long −$6, short −$3 per lot per night; toggleable), since HTF-target trades hold
  for days and omitting it would flatter returns.
- 🔧 **DECISION (confirmed) — high-slippage-on-stops sensitivity:** the $0.05/side base slippage is
  optimistic for **stop-loss / market-stop exits** (gold gaps on news). Alongside the base cost
  model, a **high-slippage-on-stops** run applies elevated slippage (`stop_slippage_high = $0.50/side`
  default, configurable) to SL exits **only**; headline configs are re-evaluated under it (§8).

---

## 7 · Look-ahead defense (testing strategy)

The brief's "deliberate look-ahead unit test" = **truncation-invariance**: recomputing any
signal/structure on the prefix `[0 … i]` must reproduce its historical value; if deleting future
bars changes a past signal, the test **fails**. Applied to: swing confirmation, FVG, BOS/CHoCH, EMA,
ATR, the MTF as-of alignment, the trailing/`HTF_level` TP, and BE. (Adopts the proven V2 pattern;
the V2 engine shipped 9 such tests.)

---

## 8 · Statistics & robustness

**Per-config performance:** N, win rate, avg R, **expectancy E[R]**, profit factor, payoff ratio,
avg win/loss, max consecutive losses; total return, CAGR, ann. vol, **Sharpe, Sortino, Calmar**; max
drawdown (% / R / duration), **Ulcer index**, MAE/MFE distributions; equity & drawdown curves, R
histogram.

**Inference (the credibility core):**
- **Monte-Carlo (≥ 10,000), for RISK not edge:** (i) trade-sequence **reshuffle** (order/path risk;
  terminal value is order-invariant under fixed-fractional, so this isolates drawdown) and (ii)
  **bootstrap** resample (composition risk). Report fan charts + percentiles for terminal equity,
  **max-DD distribution**, risk-of-ruin, and Sharpe. *MC characterizes risk; it does not validate edge.*
- **Random-entry benchmark (the central EDGE/falsification test) — TWO nulls:** identical risk
  model, costs, and exit/management; match the strategy's trade cadence (N and holding-time
  distribution). Run **≥ 1,000** random strategies per null:
  - **(a) Unconstrained** — randomize entry timing **and** direction over tradeable bars.
  - **(b) Bias-matched** — keep the strategy's **EMA-bias gating** (same per-bar direction/regime
    permission) but randomize structural timing and **ignore POI / FVG / CHoCH**.
  Report the strategy's **percentile against both**. The decomposition is a **primary result**:
  beating (a) but **not** (b) ⇒ the edge is just the trend filter and the SMC structure adds nothing;
  beating (b) ⇒ the SMC structure itself contributes. *(MC characterizes risk; random-entry tests edge.)*
- **Bootstrap CIs** on expectancy and Sharpe; **significance** via bootstrap / t-test that mean R > 0
  with **p-values**; plus a **drop-1 (jackknife)** check (does the edge survive removing the single
  best trade?).
- **Cost/fill sensitivity:** re-run headline configs under (a) the **high-slippage-on-stops** model
  (§6.5) and (b) the **optimistic TP-first** same-bar tie-break (§6.4), to show how much any apparent
  edge depends on cost/fill assumptions.
- **Sharpe convention (explicit — DSR / PSR / BH-FDR all sit on it):** Sharpe and Sortino are
  computed on **daily mark-to-market equity resampled to business days** (`B`, equity held flat
  between trade exits); returns = daily pct-change; **annualized ×√252**; risk-free rate = 0. This is
  deflated by the many flat days of a sparse-trade strategy but is consistent across configs. A
  per-trade Sharpe (mean R / std R, annualized by √(trades·yr⁻¹)) is reported as a secondary view.
  The **number of daily returns** and the **trial count (= 42)** are fed explicitly into DSR/PSR and
  the BH-FDR threshold.
- **Multiple-testing correction (mandatory):** **Benjamini–Hochberg FDR** across the **42** primary
  trials; **Deflated Sharpe Ratio** and **Probabilistic Sharpe Ratio** (Bailey & López de Prado) with
  the trial count fed in explicitly. State the **effective post-correction significance threshold**.
- **Walk-forward:** 🔧 fixed-parameter **sequential OOS** across rolling folds on IS (default 3y
  train / 1y test, step 1y) — with un-optimized params this measures OOS-vs-IS *consistency* and
  degradation per config. (A re-selecting WFA is available as an extension.)
- **Locked OOS (2023–2025):** finalists evaluated **once**; reported honestly even if they degrade.
- **Regime analysis:** by **year** and by **volatility/gold regime** (e.g., 2015–18 range, 2019–20 +
  COVID, 2022–24 bull), with ATR-based regime tags.
- **Minimum sample size:** any config with **N < 30 trades** is flagged statistically unreliable and
  not over-interpreted. Deep cascades (e.g., **W1 → … → M1**, W1 over 8 IS years ≈ ~400 weekly bars)
  are expected to be **trade-starved** — stated explicitly.

---

## 9 · Architecture & reuse

Clean layout per brief §7: `data/ indicators/ smc/ strategy/ engine/ risk/ metrics/ robustness/
reporting/ config/ tests/ notebooks/ docs/`. Type hints + docstrings throughout; **config-driven, no
magic numbers** (all params in one typed config tree + YAML). *Sensible adaptation:* the code lives
under one importable top-level package **`mtf_smc/`** (`mtf_smc/data`, `mtf_smc/engine`,
`mtf_smc/smc`, …) to avoid shadowing generic names like `data`/`engine` and to ship as a proper
distribution; YAML grids in root `configs/`, runnable entry points in `scripts/`.

**Fresh build, reusing verified pieces** (your decision). Ported/adapted from
`…/Algorithmic Trading System - V2` **with fresh unit tests**:
- `data_loader.py` (HistData EST→UTC, dedupe, cache) → `data/`.
- `data_handler.py` (MTF `shift(1)` alignment + `closed_asof`) → `engine/` alignment layer.
- `smc_structure.py` primitives (`detect_swings`, `detect_fvgs`, `_latest_confirmed_swing`,
  MSS/CHoCH) → `smc/`. The extra TK-style CB/DB modes are **not** part of V3's primary definitions
  (available only as an ablation).
- `fib.py` (leg retracement/extension) → `indicators/` or `smc/`.
- `instrument.py` (`InstrumentSpec` money math, XAUUSD spec) → `risk/`.
- Conceptual reuse (rebuilt to V3's grid/stats): Monte-Carlo, analytics/CIs, walk-forward.
**Net-new in V3:** the cascade/direct entry models A/B, the 42-config grid runner, intrabar M1 fill
engine, random-entry benchmark, BH-FDR + DSR + PSR, locked-OOS harness, reporting/heatmaps, REPORT.md.

**Reproducibility:** fixed RNG seeds, per-run config+seed snapshot, `requirements.txt`/`pyproject.toml`,
data instructions (§1.5), tiny synthetic sample; **no licensed data committed**; clean commit history.

---

## 10 · Build order (Process §8) & definition of done

1. **(this step)** `SPEC.md` + `CLAUDE.md` + `PROJECT_BRIEF.md` → **pause for confirmation.**
2. Data: port loader, build resampling + **quality report**, validate (incl. no-look-ahead alignment test).
3. Primitives bottom-up **with tests**, including the truncation-invariance look-ahead test.
4. Engine: intrabar M1 fills + costs validated on a tiny slice; one config end-to-end sanity check.
5. Primary grid (42) on **IS 2015–2022** → robustness (MC, random-entry, walk-forward, BH-FDR/DSR/PSR)
   → targeted ablations on survivors.
6. **Then** finalists on the **locked OOS** (once).
7. Reports + honest `REPORT.md` + polished `README.md`.

**Done =** full 42-config grid with multiple-testing-corrected significance, MC + random-entry
benchmark, walk-forward, one-shot OOS, reproducible configs/seeds, all tests passing, clean public
repo, honest conclusion.

---

## 11 · Confirmation log

**All five items below were confirmed (2026-06-03)**, with two refinements now folded into §1.5 and
§6.5/§8: (i) the IS loader **hard-slices to ≤ 2022-12-31** structurally; (ii) a **high-slippage-on-stops**
sensitivity run is added. Original items, for the record:

1. **Swap cost** — include overnight financing (recommended) or keep strictly to the brief's
   spread/commission/slippage? → **included.** (§6.5)
2. **Seed `data_cache/`** from the existing V2 `XAUUSD_M1_UTC_2015_2023.pkl` for immediate IS work? (§1.5)
3. **Cost values** — are the XAUUSD placeholders (spread $0.20, commission $7 RT, slippage $0.05/side)
   acceptable, or do you have broker-specific numbers? (§6.5)
4. **Direct Model B default** — primary grid uses `htf_only` (keeps trials at 42); `requires_mtf_shift`
   as ablation. OK? (§3.2)
5. Any SMC `🔧 DECISION` default above you'd override (esp. `fib_threshold=0.5`, `entry_edge=near`,
   `k=2`, FVG-POI over OB-POI, EMA filter on/HTF, Wilder ATR, SL-first tie-break).

Everything else follows the brief as written. **Confirmed — proceeding to step 2.**
