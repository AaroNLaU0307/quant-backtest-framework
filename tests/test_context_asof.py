"""The optimized as-of lookups must equal the brute-force linear scans (no behaviour change)."""
from __future__ import annotations

from mtf_smc.config import StrategyConfig
from mtf_smc.strategy.context import _assoc_fvg, build_tf_view


def _view(is_m1):
    return build_tf_view(is_m1.loc["2018-01-01":"2018-06-30"], "H1", StrategyConfig())


def test_assoc_fvg_matches_bruteforce(is_m1):
    view = _view(is_m1)
    win = StrategyConfig().fvg_assoc_window
    for e in view.structure:
        fast = view.assoc_fvg(e.index, e.direction, win)
        slow = _assoc_fvg(view.fvgs, e.index, e.direction, win)
        assert (fast is None) == (slow is None)
        if fast is not None:
            assert fast.confirm_index == slow.confirm_index and fast.lower == slow.lower


def test_latest_structure_with_fvg_matches_bruteforce(is_m1):
    view = _view(is_m1)
    win = StrategyConfig().fvg_assoc_window

    def brute(ts, d):
        out = None
        for e in view.structure:
            if view.close_time(e.index) > ts:
                break
            if e.direction == d and _assoc_fvg(view.fvgs, e.index, d, win) is not None:
                out = e
        return out

    for ts in view.df.index[::40]:
        for d in ("long", "short"):
            fast = view.latest_structure_with_fvg(ts, d)
            slow = brute(ts, d)
            assert (fast is None) == (slow is None)
            if fast is not None:
                assert fast.index == slow.index
