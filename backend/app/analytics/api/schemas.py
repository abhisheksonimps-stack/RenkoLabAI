"""Analytics API schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AnalyticsCapabilityResponse(BaseModel):
    """Analytics API capability response."""

    model_config = ConfigDict(frozen=True)

    supported_ranking_directions: tuple[str, ...]
    supported_return_periods: tuple[str, ...]
    supported_report_formats: tuple[str, ...]
    default_ranking_metrics: tuple[str, ...]


class AnalyticsHealthResponse(BaseModel):
    """Analytics API health response."""

    model_config = ConfigDict(frozen=True)

    status: str
    service: str


__all__ = ["AnalyticsCapabilityResponse", "AnalyticsHealthResponse"]
