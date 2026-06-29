"""Analytics domain entities.

Identity-bearing aggregates for the Analytics bounded context.

The entities in this module compose the existing trading/backtesting models and
analytics value objects. They intentionally contain no serialization, metric
aliasing, reporting, persistence, or API concerns.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Mapping, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.analytics.domain.value_objects import (
    DrawdownPoint,
    EquityPoint,
    Money,
    Percentage,
    PerformanceSnapshot,
    ReturnSeries,
)
from backend.app.trading.backtesting.metrics import PerformanceMetrics
from backend.app.trading.execution.position import Trade
from backend.app.trading.validation.scenario import Scenario

MetricValue: TypeAlias = Decimal | int | float | Money | Percentage | None
MetricItems: TypeAlias = tuple[tuple[str, MetricValue], ...]
MetricsSource: TypeAlias = PerformanceSnapshot | PerformanceMetrics | MetricItems
MetadataValue: TypeAlias = str | int | float | Decimal | bool | datetime | None
MetadataItems: TypeAlias = tuple[tuple[str, MetadataValue], ...]


class AnalyticsRunStatus(str, Enum):
    """Lifecycle state for an analytics run."""

    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalyticsReportStatus(str, Enum):
    """Publication state for an analytics report."""

    DRAFT = "draft"
    FINAL = "final"
    ARCHIVED = "archived"


class RankingDirection(str, Enum):
    """Sort direction represented by a precomputed analytics ranking."""

    ASCENDING = "ascending"
    DESCENDING = "descending"


class AnalyticsEntity(BaseModel):
    """Base class for immutable analytics entities."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True, extra="forbid")

    @field_validator("metadata", mode="before", check_fields=False)
    @classmethod
    def _normalize_metadata(
        cls,
        value: MetadataItems | Mapping[str, MetadataValue] | None,
    ) -> MetadataItems:
        if value is None:
            return ()
        if isinstance(value, Mapping):
            return tuple(sorted((str(key), item) for key, item in value.items()))
        return tuple((str(key), item) for key, item in value)


class StrategyAnalytics(AnalyticsEntity):
    """Analytics aggregate for one fully resolved validation scenario."""

    analytics_id: str = Field(min_length=1)
    scenario: Scenario
    performance: MetricsSource
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    trades: tuple[Trade, ...] = Field(default_factory=tuple)
    equity_curve: tuple[EquityPoint, ...] = Field(default_factory=tuple)
    drawdown_curve: tuple[DrawdownPoint, ...] = Field(default_factory=tuple)
    return_series: ReturnSeries | None = None
    metadata: MetadataItems = Field(default_factory=tuple)

    @field_validator("analytics_id")
    @classmethod
    def _strip_analytics_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("analytics_id cannot be blank")
        return stripped

    @field_validator("performance", mode="before")
    @classmethod
    def _normalize_metric_mapping(cls, value: MetricsSource | Mapping[str, MetricValue]) -> MetricsSource:
        if isinstance(value, Mapping):
            return tuple(sorted((str(key), item) for key, item in value.items()))
        return value

    @property
    def scenario_id(self) -> str:
        """Return the deterministic validation scenario identifier."""
        return self.scenario.scenario_id

    @property
    def strategy_name(self) -> str:
        """Return the strategy name from the referenced scenario."""
        return self.scenario.strategy_name

    @property
    def symbol(self) -> str:
        """Return the market symbol from the referenced scenario."""
        return self.scenario.symbol

    @property
    def dataset_id(self) -> str:
        """Return the dataset identifier from the referenced scenario."""
        return self.scenario.dataset_id

    @property
    def currency(self) -> str:
        """Return the scenario market currency."""
        return self.scenario.market.currency

    @property
    def has_trades(self) -> bool:
        """Return whether trade attribution is attached."""
        return len(self.trades) > 0

    @property
    def has_equity_curve(self) -> bool:
        """Return whether an analytics equity curve is attached."""
        return len(self.equity_curve) > 0

    @property
    def has_drawdown_curve(self) -> bool:
        """Return whether a drawdown curve is attached."""
        return len(self.drawdown_curve) > 0


class PortfolioAnalytics(AnalyticsEntity):
    """Portfolio-level analytics aggregate independent of validation scenarios."""

    portfolio_analytics_id: str = Field(min_length=1)
    portfolio_id: str = Field(min_length=1)
    snapshot: PerformanceSnapshot
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    trades: tuple[Trade, ...] = Field(default_factory=tuple)
    equity_curve: tuple[EquityPoint, ...] = Field(default_factory=tuple)
    drawdown_curve: tuple[DrawdownPoint, ...] = Field(default_factory=tuple)
    return_series: ReturnSeries | None = None
    metadata: MetadataItems = Field(default_factory=tuple)

    @field_validator("portfolio_analytics_id", "portfolio_id")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("text identifiers cannot be blank")
        return stripped

    @property
    def currency(self) -> str:
        """Return the snapshot currency."""
        return self.snapshot.currency

    @property
    def is_profitable(self) -> bool:
        """Return whether the snapshot is net profitable."""
        return self.snapshot.is_profitable

    @property
    def is_in_drawdown(self) -> bool:
        """Return whether the snapshot is in drawdown."""
        return self.snapshot.is_in_drawdown


