"""Production analytics API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from backend.app.api.services import production_services
from backend.app.security.base import Principal, TradingPermission
from backend.app.security.dependencies import require_permission

router = APIRouter(prefix="/production-analytics", tags=["Production Analytics"])


@router.get("/snapshot")
async def analytics_snapshot(_: Annotated[Principal, Depends(require_permission(TradingPermission.VIEW))]) -> dict[str, object]:
    pipeline = production_services.pipeline
    if pipeline is None or pipeline.last_result is None:
        return {"available": False, "reason": "live pipeline has not produced a report"}
    result = pipeline.last_result
    return {
        "available": True,
        "portfolio": result.portfolio_snapshot.to_dict(),
        "metrics": result.metrics.__dict__,
    }


@router.get("/report/{fmt}")
async def analytics_report(
    fmt: str,
    _: Annotated[Principal, Depends(require_permission(TradingPermission.VIEW))],
) -> Response:
    pipeline = production_services.pipeline
    if pipeline is None or pipeline.last_result is None:
        return Response("No live analytics report is available yet", media_type="text/plain", status_code=404)
    report = pipeline.last_result.report
    if fmt == "json":
        return Response(report.json, media_type="application/json")
    if fmt == "csv":
        return Response(report.csv, media_type="text/csv")
    return Response(report.markdown, media_type="text/markdown")


__all__ = ["router"]
