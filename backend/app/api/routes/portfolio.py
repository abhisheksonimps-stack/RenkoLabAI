"""Portfolio API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from backend.app.api.services import production_services
from backend.app.security.base import Principal, TradingPermission
from backend.app.security.dependencies import require_permission

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])


@router.get("/snapshot")
async def snapshot(
    _: Annotated[Principal, Depends(require_permission(TradingPermission.VIEW))],
    mark_price: float | None = Query(default=None, gt=0),
) -> dict[str, object]:
    return production_services.portfolio_snapshot(mark_price=mark_price)


@router.get("/equity-curve")
async def equity_curve(_: Annotated[Principal, Depends(require_permission(TradingPermission.VIEW))]) -> dict[str, object]:
    return {
        "points": [
            {"timestamp": point.timestamp.isoformat(), "equity": point.equity}
            for point in production_services.portfolio.equity_curve
        ]
    }


__all__ = ["router"]
