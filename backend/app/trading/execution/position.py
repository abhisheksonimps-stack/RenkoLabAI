"""Position (live exposure) and Trade (completed round trip).

Sprint T2 is long-only: BUY opens/owns a long, SELL/EXIT closes it. The model is
sign-aware (LONG/FLAT) so shorts can be added later without redesign. The
Position is order/venue-agnostic — the portfolio translates fills into
``open_long`` / ``close`` calls.

Trades carry attribution fields (strategy name, symbol, brick type, brick size,
timeframe) required for future strategy comparison.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class PositionDirection(str, Enum):
    FLAT = "flat"
    LONG = "long"


@dataclass(frozen=True)
class TradeAttribution:
    symbol: str = "UNKNOWN"
    strategy_name: str = "unknown"
    brick_type: str = "unknown"
    brick_size: float = 0.0
    timeframe: str = "unknown"


@dataclass(frozen=True)
class Trade:
    # Attribution (for future strategy comparison).
    symbol: str
    strategy_name: str
    brick_type: str
    brick_size: float
    timeframe: str
    # Round-trip economics.
    direction: str
    quantity: float
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    entry_cost: float
    exit_cost: float
    gross_pnl: float
    net_pnl: float
    return_pct: float
    bars_held: int

    @property
    def is_win(self) -> bool:
        return self.net_pnl > 0


class Position:
    def __init__(self, attribution: Optional[TradeAttribution] = None) -> None:
        self.attribution = attribution or TradeAttribution()
        self.direction = PositionDirection.FLAT
        self.quantity = 0.0
        self.average_entry_price = 0.0
        self.realized_pnl = 0.0
        self._entry_cost = 0.0
        self._entry_time: Optional[datetime] = None
        self._entry_bar: Optional[int] = None

    @property
    def is_open(self) -> bool:
        return self.direction is PositionDirection.LONG and self.quantity > 0

    def market_value(self, mark_price: float) -> float:
        return self.quantity * float(mark_price) if self.is_open else 0.0

    def unrealized_pnl(self, mark_price: float) -> float:
        if not self.is_open:
            return 0.0
        return (float(mark_price) - self.average_entry_price) * self.quantity

    def open_long(self, price: float, quantity: float, cost: float,
                  timestamp: datetime, bar_index: int) -> None:
        if quantity <= 0:
            raise ValueError("open_long quantity must be positive")
        if not self.is_open:
            self.direction = PositionDirection.LONG
            self.quantity = float(quantity)
            self.average_entry_price = float(price)
            self._entry_cost = float(cost)
            self._entry_time = timestamp
            self._entry_bar = bar_index
        else:
            # Scale in: re-average the entry price.
            new_qty = self.quantity + float(quantity)
            self.average_entry_price = (
                self.average_entry_price * self.quantity + float(price) * float(quantity)
            ) / new_qty
            self.quantity = new_qty
            self._entry_cost += float(cost)

    def close(self, price: float, cost: float, timestamp: datetime, bar_index: int) -> Optional[Trade]:
        if not self.is_open:
            return None
        qty = self.quantity
        entry = self.average_entry_price
        gross = (float(price) - entry) * qty
        net = gross - self._entry_cost - float(cost)
        notional = entry * qty
        return_pct = (net / notional) if notional else 0.0
        bars_held = (bar_index - self._entry_bar) if self._entry_bar is not None else 0
        a = self.attribution
        trade = Trade(
            symbol=a.symbol, strategy_name=a.strategy_name, brick_type=a.brick_type,
            brick_size=a.brick_size, timeframe=a.timeframe,
            direction="long", quantity=qty, entry_price=entry, exit_price=float(price),
            entry_time=self._entry_time, exit_time=timestamp,
            entry_cost=self._entry_cost, exit_cost=float(cost),
            gross_pnl=gross, net_pnl=net, return_pct=return_pct, bars_held=bars_held,
        )
        self.realized_pnl += net
        self._reset_flat()
        return trade

    def _reset_flat(self) -> None:
        self.direction = PositionDirection.FLAT
        self.quantity = 0.0
        self.average_entry_price = 0.0
        self._entry_cost = 0.0
        self._entry_time = None
        self._entry_bar = None
