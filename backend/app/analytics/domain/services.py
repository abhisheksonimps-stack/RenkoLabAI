"""Analytics domain services.

Pure domain services for metric extraction, drawdown calculation, return-series
construction, ranking, and aggregate creation. These services contain the
calculation and normalization logic intentionally kept out of entities.
"""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime
from decimal import Decimal
from typing import Iterable, Mapping, Sequence

from backend.app.analytics.domain.entities import (
    AnalyticsRanking,
    AnalyticsRankingEntry,
    AnalyticsReport,
    MetricItems,
    MetricValue,
    MetricsSource,
    PortfolioAnalytics,
    RankingDirection,
    StrategyAnalytics,
)
from backend.app.analytics.domain.value_objects import (
    ConditionalValueAtRisk,
    DrawdownPoint,
    EquityPoint,
    Money,
    Percentage,
    PerformanceSnapshot,
    ReturnMetrics,
    ReturnPeriod,
    ReturnSeries,
    RiskMetrics,
    TradeMetrics,
    ValueAtRisk,
)
from backend.app.trading.backtesting.metrics import PerformanceMetrics
from backend.app.trading.portfolio.portfolio import EquityPoint as TradingEquityPoint
from backend.app.trading.portfolio.portfolio import Portfolio
from backend.app.trading.validation.results import ResultSet, ScenarioResult
from backend.app.trading.validation.scenario import Scenario

_METRIC_ALIASES: Mapping[str, tuple[str, ...]] = {
    "average_trade": ("average_trade", "expectancy"),
    "calmar_ratio": ("calmar_ratio", "calmar"),
    "drawdown": ("drawdown", "max_drawdown"),
    "drawdown_pct": ("drawdown_pct", "max_drawdown_pct", "maximum_drawdown"),
    "net_profit": ("net_profit", "net_pnl", "total_pnl"),
    "profit_factor": ("profit_factor",),
    "return": ("return", "total_return"),
    "sharpe_ratio": ("sharpe_ratio", "sharpe"),
    "sortino_ratio": ("sortino_ratio", "sortino"),
    "total_trades": ("total_trades", "num_trades", "trade_count"),
    "win_rate": ("win_rate",),
}

_LOWER_IS_BETTER = frozenset({"max_drawdown", "max_drawdown_pct", "drawdown", "drawdown_pct"})


def _decimal(value: Decimal | float | int) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _money(value: Decimal | float | int, currency: str) -> Money:
    return Money(amount=_decimal(value), currency=currency)


def _percentage(value: Decimal | float | int) -> Percentage:
    return Percentage(value=_decimal(value))


def _ratio(value: float | None) -> Decimal:
    if value is None:
        return Decimal("0")
    if math.isinf(value):
        return Decimal("Infinity") if value > 0 else Decimal("-Infinity")
    if math.isnan(value):
        return Decimal("0")
    return Decimal(str(value))


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "|".join(str(part) for part in parts)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _metric_items_from_mapping(metrics: Mapping[str, MetricValue]) -> MetricItems:
    return tuple(sorted((str(key), value) for key, value in metrics.items()))


def _to_sortable(value: MetricValue) -> float | None:
    if value is None:
        return None
    if isinstance(value, Money):
        return float(value.amount)
    if isinstance(value, Percentage):
        return float(value.value)
    if isinstance(value, Decimal):
        if value.is_nan():
            return None
        if value.is_infinite():
            return math.inf if value > 0 else -math.inf
        return float(value)
    if isinstance(value, bool):
        return None
    if isinstance(value, (float, int)):
        number = float(value)
        if math.isnan(number):
            return None
        return number
    return None


