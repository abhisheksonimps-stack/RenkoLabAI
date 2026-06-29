"""Reusable strategy risk-management rules.

Rules are deterministic policy objects that evaluate a signal plus runtime
context. They return either the original signal or a safer replacement, without
mutating strategy or portfolio state.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable

from backend.app.trading.signals.models import Signal, SignalType
from backend.app.trading.strategy.interfaces import StrategyContext


class RiskRule(ABC):
    """Base risk rule."""

    @abstractmethod
    def evaluate(self, signal: Signal, context: StrategyContext) -> Signal:
        """Evaluate and possibly transform a signal."""
        raise NotImplementedError


@dataclass(frozen=True)
class StopLossRule(RiskRule):
    """Exit exposure when price breaches the configured stop level."""

    stop_price: float

    def __post_init__(self) -> None:
        if self.stop_price <= 0:
            raise ValueError("stop_price must be positive")

    def evaluate(self, signal: Signal, context: StrategyContext) -> Signal:
        price = context.current_price
        if price is None or not context.has_open_position:
            return signal
        if price <= self.stop_price:
            return Signal(SignalType.EXIT_LONG, price=price, reference=self.stop_price, metadata={"risk_rule": "stop_loss"})
        return signal


@dataclass(frozen=True)
class TakeProfitRule(RiskRule):
    """Exit exposure when price reaches the take-profit level."""

    take_profit_price: float

    def __post_init__(self) -> None:
        if self.take_profit_price <= 0:
            raise ValueError("take_profit_price must be positive")

    def evaluate(self, signal: Signal, context: StrategyContext) -> Signal:
        price = context.current_price
        if price is None or not context.has_open_position:
            return signal
        if price >= self.take_profit_price:
            return Signal(SignalType.EXIT_LONG, price=price, reference=self.take_profit_price, metadata={"risk_rule": "take_profit"})
        return signal


@dataclass
class TrailingStopRule(RiskRule):
    """Stateful trailing-stop rule for long exposure."""

    trail_amount: float | None = None
    trail_percent: float | None = None
    highest_price: float | None = None

    def __post_init__(self) -> None:
        if self.trail_amount is None and self.trail_percent is None:
            raise ValueError("TrailingStopRule requires trail_amount or trail_percent")
        if self.trail_amount is not None and self.trail_amount <= 0:
            raise ValueError("trail_amount must be positive")
        if self.trail_percent is not None and not 0 < self.trail_percent < 1:
            raise ValueError("trail_percent must be between 0 and 1")

    def evaluate(self, signal: Signal, context: StrategyContext) -> Signal:
        price = context.current_price
        if price is None:
            return signal
        if not context.has_open_position:
            self.highest_price = None
            return signal
        self.highest_price = price if self.highest_price is None else max(self.highest_price, price)
        stop_price = self._stop_price()
        if price <= stop_price:
            return Signal(SignalType.EXIT_LONG, price=price, reference=stop_price, metadata={"risk_rule": "trailing_stop"})
        return signal

    def _stop_price(self) -> float:
        high = self.highest_price or 0.0
        if self.trail_amount is not None:
            return high - self.trail_amount
        return high * (1.0 - float(self.trail_percent))


@dataclass(frozen=True)
class MaxDailyLossRule(RiskRule):
    """Block entries and exit exposure when daily realized loss exceeds limit."""

    max_loss: float

    def __post_init__(self) -> None:
        if self.max_loss < 0:
            raise ValueError("max_loss cannot be negative")

    def evaluate(self, signal: Signal, context: StrategyContext) -> Signal:
        daily_pnl_raw = None if context.metadata is None else context.metadata.get("daily_pnl")
        daily_pnl = float(daily_pnl_raw) if daily_pnl_raw is not None else 0.0
        if daily_pnl > -abs(self.max_loss):
            return signal
        price = context.current_price
        if context.has_open_position:
            return Signal(SignalType.EXIT_LONG, price=price, metadata={"risk_rule": "max_daily_loss"})
        if signal.type in (SignalType.BUY, SignalType.SELL):
            return Signal(SignalType.HOLD, price=signal.price, reference=signal.reference, metadata={"risk_rule": "max_daily_loss"})
        return signal


@dataclass(frozen=True)
class MaxOpenPositionsRule(RiskRule):
    """Block new entries when open position count reaches the limit."""

    max_open_positions: int

    def __post_init__(self) -> None:
        if self.max_open_positions < 0:
            raise ValueError("max_open_positions cannot be negative")

    def evaluate(self, signal: Signal, context: StrategyContext) -> Signal:
        if signal.type in (SignalType.BUY, SignalType.SELL) and context.open_positions >= self.max_open_positions:
            return Signal(SignalType.HOLD, price=signal.price, reference=signal.reference, metadata={"risk_rule": "max_open_positions"})
        return signal


class RiskManager:
    """Applies ordered risk rules to a strategy signal."""

    def __init__(self, rules: Iterable[RiskRule] = ()) -> None:
        self._rules = tuple(rules)

    @property
    def rules(self) -> tuple[RiskRule, ...]:
        """Return configured rules."""
        return self._rules

    @property
    def has_rules(self) -> bool:
        """Return whether any risk rules are configured."""
        return bool(self._rules)

    def evaluate(self, signal: Signal, context: StrategyContext) -> Signal:
        """Apply all rules in order."""
        adjusted = signal
        for rule in self._rules:
            adjusted = rule.evaluate(adjusted, context)
        return adjusted


__all__ = [
    "MaxDailyLossRule",
    "MaxOpenPositionsRule",
    "RiskManager",
    "RiskRule",
    "StopLossRule",
    "TakeProfitRule",
    "TrailingStopRule",
]
