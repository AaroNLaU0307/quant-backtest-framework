# Claude Code Project Brief — Institutional-Grade Backtest of a Multi-Timeframe SMC / Price-Action Strategy on XAUUSD (2015–2025)

> This is the original project brief, preserved verbatim. The authoritative, decision-resolved
> specification derived from it is [`SPEC.md`](SPEC.md). Where this brief and `SPEC.md` differ,
> `SPEC.md` records the chosen default and the reason; `SPEC.md` governs implementation.

## 0 · Mission & stance
You are a quantitative research engineer. Build a **reproducible, research-grade backtesting framework** that rigorously tests whether a discretionary-style, multi-timeframe Smart-Money-Concepts (SMC) price-action strategy has a **statistically real edge** on XAUUSD, across a defined grid of structural variants.
This is a **falsification-oriented research project**, not a profit-seeking bot. The goal is an honest, defensible answer — including a clean negative result if that is what the data shows. The output is a public GitHub portfolio piece aimed at quant-research recruiters. Favor correctness, statistical honesty, and reproducibility over flattering results. **Never tune parameters until something "looks profitable"** — that is data snooping, and avoiding it is the explicit purpose of this study.

## 1 · Data
- Input: **XAUUSD 1-minute (M1) OHLCV**, ~2015–2025 (HistData-style CSV). Confirm the exact schema and timezone before writing any code.
- Build all higher timeframes by resampling M1: **W1, D1, H4, H1, M15, M5, M1**. Use correct session/UTC handling and document the convention.
- Data hygiene: detect and document gaps, weekend/holiday boundaries, DST shifts, and any contract-rollover artifacts. Produce a data-quality report.
- **Lock 2023–2025 as out-of-sample (OOS).** It is touched exactly once, at the very end, only for the final selected configuration(s). All development and grid search use 2015–2022.
- Keep M1 available throughout — it is required for honest intrabar fill resolution (see §4).

## 2 · Strategy specification (make every definition explicit)
A top-down SMC model. Define each primitive precisely in `SPEC.md` and unit-test it; the validity of the entire study rests on these definitions.
**Primitives — give concrete, testable definitions:**
- *Swing high/low*: fractal with configurable lookback `k` (default 2–3 bars each side).
- *Dealing range / Fibonacci*: measured from the most recent confirmed swing low→high (or high→low). Equilibrium = 0.5; **discount = 0–0.5** (longs), **premium = 0.5–1.0** (shorts).
- *FVG (fair value gap)*: 3-candle imbalance. Bullish FVG when `low[i+1] > high[i-1]`; bearish when `high[i+1] < low[i-1]`. Record both boundaries; the **entry edge ("前沿")** is the boundary price touches first on the retracement (configurable: near edge / 50% / far edge).
- *BOS (break of structure)*: a candle **close** beyond the last confirmed swing in the prevailing direction (trend continuation).
- *CHoCH (change of character)*: the first close that breaks structure **against** the prevailing direction (potential reversal).
- *POI*: the FVG / order block / supply-demand zone produced by the displacement that caused the BOS/CHoCH.
- *EMA filter*: EMA(55) & EMA(144) used **only as a directional bias filter** (e.g., longs only when price/structure is above both). Configurable on/off and which timeframe it reads.

**Entry logic — two models:**
*Model A — full cascade:*
1. **HTF POI** on {W1 | D1}: identify a key support/resistance / supply-demand zone; apply the EMA bias filter.
2. **MTF confirmation** on {H4 | H1}: a BOS/CHoCH in the HTF-bias direction **that contains an FVG**.
3. **Pullback** into the **≤ 0.5 discount/premium** zone of the impulse leg, overlapping the POI. Fib threshold configurable (0.5 default; optional 0.618 / 0.705).
4. **LTF trigger** on {M15 | M5 | M1}: a BOS/CHoCH **with an FVG**. On confirmation, place a **limit order at the entry edge of the LTF FVG**.
5. **Stop**: the LTF (M15/M5) recent swing high/low **± ATR buffer** (ATR period & multiplier configurable).

