"""results/headline.json: schema, artifacts present, and every stat traceable to its artifact.

Each stat is either recomputed from its artifact with the repo's own code (when a recompute is
registered below) or must appear literally in it. ``provenance: reproduced`` requires a recompute. The
CSV artifacts are the derived statistics committed after the re-run (``.gitignore`` admits them); no
licensed data is read.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mtf_smc.robustness.replication import participation_ratio
from mtf_smc.robustness.stats import benjamini_hochberg, block_bootstrap_mean_ci
from mtf_smc.robustness.walkforward import period_sign_test

ROOT = Path(__file__).resolve().parents[1]
HEADLINE = json.loads((ROOT / "results" / "headline.json").read_text(encoding="utf-8"))
TOP_KEYS = {"schema", "repo", "source_commit", "as_of", "rows"}
ROW_KEYS = {"id", "section", "hypothesis", "verdict", "verdict_detail", "mechanism", "stats", "caveats"}
STAT_KEYS = {"label", "display", "value", "artifact", "locator", "provenance"}
PROVENANCE = {"reproduced", "repo-reported, not reproduced", "predates fix; pending re-run"}
STATS = [s for r in HEADLINE["rows"] for s in r["stats"]]


MINUS = "−"


def _fmt(x: float, nd: int) -> str:
    return f"{x:+.{nd}f}".replace("-", MINUS).lstrip("+")


def _bh_survivors(path: Path, stat: dict) -> None:
    cells = pd.read_csv(path)
    reject, _ = benjamini_hochberg(cells["p_value"].fillna(1.0).to_numpy(), 0.05)
    assert stat["display"] == f"{int(reject.sum())}/{len(cells)}" and stat["value"] == int(reject.sum())


def _replicating_configs(path: Path, stat: dict) -> None:
    cons = pd.read_csv(path)
    n = int((cons["n_pos_sig"] >= 2).sum())
    assert stat["display"] == f"{n}/{len(cons)}" and stat["value"] == n


def _effective_n(path: Path, stat: dict) -> None:
    corr = pd.read_csv(path, index_col=0).to_numpy()
    assert corr.shape == (5, 5)
    n_eff, _ = participation_ratio(corr)
    assert stat["display"] == f"{n_eff:.2f}"
    assert stat["value"] == pytest.approx(n_eff, abs=5e-3)


def _wf_windows(path: Path) -> tuple[pd.DataFrame, list]:
    df = pd.read_csv(path)
    assert len(df) == 24
    return df, [np.asarray(json.loads(s), dtype=float) for s in df["oos_R_json"]]


def _wf_pooled_er(path: Path, stat: dict) -> None:
    _, arrays = _wf_windows(path)
    mean = float(np.concatenate(arrays).mean())
    assert stat["display"] == f"{_fmt(mean, 3)} R"
    assert stat["value"] == pytest.approx(mean, abs=5e-4)


def _wf_block_ci(path: Path, stat: dict) -> None:
    _, arrays = _wf_windows(path)
    lo, hi = block_bootstrap_mean_ci([a for a in arrays if a.size])
    assert stat["display"] == f"[{_fmt(lo, 3)}, {_fmt(hi, 3)}]"


def _wf_sign_test(path: Path, stat: dict) -> None:
    df, _ = _wf_windows(path)
    st = period_sign_test(df)
    assert stat["display"] == f"{st['n_negative']}/{st['n_periods']} (one-sided p = {st['p_value']:.4f})"
    assert stat["value"] == st["n_negative"]


RECOMPUTE = {
    "config x instrument cells surviving cross-instrument BH-FDR": _bh_survivors,
    "configs positive-and-significant on >= 2 instruments": _replicating_configs,
    "effective number of independent instruments": _effective_n,
    "L1 walk-forward pooled OOS E[R]": _wf_pooled_er,
    "L1 walk-forward window-block 95% CI": _wf_block_ci,
    "L1 walk-forward calendar OOS periods with E[R] < 0": _wf_sign_test,
}


def test_schema():
    assert set(HEADLINE) == TOP_KEYS
    assert HEADLINE["schema"] == "headline/v1" and HEADLINE["as_of"] == "2026-09-27"
    assert HEADLINE["source_commit"] == "PENDING" or re.fullmatch(r"[0-9a-f]{40}", HEADLINE["source_commit"])
    for row in HEADLINE["rows"]:
        assert set(row) == ROW_KEYS and row["section"] in ("archive", "other")
        assert isinstance(row["caveats"], list)
        for stat in row["stats"]:
            assert set(stat) == STAT_KEYS and stat["provenance"] in PROVENANCE
            assert stat["value"] is None or isinstance(stat["value"], (int, float))


@pytest.mark.parametrize("stat", STATS, ids=lambda s: s["label"])
def test_stat_traces_to_artifact(stat):
    path = ROOT / stat["artifact"]
    assert path.is_file(), stat["artifact"]
    check = RECOMPUTE.get(stat["label"])
    if stat["provenance"] == "reproduced":
        assert check is not None, "a reproduced stat needs a recompute from its artifact"
    if check is not None:
        check(path, stat)
    else:
        assert stat["display"] in path.read_text(encoding="utf-8")
