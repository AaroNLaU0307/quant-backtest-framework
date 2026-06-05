"""Ingest the replication instruments' HistData XLSX zips -> per-symbol M1 UTC caches.

Source: a folder of ``HISTDATA_COM_XLSX_<SYM>_M1<YEAR>.zip`` (each holding one ``DAT_XLSX_*.xlsx``),
default ``../trade log`` (override with ``$SMC_RAW_ZIP_DIR``). The ``.xlsx`` is read straight from
the zip via an in-memory buffer and pushed through the **verified loader normalization**
(``read_year_xlsx`` + fixed-EST->UTC + ``normalize_ohlc`` integrity gate) — no silent re-derivation,
identical treatment to the XAUUSD feed.

    python scripts/ingest_instruments.py                  # all four, skip existing caches
    python scripts/ingest_instruments.py EURUSD GBPUSD    # subset
    python scripts/ingest_instruments.py --force WTIUSD   # rebuild
    python scripts/ingest_instruments.py smoke EURUSD 2015  # read one year, print diagnostics, no write

Writes ``data_cache/<SYM>_M1_UTC_2015_2023.pkl`` (2023 = each instrument's OOS). Idempotent/resumable.
"""
from __future__ import annotations

import io
import os
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd

from mtf_smc.config import REPO_ROOT, DataConfig
from mtf_smc.data.loader import EST_FIXED, normalize_ohlc, read_year_xlsx

SYMBOLS = ["EURUSD", "GBPUSD", "GBPJPY", "WTIUSD"]
YEARS = list(range(2015, 2024))  # 2015..2023 inclusive (2023 is the locked OOS year)
DEFAULT_ZIP_DIR = REPO_ROOT.parent / "trade log"


def _zip_path(zip_dir: Path, symbol: str, year: int) -> Path:
    return zip_dir / f"HISTDATA_COM_XLSX_{symbol}_M1{year}.zip"


def read_year_zip(zip_dir: Path, symbol: str, year: int) -> pd.DataFrame:
    """Read one year's ``.xlsx`` directly out of its zip -> naive-EST-indexed OHLC frame."""
    zp = _zip_path(zip_dir, symbol, year)
    if not zp.exists():
        raise FileNotFoundError(f"missing zip: {zp}")
    with zipfile.ZipFile(zp) as zf:
        members = [n for n in zf.namelist() if n.lower().endswith(".xlsx")]
        if not members:
            raise FileNotFoundError(f"no .xlsx inside {zp} (has {zf.namelist()})")
        data = zf.read(members[0])
    return read_year_xlsx(io.BytesIO(data))   # loader's verified reader accepts a buffer


def build_symbol(symbol: str, zip_dir: Path, force: bool) -> Path:
    cfg = DataConfig.for_symbol(symbol)
    out = cfg.cache_pickle
    if out.exists() and not force:
        print(f"[{symbol}] cache exists -> {out.name} (skip; --force to rebuild)", flush=True)
        return out
    frames = []
    for y in YEARS:
        t0 = time.time()
        fy = read_year_zip(zip_dir, symbol, y)
        frames.append(fy)
        print(f"[{symbol}] {y}: {len(fy):>7,} M1 bars ({time.time() - t0:.1f}s)", flush=True)
    raw = pd.concat(frames, axis=0)
    raw = raw[~raw.index.duplicated(keep="first")].sort_index()
    raw.index = raw.index.tz_localize(EST_FIXED).tz_convert("UTC")   # fixed EST -> UTC
    df = normalize_ohlc(raw)                                         # integrity gate (no repair)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_pickle(out)
    print(f"[{symbol}] wrote {out.name}: {len(df):,} bars {df.index[0]} -> {df.index[-1]}", flush=True)
    if symbol == "WTIUSD":   # documented data-quality landmine
        apr = df.loc["2020-04-01":"2020-04-30"]
        print(f"[{symbol}] April-2020 check: low={apr['low'].min():.3f} high={apr['high'].max():.3f} "
              f"bars={len(apr):,}  (expect ~$6.5 low, zero negatives)", flush=True)
    return out


def main() -> None:
    args = sys.argv[1:]
    zdir = Path(os.environ.get("SMC_RAW_ZIP_DIR", DEFAULT_ZIP_DIR))

    if args and args[0] == "smoke":
        sym = args[1] if len(args) > 1 else "EURUSD"
        yr = int(args[2]) if len(args) > 2 else 2015
        df = read_year_zip(zdir, sym, yr)
        print(f"[smoke {sym} {yr}] {len(df):,} rows; cols={list(df.columns)}; "
              f"index {df.index[0]} -> {df.index[-1]} (naive EST)")
        print(df.head(3).to_string())
        print("min/max:\n" + df.describe().loc[["min", "max"]].to_string())
        return

    force = "--force" in args
    syms = [a for a in args if not a.startswith("--")] or SYMBOLS
    print(f"ingest {syms} from {zdir} (force={force})", flush=True)
    for s in syms:
        build_symbol(s, zdir, force)
    print("ingest done", flush=True)


if __name__ == "__main__":
    main()
