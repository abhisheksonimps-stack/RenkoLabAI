"""WebSocket stream implementation for market data."""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from backend.app.events.base import BaseEvent
from backend.app.marketdata.streaming.events import TickEvent
from backend.app.marketdata.streaming.interfaces import MarketDataStream

logger = logging.getLogger(__name__)


class WebSocketStream(MarketDataStream):
    """Base class for WebSocket market data streams.

    Provides common WebSocket functionality including connection management,
    subscription handling, heartbeat, and message parsing.
    """

    def __init__(
        self,
        url: str,
        *,
        heartbeat_interval: float = 30.0,
        reconnect_enabled: bool = True,
        parse_message: Optional[Callable[[Dict[str, Any]], BaseEvent]] = None,
    ) -> None:
        self.url = url
        self.heartbeat_interval = heartbeat_interval
        self.reconnect_enabled = reconnect_enabled
        self.parse_message = parse_message or self._default_parse_message

        self._ws: Optional[Any] = None
        self._connected = False
        self._subscribed_symbols: List[str] = []
        self._receive_task: Optional[asyncio.Task[None]] = None
        self._heartbeat_task: Optional[asyncio.Task[None]] = None
        self._running = False
        self._message_queue: asyncio.Queue[BaseEvent] = asyncio.Queue()

    async def connect(self) -> None:
        """Establish WebSocket connection."""
        if self._connected:
            return

        try:
            # Import websockets here to avoid hard dependency
            import websockets
            self._ws = await websockets.connect(self.url)
            self._connected = True
            logger.info("Connected to WebSocket: %s", self.url)

            # Start background tasks
            self._running = True
            self._receive_task = asyncio.create_task(self._receive_loop())
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        except ImportError:
            raise RuntimeError(
                "websockets package is required for WebSocketStream. "
                "Install it with: pip install websockets"
            )
        except Exception as exc:
            logger.error("Failed to connect to WebSocket: %s", exc)
            raise

    async def disconnect(self) -> None:
        """Close WebSocket connection."""
        self._running = False

        # Cancel background tasks
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # Close WebSocket
        if self._ws:
            await self._ws.close()
            self._ws = None

        self._connected = False
        logger.info("Disconnected from WebSocket: %s", self.url)

    async def subscribe(self, symbol: str) -> None:
        """Subscribe to market data for a symbol."""
        if symbol not in self._subscribed_symbols:
            self._subscribed_symbols.append(symbol)
            await self._send_subscription(symbol, subscribe=True)

    async def unsubscribe(self, symbol: str) -> None:
        """Unsubscribe from market data for a symbol."""
        if symbol in self._subscribed_symbols:
            self._subscribed_symbols.remove(symbol)
            await self._send_subscription(symbol, subscribe=False)

    async def _send_subscription(self, symbol: str, subscribe: bool) -> None:
        """Send subscription message to WebSocket."""
        if not self._ws:
            logger.warning("WebSocket not connected, cannot %s %s",
                          "subscribe to" if subscribe else "unsubscribe from", symbol)
            return

        message = self._build_subscription_message(symbol, subscribe)
        if message:
            await self._ws.send(json.dumps(message))
            logger.debug("%s %s", "Subscribed to" if subscribe else "Unsubscribed from", symbol)

    def _build_subscription_message(self, symbol: str, subscribe: bool) -> Optional[Dict[str, Any]]:
        """Build subscription message. Override in subclasses."""
        return None

    def events(self) -> AsyncIterator[BaseEvent]:
        """Yield market data events as they arrive."""
        async def _events():
            while self._running or not self._message_queue.empty():
                try:
                    event = await asyncio.wait_for(self._message_queue.get(), timeout=1.0)
                    yield event
                except asyncio.TimeoutError:
                    continue

        return _events()

    async def _receive_loop(self) -> None:
        """Receive messages from WebSocket."""
        while self._running and self._ws:
            try:
                message = await self._ws.recv()
                event = self._parse_message(message)
                if event:
                    await self._message_queue.put(event)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error receiving message: %s", exc)
                if self.reconnect_enabled:
                    break  # Trigger reconnect
                else:
                    continue

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats."""
        while self._running and self._connected:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                if self._connected:
                    await self._send_heartbeat()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Heartbeat error: %s", exc)

    async def _send_heartbeat(self) -> None:
        """Send heartbeat message. Override in subclasses."""
        pass

    async def heartbeat(self) -> None:
        """Manual heartbeat check."""
        if self._connected:
            await self._send_heartbeat()

    def _parse_message(self, message: str) -> Optional[BaseEvent]:
        """Parse incoming message into event."""
        try:
            data = json.loads(message)
            return self.parse_message(data)
        except Exception as exc:
            logger.error("Failed to parse message: %s", exc)
            return None

    def _default_parse_message(self, data: Dict[str, Any]) -> BaseEvent:
        """Default message parser. Override in subclasses."""
        return TickEvent(
            name="TickEvent",
            occurred_at=datetime.now(),
            payload=data,
            symbol=data.get("symbol", ""),
            price=float(data.get("price", 0)),
            size=float(data.get("size", 0)),
            side=data.get("side", ""),
            exchange=data.get("exchange", ""),
        )

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._connected