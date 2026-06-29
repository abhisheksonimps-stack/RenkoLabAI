"""Analytics domain value objects.

Immutable value objects for the Analytics bounded context.

The analytics layer intentionally keeps these objects independent from
persistence, API schemas, and rendering concerns. They are Pydantic v2 models
with frozen state, strict validation, and no side effects.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import ClassVar, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


_MONEY_QUANTUM = Decimal("0.01")
_PERCENT_QUANTUM = Decimal("0.01")
_ZERO = Decimal("0")
_ONE = Decimal("1")


class AnalyticsValueObject(BaseModel):
    """Base class for immutable analytics value objects."""

    model_config = ConfigDict(
        frozen=True,
        strict=True,
        extra="forbid",
    )


class Money(AnalyticsValueObject):
    """Immutable monetary value with ISO 4217 currency support."""

    amount: Decimal
    currency: str

    @field_validator("amount")
    @classmethod
    def _validate_amount(cls, value: Decimal) -> Decimal:
        if not isinstance(value, Decimal):
            raise ValueError(
                f"Money amount must be Decimal, got {type(value).__name__}"
            )
        if value.is_nan():
            raise ValueError("Money amount cannot be NaN")
        if value.is_infinite():
            raise ValueError("Money amount cannot be infinite")
        return value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError(f"Invalid ISO 4217 currency code: {value!r}")
        return normalized

    @classmethod
    def zero(cls, currency: str) -> Self:
        """Create a zero monetary amount for the supplied currency."""
        return cls(amount=Decimal("0.00"), currency=currency)

    def _assert_same_currency(self, other: Money, operation: str) -> None:
        if self.currency != other.currency:
            raise ValueError(
                f"Cannot {operation} Money with different currencies: "
                f"{self.currency} vs {other.currency}"
            )

    @staticmethod
    def _coerce_scalar(value: Decimal | float | int) -> Decimal:
        if isinstance(value, bool):
            raise ValueError("Money scalar cannot be a boolean")
        if not isinstance(value, (Decimal, float, int)):
            raise ValueError(
                f"Money scalar must be Decimal, float, or int, got "
                f"{type(value).__name__}"
            )
        scalar = Decimal(str(value))
        if scalar.is_nan():
            raise ValueError("Money scalar cannot be NaN")
        if scalar.is_infinite():
            raise ValueError("Money scalar cannot be infinite")
        return scalar

    def __add__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_same_currency(other, "add")
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_same_currency(other, "subtract")
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def __mul__(self, other: Decimal | float | int) -> Money:
        scalar = self._coerce_scalar(other)
        return Money(amount=self.amount * scalar, currency=self.currency)

    def __rmul__(self, other: Decimal | float | int) -> Money:
        return self.__mul__(other)

    def __truediv__(self, other: Decimal | float | int) -> Money:
        scalar = self._coerce_scalar(other)
        if scalar == _ZERO:
            raise ValueError("Cannot divide Money by zero")
        return Money(amount=self.amount / scalar, currency=self.currency)

    def __neg__(self) -> Money:
        return Money(amount=-self.amount, currency=self.currency)

    def __abs__(self) -> Money:
        return Money(amount=abs(self.amount), currency=self.currency)

    def __lt__(self, other: Money) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_same_currency(other, "compare")
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_same_currency(other, "compare")
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_same_currency(other, "compare")
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_same_currency(other, "compare")
        return self.amount >= other.amount

    def __hash__(self) -> int:
        return hash((self.amount, self.currency))

    def __str__(self) -> str:
        return f"{self.currency} {self.amount}"

    def is_zero(self) -> bool:
        """Return whether this amount is exactly zero."""
        return self.amount == Decimal("0.00")

    def is_positive(self) -> bool:
        """Return whether this amount is greater than zero."""
        return self.amount > _ZERO

    def is_negative(self) -> bool:
        """Return whether this amount is less than zero."""
        return self.amount < _ZERO

    def to_decimal(self) -> Decimal:
        """Return the monetary amount as Decimal."""
        return self.amount

    def to_float(self) -> float:
        """Return the monetary amount as float."""
        return float(self.amount)


class Percentage(AnalyticsValueObject):
    """Immutable percentage stored as a decimal fraction.

    A value of Decimal("0.25") represents 25%.
    """

    value: Decimal

    @field_validator("value")
    @classmethod
    def _validate_value(cls, value: Decimal) -> Decimal:
        if not isinstance(value, Decimal):
            raise ValueError(
                f"Percentage value must be Decimal, got {type(value).__name__}"
            )
        if value.is_nan():
            raise ValueError("Percentage value cannot be NaN")
        if value.is_infinite():
            raise ValueError("Percentage value cannot be infinite")
        return value

    @classmethod
    def zero(cls) -> Self:
        """Create a zero percentage."""
        return cls(value=_ZERO)

    @classmethod
    def from_fraction(
        cls,
        numerator: Decimal | float | int,
        denominator: Decimal | float | int,
    ) -> Self:
        """Create a percentage from ``numerator / denominator``."""
        denom = Decimal(str(denominator))
        if denom == _ZERO:
            raise ValueError("Cannot create Percentage with zero denominator")
        return cls(value=Decimal(str(numerator)) / denom)

    @classmethod
    def from_percent(cls, percent: Decimal | float | int) -> Self:
        """Create a percentage from human percent form.

        Example: ``25`` becomes ``Decimal("0.25")``.
        """
        return cls(value=Decimal(str(percent)) / Decimal("100"))

    def to_percent(self) -> Decimal:
        """Return human percent form quantized to two decimal places."""
        return (self.value * Decimal("100")).quantize(_PERCENT_QUANTUM)

    def to_decimal(self) -> Decimal:
        """Return the raw decimal fraction."""
        return self.value

    def to_float(self) -> float:
        """Return the raw decimal fraction as float."""
        return float(self.value)

    def is_zero(self) -> bool:
        """Return whether the percentage is zero."""
        return self.value == _ZERO

    def is_positive(self) -> bool:
        """Return whether the percentage is positive."""
        return self.value > _ZERO

    def is_negative(self) -> bool:
        """Return whether the percentage is negative."""
        return self.value < _ZERO

    def __add__(self, other: Percentage) -> Percentage:
        if not isinstance(other, Percentage):
            return NotImplemented
        return Percentage(value=self.value + other.value)

    def __sub__(self, other: Percentage) -> Percentage:
        if not isinstance(other, Percentage):
            return NotImplemented
        return Percentage(value=self.value - other.value)

    def __neg__(self) -> Percentage:
        return Percentage(value=-self.value)

    def __abs__(self) -> Percentage:
        return Percentage(value=abs(self.value))

    def __lt__(self, other: Percentage) -> bool:
        if not isinstance(other, Percentage):
            return NotImplemented
        return self.value < other.value

    def __le__(self, other: Percentage) -> bool:
        if not isinstance(other, Percentage):
            return NotImplemented
        return self.value <= other.value

    def __gt__(self, other: Percentage) -> bool:
        if not isinstance(other, Percentage):
            return NotImplemented
        return self.value > other.value

    def __ge__(self, other: Percentage) -> bool:
        if not isinstance(other, Percentage):
            return NotImplemented
        return self.value >= other.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __str__(self) -> str:
        return f"{self.to_percent()}%"


class ReturnPeriod(str, Enum):
    """Supported return calculation periods."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ANNUAL = "annual"