*Model B — direct POI (set-and-forget):*
- Use steps 1–2/3 to locate the POI, then place a **passive limit at the HTF/MTF POI**, with **stop at the HTF swing high/low ± ATR**. No LTF confirmation. (Clarify in `SPEC.md` whether the POI is defined by HTF alone or still requires the MTF structure shift — implement both as a flag.)

**Take-profit — three modes:**
- (a) **Fixed 3R.**
- (b) **HTF key level** (next opposing structure / liquidity pool) — variable, high R:R.
- (c) **Scale-out**: close 50% at **+2R**, run the remainder to the HTF key level.

**Management rules:**
- **Risk = 1% of equity per trade.** Position size derived from stop distance (respect the XAUUSD contract spec / pip value).
- **Breakeven at +2R**: move the stop to entry. Default ON; expose as a flag for ablation.
- Order expiry / invalidation: cancel the resting limit if price closes beyond the POI (or after `N` bars) before it fills.
- Concurrency: define explicitly (suggest one open position per direction at a time).

## 3 · Parameter grid (the combinations to test)
Drive everything from a YAML config. Primary grid:
| Parameter | Values |
|---|---|
| `entry_model` | cascade, direct |
| `htf` | W1, D1 |
| `mtf` | H4, H1 |
| `ltf` | M15, M5, M1 (cascade only) |
| `tp` | 3R, HTF_level, scale_2R_then_HTF |
Primary cross-product:
- cascade: 2 (htf) × 2 (mtf) × 3 (ltf) × 3 (tp) = **36**
- direct: 2 (htf) × 3 (tp) = **6**  (or × 2 mtf = 12 if the POI requires an MTF shift)
- → **~42–48 primary configurations**. Enumerate and print the full list and count at runtime.
Secondary (sensitivity / ablation): run **only** on the strongest primary survivors, and treat these as robustness checks, **not** as extra significance trials —
`ema_filter ∈ {on, off}`, `fib_threshold ∈ {0.5, 0.618}`, `be_at_2R ∈ {on, off}`, `atr_mult ∈ {0.5, 1.0, 1.5}`, swing lookback `k`.

## 4 · Backtest engine — correctness first (zero look-ahead)
This is where backtests usually lie. Be paranoid.
- **Event-driven, bar-by-bar.** When evaluating any decision at time *t*, only candles **closed at or before *t*** are visible on **every** timeframe. Never read the still-forming HTF candle. Build an explicit MTF alignment layer and write a deliberate **look-ahead unit test** that fails if future data leaks.
- All detection (swings, FVG, BOS/CHoCH, Fib, EMA, ATR) uses **closed candles only**.
- **Intrabar resolution with M1**: resolve limit fills, stop-loss, take-profit, breakeven moves, and scale-outs by stepping through the underlying M1 bars inside each higher-TF bar — do **not** assume a bar's high and low occur in a convenient order.
- **Same-bar SL/TP conflict**: define a conservative, documented tie-break (default: assume the **stop** is hit first / worst case) and report sensitivity to this choice.
- **Costs**: realistic XAUUSD **spread**, **commission**, and **slippage** (configurable; document values and source). Apply to entries, exits, and scale-outs.
- A limit order fills only if M1 price actually trades through the level; otherwise it expires per the invalidation rule.

## 5 · Statistics & robustness (institutional / academic)
**Per-configuration performance:**
- Trades: N, win rate, average R, **expectancy (R)**, profit factor, payoff ratio, average win/loss, max consecutive losses.
- Returns: total return, CAGR, annualized volatility, **Sharpe**, **Sortino**, **Calmar**.
- Risk: **max drawdown** (% / R / duration), Ulcer index, MAE/MFE distributions.
- Artifacts: equity curve, drawdown curve, R-multiple histogram.

**Inference & robustness — the part that makes it credible:**
- **Monte Carlo (≥ 10,000 runs):**
  - (i) **Trade-sequence bootstrap / reshuffle** → distributions and CIs for terminal equity, max DD, and Sharpe (fan charts + percentiles). Drawdown is path-dependent, so report the distribution, not a point estimate.
  - (ii) **Random-entry benchmark**: same risk model, randomized entries → test whether the strategy's edge exceeds random entry. This is the core **falsification test** — keep it central.
