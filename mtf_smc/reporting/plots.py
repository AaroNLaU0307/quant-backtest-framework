"""Report figures (matplotlib, Agg). Saved to ``assets/`` and referenced by docs/REPORT.md.

Figures: per-config equity + drawdown curve, R-multiple histogram, Monte-Carlo fan chart, and the
grid expectancy heatmap. All are descriptive of an honest no-edge result, not a sales pitch.
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from mtf_smc.robustness.montecarlo import fan_chart_bands  # noqa: E402


def equity_drawdown(equity_curve: pd.Series, out_path: Path, title: str = "") -> Path:
    eq = equity_curve.dropna()
    dd = eq / eq.cummax() - 1.0
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6), sharex=True,
                                   gridspec_kw={"height_ratios": [2, 1]})
    ax1.plot(eq.index, eq.values, color="#2c3e50")
    ax1.set_ylabel("equity"); ax1.set_title(title or "Equity & drawdown")
    ax1.grid(alpha=0.3)
    ax2.fill_between(dd.index, dd.values * 100, 0, color="#c0392b", alpha=0.6)
    ax2.set_ylabel("drawdown %"); ax2.grid(alpha=0.3)
    fig.tight_layout(); _save(fig, out_path); return out_path


def r_histogram(R: Sequence[float], out_path: Path, title: str = "") -> Path:
    r = np.asarray(list(R), dtype=float)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(r, bins=40, color="#2c3e50", alpha=0.8)
    ax.axvline(0, color="k", lw=1)
    ax.axvline(float(np.mean(r)), color="#c0392b", lw=2, ls="--",
               label=f"E[R]={np.mean(r):+.3f}")
    ax.set_xlabel("R multiple"); ax.set_ylabel("trades"); ax.set_title(title or "R-multiple distribution")
    ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); _save(fig, out_path); return out_path


def mc_fan_chart(R: Sequence[float], out_path: Path, risk_pct: float = 0.01,
                 n_runs: int = 2000, seed: int = 7, title: str = "") -> Path:
    steps, bands = fan_chart_bands(R, risk_pct=risk_pct, n_runs=n_runs, seed=seed)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    if len(steps):
        ax.fill_between(steps, bands["p5"], bands["p95"], color="#2980b9", alpha=0.2, label="5-95%")
        ax.fill_between(steps, bands["p25"], bands["p75"], color="#2980b9", alpha=0.35, label="25-75%")
        ax.plot(steps, bands["p50"], color="#2c3e50", lw=2, label="median")
        ax.axhline(1.0, color="k", lw=1, ls=":")
    ax.set_xlabel("trade #"); ax.set_ylabel("equity multiple")
    ax.set_title(title or "Monte-Carlo bootstrap fan chart"); ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); _save(fig, out_path); return out_path


def grid_heatmap(master: pd.DataFrame, out_path: Path) -> Path:
    df = master.copy()
    df["cell"] = df.apply(
        lambda r: (f"{r['entry_model']}_{r['htf']}_{r['mtf']}_{r['ltf']}"
                   if r["entry_model"] == "cascade" else f"direct_{r['htf']}"), axis=1)
    piv = df.pivot_table(index="cell", columns="tp_mode", values="expectancy_R", aggfunc="first")
    piv = piv.sort_index()
    vmax = float(np.nanmax(np.abs(piv.to_numpy())))
    fig, ax = plt.subplots(figsize=(7, max(4, 0.32 * len(piv))))
    im = ax.imshow(piv.to_numpy(), cmap="RdBu", vmin=-vmax, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(piv.columns))); ax.set_xticklabels(piv.columns, rotation=20, ha="right")
    ax.set_yticks(range(len(piv.index))); ax.set_yticklabels(piv.index, fontsize=7)
    ax.set_title("Expectancy E[R] by config (red = negative)")
    fig.colorbar(im, ax=ax, label="E[R]")
    fig.tight_layout(); _save(fig, out_path); return out_path


def _save(fig, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
