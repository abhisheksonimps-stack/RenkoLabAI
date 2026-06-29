"""Analytics API routes."""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.analytics.api.schemas import (
    AnalyticsCapabilityResponse,
    AnalyticsHealthResponse,
)
from backend.app.analytics.domain.entities import RankingDirection
from backend.app.analytics.domain.value_objects import ReturnPeriod

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/health", response_model=AnalyticsHealthResponse)
async def analytics_health() -> AnalyticsHealthResponse:
    """Return analytics service health."""
    return AnalyticsHealthResponse(status="ok", service="analytics")


@router.get("/capabilities", response_model=AnalyticsCapabilityResponse)
async def analytics_capabilities() -> AnalyticsCapabilityResponse:
    """Return analytics capabilities exposed by Sprint 7."""
    return AnalyticsCapabilityResponse(
        supported_ranking_directions=tuple(direction.value for direction in RankingDirection),
        supported_return_periods=tuple(period.value for period in ReturnPeriod),
        supported_report_formats=("json", "csv", "markdown"),
        default_ranking_metrics=(
            "net_profit",
            "win_rate",
            "profit_factor",
            "sharpe",
            "sortino",
            "max_drawdown_pct",
            "total_return",
        ),
    )


__all__ = ["router"]
