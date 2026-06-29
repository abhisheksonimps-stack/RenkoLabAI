"""Market data production API."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.app.api.services import production_services
from backend.app.security.base import Principal, TradingPermission
from backend.app.security.dependencies import require_permission

router = APIRouter(prefix="/market-data", tags=["Market Data"])


class TickerResponse(BaseModel):
    symbol: str
    data: dict[str, object]


@router.get("/ticker/{symbol}", response_model=TickerResponse)
async def ticker(symbol: str, _: Annotated[Principal, Depends(require_permission(TradingPermission.VIEW))]) -> TickerResponse:
    oms = production_services.oms
    broker = getattr(oms, "_broker", None) if oms is not None else None
    if broker is None:
        raise HTTPException(status_code=409, detail="Broker is not configured")
    return TickerResponse(symbol=symbol, data=await broker.get_ticker(symbol))


@router.get("/ohlcv/{symbol}")
async def ohlcv(
    symbol: str,
    _: Annotated[Principal, Depends(require_permission(TradingPermission.VIEW))],
    timeframe: str = Query(default="1m"),
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict[str, object]:
    oms = production_services.oms
    broker = getattr(oms, "_broker", None) if oms is not None else None
    if broker is None:
        raise HTTPException(status_code=409, detail="Broker is not configured")
    candles = await broker.get_ohlcv(symbol, timeframe=timeframe, limit=limit)
    return {"symbol": symbol, "timeframe": timeframe, "candles": candles}


__all__ = ["router"]
