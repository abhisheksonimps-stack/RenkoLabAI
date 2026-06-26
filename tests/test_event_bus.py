import asyncio
from dataclasses import dataclass
from datetime import datetime

import pytest

from backend.app.events.base import BaseEvent
from backend.app.events.bus import EventBus


@dataclass(frozen=True)
class TestEvent(BaseEvent):
    payload: dict


def test_event_registry_and_publish():
    bus = EventBus()
    bus.register_event(TestEvent)

    received: list[dict] = []

    async def handler(event: TestEvent) -> None:
        received.append(event.payload)

    bus.subscribe(TestEvent, handler)

    async def run() -> None:
        await bus.publish(TestEvent(name="test", occurred_at=datetime.utcnow(), payload={"ok": True}))

    asyncio.run(run())

    assert received == [{"ok": True}]
    assert bus.registry.get("TestEvent") is TestEvent


def test_publish_unregistered_event_raises_value_error():
    bus = EventBus()
    event = TestEvent(name="test", occurred_at=datetime.utcnow(), payload={})

    async def run() -> None:
        with pytest.raises(ValueError):
            await bus.publish(event)

    asyncio.run(run())
