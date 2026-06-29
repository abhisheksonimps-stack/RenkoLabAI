from __future__ import annotations

import json

from backend.app.analytics.application import (
    AnalyticsApplicationService,
    BuildAnalyticsReportCommand,
)
from backend.app.analytics.reporting import AnalyticsReportRenderer
from backend.app.trading.validation.results import ResultSet, ScenarioResult
from backend.app.trading.validation.scenario import MarketInfo, Scenario, ScenarioStatus


def _scenario() -> Scenario:
    return Scenario.create(
        "ema_crossover",
        {"period": 10},
        symbol="AAA",
        dataset_id="d1",
        market=MarketInfo("SIM", "equities", "USD"),
    )


def test_application_service_builds_report_dto() -> None:
    result_set = ResultSet(
        [ScenarioResult(_scenario(), ScenarioStatus.COMPLETED, {"net_profit": 42.0})]
    )
    dto = AnalyticsApplicationService().build_report_dto(
        BuildAnalyticsReportCommand(
            result_set=result_set,
            title="Sprint 7 Analytics",
            ranking_metrics=("net_profit",),
        )
    )
    assert dto.title == "Sprint 7 Analytics"
    assert len(dto.strategy_analytics) == 1
    assert len(dto.rankings) == 1


def test_report_renderer_outputs_json_markdown_and_csv() -> None:
    result_set = ResultSet(
        [ScenarioResult(_scenario(), ScenarioStatus.COMPLETED, {"net_profit": 42.0})]
    )
    report = AnalyticsApplicationService().build_report(
        BuildAnalyticsReportCommand(
            result_set=result_set,
            title="Sprint 7 Analytics",
            ranking_metrics=("net_profit",),
        )
    )
    renderer = AnalyticsReportRenderer()
    payload = json.loads(renderer.to_json(report))
    assert payload["title"] == "Sprint 7 Analytics"
    assert "Strategy Analytics" in renderer.to_markdown(report)
    assert "analytics_id" in renderer.to_csv(report)
