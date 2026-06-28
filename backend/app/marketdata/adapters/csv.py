"""CSV adapter — normalizes OHLCV from a file or text with a configurable map."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Dict, List, Optional

from backend.app.marketdata.adapters.base import MarketDataAdapter, apply_adjustment
from backend.app.marketdata.errors import DataUnavailable, MalformedData
from backend.app.marketdata.models import MarketBar, MarketDataRequest, to_utc

DEFAULT_COLUMN_MAP: Dict[str, str] = {
    "timestamp": "timestamp",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
    "adj_close": "adj_close",
}


class CsvAdapter(MarketDataAdapter):
    name = "csv"

    def __init__(self, column_map: Optional[Dict[str, str]] = None,
                 datetime_format: Optional[str] = None, delimiter: str = ",") -> None:
        self.column_map = {**DEFAULT_COLUMN_MAP, **(column_map or {})}
        self.datetime_format = datetime_format
        self.delimiter = delimiter

    def _content(self, request: MarketDataRequest) -> str:
        text = request.extra.get("text")
        if text is not None:
            return text
        path = request.extra.get("path")
        if path is not None:
            with open(path, "r", encoding="utf-8") as handle:
                return handle.read()
        raise DataUnavailable("CSV adapter requires request.extra['text'] or ['path']")

    def _parse_ts(self, raw: str):
        if self.datetime_format:
            try:
                return to_utc(datetime.strptime(raw, self.datetime_format))
            except ValueError as exc:
                raise MalformedData(f"Bad timestamp {raw!r} for format {self.datetime_format!r}") from exc
        return to_utc(raw)

    def fetch(self, request: MarketDataRequest) -> List[MarketBar]:
        reader = csv.DictReader(io.StringIO(self._content(request)), delimiter=self.delimiter)
        cm = self.column_map
        bars: List[MarketBar] = []
        for row in reader:
            try:
                ts = self._parse_ts(row[cm["timestamp"]])
                o = float(row[cm["open"]])
                h = float(row[cm["high"]])
                l = float(row[cm["low"]])
                c = float(row[cm["close"]])
            except (KeyError, TypeError, ValueError) as exc:
                raise MalformedData(f"Malformed CSV row {row}: {exc}") from exc
            adj_col = cm.get("adj_close")
            adj_raw = row.get(adj_col) if adj_col else None
            adj = float(adj_raw) if adj_raw not in (None, "") else None
            o, h, l, c = apply_adjustment(o, h, l, c, adj, request.adjustment, request.asset_class)
            vol_raw = row.get(cm["volume"])
            volume = float(vol_raw) if vol_raw not in (None, "") else 0.0
            bars.append(MarketBar.create(
                symbol=request.symbol, timestamp=ts, open=o, high=h, low=l, close=c,
                volume=volume, interval=request.interval, asset_class=request.asset_class,
                source=self.name, metadata={"adjustment": request.adjustment.value},
            ))
        return bars
