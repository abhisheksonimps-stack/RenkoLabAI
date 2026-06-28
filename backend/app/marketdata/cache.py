"""MarketDataCache — in-memory, request-keyed (load once, reuse).

Caches normalized MarketBar lists (never raw payloads), keyed by the request
identity (source/symbol/asset_class/interval/start/end/adjustment). Historical
data is immutable, so caching is safe; live data should bypass the cache.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from backend.app.marketdata.models import MarketBar, MarketDataRequest


class MarketDataCache:
    def __init__(self) -> None:
        self._store: Dict[Tuple, List[MarketBar]] = {}

    def has(self, request: MarketDataRequest) -> bool:
        return request.cache_key() in self._store

    def get(self, request: MarketDataRequest) -> List[MarketBar]:
        return list(self._store[request.cache_key()])

    def set(self, request: MarketDataRequest, bars: List[MarketBar]) -> None:
        self._store[request.cache_key()] = list(bars)

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)
