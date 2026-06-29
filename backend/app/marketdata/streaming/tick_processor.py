"""Tick processing bridge from streaming events to strategy execution."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from backend.app.marketdata.models import MarketBar
from backend.app.marketdata.streaming.events import TickEvent
from backend.app.trading.signals.models import SignalType
from backend.app.trading.strategy.engine import StrategyEngine
from backend.app.trading.strategy.interfaces import Strategy, StrategyContext, StrategyParameterValue, StrategyResult


@dataclass(frozen=True)
class TickProcessingResult:
    """Result of translating a tick into a strategy decision."""

    event: TickEvent
    context: StrategyContext
    strategy_result: StrategyResult

    @property
    def actionable(self) -> bool:
        return self.strategy_result.signal.type is not SignalType.HOLD


class TickProcessor:
    """Process ``TickEvent`` instances through the existing ``StrategyEngine``."""

    def __init__(self, strategy_engine: StrategyEngine) -> None:
        self._strategy_engine = strategy_engine
        self._processed = 0

    @property
    def processed_count(self) -> int:
        return self._processed

    def process(self, event: TickEvent, context: StrategyContext | None = None) -> TickProcessingResult:
        resolved_context = context or self.context_from_tick(event)
        strategy = self._strategy_engine.strategy
        if self._strategy_overrides_tick(strategy):
            result = self._strategy_engine.process_tick(self.tick_payload(event), resolved_context)
        else:
            result = self._strategy_engine.process_market_data(self.bar_from_tick(event), resolved_context)
        self._processed += 1
        return TickProcessingResult(event=event, context=resolved_context, strategy_result=result)

    @staticmethod
    def _strategy_overrides_tick(strategy: Strategy) -> bool:
        return type(strategy).on_tick is not Strategy.on_tick

    @staticmethod
    def tick_payload(event: TickEvent) -> Mapping[str, StrategyParameterValue]:
        return {
            "symbol": event.symbol,
            "price": float(event.price),
            "size": float(event.size),
            "side": event.side,
            "exchange": event.exchange,
        }

    @staticmethod
    def context_from_tick(
        event: TickEvent,
        *,
        cash: float | None = None,
        equity: float | None = None,
        position_quantity: float = 0.0,
        open_positions: int = 0,
    ) -> StrategyContext:
        return StrategyContext(
            symbol=event.symbol,
            timestamp=event.occurred_at,
            tick=TickProcessor.tick_payload(event),
            current_price=float(event.price),
            cash=cash,
            equity=equity,
            position_quantity=position_quantity,
            open_positions=open_positions,
            metadata={"exchange": event.exchange, "side": event.side, "source_event": event.name},
        )

    @staticmethod
    def bar_from_tick(event: TickEvent) -> MarketBar:
        price = float(event.price)
        return MarketBar.create(
            symbol=event.symbol,
            timestamp=event.occurred_at,
            open=price,
            high=price,
            low=price,
            close=price,
            volume=float(event.size),
            interval="tick",
            source=event.exchange or "streaming",
            metadata={"event_name": event.name, "side": event.side},
        )


__all__ = ["TickProcessingResult", "TickProcessor"]