class AnalyticsRankingEntry(AnalyticsEntity):
    """One subject inside an analytics ranking."""

    rank: int = Field(gt=0)
    analytics_id: str = Field(min_length=1)
    value: MetricValue = None
    metadata: MetadataItems = Field(default_factory=tuple)

    @field_validator("analytics_id")
    @classmethod
    def _strip_analytics_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("analytics_id cannot be blank")
        return stripped


class AnalyticsRanking(AnalyticsEntity):
    """Precomputed ranking for one analytics metric."""

    ranking_id: str = Field(min_length=1)
    metric_name: str = Field(min_length=1)
    direction: RankingDirection
    entries: tuple[AnalyticsRankingEntry, ...] = Field(default_factory=tuple)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: MetadataItems = Field(default_factory=tuple)

    @field_validator("ranking_id", "metric_name")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("text fields cannot be blank")
        return stripped

    @model_validator(mode="after")
    def _validate_entries(self) -> AnalyticsRanking:
        ranks = [entry.rank for entry in self.entries]
        if len(ranks) != len(set(ranks)):
            raise ValueError("ranking entries must have unique ranks")

        expected_ranks = tuple(range(1, len(self.entries) + 1))
        if tuple(sorted(ranks)) != expected_ranks:
            raise ValueError("ranking entries must be consecutively ranked from 1")

        analytics_ids = [entry.analytics_id for entry in self.entries]
        if len(analytics_ids) != len(set(analytics_ids)):
            raise ValueError("ranking entries must have unique analytics_id values")

        return self

    @property
    def best(self) -> AnalyticsRankingEntry | None:
        """Return the highest-ranked entry when present."""
        if not self.entries:
            return None
        return min(self.entries, key=lambda entry: entry.rank)

    @property
    def worst(self) -> AnalyticsRankingEntry | None:
        """Return the lowest-ranked entry when present."""
        if not self.entries:
            return None
        return max(self.entries, key=lambda entry: entry.rank)


class AnalyticsReport(AnalyticsEntity):
    """Report aggregate composed from analytics outputs and rankings."""

    report_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    status: AnalyticsReportStatus = AnalyticsReportStatus.DRAFT
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    strategy_analytics: tuple[StrategyAnalytics, ...] = Field(default_factory=tuple)
    portfolio_analytics: tuple[PortfolioAnalytics, ...] = Field(default_factory=tuple)
    rankings: tuple[AnalyticsRanking, ...] = Field(default_factory=tuple)
    metadata: MetadataItems = Field(default_factory=tuple)

    @field_validator("report_id", "title")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("text fields cannot be blank")
        return stripped

    @model_validator(mode="after")
    def _validate_unique_members(self) -> AnalyticsReport:
        strategy_ids = [item.analytics_id for item in self.strategy_analytics]
        if len(strategy_ids) != len(set(strategy_ids)):
            raise ValueError("strategy analytics must have unique analytics_id values")

        portfolio_ids = [item.portfolio_analytics_id for item in self.portfolio_analytics]
        if len(portfolio_ids) != len(set(portfolio_ids)):
            raise ValueError(
                "portfolio analytics must have unique portfolio_analytics_id values"
            )

        ranking_ids = [item.ranking_id for item in self.rankings]
        if len(ranking_ids) != len(set(ranking_ids)):
            raise ValueError("report rankings must have unique ranking_id values")

        return self

    @property
    def strategy_analysis_count(self) -> int:
        """Return the number of strategy analytics entries."""
        return len(self.strategy_analytics)

    @property
    def portfolio_analysis_count(self) -> int:
        """Return the number of portfolio analytics entries."""
        return len(self.portfolio_analytics)

    @property
    def ranking_count(self) -> int:
        """Return the number of rankings."""
        return len(self.rankings)

    def add_strategy_analytics(self, analytics: StrategyAnalytics) -> AnalyticsReport:
        """Return a new report with an additional strategy analytics entry."""
        return self.model_copy(
            update={"strategy_analytics": self.strategy_analytics + (analytics,)}
        )

    def add_portfolio_analytics(self, analytics: PortfolioAnalytics) -> AnalyticsReport:
        """Return a new report with an additional portfolio analytics entry."""
        return self.model_copy(
            update={"portfolio_analytics": self.portfolio_analytics + (analytics,)}
        )

    def add_ranking(self, ranking: AnalyticsRanking) -> AnalyticsReport:
        """Return a new report with an additional ranking."""
        return self.model_copy(update={"rankings": self.rankings + (ranking,)})

    def finalize(self) -> AnalyticsReport:
        """Return a finalized copy of this report."""
        if self.status is AnalyticsReportStatus.ARCHIVED:
            raise ValueError("archived reports cannot be finalized")
        return self.model_copy(update={"status": AnalyticsReportStatus.FINAL})

    def archive(self) -> AnalyticsReport:
        """Return an archived copy of this report."""
        return self.model_copy(update={"status": AnalyticsReportStatus.ARCHIVED})


