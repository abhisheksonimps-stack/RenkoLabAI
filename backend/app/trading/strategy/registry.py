"""Strategy registry — name-keyed factories, mirroring the Renko registries.

Stores *factories* (not shared instances) because strategies hold per-run state:
each lookup yields a fresh strategy with its own state.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from backend.app.trading.strategy.interfaces import Strategy

StrategyFactoryFn = Callable[..., Strategy]


class StrategyRegistry:
    def __init__(self) -> None:
        self._factories: Dict[str, StrategyFactoryFn] = {}

    def register(self, name: str, factory: StrategyFactoryFn) -> None:
        if not name:
            raise ValueError("Strategy name must be a non-empty string")
        self._factories[name] = factory

    def get(self, name: str) -> StrategyFactoryFn:
        if name not in self._factories:
            raise KeyError(f"Unknown strategy: {name}")
        return self._factories[name]

    def exists(self, name: str) -> bool:
        return name in self._factories

    def names(self) -> List[str]:
        return list(self._factories.keys())

    def create(self, name: str, **kwargs: Any) -> Strategy:
        return self.get(name)(**kwargs)


def default_strategy_registry() -> StrategyRegistry:
    """Registry pre-populated with the built-in strategies."""
    from backend.app.trading.strategy.ema_crossover import EMACrossoverStrategy

    registry = StrategyRegistry()
    registry.register("ema_crossover", lambda **kw: EMACrossoverStrategy(**kw))
    return registry
