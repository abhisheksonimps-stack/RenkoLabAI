"""Strategy factory.

Resolution is registry-driven and configuration-aware. This keeps validation,
backtesting, paper trading, and future live trading on the same strategy seam.
"""

from __future__ import annotations

from typing import Any, Optional

from backend.app.trading.strategy.interfaces import Strategy, StrategyConfiguration
from backend.app.trading.strategy.registry import StrategyRegistry, default_strategy_registry


class StrategyFactory:
    """Create fresh strategy instances from a registry."""

    def __init__(self, registry: Optional[StrategyRegistry] = None) -> None:
        self._registry = registry if registry is not None else default_strategy_registry()

    def create(self, name: str, **kwargs: Any) -> Strategy:
        """Create a strategy by name and keyword parameters."""
        return self._registry.create(name, **kwargs)

    def create_from_configuration(self, configuration: StrategyConfiguration) -> Strategy:
        """Create a strategy from a Sprint 8 StrategyConfiguration."""
        return self.create(configuration.name, **dict(configuration.parameters))

    def available(self) -> list[str]:
        """Return all available strategy names."""
        return self._registry.names()

    @property
    def registry(self) -> StrategyRegistry:
        """Return the backing registry."""
        return self._registry
