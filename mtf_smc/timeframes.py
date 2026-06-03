"""Canonical timeframe definitions and conversions.

A *timeframe* (TF) is a short alias in ``W1, D1, H4, H1, M15, M5, M1``. Every bar is indexed by
its **open (start) time** (see :mod:`mtf_smc.data.resample`); a bar on timeframe ``tf`` labelled
``T`` spans ``[T, T + duration(tf))`` and is *closed* only at ``T + duration(tf)``. That single
convention is the backbone of the no-look-ahead guarantees in :mod:`mtf_smc.engine.alignment`.
"""
from __future__ import annotations

import pandas as pd

# Highest -> lowest. Used for HTF/MTF/LTF ordering checks.
TIMEFRAMES: tuple[str, ...] = ("W1", "D1", "H4", "H1", "M15", "M5", "M1")

_TF_MINUTES: dict[str, int] = {
    "W1": 7 * 24 * 60,  # 10080
    "D1": 24 * 60,      # 1440
    "H4": 4 * 60,       # 240
    "H1": 60,
    "M15": 15,
    "M5": 5,
    "M1": 1,
}

# pandas resample rule per TF (used for intraday + daily, which anchor to the UTC start-of-day
# by default). W1 is NOT resampled via this rule: weekly bars are built by an explicit
# Monday-anchored grouping in :mod:`mtf_smc.data.resample`, because pandas ignores the ``origin``
# keyword for day-and-up frequencies, so a ``'7D'`` bin cannot be reliably Monday-anchored.
_TF_RULE: dict[str, str] = {
    "W1": "7D", "D1": "1D", "H4": "4h", "H1": "1h",
    "M15": "15min", "M5": "5min", "M1": "1min",
}


def is_valid_tf(tf: str) -> bool:
    """Whether ``tf`` is a recognised timeframe alias."""
    return tf in _TF_MINUTES


def _check(tf: str) -> None:
    if tf not in _TF_MINUTES:
        raise KeyError(f"Unknown timeframe {tf!r}; valid: {TIMEFRAMES}")


def tf_to_minutes(tf: str) -> int:
    """Nominal bar length in minutes (W1 = 10080)."""
    _check(tf)
    return _TF_MINUTES[tf]


def tf_duration(tf: str) -> pd.Timedelta:
    """Nominal bar length as a :class:`pandas.Timedelta` (W1 = 7 days)."""
    return pd.Timedelta(minutes=tf_to_minutes(tf))


def tf_to_pandas_freq(tf: str) -> str:
    """pandas ``resample`` rule string for ``tf``."""
    _check(tf)
    return _TF_RULE[tf]


def is_higher(tf_a: str, tf_b: str) -> bool:
    """True iff ``tf_a`` is a strictly higher (longer) timeframe than ``tf_b``."""
    return tf_to_minutes(tf_a) > tf_to_minutes(tf_b)
