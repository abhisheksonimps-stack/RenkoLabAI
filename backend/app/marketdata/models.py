"""Core market-data models.

Every adapter normalizes into ``MarketBar`` (UTC-aware, OHLC-validated), so the
rest of the platform never learns where a bar came from. The Renko engine
consumes these bars by duck-typing ``open/high/low/close`` — no Renko change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from backend.app.marketdata.errors import MalformedData


class AssetClass(str, Enum):
    EQUITY = "equity"
    COMMODITY = "commodity"
    CRYPTO = "crypto"
    FOREX = "forex"


class AdjustmentPolicy(str, Enum):
    """How equity prices are reported. Adapters respect this (not just metadata)."""

    RAW = "raw"
    ADJUSTED = "adjusted"


# Intervals are simple strings (e.g. "1d", "1h", "1m"); kept open for any source.
Interval = str


def to_utc(timestamp: Any) -> datetime:
    """Coerce a datetime or ISO string to a timezone-aware UTC datetime."""
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp)
        except ValueError as exc:
            raise MalformedData(f"Unparseable timestamp: {timestamp!r}") from exc
    if not isinstance(timestamp, datetime):
        raise MalformedData(f"timestamp must be datetime or ISO string, got {type(timestamp)!r}")
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


@dataclass(frozen=True)
class MarketBar:
    symbol: str
    timestamp: datetime          # timezone-aware, UTC
    open: float
    high: float
    low: float
    close: float
    volume: float
    interval: Interval = "1d"
    asset_class: AssetClass = AssetClass.EQUITY
    source: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.timestamp, datetime) or self.timestamp.tzinfo is None:
            raise MalformedData("MarketBar.timestamp must be timezone-aware")
        o, h, l, c = self.open, self.high, self.low, self.close
        if min(o, h, l, c) < 0:
            raise MalformedData("MarketBar prices must be non-negative")
        if self.volume < 0:
            raise MalformedData("MarketBar volume must be non-negative")
        if not (l <= o <= h and l <= c <= h):
            raise MalformedData(f"Inconsistent OHLC: o={o} h={h} l={l} c={c}")

    @classmethod
    def create(cls, *, symbol: str, timestamp: Any, open: float, high: float, low: float,
               close: float, volume: float = 0.0, interval: Interval = "1d",
               asset_class: AssetClass = AssetClass.EQUITY, source: str = "unknown",
               metadata: Optional[Dict[str, Any]] = None) -> "MarketBar":
        return cls(
            symbol=symbol, timestamp=to_utc(timestamp),
            open=float(open), high=float(high), low=float(low), close=float(close),
            volume=float(volume or 0.0), interval=interval, asset_class=asset_class,
            source=source, metadata=metadata or {},
        )


@dataclass(frozen=True)
class MarketDataRequest:
    symbol: str
    asset_class: AssetClass = AssetClass.EQUITY
    interval: Interval = "1d"
    source: str = "csv"
    start: Optional[str] = None
    end: Optional[str] = None
    adjustment: AdjustmentPolicy = AdjustmentPolicy.ADJUSTED
    extra: Dict[str, Any] = field(default_factory=dict)

    def cache_key(self) -> Tuple[Any, ...]:
        return (
            self.source, self.symbol, self.asset_class.value, self.interval,
            str(self.start), str(self.end), self.adjustment.value,
        )


class MarketCalendar(ABC):
    """Reserved extension point — T4 ships NO concrete calendar.

    The framework makes no assumptions about trading sessions. A future
    implementation decides which timestamps fall within a session; the loader
    applies it only when one is supplied (``calendar=None`` => no filtering).
    """

    @abstractmethod
    def is_trading_session(self, timestamp: datetime) -> bool:
        """Return True if ``timestamp`` falls within a trading session."""