class EquityPoint(AnalyticsValueObject):
    """A single point on an analytics equity curve."""

    timestamp: datetime
    equity: Money
    realized_pnl: Money
    unrealized_pnl: Money

    @model_validator(mode="after")
    def _validate_currencies(self) -> Self:
        currencies = {
            self.equity.currency,
            self.realized_pnl.currency,
            self.unrealized_pnl.currency,
        }
        if len(currencies) != 1:
            raise ValueError(
                f"All monetary values must use the same currency, got: {currencies}"
            )
        return self

    @property
    def total_pnl(self) -> Money:
        """Return realized plus unrealized PnL."""
        return self.realized_pnl + self.unrealized_pnl

    @property
    def timestamp_ms(self) -> int:
        """Return timestamp as milliseconds since the Unix epoch."""
        return int(self.timestamp.timestamp() * 1000)

    @property
    def currency(self) -> str:
        """Return the currency shared by all monetary fields."""
        return self.equity.currency

    def __str__(self) -> str:
        return f"EquityPoint({self.timestamp.isoformat()}, equity={self.equity})"


class DrawdownPoint(AnalyticsValueObject):
    """A single point on a drawdown curve."""

    timestamp: datetime
    drawdown: Percentage
    peak_equity: Money
    current_equity: Money
    peak_timestamp: datetime

    @model_validator(mode="after")
    def _validate_drawdown(self) -> Self:
        if self.drawdown.is_positive():
            raise ValueError("Drawdown must be negative or zero")
        if self.peak_timestamp > self.timestamp:
            raise ValueError("peak_timestamp must be before or equal to timestamp")
        if self.peak_equity.currency != self.current_equity.currency:
            raise ValueError(
                "peak_equity and current_equity must have the same currency"
            )
        if self.current_equity > self.peak_equity:
            raise ValueError("current_equity cannot exceed peak_equity in drawdown")
        return self

    @property
    def drawdown_amount(self) -> Money:
        """Return peak equity less current equity."""
        return self.peak_equity - self.current_equity

    @property
    def duration_days(self) -> int:
        """Return number of whole days since the peak."""
        return (self.timestamp - self.peak_timestamp).days

    @property
    def is_in_drawdown(self) -> bool:
        """Return whether this point is below peak equity."""
        return self.drawdown.is_negative()

    @property
    def is_at_peak(self) -> bool:
        """Return whether this point has no drawdown."""
        return self.drawdown.is_zero()

    def __str__(self) -> str:
        return (
            f"DrawdownPoint({self.timestamp.isoformat()}, "
            f"drawdown={self.drawdown}, duration={self.duration_days}d)"
        )


