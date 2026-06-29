"""Tests for market data streaming infrastructure."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import List

import pytest

from backend.app.events.base import BaseEvent
from backend.app.marketdata.streaming.dispatcher import EventDispatcher
from backend.app.marketdata.streaming.events import (
    CandleEvent,
    MarketStatusEvent,
    OrderBookEvent,
    TickEvent,
)
from backend.app.marketdata.streaming.interfaces import (
    MarketDataPublisher,
    MarketDataSubscriber,
    MarketDataStream,
)
from backend.app.marketdata.streaming.manager import StreamingManager


class MockStream(MarketDataStream):
    """Mock market data stream for testing."""

    def __init__(self, events: List[BaseEvent]) -> None:
        self._events = events
        self._connected = False
        self._subscribed_symbols: List[str] = []

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def subscribe(self, symbol: str) -> None:
        self._subscribed_symbols.append(symbol)

    async def unsubscribe(self, symbol: str) -> None:
        if symbol in self._subscribed_symbols:
            self._subscribed_symbols.remove(symbol)

    def events(self):
        async def _events():
            for event in self._events:
                yield event

        return _events()

    @property
    def is_connected(self) -> bool:
        """Check if stream is connected."""
        return self._connected


class MockSubscriber(MarketDataSubscriber):
    """Mock subscriber for testing."""

    def __init__(self) -> None:
        self.events: List[BaseEvent] = []
        self.event_types: List[str] = []

    async def on_event(self, event: BaseEvent) -> None:
        self.events.append(event)
        self.event_types.append(event.name)


class MockPublisher(MarketDataPublisher):
    """Mock publisher for testing."""

    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.published_events: List[BaseEvent] = []

    async def publish(self, event: BaseEvent) -> None:
        self.published_events.append(event)

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


class TestEventDispatcher:
    """Tests for EventDispatcher."""

    @pytest.fixture
    def dispatcher(self) -> EventDispatcher:
        return EventDispatcher()

    @pytest.mark.asyncio
    async def test_subscribe(self, dispatcher: EventDispatcher) -> None:
        """Test subscribing a handler to an event type."""
        received: List[TickEvent] = []

        async def handler(event: BaseEvent) -> None:
            if isinstance(event, TickEvent):
                received.append(event)

        dispatcher.subscribe(TickEvent, handler)
        assert len(dispatcher._subscribers[TickEvent]) == 1

    @pytest.mark.asyncio
    async def test_unsubscribe(self, dispatcher: EventDispatcher) -> None:
        """Test unsubscribing a handler from an event type."""

        async def handler(event: BaseEvent) -> None:
            pass

        dispatcher.subscribe(TickEvent, handler)
        assert len(dispatcher._subscribers[TickEvent]) == 1

        dispatcher.unsubscribe(TickEvent, handler)
        assert len(dispatcher._subscribers[TickEvent]) == 0

    @pytest.mark.asyncio
    async def test_publish(self, dispatcher: EventDispatcher) -> None:
        """Test publishing an event to subscribers."""
        received: List[TickEvent] = []

        async def handler(event: BaseEvent) -> None:
            if isinstance(event, TickEvent):
                received.append(event)

        dispatcher.subscribe(TickEvent, handler)
        await dispatcher.start()

        event = TickEvent(
            name="TickEvent",
            occurred_at=datetime.now(),
            payload={},
            symbol="BTC/USD",
            price=50000.0,
            size=1.0,
            side="buy",
            exchange="binance",
        )
        await dispatcher.publish(event)

        assert len(received) == 1
        assert received[0].symbol == "BTC/USD"

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self, dispatcher: EventDispatcher) -> None:
        """Test publishing to multiple subscribers."""
        received1: List[TickEvent] = []
        received2: List[TickEvent] = []

        async def handler1(event: BaseEvent) -> None:
            if isinstance(event, TickEvent):
                received1.append(event)

        async def handler2(event: BaseEvent) -> None:
            if isinstance(event, TickEvent):
                received2.append(event)

        dispatcher.subscribe(TickEvent, handler1)
        dispatcher.subscribe(TickEvent, handler2)
        await dispatcher.start()

        event = TickEvent(
            name="TickEvent",
            occurred_at=datetime.now(),
            payload={},
            symbol="ETH/USD",
            price=3000.0,
            size=2.0,
            side="sell",
            exchange="coinbase",
        )
        await dispatcher.publish(event)

        assert len(received1) == 1
        assert len(received2) == 1
        assert received1[0].symbol == "ETH/USD"
        assert received2[0].symbol == "ETH/USD"

    @pytest.mark.asyncio
    async def test_async_delivery(self, dispatcher: EventDispatcher) -> None:
        """Test async event delivery."""
        delivery_order: List[str] = []

        async def handler1(event: BaseEvent) -> None:
            await asyncio.sleep(0.01)
            delivery_order.append("handler1")

        async def handler2(event: BaseEvent) -> None:
            delivery_order.append("handler2")

        dispatcher.subscribe(TickEvent, handler1)
        dispatcher.subscribe(TickEvent, handler2)
        await dispatcher.start()

        event = TickEvent(
            name="TickEvent",
            occurred_at=datetime.now(),
            payload={},
            symbol="BTC/USD",
            price=50000.0,
            size=1.0,
            side="buy",
            exchange="binance",
        )
        await dispatcher.publish(event)

        # Both handlers should have been called
        assert len(delivery_order) == 2
        assert "handler1" in delivery_order
        assert "handler2" in delivery_order

    @pytest.mark.asyncio
    async def test_exception_isolation(self, dispatcher: EventDispatcher) -> None:
        """Test that one failing handler doesn't affect others."""
        received: List[TickEvent] = []

        async def failing_handler(event: BaseEvent) -> None:
            raise RuntimeError("Handler failed")

        async def working_handler(event: BaseEvent) -> None:
            if isinstance(event, TickEvent):
                received.append(event)

        dispatcher.subscribe(TickEvent, failing_handler)
        dispatcher.subscribe(TickEvent, working_handler)
        await dispatcher.start()

        event = TickEvent(
            name="TickEvent",
            occurred_at=datetime.now(),
            payload={},
            symbol="BTC/USD",
            price=50000.0,
            size=1.0,
            side="buy",
            exchange="binance",
        )
        # Should not raise despite failing handler
        await dispatcher.publish(event)

        # Working handler should still have received the event
        assert len(received) == 1
        assert received[0].symbol == "BTC/USD"

    @pytest.mark.asyncio
    async def test_dispatcher_shutdown(self, dispatcher: EventDispatcher) -> None:
        """Test dispatcher shutdown."""
        await dispatcher.start()
        assert await dispatcher.health() is True

        await dispatcher.stop()
        assert await dispatcher.health() is False

    @pytest.mark.asyncio
    async def test_health_state(self, dispatcher: EventDispatcher) -> None:
        """Test health state reporting."""
        assert await dispatcher.health() is False

        await dispatcher.start()
        assert await dispatcher.health() is True

        await dispatcher.stop()
        assert await dispatcher.health() is False