class DefaultMetricExtractor:
    """Canonical metric extractor for analytics-supported metric sources."""

    def value(self, source: MetricsSource, metric_name: str) -> MetricValue:
        """Return a metric value from a supported source."""
        metric = metric_name.strip()
        if not metric:
            raise ValueError("metric_name cannot be blank")
        names = _METRIC_ALIASES.get(metric, (metric,))

        if isinstance(source, PerformanceSnapshot):
            return self._from_snapshot(source, names)

        if isinstance(source, PerformanceMetrics):
            return self._from_performance_metrics(source, names)

        metric_map = dict(source)
        for name in names:
            if name in metric_map:
                return metric_map[name]
        return None

    def _from_snapshot(
        self,
        snapshot: PerformanceSnapshot,
        names: tuple[str, ...],
    ) -> MetricValue:
        values: Mapping[str, MetricValue] = {
            "average_trade": snapshot.trades.expectancy,
            "calmar_ratio": snapshot.risk.calmar_ratio,
            "gross_loss": snapshot.gross_loss,
            "gross_profit": snapshot.gross_profit,
            "max_drawdown": snapshot.maximum_drawdown,
            "max_drawdown_pct": snapshot.maximum_drawdown,
            "net_profit": snapshot.net_profit,
            "profit_factor": snapshot.profit_factor,
            "sharpe": snapshot.sharpe_ratio,
            "sharpe_ratio": snapshot.sharpe_ratio,
            "sortino": snapshot.sortino_ratio,
            "sortino_ratio": snapshot.sortino_ratio,
            "total_return": snapshot.total_return,
            "total_trades": snapshot.trade_count,
            "trade_count": snapshot.trade_count,
            "win_rate": snapshot.win_rate,
        }
        for name in names:
            if name in values:
                return values[name]
        return None

    def _from_performance_metrics(
        self,
        metrics: PerformanceMetrics,
        names: tuple[str, ...],
    ) -> MetricValue:
        values: Mapping[str, MetricValue] = {
            "average_trade": metrics.expectancy,
            "avg_loss": metrics.avg_loss,
            "avg_win": metrics.avg_win,
            "expectancy": metrics.expectancy,
            "gross_pnl": metrics.gross_pnl,
            "largest_loss": metrics.largest_loss,
            "largest_win": metrics.largest_win,
            "max_drawdown": metrics.max_drawdown,
            "max_drawdown_pct": metrics.max_drawdown_pct,
            "net_pnl": metrics.net_pnl,
            "net_profit": metrics.net_pnl,
            "num_trades": metrics.num_trades,
            "profit_factor": metrics.profit_factor,
            "sharpe": metrics.sharpe,
            "sortino": metrics.sortino,
            "total_pnl": metrics.total_pnl,
            "total_return": metrics.total_return,
            "total_trades": metrics.num_trades,
            "win_rate": metrics.win_rate,
        }
        for name in names:
            if name in values:
                return values[name]
        return None


class AnalyticsDrawdownService:
    """Calculate drawdown curves from analytics equity curves."""

    def calculate(self, equity_curve: Sequence[EquityPoint]) -> tuple[DrawdownPoint, ...]:
        """Return the drawdown curve for the supplied equity curve."""
        if not equity_curve:
            return ()

        peak = equity_curve[0]
        points: list[DrawdownPoint] = []
        for point in equity_curve:
            if point.equity > peak.equity:
                peak = point
            if peak.equity.amount == Decimal("0.00"):
                drawdown = Percentage.zero()
            else:
                drawdown = Percentage(
                    value=(point.equity.amount - peak.equity.amount) / peak.equity.amount
                )
            points.append(
                DrawdownPoint(
                    timestamp=point.timestamp,
                    drawdown=drawdown,
                    peak_equity=peak.equity,
                    current_equity=point.equity,
                    peak_timestamp=peak.timestamp,
                )
            )
        return tuple(points)


class AnalyticsReturnSeriesService:
    """Calculate return series from analytics equity curves."""

    def calculate(
        self,
        equity_curve: Sequence[EquityPoint],
        period: ReturnPeriod = ReturnPeriod.DAILY,
    ) -> ReturnSeries:
        """Return periodic returns for the supplied equity curve."""
        if not equity_curve:
            timestamp = datetime.now(UTC)
            return ReturnSeries(
                period=period,
                returns=(),
                start_timestamp=timestamp,
                end_timestamp=timestamp,
            )

        returns: list[Percentage] = []
        for previous, current in zip(equity_curve, equity_curve[1:]):
            if previous.equity.amount == Decimal("0.00"):
                returns.append(Percentage.zero())
            else:
                returns.append(
                    Percentage(
                        value=(current.equity.amount - previous.equity.amount)
                        / previous.equity.amount
                    )
                )
        return ReturnSeries(
            period=period,
            returns=tuple(returns),
            start_timestamp=equity_curve[0].timestamp,
            end_timestamp=equity_curve[-1].timestamp,
        )


