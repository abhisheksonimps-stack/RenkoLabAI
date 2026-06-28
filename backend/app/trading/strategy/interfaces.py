"""Strategy interface.

A strategy consumes COMPLETED Renko bricks only — never candles, ticks, or raw
OHLC — and produces trading signals. The contract is deliberately small.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from backend.app.trading.signals.models import Signal


class Strategy(ABC):
    """Every strategy exposes exactly these four operations."""

    #: Stable, registry-friendly identifier.
    name: str = "strategy"

    @abstractmethod
    def initialize(self) -> None:
        """Prepare the strategy for a fresh run (clear all state)."""

    @abstractmethod
    def on_brick(self, brick: Any) -> None:
        """Consume one completed Renko brick (duck-typed: uses ``close_price``)."""

    @abstractmethod
    def generate_signal(self) -> Signal:
        """Return the signal for the most recently consumed brick."""

    @abstractmethod
    def reset(self) -> None:
        """Reset all internal state to the initial condition."""
