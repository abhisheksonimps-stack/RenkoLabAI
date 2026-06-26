from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import AsyncIterator, List

from .enums import Timeframe
from .models import Candle, Symbol, Tick


class MarketDataProvider(ABC):
    """Base interface for market data providers."""

    @abstractmethod
    async def connect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def disconnect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def is_connected(self) -> bool:
        raise NotImplementedError


class HistoricalDataProvider(MarketDataProvider):
    """Interface for historical market data providers."""

    @abstractmethod
    async def fetch_historical(
        self, symbol: Symbol, timeframe: Timeframe, start: datetime, end: datetime
    ) -> List[Candle]:
        raise NotImplementedError


class StreamingDataProvider(MarketDataProvider):
    """Interface for streaming market data providers."""

    @abstractmethod
    async def stream_ticks(self, symbol: Symbol) -> AsyncIterator[Tick]:
        raise NotImplementedError

    @abstractmethod
    async def subscribe_candles(
        self, symbol: Symbol, timeframe: Timeframe
    ) -> AsyncIterator[Candle]:
        raise NotImplementedError
