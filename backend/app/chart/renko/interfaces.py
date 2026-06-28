from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from backend.app.chart.renko.configuration import BrickConfiguration
from backend.app.chart.renko.models import BrickSnapshot, BrickState


class RenkoEngine(ABC):
    @property
    @abstractmethod
    def state(self) -> BrickState:
        raise NotImplementedError

    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def reset(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def configure(self, configuration: BrickConfiguration) -> None:
        raise NotImplementedError

    @abstractmethod
    async def process_market_data(self, market_data: Any) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_snapshot(self) -> BrickSnapshot:
        raise NotImplementedError


class PriceReferenceStrategy(ABC):
    """Selects a single reference price from one candle.

    Stateless and side-effect free: given one candle it returns one price and
    owns nothing else (no brick logic, no ATR, no percentage maths, no history).
    This keeps price selection independently extensible from sizing.
    """

    @abstractmethod
    def reference_price(self, candle: Any) -> float:
        raise NotImplementedError

    def export_state(self) -> dict:
        """Return this strategy's persistable state. Stateless by default."""
        return {}

    def import_state(self, state: dict) -> None:
        """Restore this strategy's state. No-op by default (stateless)."""
        return None


class BrickSizeProvider(ABC):
    """Abstraction that owns brick-size calculation.

    The engine treats a provider as a black box: it feeds completed candles
    in via ``update`` and reads the current brick size via ``current_size``.
    All state required to compute the size lives inside the provider so the
    engine no longer owns brick-size calculation.
    """

    @abstractmethod
    def update(self, candle: Any) -> None:
        """Incorporate a completed candle into the provider's rolling state."""
        raise NotImplementedError

    @abstractmethod
    def current_size(self) -> float:
        """Return the current brick size. Only valid when ``ready()`` is True."""
        raise NotImplementedError

    @abstractmethod
    def ready(self) -> bool:
        """Return whether a brick size is available (e.g. warm-up complete)."""
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        """Completely clear provider state so replay is deterministic."""
        raise NotImplementedError

    def export_state(self) -> dict:
        """Return this provider's persistable rolling state. Empty by default."""
        return {}

    def import_state(self, state: dict) -> None:
        """Restore this provider's rolling state. No-op by default (stateless)."""
        return None


class BrickBuilder(ABC):
    @abstractmethod
    async def build_brick(self, market_data: Any, configuration: BrickConfiguration) -> "Brick":
        raise NotImplementedError

    def export_state(self) -> dict:
        """Return this builder's persistable state. Stateless by default."""
        return {}

    def import_state(self, state: dict) -> None:
        """Restore this builder's state. No-op by default (stateless)."""
        return None


class BrickValidator(ABC):
    @abstractmethod
    async def validate_configuration(self, configuration: BrickConfiguration) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def validate_data(self, market_data: Any) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def validate_transition(self, previous_state: BrickState, next_state: BrickState) -> bool:
        raise NotImplementedError
