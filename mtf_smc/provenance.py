"""Run provenance: which code and which configuration produced an output row.

Every result row written by the grid, walk-forward and random-entry runners carries three columns:

* ``git_commit`` — ``HEAD`` of this repository, suffixed ``-dirty`` when tracked files differ from it
  (``unknown`` outside a git checkout);
* ``code_hash`` — sha256 (16 hex) over the ``mtf_smc`` package sources, so rows produced by different
  engine code can never be mixed silently (a documentation commit leaves it unchanged);
* ``config_hash`` — sha256 (16 hex) of the JSON of the configuration objects that shaped the row
  (strategy config, instrument spec, cost model, runner parameters).

Resumable runners refuse to append to an output whose ``code_hash`` / ``config_hash`` differ from the
current ones; rerun them with ``fresh``.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import subprocess
from functools import lru_cache
from typing import Any

from mtf_smc.config import REPO_ROOT

PROVENANCE_COLUMNS = ("git_commit", "code_hash", "config_hash")


def _git(*args: str) -> str:
    out = subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True, check=True)
    return out.stdout.strip()


@lru_cache(maxsize=1)
def git_commit() -> str:
    """``HEAD`` sha (``-dirty`` if tracked files are modified); ``unknown`` if git is unavailable."""
    try:
        sha = _git("rev-parse", "HEAD")
        dirty = _git("status", "--porcelain", "--untracked-files=no")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return sha + ("-dirty" if dirty else "")


@lru_cache(maxsize=1)
def code_hash() -> str:
    """sha256 (first 16 hex) over every ``mtf_smc/**/*.py`` (path + LF-normalised content)."""
    h = hashlib.sha256()
    for path in sorted((REPO_ROOT / "mtf_smc").rglob("*.py")):
        h.update(path.relative_to(REPO_ROOT).as_posix().encode())
        h.update(b"\0")
        h.update(path.read_bytes().replace(b"\r\n", b"\n"))
        h.update(b"\0")
    return h.hexdigest()[:16]


def _plain(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {"__type__": type(obj).__name__, **dataclasses.asdict(obj)}
    return obj


def config_hash(*parts: Any) -> str:
    """sha256 (first 16 hex) of the canonical JSON of ``parts`` (dataclasses, dicts, scalars)."""
    blob = json.dumps([_plain(p) for p in parts], sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def provenance(*parts: Any) -> dict[str, str]:
    """The three provenance columns for a row shaped by ``parts``."""
    return {"git_commit": git_commit(), "code_hash": code_hash(), "config_hash": config_hash(*parts)}
