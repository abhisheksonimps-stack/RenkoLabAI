"""Exponential Moving Average — an independent, reusable streaming indicator.

Seeded deterministically with the simple average of the first ``period`` values
(the standard SMA seed), then advanced by the EMA recurrence with smoothing
factor ``alpha = 2 / (period + 1)``. Not ready until the seed is complete;
``value`` is ``None`` until then.
"""

from __future__ import annotations

from typing import List, Optional


class EMA:
    def __init__(self, period: int) -> None:
        if period <= 0:
            raise ValueError("EMA period must be a positive integer")
        self.period = int(period)
        self.alpha = 2.0 / (self.period + 1)
        self._ema: Optional[float] = None
        self._seed: List[float] = []
        self._count = 0

    def update(self, value: float) -> Optional[float]:
        v = float(value)
        self._count += 1
        if self._ema is None:
            self._seed.append(v)
            if len(self._seed) == self.period:
                self._ema = sum(self._seed) / self.period
            return self._ema
        self._ema = self.alpha * v + (1.0 - self.alpha) * self._ema
        return self._ema

    @property
    def ready(self) -> bool:
        return self._ema is not None

    @property
    def value(self) -> Optional[float]:
        return self._ema

    @property
    def count(self) -> int:
        return self._count

    def reset(self) -> None:
        self._ema = None
        self._seed = []
        self._count = 0
