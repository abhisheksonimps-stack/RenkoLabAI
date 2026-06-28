"""Adapter base: the uniform contract + shared normalization helpers.

Adapters are the only place that knows a source's quirks. Everything above sees
uniform ``MarketBar``s. Adapters are stateless per request; caching is layered
above them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator, List, Optional, Tuple

from backend.app.marketdata.errors import NotSupported
from backend.app.marketdata.models import (
    AdjustmentPolicy,
    AssetClass,
    MarketBar,
    MarketDataRequest,
)


class MarketDataAdapter(ABC):
    """Turns one source's raw data into normalized MarketBars."""

    name: str = "adapter"

    @abstractmethod
    def fetch(self, request: MarketDataRequest) -> List[MarketBar]:
        """Return normalized bars for the request (historical)."""

    def supports(self, request: MarketDataRequest) -> bool:
        """Capability check; override to reject unsupported intervals/assets."""
        return True

    def stream(self, request: MarketDataRequest) -> Iterator[MarketBar]:
        """Live streaming seam (future). Historical-only adapters leave this."""
        raise NotSupported(f"{self.name} adapter does not support live streaming")


def apply_adjustment(
    open_: float, high: float, low: float, close: float,
    adj_close: Optional[float],
    policy: AdjustmentPolicy,
    asset_class: AssetClass,
) -> Tuple[float, float, float, float]:
    """Respect the AdjustmentPolicy for equity data.

    ADJUSTED + equity + an adjusted close available -> scale OHLC by the
    adjusted/raw ratio and use the adjusted close. Otherwise return raw values.
    Non-equity asset classes are never adjusted.
    """
    if (
        policy is AdjustmentPolicy.ADJUSTED
        and asset_class is AssetClass.EQUITY
        and adj_close is not None
        and close
    ):
        factor = adj_close / close
        return open_ * factor, high * factor, low * factor, adj_close
    return open_, high, low, close


def normalize_bars(bars: List[MarketBar]) -> List[MarketBar]:
    """Deduplicate by timestamp (last wins) and sort ascending by time."""
    by_ts = {}
    for bar in bars:
        by_ts[bar.timestamp] = bar
    return sorted(by_ts.values(), key=lambda b: b.timestamp)
