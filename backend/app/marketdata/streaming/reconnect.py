"""Automatic reconnect manager for WebSocket streams."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from backend.app.marketdata.streaming.interfaces import MarketDataStream

logger = logging.getLogger(__name__)


class ReconnectManager:
    """Automatic reconnect manager with exponential backoff."""

    def __init__(
        self,
        stream: MarketDataStream,
        *,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
        max_retries: int = 10,
        on_reconnect: Optional[Callable[[], None]] = None,
        on_disconnect: Optional[Callable[[], None]] = None,
    ) -> None:
        self.stream = stream
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.max_retries = max_retries
        self.on_reconnect = on_reconnect
        self.on_disconnect = on_disconnect

        self._retry_count = 0
        self._current_delay = initial_delay
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._last_connect_time: Optional[datetime] = None
        self._last_disconnect_time: Optional[datetime] = None

    async def start(self) -> None:
        """Start the reconnect manager."""
        if self._running:
            return

        self._running = True
        self._retry_count = 0
        self._current_delay = self.initial_delay
        logger.info("Reconnect manager started")

    async def stop(self) -> None:
        """Stop the reconnect manager."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Reconnect manager stopped")

    async def monitor(self) -> None:
        """Monitor the stream and reconnect on failures."""
        if not self._running:
            return

        try:
            await self.stream.connect()
            self._last_connect_time = datetime.now()
            self._retry_count = 0
            self._current_delay = self.initial_delay
            logger.info("Stream connected successfully")

            if self.on_reconnect:
                self.on_reconnect()

            while self._running:
                await asyncio.sleep(1.0)
                if not self.stream.is_connected:
                    logger.warning("Stream disconnected, attempting reconnect")
                    self._last_disconnect_time = datetime.now()
                    if self.on_disconnect:
                        self.on_disconnect()
                    await self._reconnect()

        except asyncio.CancelledError:
            logger.info("Monitor task cancelled")
        except Exception as exc:
            logger.error("Monitor error: %s", exc)
            if self._running:
                await self._reconnect()

    async def _reconnect(self) -> None:
        """Attempt to reconnect with exponential backoff."""
        if self._retry_count >= self.max_retries:
            logger.error("Max retries (%d) reached, giving up", self.max_retries)
            return

        logger.info(
            "Reconnect attempt %d/%d in %.1f seconds",
            self._retry_count + 1,
            self.max_retries,
            self._current_delay,
        )

        await asyncio.sleep(self._current_delay)

        try:
            await self.stream.connect()
            self._last_connect_time = datetime.now()
            self._retry_count = 0
            self._current_delay = self.initial_delay
            logger.info("Reconnected successfully")

            if self.on_reconnect:
                self.on_reconnect()

        except Exception as exc:
            self._retry_count += 1
            self._current_delay = min(
                self._current_delay * self.backoff_factor,
                self.max_delay,
            )
            logger.error("Reconnect attempt %d failed: %s", self._retry_count, exc)

    async def health(self) -> Dict[str, Any]:
        """Get health status."""
        return {
            "running": self._running,
            "connected": self.stream.is_connected,
            "retry_count": self._retry_count,
            "current_delay": self._current_delay,
            "last_connect_time": self._last_connect_time,
            "last_disconnect_time": self._last_disconnect_time,
            "max_retries": self.max_retries,
        }

    @property
    def retry_count(self) -> int:
        """Get current retry count."""
        return self._retry_count

    @property
    def is_connected(self) -> bool:
        """Check if stream is connected."""
        return self.stream.is_connected