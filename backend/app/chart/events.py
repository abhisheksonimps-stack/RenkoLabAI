from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.app.events.base import BaseEvent


@dataclass(frozen=True)
class ChartCreated(BaseEvent):
    pass


@dataclass(frozen=True)
class ChartUpdated(BaseEvent):
    pass


@dataclass(frozen=True)
class ChartClosed(BaseEvent):
    pass


@dataclass(frozen=True)
class ChartValidationFailed(BaseEvent):
    pass
