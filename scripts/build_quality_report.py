"""Generate per-instrument data-quality report(s) on the IN-SAMPLE data (2015-2022).

Usage:
    .venv\\Scripts\\python scripts\\build_quality_report.py                 # all 5 instruments
    .venv\\Scripts\\python scripts\\build_quality_report.py EURUSD WTIUSD   # a subset

Reads each cache via the IS loader (hard-sliced to < 2023), so this never touches the locked OOS.
XAUUSD writes docs/DATA_QUALITY.md; replication instruments write docs/DATA_QUALITY_<SYM>.md (plus
per-symbol CSVs under output/quality/<SYM>/ and a suffixed bars-per-year PNG).
"""
from __future__ import annotations

import sys

from mtf_smc.config import DataConfig
from mtf_smc.data.loader import load_is
from mtf_smc.data.quality import build_report
from mtf_smc.timeframes import TIMEFRAMES

ALL_SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "GBPJPY", "WTIUSD"]


def main() -> None:
    symbols = [a for a in sys.argv[1:] if not a.startswith("--")] or ALL_SYMBOLS
    for sym in symbols:
        cfg = DataConfig.for_symbol(sym)
        m1 = load_is(cfg, verbose=True)
        paths = build_report(m1, cfg, tfs=TIMEFRAMES, label="IN-SAMPLE (2015-2022)")
        print(f"\n[{sym}] wrote:")
        for k, v in paths.items():
            print(f"  {k:>14}: {v}")


if __name__ == "__main__":
    main()
