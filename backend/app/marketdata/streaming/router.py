"""Market data router for symbol-based event distribution."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable, Dict, List, Set

from backend.app.events.base import BaseEvent
from backend.app.marketdata.streaming.events import TickEvent

logger = logging.getLogger(__name__)

EventHandler = Callable[[BaseEvent], Awaitable[None]]


class MarketRouter:
    """Routes market data events by symbol to registered handlers."""

    def __init__(self, max_queue_size: int = 10000) -> None:
        self._symbol_handlers: Dict[str, List[EventHandler]] = defaultdict(list)
        self._global_handlers: List[EventHandler] = []
        self._symbol_registry: Set[str] = set()
        self._queue: asyncio.Queue[BaseEvent] = asyncio.Queue(maxsize=max_queue_size)
        self._running = False
        self._processed_count = 0

    def register_symbol(self, symbol: str) -> None:
        """Register a symbol for routing."""
        self._symbol_registry.add(symbol)

    def unregister_symbol(self, symbol: str) -> None:
        """Unregister a symbol and remove all handlers."""
        self._symbol_registry.discard(symbol)
        if symbol in self._symbol_handlers:
            del self._symbol_handlers[symbol]

    def subscribe(self, symbol: str, handler: EventHandler) -> None:
        """Subscribe a handler to a specific symbol."""
        if symbol not in self._symbol_registry:
            self.register_symbol(symbol)
        if handler not in self._symbol_handlers[symbol]:
            self._symbol_handlers[symbol].append(handler)

    def unsubscribe(self, symbol: str, handler: EventHandler) -> None:
        """Unsubscribe a handler from a specific symbol."""
        handlers = self._symbol_handlers.get(symbol, [])
        if handler in handlers:
            handlers.remove(handler)
        if not handlers and symbol in self._symbol_handlers:
            del self._symbol_handlers[symbol]

    def subscribe_global(self, handler: EventHandler) -> None:
        """Subscribe a handler to all events."""
        if handler not in self._global_handlers:
            self._global_handlers.append(handler)

    def unsubscribe_global(self, handler: EventHandler) -> None:
        """Unsubscribe a global handler."""
        if handler in self._global_handlers:
            self._global_handlers.remove(handler)

    async def route(self, event: BaseEvent) -> None:
        """Route an event to appropriate handlers."""
        if not self._running:
            try:
                self._queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Router queue full, dropping event")
            return
        await self._dispatch(event)

    async def _dispatch(self, event: BaseEvent) -> None:
        """Dispatch event to symbol-specific and global handlers."""
        tasks = []
        if isinstance(event, TickEvent) and event.symbol:
            handlers = self._symbol_handlers.get(event.symbol, [])
            for handler in handlers:
                tasks.append(self._safe_handler(handler, event))
        for handler in self._global_handlers:
            tasks.append(self._safe_handler(handler, event))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._processed_count += 1

    async def _safe_handler(self, handler: EventHandler, event: BaseEvent) -> None:
        """Execute handler with exception isolation."""
        try:
            await handler(event)
        except Exception as exc:
            logger.exception("Handler failed: %s", exc)

    async def start(self) -> None:
        """Start the router."""
        if self._running:
            return
        self._running = True
        while not self._queue.empty():
            try:
                event = self._queue.get_nowait()
                await self._dispatch(event)
            except asyncio.QueueEmpty:
                break

    async def stop(self) -> None:
        """Stop the router."""
        self._running = False

    async def health(self) -> Dict[str, Any]:
        """Get router health status."""
        return {
            "running": self._running,
            "registered_symbols": len(self._symbol_registry),
            "active_subscriptions": sum(len(h) for h in self._symbol_handlers.values()),
            "global_handlers": len(self._global_handlers),
            "queue_size": self._queue.qsize(),
            "processed_count": self._processed_count,
        }

    @property
    def active_symbols(self) -> Set[str]:
        """Get set of active symbols."""
        return self._symbol_registry.copy()

    @property
    def processed_count(self) -> int:
        """Get total processed event count."""
        return self._processed_count