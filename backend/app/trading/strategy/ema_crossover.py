"""EMA crossover strategy (Sprint T1) — implemented exactly as specified.

Rules (completed Renko bricks only):
    BUY   - brick closes above the 10 EMA
    SELL  - brick closes below the 10 EMA
    EXIT  - opposite signal arrives while a position is held
    HOLD  - otherwise (no position change, or the EMA is not yet ready)

No optimization, no filters, no AI. Signals are produced at brick close from
completed bricks and prior state only, so they never repaint.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from backend.app.trading.indicators.ema import EMA
from backend.app.trading.signals.models import Signal, SignalType
from backend.app.trading.strategy.interfaces import Strategy


class _Position(str, Enum):
    FLAT = "flat"
    LONG = "long"
    SHORT = "short"


class EMACrossoverStrategy(Strategy):
    name = "ema_crossover"

    def __init__(self, period: int = 10) -> None:
        self._period = int(period)
        self._ema = EMA(self._period)
        self._last_brick: Optional[Any] = None
        self._position = _Position.FLAT

    # -- lifecycle ------------------------------------------------------------
    def initialize(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._ema.reset()
        self._last_brick = None
        self._position = _Position.FLAT

    # -- consume bricks -------------------------------------------------------
    def on_brick(self, brick: Any) -> None:
        # Completed bricks only. The EMA includes this brick's close, matching
        # "brick closes above/below the EMA" evaluated at the brick close.
        self._last_brick = brick
        self._ema.update(brick.close_price)

    # -- decide ---------------------------------------------------------------
    def generate_signal(self) -> Signal:
        if self._last_brick is None or not self._ema.ready:
            return self._signal(SignalType.HOLD)

        close = self._last_brick.close_price
        ema = self._ema.value

        if close > ema:  # bullish brick
            if self._position is _Position.SHORT:
                self._position = _Position.FLAT
                return self._signal(SignalType.EXIT)
            if self._position is _Position.FLAT:
                self._position = _Position.LONG
                return self._signal(SignalType.BUY)
            return self._signal(SignalType.HOLD)  # already long

        if close < ema:  # bearish brick
            if self._position is _Position.LONG:
                self._position = _Position.FLAT
                return self._signal(SignalType.EXIT)
            if self._position is _Position.FLAT:
                self._position = _Position.SHORT
                return self._signal(SignalType.SELL)
            return self._signal(SignalType.HOLD)  # already short

        return self._signal(SignalType.HOLD)  # close == ema

    # -- helpers --------------------------------------------------------------
    def _signal(self, signal_type: SignalType) -> Signal:
        brick = self._last_brick
        return Signal(
            type=signal_type,
            brick_id=getattr(brick, "brick_id", None) if brick is not None else None,
            price=getattr(brick, "close_price", None) if brick is not None else None,
            reference=self._ema.value,
            metadata={"position": self._position.value, "period": self._period},
        )

    # -- introspection (tests/diagnostics) ------------------------------------
    @property
    def position(self) -> str:
        return self._position.value

    @property
    def ema(self) -> EMA:
        return self._ema
