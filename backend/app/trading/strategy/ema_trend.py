"""EMA trend-following strategy.

Uses completed Renko bricks in backtests and normalized MarketBar objects in
paper/live contexts. The strategy is deliberately deterministic: decisions are
made only after the current observation updates the EMA.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from backend.app.marketdata.models import MarketBar
from backend.app.trading.indicators.ema import EMA
from backend.app.trading.signals.models import Signal, SignalType
from backend.app.trading.strategy.interfaces import Strategy, StrategyContext, StrategyResult


class _Position(str, Enum):
    FLAT = "flat"
    LONG = "long"
    SHORT = "short"


class EMATrendStrategy(Strategy):
    """Single-EMA trend strategy.

    BUY when price closes above EMA from flat, SELL when it closes below EMA
    from flat, and EXIT when an opposite trend appears while exposed.
    """

    name = "ema_trend"

    def __init__(self, period: int = 20) -> None:
        if period <= 0:
            raise ValueError("period must be positive")
        self._period = int(period)
        self._ema = EMA(self._period)
        self._last_price: float | None = None
        self._last_brick: Any | None = None
        self._position = _Position.FLAT
        self._last_signal = Signal(SignalType.HOLD)

    def initialize(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._ema.reset()
        self._last_price = None
        self._last_brick = None
        self._position = _Position.FLAT
        self._last_signal = Signal(SignalType.HOLD)

    def on_market_data(self, bar: MarketBar, context: StrategyContext | None = None) -> StrategyResult:
        self._last_brick = None
        self._last_price = float(bar.close)
        self._ema.update(self._last_price)
        self._last_signal = self._decide(price=self._last_price, brick=None)
        resolved_context = context or StrategyContext(symbol=bar.symbol, market_data=bar)
        return StrategyResult(signal=self._last_signal, context=resolved_context)

    def on_brick(self, brick: Any) -> None:
        self._last_brick = brick
        self._last_price = float(brick.close_price)
        self._ema.update(self._last_price)
        self._last_signal = self._decide(price=self._last_price, brick=brick)

    def generate_signal(self) -> Signal:
        return self._last_signal

    def _decide(self, price: float, brick: Any | None) -> Signal:
        ema_value = self._ema.value
        if ema_value is None:
            return self._signal(SignalType.HOLD, price, ema_value, brick)

        if price > ema_value:
            if self._position is _Position.SHORT:
                self._position = _Position.FLAT
                return self._signal(SignalType.EXIT_SHORT, price, ema_value, brick)
            if self._position is _Position.FLAT:
                self._position = _Position.LONG
                return self._signal(SignalType.BUY, price, ema_value, brick)
            return self._signal(SignalType.HOLD, price, ema_value, brick)

        if price < ema_value:
            if self._position is _Position.LONG:
                self._position = _Position.FLAT
                return self._signal(SignalType.EXIT_LONG, price, ema_value, brick)
            if self._position is _Position.FLAT:
                self._position = _Position.SHORT
                return self._signal(SignalType.SELL, price, ema_value, brick)
            return self._signal(SignalType.HOLD, price, ema_value, brick)

        return self._signal(SignalType.HOLD, price, ema_value, brick)

    def _signal(self, signal_type: SignalType, price: float, reference: float | None, brick: Any | None) -> Signal:
        return Signal(
            type=signal_type,
            brick_id=getattr(brick, "brick_id", None) if brick is not None else None,
            price=price,
            reference=reference,
            metadata={"strategy": self.name, "position": self._position.value, "period": self._period},
        )

    @property
    def position(self) -> str:
        return self._position.value

    @property
    def ema(self) -> EMA:
        return self._ema