class AnalyticsPerformanceSnapshotFactory:
    """Create analytics performance snapshots from trading metrics."""

    def from_performance_metrics(
        self,
        metrics: PerformanceMetrics,
        currency: str,
    ) -> PerformanceSnapshot:
        """Return a performance snapshot from trading PerformanceMetrics."""
        now = datetime.now(UTC)
        total_return = _percentage(metrics.total_return)
        daily_return = total_return
        weekly_return = total_return
        monthly_return = total_return
        annual_return = total_return
        cagr = total_return
        roi = total_return

        max_drawdown = Percentage(value=-abs(_decimal(metrics.max_drawdown_pct)))
        average_drawdown = max_drawdown
        max_dd_abs = abs(_decimal(metrics.max_drawdown_pct))
        annual_return_decimal = _decimal(metrics.total_return)
        calmar = Decimal("0") if max_dd_abs == Decimal("0") else annual_return_decimal / max_dd_abs
        mar_ratio = calmar

        total_costs = _decimal(metrics.total_brokerage) + _decimal(metrics.total_slippage)
        gross_before_costs = _decimal(metrics.net_pnl) + total_costs
        gross_profit = max(gross_before_costs, Decimal("0"))
        gross_loss = min(gross_before_costs, Decimal("0"))
        losses = max(metrics.losses, 0)
        loss_rate = Decimal("0") if metrics.num_trades == 0 else Decimal(losses) / Decimal(metrics.num_trades)

        recovery_denominator = _decimal(metrics.max_drawdown)
        recovery_factor = (
            Decimal("0")
            if recovery_denominator == Decimal("0")
            else _decimal(metrics.net_pnl) / abs(recovery_denominator)
        )
        payoff_ratio = (
            Decimal("0")
            if metrics.avg_loss == 0
            else _decimal(metrics.avg_win) / abs(_decimal(metrics.avg_loss))
        )

        return PerformanceSnapshot(
            timestamp=now,
            returns=ReturnMetrics(
                total_return=total_return,
                daily_return=daily_return,
                weekly_return=weekly_return,
                monthly_return=monthly_return,
                annual_return=annual_return,
                cagr=cagr,
                roi=roi,
            ),
            risk=RiskMetrics(
                sharpe_ratio=_ratio(metrics.sharpe),
                sortino_ratio=_ratio(metrics.sortino),
                calmar_ratio=calmar,
                treynor_ratio=None,
                information_ratio=None,
                maximum_drawdown=max_drawdown,
                average_drawdown=average_drawdown,
                drawdown_duration_days=0,
                volatility=Percentage.zero(),
                beta=None,
                alpha=None,
                ulcer_index=Percentage(value=max_dd_abs),
                mar_ratio=mar_ratio,
                var_95=ValueAtRisk(
                    value=max_drawdown,
                    confidence_level=Percentage(value=Decimal("0.95")),
                    time_horizon_days=1,
                ) if not max_drawdown.is_zero() else None,
                cvar_95=ConditionalValueAtRisk(
                    value=max_drawdown,
                    confidence_level=Percentage(value=Decimal("0.95")),
                    time_horizon_days=1,
                ) if not max_drawdown.is_zero() else None,
            ),
            trades=TradeMetrics(
                profit_factor=_ratio(metrics.profit_factor),
                recovery_factor=recovery_factor,
                payoff_ratio=payoff_ratio,
                expectancy=_money(metrics.expectancy, currency),
                win_rate=_percentage(metrics.win_rate),
                loss_rate=Percentage(value=loss_rate),
                gross_profit=_money(gross_profit, currency),
                gross_loss=_money(gross_loss, currency),
                net_profit=_money(metrics.net_pnl, currency),
                realized_pnl=_money(metrics.net_pnl, currency),
                unrealized_pnl=Money.zero(currency),
                average_win=_money(max(metrics.avg_win, 0.0), currency),
                average_loss=_money(min(metrics.avg_loss, 0.0), currency),
                largest_win=_money(max(metrics.largest_win, 0.0), currency),
                largest_loss=_money(min(metrics.largest_loss, 0.0), currency),
                consecutive_wins=0,
                consecutive_losses=0,
                max_consecutive_wins=0,
                max_consecutive_losses=0,
                average_holding_time=float(metrics.avg_bars_held),
                exposure=Percentage.zero(),
                trade_count=metrics.num_trades,
                long_trades=metrics.num_trades,
                short_trades=0,
                commission=_money(metrics.total_brokerage, currency),
                slippage=_money(metrics.total_slippage, currency),
            ),
        )


