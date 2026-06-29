"""Latency models — the submission-to-fill delay of a simulated venue.

Latency in paper trading is the gap between when an order is matched and when
its fill is acknowledged. It never changes *whether* or *at what price* an order
fills, only the fill's timestamp, so it slots in cleanly without touching the
``Executor`` interface. Mirrors the shape of the existing slippage/brokerage
model families: an ABC plus small concrete strategies.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from datetime import datetime, timedelta


class LatencyModel(ABC):
    @abstractmethod
    def delay(self) -> timedelta:
        """Return the latency to add to a fill's timestamp (>= 0)."""

    def apply(self, timestamp: datetime) -> datetime:
        """Shift ``timestamp`` forward by this model's delay."""
        return timestamp + self.delay()


class ZeroLatency(LatencyModel):
    def delay(self) -> timedelta:
        return timedelta()


class FixedLatency(LatencyModel):
    """A constant delay expressed in milliseconds."""

    def __init__(self, milliseconds: float) -> None:
        if milliseconds < 0:
            raise ValueError("FixedLatency milliseconds must be >= 0")
        self._delta = timedelta(milliseconds=float(milliseconds))

    def delay(self) -> timedelta:
        return self._delta


class RandomLatency(LatencyModel):
    """A uniformly random delay between ``min_ms`` and ``max_ms`` (inclusive).

    A seed yields deterministic, reproducible draws for testing.
    """

    def __init__(self, min_ms: float, max_ms: float, seed: int | None = None) -> None:
        if min_ms < 0 or max_ms < 0:
            raise ValueError("RandomLatency bounds must be >= 0")
        if max_ms < min_ms:
            raise ValueError("RandomLatency max_ms must be >= min_ms")
        self._min_ms = float(min_ms)
        self._max_ms = float(max_ms)
        self._rng = random.Random(seed)

    def delay(self) -> timedelta:
        return timedelta(milliseconds=self._rng.uniform(self._min_ms, self._max_ms))
