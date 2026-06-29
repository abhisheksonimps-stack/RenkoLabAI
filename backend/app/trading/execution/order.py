"""Order and Fill types — venue-agnostic execution primitives.

These carry no backtest/paper/live assumptions, so the same types flow through
every executor. An Order is a mutable record whose status transitions are
explicit and logged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderIntent(str, Enum):
    ENTRY = "entry"
    EXIT = "exit"


class OrderStatus(str, Enum):
    CREATED = "created"
    PENDING = "pending"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


@dataclass
class Fill:
    price: float
    quantity: float
    cost: float                 # brokerage/commission
    reference_price: float      # pre-slippage reference (for slippage accounting)
    side: OrderSide
    timestamp: datetime

    @property
    def slippage(self) -> float:
        return abs(self.price - self.reference_price) * abs(self.quantity)


@dataclass
class Order:
    order_id: int
    side: OrderSide
    intent: OrderIntent
    quantity: float
    reference_price: float
    created_at: datetime
    symbol: str = "UNKNOWN"     # trading symbol (required for live execution)
    status: OrderStatus = OrderStatus.CREATED
    fill: Optional[Fill] = None
    reject_reason: Optional[str] = None
    reserved: float = 0.0       # capital reserved at creation (released on settle)

    def submit(self) -> None:
        self.status = OrderStatus.PENDING

    def complete(self, fill: Fill) -> None:
        self.fill = fill
        self.status = OrderStatus.FILLED

    def reject(self, reason: str) -> None:
        self.reject_reason = reason
        self.status = OrderStatus.REJECTED

    def cancel(self) -> None:
        self.status = OrderStatus.CANCELLED

    @property
    def is_filled(self) -> bool:
        return self.status is OrderStatus.FILLED
