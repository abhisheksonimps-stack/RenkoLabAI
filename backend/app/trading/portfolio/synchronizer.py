"""Idempotent propagation of filled OMS orders into the portfolio aggregate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from backend.app.trading.execution.order import Order
from backend.app.trading.execution.position import Trade
from backend.app.trading.portfolio.live_snapshot import LivePortfolioSnapshot
from backend.app.trading.portfolio.portfolio import Portfolio


@dataclass(frozen=True)
class PortfolioSyncResult:
    """Outcome from applying one order to a portfolio."""

    order: Order
    applied: bool
    trade: Trade | None
    snapshot: LivePortfolioSnapshot | None


class PortfolioSynchronizer:
    """Apply live fills to ``Portfolio`` exactly once."""

    def __init__(self, portfolio: Portfolio, *, portfolio_id: str = "live_portfolio") -> None:
        self._portfolio = portfolio
        self._portfolio_id = portfolio_id
        self._applied_fill_keys: set[str] = set()
        self._recorded_order_ids: set[int] = set()
        self._last_snapshot: LivePortfolioSnapshot | None = None

    @property
    def portfolio(self) -> Portfolio:
        return self._portfolio

    @property
    def last_snapshot(self) -> LivePortfolioSnapshot | None:
        return self._last_snapshot

    def apply_order(self, order: Order, *, bar_index: int, mark_price: float, timestamp: datetime) -> PortfolioSyncResult:
        self.record_order(order)
        if not order.is_filled or order.fill is None:
            snapshot = self.snapshot(mark_price=mark_price, timestamp=timestamp)
            return PortfolioSyncResult(order=order, applied=False, trade=None, snapshot=snapshot)

        fill_key = self._fill_key(order)
        if fill_key in self._applied_fill_keys:
            snapshot = self.snapshot(mark_price=mark_price, timestamp=timestamp)
            return PortfolioSyncResult(order=order, applied=False, trade=None, snapshot=snapshot)

        trade = self._portfolio.apply_order(order, bar_index)
        self._applied_fill_keys.add(fill_key)
        snapshot = self.snapshot(mark_price=mark_price, timestamp=timestamp)
        return PortfolioSyncResult(order=order, applied=True, trade=trade, snapshot=snapshot)

    def apply_orders(self, orders: Iterable[Order], *, bar_index: int, mark_price: float, timestamp: datetime) -> list[PortfolioSyncResult]:
        return [self.apply_order(order, bar_index=bar_index, mark_price=mark_price, timestamp=timestamp) for order in orders]

    def record_order(self, order: Order) -> None:
        if order.order_id not in self._recorded_order_ids:
            self._portfolio.record_order(order)
            self._recorded_order_ids.add(order.order_id)

    def snapshot(self, *, mark_price: float, timestamp: datetime) -> LivePortfolioSnapshot:
        self._last_snapshot = LivePortfolioSnapshot.from_portfolio(
            self._portfolio_id,
            self._portfolio,
            timestamp=timestamp,
            mark_price=mark_price,
        )
        return self._last_snapshot

    @staticmethod
    def _fill_key(order: Order) -> str:
        fill = order.fill
        if fill is None:
            return f"order:{order.order_id}:empty"
        explicit = getattr(fill, "fill_id", None)
        if explicit:
            return str(explicit)
        broker_order_id = getattr(order, "broker_order_id", None) or "local"
        return f"{broker_order_id}:{order.order_id}:{fill.side.value}:{fill.timestamp.isoformat()}:{fill.price}:{fill.quantity}"


__all__ = ["PortfolioSyncResult", "PortfolioSynchronizer"]
