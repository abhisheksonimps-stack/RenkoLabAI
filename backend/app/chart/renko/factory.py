from __future__ import annotations

from backend.app.chart.renko.configuration import BrickConfiguration
from backend.app.chart.renko.registry import RenkoRegistry
from backend.app.chart.renko.interfaces import RenkoEngine


class RenkoFactory:
    def __init__(self, registry: RenkoRegistry) -> None:
        self._registry = registry

    def create(self, configuration: BrickConfiguration) -> RenkoEngine:
        return self._registry.lookup(configuration)
