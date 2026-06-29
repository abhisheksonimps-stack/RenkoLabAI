"""ExchangeSimulator — the deterministic matching core of the paper venue.

Converts incoming market data into fills against the reusable execution stack:

  * holds the order-id sequence, the market-order queue and the resting
    limit/stop book (:class:`PendingOrderManager`);
  * matches orders against each :class:`MarketQuote` and resolves them through
    the :class:`PaperExecutor` (slippage + commission + latency);
  * synchronises every fill into the existing :class:`Portfolio`
    (``apply_order`` / reserve / release / mark), exactly as ``BacktestEngine``
    does, so cash, positions, trades and the equity curve stay authoritative.

It is intentionally synchronous and side-effect-light: every state change is
reported back as an :class:`OrderEvent`. The async EventBus wiring lives one
layer up in :class:`PaperTradingSession`, which keeps this core trivial to unit
test without an event loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from backend.app.trading.execution.order import (
    Order,
    OrderIntent,
    OrderSide,
    OrderStatus,
)
from backend.app.trading.execution.position import TradeAttribution
from backend.app.trading.paper.enums import OrderType, TimeInForce
from backend.app.trading.paper.executor import PaperExecutor
from backend.app.trading.paper.pending import PendingOrderManager
from backend.app.trading.paper.quote import MarketQuote
from backend.app.trading.paper.ticket import OrderTicket
from backend.app.trading.portfolio.portfolio import Portfolio


@dataclass(frozen=True)
class OrderEvent:
    """A single state transition reported by the simulator."""

    kind: str  # "accepted" | "triggered" | "filled" | "rejected" | "cancelled"
    order: Order
    reference_price: Optional[float] = None


class ExchangeSimulator:
    """Matches paper orders against market data and syncs the portfolio."""

    def __init__(
        self,
        portfolio: Portfolio,
        executor: Optional[PaperExecutor] = None,
        *,
        attribution: Optional[TradeAttribution] = None,
    ) -> None:
        self.portfolio = portfolio
        self._executor = executor or PaperExecutor()
        self._pending = PendingOrderManager()
        self._market_queue: Dict[int, OrderTicket] = {}
        self._attribution = attribution
        self._next_order_id = 0
        self._sequence = -1
        self._last_quote: Optional[MarketQuote] = None

    # -- introspection --------------------------------------------------------
    @property
    def open_orders(self) -> List[OrderTicket]:
        return list(self._market_queue.values()) + self._pending.open_orders

    @property
    def last_price(self) -> Optional[float]:
        return self._last_quote.price if self._last_quote else None

    # -- order entry ----------------------------------------------------------
    def _new_order_id(self) -> int:
        self._next_order_id += 1
        return self._next_order_id

    def _reference_estimate(self, order_type: OrderType,
                            limit_price: Optional[float],
                            stop_price: Optional[float]) -> float:
        """Best-available price estimate for capital reservation/bookkeeping."""
        if order_type is OrderType.LIMIT and limit_price is not None:
            return float(limit_price)
        if order_type is OrderType.STOP and stop_price is not None:
            return float(stop_price)
        if self._last_quote is not None:
            return self._last_quote.price
        return 0.0

    def submit(
        self,
        *,
        side: OrderSide,
        intent: OrderIntent,
        quantity: float,
        order_type: OrderType,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        timestamp: Optional[datetime] = None,
    ) -> OrderEvent:
        """Create, validate and enqueue an order; return an ``accepted`` event.

        Validation failures (non-positive quantity) yield a ``rejected`` event
        and do not enqueue anything.
        """
        ts = timestamp or (self._last_quote.timestamp if self._last_quote else datetime.utcnow())
        reference = self._reference_estimate(order_type, limit_price, stop_price)
        order = Order(self._new_order_id(), side, intent, float(quantity), reference, ts)

        if quantity <= 0:
            order.reject("quantity must be positive")
            return OrderEvent("rejected", order)

        ticket = OrderTicket(
            order=order,
            order_type=order_type,
            time_in_force=time_in_force,
            limit_price=limit_price,
            stop_price=stop_price,
        )

        # Reserve capital for buys (released by Portfolio.apply_order on settle),
        # mirroring the backtest engine's reservation discipline.
        if side is OrderSide.BUY and reference > 0:
            order.reserved = float(quantity) * reference
            self.portfolio.reserve(order.reserved)

        self.portfolio.record_order(order)
        if ticket.is_resting:
            self._pending.add(ticket)
        else:
            self._market_queue[order.order_id] = ticket
        return OrderEvent("accepted", order)

    # -- cancellation ---------------------------------------------------------
    def cancel(self, order_id: int) -> Optional[OrderEvent]:
        """Cancel a queued/resting order. Returns ``None`` if not cancellable."""
        ticket = self._market_queue.pop(order_id, None) or self._pending.remove(order_id)
        if ticket is None:
            return None
        order = ticket.order
        if order.side is OrderSide.BUY:
            self.portfolio.release(order.reserved)
        order.cancel()
        return OrderEvent("cancelled", order)

    # -- market data ----------------------------------------------------------
    def on_market_data(self, quote: MarketQuote) -> List[OrderEvent]:
        """Advance the venue by one market update; return resulting events."""
        self._sequence += 1
        self._last_quote = quote
        events: List[OrderEvent] = []

        # 1. Market orders fill at this quote's price (deterministic order).
        for order_id in sorted(self._market_queue):
            ticket = self._market_queue[order_id]
            events.append(self._fill(ticket, quote.price, quote.timestamp))
        self._market_queue.clear()

        # 2. Resting limit/stop orders that trigger on this quote.
        for ticket, reference in self._pending.match(quote):
            events.append(OrderEvent("triggered", ticket.order, reference))
            events.append(self._fill(ticket, reference, quote.timestamp))

        # 3. Immediate-or-cancel orders that did not fill this cycle are pulled.
        events.extend(self._cancel_unfilled_ioc())

        # 4. Mark the portfolio to this quote (build the equity curve).
        self.portfolio.mark(quote.timestamp, quote.price)
        return events

    # -- internals ------------------------------------------------------------
    def _fill(self, ticket: OrderTicket, reference_price: float, timestamp: datetime) -> OrderEvent:
        order = ticket.order
        self._executor.execute(order, reference_price=reference_price, timestamp=timestamp)
        self.portfolio.apply_order(order, self._sequence)
        if order.status is OrderStatus.FILLED:
            return OrderEvent("filled", order, reference_price)
        return OrderEvent("rejected", order, reference_price)

    def _cancel_unfilled_ioc(self) -> List[OrderEvent]:
        events: List[OrderEvent] = []
        for ticket in self._pending.open_orders:
            if ticket.time_in_force is TimeInForce.IOC:
                cancelled = self.cancel(ticket.order_id)
                if cancelled is not None:
                    events.append(cancelled)
        return events
