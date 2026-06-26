from __future__ import annotations

from backend.app.events.bus import EventBus
from backend.app.plugins.base import PluginInterface


class SamplePlugin:
    name = "sample"

    def __init__(self) -> None:
        self.is_loaded = False
        self.is_started = False
        self.is_stopped = False
        self.is_unloaded = False
        self.event_bus: EventBus | None = None

    async def load(self, event_bus: EventBus | None = None) -> None:
        self.is_loaded = True
        self.event_bus = event_bus

    async def start(self) -> None:
        self.is_started = True

    async def stop(self) -> None:
        self.is_stopped = True

    async def unload(self) -> None:
        self.is_unloaded = True
