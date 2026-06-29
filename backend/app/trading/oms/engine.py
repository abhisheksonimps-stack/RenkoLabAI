"""Order Management System engine."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from backend.app.trading.broker.interfaces import BrokerAdapter
from backend.app.trading.broker.live_executor import LiveExecutor
from backend.app.trading.execution.executor import Executor
from backend.app.trading.execution.order import Order, OrderIntent, OrderSide, OrderStatus
from backend.app.trading.oms.order_sync import BrokerOrderSynchronizer, OrderSyncDecision
from backend.app.trading.oms.positions import PositionRecord, PositionSynchronizer
from backend.app.trading.oms.risk import PreExecutionRiskValidator, RiskCheckResult
from backend.app.trading.signals.models import Signal, SignalType
from backend.app.trading.strategy.interfaces import StrategyContext
from backend.app.trading.strategy.risk import RiskManager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RiskDecision:
    """Stored risk validation decision for an OMS order."""

    order_id: int
    passed: bool
    reason: str
    rule_name: str
    decided_at: datetime = field(default_factory=datetime.utcnow)


class OMSConfig:
    """Configuration for the OMS."""

    def __init__(
        self,
        max_position_size: float = 1.0,
        max_order_value: Optional[float] = None,
        allowed_symbols: Optional[List[str]] = None,
        require_risk_validation: bool = True,
    ) -> None:
        self.max_position_size = max_position_size
        self.max_order_value = max_order_value
        self.allowed_symbols = allowed_symbols
        self.require_risk_validation = require_risk_validation


class OrderManager:
    """Tracks and manages all orders in the system."""

    def __init__(self) -> None:
        self._orders: Dict[int, Order] = {}
        self._next_order_id = 0

    def create_order(
        self,
        side: OrderSide,
        intent: OrderIntent,
        quantity: float,
        reference_price: float,
        symbol: str,
    ) -> Order:
        self._next_order_id += 1
        order = Order(
            order_id=self._next_order_id,
            side=side,
            intent=intent,
            quantity=quantity,
            reference_price=reference_price,
            created_at=datetime.utcnow(),
            symbol=symbol,
            client_order_id=f"renkolab-{self._next_order_id}",
        )
        self._orders[order.order_id] = order
        return order

    def get_order(self, order_id: int) -> Optional[Order]:
        return self._orders.get(order_id)

    def update_order(self, order: Order) -> None:
        self._orders[order.order_id] = order

    def get_active_orders(self) -> List[Order]:
        return [
            order
            for order in self._orders.values()
            if order.status not in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED)
        ]

    @property
    def all_orders(self) -> List[Order]:
        return list(self._orders.values())


class OMS:
    """Order Management System coordinating signal, risk and execution flow."""

    def __init__(
        self,
        executor: Executor,
        *,
        broker: Optional[BrokerAdapter] = None,
        risk_manager: Optional[RiskManager] = None,
        position_synchronizer: Optional[PositionSynchronizer] = None,
        config: Optional[OMSConfig] = None,
    ) -> None:
        self._executor = executor
        self._broker = broker or (executor.broker if isinstance(executor, LiveExecutor) else None)
        self._risk_manager = risk_manager
        self._position_synchronizer = position_synchronizer
        self._config = config or OMSConfig()
        self._order_manager = OrderManager()
        self._risk_validator = PreExecutionRiskValidator(
            risk_manager=risk_manager,
            position_synchronizer=position_synchronizer,
            max_position_value=self._config.max_order_value,
        )
        self._risk_decisions: list[RiskDecision] = []
        self._order_synchronizer = BrokerOrderSynchronizer(self._broker) if self._broker is not None else None

    @property
    def order_manager(self) -> OrderManager:
        return self._order_manager

    @property
    def position_synchronizer(self) -> Optional[PositionSynchronizer]:
        return self._position_synchronizer

    @property
    def risk_decisions(self) -> list[RiskDecision]:
        return list(self._risk_decisions)

    @property
    def order_synchronizer(self) -> Optional[BrokerOrderSynchronizer]:
        return self._order_synchronizer

    async def process_signal(self, signal: Signal, context: StrategyContext, reference_price: float) -> Optional[Order]:
        if signal.type == SignalType.HOLD:
            return None
        if not self._validate_signal(signal, context):
            return None
        order = self._signal_to_order(signal, context, reference_price)
        if order is None:
            return None

        risk_result = await self._validate_order_risk(order, reference_price)
        if not risk_result.passed:
            order.reject(risk_result.reason)
            self._order_manager.update_order(order)
            logger.warning("OMS rejected order %s by %s: %s", order.order_id, risk_result.rule_name, risk_result.reason)
            return order

        try:
            timestamp = datetime.utcnow()
            executed_order = await self._executor.execute(order, reference_price, timestamp)
            self._order_manager.update_order(executed_order)
            self._record_fill_integrations(executed_order)
            return executed_order
        except Exception as exc:  # pylint: disable=broad-except
            order.reject(f"Execution failed: {exc}")
            self._order_manager.update_order(order)
            logger.exception("OMS execution failed for order %s", order.order_id)
            return order

    async def _validate_order_risk(self, order: Order, reference_price: float) -> RiskCheckResult:
        if not self._config.require_risk_validation:
            result = RiskCheckResult(passed=True, reason="Risk validation disabled", rule_name="disabled")
        else:
            result = await self._risk_validator.validate(order, reference_price)
        self._risk_decisions.append(
            RiskDecision(order_id=order.order_id, passed=result.passed, reason=result.reason, rule_name=result.rule_name)
        )
        return result

    def _record_fill_integrations(self, order: Order) -> None:
        if order.is_filled and order.fill is not None:
            self._risk_validator.record_fill(order.fill)
            if self._position_synchronizer is not None:
                self._position_synchronizer.apply_fill(order.fill, order.symbol)

    def _validate_signal(self, signal: Signal, context: StrategyContext) -> bool:
        if self._config.allowed_symbols is not None and context.symbol not in self._config.allowed_symbols:
            return False
        return True

    def _signal_to_order(self, signal: Signal, context: StrategyContext, reference_price: float) -> Optional[Order]:
        symbol = context.symbol
        if signal.type == SignalType.BUY:
            quantity = self._calculate_entry_quantity(context, reference_price)
            if quantity <= 0:
                return None
            return self._order_manager.create_order(OrderSide.BUY, OrderIntent.ENTRY, quantity, reference_price, symbol)

        if signal.type == SignalType.SELL:
            if context.position_quantity > 0:
                return self._order_manager.create_order(
                    OrderSide.SELL, OrderIntent.EXIT, context.position_quantity, reference_price, symbol
                )

        if signal.type == SignalType.EXIT:
            if context.position_quantity > 0:
                return self._order_manager.create_order(
                    OrderSide.SELL, OrderIntent.EXIT, context.position_quantity, reference_price, symbol
                )
        return None

    def _calculate_entry_quantity(self, context: StrategyContext, price: float) -> float:
        if price <= 0:
            return 0.0
        available = context.cash if context.cash else 0.0
        return (available * self._config.max_position_size) / price

    async def cancel_order(self, order_id: int) -> bool:
        order = self._order_manager.get_order(order_id)
        if order is None or order.status not in (OrderStatus.CREATED, OrderStatus.PENDING):
            return False
        if self._order_synchronizer is not None:
            await self._order_synchronizer.cancel(order)
        elif isinstance(self._executor, LiveExecutor) and self._broker:
            await self._broker.cancel_order(order.broker_order_id or str(order_id), order.symbol)
        if order.status is not OrderStatus.CANCELLED:
            order.cancel()
        self._order_manager.update_order(order)
        return True

    async def synchronize_orders(self) -> list[OrderSyncDecision]:
        if self._order_synchronizer is None:
            return []
        return await self._order_synchronizer.synchronize(self._order_manager.get_active_orders())

    async def recover(self) -> list[OrderSyncDecision]:
        return await self.synchronize_orders()

    async def modify_order(
        self,
        order_id: int,
        *,
        quantity: float | None = None,
        reference_price: float | None = None,
    ) -> bool:
        order = self._order_manager.get_order(order_id)
        if order is None or order.status not in (OrderStatus.CREATED, OrderStatus.PENDING):
            return False
        if self._order_synchronizer is not None:
            await self._order_synchronizer.modify(order, quantity=quantity, reference_price=reference_price)
        elif quantity is not None:
            order.quantity = quantity
        if reference_price is not None:
            order.reference_price = reference_price
        self._order_manager.update_order(order)
        return True

    def get_active_positions(self) -> List[PositionRecord]:
        if self._position_synchronizer is None:
            return []
        return [position for position in self._position_synchronizer.positions.values() if position.quantity > 0]


__all__ = ["OMS", "OMSConfig", "OrderManager", "RiskDecision"]
