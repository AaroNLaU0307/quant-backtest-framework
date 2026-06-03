"""Fibonacci impulse leg — discount/premium entry zones and extension targets.

Disambiguates the discount/premium anchor exactly (``docs/SPEC.md`` §2.2). For a **long** leg the
protected extreme is the low and the impulse extreme the high; for a **short** leg they swap.

* ``depth(price)`` = fractional retracement from the impulse extreme: 0 at the extreme, 1 at the
  protected end, **0.5 = equilibrium**. Deeper (closer to the protected end) ⇒ larger depth.
* ``in_entry_zone(price, t)`` ⇔ price is within the leg and ``depth >= t`` (long: discount;
  short: premium). ``t=0.5`` is equilibrium; ``t=0.618`` is the deeper OTE.
* ``extension(e)`` projects beyond the impulse extreme for targets (e.g. 1.618, 4.236).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class FibLeg:
    """An impulse leg. ``low``/``high`` are the leg extremes (always ``low <= high``)."""

    direction: str  # 'long' | 'short'
    low: float
    high: float
    low_index: int
    high_index: int

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def origin_index(self) -> int:
        """Index of the leg's start bar (long: the low; short: the high)."""
        return self.low_index if self.direction == "long" else self.high_index

    def retracement(self, r: float) -> float:
        """Price at retracement depth ``r`` from the impulse extreme."""
        rng = self.range
        return self.high - r * rng if self.direction == "long" else self.low + r * rng

    def extension(self, e: float) -> float:
        """Target price at extension ``e`` (``e>1`` projects beyond the impulse extreme)."""
        rng = self.range
        return self.low + e * rng if self.direction == "long" else self.high - e * rng

    def retracement_zone(self, r_lo: float, r_hi: float) -> Tuple[float, float]:
        """Sorted (low, high) price band between retracement depths ``r_lo`` and ``r_hi``."""
        a, b = self.retracement(r_lo), self.retracement(r_hi)
        return (min(a, b), max(a, b))

    def depth(self, price: float) -> float:
        """Retracement depth of ``price`` (0 at impulse extreme, 1 at protected end)."""
        rng = self.range
        if rng <= 0:
            return float("nan")
        return (self.high - price) / rng if self.direction == "long" else (price - self.low) / rng

    def normalized_pos(self, price: float) -> float:
        """Position on the dealing range, 0 at the low and 1 at the high (the brief's convention)."""
        rng = self.range
        if rng <= 0:
            return float("nan")
        return (price - self.low) / rng

    def in_entry_zone(self, price: float, threshold: float = 0.5) -> bool:
        """True iff ``price`` is within the leg and retraced at least ``threshold``."""
        if not (self.low <= price <= self.high):
            return False
        return self.depth(price) >= threshold - 1e-9
