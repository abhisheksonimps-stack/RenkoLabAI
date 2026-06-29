"""Async event dispatcher for market data streaming."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Awaitable, Callable, Dict, List, Type

from backend.app.events.base import BaseEvent

logger = logging.getLogger(__name__)

EventHandler = Callable[[BaseEvent], Awaitable[None]]


class EventDispatcher:
    """Async event dispatcher with exception isolation.

    Dispatches events to multiple subscribers while isolating exceptions
    so one failing handler does not affect others.
    """

    def __init__(self) -> None:
        self._subscribers: Dict[Type[BaseEvent], List[EventHandler]] = defaultdict(list)
        self._running = False
        self._queue: asyncio.Queue[BaseEvent] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    def subscribe(self, event_type: Type[BaseEvent], handler: EventHandler) -> None:
        """Subscribe a handler to an event type."""
        self._subscribers[event_type].append(handler)
        logger.debug("Subscribed %s to %s", handler, event_type.__name__)

    def unsubscribe(self, event_type: Type[BaseEvent], handler: EventHandler) -> None:
        """Unsubscribe a handler from an event type."""
        handlers = self._subscribers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)
            logger.debug("Unsubscribed %s from %s", handler, event_type.__name__)

    async def publish(self, event: BaseEvent) -> None:
        """Publish an event to all matching subscribers."""
        if not self._running:
            logger.warning("Dispatcher is not running, queuing event %s", event.name)
            await self._queue.put(event)
            return

        await self._dispatch(event)

    async def _dispatch(self, event: BaseEvent) -> None:
        """Dispatch event to all matching handlers with exception isolation."""
        tasks = []
        for event_type, handlers in self._subscribers.items():
            if isinstance(event, event_type):
                for handler in handlers:
                    tasks.append(self._safe_handler(handler, event))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_handler(self, handler: EventHandler, event: BaseEvent) -> None:
        """Execute handler with exception isolation."""
        try:
            await handler(event)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception(
                "Handler %s failed for event %s: %s", handler, event.name, exc
            )

    async def start(self) -> None:
        """Start the dispatcher and process queued events."""
        if self._running:
            return

        self._running = True
        logger.info("Event dispatcher started")

        # Process any queued events
        while not self._queue.empty():
            event = await self._queue.get()
            await self._dispatch(event)
            self._queue.task_done()

    async def stop(self) -> None:
        """Stop the dispatcher."""
        self._running = False
        logger.info("Event dispatcher stopped")

    async def health(self) -> bool:
        """Check dispatcher health."""
        return self._running