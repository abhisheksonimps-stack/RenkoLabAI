"""Normalized market quote — the executable view of incoming market data.

Live feeds and replay sources speak in :class:`Tick` and :class:`Candle`
objects (see :mod:`backend.app.domain.market_data.models`). The exchange
simulator only needs a small, uniform view of price: a reference price plus the
intrabar extremes used to decide whether resting limit/stop orders trigger.
``MarketQuote`` is that view, and the ``from_tick`` / ``from_candle`` adapters
keep the conversion in one place so no caller has to special-case the source.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.app.domain.market_data.models import Candle, Tick


@dataclass(frozen=True)
class MarketQuote:
    """A single executable price point for one symbol.

    ``price`` is the reference (last/trade/close) price. ``high`` and ``low``
    bound the move covered by this update; for a tick they collapse onto
    ``price``, for a candle they are the bar extremes. Trigger detection uses
    ``high``/``low`` so an intrabar limit/stop touch is not missed.
    """

    symbol: str
    timestamp: datetime
    price: float
    high: float
    low: float

    @classmethod
    def from_tick(cls, tick: Tick) -> "MarketQuote":
        price = float(tick.price)
        return cls(symbol=tick.symbol, timestamp=tick.timestamp,
                   price=price, high=price, low=price)

    @classmethod
    def from_candle(cls, candle: Candle) -> "MarketQuote":
        return cls(
            symbol=candle.symbol,
            timestamp=candle.start_time,
            price=float(candle.close),
            high=float(candle.high),
            low=float(candle.low),
        )