class TestStreamingManager:
    """Tests for StreamingManager."""

    @pytest.fixture
    def manager(self) -> StreamingManager:
        return StreamingManager()

    @pytest.fixture
    def sample_events(self) -> List[BaseEvent]:
        """Create sample events for testing."""
        return [
            TickEvent(
                name="TickEvent",
                occurred_at=datetime.now(),
                payload={},
                symbol="BTC/USD",
                price=50000.0,
                size=1.0,
                side="buy",
                exchange="binance",
            ),
            CandleEvent(
                name="CandleEvent",
                occurred_at=datetime.now(),
                payload={},
                symbol="BTC/USD",
                open=50000.0,
                high=50100.0,
                low=49900.0,
                close=50050.0,
                volume=100.0,
                interval="1m",
                trades=50,
            ),
        ]

    @pytest.mark.asyncio
    async def test_register_stream(self, manager: StreamingManager) -> None:
        """Test registering a stream."""
        stream = MockStream([])
        manager.register_stream("test", stream)
        assert "test" in manager._streams

    @pytest.mark.asyncio
    async def test_unregister_stream(self, manager: StreamingManager) -> None:
        """Test unregistering a stream."""
        stream = MockStream([])
        manager.register_stream("test", stream)
        manager.unregister_stream("test")
        assert "test" not in manager._streams

    @pytest.mark.asyncio
    async def test_register_subscriber(self, manager: StreamingManager) -> None:
        """Test registering a subscriber."""
        subscriber = MockSubscriber()
        manager.register_subscriber("sub1", subscriber)
        assert "sub1" in manager._subscribers

    @pytest.mark.asyncio
    async def test_unregister_subscriber(self, manager: StreamingManager) -> None:
        """Test unregistering a subscriber."""
        subscriber = MockSubscriber()
        manager.register_subscriber("sub1", subscriber)
        manager.unregister_subscriber("sub1")
        assert "sub1" not in manager._subscribers

    @pytest.mark.asyncio
    async def test_start_stop(
        self, manager: StreamingManager, sample_events: List[BaseEvent]
    ) -> None:
        """Test starting and stopping the manager."""
        stream = MockStream(sample_events)
        manager.register_stream("test", stream)

        await manager.start()
        assert manager._running is True
        health = await manager.health()
        assert health["running"] is True

        await manager.stop()
        assert manager._running is False
        health = await manager.health()
        assert health["running"] is False

    @pytest.mark.asyncio
    async def test_event_delivery(
        self, manager: StreamingManager, sample_events: List[BaseEvent]
    ) -> None:
        """Test event delivery through the manager."""
        stream = MockStream(sample_events)
        subscriber = MockSubscriber()

        manager.register_stream("test", stream)
        manager.register_subscriber("sub1", subscriber)

        await manager.start()

        # Give time for events to be processed
        await asyncio.sleep(0.1)

        await manager.stop()

        # Subscriber should have received events
        assert len(subscriber.events) == len(sample_events)

    @pytest.mark.asyncio
    async def test_multiple_subscribers(
        self, manager: StreamingManager, sample_events: List[BaseEvent]
    ) -> None:
        """Test multiple subscribers receiving events."""
        stream = MockStream(sample_events)
        subscriber1 = MockSubscriber()
        subscriber2 = MockSubscriber()

        manager.register_stream("test", stream)
        manager.register_subscriber("sub1", subscriber1)
        manager.register_subscriber("sub2", subscriber2)

        await manager.start()
        await asyncio.sleep(0.1)
        await manager.stop()

        # Both subscribers should have received all events
        assert len(subscriber1.events) == len(sample_events)
        assert len(subscriber2.events) == len(sample_events)

    @pytest.mark.asyncio
    async def test_health_state(self, manager: StreamingManager) -> None:
        """Test health state reporting."""
        health = await manager.health()
        assert health["running"] is False
        assert health["dispatcher"] is False
        assert health["streams"] == {}
        assert health["subscribers"] == 0

        stream = MockStream([])
        manager.register_stream("test", stream)
        await manager.start()

        health = await manager.health()
        assert health["running"] is True
        assert health["dispatcher"] is True
        assert "test" in health["streams"]

        await manager.stop()