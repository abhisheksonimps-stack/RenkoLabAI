"""Paper-trading framework (Milestone 1).

A simulated execution venue built entirely on the platform's existing,
venue-agnostic primitives — ``Order``, ``Fill``, ``Position``, ``Portfolio``,
the ``Executor`` contract, the cost models and the ``EventBus``. Nothing in the
core trading stack is modified or duplicated; this package only *composes* it.

Public surface:
  * :class:`PaperExecutor`        — ``Executor`` implementation (slippage +
                                    commission + latency).
  * :class:`ExchangeSimulator`    — deterministic matching core.
  * :class:`PaperTradingSession`  — async EventBus-facing session.
  * :class:`PaperSessionManager`  — multi-session registry.
  * :class:`ReplayMarketFeed`     — replay-engine integration.
  * Latency models, order enums, ticket and quote value objects.
"""

from __future__ import annotations

from backend.app.trading.paper.enums import OrderType, TimeInForce
from backend.app.trading.paper.events import (
    OrderAccepted,
    OrderCancelled,
    OrderFilled,
    OrderRejected,
    OrderTriggered,
)
from backend.app.trading.paper.executor import PaperExecutor
from backend.app.trading.paper.latency import (
    FixedLatency,
    LatencyModel,
    RandomLatency,
    ZeroLatency,
)
from backend.app.trading.paper.pending import PendingOrderManager
from backend.app.trading.paper.quote import MarketQuote
from backend.app.trading.paper.replay_feed import ReplayMarketFeed
from backend.app.trading.paper.session import (
    PaperSessionManager,
    PaperTradingSession,
    SessionState,
)
from backend.app.trading.paper.simulator import ExchangeSimulator, OrderEvent
from backend.app.trading.paper.ticket import OrderTicket

__all__ = [
    "OrderType",
    "TimeInForce",
    "OrderTicket",
    "MarketQuote",
    "LatencyModel",
    "ZeroLatency",
    "FixedLatency",
    "RandomLatency",
    "PaperExecutor",
    "PendingOrderManager",
    "ExchangeSimulator",
    "OrderEvent",
    "PaperTradingSession",
    "PaperSessionManager",
    "SessionState",
    "ReplayMarketFeed",
    "OrderAccepted",
    "OrderTriggered",
    "OrderFilled",
    "OrderRejected",
    "OrderCancelled",
]
