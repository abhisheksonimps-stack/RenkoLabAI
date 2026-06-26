from __future__ import annotations

from backend.app.chart.renko.registry import RenkoRegistry
from backend.app.plugins.base import PluginInterface


class RenkoPlugin(PluginInterface):
    name = "renko_plugin"

    def __init__(self, renko_registry: RenkoRegistry) -> None:
        self.renko_registry = renko_registry

    async def load(self, event_bus=None) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def unload(self) -> None:
        pass

    async def register_renko_engines(self, registry: RenkoRegistry) -> None:
        pass
