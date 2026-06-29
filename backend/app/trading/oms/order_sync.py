"""Broker order synchronization for OMS-managed orders."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from backend.app.trading.broker.interfaces import BrokerAdapter, BrokerOrder, OrderStatus as BrokerOrderStatus
from backend.app.trading.execution.order import Order, OrderStatus


@dataclass(frozen=True)
class OrderSyncDecision:
    """One broker-to-platform order reconciliation decision."""

    order_id: int
    broker_order_id: str | None
    previous_status: OrderStatus
    current_status: OrderStatus
    changed: bool
    reason: str
    synchronized_at: datetime = field(default_factory=datetime.utcnow)


class BrokerOrderSynchronizer:
    """Reconcile platform orders against broker order state."""

    def __init__(self, broker: BrokerAdapter) -> None:
        self._broker = broker
        self._decisions: list[OrderSyncDecision] = []

    @property
    def decisions(self) -> list[OrderSyncDecision]:
        return list(self._decisions)

    async def synchronize(self, orders: Iterable[Order]) -> list[OrderSyncDecision]:
        decisions: list[OrderSyncDecision] = []
        for order in orders:
            decision = await self.synchronize_order(order)
            decisions.append(decision)
        return decisions

    async def synchronize_order(self, order: Order) -> OrderSyncDecision:
        broker_order_id = getattr(order, "broker_order_id", None)
        previous = order.status
        if not broker_order_id:
            decision = OrderSyncDecision(
                order_id=order.order_id,
                broker_order_id=None,
                previous_status=previous,
                current_status=order.status,
                changed=False,
                reason="order has no broker_order_id",
            )
            self._decisions.append(decision)
            return decision

        try:
            broker_order = await self._broker.get_order(str(broker_order_id), order.symbol)
            self.apply_broker_state(order, broker_order)
            reason = f"broker status {broker_order.status.value}"
        except Exception as exc:  # pylint: disable=broad-except
            reason = f"broker synchronization failed: {exc}"

        decision = OrderSyncDecision(
            order_id=order.order_id,
            broker_order_id=str(broker_order_id),
            previous_status=previous,
            current_status=order.status,
            changed=previous is not order.status,
            reason=reason,
        )
        self._decisions.append(decision)
        return decision

    async def cancel(self, order: Order) -> OrderSyncDecision:
        broker_order_id = getattr(order, "broker_order_id", None) or str(order.order_id)
        previous = order.status
        try:
            broker_order = await self._broker.cancel_order(str(broker_order_id), order.symbol)
            self.apply_broker_state(order, broker_order)
            if broker_order.status == BrokerOrderStatus.CANCELLED:
                order.cancel()
            reason = f"broker cancel status {broker_order.status.value}"
        except Exception as exc:  # pylint: disable=broad-except
            reason = f"broker cancel failed: {exc}"
        decision = OrderSyncDecision(
            order_id=order.order_id,
            broker_order_id=str(broker_order_id),
            previous_status=previous,
            current_status=order.status,
            changed=previous is not order.status,
            reason=reason,
        )
        self._decisions.append(decision)
        return decision

    async def modify(self, order: Order, *, quantity: float | None = None, reference_price: float | None = None) -> OrderSyncDecision:
        previous = order.status
        if quantity is not None:
            if quantity <= 0:
                raise ValueError("quantity must be positive")
            order.quantity = float(quantity)
        if reference_price is not None:
            if reference_price <= 0:
                raise ValueError("reference_price must be positive")
            order.reference_price = float(reference_price)
        decision = OrderSyncDecision(
            order_id=order.order_id,
            broker_order_id=getattr(order, "broker_order_id", None),
            previous_status=previous,
            current_status=order.status,
            changed=False,
            reason="local order parameters updated before broker-native replace support",
        )
        self._decisions.append(decision)
        return decision

    @staticmethod
    def apply_broker_state(order: Order, broker_order: BrokerOrder) -> None:
        order.broker_order_id = broker_order.broker_order_id
        if broker_order.status in (BrokerOrderStatus.OPEN, BrokerOrderStatus.PARTIALLY_FILLED):
            order.submit()
        elif broker_order.status == BrokerOrderStatus.CANCELLED:
            order.cancel()
        elif broker_order.status in (BrokerOrderStatus.REJECTED, BrokerOrderStatus.EXPIRED):
            order.reject(broker_order.reject_reason or f"Broker order {broker_order.status.value}")


__all__ = ["BrokerOrderSynchronizer", "OrderSyncDecision"]
