"""Drawdown analytics facade."""

from __future__ import annotations

from typing import Sequence

from backend.app.analytics.domain.services import AnalyticsDrawdownService
from backend.app.analytics.domain.value_objects import DrawdownPoint, EquityPoint


class DrawdownEngine:
    """Calculate drawdown curves for analytics equity curves."""

    def __init__(self, service: AnalyticsDrawdownService | None = None) -> None:
        self._service = service or AnalyticsDrawdownService()

    def calculate(self, equity_curve: Sequence[EquityPoint]) -> tuple[DrawdownPoint, ...]:
        """Return the drawdown curve for an equity curve."""
        return self._service.calculate(equity_curve)


__all__ = ["DrawdownEngine"]
