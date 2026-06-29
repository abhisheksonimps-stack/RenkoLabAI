"""Analytics data transfer objects.

DTOs are application-facing, serializable shapes. Domain entities remain free of
serialization concerns and are mapped into these DTOs by analytics mappers.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AnalyticsDTO(BaseModel):
    """Base DTO configuration for analytics outputs."""

    model_config = ConfigDict(frozen=True)


class MoneyDTO(AnalyticsDTO):
    """Serializable monetary value."""

    amount: Decimal
    currency: str


class PercentageDTO(AnalyticsDTO):
    """Serializable percentage value."""

    value: Decimal
    percent: Decimal


class MetricDTO(AnalyticsDTO):
    """Serializable metric value."""

    name: str
    value: str | int | float | Decimal | MoneyDTO | PercentageDTO | None


class StrategyAnalyticsDTO(AnalyticsDTO):
    """Serializable strategy analytics summary."""

    analytics_id: str
    scenario_id: str
    strategy_name: str
    symbol: str
    dataset_id: str
    currency: str
    generated_at: datetime
    metrics: tuple[MetricDTO, ...]
    trade_count: int
    equity_points: int
    drawdown_points: int


class PortfolioAnalyticsDTO(AnalyticsDTO):
    """Serializable portfolio analytics summary."""

    portfolio_analytics_id: str
    portfolio_id: str
    currency: str
    generated_at: datetime
    net_profit: MoneyDTO
    total_return: PercentageDTO
    maximum_drawdown: PercentageDTO
    sharpe_ratio: Decimal
    trade_count: int
    equity_points: int
    drawdown_points: int


class AnalyticsRankingEntryDTO(AnalyticsDTO):
    """Serializable ranking entry."""

    rank: int
    analytics_id: str
    value: str | int | float | Decimal | MoneyDTO | PercentageDTO | None


class AnalyticsRankingDTO(AnalyticsDTO):
    """Serializable analytics ranking."""

    ranking_id: str
    metric_name: str
    direction: str
    generated_at: datetime
    entries: tuple[AnalyticsRankingEntryDTO, ...]


class AnalyticsReportDTO(AnalyticsDTO):
    """Serializable analytics report."""

    report_id: str
    title: str
    status: str
    generated_at: datetime
    strategy_analytics: tuple[StrategyAnalyticsDTO, ...] = Field(default_factory=tuple)
    portfolio_analytics: tuple[PortfolioAnalyticsDTO, ...] = Field(default_factory=tuple)
    rankings: tuple[AnalyticsRankingDTO, ...] = Field(default_factory=tuple)


class AnalyticsRunDTO(AnalyticsDTO):
    """Serializable analytics run state."""

    run_id: str
    name: str
    status: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: float | None
    error: str | None
    report: AnalyticsReportDTO | None


__all__ = [
    "AnalyticsDTO",
    "AnalyticsRankingDTO",
    "AnalyticsRankingEntryDTO",
    "AnalyticsReportDTO",
    "AnalyticsRunDTO",
    "MetricDTO",
    "MoneyDTO",
    "PercentageDTO",
    "PortfolioAnalyticsDTO",
    "StrategyAnalyticsDTO",
]
