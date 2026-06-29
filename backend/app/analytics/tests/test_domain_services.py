from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from backend.app.analytics.domain.entities import RankingDirection
from backend.app.analytics.domain.services import (
    AnalyticsDomainEngine,
    AnalyticsDrawdownService,
    AnalyticsRankingService,
    DefaultMetricExtractor,
)
from backend.app.analytics.domain.value_objects import EquityPoint, Money
from backend.app.trading.validation.results import ResultSet, ScenarioResult
from backend.app.trading.validation.scenario import MarketInfo, Scenario, ScenarioStatus

TS = datetime(2024, 1, 1, 0, 0, 0)


def _point(offset: int, equity: Decimal) -> EquityPoint:
    return EquityPoint(
        timestamp=TS + timedelta(days=offset),
        equity=Money(amount=equity, currency="USD"),
        realized_pnl=Money(amount=equity - Decimal("100"), currency="USD"),
        unrealized_pnl=Money(amount=Decimal("0"), currency="USD"),
    )


def _scenario(symbol: str, strategy: str = "ema_crossover") -> Scenario:
    return Scenario.create(
        strategy,
        {"period": 10},
        symbol=symbol,
        dataset_id="d1",
        market=MarketInfo("SIM", "equities", "USD"),
    )


def test_drawdown_service_tracks_peak_and_drawdown() -> None:
    curve = (_point(0, Decimal("100")), _point(1, Decimal("120")), _point(2, Decimal("90")))
    points = AnalyticsDrawdownService().calculate(curve)
    assert len(points) == 3
    assert points[-1].peak_equity.amount == Decimal("120.00")
    assert points[-1].drawdown.to_decimal().quantize(Decimal("0.0001")) == Decimal("-0.2500")


def test_metric_extractor_reads_validation_metric_items() -> None:
    source = (("net_profit", 125.50), ("win_rate", 0.75))
    extractor = DefaultMetricExtractor()
    assert extractor.value(source, "net_profit") == 125.50
    assert extractor.value(source, "missing") is None


def test_ranking_service_orders_strategy_analytics() -> None:
    result_set = ResultSet(
        [
            ScenarioResult(_scenario("AAA"), ScenarioStatus.COMPLETED, {"net_profit": 10.0}),
            ScenarioResult(_scenario("BBB"), ScenarioStatus.COMPLETED, {"net_profit": 25.0}),
        ]
    )
    report = AnalyticsDomainEngine().build_report_from_result_set(
        result_set,
        "Validation Analytics",
        ("net_profit",),
    )
    ranking = report.rankings[0]
    assert ranking.direction is RankingDirection.DESCENDING
    assert ranking.best is not None
    assert ranking.best.value == 25.0


def test_explicit_drawdown_ranking_uses_ascending_direction() -> None:
    report = AnalyticsDomainEngine().build_report_from_result_set(
        ResultSet(
            [
                ScenarioResult(_scenario("AAA"), ScenarioStatus.COMPLETED, {"max_drawdown_pct": 0.30}),
                ScenarioResult(_scenario("BBB"), ScenarioStatus.COMPLETED, {"max_drawdown_pct": 0.10}),
            ]
        ),
        "Drawdown Ranking",
        ("max_drawdown_pct",),
    )
    assert report.rankings[0].direction is RankingDirection.ASCENDING
    assert report.rankings[0].best is not None
    assert report.rankings[0].best.value == 0.10


def test_ranking_service_can_rank_empty_collection() -> None:
    ranking = AnalyticsRankingService().rank_strategy_analytics([], "net_profit")
    assert ranking.entries == ()
