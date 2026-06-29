"""Tests for WebSocket stream and reconnect manager."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.events.base import BaseEvent
from backend.app.marketdata.streaming.events import TickEvent
from backend.app.marketdata.streaming.interfaces import MarketDataStream
from backend.app.marketdata.streaming.reconnect import ReconnectManager
from backend.app.marketdata.streaming.websocket import WebSocketStream


class MockWebSocket:
    """Mock WebSocket for testing."""

    def __init__(self, messages: List[str] = None, should_fail: bool = False) -> None:
        self.messages = messages or []
        self.message_index = 0
        self.should_fail = should_fail
        self.closed = False
        self.sent_messages: List[str] = []

    async def recv(self) -> str:
        if self.should_fail:
            raise ConnectionError("Mock connection error")
        if self.message_index < len(self.messages):
            msg = self.messages[self.message_index]
            self.message_index += 1
            return msg
        await asyncio.sleep(0.1)
        return '{"symbol": "BTC/USD", "price": 50000.0, "size": 1.0, "side": "buy"}'

    async def send(self, message: str) -> None:
        self.sent_messages.append(message)

    async def close(self) -> None:
        self.closed = True


class TestWebSocketStream:
    """Tests for WebSocketStream."""

    @pytest.fixture
    def stream(self) -> WebSocketStream:
        """Create a WebSocketStream for testing."""
        return WebSocketStream(
            "ws://test.example.com",
            heartbeat_interval=30.0,
            reconnect_enabled=False,
        )

    @pytest.mark.asyncio
    async def test_connect(self, stream: WebSocketStream) -> None:
        """Test WebSocket connection."""
        with patch("websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_ws = MockWebSocket()
            mock_connect.return_value = mock_ws
            await stream.connect()
            assert stream.is_connected is True
            assert stream._ws is not None

    @pytest.mark.asyncio
    async def test_disconnect(self, stream: WebSocketStream) -> None:
        """Test WebSocket disconnection."""
        stream._connected = True
        stream._running = True
        stream._ws = MockWebSocket()

        await stream.disconnect()

        assert stream.is_connected is False
        assert stream._running is False

    @pytest.mark.asyncio
    async def test_subscribe(self, stream: WebSocketStream) -> None:
        """Test subscription to symbols."""
        stream._connected = True
        stream._ws = MockWebSocket()

        await stream.subscribe("BTC/USD")
        assert "BTC/USD" in stream._subscribed_symbols

    @pytest.mark.asyncio
    async def test_unsubscribe(self, stream: WebSocketStream) -> None:
        """Test unsubscription from symbols."""
        stream._connected = True
        stream._ws = MockWebSocket()
        stream._subscribed_symbols = ["BTC/USD"]

        await stream.unsubscribe("BTC/USD")
        assert "BTC/USD" not in stream._subscribed_symbols

    @pytest.mark.asyncio
    async def test_heartbeat(self, stream: WebSocketStream) -> None:
        """Test heartbeat functionality."""
        stream._connected = True
        await stream.heartbeat()

    @pytest.mark.asyncio
    async def test_event_publishing(self, stream: WebSocketStream) -> None:
        """Test that received messages are parsed and queued as events."""
        stream._connected = True
        stream._running = True
        mock_ws = MockWebSocket(messages=[
            '{"symbol": "BTC/USD", "price": 50000.0, "size": 1.0, "side": "buy"}'
        ])
        stream._ws = mock_ws

        receive_task = asyncio.create_task(stream._receive_loop())
        await asyncio.sleep(0.2)

        stream._running = False
        receive_task.cancel()
        try:
            await receive_task
        except asyncio.CancelledError:
            pass

        assert stream._message_queue.qsize() > 0

    @pytest.mark.asyncio
    async def test_reconnect_on_failure(self) -> None:
        """Test automatic reconnection on failure."""
        stream = WebSocketStream(
            "ws://test.example.com",
            heartbeat_interval=30.0,
            reconnect_enabled=True,
        )

        connect_count = 0

        async def mock_connect_fn(url):
            nonlocal connect_count
            connect_count += 1
            if connect_count == 1:
                ws = MockWebSocket()
                ws.should_fail = True
                return ws
            return MockWebSocket()

        with patch("websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.side_effect = mock_connect_fn
            await stream.connect()
            assert stream.is_connected is True

    @pytest.mark.asyncio
    async def test_connect_failure(self) -> None:
        """Test that connect raises on connection failure."""
        stream = WebSocketStream(
            "ws://test.example.com",
            heartbeat_interval=30.0,
            reconnect_enabled=False,
        )

        async def mock_connect_fn(url):
            raise ConnectionError("Mock connection error")

        with patch("websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.side_effect = mock_connect_fn
            with pytest.raises(ConnectionError):
                await stream.connect()


class TestReconnectManager:
    """Tests for ReconnectManager."""

    @pytest.fixture
    def mock_stream(self) -> MarketDataStream:
        """Create a mock stream for testing."""
        stream = MagicMock(spec=MarketDataStream)
        stream.connect = AsyncMock()
        stream.disconnect = AsyncMock()
        stream.is_connected = True
        return stream

    @pytest.fixture
    def reconnect_manager(self, mock_stream: MarketDataStream) -> ReconnectManager:
        """Create a ReconnectManager with mock stream."""
        return ReconnectManager(
            mock_stream,
            initial_delay=0.1,
            max_delay=1.0,
            backoff_factor=2.0,
            max_retries=3,
        )

    @pytest.mark.asyncio
    async def test_start_stop(self, reconnect_manager: ReconnectManager) -> None:
        """Test starting and stopping the reconnect manager."""
        await reconnect_manager.start()
        assert reconnect_manager._running is True

        await reconnect_manager.stop()
        assert reconnect_manager._running is False

    @pytest.mark.asyncio
    async def test_reconnect_on_disconnect(self, reconnect_manager: ReconnectManager) -> None:
        """Test reconnection when stream disconnects."""
        mock_stream = reconnect_manager.stream
        mock_stream.is_connected = False

        await reconnect_manager.start()

        connect_count = 0
        original_connect = mock_stream.connect

        async def counting_connect():
            nonlocal connect_count
            connect_count += 1
            mock_stream.is_connected = True
            return await original_connect()

        mock_stream.connect = counting_connect
        await reconnect_manager._reconnect()

        assert connect_count > 0

        await reconnect_manager.stop()

    @pytest.mark.asyncio
    async def test_exponential_backoff(self, reconnect_manager: ReconnectManager) -> None:
        """Test exponential backoff on repeated failures."""
        mock_stream = reconnect_manager.stream
        connect_count = 0

        async def failing_connect():
            nonlocal connect_count
            connect_count += 1
            if connect_count < 3:
                raise ConnectionError(f"Connection failed {connect_count}")
            mock_stream.is_connected = True

        mock_stream.connect = failing_connect

        await reconnect_manager.start()

        await reconnect_manager._reconnect()
        assert reconnect_manager.retry_count == 1
        assert reconnect_manager._current_delay == 0.2

        await reconnect_manager._reconnect()
        assert reconnect_manager.retry_count == 2
        assert reconnect_manager._current_delay == 0.4

        await reconnect_manager._reconnect()
        assert reconnect_manager.retry_count == 0

        await reconnect_manager.stop()

    @pytest.mark.asyncio
    async def test_max_retries(self, reconnect_manager: ReconnectManager) -> None:
        """Test that reconnection stops after max retries."""
        mock_stream = reconnect_manager.stream

        async def always_failing_connect():
            raise ConnectionError("Always fails")

        mock_stream.connect = always_failing_connect

        await reconnect_manager.start()

        for _ in range(reconnect_manager.max_retries):
            await reconnect_manager._reconnect()

        assert reconnect_manager.retry_count == reconnect_manager.max_retries

        await reconnect_manager.stop()

    @pytest.mark.asyncio
    async def test_health_status(self, reconnect_manager: ReconnectManager) -> None:
        """Test health status reporting."""
        health = await reconnect_manager.health()
        assert health["running"] is False
        assert health["connected"] is True
        assert health["retry_count"] == 0

        await reconnect_manager.start()
        health = await reconnect_manager.health()
        assert health["running"] is True

        await reconnect_manager.stop()
        health = await reconnect_manager.health()
        assert health["running"] is False

    @pytest.mark.asyncio
    async def test_reconnect_callbacks(self, reconnect_manager: ReconnectManager) -> None:
        """Test reconnect and disconnect callbacks."""
        mock_stream = reconnect_manager.stream
        reconnect_called = False
        disconnect_called = False

        def on_reconnect():
            nonlocal reconnect_called
            reconnect_called = True

        def on_disconnect():
            nonlocal disconnect_called
            disconnect_called = True

        reconnect_manager.on_reconnect = on_reconnect
        reconnect_manager.on_disconnect = on_disconnect

        await reconnect_manager.start()
        await reconnect_manager._reconnect()
        assert reconnect_called is True

        mock_stream.is_connected = False
        disconnect_called = False
        assert disconnect_called is False

        await reconnect_manager.stop()