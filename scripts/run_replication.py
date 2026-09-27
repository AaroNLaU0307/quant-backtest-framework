"""Multi-instrument replication & meta-analysis.

Per-instrument E[R] side-by-side (config x instrument), cross-instrument return correlation +
effective number of independent instruments, a correlation-aware random-effects pool, and a
cross-(config x instrument) BH-FDR over the full trial set. The replication question: does any config
land positive-AND-significant on multiple *independent* instruments? Writes output/replication/*
(including stopouts.csv, the real-trade stop-out check, and provenance.json) and docs/REPLICATION.md.
See docs/SPEC_multi_instrument.md §6. The five master tables must come from one engine version (one
``code_hash``); mixing grids from different engine code raises.

    python scripts/run_replication.py
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from mtf_smc.config import REPO_ROOT, DataConfig
from mtf_smc.data.loader import load_is
from mtf_smc.data.resample import resample_ohlc
from mtf_smc.provenance import PROVENANCE_COLUMNS, code_hash, git_commit
from mtf_smc.robustness import replication as rep

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)
SYMS = rep.SYMBOLS


def _md(df: pd.DataFrame, fmt: str = "{:.3f}") -> str:
    """Render a DataFrame as a GitHub markdown table (no tabulate dependency)."""
    d = df.reset_index()
    f = lambda v: fmt.format(v) if isinstance(v, (float, np.floating)) else str(v)
    cols = [str(c) for c in d.columns]
    rows = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    rows += ["| " + " | ".join(f(v) for v in row) + " |" for row in d.itertuples(index=False)]
    return "\n".join(rows)


def _table_path(sym: str):
    return REPO_ROOT / "output" / "grid" / ("master_table.csv" if sym == "XAUUSD" else f"{sym}/master_table.csv")


def load_tables() -> dict:
    return {s: pd.read_csv(_table_path(s), dtype={c: str for c in PROVENANCE_COLUMNS}) for s in SYMS}


def table_sha256(path) -> str:
    """sha256 of a master table over LF-normalised bytes. The CSVs are written with the platform's line
    endings but committed and checked out as LF (``.gitattributes``: ``eol=lf``), so hashing the raw
    bytes on Windows gives a value no checkout reproduces."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def input_provenance(tables: dict) -> dict:
    """Provenance of the inputs; raises unless all five grids came from one engine version."""
    inputs, codes = {}, set()
    for s, df in tables.items():
        if "code_hash" not in df.columns:
            raise RuntimeError(f"{_table_path(s)} has no provenance columns; rerun its grid "
                               f"(scripts/run_grid.py fresh --symbol={s}).")
        codes |= set(df["code_hash"])
        inputs[s] = {"code_hash": sorted(set(df["code_hash"])), "git_commit": sorted(set(df["git_commit"])),
                     "sha256": table_sha256(_table_path(s))}
    if len(codes) != 1:
        raise RuntimeError(f"master tables come from different engine code {sorted(codes)}; "
                           f"rerun the stale grids with `fresh`.")
    return {"git_commit": git_commit(), "code_hash": code_hash(), "grid_code_hash": codes.pop(),
            "inputs": inputs}


def daily_returns() -> dict:
    r = {}
    for s in SYMS:
        d = resample_ohlc(load_is(DataConfig.for_symbol(s)), "D1", anchor="ny_close")
        r[s] = np.log(d["close"]).diff().rename(s)
    return r


