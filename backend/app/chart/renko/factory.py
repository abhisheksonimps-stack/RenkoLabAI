from __future__ import annotations

from typing import Optional

from backend.app.chart.renko.builder import BrickBuilderRegistry
from backend.app.chart.renko.configuration import BrickConfiguration
from backend.app.chart.renko.interfaces import RenkoEngine
from backend.app.chart.renko.providers import BrickSizeProviderRegistry
from backend.app.chart.renko.registry import RenkoRegistry
from backend.app.chart.renko.strategies import PriceReferenceStrategyRegistry


class RenkoFactory:
    """Creates a configured engine wired with the appropriate brick-size provider.

    The engine is resolved from the engine registry (unchanged). When a provider
    registry is supplied, the factory builds the configured provider and injects
    it into the engine. When a price-reference-strategy registry is also
    supplied, the factory resolves the strategy and injects it into providers
    that select a reference price. When a builder registry is supplied, the
    factory resolves the brick builder through the BrickBuilder abstraction and
    injects it into the engine, so the engine depends on the interface rather
    than a concrete builder.
    """

    def __init__(
        self,
        registry: RenkoRegistry,
        provider_registry: Optional[BrickSizeProviderRegistry] = None,
        strategy_registry: Optional[PriceReferenceStrategyRegistry] = None,
        builder_registry: Optional[BrickBuilderRegistry] = None,
    ) -> None:
        self._registry = registry
        self._provider_registry = provider_registry
        self._strategy_registry = strategy_registry
        self._builder_registry = builder_registry

    def _build_provider(self, configuration: BrickConfiguration):
        provider = self._provider_registry.create(configuration)
        if self._strategy_registry is not None:
            inject_strategy = getattr(provider, "set_price_reference_strategy", None)
            if callable(inject_strategy):
                inject_strategy(self._strategy_registry.create(configuration))
        return provider

    def create(self, configuration: BrickConfiguration) -> RenkoEngine:
        engine = self._registry.lookup(configuration)
        if self._provider_registry is not None:
            provider = self._build_provider(configuration)
            inject = getattr(engine, "set_brick_size_provider", None)
            if callable(inject):
                inject(provider)
        if self._builder_registry is not None:
            inject_builder = getattr(engine, "set_brick_builder", None)
            if callable(inject_builder):
                inject_builder(self._builder_registry.create(configuration))
        return engine

    def create_provider(self, configuration: BrickConfiguration):
        if self._provider_registry is None:
            raise RuntimeError("RenkoFactory has no provider registry configured")
        return self._build_provider(configuration)

    def create_builder(self, configuration: BrickConfiguration):
        if self._builder_registry is None:
            raise RuntimeError("RenkoFactory has no builder registry configured")
        return self._builder_registry.create(configuration)
