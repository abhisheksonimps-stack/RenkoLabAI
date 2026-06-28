"""Adapter registry — name-keyed factories (same pattern as the Renko/strategy
registries). New sources register here with no change to provider/models/consumers.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from backend.app.marketdata.adapters.base import MarketDataAdapter
from backend.app.marketdata.errors import AdapterNotFound

AdapterFactory = Callable[..., MarketDataAdapter]


class AdapterRegistry:
    def __init__(self) -> None:
        self._factories: Dict[str, AdapterFactory] = {}

    def register(self, name: str, factory: AdapterFactory) -> None:
        if not name:
            raise ValueError("Adapter name must be a non-empty string")
        self._factories[name] = factory

    def get(self, name: str) -> AdapterFactory:
        if name not in self._factories:
            raise AdapterNotFound(f"Unknown market data adapter: {name}")
        return self._factories[name]

    def exists(self, name: str) -> bool:
        return name in self._factories

    def names(self) -> List[str]:
        return list(self._factories.keys())

    def create(self, name: str, **kwargs: Any) -> MarketDataAdapter:
        return self.get(name)(**kwargs)


def default_registry() -> AdapterRegistry:
    from backend.app.marketdata.adapters.csv import CsvAdapter
    from backend.app.marketdata.adapters.yahoo import YahooAdapter

    registry = AdapterRegistry()
    registry.register("csv", lambda **kw: CsvAdapter(**kw))
    registry.register("yahoo", lambda **kw: YahooAdapter(**kw))
    return registry
