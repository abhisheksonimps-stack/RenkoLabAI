"""Strategy engine — drives a single strategy over completed Renko bricks.

Thin orchestration only: for each completed brick it feeds the strategy and
collects the resulting signal. It consumes bricks exclusively (never candles,
ticks, or raw OHLC) and holds no trading/broker logic.
"""

from __future__ import annotations

from typing import Any, Iterable, List

from backend.app.trading.signals.models import Signal
from backend.app.trading.strategy.interfaces import Strategy


class StrategyEngine:
    def __init__(self, strategy: Strategy) -> None:
        self._strategy = strategy
        self._signals: List[Signal] = []
        self._started = False

    def start(self) -> None:
        self._strategy.initialize()
        self._signals = []
        self._started = True

    def process_brick(self, brick: Any) -> Signal:
        if not self._started:
            self.start()
        self._strategy.on_brick(brick)
        signal = self._strategy.generate_signal()
        self._signals.append(signal)
        return signal

    def process_bricks(self, bricks: Iterable[Any]) -> List[Signal]:
        return [self.process_brick(brick) for brick in bricks]

    def signals(self) -> List[Signal]:
        return list(self._signals)

    def reset(self) -> None:
        self._strategy.reset()
        self._signals = []
        self._started = False

    @property
    def strategy(self) -> Strategy:
        return self._strategy
