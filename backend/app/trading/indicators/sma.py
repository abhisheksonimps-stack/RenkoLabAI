"""Simple Moving Average — an independent, reusable streaming indicator.

O(1) per update via a fixed-length window and a running sum. Not ready until
``period`` values have been seen; ``value`` is ``None`` until then.
"""

from __future__ import annotations

from collections import deque
from typing import Optional


class SMA:
    def __init__(self, period: int) -> None:
        if period <= 0:
            raise ValueError("SMA period must be a positive integer")
        self.period = int(period)
        self._window: deque[float] = deque()
        self._sum = 0.0

    def update(self, value: float) -> Optional[float]:
        v = float(value)
        self._window.append(v)
        self._sum += v
        if len(self._window) > self.period:
            self._sum -= self._window.popleft()
        return self.value

    @property
    def ready(self) -> bool:
        return len(self._window) == self.period

    @property
    def value(self) -> Optional[float]:
        if not self.ready:
            return None
        return self._sum / self.period

    @property
    def count(self) -> int:
        return len(self._window)

    def reset(self) -> None:
        self._window.clear()
        self._sum = 0.0