class ReturnSeries(AnalyticsValueObject):
    """Immutable series of periodic returns."""

    period: ReturnPeriod
    returns: tuple[Percentage, ...]
    start_timestamp: datetime
    end_timestamp: datetime

    _PERIODS_PER_YEAR: ClassVar[dict[ReturnPeriod, int]] = {
        ReturnPeriod.DAILY: 252,
        ReturnPeriod.WEEKLY: 52,
        ReturnPeriod.MONTHLY: 12,
        ReturnPeriod.ANNUAL: 1,
    }

    @model_validator(mode="after")
    def _validate_timestamps(self) -> Self:
        if self.start_timestamp > self.end_timestamp:
            raise ValueError(
                f"start_timestamp ({self.start_timestamp}) must be before or "
                f"equal to end_timestamp ({self.end_timestamp})"
            )
        return self

    @property
    def count(self) -> int:
        """Return number of observations."""
        return len(self.returns)

    @property
    def is_empty(self) -> bool:
        """Return whether the series has no observations."""
        return len(self.returns) == 0

    @property
    def mean(self) -> Percentage:
        """Return arithmetic mean of returns."""
        if not self.returns:
            return Percentage.zero()
        total = sum((item.to_decimal() for item in self.returns), _ZERO)
        return Percentage(value=total / Decimal(len(self.returns)))

    @property
    def standard_deviation(self) -> Percentage:
        """Return sample standard deviation of returns."""
        if len(self.returns) < 2:
            return Percentage.zero()
        mean_value = self.mean.to_decimal()
        sum_squared_diff = sum(
            ((item.to_decimal() - mean_value) ** 2 for item in self.returns),
            _ZERO,
        )
        variance = sum_squared_diff / Decimal(len(self.returns) - 1)
        return Percentage(value=variance.sqrt())

    @property
    def cumulative(self) -> Percentage:
        """Return geometrically compounded cumulative return."""
        if not self.returns:
            return Percentage.zero()
        cumulative = _ONE
        for item in self.returns:
            cumulative *= _ONE + item.to_decimal()
        return Percentage(value=cumulative - _ONE)

    @property
    def positive_returns(self) -> tuple[Percentage, ...]:
        """Return positive observations."""
        return tuple(item for item in self.returns if item.is_positive())

    @property
    def negative_returns(self) -> tuple[Percentage, ...]:
        """Return negative observations."""
        return tuple(item for item in self.returns if item.is_negative())

    @property
    def positive_count(self) -> int:
        """Return positive observation count."""
        return len(self.positive_returns)

    @property
    def negative_count(self) -> int:
        """Return negative observation count."""
        return len(self.negative_returns)

    def periods_per_year(self) -> int:
        """Return annualization periods for the series period."""
        return self._PERIODS_PER_YEAR[self.period]

    def __len__(self) -> int:
        return len(self.returns)

    def __getitem__(self, index: int) -> Percentage:
        return self.returns[index]

    def __str__(self) -> str:
        return f"ReturnSeries(period={self.period.value}, count={self.count})"


