"""Ingest the 2024-2025 MetaTrader M1 zips and build the full sealed 2015-2025 UTC cache.

The 2015-2023 portion is copied verbatim from the existing pickle (so the in-sample slice stays
bit-identical); 2024-2025 come from the HistData MT CSVs (fixed EST -> UTC). Prints an OOS data-quality
summary (counts/gaps/integrity) -- **data hygiene only; no strategy is run on the OOS** (it stays
locked until the step-6 one-shot).

Usage:  .venv\\Scripts\\python scripts\\ingest_oos_data.py ["C:\\path\\to\\zip dir"]
"""
from __future__ import annotations

import os
import sys
import zipfile

import pandas as pd

from mtf_smc.config import DataConfig
from mtf_smc.data.loader import EST_FIXED, normalize_ohlc, read_mt_csv
from mtf_smc.data.quality import gap_stats, integrity_summary

ZIP_DIR = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\Aaron\Downloads\trade log"
MT_YEARS = [2024, 2025]


def load_mt_year(zip_dir: str, year: int) -> pd.DataFrame:
    zp = os.path.join(zip_dir, f"HISTDATA_COM_MT_XAUUSD_M1{year}.zip")
    with zipfile.ZipFile(zp) as z:
        csv_name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        with z.open(csv_name) as f:
            raw = read_mt_csv(f)
    raw.index = raw.index.tz_localize(EST_FIXED).tz_convert("UTC")   # fixed EST -> UTC
    return normalize_ohlc(raw)


def main() -> None:
    cfg = DataConfig()
    seed_pkl = cfg.data_cache_dir / "XAUUSD_M1_UTC_2015_2023.pkl"
    existing = normalize_ohlc(pd.read_pickle(seed_pkl))
    print(f"existing cache: {len(existing):,} bars  {existing.index[0]} -> {existing.index[-1]}")

    frames = [existing]
    for y in MT_YEARS:
        df = load_mt_year(ZIP_DIR, y)
        print(f"MT {y}: {len(df):,} bars  {df.index[0]} -> {df.index[-1]}")
        frames.append(df)

    full = pd.concat(frames).sort_index()
    full = normalize_ohlc(full[~full.index.duplicated(keep="first")])
    out = cfg.data_cache_dir / "XAUUSD_M1_UTC_2015_2025.pkl"
    full.to_pickle(out)
    print(f"\nwrote {out.name}: {len(full):,} bars  {full.index[0]} -> {full.index[-1]}")

    # IS portion must be unchanged vs the seed (the wall stays intact).
    is_old = existing.loc[existing.index < cfg.oos_start]
    is_new = full.loc[full.index < cfg.oos_start]
    print(f"IS (<2023) bit-identical to seed: {is_old.equals(is_new)}")

    # OOS data hygiene only (no strategy).
    oos = full.loc[full.index >= cfg.oos_start]
    print("\nOOS (2023-2025) per-year M1 bars:")
    print(oos.groupby(oos.index.year).size().to_string())
    print(f"\nlast 2023 bar : {existing.index[-1]}")
    print(f"first 2024 bar: {full.loc['2024-01-01':].index[0]}")
    print("\nOOS integrity:", integrity_summary(oos))
    gs = gap_stats(oos)
    print(f"OOS gaps: intrabar>5m={gs.intrabar_gt_5min}, weekend>24h={gs.weekend_gt_24h}, "
          f"max={gs.max_gap_hours:.1f}h @ {gs.max_gap_at}")


if __name__ == "__main__":
    main()