def main() -> None:
    out = REPO_ROOT / "output" / "replication"
    out.mkdir(parents=True, exist_ok=True)
    tables = load_tables()
    prov = input_provenance(tables)

    # 1) Cross-instrument correlation + effective # independent instruments (mandatory pre-pooling).
    C, n_eff, ev = rep.return_correlation(daily_returns())
    var_infl = len(SYMS) / n_eff

    # 2) Replication grid + consistency + correlation-aware meta + cross-BH-FDR.
    er = rep.grid(tables, "expectancy_R").round(3)
    ntr = rep.grid(tables, "n_trades").astype(int)
    cons = rep.consistency(tables)
    meta = rep.meta_table(tables, var_inflation=var_infl)
    cells, n_rej, crit = rep.cross_bh_fdr(tables)

    C.to_csv(out / "correlation.csv")
    er.to_csv(out / "replication_grid_ER.csv")
    ntr.to_csv(out / "replication_grid_N.csv")
    cons.to_csv(out / "consistency.csv")
    meta.to_csv(out / "meta_random_effects.csv")
    cells.to_csv(out / "cross_cells.csv", index=False)
    stops = rep.stopout_summary(tables)
    stops.to_csv(out / "stopouts.csv")
    (out / "provenance.json").write_text(json.dumps(prov, indent=2) + "\n", encoding="utf-8")

    # within-instrument BH survivors (per instrument)
    per_inst_sig = {s: int(df["bh_reject"].astype(bool).sum()) for s, df in tables.items()}
    n_pos_sig_any = int((cons["n_pos_sig"] >= 1).sum())
    n_multi = int((cons["n_pos_sig"] >= 2).sum())

    print("=== cross-instrument daily-return correlation (IS 2015-2022) ===")
    print(C.round(2).to_string())
    print(f"\neffective # independent instruments (participation ratio): {n_eff:.2f} of {len(SYMS)} "
          f"(var inflation x{var_infl:.2f})")
    print(f"\nwithin-instrument BH-FDR survivors: {per_inst_sig}")
    print(f"configs positive-and-significant on >=1 instrument: {n_pos_sig_any}/42")
    print(f"configs positive-and-significant on >=2 instruments (replication): {n_multi}/42")
    print(f"\ncross-(config x instrument) BH-FDR: {n_rej}/{len(cells)} cells reject "
          f"(crit p={crit:.2e})")
    print("\n=== consistency (top 8 by # positive-and-significant) ===")
    print(cons.head(8).to_string())
    print("\n=== correlation-aware random-effects pool (top 6 by pooled E[R]) ===")
    print(meta.head(6)[["k", "pooled", "se", "ci_lo", "ci_hi", "p_one_sided", "I2"]].round(3).to_string())
    print("\n=== real-trade stop-outs: per-config median full stop-out R, spread across the 42 configs ===")
    print(stops.round(3).to_string())

    _write_markdown(out, tables, C, n_eff, var_infl, er, ntr, cons, meta,
                    per_inst_sig, n_pos_sig_any, n_multi, n_rej, len(cells), crit, prov)
    print(f"\nwrote {out/'*.csv'} and docs/REPLICATION.md")


def _write_markdown(out, tables, C, n_eff, var_infl, er, ntr, cons, meta,
                    per_inst_sig, n_pos_sig_any, n_multi, n_rej, n_cells, crit, prov) -> None:
    L = []
    L.append("# Multi-Instrument Replication — MTF-SMC across FX, Metals and Crude\n")
    L.append("> Per-instrument estimates, then consistency across **independent** instruments. "
             "Pooled significance is correlation-aware (deflated by the effective number of "
             "independent instruments); the primary evidence is the consistency count. "
             f"Generated by `scripts/run_replication.py` (git `{prov['git_commit']}`) from grids run "
             f"at engine code_hash `{prov['grid_code_hash']}`; inputs and hashes in "
             "`output/replication/provenance.json`.\n")

    L.append("## Headline\n")
    L.append(f"- Within-instrument BH-FDR survivors (mean R>0): "
             f"{', '.join(f'{s} {n}/42' for s, n in per_inst_sig.items())}.")
    L.append(f"- Configs **positive-and-significant on >=2 independent instruments**: "
             f"**{n_multi}/42**.")
    L.append(f"- Cross-(config x instrument) BH-FDR over all {n_cells} trials: "
             f"**{n_rej} reject** (critical p = {crit:.2e}).\n")

    L.append("## Cross-instrument correlation (daily returns, IS 2015-2022)\n")
    L.append(_md(C.round(2), "{:.2f}"))
    L.append(f"\n**Effective # independent instruments = {n_eff:.2f} of 5** "
             f"(participation ratio of the correlation eigenvalues; pooled variance inflated "
             f"x{var_infl:.2f}). EURUSD/GBPUSD/GBPJPY share USD/GBP factors; WTIUSD is the most "
             f"independent; XAUUSD moderate. **Never treat 5xN trades as independent.**\n")

    L.append("## Replication grid — per-instrument E[R] (config x instrument)\n")
    g = er.copy()
    g.insert(0, "n_pos_sig", cons.reindex(g.index)["n_pos_sig"])
    g = g.sort_values("n_pos_sig", ascending=False)
    L.append(_md(g))
    L.append("\n*(N per cell in `output/replication/replication_grid_N.csv`.)*\n")

    L.append("## Correlation-aware random-effects pool (top 8 by pooled E[R])\n")
    mt = meta.head(8)[["k", "pooled", "se", "ci_lo", "ci_hi", "p_one_sided", "I2"]].round(3)
    L.append(_md(mt))
    L.append("\n`p_one_sided` = correlation-aware one-sided p that the pooled E[R] > 0; "
             "`I2` = between-instrument heterogeneity.\n")

    L.append("## Verdict\n")
    if n_multi == 0:
        L.append("**No configuration replicates** — none is positive-and-significant on even two "
                 "independent instruments, and 0 cells survive the cross-(config x instrument) "
                 "BH-FDR. The handful of per-instrument positive point estimates are small-N noise "
                 "that regresses toward zero across assets: a **stronger, multi-asset falsification** "
                 "than the single-instrument study. No edge to carry to out-of-sample.")
    else:
        L.append(f"{n_multi} config(s) are positive-and-significant on >=2 independent instruments; "
                 f"see the meta-analysis and carry only those (and only if they survive the cross "
                 f"correction) to the conditional OOS.")
    (REPO_ROOT / "docs" / "REPLICATION.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
