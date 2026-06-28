"""Executor abstraction.

The single seam that makes the execution layer reusable: given an order and a
market reference price, produce a fill (or rejection). Backtesting supplies a
``SimulatedExecutor``; paper/live trading later supply their own executors that
return the same ``Fill`` against the same ``Order`` type.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from backend.app.trading.costs.brokerage import BrokerageModel, ZeroBrokerage
from backend.app.trading.costs.slippage import SlippageModel, ZeroSlippage
from backend.app.trading.execution.order import Fill, Order


class Executor(ABC):
    @abstractmethod
    def execute(self, order: Order, reference_price: float, timestamp: datetime) -> Order:
        """Resolve the order against ``reference_price``; set fill or reject."""


class SimulatedExecutor(Executor):
    """Deterministic fills for backtesting: slippage-adjusted price + brokerage."""

    def __init__(self, slippage: SlippageModel | None = None,
                 brokerage: BrokerageModel | None = None) -> None:
        self._slippage = slippage or ZeroSlippage()
        self._brokerage = brokerage or ZeroBrokerage()

    def execute(self, order: Order, reference_price: float, timestamp: datetime) -> Order:
        order.submit()
        if reference_price is None or reference_price <= 0:
            order.reject("no valid reference price")
            return order
        fill_price = self._slippage.adjust(price=float(reference_price), side=order.side.value)
        cost = self._brokerage.cost(quantity=order.quantity, price=fill_price)
        order.complete(
            Fill(
                price=fill_price,
                quantity=order.quantity,
                cost=cost,
                reference_price=float(reference_price),
                side=order.side,
                timestamp=timestamp,
            )
        )
        return order
