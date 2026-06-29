"""Backtesting production API."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.app.chart.renko.models import Brick, BrickDirection
from backend.app.security.base import Principal, TradingPermission
from backend.app.security.dependencies import require_permission
from backend.app.trading.backtesting.engine import BacktestEngine
from backend.app.trading.backtesting.report import metrics_to_dict
from backend.app.api.services import production_services

router = APIRouter(prefix="/backtesting", tags=["Backtesting"])


class BacktestBrick(BaseModel):
    close_price: float
    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
    direction: str = "up"
    created_at: datetime | None = None


class BacktestRequest(BaseModel):
    strategy_name: str = Field(min_length=1)
    strategy_parameters: dict[str, Any] = Field(default_factory=dict)
    starting_capital: float = Field(default=100_000.0, gt=0)
    bricks: list[BacktestBrick] = Field(min_length=1)


@router.post("/run")
async def run_backtest(
    payload: BacktestRequest,
    _: Annotated[Principal, Depends(require_permission(TradingPermission.VIEW))],
) -> dict[str, object]:
    strategy = production_services.strategy_factory.create(payload.strategy_name, **payload.strategy_parameters)
    engine = BacktestEngine(strategy, starting_capital=payload.starting_capital)
    bricks: list[Brick] = []
    for index, item in enumerate(payload.bricks):
        close = float(item.close_price)
        bricks.append(
            Brick(
                brick_id=f"api-{index}",
                open_price=float(item.open_price if item.open_price is not None else close),
                high_price=float(item.high_price if item.high_price is not None else close),
                low_price=float(item.low_price if item.low_price is not None else close),
                close_price=close,
                direction=BrickDirection.UP if item.direction.lower() != "down" else BrickDirection.DOWN,
                volume=0.0,
                created_at=item.created_at or datetime.utcnow(),
                metadata={"symbol": "API", "index": index},
            )
        )
    result = engine.run(bricks)
    return {
        "metrics": metrics_to_dict(result.metrics),
        "trades": [trade.__dict__ for trade in result.trades],
        "equity_curve": [{"timestamp": point.timestamp.isoformat(), "equity": point.equity} for point in result.equity_curve],
    }


__all__ = ["router"]
