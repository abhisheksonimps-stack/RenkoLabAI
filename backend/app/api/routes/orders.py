"""OMS order API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.app.api.services import RuntimeNotConfiguredError, production_services
from backend.app.security.base import Principal, TradingPermission
from backend.app.security.dependencies import require_permission
from backend.app.trading.execution.order import Order

router = APIRouter(prefix="/orders", tags=["Orders"])


class OrderResponse(BaseModel):
    order_id: int
    symbol: str
    side: str
    intent: str
    quantity: float
    reference_price: float
    status: str
    broker_order_id: str | None = None
    client_order_id: str | None = None
    reject_reason: str | None = None


class ModifyOrderRequest(BaseModel):
    quantity: float | None = Field(default=None, gt=0)
    reference_price: float | None = Field(default=None, gt=0)


def _response(order: Order) -> OrderResponse:
    return OrderResponse(
        order_id=order.order_id,
        symbol=order.symbol,
        side=order.side.value,
        intent=order.intent.value,
        quantity=order.quantity,
        reference_price=order.reference_price,
        status=order.status.value,
        broker_order_id=order.broker_order_id,
        client_order_id=order.client_order_id,
        reject_reason=order.reject_reason,
    )


@router.get("", response_model=list[OrderResponse])
async def list_orders(_: Annotated[Principal, Depends(require_permission(TradingPermission.VIEW))]) -> list[OrderResponse]:
    try:
        return [_response(order) for order in production_services.require_oms().order_manager.all_orders]
    except RuntimeNotConfiguredError:
        return []


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(order_id: int, _: Annotated[Principal, Depends(require_permission(TradingPermission.VIEW))]) -> OrderResponse:
    order = production_services.require_oms().order_manager.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return _response(order)


@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    _: Annotated[Principal, Depends(require_permission(TradingPermission.CANCEL_ORDER))],
) -> dict[str, object]:
    ok = await production_services.require_oms().cancel_order(order_id)
    return {"cancelled": ok}


@router.post("/{order_id}/modify")
async def modify_order(
    order_id: int,
    payload: ModifyOrderRequest,
    _: Annotated[Principal, Depends(require_permission(TradingPermission.MODIFY_ORDER))],
) -> dict[str, object]:
    ok = await production_services.require_oms().modify_order(
        order_id,
        quantity=payload.quantity,
        reference_price=payload.reference_price,
    )
    return {"modified": ok}


@router.post("/synchronize")
async def synchronize_orders(_: Annotated[Principal, Depends(require_permission(TradingPermission.MANAGE_RUNTIME))]) -> dict[str, object]:
    decisions = await production_services.require_oms().synchronize_orders()
    return {"decisions": [decision.__dict__ for decision in decisions]}


__all__ = ["router"]
