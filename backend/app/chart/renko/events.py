from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.app.events.base import BaseEvent
from backend.app.chart.renko.configuration import BrickConfiguration
from backend.app.chart.renko.models import Brick, BrickSnapshot, BrickState


@dataclass(frozen=True)
class BrickOpened(BaseEvent):
    configuration: BrickConfiguration
    snapshot: BrickSnapshot


@dataclass(frozen=True)
class BrickClosed(BaseEvent):
    configuration: BrickConfiguration
    snapshot: BrickSnapshot
    brick: Brick


@dataclass(frozen=True)
class BrickExtended(BaseEvent):
    configuration: BrickConfiguration
    snapshot: BrickSnapshot
    brick: Brick


@dataclass(frozen=True)
class BrickReversed(BaseEvent):
    configuration: BrickConfiguration
    snapshot: BrickSnapshot
    brick: Brick


@dataclass(frozen=True)
class BrickValidationFailed(BaseEvent):
    configuration: BrickConfiguration
    reason: str


@dataclass(frozen=True)
class BrickSizeUpdated(BaseEvent):
    """Published by the engine when the brick-size provider changes the size.

    Provider-specific event (e.g. ATR re-estimates the size each candle). This
    does not duplicate the existing brick lifecycle events.
    """

    configuration: BrickConfiguration
    provider: str
    brick_size: float


@dataclass(frozen=True)
class RenkoEngineStarted(BaseEvent):
    configuration: BrickConfiguration


@dataclass(frozen=True)
class RenkoEngineStopped(BaseEvent):
    configuration: BrickConfiguration
