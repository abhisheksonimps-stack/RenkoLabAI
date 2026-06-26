from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import AsyncIterator, Iterator, Protocol

from backend.app.domain.market_data.models import Candle, Tick
from backend.app.engines.replay.models import ReplaySession


class ReplaySource(Protocol):
    def ticks(self, session: ReplaySession) -> AsyncIterator[Tick]:
        """Yield ticks for a given replay session."""

    def candles(self, session: ReplaySession) -> AsyncIterator[Candle]:
        """Yield candles for a given replay session."""


class ReplayEngine(ABC):
    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def pause(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def resume(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def restart(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def seek(self, timestamp: datetime) -> None:
        raise NotImplementedError

    @abstractmethod
    async def step_tick(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def step_candle(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def change_speed(self, speed: "ReplaySpeed") -> None:
        raise NotImplementedError
