from __future__ import annotations

from typing import Optional

from backend.app.chart.renko.builder import BrickBuilderRegistry
from backend.app.chart.renko.providers import BrickSizeProviderRegistry
from backend.app.chart.renko.registry import RenkoRegistry
from backend.app.chart.renko.strategies import PriceReferenceStrategyRegistry
from backend.app.plugins.base import PluginInterface


class RenkoPlugin(PluginInterface):
    name = "renko_plugin"

    def __init__(
        self,
        renko_registry: RenkoRegistry,
        provider_registry: Optional[BrickSizeProviderRegistry] = None,
        strategy_registry: Optional[PriceReferenceStrategyRegistry] = None,
        builder_registry: Optional[BrickBuilderRegistry] = None,
    ) -> None:
        self.renko_registry = renko_registry
        self.provider_registry = provider_registry
        self.strategy_registry = strategy_registry
        self.builder_registry = builder_registry

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

    async def register_brick_size_providers(self, registry: BrickSizeProviderRegistry) -> None:
        """Hook for plugins to register additional brick-size providers."""
        pass

    async def register_price_reference_strategies(
        self, registry: PriceReferenceStrategyRegistry
    ) -> None:
        """Hook for plugins to register additional price-reference strategies."""
        pass

    async def register_brick_builders(self, registry: BrickBuilderRegistry) -> None:
        """Hook for plugins to register additional brick builders."""
        pass
