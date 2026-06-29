"""Immutable live portfolio snapshot objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping

from backend.app.trading.portfolio.portfolio import Portfolio


@dataclass(frozen=True)
class LivePortfolioSnapshot:
    """Point-in-time live portfolio view for persistence, metrics and reporting."""

    portfolio_id: str
    timestamp: datetime
    cash: float
    reserved: float
    available_capital: float
    buying_power: float
    equity: float
    position_quantity: float
    position_market_value: float
    trade_count: int
    order_count: int
    metadata: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def from_portfolio(
        cls,
        portfolio_id: str,
        portfolio: Portfolio,
        *,
        timestamp: datetime,
        mark_price: float,
        metadata: Mapping[str, object] | None = None,
    ) -> "LivePortfolioSnapshot":
        return cls(
            portfolio_id=portfolio_id,
            timestamp=timestamp,
            cash=portfolio.cash,
            reserved=portfolio.reserved,
            available_capital=portfolio.available_capital,
            buying_power=portfolio.buying_power,
            equity=portfolio.equity(mark_price),
            position_quantity=portfolio.position.quantity if portfolio.position.is_open else 0.0,
            position_market_value=portfolio.position.market_value(mark_price),
            trade_count=len(portfolio.trades),
            order_count=len(portfolio.orders),
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "portfolio_id": self.portfolio_id,
            "timestamp": self.timestamp.isoformat(),
            "cash": self.cash,
            "reserved": self.reserved,
            "available_capital": self.available_capital,
            "buying_power": self.buying_power,
            "equity": self.equity,
            "position_quantity": self.position_quantity,
            "position_market_value": self.position_market_value,
            "trade_count": self.trade_count,
            "order_count": self.order_count,
            "metadata": dict(self.metadata),
        }


__all__ = ["LivePortfolioSnapshot"]