class AnalyticsRun(AnalyticsEntity):
    """Immutable lifecycle aggregate for an analytics execution."""

    run_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    status: AnalyticsRunStatus = AnalyticsRunStatus.CREATED
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    report: AnalyticsReport | None = None
    error: str | None = None
    metadata: MetadataItems = Field(default_factory=tuple)

    @field_validator("run_id", "name")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("text fields cannot be blank")
        return stripped

    @field_validator("error")
    @classmethod
    def _strip_error(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("error cannot be blank")
        return stripped

    @model_validator(mode="after")
    def _validate_lifecycle(self) -> AnalyticsRun:
        if self.started_at is not None and self.started_at < self.created_at:
            raise ValueError("started_at cannot be before created_at")

        if self.completed_at is not None:
            reference_time = self.started_at or self.created_at
            if self.completed_at < reference_time:
                raise ValueError("completed_at cannot be before run start")

        if self.status is AnalyticsRunStatus.CREATED:
            if self.started_at is not None or self.completed_at is not None:
                raise ValueError("created runs cannot have lifecycle timestamps")
            if self.report is not None or self.error is not None:
                raise ValueError("created runs cannot have report or error state")

        if self.status is AnalyticsRunStatus.RUNNING:
            if self.started_at is None:
                raise ValueError("running runs must have started_at")
            if self.completed_at is not None:
                raise ValueError("running runs cannot have completed_at")
            if self.report is not None or self.error is not None:
                raise ValueError("running runs cannot have report or error state")

        if self.status is AnalyticsRunStatus.COMPLETED:
            if self.started_at is None or self.completed_at is None:
                raise ValueError("completed runs must have lifecycle timestamps")
            if self.report is None:
                raise ValueError("completed runs must have a report")
            if self.error is not None:
                raise ValueError("completed runs cannot have an error")

        if self.status is AnalyticsRunStatus.FAILED:
            if self.started_at is None or self.completed_at is None:
                raise ValueError("failed runs must have lifecycle timestamps")
            if self.error is None:
                raise ValueError("failed runs must have an error")
            if self.report is not None:
                raise ValueError("failed runs cannot have a report")

        return self

    @property
    def is_terminal(self) -> bool:
        """Return whether the run is completed or failed."""
        return self.status in (AnalyticsRunStatus.COMPLETED, AnalyticsRunStatus.FAILED)

    @property
    def duration_seconds(self) -> float | None:
        """Return execution duration when both timestamps are available."""
        if self.started_at is None or self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()

    def start(self, at: datetime | None = None) -> AnalyticsRun:
        """Return a running copy of this analytics run."""
        if self.status is not AnalyticsRunStatus.CREATED:
            raise ValueError("only created analytics runs can be started")
        return AnalyticsRun(
            run_id=self.run_id,
            name=self.name,
            status=AnalyticsRunStatus.RUNNING,
            created_at=self.created_at,
            started_at=at or datetime.now(UTC),
            completed_at=None,
            report=None,
            error=None,
            metadata=self.metadata,
        )

    def complete(
        self,
        report: AnalyticsReport,
        at: datetime | None = None,
    ) -> AnalyticsRun:
        """Return a completed copy of this analytics run."""
        if self.status not in (AnalyticsRunStatus.CREATED, AnalyticsRunStatus.RUNNING):
            raise ValueError("only created or running analytics runs can be completed")
        return AnalyticsRun(
            run_id=self.run_id,
            name=self.name,
            status=AnalyticsRunStatus.COMPLETED,
            created_at=self.created_at,
            started_at=self.started_at or self.created_at,
            completed_at=at or datetime.now(UTC),
            report=report,
            error=None,
            metadata=self.metadata,
        )

    def fail(self, error: str, at: datetime | None = None) -> AnalyticsRun:
        """Return a failed copy of this analytics run."""
        if self.status is AnalyticsRunStatus.COMPLETED:
            raise ValueError("completed analytics runs cannot be failed")
        return AnalyticsRun(
            run_id=self.run_id,
            name=self.name,
            status=AnalyticsRunStatus.FAILED,
            created_at=self.created_at,
            started_at=self.started_at or self.created_at,
            completed_at=at or datetime.now(UTC),
            report=None,
            error=error,
            metadata=self.metadata,
        )


__all__ = [
    "AnalyticsEntity",
    "AnalyticsRanking",
    "AnalyticsRankingEntry",
    "AnalyticsReport",
    "AnalyticsReportStatus",
    "AnalyticsRun",
    "AnalyticsRunStatus",
    "MetadataItems",
    "MetadataValue",
    "MetricItems",
    "MetricValue",
    "MetricsSource",
    "PortfolioAnalytics",
    "RankingDirection",
    "StrategyAnalytics",
]
