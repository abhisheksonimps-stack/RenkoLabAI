from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Awaitable, Callable, DefaultDict, Dict, List, Type

from backend.app.events.base import BaseEvent

EventHandler = Callable[[BaseEvent], Awaitable[None]]


class EventRegistry:
    """Registry for typed event classes."""

    def __init__(self) -> None:
        self._registry: Dict[str, Type[BaseEvent]] = {}

    def register(self, event_type: Type[BaseEvent]) -> None:
        if not isinstance(event_type, type) or not issubclass(event_type, BaseEvent):
            raise TypeError("Event type must be a subclass of BaseEvent")
        self._registry[event_type.__name__] = event_type

    def get(self, name: str) -> Type[BaseEvent] | None:
        return self._registry.get(name)

    def all(self) -> list[Type[BaseEvent]]:
        return list(self._registry.values())

    def is_registered(self, event_type: Type[BaseEvent]) -> bool:
        return event_type.__name__ in self._registry


class EventBus:
    """Asynchronous publish/subscribe event bus with typed event support."""

    def __init__(self) -> None:
        self._registry = EventRegistry()
        self._subscribers: DefaultDict[Type[BaseEvent], List[EventHandler]] = defaultdict(list)

    @property
    def registry(self) -> EventRegistry:
        return self._registry

    def register_event(self, event_type: Type[BaseEvent]) -> None:
        self._registry.register(event_type)

    def subscribe(self, event_type: Type[BaseEvent], handler: EventHandler) -> None:
        self._registry.register(event_type)
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: Type[BaseEvent], handler: EventHandler) -> None:
        handlers = self._subscribers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    async def publish(self, event: BaseEvent) -> None:
        if not isinstance(event, BaseEvent):
            raise TypeError("Published event must be an instance of BaseEvent")

        if not self._registry.is_registered(type(event)):
            raise ValueError("Event type is not registered in the event bus")

        tasks = [
            handler(event)
            for registered_type, handlers in self._subscribers.items()
            if isinstance(event, registered_type)
            for handler in handlers
        ]

        if tasks:
            await asyncio.gather(*tasks)
