"""Data-quality report for the XAUUSD M1 series.

Detects and *documents* (never silently patches): per-year bar counts (flagging years materially
below the median, e.g. the known ~12%-thin 2023), gaps (intrabar >5min, session >1h, weekend
>24h, the max gap), OHLC integrity, duplicate/monotonicity, and the largest gaps with timestamps
(useful for eyeballing holidays/rollover artifacts). See ``docs/SPEC.md`` §1.4.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np
import pandas as pd

from mtf_smc.config import DataConfig
from mtf_smc.data.resample import resample_ohlc
from mtf_smc.timeframes import TIMEFRAMES

OHLC = ["open", "high", "low", "close"]


@dataclass
class GapStats:
    intrabar_gt_5min: int
    session_gt_1h: int
    weekend_gt_24h: int
    max_gap_hours: float
    max_gap_at: pd.Timestamp


def gap_stats(m1: pd.DataFrame) -> GapStats:
    """Magnitude of gaps between consecutive M1 bars (reported, not patched)."""
    deltas = m1.index.to_series().diff().dropna()
    sec = deltas.dt.total_seconds()
    max_at = deltas.index[int(np.argmax(sec.to_numpy()))] if len(sec) else m1.index[0]
    return GapStats(
        intrabar_gt_5min=int((sec > 5 * 60).sum()),
        session_gt_1h=int((sec > 3600).sum()),
        weekend_gt_24h=int((sec > 24 * 3600).sum()),
        max_gap_hours=float(sec.max() / 3600.0) if len(sec) else 0.0,
        max_gap_at=max_at,
    )


def largest_gaps(m1: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """The ``n`` largest inter-bar gaps with their start timestamp and duration in hours."""
    deltas = m1.index.to_series().diff()
    top = deltas.sort_values(ascending=False).head(n)
    return pd.DataFrame({
        "gap_start": top.index - top.values,  # previous bar timestamp
        "resumes_at": top.index,
        "gap_hours": (top.dt.total_seconds() / 3600.0).round(2),
    }).reset_index(drop=True)


def per_year_counts(m1: pd.DataFrame, thin_frac: float = 0.9) -> pd.DataFrame:
    """Per-year M1 bar counts, flagging years below ``thin_frac`` x median as thin."""
    counts = m1.groupby(m1.index.year).size()
    median = float(counts.median())
    out = counts.to_frame("bars")
    out["pct_of_median"] = (out["bars"] / median * 100).round(1)
    out["thin_flag"] = out["bars"] < thin_frac * median
    out.index.name = "year"
    return out


def integrity_summary(m1: pd.DataFrame) -> Dict[str, object]:
    """Integrity facts (post-load these should all be clean; reported for the record)."""
    dup = int(m1.index.duplicated().sum())
    monotonic = bool(m1.index.is_monotonic_increasing)
    bad = (
        (m1["high"] < m1["low"])
        | (m1["high"] < m1["open"]) | (m1["high"] < m1["close"])
        | (m1["low"] > m1["open"]) | (m1["low"] > m1["close"])
    )
    nan_rows = int(m1[OHLC].isna().any(axis=1).sum())
    return {
        "duplicate_timestamps": dup,
        "index_monotonic_increasing": monotonic,
        "ohlc_violations": int(bad.sum()),
        "rows_with_nan_ohlc": nan_rows,
    }


def resample_counts(
    m1: pd.DataFrame, tfs: Sequence[str] = TIMEFRAMES, anchor: str = "ny_close"
) -> pd.DataFrame:
    """Bar counts at every timeframe (sanity-checks the resampling)."""
    rows: List[dict] = []
    for tf in tfs:
        r = resample_ohlc(m1, tf, anchor=anchor)
        rows.append({"timeframe": tf, "bars": len(r),
                     "start": r.index[0], "end": r.index[-1]})
    return pd.DataFrame(rows)


def _plot_bars_per_year(per_year: pd.DataFrame, out_png: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4))
    colors = ["#c0392b" if t else "#2c3e50" for t in per_year["thin_flag"]]
    ax.bar(per_year.index.astype(str), per_year["bars"], color=colors)
    ax.set_title("XAUUSD M1 bars per year (red = thin vs median)")
    ax.set_xlabel("year"); ax.set_ylabel("M1 bars")
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=120)
    plt.close(fig)


def build_report(
    m1: pd.DataFrame,
    cfg: DataConfig | None = None,
    tfs: Sequence[str] = TIMEFRAMES,
    label: str = "IN-SAMPLE (2015-2022)",
) -> Dict[str, Path]:
    """Compute the report and write Markdown (docs/), CSVs (output/quality/), and a PNG (assets/).

    Returns a dict of written paths.
    """
    cfg = cfg or DataConfig()
    repo = cfg.output_dir.parent
    out_dir = cfg.output_dir / "quality"
    out_dir.mkdir(parents=True, exist_ok=True)

    anchor = cfg.session_anchor
    gs = gap_stats(m1)
    per_year = per_year_counts(m1)
    integ = integrity_summary(m1)
    rs = resample_counts(m1, tfs, anchor=anchor)
    big = largest_gaps(m1)

    # CSV artifacts (regenerable; git-ignored under output/).
    per_year.to_csv(out_dir / "per_year.csv")
    rs.to_csv(out_dir / "resample_counts.csv", index=False)
    big.to_csv(out_dir / "largest_gaps.csv", index=False)

    png = repo / "assets" / "data_quality_bars_per_year.png"
    _plot_bars_per_year(per_year, png)

    md = repo / "docs" / "DATA_QUALITY.md"
    lines: List[str] = []
    lines.append(f"# Data-Quality Report — {cfg.symbol} M1 ({label})\n")
    lines.append("> Generated by `scripts/build_quality_report.py`. Gaps and anomalies are "
                 "**reported, not patched** (see `docs/SPEC.md` §1.4).\n")
    lines.append("## Overview\n")
    lines.append(f"- Bars (M1): **{len(m1):,}**")
    lines.append(f"- Range: `{m1.index[0]}` -> `{m1.index[-1]}` (UTC)")
    lines.append(f"- Timezone: UTC (source HistData fixed EST, UTC-5, no DST)")
    anchor_note = ("17:00 America/New_York close, DST-aware" if anchor == "ny_close"
                   else "UTC calendar day / UTC Monday week")
    lines.append(f"- Session anchor (D1/W1): **{anchor}** ({anchor_note})\n")

    lines.append("## Per-year M1 bars\n")
    lines.append("| year | bars | % of median | thin? |")
    lines.append("|---|---:|---:|:--:|")
    for yr, row in per_year.iterrows():
        flag = "⚠️ thin" if row["thin_flag"] else ""
        lines.append(f"| {yr} | {int(row['bars']):,} | {row['pct_of_median']:.1f}% | {flag} |")
    lines.append(f"\n![bars per year](../assets/{png.name})\n")

    lines.append("## Gaps (inter-bar)\n")
    lines.append(f"- Intrabar gaps > 5 min: **{gs.intrabar_gt_5min:,}**")
    lines.append(f"- Session gaps > 1 h: **{gs.session_gt_1h:,}**")
    lines.append(f"- Weekend/holiday gaps > 24 h: **{gs.weekend_gt_24h:,}**")
    lines.append(f"- Largest gap: **{gs.max_gap_hours:.1f} h** (resumes at `{gs.max_gap_at}`)\n")
    lines.append("### 10 largest gaps\n")
    lines.append("| gap_start | resumes_at | gap_hours |")
    lines.append("|---|---|---:|")
    for _, r in big.iterrows():
        lines.append(f"| `{r['gap_start']}` | `{r['resumes_at']}` | {r['gap_hours']:.2f} |")
    lines.append("")

    lines.append("## Integrity\n")
    for k, v in integ.items():
        lines.append(f"- {k}: **{v}**")
    lines.append("")

    lines.append("## Resampled bar counts\n")
    lines.append("| timeframe | bars | start | end |")
    lines.append("|---|---:|---|---|")
    for _, r in rs.iterrows():
        lines.append(f"| {r['timeframe']} | {int(r['bars']):,} | `{r['start']}` | `{r['end']}` |")
    lines.append("")

    md.write_text("\n".join(lines), encoding="utf-8")
    return {"markdown": md, "plot": png, "per_year_csv": out_dir / "per_year.csv",
            "resample_csv": out_dir / "resample_counts.csv",
            "gaps_csv": out_dir / "largest_gaps.csv"}
