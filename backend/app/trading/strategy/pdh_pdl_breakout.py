"""Previous-day high / previous-day low breakout strategy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any

from backend.app.marketdata.models import MarketBar
from backend.app.trading.signals.models import Signal, SignalType
from backend.app.trading.strategy.interfaces import Strategy, StrategyContext, StrategyResult


class _Position(str, Enum):
    FLAT = "flat"
    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True)
class _SessionRange:
    session_date: date
    high: float
    low: float

    def extend(self, high: float, low: float) -> "_SessionRange":
        return _SessionRange(self.session_date, max(self.high, high), min(self.low, low))


class PDHPDLBreakoutStrategy(Strategy):
    """Break out above previous-day high or below previous-day low."""

    name = "pdh_pdl_breakout"

    def __init__(self, buffer: float = 0.0) -> None:
        if buffer < 0:
            raise ValueError("buffer cannot be negative")
        self._buffer = float(buffer)
        self._previous: _SessionRange | None = None
        self._current: _SessionRange | None = None
        self._position = _Position.FLAT
        self._last_signal = Signal(SignalType.HOLD)
        self._last_price: float | None = None
        self._last_brick: Any | None = None

    def initialize(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._previous = None
        self._current = None
        self._position = _Position.FLAT
        self._last_signal = Signal(SignalType.HOLD)
        self._last_price = None
        self._last_brick = None

    def on_market_data(self, bar: MarketBar, context: StrategyContext | None = None) -> StrategyResult:
        self._last_brick = None
        self._last_price = float(bar.close)
        self._update_session(bar.timestamp.date(), float(bar.high), float(bar.low))
        self._last_signal = self._decide(price=float(bar.close), brick=None)
        resolved_context = context or StrategyContext(symbol=bar.symbol, market_data=bar)
        return StrategyResult(signal=self._last_signal, context=resolved_context)

    def on_brick(self, brick: Any) -> None:
        self._last_brick = brick
        self._last_price = float(brick.close_price)
        metadata = getattr(brick, "metadata", {}) or {}
        pdh = metadata.get("previous_day_high")
        pdl = metadata.get("previous_day_low")
        if pdh is not None and pdl is not None:
            self._previous = _SessionRange(getattr(brick, "created_at").date(), float(pdh), float(pdl))
        self._last_signal = self._decide(price=self._last_price, brick=brick)

    def generate_signal(self) -> Signal:
        return self._last_signal

    def _update_session(self, session_date: date, high: float, low: float) -> None:
        if self._current is None:
            self._current = _SessionRange(session_date, high, low)
            return
        if self._current.session_date == session_date:
            self._current = self._current.extend(high, low)
            return
        self._previous = self._current
        self._current = _SessionRange(session_date, high, low)

    def _decide(self, price: float, brick: Any | None) -> Signal:
        if self._previous is None:
            return self._signal(SignalType.HOLD, price, None, brick)

        high_trigger = self._previous.high + self._buffer
        low_trigger = self._previous.low - self._buffer

        if price > high_trigger:
            if self._position is _Position.SHORT:
                self._position = _Position.FLAT
                return self._signal(SignalType.EXIT_SHORT, price, high_trigger, brick)
            if self._position is _Position.FLAT:
                self._position = _Position.LONG
                return self._signal(SignalType.BUY, price, high_trigger, brick)
            return self._signal(SignalType.HOLD, price, high_trigger, brick)

        if price < low_trigger:
            if self._position is _Position.LONG:
                self._position = _Position.FLAT
                return self._signal(SignalType.EXIT_LONG, price, low_trigger, brick)
            if self._position is _Position.FLAT:
                self._position = _Position.SHORT
                return self._signal(SignalType.SELL, price, low_trigger, brick)
            return self._signal(SignalType.HOLD, price, low_trigger, brick)

        return self._signal(SignalType.HOLD, price, None, brick)

    def _signal(self, signal_type: SignalType, price: float | None, reference: float | None, brick: Any | None) -> Signal:
        return Signal(
            type=signal_type,
            brick_id=getattr(brick, "brick_id", None) if brick is not None else None,
            price=price,
            reference=reference,
            metadata={
                "strategy": self.name,
                "position": self._position.value,
                "buffer": self._buffer,
                "previous_day_high": None if self._previous is None else self._previous.high,
                "previous_day_low": None if self._previous is None else self._previous.low,
            },
        )

    @property
    def position(self) -> str:
        return self._position.value
