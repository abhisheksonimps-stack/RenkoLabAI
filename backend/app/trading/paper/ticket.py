"""OrderTicket — a paper-venue wrapper around the reusable ``Order``.

The platform's :class:`Order` is venue-agnostic and carries no order-type or
trigger-price fields (by design — it must flow unchanged through backtest, paper
and live executors). Rather than duplicate or mutate ``Order``, the paper venue
attaches its extra matching metadata (order type, limit/stop price, time in
force) to a *ticket* that holds a reference to the very same ``Order`` instance.
The ``Order`` remains the single record of identity, status and fill.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.trading.execution.order import Order, OrderSide
from backend.app.trading.paper.enums import OrderType, TimeInForce


@dataclass
class OrderTicket:
    """Pairs an existing :class:`Order` with its paper-matching parameters."""

    order: Order
    order_type: OrderType
    time_in_force: TimeInForce = TimeInForce.GTC
    limit_price: float | None = None
    stop_price: float | None = None

    def __post_init__(self) -> None:
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError("LIMIT order requires a limit_price")
        if self.order_type is OrderType.STOP and self.stop_price is None:
            raise ValueError("STOP order requires a stop_price")
        if self.limit_price is not None and self.limit_price <= 0:
            raise ValueError("limit_price must be positive")
        if self.stop_price is not None and self.stop_price <= 0:
            raise ValueError("stop_price must be positive")

    @property
    def order_id(self) -> int:
        return self.order.order_id

    @property
    def side(self) -> OrderSide:
        return self.order.side

    @property
    def is_resting(self) -> bool:
        """Limit and stop orders rest on the book; market orders do not."""
        return self.order_type in (OrderType.LIMIT, OrderType.STOP)
