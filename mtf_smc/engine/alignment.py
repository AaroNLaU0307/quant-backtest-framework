"""No-look-ahead multi-timeframe alignment — the structural guarantee that a decision made at
time ``t`` sees only higher-timeframe bars that have **already closed** by ``t``.

Two complementary primitives (ported from the verified V2 ``data_handler``):

* :func:`closed_asof` — given a higher-TF frame (bar-start index), return only bars whose close
  time ``bar_start + duration(tf)`` is ``<= t``. The event loop fetches this as-of slice.
* :func:`align_shift` — vectorized counterpart: shift a higher-TF series by one bar and
  forward-fill onto a lower-TF index, so LTF bar ``t`` only ever sees an already-closed HTF bar.

Both are *exactly* aligned at close boundaries: a higher-TF bar spanning ``[T, T+dur)`` (label
``T``, closing at ``T+dur``) first becomes visible at ``t = T+dur`` and not one tick earlier.
"""
from __future__ import annotations

from typing import Optional, Sequence

import pandas as pd

from mtf_smc.timeframes import tf_duration


def closed_asof(frame: pd.DataFrame, tf: str, ts: pd.Timestamp) -> pd.DataFrame:
    """Rows of ``frame`` (a full TF series, bar-start index) that are fully closed at ``ts``.

    A bar's close is the **start of the next bar** (sessions are contiguous during trading); the
    final bar falls back to ``start + duration(tf)``. Using the next bar's start makes this exact
    under variable-length sessions (e.g. DST-affected 23h/25h NY days, where a nominal 24h would be
    off by an hour). A bar is kept iff its close ``<= ts`` — never any future leakage.
    """
    if frame.empty:
        return frame
    last_close = frame.index[-1] + tf_duration(tf)
    close_times = frame.index[1:].append(pd.DatetimeIndex([last_close]))
    return frame[close_times <= ts]


def latest_closed(frame: pd.DataFrame, tf: str, ts: pd.Timestamp) -> Optional[pd.Series]:
    """The single most recent fully-closed bar at ``ts``, or ``None`` if none has closed yet."""
    sl = closed_asof(frame, tf, ts)
    return None if sl.empty else sl.iloc[-1]


def align_shift(
    htf_frame: pd.DataFrame,
    ltf_index: pd.DatetimeIndex,
    columns: Optional[Sequence[str]] = None,
    prefix: str = "",
    shift: int = 1,
) -> pd.DataFrame:
    """Right-align HTF columns onto an LTF index without look-ahead.

    Shift the HTF frame by ``shift`` bars (default 1) then reindex + forward-fill onto
    ``ltf_index``. Because the HTF index is the bar *start*, the shift is what prevents reading an
    in-progress bar: at an LTF timestamp inside HTF bar ``[T, T+dur)`` the aligned value is the
    prior (already-closed) HTF bar. Columns get an optional ``prefix_``.
    """
    cols = list(columns) if columns is not None else list(htf_frame.columns)
    shifted = htf_frame[cols].shift(shift)
    aligned = shifted.reindex(ltf_index, method="ffill")
    if prefix:
        aligned.columns = [f"{prefix}_{c}" for c in cols]
    return aligned