class ValueAtRisk(AnalyticsValueObject):
    """Value at Risk estimate at a confidence level and time horizon."""

    value: Percentage
    confidence_level: Percentage
    time_horizon_days: int

    @model_validator(mode="after")
    def _validate_var(self) -> Self:
        confidence_level = self.confidence_level.to_decimal()
        if confidence_level <= _ZERO or confidence_level >= _ONE:
            raise ValueError(
                "confidence_level must be between 0 and 1 exclusive, "
                f"got {confidence_level}"
            )
        if self.value.is_positive():
            raise ValueError(f"VaR value must be negative or zero, got {self.value}")
        if self.time_horizon_days <= 0:
            raise ValueError(
                "time_horizon_days must be positive, "
                f"got {self.time_horizon_days}"
            )
        return self

    @property
    def loss_amount(self) -> Percentage:
        """Return VaR magnitude as a positive percentage."""
        return Percentage(value=abs(self.value.to_decimal()))

    def __str__(self) -> str:
        return (
            f"VaR({self.confidence_level.to_percent()}%, "
            f"{self.time_horizon_days}d)={self.value}"
        )


class ConditionalValueAtRisk(AnalyticsValueObject):
    """Conditional Value at Risk / Expected Shortfall estimate."""

    value: Percentage
    confidence_level: Percentage
    time_horizon_days: int

    @model_validator(mode="after")
    def _validate_cvar(self) -> Self:
        confidence_level = self.confidence_level.to_decimal()
        if confidence_level <= _ZERO or confidence_level >= _ONE:
            raise ValueError(
                "confidence_level must be between 0 and 1 exclusive, "
                f"got {confidence_level}"
            )
        if self.value.is_positive():
            raise ValueError(f"CVaR value must be negative or zero, got {self.value}")
        if self.time_horizon_days <= 0:
            raise ValueError(
                "time_horizon_days must be positive, "
                f"got {self.time_horizon_days}"
            )
        return self

    @property
    def expected_shortfall(self) -> Percentage:
        """Return the CVaR value."""
        return self.value

    @property
    def loss_amount(self) -> Percentage:
        """Return expected shortfall magnitude as a positive percentage."""
        return Percentage(value=abs(self.value.to_decimal()))

    def __str__(self) -> str:
        return (
            f"CVaR({self.confidence_level.to_percent()}%, "
            f"{self.time_horizon_days}d)={self.value}"
        )


class ReturnMetrics(AnalyticsValueObject):
    """Immutable collection of return-related performance metrics."""

    total_return: Percentage
    daily_return: Percentage
    weekly_return: Percentage
    monthly_return: Percentage
    annual_return: Percentage
    cagr: Percentage
    roi: Percentage


class RiskMetrics(AnalyticsValueObject):
    """Immutable collection of risk-related performance metrics."""

    sharpe_ratio: Decimal
    sortino_ratio: Decimal
    calmar_ratio: Decimal
    treynor_ratio: Decimal | None
    information_ratio: Decimal | None
    maximum_drawdown: Percentage
    average_drawdown: Percentage
    drawdown_duration_days: int
    volatility: Percentage
    beta: Decimal | None
    alpha: Percentage | None
    ulcer_index: Percentage
    mar_ratio: Decimal
    var_95: ValueAtRisk | None
    cvar_95: ConditionalValueAtRisk | None

    @model_validator(mode="after")
    def _validate_risk_metrics(self) -> Self:
        if self.maximum_drawdown.is_positive():
            raise ValueError("maximum_drawdown must be negative or zero")
        if self.average_drawdown.is_positive():
            raise ValueError("average_drawdown must be negative or zero")
        if self.drawdown_duration_days < 0:
            raise ValueError("drawdown_duration_days cannot be negative")
        if self.volatility.is_negative():
            raise ValueError("volatility must be non-negative")
        if self.ulcer_index.is_negative():
            raise ValueError("ulcer_index must be non-negative")
        return self


