"""MarketDataProvider — the single public entry point.

Resolves an adapter from the registry by ``request.source``, delegates, and
returns validated, normalized bars. Knows nothing about specific sources.
"""

from __future__ import annotations

from typing import Iterator, List, Optional

from backend.app.marketdata.adapters.base import normalize_bars
from backend.app.marketdata.errors import NotSupported
from backend.app.marketdata.models import MarketBar, MarketDataRequest
from backend.app.marketdata.registry import AdapterRegistry, default_registry


class MarketDataProvider:
    def __init__(self, registry: Optional[AdapterRegistry] = None, **adapter_kwargs) -> None:
        self._registry = registry or default_registry()
        # Per-source construction kwargs (e.g. {"yahoo": {"client": ...}}).
        self._adapter_kwargs = adapter_kwargs

    def _adapter(self, request: MarketDataRequest):
        kwargs = self._adapter_kwargs.get(request.source, {})
        return self._registry.create(request.source, **kwargs)

    def get_history(self, request: MarketDataRequest) -> List[MarketBar]:
        adapter = self._adapter(request)
        if not adapter.supports(request):
            raise NotSupported(f"{request.source} does not support request {request.symbol}/{request.interval}")
        return normalize_bars(list(adapter.fetch(request)))

    def stream(self, request: MarketDataRequest) -> Iterator[MarketBar]:
        return self._adapter(request).stream(request)
