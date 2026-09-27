"""results/headline.json: schema, artifacts present, and every stat traceable to its artifact.

Markdown-backed stats are either recomputed from the artifact with the repo's own code (when a
recompute is registered below) or must appear literally in it. ``provenance: reproduced`` requires a
recompute. Runs without licensed data.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest

from mtf_smc.robustness.replication import participation_ratio

ROOT = Path(__file__).resolve().parents[1]
HEADLINE = json.loads((ROOT / "results" / "headline.json").read_text(encoding="utf-8"))
TOP_KEYS = {"schema", "repo", "source_commit", "as_of", "rows"}
ROW_KEYS = {"id", "section", "hypothesis", "verdict", "verdict_detail", "mechanism", "stats", "caveats"}
STAT_KEYS = {"label", "display", "value", "artifact", "locator", "provenance"}
PROVENANCE = {"reproduced", "repo-reported, not reproduced", "predates fix; pending re-run"}
STATS = [s for r in HEADLINE["rows"] for s in r["stats"]]


def _bh_survivors(text: str, stat: dict) -> None:
    n_cells, n_rej = map(int, re.search(r"over all (\d+) trials: \*\*(\d+) reject\*\*", text).groups())
    assert stat["display"] == f"{n_rej}/{n_cells}" and stat["value"] == n_rej


def _effective_n(text: str, stat: dict) -> None:
    section = text.split("## Cross-instrument correlation", 1)[1].split("**Effective", 1)[0]
    rows = [ln for ln in section.splitlines()
            if ln.startswith("| ") and not ln.startswith(("| index", "| ---"))]
    corr = np.array([[float(x) for x in ln.strip().strip("|").split("|")[1:]] for ln in rows])
    assert corr.shape == (5, 5)
    n_eff, _ = participation_ratio(corr)
    assert stat["display"] == f"{n_eff:.2f}"
    assert stat["value"] == pytest.approx(n_eff, abs=5e-4)


RECOMPUTE = {
    "config x instrument cells surviving cross-instrument BH-FDR": _bh_survivors,
    "effective number of independent instruments": _effective_n,
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
    text = path.read_text(encoding="utf-8")
    check = RECOMPUTE.get(stat["label"])
    if stat["provenance"] == "reproduced":
        assert check is not None, "a reproduced stat needs a recompute from its artifact"
    if check is not None:
        check(text, stat)
    else:
        assert stat["display"] in text