class AnalyticsPortfolioService:
    """Create portfolio analytics aggregates from trading portfolios."""

    def __init__(
        self,
        snapshot_factory: AnalyticsPerformanceSnapshotFactory | None = None,
        drawdown_service: AnalyticsDrawdownService | None = None,
        return_service: AnalyticsReturnSeriesService | None = None,
    ) -> None:
        self._snapshot_factory = snapshot_factory or AnalyticsPerformanceSnapshotFactory()
        self._drawdown_service = drawdown_service or AnalyticsDrawdownService()
        self._return_service = return_service or AnalyticsReturnSeriesService()

    def from_portfolio(
        self,
        portfolio_id: str,
        portfolio: Portfolio,
        metrics: PerformanceMetrics,
        currency: str,
    ) -> PortfolioAnalytics:
        """Return portfolio analytics for an existing trading portfolio."""
        equity_curve = self._to_analytics_equity_curve(
            portfolio.equity_curve,
            portfolio.starting_capital,
            currency,
        )
        return PortfolioAnalytics(
            portfolio_analytics_id=_stable_id(
                "portfolio_analytics",
                portfolio_id,
                len(portfolio.equity_curve),
                metrics.ending_equity,
            ),
            portfolio_id=portfolio_id,
            snapshot=self._snapshot_factory.from_performance_metrics(metrics, currency),
            trades=tuple(portfolio.trades),
            equity_curve=equity_curve,
            drawdown_curve=self._drawdown_service.calculate(equity_curve),
            return_series=self._return_service.calculate(equity_curve),
        )

    def _to_analytics_equity_curve(
        self,
        equity_curve: Sequence[TradingEquityPoint],
        starting_capital: float,
        currency: str,
    ) -> tuple[EquityPoint, ...]:
        points: list[EquityPoint] = []
        for point in equity_curve:
            equity = _money(point.equity, currency)
            realized = _money(point.equity - starting_capital, currency)
            points.append(
                EquityPoint(
                    timestamp=point.timestamp,
                    equity=equity,
                    realized_pnl=realized,
                    unrealized_pnl=Money.zero(currency),
                )
            )
        return tuple(points)


class AnalyticsRankingService:
    """Build precomputed analytics rankings."""

    def __init__(self, extractor: DefaultMetricExtractor | None = None) -> None:
        self._extractor = extractor or DefaultMetricExtractor()

    def rank_strategy_analytics(
        self,
        analytics: Iterable[StrategyAnalytics],
        metric_name: str,
        direction: RankingDirection | None = None,
    ) -> AnalyticsRanking:
        """Rank strategy analytics by a canonical metric."""
        clean_metric = metric_name.strip()
        if not clean_metric:
            raise ValueError("metric_name cannot be blank")
        selected_direction = direction or self.default_direction(clean_metric)
        items = list(analytics)

        def sort_key(item: StrategyAnalytics) -> tuple[int, float, str]:
            raw_value = self._extractor.value(item.performance, clean_metric)
            sortable = _to_sortable(raw_value)
            if sortable is None:
                return (1, math.inf, item.analytics_id)
            if selected_direction is RankingDirection.DESCENDING:
                sortable = -sortable
            return (0, sortable, item.analytics_id)

        ordered = sorted(items, key=sort_key)
        entries = tuple(
            AnalyticsRankingEntry(
                rank=index + 1,
                analytics_id=item.analytics_id,
                value=self._extractor.value(item.performance, clean_metric),
            )
            for index, item in enumerate(ordered)
        )
        return AnalyticsRanking(
            ranking_id=_stable_id("ranking", clean_metric, selected_direction.value, len(entries)),
            metric_name=clean_metric,
            direction=selected_direction,
            entries=entries,
        )

    def default_direction(self, metric_name: str) -> RankingDirection:
        """Return the conventional direction for a metric."""
        if metric_name in _LOWER_IS_BETTER:
            return RankingDirection.ASCENDING
        return RankingDirection.DESCENDING


