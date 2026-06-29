"""Streaming manager for market data."""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional, Type

from backend.app.events.base import BaseEvent
from backend.app.marketdata.streaming.dispatcher import EventDispatcher
from backend.app.marketdata.streaming.interfaces import (
    MarketDataPublisher,
    MarketDataStream,
    MarketDataSubscriber,
)

logger = logging.getLogger(__name__)


class StreamingManager:
    """Manager for market data streams and subscribers.

    Coordinates multiple streams, dispatches events to subscribers,
    and provides health monitoring.
    """

    def __init__(self) -> None:
        self._streams: Dict[str, MarketDataStream] = {}
        self._subscribers: Dict[str, MarketDataSubscriber] = {}
        self._dispatcher = EventDispatcher()
        self._running = False
        self._tasks: List[asyncio.Task[None]] = []

    def register_stream(self, name: str, stream: MarketDataStream) -> None:
        """Register a market data stream."""
        self._streams[name] = stream
        logger.info("Registered stream: %s", name)

    def unregister_stream(self, name: str) -> None:
        """Unregister a market data stream."""
        if name in self._streams:
            del self._streams[name]
            logger.info("Unregistered stream: %s", name)

    def register_subscriber(self, name: str, subscriber: MarketDataSubscriber) -> None:
        """Register a subscriber for all events."""
        self._subscribers[name] = subscriber
        # Subscribe to all event types through the dispatcher
        from backend.app.marketdata.streaming.events import (
            CandleEvent,
            MarketStatusEvent,
            OrderBookEvent,
            TickEvent,
        )

        for event_type in [TickEvent, CandleEvent, OrderBookEvent, MarketStatusEvent]:
            self._dispatcher.subscribe(event_type, subscriber.on_event)
        logger.info("Registered subscriber: %s", name)

    def unregister_subscriber(self, name: str) -> None:
        """Unregister a subscriber."""
        if name in self._subscribers:
            del self._subscribers[name]
            logger.info("Unregistered subscriber: %s", name)

    async def start(self) -> None:
        """Start all streams and the dispatcher."""
        if self._running:
            return

        self._running = True
        logger.info("Starting streaming manager")

        # Start dispatcher
        await self._dispatcher.start()

        # Start all streams
        for name, stream in self._streams.items():
            task = asyncio.create_task(self._run_stream(name, stream))
            self._tasks.append(task)

        logger.info("Streaming manager started with %d streams", len(self._streams))

    async def stop(self) -> None:
        """Stop all streams and the dispatcher."""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping streaming manager")

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()

        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        # Stop dispatcher
        await self._dispatcher.stop()

        # Disconnect all streams
        for stream in self._streams.values():
            try:
                await stream.disconnect()
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("Error disconnecting stream: %s", exc)

        logger.info("Streaming manager stopped")

    async def _run_stream(self, name: str, stream: MarketDataStream) -> None:
        """Run a single stream and dispatch its events."""
        try:
            await stream.connect()
            logger.info("Stream %s connected", name)

            async for event in stream.events():
                if not self._running:
                    break
                await self._dispatcher.publish(event)

        except asyncio.CancelledError:
            logger.info("Stream %s cancelled", name)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Stream %s error: %s", name, exc)
        finally:
            try:
                await stream.disconnect()
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("Error disconnecting stream %s: %s", name, exc)

    async def health(self) -> Dict[str, bool]:
        """Check health of all streams and dispatcher."""
        dispatcher_health = await self._dispatcher.health()

        stream_health = {}
        for name, stream in self._streams.items():
            # Basic health check - stream is registered
            stream_health[name] = name in self._streams

        return {
            "running": self._running,
            "dispatcher": dispatcher_health,
            "streams": stream_health,
            "subscribers": len(self._subscribers),
        }

    @property
    def dispatcher(self) -> EventDispatcher:
        """Get the event dispatcher."""
        return self._dispatcher