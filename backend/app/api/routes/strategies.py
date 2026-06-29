"""Strategy production API."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.app.api.services import production_services
from backend.app.security.base import Principal, TradingPermission
from backend.app.security.dependencies import require_permission

router = APIRouter(prefix="/strategies", tags=["Strategies"])


class StrategyListResponse(BaseModel):
    strategies: list[str]


class StrategyCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)


class StrategyResponse(BaseModel):
    name: str
    class_name: str
    parameters: dict[str, Any]


@router.get("", response_model=StrategyListResponse)
async def list_strategies(_: Annotated[Principal, Depends(require_permission(TradingPermission.VIEW))]) -> StrategyListResponse:
    return StrategyListResponse(strategies=production_services.strategy_factory.available())


@router.post("/instantiate", response_model=StrategyResponse)
async def instantiate_strategy(
    payload: StrategyCreateRequest,
    _: Annotated[Principal, Depends(require_permission(TradingPermission.VIEW))],
) -> StrategyResponse:
    strategy = production_services.strategy_factory.create(payload.name, **payload.parameters)
    return StrategyResponse(name=strategy.name, class_name=strategy.__class__.__name__, parameters=payload.parameters)


__all__ = ["router"]
