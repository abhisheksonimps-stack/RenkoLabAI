"""Analytics domain-to-DTO mappers."""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
from typing import Mapping

from backend.app.analytics.domain.entities import (
    AnalyticsRanking,
    AnalyticsRankingEntry,
    AnalyticsReport,
    AnalyticsRun,
    MetricItems,
    MetricValue,
    PortfolioAnalytics,
    StrategyAnalytics,
)
from backend.app.analytics.domain.value_objects import Money, Percentage, PerformanceSnapshot
from backend.app.analytics.dto.analytics import (
    AnalyticsRankingDTO,
    AnalyticsRankingEntryDTO,
    AnalyticsReportDTO,
    AnalyticsRunDTO,
    MetricDTO,
    MoneyDTO,
    PercentageDTO,
    PortfolioAnalyticsDTO,
    StrategyAnalyticsDTO,
)
from backend.app.trading.backtesting.metrics import PerformanceMetrics

SerializableMetricValue = str | int | float | Decimal | MoneyDTO | PercentageDTO | None


def money_to_dto(value: Money) -> MoneyDTO:
    """Map a Money value object to a DTO."""
    return MoneyDTO(amount=value.amount, currency=value.currency)


def percentage_to_dto(value: Percentage) -> PercentageDTO:
    """Map a Percentage value object to a DTO."""
    return PercentageDTO(value=value.value, percent=value.to_percent())


def metric_value_to_dto(value: MetricValue) -> SerializableMetricValue:
    """Map a domain metric value to a serializable DTO value."""
    if isinstance(value, Money):
        return money_to_dto(value)
    if isinstance(value, Percentage):
        return percentage_to_dto(value)
    return value


def metrics_source_to_items(source: PerformanceSnapshot | PerformanceMetrics | MetricItems) -> MetricItems:
    """Normalize a domain metric source into named metric items."""
    if isinstance(source, PerformanceSnapshot):
        return (
            ("total_return", source.total_return),
            ("roi", source.roi),
            ("cagr", source.cagr),
            ("sharpe_ratio", source.sharpe_ratio),
            ("sortino_ratio", source.sortino_ratio),
            ("calmar_ratio", source.calmar_ratio),
            ("maximum_drawdown", source.maximum_drawdown),
            ("volatility", source.volatility),
            ("net_profit", source.net_profit),
            ("gross_profit", source.gross_profit),
            ("gross_loss", source.gross_loss),
            ("win_rate", source.win_rate),
            ("profit_factor", source.profit_factor),
            ("trade_count", source.trade_count),
            ("exposure", source.exposure),
        )
    if isinstance(source, PerformanceMetrics):
        raw = asdict(source)
        return tuple(sorted((str(key), _raw_metric_value(value)) for key, value in raw.items()))
    return tuple(source)


def _raw_metric_value(value: object) -> MetricValue:
    if value is None:
        return None
    if isinstance(value, (Decimal, int, float, Money, Percentage)) and not isinstance(value, bool):
        return value
    return None


def strategy_analytics_to_dto(entity: StrategyAnalytics) -> StrategyAnalyticsDTO:
    """Map strategy analytics to a DTO."""
    metrics = tuple(
        MetricDTO(name=name, value=metric_value_to_dto(value))
        for name, value in metrics_source_to_items(entity.performance)
    )
    return StrategyAnalyticsDTO(
        analytics_id=entity.analytics_id,
        scenario_id=entity.scenario_id,
        strategy_name=entity.strategy_name,
        symbol=entity.symbol,
        dataset_id=entity.dataset_id,
        currency=entity.currency,
        generated_at=entity.generated_at,
        metrics=metrics,
        trade_count=len(entity.trades),
        equity_points=len(entity.equity_curve),
        drawdown_points=len(entity.drawdown_curve),
    )


def portfolio_analytics_to_dto(entity: PortfolioAnalytics) -> PortfolioAnalyticsDTO:
    """Map portfolio analytics to a DTO."""
    return PortfolioAnalyticsDTO(
        portfolio_analytics_id=entity.portfolio_analytics_id,
        portfolio_id=entity.portfolio_id,
        currency=entity.currency,
        generated_at=entity.generated_at,
        net_profit=money_to_dto(entity.snapshot.net_profit),
        total_return=percentage_to_dto(entity.snapshot.total_return),
        maximum_drawdown=percentage_to_dto(entity.snapshot.maximum_drawdown),
        sharpe_ratio=entity.snapshot.sharpe_ratio,
        trade_count=entity.snapshot.trade_count,
        equity_points=len(entity.equity_curve),
        drawdown_points=len(entity.drawdown_curve),
    )


def ranking_entry_to_dto(entity: AnalyticsRankingEntry) -> AnalyticsRankingEntryDTO:
    """Map a ranking entry to a DTO."""
    return AnalyticsRankingEntryDTO(
        rank=entity.rank,
        analytics_id=entity.analytics_id,
        value=metric_value_to_dto(entity.value),
    )


def ranking_to_dto(entity: AnalyticsRanking) -> AnalyticsRankingDTO:
    """Map a ranking to a DTO."""
    return AnalyticsRankingDTO(
        ranking_id=entity.ranking_id,
        metric_name=entity.metric_name,
        direction=entity.direction.value,
        generated_at=entity.generated_at,
        entries=tuple(ranking_entry_to_dto(entry) for entry in entity.entries),
    )


def report_to_dto(entity: AnalyticsReport) -> AnalyticsReportDTO:
    """Map an analytics report to a DTO."""
    return AnalyticsReportDTO(
        report_id=entity.report_id,
        title=entity.title,
        status=entity.status.value,
        generated_at=entity.generated_at,
        strategy_analytics=tuple(
            strategy_analytics_to_dto(item) for item in entity.strategy_analytics
        ),
        portfolio_analytics=tuple(
            portfolio_analytics_to_dto(item) for item in entity.portfolio_analytics
        ),
        rankings=tuple(ranking_to_dto(item) for item in entity.rankings),
    )


def run_to_dto(entity: AnalyticsRun) -> AnalyticsRunDTO:
    """Map an analytics run to a DTO."""
    return AnalyticsRunDTO(
        run_id=entity.run_id,
        name=entity.name,
        status=entity.status.value,
        created_at=entity.created_at,
        started_at=entity.started_at,
        completed_at=entity.completed_at,
        duration_seconds=entity.duration_seconds,
        error=entity.error,
        report=report_to_dto(entity.report) if entity.report is not None else None,
    )


def metadata_to_dict(metadata: tuple[tuple[str, object], ...]) -> Mapping[str, object]:
    """Map normalized metadata items into a read-only mapping shape."""
    return dict(metadata)


__all__ = [
    "metric_value_to_dto",
    "metrics_source_to_items",
    "money_to_dto",
    "percentage_to_dto",
    "portfolio_analytics_to_dto",
    "ranking_entry_to_dto",
    "ranking_to_dto",
    "report_to_dto",
    "run_to_dto",
    "strategy_analytics_to_dto",
]
