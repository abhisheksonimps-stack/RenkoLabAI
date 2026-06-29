"""Market data streaming events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from backend.app.events.base import BaseEvent


@dataclass(frozen=True)
class TickEvent(BaseEvent):
    """Individual trade or quote update."""

    symbol: str = ""
    price: Decimal = Decimal("0")
    size: Decimal = Decimal("0")
    side: str = ""  # "buy" or "sell"
    exchange: str = ""

    def __init__(
        self,
        name: str = "TickEvent",
        occurred_at: Optional[datetime] = None,
        payload: Optional[Dict[str, Any]] = None,
        *,
        symbol: str = "",
        price: Decimal = Decimal("0"),
        size: Decimal = Decimal("0"),
        side: str = "",
        exchange: str = "",
    ) -> None:
        import asyncio
        if occurred_at is None:
            occurred_at = datetime.now()
        if payload is None:
            payload = {}
        payload.update({
            "symbol": symbol,
            "price": str(price),
            "size": str(size),
            "side": side,
            "exchange": exchange,
        })
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "occurred_at", occurred_at)
        object.__setattr__(self, "payload", payload)
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "price", price)
        object.__setattr__(self, "size", size)
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "exchange", exchange)


@dataclass(frozen=True)
class CandleEvent(BaseEvent):
    """OHLCV candle data."""

    symbol: str = ""
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    volume: Decimal = Decimal("0")
    interval: str = "1m"
    trades: int = 0

    def __init__(
        self,
        name: str = "CandleEvent",
        occurred_at: Optional[datetime] = None,
        payload: Optional[Dict[str, Any]] = None,
        *,
        symbol: str = "",
        open: Decimal = Decimal("0"),
        high: Decimal = Decimal("0"),
        low: Decimal = Decimal("0"),
        close: Decimal = Decimal("0"),
        volume: Decimal = Decimal("0"),
        interval: str = "1m",
        trades: int = 0,
    ) -> None:
        if occurred_at is None:
            occurred_at = datetime.now()
        if payload is None:
            payload = {}
        payload.update({
            "symbol": symbol,
            "open": str(open),
            "high": str(high),
            "low": str(low),
            "close": str(close),
            "volume": str(volume),
            "interval": interval,
            "trades": trades,
        })
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "occurred_at", occurred_at)
        object.__setattr__(self, "payload", payload)
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "open", open)
        object.__setattr__(self, "high", high)
        object.__setattr__(self, "low", low)
        object.__setattr__(self, "close", close)
        object.__setattr__(self, "volume", volume)
        object.__setattr__(self, "interval", interval)
        object.__setattr__(self, "trades", trades)


@dataclass(frozen=True)
class OrderBookEvent(BaseEvent):
    """Order book snapshot or update."""

    symbol: str = ""
    bids: List[Dict[str, Decimal]] = None  # type: ignore
    asks: List[Dict[str, Decimal]] = None  # type: ignore
    timestamp: Optional[datetime] = None

    def __init__(
        self,
        name: str = "OrderBookEvent",
        occurred_at: Optional[datetime] = None,
        payload: Optional[Dict[str, Any]] = None,
        *,
        symbol: str = "",
        bids: Optional[List[Dict[str, Decimal]]] = None,
        asks: Optional[List[Dict[str, Decimal]]] = None,
        timestamp: Optional[datetime] = None,
    ) -> None:
        if occurred_at is None:
            occurred_at = datetime.now()
        if payload is None:
            payload = {}
        if bids is None:
            bids = []
        if asks is None:
            asks = []
        payload.update({
            "symbol": symbol,
            "bids": [[str(b["price"]), str(b["size"])] for b in bids],
            "asks": [[str(a["price"]), str(a["size"])] for a in asks],
            "timestamp": timestamp.isoformat() if timestamp else None,
        })
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "occurred_at", occurred_at)
        object.__setattr__(self, "payload", payload)
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "bids", bids)
        object.__setattr__(self, "asks", asks)
        object.__setattr__(self, "timestamp", timestamp)


@dataclass(frozen=True)
class MarketStatusEvent(BaseEvent):
    """Market status change (open, closed, halted, etc.)."""

    symbol: str = ""
    status: str = ""  # "open", "closed", "halted", "pre_market", "after_hours"
    reason: str = ""

    def __init__(
        self,
        name: str = "MarketStatusEvent",
        occurred_at: Optional[datetime] = None,
        payload: Optional[Dict[str, Any]] = None,
        *,
        symbol: str = "",
        status: str = "",
        reason: str = "",
    ) -> None:
        if occurred_at is None:
            occurred_at = datetime.now()
        if payload is None:
            payload = {}
        payload.update({
            "symbol": symbol,
            "status": status,
            "reason": reason,
        })
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "occurred_at", occurred_at)
        object.__setattr__(self, "payload", payload)
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "reason", reason)