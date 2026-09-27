"""Hash-pin the statistics helpers so no inference routine changes silently.

``mtf_smc/robustness/stats.py`` is this repository's own code (not vendored). Each helper's source
(``inspect.getsource``, trailing whitespace stripped per line) is pinned by sha256 below. Changing a
helper is allowed, but the change must be deliberate: update the hash here in the same commit and say
why in its message.
"""
from __future__ import annotations

import hashlib
import inspect

from mtf_smc.robustness import stats

PINNED = {
    "benjamini_hochberg": "e76459744cdcc9c5bb9bc9cd18981da2dd1e05089ec466f7f05e21ff82146feb",
    "block_bootstrap_mean_ci": "5362ab6f34635badfc4a6ed646d9dd078363f6d152012154997ae58a9b2350dc",
    "bootstrap_mean_ci": "a67e4ec6128a2f0673598c9281cbd87984d5a815ee12a061c8d5fc10577ab8c9",
    "deflated_sharpe_ratio": "2cdf224a311d60f3ee5fb28252adfb423b8692e4c0b37122b79ba2a707668cea",
    "drop_one_expectancy": "c2020eeffc6cfe6d1adf14137690376e08a679e1ca3a76bd23881a42a76d61d5",
    "expected_max_sharpe": "cbc0e02801b7cba72d31ff55dbbc2cf8e69f58d5957c6d8c8e4f5c778f41f841",
    "mean_positive_pvalue": "7f4491c4174feb3e12236808cc591c41f96e9a641521bbd36b8558c89a479ccd",
    "probabilistic_sharpe_ratio": "dd611e014f8211dc43882d5b2d29ea5e11e73b221b4b6959a5d046c5c07eecf6",
    "sharpe_inputs_from_equity": "ecce90da8c5ec47386d1fa4cc9b166a5e856b0598962042335bfc7f50dc9173a",
    "sign_test_pvalue": "cb2060050a2822a80cf9e8409eead757904c9e0eff3899ff47baddad705d2aa8",
    "ttest_mean_positive_pvalue": "8be38fa5f017ab02b200d1ed63a4213387971b4c93a13f7d997d3fc26d0dea95",
}


def _helpers():
    return {n: f for n, f in inspect.getmembers(stats, inspect.isfunction) if f.__module__ == stats.__name__}


def _sha(fn) -> str:
    src = "\n".join(line.rstrip() for line in inspect.getsource(fn).splitlines())
    return hashlib.sha256(src.encode()).hexdigest()


def test_every_helper_is_pinned():
    assert set(_helpers()) == set(PINNED)


def test_helper_sources_match_pinned_hashes():
    drift = {n: _sha(f) for n, f in _helpers().items() if _sha(f) != PINNED.get(n)}
    assert not drift, f"stats helper(s) changed; update PINNED deliberately: {drift}"


def test_documented_conventions_match_code():
    assert inspect.signature(stats.benjamini_hochberg).parameters["alpha"].default == 0.05
    assert "alpha = 0.05" in stats.__doc__
    assert inspect.signature(stats.bootstrap_mean_ci).parameters["n_boot"].default == 10_000
    assert inspect.signature(stats.block_bootstrap_mean_ci).parameters["seed"].default == 7
