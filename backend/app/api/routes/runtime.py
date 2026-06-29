"""Live runtime production API."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.app.api.services import RuntimeNotConfiguredError, production_services
from backend.app.security.base import Principal, TradingPermission
from backend.app.security.dependencies import require_permission

router = APIRouter(prefix="/runtime", tags=["Runtime Control"])


class RuntimeConfigureRequest(BaseModel):
    exchange_id: str = Field(min_length=1)
    strategy_name: str = Field(min_length=1)
    strategy_parameters: dict[str, Any] = Field(default_factory=dict)
    starting_capital: float | None = Field(default=None, gt=0)


class RuntimeSymbolsRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list)


class KillSwitchRequest(BaseModel):
    reason: str = Field(min_length=1)


@router.post("/configure")
async def configure_runtime(
    payload: RuntimeConfigureRequest,
    _: Annotated[Principal, Depends(require_permission(TradingPermission.MANAGE_RUNTIME))],
) -> dict[str, object]:
    try:
        return production_services.configure_live_runtime(
            exchange_id=payload.exchange_id,
            strategy_name=payload.strategy_name,
            strategy_parameters=payload.strategy_parameters,
            starting_capital=payload.starting_capital,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/status")
async def status(_: Annotated[Principal, Depends(require_permission(TradingPermission.VIEW))]) -> dict[str, object]:
    return await production_services.runtime_status()


@router.post("/start")
async def start_runtime(
    payload: RuntimeSymbolsRequest,
    _: Annotated[Principal, Depends(require_permission(TradingPermission.MANAGE_RUNTIME))],
) -> dict[str, object]:
    try:
        production_services.kill_switch.ensure_trading_allowed()
        runtime = production_services.require_runtime()
        await runtime.start(payload.symbols)
        return {"status": "started", "symbols": payload.symbols}
    except RuntimeNotConfiguredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/stop")
async def stop_runtime(_: Annotated[Principal, Depends(require_permission(TradingPermission.MANAGE_RUNTIME))]) -> dict[str, object]:
    try:
        await production_services.require_runtime().stop()
        return {"status": "stopped"}
    except RuntimeNotConfiguredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/recover")
async def recover_runtime(_: Annotated[Principal, Depends(require_permission(TradingPermission.MANAGE_RUNTIME))]) -> dict[str, object]:
    try:
        await production_services.require_runtime().recover()
        return {"status": "recovered"}
    except RuntimeNotConfiguredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/kill-switch/engage")
async def engage_kill_switch(
    payload: KillSwitchRequest,
    _: Annotated[Principal, Depends(require_permission(TradingPermission.KILL_SWITCH))],
) -> dict[str, object]:
    production_services.kill_switch.engage(payload.reason)
    return {"engaged": True, "reason": production_services.kill_switch.reason}


@router.post("/kill-switch/release")
async def release_kill_switch(_: Annotated[Principal, Depends(require_permission(TradingPermission.KILL_SWITCH))]) -> dict[str, object]:
    production_services.kill_switch.release()
    return {"engaged": False}


__all__ = ["router"]
