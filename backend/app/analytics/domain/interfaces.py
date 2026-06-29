"""Analytics domain interfaces.

Ports for analytics services. These interfaces remain inside the domain layer so
application and infrastructure components depend on domain abstractions rather
than concrete implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Sequence

from backend.app.analytics.domain.entities import (
    AnalyticsRanking,
    AnalyticsReport,
    AnalyticsRun,
    MetricValue,
    MetricsSource,
    PortfolioAnalytics,
    RankingDirection,
    StrategyAnalytics,
)
from backend.app.analytics.domain.value_objects import (
    DrawdownPoint,
    EquityPoint,
    PerformanceSnapshot,
    ReturnPeriod,
    ReturnSeries,
)
from backend.app.trading.backtesting.metrics import PerformanceMetrics
from backend.app.trading.portfolio.portfolio import Portfolio
from backend.app.trading.validation.results import ResultSet


class MetricExtractor(ABC):
    """Extract canonical metric values from supported metric sources."""

    @abstractmethod
    def value(self, source: MetricsSource, metric_name: str) -> MetricValue:
        """Return a metric value from a supported source."""
        raise NotImplementedError


class RankingService(ABC):
    """Build rankings from analytics aggregates."""

    @abstractmethod
    def rank_strategy_analytics(
        self,
        analytics: Iterable[StrategyAnalytics],
        metric_name: str,
        direction: RankingDirection,
    ) -> AnalyticsRanking:
        """Rank strategy analytics by a metric."""
        raise NotImplementedError


class DrawdownService(ABC):
    """Build drawdown curves from analytics equity curves."""

    @abstractmethod
    def calculate(self, equity_curve: Sequence[EquityPoint]) -> tuple[DrawdownPoint, ...]:
        """Return the drawdown curve for the supplied equity curve."""
        raise NotImplementedError


class ReturnSeriesService(ABC):
    """Build return series from analytics equity curves."""

    @abstractmethod
    def calculate(
        self,
        equity_curve: Sequence[EquityPoint],
        period: ReturnPeriod = ReturnPeriod.DAILY,
    ) -> ReturnSeries:
        """Return periodic returns for the supplied equity curve."""
        raise NotImplementedError


class PerformanceSnapshotFactory(ABC):
    """Create analytics snapshots from existing backtesting metrics."""

    @abstractmethod
    def from_performance_metrics(
        self,
        metrics: PerformanceMetrics,
        currency: str,
    ) -> PerformanceSnapshot:
        """Return a performance snapshot from trading PerformanceMetrics."""
        raise NotImplementedError


class PortfolioAnalyticsFactory(ABC):
    """Create portfolio analytics aggregates from existing portfolios."""

    @abstractmethod
    def from_portfolio(
        self,
        portfolio_id: str,
        portfolio: Portfolio,
        metrics: PerformanceMetrics,
        currency: str,
    ) -> PortfolioAnalytics:
        """Return portfolio analytics for an existing trading portfolio."""
        raise NotImplementedError


class AnalyticsReportFactory(ABC):
    """Create analytics reports from strategy and portfolio analytics."""

    @abstractmethod
    def create_report(
        self,
        title: str,
        strategy_analytics: Iterable[StrategyAnalytics] = (),
        portfolio_analytics: Iterable[PortfolioAnalytics] = (),
        rankings: Iterable[AnalyticsRanking] = (),
    ) -> AnalyticsReport:
        """Return an analytics report aggregate."""
        raise NotImplementedError


class AnalyticsEngine(ABC):
    """Orchestrate analytics creation from validation result sets."""

    @abstractmethod
    def build_report_from_result_set(
        self,
        result_set: ResultSet,
        title: str,
        ranking_metrics: Sequence[str] = (),
    ) -> AnalyticsReport:
        """Return an analytics report generated from validation results."""
        raise NotImplementedError


class AnalyticsRunRepository(ABC):
    """Persistence port for analytics runs."""

    @abstractmethod
    async def save(self, run: AnalyticsRun) -> None:
        """Persist an analytics run."""
        raise NotImplementedError

    @abstractmethod
    async def get(self, run_id: str) -> AnalyticsRun | None:
        """Load an analytics run by identifier."""
        raise NotImplementedError


__all__ = [
    "AnalyticsEngine",
    "AnalyticsReportFactory",
    "AnalyticsRunRepository",
    "DrawdownService",
    "MetricExtractor",
    "PerformanceSnapshotFactory",
    "PortfolioAnalyticsFactory",
    "RankingService",
    "ReturnSeriesService",
]