class TradeMetrics(AnalyticsValueObject):
    """Immutable collection of trade-related performance metrics."""

    profit_factor: Decimal
    recovery_factor: Decimal
    payoff_ratio: Decimal
    expectancy: Money
    win_rate: Percentage
    loss_rate: Percentage
    gross_profit: Money
    gross_loss: Money
    net_profit: Money
    realized_pnl: Money
    unrealized_pnl: Money
    average_win: Money
    average_loss: Money
    largest_win: Money
    largest_loss: Money
    consecutive_wins: int
    consecutive_losses: int
    max_consecutive_wins: int
    max_consecutive_losses: int
    average_holding_time: float
    exposure: Percentage
    trade_count: int
    long_trades: int
    short_trades: int
    commission: Money
    slippage: Money

    @model_validator(mode="after")
    def _validate_trade_metrics(self) -> Self:
        self._validate_counts()
        self._validate_currency_consistency()
        self._validate_pnl_signs()
        self._validate_pnl_consistency()
        self._validate_rates()
        self._validate_streaks()
        self._validate_averages()
        return self

    def _validate_counts(self) -> None:
        if self.trade_count < 0:
            raise ValueError("trade_count cannot be negative")
        if self.long_trades < 0:
            raise ValueError("long_trades cannot be negative")
        if self.short_trades < 0:
            raise ValueError("short_trades cannot be negative")
        side_total = self.long_trades + self.short_trades
        if side_total != self.trade_count:
            raise ValueError(
                f"long_trades ({self.long_trades}) + short_trades "
                f"({self.short_trades}) must equal trade_count ({self.trade_count})"
            )

    def _validate_currency_consistency(self) -> None:
        money_fields = (
            self.expectancy,
            self.gross_profit,
            self.gross_loss,
            self.net_profit,
            self.realized_pnl,
            self.unrealized_pnl,
            self.average_win,
            self.average_loss,
            self.largest_win,
            self.largest_loss,
            self.commission,
            self.slippage,
        )
        currencies = {item.currency for item in money_fields}
        if len(currencies) != 1:
            raise ValueError(
                f"All monetary values must use the same currency, got: {currencies}"
            )

    def _validate_pnl_signs(self) -> None:
        if self.gross_profit.is_negative():
            raise ValueError("gross_profit must be non-negative")
        if self.gross_loss.is_positive():
            raise ValueError("gross_loss must be non-positive")
        if self.average_win.is_negative():
            raise ValueError("average_win must be non-negative")
        if self.average_loss.is_positive():
            raise ValueError("average_loss must be non-positive")
        if self.largest_win.is_negative():
            raise ValueError("largest_win must be non-negative")
        if self.largest_loss.is_positive():
            raise ValueError("largest_loss must be non-positive")
        if self.commission.is_negative():
            raise ValueError("commission cannot be negative")
        if self.slippage.is_negative():
            raise ValueError("slippage cannot be negative")

    def _validate_pnl_consistency(self) -> None:
        expected_net = (
            self.gross_profit
            + self.gross_loss
            - self.commission
            - self.slippage
        )
        diff = abs(expected_net.amount - self.net_profit.amount)
        if diff > _MONEY_QUANTUM:
            raise ValueError(
                f"net_profit ({self.net_profit.amount}) does not match "
                f"gross_profit ({self.gross_profit.amount}) + gross_loss "
                f"({self.gross_loss.amount}) - commission "
                f"({self.commission.amount}) - slippage "
                f"({self.slippage.amount}) = {expected_net.amount}"
            )

    def _validate_rates(self) -> None:
        if self.win_rate.is_negative():
            raise ValueError("win_rate cannot be negative")
        if self.loss_rate.is_negative():
            raise ValueError("loss_rate cannot be negative")
        if self.exposure.is_negative():
            raise ValueError("exposure cannot be negative")
        if self.win_rate.to_decimal() > _ONE:
            raise ValueError("win_rate cannot exceed 1")
        if self.loss_rate.to_decimal() > _ONE:
            raise ValueError("loss_rate cannot exceed 1")
        if self.win_rate.to_decimal() + self.loss_rate.to_decimal() > _ONE:
            raise ValueError("win_rate plus loss_rate cannot exceed 1")

    def _validate_streaks(self) -> None:
        if self.consecutive_wins < 0:
            raise ValueError("consecutive_wins cannot be negative")
        if self.consecutive_losses < 0:
            raise ValueError("consecutive_losses cannot be negative")
        if self.max_consecutive_wins < 0:
            raise ValueError("max_consecutive_wins cannot be negative")
        if self.max_consecutive_losses < 0:
            raise ValueError("max_consecutive_losses cannot be negative")
        if self.consecutive_wins > self.max_consecutive_wins:
            raise ValueError("consecutive_wins cannot exceed max_consecutive_wins")
        if self.consecutive_losses > self.max_consecutive_losses:
            raise ValueError(
                "consecutive_losses cannot exceed max_consecutive_losses"
            )

    def _validate_averages(self) -> None:
        if self.average_holding_time < 0:
            raise ValueError("average_holding_time cannot be negative")

    @property
    def total_costs(self) -> Money:
        """Return commission plus slippage."""
        return self.commission + self.slippage

    @property
    def currency(self) -> str:
        """Return the shared currency for monetary trade metrics."""
        return self.net_profit.currency

    @property
    def is_profitable(self) -> bool:
        """Return whether net profit is positive."""
        return self.net_profit.is_positive()

    def __str__(self) -> str:
        return (
            f"TradeMetrics(trades={self.trade_count}, "
            f"win_rate={self.win_rate}, net_profit={self.net_profit})"
        )


