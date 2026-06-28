"""BrickDataSource — supplies completed Renko bricks for a scenario.

The frozen layers consume bricks (not OHLC), so validation needs a deterministic
source of bricks keyed by (symbol, dataset, brick spec, date range). T3 ships an
in-memory provider and a caching wrapper (load once, reuse across scenarios that
share data). Real OHLC->Renko loaders can implement the same ABC later without
touching this module's consumers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional, Tuple

from backend.app.trading.validation.scenario import BrickSpec

DateRange = Tuple[Optional[str], Optional[str]]
SourceKey = Tuple[str, str, str, float, str, Optional[str], Optional[str]]


def make_key(symbol: str, dataset_id: str, brick: BrickSpec, date_range: DateRange) -> SourceKey:
    return (
        symbol, dataset_id, brick.brick_type, brick.brick_size, brick.timeframe,
        date_range[0], date_range[1],
    )


class BrickDataSource(ABC):
    @abstractmethod
    def get_bricks(self, *, symbol: str, dataset_id: str, brick: BrickSpec,
                   date_range: DateRange = (None, None)) -> List:
        """Return the (deterministic) list of completed bricks for the key."""


class InMemoryBrickDataSource(BrickDataSource):
    """Holds pre-built brick series registered by key."""

    def __init__(self) -> None:
        self._store: Dict[SourceKey, List] = {}

    def register(self, *, symbol: str, dataset_id: str, bricks: List,
                 brick: Optional[BrickSpec] = None,
                 date_range: DateRange = (None, None)) -> None:
        key = make_key(symbol, dataset_id, brick or BrickSpec(), date_range)
        self._store[key] = list(bricks)

    def get_bricks(self, *, symbol: str, dataset_id: str, brick: BrickSpec,
                   date_range: DateRange = (None, None)) -> List:
        key = make_key(symbol, dataset_id, brick, date_range)
        if key not in self._store:
            raise KeyError(f"No bricks registered for {key}")
        return self._store[key]


class CachingBrickDataSource(BrickDataSource):
    """Wraps a loader function and caches by key (loads once, reuses)."""

    def __init__(self, loader: Callable[[str, str, BrickSpec, DateRange], List]) -> None:
        self._loader = loader
        self._cache: Dict[SourceKey, List] = {}
        self.load_count = 0

    def get_bricks(self, *, symbol: str, dataset_id: str, brick: BrickSpec,
                   date_range: DateRange = (None, None)) -> List:
        key = make_key(symbol, dataset_id, brick, date_range)
        if key not in self._cache:
            self.load_count += 1
            self._cache[key] = list(self._loader(symbol, dataset_id, brick, date_range))
        return self._cache[key]
