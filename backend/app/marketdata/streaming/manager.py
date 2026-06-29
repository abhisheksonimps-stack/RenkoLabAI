"""Streaming manager for market data."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Type

from backend.app.events.base import BaseEvent
from backend.app.marketdata.streaming.dispatcher import EventDispatcher
from backend.app.marketdata.streaming.interfaces import (
    MarketDataPublisher,
    MarketDataStream,
    MarketDataSubscriber,
)
from backend.app.marketdata.streaming.reconnect import ReconnectManager
from backend.app.marketdata.streaming.router import MarketRouter

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
        self._router = MarketRouter()
        self._reconnect_managers: Dict[str, ReconnectManager] = {}
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
            if name in self._reconnect_managers:
                del self._reconnect_managers[name]
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

    def register_reconnect_manager(self, stream_name: str, manager: ReconnectManager) -> None:
        """Register a reconnect manager for a stream."""
        self._reconnect_managers[stream_name] = manager
        logger.info("Registered reconnect manager for stream: %s", stream_name)

    async def start(self) -> None:
        """Start all streams and the dispatcher."""
        if self._running:
            return

        self._running = True
        logger.info("Starting streaming manager")

        # Start dispatcher and router
        await self._dispatcher.start()
        await self._router.start()

        # Start all streams
        for name, stream in self._streams.items():
            task = asyncio.create_task(self._run_stream(name, stream))
            self._tasks.append(task)

        # Start all reconnect managers
        for name, manager in self._reconnect_managers.items():
            task = asyncio.create_task(self._run_reconnect_manager(name, manager))
            self._tasks.append(task)

        logger.info("Streaming manager started with %d streams", len(self._streams))

    async def _run_reconnect_manager(self, name: str, manager: ReconnectManager) -> None:
        """Run a reconnect manager."""
        try:
            await manager.monitor()
        except asyncio.CancelledError:
            logger.info("Reconnect manager %s cancelled", name)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Reconnect manager %s error: %s", name, exc)
        finally:
            await manager.stop()

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

        # Stop all reconnect managers
        for manager in self._reconnect_managers.values():
            try:
                await manager.stop()
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("Error stopping reconnect manager: %s", exc)

        # Stop dispatcher and router
        await self._router.stop()
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
                await self._router.route(event)

        except asyncio.CancelledError:
            logger.info("Stream %s cancelled", name)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Stream %s error: %s", name, exc)
        finally:
            try:
                await stream.disconnect()
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("Error disconnecting stream %s: %s", name, exc)

    async def health(self) -> Dict[str, Any]:
        """Check health of all streams, dispatcher, and reconnect managers."""
        dispatcher_health = await self._dispatcher.health()

        stream_health = {}
        for name, stream in self._streams.items():
            stream_health[name] = stream.is_connected

        reconnect_health = {}
        for name, manager in self._reconnect_managers.items():
            reconnect_health[name] = await manager.health()

        return {
            "running": self._running,
            "dispatcher": dispatcher_health,
            "router": await self._router.health(),
            "streams": stream_health,
            "reconnect_managers": reconnect_health,
            "subscribers": len(self._subscribers),
        }

    @property
    def dispatcher(self) -> EventDispatcher:
        """Get the event dispatcher."""
        return self._dispatcher
    @property
    def router(self) -> MarketRouter:
        """Get the market data router."""
        return self._router

    @property
    def streams(self) -> Dict[str, MarketDataStream]:
        """Get registered streams."""
        return dict(self._streams)
