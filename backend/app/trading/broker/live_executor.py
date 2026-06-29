"""LiveExecutor bridges the platform executor contract to a BrokerAdapter."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from backend.app.trading.broker.interfaces import (
    BrokerAdapter,
    BrokerError,
    BrokerOrder,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from backend.app.trading.costs.brokerage import BrokerageModel, ZeroBrokerage
from backend.app.trading.costs.slippage import SlippageModel, ZeroSlippage
from backend.app.trading.execution.executor import Executor
from backend.app.trading.execution.order import Fill, Order


class LiveExecutor(Executor):
    """Live trading executor that submits validated platform orders to a broker."""

    def __init__(
        self,
        broker: BrokerAdapter,
        *,
        slippage: Optional[SlippageModel] = None,
        brokerage: Optional[BrokerageModel] = None,
        poll_interval: float = 1.0,
        fill_timeout: float = 60.0,
    ) -> None:
        self._broker = broker
        self._slippage = slippage or ZeroSlippage()
        self._brokerage = brokerage or ZeroBrokerage()
        self._poll_interval = poll_interval
        self._fill_timeout = fill_timeout

    @property
    def broker(self) -> BrokerAdapter:
        return self._broker

    async def execute(self, order: Order, reference_price: float, timestamp: datetime) -> Order:
        """Submit an order to the broker and map broker state back to the order."""
        broker_order_type = self._map_order_type(order)
        broker_side = OrderSide.BUY if order.side.value == "buy" else OrderSide.SELL
        order.submit()

        try:
            broker_order = await self._broker.submit_order(
                symbol=order.symbol,
                side=broker_side,
                order_type=broker_order_type,
                quantity=order.quantity,
                time_in_force=TimeInForce.GTC,
                client_order_id=order.client_order_id or f"renkolab-{order.order_id}",
            )
            order.broker_order_id = broker_order.broker_order_id
            filled_order = broker_order if self._is_terminal(broker_order) else await self._wait_for_fill(broker_order)
            self._apply_broker_fill(order, filled_order, timestamp)
            return order

        except BrokerError as exc:
            order.reject(str(exc))
            return order
        except Exception as exc:  # pylint: disable=broad-except
            order.reject(f"Unexpected error: {exc}")
            return order

    def _map_order_type(self, order: Order) -> OrderType:
        return OrderType.MARKET

    async def _wait_for_fill(self, broker_order: BrokerOrder) -> BrokerOrder:
        """Poll broker until an order reaches a terminal state or timeout."""
        if self._is_terminal(broker_order):
            return broker_order
        start = datetime.utcnow()
        latest = broker_order
        while True:
            await asyncio.sleep(self._poll_interval)
            elapsed = (datetime.utcnow() - start).total_seconds()
            if elapsed > self._fill_timeout:
                try:
                    latest = await self._broker.cancel_order(broker_order.broker_order_id, broker_order.symbol)
                except Exception:  # pylint: disable=broad-except
                    latest = broker_order
                    latest.status = OrderStatus.EXPIRED
                return latest

            latest = await self._broker.get_order(broker_order.broker_order_id, broker_order.symbol)
            if self._is_terminal(latest):
                return latest

    @staticmethod
    def _is_terminal(broker_order: BrokerOrder) -> bool:
        return broker_order.status in (
            OrderStatus.FILLED,
            OrderStatus.REJECTED,
            OrderStatus.CANCELLED,
            OrderStatus.EXPIRED,
        )

    def _apply_broker_fill(self, order: Order, broker_order: BrokerOrder, timestamp: datetime) -> None:
        """Apply broker fill, rejection or cancellation state to the platform order."""
        order.broker_order_id = broker_order.broker_order_id or order.broker_order_id
        if broker_order.status == OrderStatus.FILLED:
            fill_price = broker_order.average_fill_price or order.reference_price
            filled_quantity = broker_order.filled_quantity or broker_order.quantity
            cost = self._brokerage.cost(quantity=filled_quantity, price=fill_price)
            fill = Fill(
                price=fill_price,
                quantity=filled_quantity,
                cost=cost,
                reference_price=float(order.reference_price),
                side=order.side,
                timestamp=broker_order.updated_at or timestamp,
                fill_id=f"{broker_order.broker_order_id}:{filled_quantity}:{fill_price}",
            )
            order.complete(fill)
        elif broker_order.status == OrderStatus.CANCELLED:
            order.cancel()
        elif broker_order.status in (OrderStatus.REJECTED, OrderStatus.EXPIRED):
            reason = broker_order.reject_reason or f"Order {broker_order.status.value}"
            order.reject(reason)


__all__ = ["LiveExecutor"]
