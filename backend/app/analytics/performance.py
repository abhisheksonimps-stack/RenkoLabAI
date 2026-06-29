"""Performance analytics facade."""

from __future__ import annotations

from backend.app.analytics.domain.services import AnalyticsPerformanceSnapshotFactory
from backend.app.analytics.domain.value_objects import PerformanceSnapshot
from backend.app.trading.backtesting.metrics import PerformanceMetrics


class PerformanceMetricsCalculator:
    """Create analytics performance snapshots from trading metrics."""

    def __init__(self, factory: AnalyticsPerformanceSnapshotFactory | None = None) -> None:
        self._factory = factory or AnalyticsPerformanceSnapshotFactory()

    def snapshot_from_metrics(
        self,
        metrics: PerformanceMetrics,
        currency: str = "USD",
    ) -> PerformanceSnapshot:
        """Return an analytics snapshot for existing PerformanceMetrics."""
        return self._factory.from_performance_metrics(metrics, currency)


__all__ = ["PerformanceMetricsCalculator"]
