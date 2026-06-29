"""Session layer — async EventBus wiring and lifecycle around the simulator.

:class:`PaperTradingSession` is the public, async-facing entry point for paper
trading. It owns one :class:`ExchangeSimulator`, accepts market data and order
commands, and publishes the resulting :mod:`paper.events` on the shared
``EventBus`` so the rest of the platform can observe the order lifecycle.

The synchronous matching core stays in the simulator; this layer adds only the
async/event concerns, so it can be reasoned about (and tested) independently.

:class:`PaperSessionManager` is a thin registry for running multiple named
sessions (e.g. several symbols or strategies) over a single bus.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from backend.app.domain.market_data.models import Candle, Tick
from backend.app.events.bus import EventBus
from backend.app.trading.execution.order import Order, OrderIntent, OrderSide
from backend.app.trading.paper.enums import OrderType, TimeInForce
from backend.app.trading.paper.events import (
    OrderAccepted,
    OrderCancelled,
    OrderFilled,
    OrderRejected,
    OrderTriggered,
)
from backend.app.trading.paper.executor import PaperExecutor
from backend.app.trading.paper.quote import MarketQuote
from backend.app.trading.paper.simulator import ExchangeSimulator, OrderEvent
from backend.app.trading.portfolio.portfolio import Portfolio

_EVENT_TYPES = {
    "accepted": OrderAccepted,
    "triggered": OrderTriggered,
    "filled": OrderFilled,
    "rejected": OrderRejected,
    "cancelled": OrderCancelled,
}


def _order_snapshot(order: Order) -> dict:
    """Serialisable snapshot of an order for event payloads."""
    fill = order.fill
    return {
        "order_id": order.order_id,
        "side": order.side.value,
        "intent": order.intent.value,
        "quantity": order.quantity,
        "status": order.status.value,
        "reference_price": order.reference_price,
        "reject_reason": order.reject_reason,
        "fill": None if fill is None else {
            "price": fill.price,
            "quantity": fill.quantity,
            "cost": fill.cost,
            "reference_price": fill.reference_price,
            "slippage": fill.slippage,
            "timestamp": fill.timestamp.isoformat(),
        },
    }


class SessionState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    STOPPED = "stopped"


class PaperTradingSession:
    """Async, event-publishing facade over an :class:`ExchangeSimulator`."""

    def __init__(
        self,
        symbol: str,
        portfolio: Portfolio,
        event_bus: EventBus,
        *,
        executor: Optional[PaperExecutor] = None,
    ) -> None:
        self.symbol = symbol
        self.event_bus = event_bus
        self.simulator = ExchangeSimulator(portfolio, executor=executor)
        self.state = SessionState.CREATED
        self._register_events()

    @property
    def portfolio(self) -> Portfolio:
        return self.simulator.portfolio

    def _register_events(self) -> None:
        for event_type in _EVENT_TYPES.values():
            self.event_bus.register_event(event_type)

    # -- lifecycle ------------------------------------------------------------
    def start(self) -> None:
        self.state = SessionState.RUNNING

    def stop(self) -> None:
        self.state = SessionState.STOPPED

    # -- order commands -------------------------------------------------------
    async def submit_market(self, side: OrderSide, quantity: float, *,
                            intent: OrderIntent = OrderIntent.ENTRY,
                            time_in_force: TimeInForce = TimeInForce.GTC) -> Order:
        event = self.simulator.submit(
            side=side, intent=intent, quantity=quantity,
            order_type=OrderType.MARKET, time_in_force=time_in_force,
        )
        await self._publish(event)
        return event.order

    async def submit_limit(self, side: OrderSide, quantity: float, limit_price: float, *,
                           intent: OrderIntent = OrderIntent.ENTRY,
                           time_in_force: TimeInForce = TimeInForce.GTC) -> Order:
        event = self.simulator.submit(
            side=side, intent=intent, quantity=quantity,
            order_type=OrderType.LIMIT, limit_price=limit_price, time_in_force=time_in_force,
        )
        await self._publish(event)
        return event.order

    async def submit_stop(self, side: OrderSide, quantity: float, stop_price: float, *,
                          intent: OrderIntent = OrderIntent.ENTRY,
                          time_in_force: TimeInForce = TimeInForce.GTC) -> Order:
        event = self.simulator.submit(
            side=side, intent=intent, quantity=quantity,
            order_type=OrderType.STOP, stop_price=stop_price, time_in_force=time_in_force,
        )
        await self._publish(event)
        return event.order

    async def cancel(self, order_id: int) -> bool:
        event = self.simulator.cancel(order_id)
        if event is None:
            return False
        await self._publish(event)
        return True

    # -- market data ----------------------------------------------------------
    async def feed_quote(self, quote: MarketQuote) -> List[OrderEvent]:
        events = self.simulator.on_market_data(quote)
        for event in events:
            await self._publish(event)
        return events

    async def on_candle(self, candle: Candle) -> List[OrderEvent]:
        return await self.feed_quote(MarketQuote.from_candle(candle))

    async def on_tick(self, tick: Tick) -> List[OrderEvent]:
        return await self.feed_quote(MarketQuote.from_tick(tick))

    # -- internals ------------------------------------------------------------
    async def _publish(self, event: OrderEvent) -> None:
        event_type = _EVENT_TYPES[event.kind]
        payload = {"symbol": self.symbol, "order": _order_snapshot(event.order)}
        if event.reference_price is not None:
            payload["reference_price"] = event.reference_price
        await self.event_bus.publish(event_type(
            name=event_type.__name__,
            occurred_at=datetime.utcnow(),
            payload=payload,
        ))


class PaperSessionManager:
    """Registry of named paper-trading sessions sharing one EventBus."""

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self._sessions: Dict[str, PaperTradingSession] = {}

    def create_session(self, name: str, symbol: str, portfolio: Portfolio, *,
                        executor: Optional[PaperExecutor] = None) -> PaperTradingSession:
        if name in self._sessions:
            raise ValueError(f"session '{name}' already exists")
        session = PaperTradingSession(symbol, portfolio, self.event_bus, executor=executor)
        self._sessions[name] = session
        return session

    def get(self, name: str) -> Optional[PaperTradingSession]:
        return self._sessions.get(name)

    def close(self, name: str) -> bool:
        session = self._sessions.pop(name, None)
        if session is None:
            return False
        session.stop()
        return True

    @property
    def sessions(self) -> List[str]:
        return list(self._sessions)
