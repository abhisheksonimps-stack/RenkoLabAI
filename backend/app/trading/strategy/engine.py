"""Strategy engine.

A thin orchestration layer for strategy lifecycle hooks. It preserves the
original completed-Renko-brick contract used by the backtesting engine and adds
Sprint 8 context-aware market-data/tick/fill hooks.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Iterable, List, Mapping

from backend.app.marketdata.models import MarketBar
from backend.app.trading.execution.order import Fill
from backend.app.trading.execution.position import Trade
from backend.app.trading.signals.models import Signal
from backend.app.trading.strategy.interfaces import (
    Strategy,
    StrategyContext,
    StrategyParameterValue,
    StrategyResult,
)
from backend.app.trading.strategy.risk import RiskManager


class StrategyEngine:
    """Drive a single stateful strategy instance."""

    def __init__(self, strategy: Strategy, risk_manager: RiskManager | None = None) -> None:
        self._strategy = strategy
        self._risk_manager = risk_manager or RiskManager()
        self._signals: List[Signal] = []
        self._results: List[StrategyResult] = []
        self._started = False

    def start(self) -> None:
        """Initialize the strategy for a fresh run."""
        self._strategy.initialize()
        self._signals = []
        self._results = []
        self._started = True

    def process_market_data(self, bar: MarketBar, context: StrategyContext | None = None) -> StrategyResult:
        """Process one normalized market-data bar."""
        if not self._started:
            self.start()
        resolved_context = context or StrategyContext(symbol=bar.symbol, market_data=bar)
        result = self._strategy.on_market_data(bar, resolved_context)
        result = self._with_risk(result, resolved_context)
        self._record(result)
        return result

    def process_brick(self, brick: Any) -> Signal:
        """Process one completed Renko brick and return its Signal.

        This method is the backtesting hot path. It uses Pydantic's
        ``model_construct`` only after reading trusted in-process brick data,
        preserving the public Sprint 8 API while avoiding repeated validation
        and mapping normalization for every replayed brick.
        """
        if not self._started:
            self.start()
        self._strategy.on_brick(brick)
        signal = self._strategy.generate_signal()
        context = self._context_from_brick(brick)
        if self._risk_manager.has_rules:
            signal = self._risk_manager.evaluate(signal, context)
        result = StrategyResult.model_construct(
            signal=signal,
            context=context,
            confidence=None,
            diagnostics={},
            created_at=datetime.now(UTC),
        )
        self._record(result)
        return signal


    @staticmethod
    def _context_from_brick(brick: Any) -> StrategyContext:
        """Build a StrategyContext from a trusted completed brick.

        Backtests feed internal Brick instances here, so full Pydantic
        validation is unnecessary on every iteration. The constructed object is
        still a StrategyContext and remains compatible with risk rules, tests,
        and public callers.
        """
        metadata = getattr(brick, "metadata", {}) or {}
        return StrategyContext.model_construct(
            symbol=str(metadata.get("symbol", "UNKNOWN")),
            timestamp=getattr(brick, "created_at", datetime.now(UTC)),
            configuration=None,
            market_data=None,
            brick=brick,
            tick=None,
            current_price=float(getattr(brick, "close_price")),
            cash=None,
            equity=None,
            position_quantity=0.0,
            open_positions=0,
            metadata=metadata,
        )

    def process_tick(
        self,
        tick: Mapping[str, StrategyParameterValue],
        context: StrategyContext,
    ) -> StrategyResult:
        """Process one tick-level update."""
        if not self._started:
            self.start()
        result = self._strategy.on_tick(tick, context)
        result = self._with_risk(result, context)
        self._record(result)
        return result

    def on_order_fill(self, fill: Fill, context: StrategyContext | None = None) -> StrategyResult:
        """Notify the strategy of an execution fill."""
        if not self._started:
            self.start()
        result = self._strategy.on_order_fill(fill, context)
        self._record(result)
        return result

    def on_position_close(self, trade: Trade, context: StrategyContext | None = None) -> StrategyResult:
        """Notify the strategy of a closed position."""
        if not self._started:
            self.start()
        result = self._strategy.on_position_close(trade, context)
        self._record(result)
        return result

    def process_bricks(self, bricks: Iterable[Any]) -> List[Signal]:
        """Process many completed bricks."""
        return [self.process_brick(brick) for brick in bricks]

    def signals(self) -> List[Signal]:
        """Return a copy of produced signals."""
        return list(self._signals)

    def results(self) -> List[StrategyResult]:
        """Return a copy of produced strategy results."""
        return list(self._results)

    def reset(self) -> None:
        """Reset engine and strategy state."""
        self._strategy.reset()
        self._signals = []
        self._results = []
        self._started = False

    def shutdown(self) -> None:
        """Shutdown the strategy."""
        self._strategy.shutdown()
        self._started = False

    def _with_risk(self, result: StrategyResult, context: StrategyContext) -> StrategyResult:
        signal = self._risk_manager.evaluate(result.signal, context)
        if signal is result.signal:
            return result
        return StrategyResult(
            signal=signal,
            context=result.context or context,
            confidence=result.confidence,
            diagnostics=result.diagnostics,
            created_at=result.created_at,
        )

    def _record(self, result: StrategyResult) -> None:
        self._results.append(result)
        self._signals.append(result.signal)

    @property
    def strategy(self) -> Strategy:
        """Return the managed strategy."""
        return self._strategy
