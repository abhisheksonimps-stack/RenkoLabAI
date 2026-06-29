"""Strategy framework interfaces.

Sprint 8 expands the original brick-only strategy contract into a reusable
strategy SDK while preserving the Sprint T1/T2 backtesting API. Existing
strategies that implement ``initialize()``, ``on_brick()``, ``generate_signal()``
and ``reset()`` remain valid Strategy subclasses. New strategies may also use
context-aware lifecycle hooks and return ``StrategyResult`` objects for richer
paper/backtest integration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping, Protocol, TYPE_CHECKING, TypeAlias, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.marketdata.models import MarketBar
from backend.app.trading.signals.models import Signal, SignalType

if TYPE_CHECKING:
    from backend.app.trading.execution.order import Fill
    from backend.app.trading.execution.position import Trade

StrategyParameterValue: TypeAlias = str | int | float | bool | Decimal | None
StrategyMetadataValue: TypeAlias = str | int | float | bool | Decimal | datetime | None


@runtime_checkable
class SignalInterface(Protocol):
    """Protocol implemented by strategy signal objects."""

    type: SignalType

    @property
    def is_actionable(self) -> bool:
        """Return whether this signal should become an execution decision."""
        raise NotImplementedError


class StrategyConfiguration(BaseModel):
    """Immutable strategy configuration.

    ``name`` is the registry key. ``parameters`` contains strategy-specific
    validated inputs. The strategy framework keeps parameters typed as scalar
    values so configurations remain stable across API, backtest, and paper
    trading boundaries.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    parameters: Mapping[str, StrategyParameterValue] = Field(default_factory=dict)
    metadata: Mapping[str, StrategyMetadataValue] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("strategy configuration name cannot be blank")
        return normalized

    @field_validator("parameters", "metadata", mode="before")
    @classmethod
    def _normalize_mapping(cls, value: Mapping[str, Any] | None) -> dict[str, Any]:
        if value is None:
            return {}
        return {str(key): item for key, item in value.items()}

    def parameter(self, name: str, default: StrategyParameterValue = None) -> StrategyParameterValue:
        """Return a configuration parameter by name."""
        return self.parameters.get(name, default)


class StrategyContext(BaseModel):
    """Immutable runtime context supplied to strategy lifecycle hooks."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True, extra="forbid")

    symbol: str = Field(min_length=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    configuration: StrategyConfiguration | None = None
    market_data: "MarketBar | None" = None
    brick: Any | None = None
    tick: Mapping[str, StrategyParameterValue] | None = None
    current_price: float | None = None
    cash: float | None = None
    equity: float | None = None
    position_quantity: float = 0.0
    open_positions: int = 0
    metadata: Mapping[str, StrategyMetadataValue] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("strategy context symbol cannot be blank")
        return normalized

    @field_validator("current_price", "cash", "equity")
    @classmethod
    def _validate_optional_non_negative_float(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("monetary and price context values cannot be negative")
        return value

    @field_validator("position_quantity")
    @classmethod
    def _validate_position_quantity(cls, value: float) -> float:
        if value < 0:
            raise ValueError("position_quantity cannot be negative")
        return value

    @field_validator("open_positions")
    @classmethod
    def _validate_open_positions(cls, value: int) -> int:
        if value < 0:
            raise ValueError("open_positions cannot be negative")
        return value

    @field_validator("tick", "metadata", mode="before")
    @classmethod
    def _normalize_optional_mapping(cls, value: Mapping[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        return {str(key): item for key, item in value.items()}

    @model_validator(mode="after")
    def _derive_price_when_available(self) -> StrategyContext:
        if self.current_price is not None:
            return self

        derived_price: float | None = None
        if self.brick is not None and hasattr(self.brick, "close_price"):
            derived_price = float(getattr(self.brick, "close_price"))
        elif self.market_data is not None:
            derived_price = float(self.market_data.close)
        elif self.tick is not None and "price" in self.tick and self.tick["price"] is not None:
            derived_price = float(self.tick["price"])

        if derived_price is not None:
            object.__setattr__(self, "current_price", derived_price)
        return self

    @property
    def has_open_position(self) -> bool:
        """Return whether the context represents open exposure."""
        return self.position_quantity > 0 or self.open_positions > 0


class StrategyResult(BaseModel):
    """Immutable result produced by a strategy lifecycle hook."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True, extra="forbid")

    signal: Signal
    context: StrategyContext | None = None
    confidence: float | None = None
    diagnostics: Mapping[str, StrategyMetadataValue] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("confidence")
    @classmethod
    def _validate_confidence(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if value < 0 or value > 1:
            raise ValueError("strategy result confidence must be between 0 and 1")
        return value

    @field_validator("diagnostics", mode="before")
    @classmethod
    def _normalize_diagnostics(cls, value: Mapping[str, Any] | None) -> dict[str, Any]:
        if value is None:
            return {}
        return {str(key): item for key, item in value.items()}

    @property
    def is_actionable(self) -> bool:
        """Return whether the contained signal is actionable."""
        return self.signal.is_actionable

    @classmethod
    def hold(cls, context: StrategyContext | None = None) -> StrategyResult:
        """Create a HOLD result for no-action lifecycle events."""
        return cls(signal=Signal(type=SignalType.HOLD), context=context)


class Strategy(ABC):
    """Base strategy interface.

    The four original abstract methods are retained for backward compatibility
    with the existing backtesting engine. Context-aware lifecycle methods are
    concrete extension points so Sprint T1/T2 strategies continue to compile
    without modification.
    """

    name: str = "strategy"

    @abstractmethod
    def initialize(self) -> None:
        """Prepare the strategy for a fresh run."""
        raise NotImplementedError

    def on_market_data(self, bar: "MarketBar", context: StrategyContext | None = None) -> StrategyResult:
        """Consume normalized OHLC market data."""
        return StrategyResult.hold(context)

    @abstractmethod
    def on_brick(self, brick: Any) -> None:
        """Consume one completed Renko brick."""
        raise NotImplementedError

    def on_tick(
        self,
        tick: Mapping[str, StrategyParameterValue],
        context: StrategyContext | None = None,
    ) -> StrategyResult:
        """Consume one tick-level market update."""
        return StrategyResult.hold(context)

    def on_order_fill(self, fill: "Fill", context: StrategyContext | None = None) -> StrategyResult:
        """React to an execution fill notification."""
        return StrategyResult.hold(context)

    def on_position_close(self, trade: "Trade", context: StrategyContext | None = None) -> StrategyResult:
        """React to a completed position close notification."""
        return StrategyResult.hold(context)

    @abstractmethod
    def generate_signal(self) -> Signal:
        """Return the signal for the most recently consumed market event."""
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        """Reset all internal state to the initial condition."""
        raise NotImplementedError

    def shutdown(self) -> None:
        """Release strategy resources at the end of a run."""
        self.reset()

    def result(self, context: StrategyContext | None = None) -> StrategyResult:
        """Return the current signal wrapped in a StrategyResult."""
        return StrategyResult(signal=self.generate_signal(), context=context)


__all__ = [
    "SignalInterface",
    "Strategy",
    "StrategyConfiguration",
    "StrategyContext",
    "StrategyMetadataValue",
    "StrategyParameterValue",
    "StrategyResult",
]
