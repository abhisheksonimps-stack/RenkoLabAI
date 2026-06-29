"""Database repositories for trading persistence."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database.models.trading import (
    AnalyticsSnapshotModel,
    OrderHistoryModel,
    PortfolioSnapshotModel,
    TradeHistoryModel,
)
from backend.app.trading.execution.order import Order
from backend.app.trading.execution.position import Trade
from backend.app.trading.portfolio.live_snapshot import LivePortfolioSnapshot


class TradingRepository:
    """SQL-backed order, trade, portfolio and analytics repository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_order(self, order: Order) -> OrderHistoryModel:
        payload = self._serialize(order)
        model = OrderHistoryModel(
            order_id=order.order_id,
            broker_order_id=order.broker_order_id,
            symbol=order.symbol,
            side=order.side.value,
            intent=order.intent.value,
            quantity=order.quantity,
            reference_price=order.reference_price,
            status=order.status.value,
            payload=json.dumps(payload, sort_keys=True),
        )
        self._session.add(model)
        await self._session.flush()
        return model

    async def save_trade(self, trade: Trade) -> TradeHistoryModel:
        model = TradeHistoryModel(
            symbol=trade.symbol,
            strategy_name=trade.strategy_name,
            quantity=trade.quantity,
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            net_pnl=trade.net_pnl,
            payload=json.dumps(self._serialize(trade), sort_keys=True),
        )
        self._session.add(model)
        await self._session.flush()
        return model

    async def save_portfolio_snapshot(self, snapshot: LivePortfolioSnapshot) -> PortfolioSnapshotModel:
        payload = snapshot.to_dict()
        model = PortfolioSnapshotModel(
            portfolio_id=snapshot.portfolio_id,
            equity=float(payload.get("equity", 0.0)),
            cash=float(payload.get("cash", 0.0)),
            payload=json.dumps(payload, sort_keys=True),
        )
        self._session.add(model)
        await self._session.flush()
        return model

    async def save_analytics_snapshot(self, portfolio_id: str, payload: dict[str, Any]) -> AnalyticsSnapshotModel:
        model = AnalyticsSnapshotModel(portfolio_id=portfolio_id, payload=json.dumps(payload, sort_keys=True))
        self._session.add(model)
        await self._session.flush()
        return model

    async def list_orders(self, limit: int = 100) -> list[OrderHistoryModel]:
        result = await self._session.execute(select(OrderHistoryModel).order_by(OrderHistoryModel.id.desc()).limit(limit))
        return list(result.scalars().all())

    @classmethod
    def _serialize(cls, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Enum):
            return value.value
        if is_dataclass(value):
            return {key: cls._serialize(item) for key, item in asdict(value).items()}
        if isinstance(value, dict):
            return {str(key): cls._serialize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [cls._serialize(item) for item in value]
        return value


__all__ = ["TradingRepository"]
