"""Broker credential and synchronization API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.app.api.services import production_services
from backend.app.security.base import Principal, TradingPermission
from backend.app.security.credentials import BrokerCredentials
from backend.app.security.dependencies import require_permission

router = APIRouter(prefix="/brokers", tags=["Brokers"])


class BrokerCredentialRequest(BaseModel):
    exchange_id: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    secret: str = Field(min_length=1)
    password: str | None = None
    sandbox: bool = False


@router.get("/credentials")
async def list_credentials(_: Annotated[Principal, Depends(require_permission(TradingPermission.MANAGE_RUNTIME))]) -> dict[str, object]:
    return {"credentials": production_services.credentials.list_public()}


@router.post("/credentials")
async def save_credentials(
    payload: BrokerCredentialRequest,
    _: Annotated[Principal, Depends(require_permission(TradingPermission.MANAGE_RUNTIME))],
) -> dict[str, object]:
    credentials = BrokerCredentials(**payload.model_dump())
    production_services.credentials.save(credentials)
    return {"stored": True, "credential": credentials.public_dict()}


@router.post("/sync/account")
async def sync_account(_: Annotated[Principal, Depends(require_permission(TradingPermission.MANAGE_RUNTIME))]) -> dict[str, object]:
    oms = production_services.require_oms()
    broker = getattr(oms, "_broker", None)
    if broker is None:
        return {"synchronized": False, "reason": "broker is not configured"}
    account = await broker.get_account_info()
    return {"synchronized": True, "account": account.__dict__}


__all__ = ["router"]
