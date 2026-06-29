"""Market data streaming interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterable, Awaitable, Callable, TypeVar

from backend.app.events.base import BaseEvent

T = TypeVar("T", bound=BaseEvent)


class MarketDataStream(ABC):
    """Abstract base class for market data streams."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the data source."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the data source."""

    @abstractmethod
    async def subscribe(self, symbol: str) -> None:
        """Subscribe to market data for a symbol."""

    @abstractmethod
    async def unsubscribe(self, symbol: str) -> None:
        """Unsubscribe from market data for a symbol."""

    @abstractmethod
    def events(self) -> AsyncIterable[BaseEvent]:
        """Yield market data events as they arrive."""


class MarketDataSubscriber(ABC):
    """Abstract base class for market data subscribers."""

    @abstractmethod
    async def on_event(self, event: BaseEvent) -> None:
        """Handle an incoming market data event."""


class MarketDataPublisher(ABC):
    """Abstract base class for market data publishers."""

    @abstractmethod
    async def publish(self, event: BaseEvent) -> None:
        """Publish a market data event to subscribers."""

    @abstractmethod
    async def start(self) -> None:
        """Start the publisher."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the publisher."""