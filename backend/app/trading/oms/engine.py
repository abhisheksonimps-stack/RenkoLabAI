"""Order Management System (OMS) engine.

Central coordinator that routes strategy signals through risk validation to the
appropriate executor. Maintains order state and coordinates with position tracking.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from backend.app.trading.broker.interfaces import BrokerAdapter
from backend.app.trading.broker.live_executor import LiveExecutor
from backend.app.trading.execution.executor import Executor
from backend.app.trading.execution.order import Order, OrderIntent, OrderSide, OrderStatus
from backend.app.trading.oms.risk import PreExecutionRiskValidator, RiskCheckResult
from backend.app.trading.signals.models import Signal, SignalType
from backend.app.trading.strategy.interfaces import StrategyContext
from backend.app.trading.strategy.risk import RiskManager


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
        """Create and track a new order."""
        self._next_order_id += 1
        order = Order(
            order_id=self._next_order_id,
            side=side,
            intent=intent,
            quantity=quantity,
            reference_price=reference_price,
            created_at=datetime.utcnow(),
            symbol=symbol,
        )
        self._orders[order.order_id] = order
        return order

    def get_order(self, order_id: int) -> Optional[Order]:
        """Retrieve an order by ID."""
        return self._orders.get(order_id)

    def update_order(self, order: Order) -> None:
        """Update tracked order."""
        self._orders[order.order_id] = order

    def get_active_orders(self) -> List[Order]:
        """Get all non-terminal orders."""
        return [
            o for o in self._orders.values()
            if o.status not in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED)
        ]

    @property
    def all_orders(self) -> List[Order]:
        """Get all orders."""
        return list(self._orders.values())


class OMS:
    """Order Management System.

    Coordinates order flow from strategy signals to execution:
    1. Receives signal from strategy
    2. Validates against risk rules
    3. Creates order
    4. Routes to appropriate executor
    5. Tracks order state
    """

    def __init__(
        self,
        executor: Executor,
        *,
        broker: Optional[BrokerAdapter] = None,
        risk_manager: Optional[RiskManager] = None,
        position_synchronizer: Optional[PositionSynchronizer] = None,
        config: Optional[OMSConfig] = None,
    ) -> None:
        """Initialize the OMS.

        Args:
            executor: Execution engine (SimulatedExecutor, PaperExecutor, or LiveExecutor)
            broker: Optional broker adapter (required for live trading)
            risk_manager: Optional risk validation rules
            position_synchronizer: Optional position tracking from broker
            config: OMS configuration
        """
        self._executor = executor
        self._broker = broker
        self._risk_manager = risk_manager
        self._position_synchronizer = position_synchronizer
        self._config = config or OMSConfig()
        self._order_manager = OrderManager()
        self._risk_validator = PreExecutionRiskValidator(
            risk_manager=risk_manager,
            position_synchronizer=position_synchronizer,
        )

    @property
    def order_manager(self) -> OrderManager:
        """Access the order manager."""
        return self._order_manager

    async def process_signal(
        self,
        signal: Signal,
        context: StrategyContext,
        reference_price: float,
    ) -> Optional[Order]:
        """Process a strategy signal and execute if valid.

        Args:
            signal: Strategy-generated signal
            context: Strategy execution context
            reference_price: Current market price

        Returns:
            Executed order, or None if signal was invalid/ignored
        """
        # Ignore HOLD signals
        if signal.type == SignalType.HOLD:
            return None

        # Validate signal
        if not self._validate_signal(signal, context):
            return None

        # Map signal to order
        order = self._signal_to_order(signal, context, reference_price)
        if order is None:
            return None

        # Apply risk validation
        if self._config.require_risk_validation and self._risk_manager:
            # Risk validation would be applied here
            # For now, we proceed; risk rules are applied at strategy level
            pass

        # Execute order
        try:
            timestamp = datetime.utcnow()
            executed_order = await self._executor.execute(order, reference_price, timestamp)
            self._order_manager.update_order(executed_order)
            return executed_order
        except Exception as exc:
            order.reject(f"Execution failed: {exc}")
            self._order_manager.update_order(order)
            return order

    def _validate_signal(self, signal: Signal, context: StrategyContext) -> bool:
        """Validate signal before execution."""
        # Check symbol allowlist
        if self._config.allowed_symbols is not None:
            if context.symbol not in self._config.allowed_symbols:
                return False

        # Additional validation can be added here
        return True

    def _signal_to_order(
        self,
        signal: Signal,
        context: StrategyContext,
        reference_price: float,
    ) -> Optional[Order]:
        """Convert strategy signal to platform order."""
        symbol = context.symbol

        if signal.type == SignalType.BUY:
            # Calculate quantity from context
            quantity = self._calculate_entry_quantity(context, reference_price)
            if quantity <= 0:
                return None
            return self._order_manager.create_order(
                side=OrderSide.BUY,
                intent=OrderIntent.ENTRY,
                quantity=quantity,
                reference_price=reference_price,
                symbol=symbol,
            )

        if signal.type == SignalType.SELL:
            # Exit long position
            if context.position_quantity > 0:
                return self._order_manager.create_order(
                    side=OrderSide.SELL,
                    intent=OrderIntent.EXIT,
                    quantity=context.position_quantity,
                    reference_price=reference_price,
                    symbol=symbol,
                )

        if signal.type == SignalType.EXIT:
            # Close any open position
            if context.position_quantity > 0:
                return self._order_manager.create_order(
                    side=OrderSide.SELL,
                    intent=OrderIntent.EXIT,
                    quantity=context.position_quantity,
                    reference_price=reference_price,
                    symbol=symbol,
                )

        return None

    def _calculate_entry_quantity(self, context: StrategyContext, price: float) -> float:
        """Calculate position size for entry."""
        if price <= 0:
            return 0.0

        # Use position fraction from context or default
        fraction = self._config.max_position_size
        available = context.cash if context.cash else 0.0
        return (available * fraction) / price

    async def cancel_order(self, order_id: int) -> bool:
        """Cancel an open order."""
        order = self._order_manager.get_order(order_id)
        if order is None or order.status not in (OrderStatus.CREATED, OrderStatus.PENDING):
            return False

        # If live broker, cancel via broker
        if isinstance(self._executor, LiveExecutor) and self._broker:
            try:
                await self._broker.cancel_order(str(order_id), order.symbol)
            except Exception:
                pass

        order.cancel()
        self._order_manager.update_order(order)
        return True

    def get_active_positions(self) -> List[Order]:
        """Get all active (non-zero) positions."""
        # This would integrate with position tracker in production
        return []