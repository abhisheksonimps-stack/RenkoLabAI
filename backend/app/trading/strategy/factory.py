"""Strategy factory — resolves strategies dynamically from a registry.

No hardcoded if/else chains: resolution is purely registry-driven, the same
architectural style used by the Renko factory/registry.
"""

from __future__ import annotations

from typing import Any, Optional

from backend.app.trading.strategy.interfaces import Strategy
from backend.app.trading.strategy.registry import StrategyRegistry, default_strategy_registry


class StrategyFactory:
    def __init__(self, registry: Optional[StrategyRegistry] = None) -> None:
        self._registry = registry if registry is not None else default_strategy_registry()

    def create(self, name: str, **kwargs: Any) -> Strategy:
        return self._registry.create(name, **kwargs)

    def available(self) -> list[str]:
        return self._registry.names()

    @property
    def registry(self) -> StrategyRegistry:
        return self._registry
