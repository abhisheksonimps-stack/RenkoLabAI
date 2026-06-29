"""Strategy registry.

Name-keyed factories mirror the Renko registries. Strategies are stateful, so
registries store factories instead of shared strategy instances.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, Iterable, List, Type

from backend.app.trading.strategy.interfaces import Strategy

StrategyFactoryFn = Callable[..., Strategy]


class StrategyRegistry:
    """Registry of strategy factories keyed by canonical strategy name."""

    def __init__(self) -> None:
        self._factories: Dict[str, StrategyFactoryFn] = {}
        self._classes: Dict[str, Type[Strategy]] = {}

    @staticmethod
    def _normalize_name(name: str) -> str:
        normalized = str(name).strip()
        if not normalized:
            raise ValueError("Strategy name must be a non-empty string")
        return normalized

    def register(self, name: str, factory: StrategyFactoryFn) -> None:
        """Register a strategy factory under ``name``."""
        normalized = self._normalize_name(name)
        if not callable(factory):
            raise TypeError("Strategy factory must be callable")
        self._factories[normalized] = factory

    def register_class(self, strategy_cls: Type[Strategy], name: str | None = None) -> None:
        """Register a Strategy subclass using its explicit or declared name."""
        if not inspect.isclass(strategy_cls) or not issubclass(strategy_cls, Strategy):
            raise TypeError("strategy_cls must be a Strategy subclass")
        resolved_name = self._normalize_name(name or getattr(strategy_cls, "name", strategy_cls.__name__))
        self._classes[resolved_name] = strategy_cls
        self.register(resolved_name, lambda **kwargs: strategy_cls(**kwargs))

    def get(self, name: str) -> StrategyFactoryFn:
        """Return the factory registered for ``name``."""
        normalized = self._normalize_name(name)
        if normalized not in self._factories:
            raise KeyError(f"Unknown strategy: {normalized}")
        return self._factories[normalized]

    def exists(self, name: str) -> bool:
        """Return whether a strategy exists in this registry."""
        return self._normalize_name(name) in self._factories

    def names(self) -> List[str]:
        """Return registered names in deterministic order."""
        return sorted(self._factories.keys())

    def classes(self) -> Dict[str, Type[Strategy]]:
        """Return registered concrete strategy classes."""
        return dict(self._classes)

    def create(self, name: str, **kwargs: Any) -> Strategy:
        """Create a fresh strategy instance."""
        strategy = self.get(name)(**kwargs)
        if not isinstance(strategy, Strategy):
            raise TypeError(f"Factory for strategy {name!r} did not return a Strategy")
        return strategy

    def merge(self, other: "StrategyRegistry") -> None:
        """Copy registrations from another registry."""
        for name in other.names():
            self.register(name, other.get(name))
        self._classes.update(other.classes())


_DEFAULT_REGISTRY: StrategyRegistry | None = None


def register_builtin_strategies(registry: StrategyRegistry) -> StrategyRegistry:
    """Register all first-party strategies."""
    from backend.app.trading.strategy.ema_crossover import EMACrossoverStrategy
    from backend.app.trading.strategy.ema_trend import EMATrendStrategy
    from backend.app.trading.strategy.pdh_pdl_breakout import PDHPDLBreakoutStrategy
    from backend.app.trading.strategy.renko_trend import RenkoTrendStrategy

    for strategy_cls in (
        EMACrossoverStrategy,
        EMATrendStrategy,
        PDHPDLBreakoutStrategy,
        RenkoTrendStrategy,
    ):
        registry.register_class(strategy_cls)
    return registry


def default_strategy_registry(*, reload: bool = False) -> StrategyRegistry:
    """Return the process default strategy registry."""
    global _DEFAULT_REGISTRY
    if reload or _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = register_builtin_strategies(StrategyRegistry())
    return _DEFAULT_REGISTRY


def build_strategy_registry(strategies: Iterable[Type[Strategy]] = ()) -> StrategyRegistry:
    """Build a registry with built-ins plus supplied strategy classes."""
    registry = register_builtin_strategies(StrategyRegistry())
    for strategy_cls in strategies:
        registry.register_class(strategy_cls)
    return registry
