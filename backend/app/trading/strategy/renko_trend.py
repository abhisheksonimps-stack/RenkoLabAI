"""Renko trend strategy."""

from __future__ import annotations

from enum import Enum
from typing import Any

from backend.app.chart.renko.models import BrickDirection
from backend.app.trading.signals.models import Signal, SignalType
from backend.app.trading.strategy.interfaces import Strategy


class _Position(str, Enum):
    FLAT = "flat"
    LONG = "long"
    SHORT = "short"


class RenkoTrendStrategy(Strategy):
    """Trade after a configurable number of same-direction Renko bricks."""

    name = "renko_trend"

    def __init__(self, trend_length: int = 3) -> None:
        if trend_length <= 0:
            raise ValueError("trend_length must be positive")
        self._trend_length = int(trend_length)
        self._last_direction: BrickDirection | None = None
        self._streak = 0
        self._position = _Position.FLAT
        self._last_brick: Any | None = None
        self._last_signal = Signal(SignalType.HOLD)

    def initialize(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._last_direction = None
        self._streak = 0
        self._position = _Position.FLAT
        self._last_brick = None
        self._last_signal = Signal(SignalType.HOLD)

    def on_brick(self, brick: Any) -> None:
        self._last_brick = brick
        direction = self._direction(brick)
        if direction is BrickDirection.NEUTRAL:
            self._last_signal = self._signal(SignalType.HOLD)
            return
        if direction == self._last_direction:
            self._streak += 1
        else:
            self._last_direction = direction
            self._streak = 1
        self._last_signal = self._decide(direction)

    def generate_signal(self) -> Signal:
        return self._last_signal

    def _decide(self, direction: BrickDirection) -> Signal:
        if direction is BrickDirection.UP:
            if self._position is _Position.SHORT:
                self._position = _Position.FLAT
                return self._signal(SignalType.EXIT_SHORT)
            if self._position is _Position.FLAT and self._streak >= self._trend_length:
                self._position = _Position.LONG
                return self._signal(SignalType.BUY)
            return self._signal(SignalType.HOLD)

        if self._position is _Position.LONG:
            self._position = _Position.FLAT
            return self._signal(SignalType.EXIT_LONG)
        if self._position is _Position.FLAT and self._streak >= self._trend_length:
            self._position = _Position.SHORT
            return self._signal(SignalType.SELL)
        return self._signal(SignalType.HOLD)

    @staticmethod
    def _direction(brick: Any) -> BrickDirection:
        raw = getattr(brick, "direction", BrickDirection.NEUTRAL)
        return raw if isinstance(raw, BrickDirection) else BrickDirection(str(raw))

    def _signal(self, signal_type: SignalType) -> Signal:
        brick = self._last_brick
        return Signal(
            type=signal_type,
            brick_id=getattr(brick, "brick_id", None) if brick is not None else None,
            price=getattr(brick, "close_price", None) if brick is not None else None,
            reference=float(self._streak),
            metadata={
                "strategy": self.name,
                "position": self._position.value,
                "trend_length": self._trend_length,
                "streak": self._streak,
                "direction": self._last_direction.value if self._last_direction else None,
            },
        )

    @property
    def position(self) -> str:
        return self._position.value

    @property
    def streak(self) -> int:
        return self._streak
