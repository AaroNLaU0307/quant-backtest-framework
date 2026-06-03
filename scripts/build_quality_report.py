"""Generate the XAUUSD data-quality report on the IN-SAMPLE data (2015-2022).

Usage:
    .venv\\Scripts\\python scripts\\build_quality_report.py

Reads the seeded cache via the IS loader (hard-sliced to < 2023), so this never touches the
locked OOS. Writes docs/DATA_QUALITY.md, output/quality/*.csv, assets/*.png.
"""
from __future__ import annotations

from mtf_smc.config import DataConfig
from mtf_smc.data.loader import load_is
from mtf_smc.data.quality import build_report
from mtf_smc.timeframes import TIMEFRAMES


def main() -> None:
    cfg = DataConfig()
    m1 = load_is(cfg, verbose=True)
    paths = build_report(m1, cfg, tfs=TIMEFRAMES, label="IN-SAMPLE (2015-2022)")
    print("\nwrote:")
    for k, v in paths.items():
        print(f"  {k:>14}: {v}")


if __name__ == "__main__":
    main()
