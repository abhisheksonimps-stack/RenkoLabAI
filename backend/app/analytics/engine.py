"""Analytics engine entry points."""

from __future__ import annotations

from typing import Sequence

from backend.app.analytics.domain.entities import AnalyticsReport
from backend.app.analytics.domain.services import AnalyticsDomainEngine
from backend.app.trading.validation.results import ResultSet


class AnalyticsEngine:
    """Public analytics engine facade for validation result analytics."""

    def __init__(self, domain_engine: AnalyticsDomainEngine | None = None) -> None:
        self._domain_engine = domain_engine or AnalyticsDomainEngine()

    def build_report_from_result_set(
        self,
        result_set: ResultSet,
        title: str = "Analytics Report",
        ranking_metrics: Sequence[str] = (),
    ) -> AnalyticsReport:
        """Return an analytics report generated from validation results."""
        return self._domain_engine.build_report_from_result_set(
            result_set=result_set,
            title=title,
            ranking_metrics=tuple(ranking_metrics),
        )


__all__ = ["AnalyticsEngine"]
