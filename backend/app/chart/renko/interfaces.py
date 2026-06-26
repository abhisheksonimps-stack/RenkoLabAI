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
    async def process_market_data(self, market_data: Any) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_snapshot(self) -> BrickSnapshot:
        raise NotImplementedError


class BrickBuilder(ABC):
    @abstractmethod
    async def build_brick(self, market_data: Any, configuration: BrickConfiguration) -> "Brick":
        raise NotImplementedError


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
