"""PendingOrderManager — the resting-order book and trigger rules.

Owns the limit/stop orders waiting to match and answers one question per market
update: which resting tickets should fill, and at what reference price. The
*how* of filling (slippage, commission, latency) belongs to
:class:`PaperExecutor`; this component only decides *when* and against *which*
reference price, keeping the two concerns separate.

Trigger rules (long/short symmetric, evaluated against the quote's intrabar
high/low so a touch is never missed):

  * LIMIT BUY  — triggers when ``low <= limit``;  reference = limit price.
  * LIMIT SELL — triggers when ``high >= limit``; reference = limit price.
  * STOP BUY   — triggers when ``high >= stop``;  reference = stop price.
  * STOP SELL  — triggers when ``low <= stop``;   reference = stop price.

A limit reference is the limit price (the guaranteed worst price); a stop
reference is the stop level (where the order becomes marketable). In both cases
the executor's slippage model is applied uniformly on top, so configure
``ZeroSlippage`` if you want limit orders to fill exactly at their limit.
"""

from __future__ import annotations

from typing import Dict, List

from backend.app.trading.execution.order import OrderSide
from backend.app.trading.paper.enums import OrderType
from backend.app.trading.paper.quote import MarketQuote
from backend.app.trading.paper.ticket import OrderTicket


class PendingOrderManager:
    """Holds resting limit/stop tickets and resolves triggers per quote."""

    def __init__(self) -> None:
        self._resting: Dict[int, OrderTicket] = {}

    # -- book management ------------------------------------------------------
    def add(self, ticket: OrderTicket) -> None:
        self._resting[ticket.order_id] = ticket

    def remove(self, order_id: int) -> OrderTicket | None:
        return self._resting.pop(order_id, None)

    def get(self, order_id: int) -> OrderTicket | None:
        return self._resting.get(order_id)

    @property
    def open_orders(self) -> List[OrderTicket]:
        return list(self._resting.values())

    def __contains__(self, order_id: int) -> bool:
        return order_id in self._resting

    def __len__(self) -> int:
        return len(self._resting)

    # -- matching -------------------------------------------------------------
    def match(self, quote: MarketQuote) -> List[tuple[OrderTicket, float]]:
        """Return ``(ticket, reference_price)`` pairs that trigger on ``quote``.

        Triggered tickets are removed from the book. Pairs are returned in
        ascending order id for deterministic processing.
        """
        triggered: List[tuple[OrderTicket, float]] = []
        for order_id in sorted(self._resting):
            ticket = self._resting[order_id]
            reference = self._trigger_reference(ticket, quote)
            if reference is not None:
                triggered.append((ticket, reference))
        for ticket, _ in triggered:
            self._resting.pop(ticket.order_id, None)
        return triggered

    def _trigger_reference(self, ticket: OrderTicket, quote: MarketQuote) -> float | None:
        """Reference price if the ticket triggers on ``quote``, else ``None``."""
        if ticket.order_type is OrderType.LIMIT:
            limit = ticket.limit_price
            assert limit is not None  # guaranteed by OrderTicket validation
            if ticket.side is OrderSide.BUY and quote.low <= limit:
                return limit
            if ticket.side is OrderSide.SELL and quote.high >= limit:
                return limit
            return None

        if ticket.order_type is OrderType.STOP:
            stop = ticket.stop_price
            assert stop is not None  # guaranteed by OrderTicket validation
            if ticket.side is OrderSide.BUY and quote.high >= stop:
                return stop
            if ticket.side is OrderSide.SELL and quote.low <= stop:
                return stop
            return None

        return None  # MARKET orders never rest here
