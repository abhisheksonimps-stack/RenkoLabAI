"""Subscription manager for market data streams."""

from __future__ import annotations

import asyncio
import logging
from typing import List, Set

from backend.app.marketdata.streaming.interfaces import MarketDataStream

logger = logging.getLogger(__name__)


class SubscriptionManager:
    """Manages subscriptions to market data streams."""

    def __init__(self, stream: MarketDataStream) -> None:
        self._stream = stream
        self._subscriptions: Set[str] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self, symbol: str) -> None:
        """Subscribe to a single symbol."""
        async with self._lock:
            if symbol not in self._subscriptions:
                await self._stream.subscribe(symbol)
                self._subscriptions.add(symbol)

    async def unsubscribe(self, symbol: str) -> None:
        """Unsubscribe from a single symbol."""
        async with self._lock:
            if symbol in self._subscriptions:
                await self._stream.unsubscribe(symbol)
                self._subscriptions.discard(symbol)

    async def subscribe_many(self, symbols: List[str]) -> None:
        """Subscribe to multiple symbols."""
        async with self._lock:
            for symbol in symbols:
                if symbol not in self._subscriptions:
                    await self._stream.subscribe(symbol)
                    self._subscriptions.add(symbol)

    async def unsubscribe_many(self, symbols: List[str]) -> None:
        """Unsubscribe from multiple symbols."""
        async with self._lock:
            for symbol in symbols:
                if symbol in self._subscriptions:
                    await self._stream.unsubscribe(symbol)
                    self._subscriptions.discard(symbol)

    def is_subscribed(self, symbol: str) -> bool:
        """Check if subscribed to a symbol."""
        return symbol in self._subscriptions

    @property
    def active_subscriptions(self) -> Set[str]:
        """Get set of active subscriptions."""
        return self._subscriptions.copy()

    @property
    def subscription_count(self) -> int:
        """Get number of active subscriptions."""
        return len(self._subscriptions)