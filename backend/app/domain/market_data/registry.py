from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

from .enums import AssetClass
from .models import Symbol


class SymbolRegistry:
    """Registry for symbol metadata and lookup operations."""

    def __init__(self) -> None:
        self._symbols: Dict[str, Symbol] = {}
        self._symbols_by_exchange: Dict[str, List[Symbol]] = defaultdict(list)
        self._symbols_by_asset_class: Dict[AssetClass, List[Symbol]] = defaultdict(list)

    def register(self, symbol: Symbol) -> None:
        self._symbols[symbol.symbol] = symbol
        self._symbols_by_exchange[symbol.exchange].append(symbol)
        self._symbols_by_asset_class[symbol.asset_class].append(symbol)

    def get(self, symbol: str) -> Optional[Symbol]:
        return self._symbols.get(symbol.strip().upper())

    def list(
        self, exchange: Optional[str] = None, asset_class: Optional[AssetClass] = None
    ) -> List[Symbol]:
        if exchange and asset_class:
            return [
                symbol
                for symbol in self._symbols_by_exchange.get(exchange.strip().upper(), [])
                if symbol.asset_class == asset_class
            ]
        if exchange:
            return self._symbols_by_exchange.get(exchange.strip().upper(), [])
        if asset_class:
            return self._symbols_by_asset_class.get(asset_class, [])
        return list(self._symbols.values())
