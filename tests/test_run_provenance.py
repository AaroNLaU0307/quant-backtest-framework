"""Run provenance that must survive a checkout (addendum §12).

* ``output/replication/provenance.json`` records a sha256 per master table; it must be reproducible from
  the committed (LF) tables, whatever line endings the run wrote them with.
* ``scripts/run_all.py`` must run every row-stamping stage before the stages that rewrite tracked files,
  so one call cannot stamp rows ``-dirty``.

Runs without licensed data.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_table_sha256_ignores_line_endings(tmp_path):
    rr = _load("run_replication")
    lf, crlf = tmp_path / "lf.csv", tmp_path / "crlf.csv"
    lf.write_bytes(b"a,b\n1,2\n")
    crlf.write_bytes(b"a,b\r\n1,2\r\n")
    assert rr.table_sha256(lf) == rr.table_sha256(crlf) == hashlib.sha256(b"a,b\n1,2\n").hexdigest()


def test_committed_provenance_reproduces_from_the_committed_tables():
    prov_path = ROOT / "output" / "replication" / "provenance.json"
    if not prov_path.is_file():
        pytest.skip("no committed replication provenance")
    rr = _load("run_replication")
    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    for sym, entry in prov["inputs"].items():
        assert rr.table_sha256(rr._table_path(sym)) == entry["sha256"], sym


def test_run_all_stamps_every_row_before_rewriting_tracked_files():
    ra = _load("run_all")
    order = {s: i for i, s in enumerate(ra.STAGES)}
    assert set(ra.ROW_STAMPING_STAGES) | set(ra.TRACKED_WRITING_STAGES) <= set(ra.STAGES)
    assert max(order[s] for s in ra.ROW_STAMPING_STAGES) < min(order[s] for s in ra.TRACKED_WRITING_STAGES)
    assert "stopslip" not in ra.DEFAULT_STAGES and set(ra.DEFAULT_STAGES) == set(ra.STAGES) - {"stopslip"}
