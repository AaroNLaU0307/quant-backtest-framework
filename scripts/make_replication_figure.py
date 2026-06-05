"""Replication heatmap: per-instrument E[R] for all 42 configs x 5 instruments.

Reads output/replication/*.csv (produced by run_replication.py) and writes
assets/replication_heatmap.png. Green = positive, red = negative; the near-uniform red — and the
isolated bright cells that do not repeat across a row — is the multi-asset null at a glance.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from mtf_smc.config import REPO_ROOT

OUT = REPO_ROOT / "output" / "replication"


def main() -> None:
    er = pd.read_csv(OUT / "replication_grid_ER.csv").set_index("config_id")
    cons = pd.read_csv(OUT / "consistency.csv").set_index("config_id")
    er = er.loc[cons.sort_values("mean_ER", ascending=False).index]      # least-bad at top
    M = er.to_numpy(float)
    vmax = 0.75                                                          # clip; outliers saturate

    fig, ax = plt.subplots(figsize=(6.4, 13.0))
    im = ax.imshow(M, aspect="auto", cmap="RdYlGn", vmin=-vmax, vmax=vmax)
    ax.set_xticks(range(er.shape[1]))
    ax.set_xticklabels(er.columns, fontsize=9)
    ax.set_yticks(range(er.shape[0]))
    ax.set_yticklabels(er.index, fontsize=6)
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            v = M[i, j]
            ax.text(j, i, f"{v:+.2f}", ha="center", va="center", fontsize=5.2,
                    color="black" if abs(v) < 0.55 else "white")
    ax.set_title("Per-instrument expectancy E[R]  (42 configs x 5 instruments, IS 2015-2022)\n"
                 "0/42 positive-and-significant on >=2 independent instruments", fontsize=9)
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label("E[R] per trade (clipped +/-0.75)", fontsize=8)
    fig.tight_layout()
    png = REPO_ROOT / "assets" / "replication_heatmap.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png, dpi=130)
    plt.close(fig)
    print(f"wrote {png}")


if __name__ == "__main__":
    main()
