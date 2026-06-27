from __future__ import annotations

from typing import Optional

from backend.app.chart.renko.configuration import BrickConfiguration
from backend.app.chart.renko.interfaces import RenkoEngine
from backend.app.chart.renko.providers import BrickSizeProviderRegistry
from backend.app.chart.renko.registry import RenkoRegistry


class RenkoFactory:
    """Creates a configured engine wired with the appropriate brick-size provider.

    The engine is resolved from the engine registry (unchanged from before). When
    a provider registry is supplied, the factory also builds the correct
    ``FixedBrickSizeProvider`` or ``ATRBrickSizeProvider`` from configuration and
    injects it into the engine, so the engine no longer owns size calculation.
    """

    def __init__(
        self,
        registry: RenkoRegistry,
        provider_registry: Optional[BrickSizeProviderRegistry] = None,
    ) -> None:
        self._registry = registry
        self._provider_registry = provider_registry

    def create(self, configuration: BrickConfiguration) -> RenkoEngine:
        engine = self._registry.lookup(configuration)
        if self._provider_registry is not None:
            inject = getattr(engine, "set_brick_size_provider", None)
            if callable(inject):
                inject(self._provider_registry.create(configuration))
        return engine

    def create_provider(self, configuration: BrickConfiguration):
        if self._provider_registry is None:
            raise RuntimeError("RenkoFactory has no provider registry configured")
        return self._provider_registry.create(configuration)
