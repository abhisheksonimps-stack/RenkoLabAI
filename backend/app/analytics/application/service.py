"""Analytics application service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from backend.app.analytics.domain.entities import AnalyticsReport
from backend.app.analytics.domain.services import AnalyticsDomainEngine
from backend.app.analytics.dto.analytics import AnalyticsReportDTO
from backend.app.analytics.mappers.analytics import report_to_dto
from backend.app.trading.validation.results import ResultSet


@dataclass(frozen=True)
class BuildAnalyticsReportCommand:
    """Command for building an analytics report from validation results."""

    result_set: ResultSet
    title: str = "Analytics Report"
    ranking_metrics: Sequence[str] = field(default_factory=tuple)


class AnalyticsApplicationService:
    """Application orchestration for analytics use cases."""

    def __init__(self, engine: AnalyticsDomainEngine | None = None) -> None:
        self._engine = engine or AnalyticsDomainEngine()

    def build_report(self, command: BuildAnalyticsReportCommand) -> AnalyticsReport:
        """Build and return a domain analytics report."""
        return self._engine.build_report_from_result_set(
            result_set=command.result_set,
            title=command.title,
            ranking_metrics=tuple(command.ranking_metrics),
        )

    def build_report_dto(self, command: BuildAnalyticsReportCommand) -> AnalyticsReportDTO:
        """Build and return a serializable analytics report DTO."""
        return report_to_dto(self.build_report(command))


__all__ = ["AnalyticsApplicationService", "BuildAnalyticsReportCommand"]
