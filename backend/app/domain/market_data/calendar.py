from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Iterable

from .models import Symbol, TradingSession


class MarketCalendar(ABC):
    """Interface for market calendars and trading sessions."""

    @abstractmethod
    async def is_open(self, symbol: Symbol, when: datetime) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def next_open(self, symbol: Symbol, after: datetime) -> datetime:
        raise NotImplementedError

    @abstractmethod
    async def trading_sessions(self, exchange: str, date: datetime) -> Iterable[TradingSession]:
        raise NotImplementedError
