"""LiveExecutor — bridges the platform's Executor contract to a BrokerAdapter.

Converts platform-native Order/Fill objects to/from broker-native representations
and handles the async submission, polling, and fill lifecycle for live trading.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from backend.app.trading.broker.interfaces import (
    BrokerAdapter,
    BrokerOrder,
    BrokerError,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from backend.app.trading.costs.brokerage import BrokerageModel, ZeroBrokerage
from backend.app.trading.costs.slippage import SlippageModel, ZeroSlippage
from backend.app.trading.execution.executor import Executor
from backend.app.trading.execution.order import Fill, Order, OrderIntent


class LiveExecutor(Executor):
    """Live trading executor that submits orders via a BrokerAdapter.

    Unlike SimulatedExecutor/PaperExecutor which resolve fills synchronously,
    LiveExecutor submits orders asynchronously and polls for fill status. It
    translates between the platform's Order/Fill model and the broker's model.

    The executor does NOT decide whether to submit — that is the OMS's job.
    It only executes validated orders against the broker.
    """

    def __init__(
        self,
        broker: BrokerAdapter,
        *,
        slippage: Optional[SlippageModel] = None,
        brokerage: Optional[BrokerageModel] = None,
        poll_interval: float = 1.0,
        fill_timeout: float = 60.0,
    ) -> None:
        """Initialize the live executor.

        Args:
            broker: Connected broker adapter
            slippage: Slippage model for cost estimation (not applied to live fills)
            brokerage: Brokerage/commission model
            poll_interval: Seconds between order status polls
            fill_timeout: Maximum seconds to wait for a fill
        """
        self._broker = broker
        self._slippage = slippage or ZeroSlippage()
        self._brokerage = brokerage or ZeroBrokerage()
        self._poll_interval = poll_interval
        self._fill_timeout = fill_timeout

    async def execute(self, order: Order, reference_price: float, timestamp: datetime) -> Order:
        """Submit order to broker and wait for fill.

        Args:
            order: Platform-native order to execute
            reference_price: Current market price (for validation/logging)
            timestamp: Current timestamp

        Returns:
            Updated order with fill or rejection status
        """
        # Map platform order to broker order
        broker_order_type = self._map_order_type(order)
        broker_side = OrderSide.BUY if order.side.value == "buy" else OrderSide.SELL

        try:
            # Submit to broker
            broker_order = await self._broker.submit_order(
                symbol=order.symbol,
                side=broker_side,
                order_type=broker_order_type,
                quantity=order.quantity,
                time_in_force=TimeInForce.GTC,
            )

            # Poll for fill
            filled_order = await self._wait_for_fill(broker_order)

            # Map back to platform order
            self._apply_broker_fill(order, filled_order, timestamp)
            return order

        except BrokerError as exc:
            order.reject(str(exc))
            return order
        except Exception as exc:
            order.reject(f"Unexpected error: {exc}")
            return order

    def _map_order_type(self, order: Order) -> OrderType:
        """Map platform order type to broker order type."""
        # Platform currently uses OrderIntent; map to market/limit based on context
        # For now, default to MARKET; OMS will provide proper mapping
        return OrderType.MARKET

    async def _wait_for_fill(self, broker_order: BrokerOrder) -> BrokerOrder:
        """Poll broker until order is filled, rejected, or timeout."""
        start = datetime.utcnow()
        while True:
            await asyncio.sleep(self._poll_interval)

            # Check timeout
            elapsed = (datetime.utcnow() - start).total_seconds()
            if elapsed > self._fill_timeout:
                # Cancel the order
                try:
                    await self._broker.cancel_order(broker_order.broker_order_id, broker_order.symbol)
                except Exception:
                    pass
                broker_order.status = OrderStatus.EXPIRED
                return broker_order

            # Fetch updated status
            updated = await self._broker.get_order(broker_order.broker_order_id, broker_order.symbol)

            if updated.status in (OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.CANCELLED, OrderStatus.EXPIRED):
                return updated

    def _apply_broker_fill(self, order: Order, broker_order: BrokerOrder, timestamp: datetime) -> None:
        """Apply broker fill to platform order."""
        if broker_order.status == OrderStatus.FILLED:
            # Calculate brokerage cost
            fill_price = broker_order.average_fill_price or 0.0
            cost = self._brokerage.cost(quantity=broker_order.filled_quantity, price=fill_price)

            fill = Fill(
                price=fill_price,
                quantity=broker_order.filled_quantity,
                cost=cost,
                reference_price=float(order.reference_price),
                side=order.side,
                timestamp=broker_order.updated_at or timestamp,
            )
            order.complete(fill)
        elif broker_order.status in (OrderStatus.REJECTED, OrderStatus.CANCELLED, OrderStatus.EXPIRED):
            reason = broker_order.reject_reason or f"Order {broker_order.status.value}"
            order.reject(reason)