"""Portfolio analytics facade."""

from __future__ import annotations

from backend.app.analytics.domain.entities import PortfolioAnalytics
from backend.app.analytics.domain.services import AnalyticsPortfolioService
from backend.app.trading.backtesting.metrics import PerformanceMetrics
from backend.app.trading.portfolio.portfolio import Portfolio


class PortfolioAnalyticsCalculator:
    """Application-friendly facade for portfolio analytics calculations."""

    def __init__(self, service: AnalyticsPortfolioService | None = None) -> None:
        self._service = service or AnalyticsPortfolioService()

    def calculate(
        self,
        portfolio_id: str,
        portfolio: Portfolio,
        metrics: PerformanceMetrics,
        currency: str = "USD",
    ) -> PortfolioAnalytics:
        """Return portfolio analytics for an existing trading portfolio."""
        return self._service.from_portfolio(
            portfolio_id=portfolio_id,
            portfolio=portfolio,
            metrics=metrics,
            currency=currency,
        )


__all__ = ["PortfolioAnalyticsCalculator"]