class PerformanceSnapshot(AnalyticsValueObject):
    """Portfolio performance snapshot at a point in time."""

    timestamp: datetime
    returns: ReturnMetrics
    risk: RiskMetrics
    trades: TradeMetrics

    @property
    def is_profitable(self) -> bool:
        """Return whether the snapshot is net profitable."""
        return self.trades.is_profitable

    @property
    def is_in_drawdown(self) -> bool:
        """Return whether maximum drawdown is negative."""
        return self.risk.maximum_drawdown.is_negative()

    @property
    def total_return(self) -> Percentage:
        return self.returns.total_return

    @property
    def roi(self) -> Percentage:
        return self.returns.roi

    @property
    def cagr(self) -> Percentage:
        return self.returns.cagr

    @property
    def sharpe_ratio(self) -> Decimal:
        return self.risk.sharpe_ratio

    @property
    def sortino_ratio(self) -> Decimal:
        return self.risk.sortino_ratio

    @property
    def calmar_ratio(self) -> Decimal:
        return self.risk.calmar_ratio

    @property
    def maximum_drawdown(self) -> Percentage:
        return self.risk.maximum_drawdown

    @property
    def volatility(self) -> Percentage:
        return self.risk.volatility

    @property
    def net_profit(self) -> Money:
        return self.trades.net_profit

    @property
    def gross_profit(self) -> Money:
        return self.trades.gross_profit

    @property
    def gross_loss(self) -> Money:
        return self.trades.gross_loss

    @property
    def win_rate(self) -> Percentage:
        return self.trades.win_rate

    @property
    def profit_factor(self) -> Decimal:
        return self.trades.profit_factor

    @property
    def trade_count(self) -> int:
        return self.trades.trade_count

    @property
    def exposure(self) -> Percentage:
        return self.trades.exposure

    @property
    def currency(self) -> str:
        return self.trades.currency

    def __str__(self) -> str:
        return (
            "PerformanceSnapshot("
            f"{self.timestamp.isoformat()}, "
            f"return={self.returns.total_return}, "
            f"sharpe={self.risk.sharpe_ratio}, "
            f"max_dd={self.risk.maximum_drawdown})"
        )


__all__ = [
    "AnalyticsValueObject",
    "ConditionalValueAtRisk",
    "DrawdownPoint",
    "EquityPoint",
    "Money",
    "Percentage",
    "PerformanceSnapshot",
    "ReturnMetrics",
    "ReturnPeriod",
    "ReturnSeries",
    "RiskMetrics",
    "TradeMetrics",
    "ValueAtRisk",
]
