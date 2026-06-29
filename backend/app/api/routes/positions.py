"""Position API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.app.api.services import RuntimeNotConfiguredError, production_services
from backend.app.security.base import Principal, TradingPermission
from backend.app.security.dependencies import require_permission

router = APIRouter(prefix="/positions", tags=["Positions"])


class PositionResponse(BaseModel):
    symbol: str
    quantity: float
    average_price: float
    current_price: float | None = None
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0


@router.get("", response_model=list[PositionResponse])
async def positions(_: Annotated[Principal, Depends(require_permission(TradingPermission.VIEW))]) -> list[PositionResponse]:
    try:
        active = production_services.require_oms().get_active_positions()
    except RuntimeNotConfiguredError:
        active = []
    return [
        PositionResponse(
            symbol=position.symbol,
            quantity=position.quantity,
            average_price=position.average_price,
            current_price=position.current_price,
            realized_pnl=position.realized_pnl,
            unrealized_pnl=position.unrealized_pnl,
        )
        for position in active
    ]


__all__ = ["router"]
