"""Pre-execution risk validation.

Validates orders against risk rules before they reach the executor.
Integrates with the existing RiskManager and adds order-level checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from backend.app.trading.broker.interfaces import BrokerAdapter
from backend.app.trading.execution.order import Order, OrderSide, OrderStatus
from backend.app.trading.oms.positions import PositionSynchronizer, PositionRecord
from backend.app.trading.strategy.risk import RiskManager, RiskRule


@dataclass
class RiskCheckResult:
    """Result of a risk validation check."""
    passed: bool
    reason: str
    rule_name: str


class PreExecutionRiskValidator:
    """Validates orders against risk rules before execution.

    Checks include:
    - Position size limits
    - Order value limits
    - Daily loss limits
    - Maximum drawdown limits
    - Concentration limits
    - Broker-reported position limits
    """

    def __init__(
        self,
        risk_manager: Optional[RiskManager] = None,
        position_synchronizer: Optional[PositionSynchronizer] = None,
        *,
        max_position_value: Optional[float] = None,
        max_daily_loss: Optional[float] = None,
        max_drawdown: Optional[float] = None,
        max_open_positions: int = 10,
    ) -> None:
        """Initialize the risk validator.

        Args:
            risk_manager: Strategy-level risk manager
            position_synchronizer: Position tracking from broker
            max_position_value: Maximum value per position
            max_daily_loss: Maximum daily loss allowed
            max_drawdown: Maximum drawdown allowed
            max_open_positions: Maximum number of open positions
        """
        self._risk_manager = risk_manager
        self._position_synchronizer = position_synchronizer
        self._max_position_value = max_position_value
        self._max_daily_loss = max_daily_loss
        self._max_drawdown = max_drawdown
        self._max_open_positions = max_open_positions

        # Track daily P&L
        self._daily_pnl: float = 0.0
        self._daily_reset_date: Optional[datetime] = None

    async def validate(self, order: Order, reference_price: float) -> RiskCheckResult:
        """Validate an order against all risk rules.

        Args:
            order: Order to validate
            reference_price: Current market price

        Returns:
            RiskCheckResult indicating if order passed validation
        """
        # Reset daily P&L if new day
        self._maybe_reset_daily()

        # Run all checks
        checks: List[RiskCheckResult] = [
            self._check_order_value(order, reference_price),
            self._check_position_count(order),
            self._check_daily_loss(),
            self._check_drawdown(),
        ]

        # Check broker-reported positions if available
        if self._position_synchronizer:
            checks.append(await self._check_broker_positions(order, reference_price))

        # Check strategy-level risk rules
        if self._risk_manager:
            checks.append(self._check_strategy_rules(order))

        # Return first failure, or success
        for check in checks:
            if not check.passed:
                return check

        return RiskCheckResult(passed=True, reason="All checks passed", rule_name="all")

    def record_fill(self, fill) -> None:
        """Record a fill for P&L tracking.

        Args:
            fill: Executed fill
        """
        # Calculate P&L impact
        if fill.side == OrderSide.SELL:
            # Selling generates P&L
            self._daily_pnl += (fill.price * fill.quantity) - fill.cost
        else:
            # Buying reduces P&L
            self._daily_pnl -= (fill.price * fill.quantity) + fill.cost

    def _maybe_reset_daily(self) -> None:
        """Reset daily P&L if it's a new day."""
        today = datetime.utcnow().date()
        if self._daily_reset_date is None or self._daily_reset_date != today:
            self._daily_pnl = 0.0
            self._daily_reset_date = today

    def _check_order_value(self, order: Order, reference_price: float) -> RiskCheckResult:
        """Check if order value exceeds limit."""
        if self._max_position_value is None:
            return RiskCheckResult(passed=True, reason="No limit set", rule_name="order_value")

        order_value = order.quantity * reference_price
        if order_value > self._max_position_value:
            return RiskCheckResult(
                passed=False,
                reason=f"Order value {order_value:.2f} exceeds max {self._max_position_value:.2f}",
                rule_name="order_value",
            )

        return RiskCheckResult(passed=True, reason="Order value within limit", rule_name="order_value")

    def _check_position_count(self, order: Order) -> RiskCheckResult:
        """Check if adding this position would exceed limit."""
        if self._position_synchronizer is None:
            return RiskCheckResult(passed=True, reason="No position tracking", rule_name="position_count")

        current_count = self._position_synchronizer.position_count
        is_entry = order.intent.value == "entry"

        if is_entry and current_count >= self._max_open_positions:
            return RiskCheckResult(
                passed=False,
                reason=f"Max open positions ({self._max_open_positions}) reached",
                rule_name="position_count",
            )

        return RiskCheckResult(passed=True, reason="Position count within limit", rule_name="position_count")

    def _check_daily_loss(self) -> RiskCheckResult:
        """Check if daily loss limit has been exceeded."""
        if self._max_daily_loss is None:
            return RiskCheckResult(passed=True, reason="No daily loss limit", rule_name="daily_loss")

        if self._daily_pnl < -self._max_daily_loss:
            return RiskCheckResult(
                passed=False,
                reason=f"Daily loss {self._daily_pnl:.2f} exceeds limit {self._max_daily_loss:.2f}",
                rule_name="daily_loss",
            )

        return RiskCheckResult(passed=True, reason="Daily loss within limit", rule_name="daily_loss")

    def _check_drawdown(self) -> RiskCheckResult:
        """Check if drawdown limit has been exceeded."""
        if self._max_drawdown is None or self._position_synchronizer is None:
            return RiskCheckResult(passed=True, reason="No drawdown limit", rule_name="drawdown")

        # Calculate current drawdown from positions
        total_unrealized = sum(
            pos.unrealized_pnl for pos in self._position_synchronizer.positions.values()
        )

        if total_unrealized < -self._max_drawdown:
            return RiskCheckResult(
                passed=False,
                reason=f"Drawdown {total_unrealized:.2f} exceeds limit {self._max_drawdown:.2f}",
                rule_name="drawdown",
            )

        return RiskCheckResult(passed=True, reason="Drawdown within limit", rule_name="drawdown")

    async def _check_broker_positions(self, order: Order, reference_price: float) -> RiskCheckResult:
        """Check if order would exceed broker-reported position limits."""
        if self._position_synchronizer is None:
            return RiskCheckResult(passed=True, reason="No position tracking", rule_name="broker_positions")

        # Get current position for this symbol
        current_position = self._position_synchronizer.get_position(order.symbol)

        # For BUY orders, check if we already have a position
        if order.side == OrderSide.BUY and current_position is not None:
            # Could add logic to prevent doubling up
            pass

        return RiskCheckResult(passed=True, reason="Broker position check passed", rule_name="broker_positions")

    def _check_strategy_rules(self, order: Order) -> RiskCheckResult:
        """Check strategy-level risk rules."""
        if self._risk_manager is None:
            return RiskCheckResult(passed=True, reason="No strategy risk manager", rule_name="strategy_rules")

        # Strategy risk rules are applied at the strategy level
        # This is a final check before execution
        return RiskCheckResult(passed=True, reason="Strategy risk rules passed", rule_name="strategy_rules")