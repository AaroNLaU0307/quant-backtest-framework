"""Instrument-layer generalization seam (no licensed data): per-symbol ``DataConfig`` + registry,
with the XAUUSD data path proven unperturbed by the additive ``for_symbol`` factory.

The *numeric* bit-identical proof (the full XAUUSD master table within <1e-9) needs the licensed M1
cache and runs as ``scripts/verify_xauusd_regression.py``; these fast tests pin the seam itself.
"""
from __future__ import annotations

import pytest

from mtf_smc.config import DataConfig
from mtf_smc.risk.instrument import XAUUSD, get_instrument


def test_for_symbol_xauusd_is_the_default_data_path():
    """``for_symbol("XAUUSD")`` must equal the legacy ``DataConfig()`` on every data-relevant field."""
    a, b = DataConfig(), DataConfig.for_symbol("XAUUSD")
    assert b.symbol == a.symbol == "XAUUSD"
    assert b.cache_pickle_name == a.cache_pickle_name == "XAUUSD_M1_UTC_2015_2025.pkl"
    assert b.cache_pickle == a.cache_pickle
    assert b.session_anchor == a.session_anchor == "ny_close"
    assert (b.is_start, b.oos_start, b.oos_end) == (a.is_start, a.oos_start, a.oos_end)
    assert get_instrument("XAUUSD") is XAUUSD


@pytest.mark.parametrize("sym", ["EURUSD", "GBPUSD", "GBPJPY", "WTIUSD"])
def test_for_symbol_new_instruments_resolve_distinctly(sym):
    c = DataConfig.for_symbol(sym)
    assert c.symbol == sym
    assert c.cache_pickle_name == f"{sym}_M1_UTC_2015_2023.pkl"   # 2015-2023; 2023 = their OOS
    assert c.session_anchor == "ny_close"
    assert get_instrument(sym).symbol == sym
    # new instruments must NOT collide with the XAUUSD cache
    assert c.cache_pickle != DataConfig.for_symbol("XAUUSD").cache_pickle


def test_for_symbol_overrides_pass_through():
    c = DataConfig.for_symbol("EURUSD", session_anchor="utc")
    assert c.symbol == "EURUSD" and c.session_anchor == "utc"
