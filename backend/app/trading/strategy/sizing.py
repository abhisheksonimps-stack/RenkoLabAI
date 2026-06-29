"""Position sizing models for strategies.

Sizing components are pure, reusable policy objects. They do not submit orders
or mutate portfolios; engines call them to determine quantities before routing
signals into execution.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from math import floor


class PositionSizingMethod(str, Enum):
    """Supported position sizing policies."""

    FIXED_QUANTITY = "fixed_quantity"
    FIXED_RISK_PERCENT = "fixed_risk_percent"
    ATR = "atr"
    KELLY = "kelly"


@dataclass(frozen=True)
class PositionSizingContext:
    """Inputs required by position sizing policies."""

    equity: float
    price: float
    stop_price: float | None = None
    atr: float | None = None
    win_rate: float | None = None
    payoff_ratio: float | None = None
    metadata: dict[str, float | int | str | bool | None] | None = None

    def __post_init__(self) -> None:
        if self.equity < 0:
            raise ValueError("equity cannot be negative")
        if self.price <= 0:
            raise ValueError("price must be positive")
        if self.stop_price is not None and self.stop_price <= 0:
            raise ValueError("stop_price must be positive when supplied")
        if self.atr is not None and self.atr <= 0:
            raise ValueError("atr must be positive when supplied")
        if self.win_rate is not None and not 0 <= self.win_rate <= 1:
            raise ValueError("win_rate must be between 0 and 1")
        if self.payoff_ratio is not None and self.payoff_ratio <= 0:
            raise ValueError("payoff_ratio must be positive when supplied")


class PositionSizer(ABC):
    """Abstract position sizing policy."""

    method: PositionSizingMethod

    @abstractmethod
    def size(self, context: PositionSizingContext) -> float:
        """Return the quantity to trade for the supplied context."""
        raise NotImplementedError


@dataclass(frozen=True)
class FixedQuantitySizer(PositionSizer):
    """Always return the configured quantity."""

    quantity: float
    method: PositionSizingMethod = PositionSizingMethod.FIXED_QUANTITY

    def __post_init__(self) -> None:
        if self.quantity < 0:
            raise ValueError("quantity cannot be negative")

    def size(self, context: PositionSizingContext) -> float:
        return float(self.quantity)


@dataclass(frozen=True)
class FixedRiskPercentSizer(PositionSizer):
    """Size by risking a fixed fraction of account equity to the stop."""

    risk_percent: float
    round_down: bool = False
    method: PositionSizingMethod = PositionSizingMethod.FIXED_RISK_PERCENT

    def __post_init__(self) -> None:
        if not 0 <= self.risk_percent <= 1:
            raise ValueError("risk_percent must be between 0 and 1")

    def size(self, context: PositionSizingContext) -> float:
        if context.stop_price is None:
            raise ValueError("FixedRiskPercentSizer requires stop_price")
        risk_per_unit = abs(context.price - context.stop_price)
        if risk_per_unit <= 0:
            return 0.0
        quantity = (context.equity * self.risk_percent) / risk_per_unit
        return float(floor(quantity) if self.round_down else quantity)


@dataclass(frozen=True)
class ATRPositionSizer(PositionSizer):
    """Size positions using ATR as the stop-distance proxy."""

    risk_percent: float
    atr_multiple: float = 1.0
    round_down: bool = False
    method: PositionSizingMethod = PositionSizingMethod.ATR

    def __post_init__(self) -> None:
        if not 0 <= self.risk_percent <= 1:
            raise ValueError("risk_percent must be between 0 and 1")
        if self.atr_multiple <= 0:
            raise ValueError("atr_multiple must be positive")

    def size(self, context: PositionSizingContext) -> float:
        if context.atr is None:
            raise ValueError("ATRPositionSizer requires atr")
        risk_per_unit = context.atr * self.atr_multiple
        if risk_per_unit <= 0:
            return 0.0
        quantity = (context.equity * self.risk_percent) / risk_per_unit
        return float(floor(quantity) if self.round_down else quantity)


@dataclass(frozen=True)
class KellySizer(PositionSizer):
    """Fractional Kelly extension point implemented as a pure sizing policy."""

    max_fraction: float = 1.0
    fraction: float = 1.0
    method: PositionSizingMethod = PositionSizingMethod.KELLY

    def __post_init__(self) -> None:
        if not 0 <= self.max_fraction <= 1:
            raise ValueError("max_fraction must be between 0 and 1")
        if not 0 <= self.fraction <= 1:
            raise ValueError("fraction must be between 0 and 1")

    def size(self, context: PositionSizingContext) -> float:
        if context.win_rate is None or context.payoff_ratio is None:
            raise ValueError("KellySizer requires win_rate and payoff_ratio")
        loss_rate = 1.0 - context.win_rate
        raw_fraction = context.win_rate - (loss_rate / context.payoff_ratio)
        kelly_fraction = max(0.0, min(raw_fraction * self.fraction, self.max_fraction))
        return (context.equity * kelly_fraction) / context.price


class PositionSizerFactory:
    """Create sizing policies from stable names."""

    def create(self, method: PositionSizingMethod | str, **kwargs: float | bool) -> PositionSizer:
        resolved = PositionSizingMethod(method)
        if resolved is PositionSizingMethod.FIXED_QUANTITY:
            return FixedQuantitySizer(quantity=float(kwargs.get("quantity", 0.0)))
        if resolved is PositionSizingMethod.FIXED_RISK_PERCENT:
            return FixedRiskPercentSizer(
                risk_percent=float(kwargs.get("risk_percent", 0.01)),
                round_down=bool(kwargs.get("round_down", False)),
            )
        if resolved is PositionSizingMethod.ATR:
            return ATRPositionSizer(
                risk_percent=float(kwargs.get("risk_percent", 0.01)),
                atr_multiple=float(kwargs.get("atr_multiple", 1.0)),
                round_down=bool(kwargs.get("round_down", False)),
            )
        return KellySizer(
            max_fraction=float(kwargs.get("max_fraction", 1.0)),
            fraction=float(kwargs.get("fraction", 1.0)),
        )


__all__ = [
    "ATRPositionSizer",
    "FixedQuantitySizer",
    "FixedRiskPercentSizer",
    "KellySizer",
    "PositionSizer",
    "PositionSizerFactory",
    "PositionSizingContext",
    "PositionSizingMethod",
]
