"""Compatibility bridge between EventBus and EventDispatcher."""

from __future__ import annotations

from backend.app.events.base import BaseEvent
from backend.app.events.bus import EventBus
from backend.app.marketdata.streaming.dispatcher import EventDispatcher


class EventSystemBridge:
    """Mirror published events between the domain event bus and streaming dispatcher."""

    def __init__(self, event_bus: EventBus, dispatcher: EventDispatcher) -> None:
        self._event_bus = event_bus
        self._dispatcher = dispatcher
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        await self._dispatcher.start()
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return
        await self._dispatcher.stop()
        self._started = False

    def subscribe(self, event_type: type[BaseEvent], handler) -> None:
        self._event_bus.subscribe(event_type, handler)
        self._dispatcher.subscribe(event_type, handler)

    def unsubscribe(self, event_type: type[BaseEvent], handler) -> None:
        self._event_bus.unsubscribe(event_type, handler)
        self._dispatcher.unsubscribe(event_type, handler)

    async def publish(self, event: BaseEvent) -> None:
        if not self._event_bus.registry.is_registered(type(event)):
            self._event_bus.register_event(type(event))
        await self._event_bus.publish(event)
        await self._dispatcher.publish(event)

    async def health(self) -> dict[str, object]:
        return {
            "started": self._started,
            "dispatcher": await self._dispatcher.health(),
            "registered_events": len(self._event_bus.registry.all()),
        }


__all__ = ["EventSystemBridge"]
