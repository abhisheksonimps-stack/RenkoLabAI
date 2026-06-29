"""Production health, metrics and monitoring API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from backend.app.api.services import production_services
from backend.app.security.base import Principal, TradingPermission
from backend.app.security.dependencies import require_permission

router = APIRouter(prefix="/production", tags=["Production Health"])


@router.get("/health")
async def production_health(_: Annotated[Principal, Depends(require_permission(TradingPermission.VIEW))]) -> dict[str, object]:
    return await production_services.health_summary()


@router.get("/metrics")
async def production_metrics(_: Annotated[Principal, Depends(require_permission(TradingPermission.VIEW))]) -> dict[str, object]:
    snapshot = production_services.metrics.snapshot()
    return snapshot.__dict__


@router.get("/metrics/prometheus")
async def prometheus(_: Annotated[Principal, Depends(require_permission(TradingPermission.VIEW))]) -> Response:
    return Response(production_services.metrics.prometheus(), media_type="text/plain; version=0.0.4")


@router.get("/readiness")
async def readiness() -> dict[str, object]:
    return await production_services.health_summary()


__all__ = ["router"]
