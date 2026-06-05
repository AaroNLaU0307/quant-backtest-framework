"""Bit-identical regression check: regenerated XAUUSD master table vs the committed reference.

The instrument-layer generalization must not perturb the XAUUSD result. This aligns two master
tables on ``config_id`` (order-independent) and asserts every numeric column matches within ``tol``
(default 1e-9), with identical config sets and NaN patterns. Exits nonzero on any mismatch.
(Licensed-data run; not a CI test.)

    python scripts/verify_xauusd_regression.py \\
        output/grid/master_table_REFERENCE.csv output/grid/master_table.csv [tol]
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd


def compare(ref_path: str, new_path: str, tol: float = 1e-9) -> bool:
    ref = pd.read_csv(ref_path).set_index("config_id").sort_index()
    new = pd.read_csv(new_path).set_index("config_id").sort_index()

    if set(ref.index) != set(new.index):
        print(f"FAIL config_id set differs: only_ref={sorted(set(ref.index) - set(new.index))} "
              f"only_new={sorted(set(new.index) - set(ref.index))}")
        return False
    new = new.loc[ref.index]

    ok = True
    max_diff = 0.0
    for col in ref.columns:
        if col not in new.columns:
            print(f"FAIL column missing in new: {col}")
            ok = False
            continue
        rc, nc = ref[col], new[col]
        if pd.api.types.is_numeric_dtype(rc) and pd.api.types.is_numeric_dtype(nc):
            a, b = rc.to_numpy(float), nc.to_numpy(float)
            nan_mismatch = np.isnan(a) ^ np.isnan(b)
            if nan_mismatch.any():
                print(f"FAIL {col}: NaN pattern differs at {list(ref.index[nan_mismatch])}")
                ok = False
            d = np.where(np.isnan(a) & np.isnan(b), 0.0, np.abs(a - b))
            d = np.nan_to_num(d, nan=0.0)
            cd = float(d.max()) if d.size else 0.0
            max_diff = max(max_diff, cd)
            if cd > tol:
                i = int(d.argmax())
                print(f"FAIL {col}: max|diff|={cd:.3e} > {tol:.0e} "
                      f"({ref.index[i]}: {a[i]!r} vs {b[i]!r})")
                ok = False
        else:
            mism = rc.astype(str).to_numpy() != nc.astype(str).to_numpy()
            if mism.any():
                print(f"FAIL {col}: {int(mism.sum())} non-numeric cells differ "
                      f"(e.g. {ref.index[mism][0]}: {rc[mism].iloc[0]!r} vs {nc[mism].iloc[0]!r})")
                ok = False

    print(f"max numeric |diff| = {max_diff:.3e} over {len(ref)} configs x {len(ref.columns)} cols")
    return ok


def main() -> None:
    args = sys.argv[1:]
    ref = args[0] if len(args) > 0 else "output/grid/master_table_REFERENCE.csv"
    new = args[1] if len(args) > 1 else "output/grid/master_table.csv"
    tol = float(args[2]) if len(args) > 2 else 1e-9
    print(f"comparing NEW {new}  vs  REF {ref}  (tol={tol:.0e})")
    ok = compare(ref, new, tol)
    print("RESULT:", "BIT-IDENTICAL within tol" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
