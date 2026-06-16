"""POSITIVE CONTROL (baseline, not part of the SMC study): time-series momentum (TSMOM).

The one robust technical anomaly (Moskowitz-Ooi-Pedersen): the sign of the trailing return predicts
the next period, diversified across assets. Run it through the SAME data layer, the SAME per-instrument
costs, and the SAME statistics (bootstrap CI, mean>0 bootstrap p, BH-FDR) as the SMC grid, to calibrate
the apparatus's power: if even TSMOM cannot clear the bar on this universe/period, the test is just
harsh; if TSMOM shows detectable signal where SMC showed 0/42, the SMC null is real, not an artifact.

Strictly ex-ante: the signal is the trailing-L-day return sign, applied to the NEXT day (shift(1)).
Turnover costs (spread + round-turn commission) are charged on every position flip. IS 2015-2022 only.
Writes output/control/momentum.csv. Compare vs the SMC null (0/42, max DSR=0) and buy-and-hold.

    .venv\\Scripts\\python scripts\\run_momentum_control.py
"""
from __future__ import annotations

from math import sqrt

import numpy as np
import pandas as pd

from mtf_smc.config import REPO_ROOT, DataConfig
from mtf_smc.data.loader import load_is
from mtf_smc.data.resample import resample_ohlc
from mtf_smc.risk.instrument import get_instrument
from mtf_smc.robustness.stats import benjamini_hochberg, bootstrap_mean_ci, mean_positive_pvalue

SYMS = ["XAUUSD", "EURUSD", "GBPUSD", "GBPJPY", "WTIUSD"]
LOOKBACKS = {"1m": 21, "3m": 63, "6m": 126, "12m": 252}
ANN = 252


def daily(sym: str):
    c = resample_ohlc(load_is(DataConfig.for_symbol(sym)), "D1", anchor="ny_close")["close"]
    return c, c.pct_change()


def tsmom_net(sym: str, c: pd.Series, r: pd.Series, L: int) -> pd.Series:
    inst = get_instrument(sym)
    sig = np.sign(r.rolling(L).sum()).shift(1)                 # ex-ante: past-L sign, applied next day
    flip = sig.diff().abs() / 2.0                              # 1.0 on a long<->short flip
    cost = flip * (inst.base_spread_price / c
                   + inst.commission_round_turn(1.0) / (inst.contract_size * c))
    return (sig * r - cost).dropna()


def stat_row(net: pd.Series) -> dict:
    x = net.to_numpy()
    mu, lo, hi = bootstrap_mean_ci(x, n_boot=5000, seed=7)
    return dict(n=int(len(x)), ann_ret=float(net.mean() * ANN),
                sharpe=float(net.mean() / net.std() * sqrt(ANN)),
                p_value=float(mean_positive_pvalue(x, n_boot=5000, seed=7)),
                ci_lo_ann=float(lo * ANN), ci_hi_ann=float(hi * ANN))


def main() -> None:
    data = {s: daily(s) for s in SYMS}
    rows, pvals, nets = [], [], {}
    for s in SYMS:
        c, r = data[s]
        for name, L in LOOKBACKS.items():
            net = tsmom_net(s, c, r, L)
            nets[(s, name)] = net
            row = {"instrument": s, "lookback": name, **stat_row(net)}
            rows.append(row); pvals.append(row["p_value"])
    R = pd.DataFrame(rows)
    rej, crit = benjamini_hochberg(np.array(pvals), 0.05)
    R["bh_reject"] = rej

    out = REPO_ROOT / "output" / "control"; out.mkdir(parents=True, exist_ok=True)
    R.to_csv(out / "momentum.csv", index=False)

    # Diversified risk-parity TSMOM portfolio per lookback (vol-scale each instrument, equal-weight).
    print("=== TSMOM positive control (IS 2015-2022, NET of per-instrument costs) ===\n")
    print("per-instrument Sharpe by lookback:")
    piv = R.pivot(index="instrument", columns="lookback", values="sharpe")[list(LOOKBACKS)]
    print(piv.round(2).to_string())
    print(f"\nper-(instrument x lookback) cells significant after BH-FDR: {int(rej.sum())}/{len(R)} "
          f"(crit p={crit:.3f})")

    print("\ndiversified equal-risk TSMOM portfolio (the factor lives here):")
    print(f"{'lookback':9} {'ann_ret':>8} {'sharpe':>7} {'t_stat':>7} {'p_value':>8} {'95% CI (ann)':>20}")
    for name in LOOKBACKS:
        df = pd.concat({s: nets[(s, name)] for s in SYMS}, axis=1).dropna()
        port = (df / df.std()).mean(axis=1)                   # unit-vol each, equal weight
        x = port.to_numpy()
        mu, lo, hi = bootstrap_mean_ci(x, n_boot=5000, seed=7)
        sr = port.mean() / port.std() * sqrt(ANN)
        t = port.mean() / (port.std() / sqrt(len(port)))
        p = mean_positive_pvalue(x, n_boot=5000, seed=7)
        print(f"{name:9} {port.mean()*ANN:>+8.3f} {sr:>+7.2f} {t:>+7.2f} {p:>8.3f} "
              f"[{lo*ANN:+.3f}, {hi*ANN:+.3f}]")

    print("\nbuy-and-hold baseline (long-only) Sharpe:")
    print("  " + "  ".join(f"{s}={data[s][1].mean()/data[s][1].std()*sqrt(ANN):+.2f}" for s in SYMS))
    print("\nfor reference: the SMC grid was 0/42 BH survivors per instrument, 0/210 cross, max DSR=0.")


if __name__ == "__main__":
    main()