- **Confidence intervals** (bootstrap) on expectancy and Sharpe.
- **Significance**: bootstrap / t-test that mean R > 0; report p-values.
- **Multiple-testing correction — mandatory.** Testing ~42 configurations means several will look "significant" by chance. Apply **Benjamini–Hochberg FDR**, and report the **Deflated Sharpe Ratio** and **Probabilistic Sharpe Ratio** (Bailey & López de Prado), explicitly feeding in the number of trials. State the effective significance threshold after correction.
- **Walk-forward analysis**: rolling in-sample → out-of-sample windows; report OOS-vs-IS degradation per config.
- **Locked OOS (2023–2025)**: evaluate the final selected config(s) once; report honestly even if they degrade.
- **Regime analysis**: break results down by year and by volatility/gold regime (e.g., 2015–18 range, 2019–20 + COVID, 2022–24 bull).
- **Minimum sample size**: flag any config with < ~30 trades as statistically unreliable and refuse to over-interpret it. Expect deep-cascade combos (e.g., W1 → M1) to be trade-starved — say so explicitly.

## 6 · Reporting & reproducibility
- A per-config report plus a **master comparison table** (sortable; all metrics + corrected significance).
- Plots: equity & drawdown curves, R-distributions, Monte Carlo fan charts, walk-forward windows, and a **parameter-grid heatmap** of the headline metric.
- **Academic write-up** (`docs/REPORT.md` or a notebook): abstract, data, precise methodology, assumptions, results, **limitations**, and an honest conclusion. If there is no robust edge, state it plainly and explain why that is a valid and valuable finding.
- Reproducibility: YAML configs, **fixed random seeds**, `requirements.txt` / `pyproject.toml`, and clear data-acquisition instructions. **Do not commit licensed data** — provide a loader + schema + a tiny sample.

## 7 · Architecture (clean research codebase)
Suggested layout (adapt sensibly):
```
data/            # loaders, resampling, quality report
indicators/      # ema, atr, fib
smc/             # swings, fvg, structure (bos/choch), zones/poi
strategy/        # entry models A & B, TP modes, BE, sizing
engine/          # event-driven backtester, MTF alignment, intrabar fills, costs
risk/            # position sizing, R accounting
metrics/         # performance stats
robustness/      # montecarlo, random_entry, walkforward, dsr/psr, fdr
reporting/       # tables, plots, report generation
config/          # YAML grids
tests/           # unit tests incl. look-ahead test, fill logic, R/BE math
notebooks/       # exploration + final report
docs/            # SPEC.md, REPORT.md, PROJECT_BRIEF.md
```
Type hints + docstrings throughout. **Unit-test the fragile pieces**: FVG detection, structure detection, no-look-ahead alignment, intrabar fill ordering, R calculation, and breakeven / scale-out accounting.

## 8 · Process (how to work)
1. First write **`SPEC.md`** fixing every definition and assumption above; explicitly flag the ambiguous SMC choices and the defaults you'll use, plus a short **`CLAUDE.md`** for repo conventions. **Pause for my confirmation on the definitions before heavy coding.**
2. Confirm the data schema; build data loading + resampling + quality report; validate.
3. Build primitives bottom-up **with tests**, including the deliberate look-ahead test.
4. Build the engine; validate fills/costs on a tiny slice; sanity-check a single config end-to-end before scaling.
5. Run the **primary grid** on 2015–2022; then robustness (MC, walk-forward, corrections); then targeted ablations on survivors.
6. Only then, evaluate finalists on the **locked OOS**.
7. Generate reports; write the honest `REPORT.md`; polish the repo + `README.md`.

**Definition of done:** full primary grid run with multiple-testing-corrected significance, Monte Carlo + random-entry benchmark, walk-forward, one-shot OOS, reproducible configs/seeds, complete tests passing, and a clean, well-documented public repo with an honest conclusion.

## 9 · Portfolio polish
`README.md`: a one-paragraph abstract, the research question, a methodology summary, **key findings stated honestly** (edge / no edge, with the corrected statistics), how to reproduce, limitations, and future work. Add a license and keep a clean, legible commit history.
