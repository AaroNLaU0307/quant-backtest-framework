"""One driver for the whole study: data check -> 5 grids -> replication -> L1 walk-forward -> report.

Runs every stage from scratch (``fresh``: no row from an earlier run is reused) in the order the results
depend on each other. Each stage is a separate process, so the multi-gigabyte M1 contexts of one grid
are released before the next starts. Every result row carries ``git_commit`` / ``code_hash`` /
``config_hash`` (:mod:`mtf_smc.provenance`); ``output/data_manifest.csv`` records a content hash of
each instrument's in-sample M1 frame.

Needs ``mtf_smc`` importable (``pip install -e . --no-deps`` or ``PYTHONPATH=<repo root>``), like
every script here.

    python scripts/run_all.py                          # everything (many hours)
    python scripts/run_all.py --stages=check,grids     # a subset, in pipeline order
    python scripts/run_all.py --dry-run                # print the commands only

Stages (default = all but ``stopslip``):
  check        in-sample M1 caches for the 5 instruments -> output/data_manifest.csv
  grids        scripts/run_grid.py fresh --symbol=<SYM> for XAUUSD EURUSD GBPUSD GBPJPY WTIUSD
  replication  scripts/run_replication.py (+ stopouts.csv, provenance.json, docs/REPLICATION.md)
  walkforward  scripts/run_legacy_walkforward.py fresh (L1, XAUUSD + EURUSD)
  wf_report    scripts/run_legacy_walkforward_report.py
  robustness   scripts/run_robustness.py 1000 (L3 random-entry nulls, XAUUSD survivors)
  figures      scripts/make_replication_figure.py and scripts/make_figures.py (assets/*.png)
  stopslip     optional: the high-slippage-on-stops grids (stop slippage x10) on XAUUSD, GBPJPY, WTIUSD

A committed ``output/data_manifest.csv`` pins the data: if an in-sample frame hashes differently, the
check stage stops (pass ``--allow-data-change`` to overwrite the manifest deliberately).
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import time

import numpy as np
import pandas as pd

from mtf_smc.config import REPO_ROOT, DataConfig
from mtf_smc.data.loader import load_is
from mtf_smc.provenance import code_hash, git_commit
from mtf_smc.robustness.replication import SYMBOLS

STAGES = ("check", "grids", "replication", "walkforward", "wf_report", "robustness", "figures", "stopslip")
DEFAULT_STAGES = STAGES[:-1]
MANIFEST = REPO_ROOT / "output" / "data_manifest.csv"
N_NULL = 1000                      # report-grade random-entry nulls (docs/SPEC.md §8: >= 1000)
STOPSLIP_SYMBOLS = ("XAUUSD", "GBPJPY", "WTIUSD")   # SPEC §6.5 (gold) + SPEC_multi_instrument §6


def frame_sha256(df: pd.DataFrame) -> str:
    """Content hash of an OHLC frame: int64 ns timestamps + float64 OHLC (independent of pickling)."""
    h = hashlib.sha256()
    h.update(np.ascontiguousarray(df.index.as_unit("ns").asi8).tobytes())
    h.update(np.ascontiguousarray(df[["open", "high", "low", "close"]].to_numpy(dtype="float64")).tobytes())
    return h.hexdigest()


def check_data(allow_change: bool) -> None:
    rows = []
    for sym in SYMBOLS:
        cfg = DataConfig.for_symbol(sym)
        if not cfg.cache_pickle.exists():
            raise SystemExit(f"missing M1 cache {cfg.cache_pickle} — build it first "
                             f"(scripts/ingest_instruments.py; XAUUSD: docs/SPEC.md §1.5).")
        m1 = load_is(cfg)
        rows.append({"symbol": sym, "cache_file": cfg.cache_pickle.name, "is_bars": len(m1),
                     "is_first": str(m1.index[0]), "is_last": str(m1.index[-1]), "is_sha256": frame_sha256(m1)})
        print(f"[check] {sym}: {len(m1):,} IS bars {m1.index[0]} -> {m1.index[-1]}", flush=True)
    new = pd.DataFrame(rows)
    if MANIFEST.exists():
        old = pd.read_csv(MANIFEST).set_index("symbol")["is_sha256"]
        changed = [r["symbol"] for r in rows if old.get(r["symbol"]) != r["is_sha256"]]
        if changed and not allow_change:
            raise SystemExit(f"in-sample data differ from {MANIFEST.name} for {changed}; "
                             f"pass --allow-data-change to accept and overwrite the manifest.")
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    new.to_csv(MANIFEST, index=False)
    print(f"[check] wrote {MANIFEST}", flush=True)


def _script(name: str) -> str:
    return str(REPO_ROOT / "scripts" / name)


def commands(stage: str) -> list:
    py, s = sys.executable, _script
    if stage == "grids":
        return [[py, s("run_grid.py"), "fresh", f"--symbol={sym}"] for sym in SYMBOLS]
    if stage == "replication":
        return [[py, s("run_replication.py")]]
    if stage == "walkforward":
        return [[py, s("run_legacy_walkforward.py"), "fresh"]]
    if stage == "wf_report":
        return [[py, s("run_legacy_walkforward_report.py")]]
    if stage == "robustness":
        return [[py, s("run_robustness.py"), str(N_NULL)]]
    if stage == "figures":
        return [[py, s("make_replication_figure.py")], [py, s("make_figures.py")]]
    if stage == "stopslip":
        return [[py, s("run_grid.py"), "fresh", f"--symbol={sym}", "--stop-slip-mult=10"]
                for sym in STOPSLIP_SYMBOLS]
    raise ValueError(stage)


def main() -> None:
    args = sys.argv[1:]
    chosen = next((a.split("=", 1)[1].split(",") for a in args if a.startswith("--stages=")), DEFAULT_STAGES)
    unknown = sorted(set(chosen) - set(STAGES))
    if unknown:
        raise SystemExit(f"unknown stage(s) {unknown}; valid: {', '.join(STAGES)}")
    dry = "--dry-run" in args
    print(f"run_all: git_commit={git_commit()} code_hash={code_hash()} stages={[s for s in STAGES if s in chosen]}",
          flush=True)
    for stage in (s for s in STAGES if s in chosen):          # always pipeline order
        t0 = time.time()
        if stage == "check":
            if dry:
                print("[check] load each IS cache, hash it, write output/data_manifest.csv")
            else:
                check_data("--allow-data-change" in args)
            continue
        for cmd in commands(stage):
            print(f"[{stage}] $ {' '.join(cmd)}", flush=True)
            if not dry:
                subprocess.run(cmd, check=True, cwd=REPO_ROOT)
        print(f"[{stage}] done in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
