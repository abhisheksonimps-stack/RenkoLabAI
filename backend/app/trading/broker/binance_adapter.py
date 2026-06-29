"""Binance broker adapter built on the existing CCXT adapter."""

from __future__ import annotations

from typing import Any

from backend.app.trading.broker.ccxt_adapter import CCXTAdapter


class BinanceAdapter(CCXTAdapter):
    """Production Binance adapter using CCXT's Binance implementation."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__("binance", config or {})


__all__ = ["BinanceAdapter"]
