"""Yahoo Finance adapter.

Network access is isolated behind an injected ``client`` callable, so unit tests
inject a stub and never touch the network. The client returns row mappings with
open/high/low/close/(adj_close)/volume and a timestamp/date field.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, List, Mapping, Optional

from backend.app.marketdata.adapters.base import MarketDataAdapter, apply_adjustment
from backend.app.marketdata.errors import DataUnavailable, MalformedData, RateLimited
from backend.app.marketdata.models import MarketBar, MarketDataRequest

YahooClient = Callable[..., Iterable[Mapping[str, Any]]]


def _default_client(**_: Any) -> Iterable[Mapping[str, Any]]:
    # Real network access is deliberately not bundled. Provide a client via
    # dependency injection (or register a configured adapter) to fetch live data.
    raise DataUnavailable(
        "YahooAdapter requires an injected client; none configured"
    )


class YahooAdapter(MarketDataAdapter):
    name = "yahoo"

    def __init__(self, client: Optional[YahooClient] = None) -> None:
        self._client = client or _default_client

    def fetch(self, request: MarketDataRequest) -> List[MarketBar]:
        try:
            rows = self._client(
                symbol=request.symbol, interval=request.interval,
                start=request.start, end=request.end,
            )
        except (DataUnavailable, RateLimited, MalformedData):
            raise
        except Exception as exc:  # translate any source/network error
            raise DataUnavailable(f"Yahoo fetch failed for {request.symbol}: {exc}") from exc

        bars: List[MarketBar] = []
        for row in rows:
            try:
                ts = row.get("timestamp", row.get("date"))
                o = float(row["open"]); h = float(row["high"])
                l = float(row["low"]); c = float(row["close"])
            except (KeyError, TypeError, ValueError) as exc:
                raise MalformedData(f"Malformed Yahoo row {row}: {exc}") from exc
            adj_raw = row.get("adj_close")
            adj = float(adj_raw) if adj_raw is not None else None
            o, h, l, c = apply_adjustment(o, h, l, c, adj, request.adjustment, request.asset_class)
            volume = float(row.get("volume", 0.0) or 0.0)
            bars.append(MarketBar.create(
                symbol=request.symbol, timestamp=ts, open=o, high=h, low=l, close=c,
                volume=volume, interval=request.interval, asset_class=request.asset_class,
                source=self.name, metadata={"adjustment": request.adjustment.value},
            ))
        return bars
