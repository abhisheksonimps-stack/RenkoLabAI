"""PaperExecutor — a venue executor for simulated (paper) trading.

Implements the platform's :class:`Executor` contract exactly
(``execute(order, reference_price, timestamp) -> Order``) so it is a drop-in
peer of ``SimulatedExecutor``: the same ``Order`` goes in and the same ``Fill``
comes out. It composes the existing, reusable slippage and brokerage
(commission) models, and adds a latency model that shifts the fill's timestamp
to reflect the venue's acknowledgement delay.

It does *not* decide whether an order should fill — that triggering logic for
limit/stop orders lives in :class:`PendingOrderManager`. By the time an order
reaches the executor it has already been matched; the executor's sole job is to
turn the matched reference price into a concrete fill. This keeps a single
responsibility per component and preserves the ``Executor`` seam unchanged.
"""

from __future__ import annotations

from datetime import datetime

from backend.app.trading.costs.brokerage import BrokerageModel, ZeroBrokerage
from backend.app.trading.costs.slippage import SlippageModel, ZeroSlippage
from backend.app.trading.execution.executor import Executor
from backend.app.trading.execution.order import Fill, Order
from backend.app.trading.paper.latency import LatencyModel, ZeroLatency


class PaperExecutor(Executor):
    """Slippage + commission fills with a venue acknowledgement latency."""

    def __init__(
        self,
        slippage: SlippageModel | None = None,
        brokerage: BrokerageModel | None = None,
        latency: LatencyModel | None = None,
    ) -> None:
        self._slippage = slippage or ZeroSlippage()
        self._brokerage = brokerage or ZeroBrokerage()
        self._latency = latency or ZeroLatency()

    def execute(self, order: Order, reference_price: float, timestamp: datetime) -> Order:
        order.submit()
        if reference_price is None or reference_price <= 0:
            order.reject("no valid reference price")
            return order

        fill_price = self._slippage.adjust(price=float(reference_price), side=order.side.value)
        cost = self._brokerage.cost(quantity=order.quantity, price=fill_price)
        fill_time = self._latency.apply(timestamp)
        order.complete(
            Fill(
                price=fill_price,
                quantity=order.quantity,
                cost=cost,
                reference_price=float(reference_price),
                side=order.side,
                timestamp=fill_time,
            )
        )
        return order