class AnalyticsReportService:
    """Create analytics report aggregates."""

    def create_report(
        self,
        title: str,
        strategy_analytics: Iterable[StrategyAnalytics] = (),
        portfolio_analytics: Iterable[PortfolioAnalytics] = (),
        rankings: Iterable[AnalyticsRanking] = (),
    ) -> AnalyticsReport:
        """Return an analytics report aggregate."""
        strategy_items = tuple(strategy_analytics)
        portfolio_items = tuple(portfolio_analytics)
        ranking_items = tuple(rankings)
        return AnalyticsReport(
            report_id=_stable_id(
                "analytics_report",
                title,
                len(strategy_items),
                len(portfolio_items),
                len(ranking_items),
            ),
            title=title,
            strategy_analytics=strategy_items,
            portfolio_analytics=portfolio_items,
            rankings=ranking_items,
        )


class StrategyAnalyticsService:
    """Create strategy analytics aggregates from validation results."""

    def from_scenario_result(self, result: ScenarioResult) -> StrategyAnalytics:
        """Return strategy analytics for a completed validation scenario result."""
        return StrategyAnalytics(
            analytics_id=_stable_id("strategy_analytics", result.scenario.scenario_id),
            scenario=result.scenario,
            performance=_metric_items_from_mapping(result.metrics),
            metadata={"duration_seconds": result.duration_seconds},
        )

    def from_scenario_metrics(
        self,
        scenario: Scenario,
        metrics: PerformanceMetrics,
    ) -> StrategyAnalytics:
        """Return strategy analytics directly from a scenario and metrics."""
        return StrategyAnalytics(
            analytics_id=_stable_id("strategy_analytics", scenario.scenario_id),
            scenario=scenario,
            performance=metrics,
        )


class AnalyticsDomainEngine:
    """Domain-level analytics orchestration for validation results."""

    def __init__(
        self,
        strategy_service: StrategyAnalyticsService | None = None,
        ranking_service: AnalyticsRankingService | None = None,
        report_service: AnalyticsReportService | None = None,
    ) -> None:
        self._strategy_service = strategy_service or StrategyAnalyticsService()
        self._ranking_service = ranking_service or AnalyticsRankingService()
        self._report_service = report_service or AnalyticsReportService()

    def build_report_from_result_set(
        self,
        result_set: ResultSet,
        title: str,
        ranking_metrics: Sequence[str] = (),
    ) -> AnalyticsReport:
        """Return an analytics report generated from validation results."""
        strategy_analytics = tuple(
            self._strategy_service.from_scenario_result(result)
            for result in result_set.completed()
        )
        rankings = tuple(
            self._ranking_service.rank_strategy_analytics(strategy_analytics, metric)
            for metric in ranking_metrics
        )
        return self._report_service.create_report(
            title=title,
            strategy_analytics=strategy_analytics,
            rankings=rankings,
        )


__all__ = [
    "AnalyticsDomainEngine",
    "AnalyticsDrawdownService",
    "AnalyticsPerformanceSnapshotFactory",
    "AnalyticsPortfolioService",
    "AnalyticsRankingService",
    "AnalyticsReportService",
    "AnalyticsReturnSeriesService",
    "DefaultMetricExtractor",
    "StrategyAnalyticsService",
]
