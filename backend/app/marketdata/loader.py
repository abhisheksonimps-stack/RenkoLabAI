"""HistoricalLoader — orchestrates a clean, ordered historical pull.

Wraps the provider with optional caching and an optional MarketCalendar hook.
The calendar is the reserved extension point: when ``None`` (the default) the
loader makes NO trading-session assumptions; when supplied, it filters bars to
sessions. Output is purely ``List[MarketBar]`` — converting bars to Renko bricks
remains the frozen engine's job.
"""

from __future__ import annotations

from typing import List, Optional

from backend.app.marketdata.cache import MarketDataCache
from backend.app.marketdata.models import MarketBar, MarketCalendar, MarketDataRequest
from backend.app.marketdata.provider import MarketDataProvider


class HistoricalLoader:
    def __init__(self, provider: Optional[MarketDataProvider] = None,
                 cache: Optional[MarketDataCache] = None) -> None:
        self._provider = provider or MarketDataProvider()
        self._cache = cache

    def load(self, request: MarketDataRequest,
             calendar: Optional[MarketCalendar] = None) -> List[MarketBar]:
        if self._cache is not None and self._cache.has(request):
            bars = self._cache.get(request)
        else:
            bars = self._provider.get_history(request)
            if self._cache is not None:
                self._cache.set(request, bars)

        # Reserved extension point: no session assumptions unless a calendar is given.
        if calendar is not None:
            bars = [bar for bar in bars if calendar.is_trading_session(bar.timestamp)]
        return bars
