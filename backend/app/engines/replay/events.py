from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.app.events.base import BaseEvent


@dataclass(frozen=True)
class ReplayStarted(BaseEvent):
    pass


@dataclass(frozen=True)
class ReplayPaused(BaseEvent):
    pass


@dataclass(frozen=True)
class ReplayResumed(BaseEvent):
    pass


@dataclass(frozen=True)
class ReplayStopped(BaseEvent):
    pass


@dataclass(frozen=True)
class ReplayCompleted(BaseEvent):
    pass


@dataclass(frozen=True)
class TickReplayed(BaseEvent):
    pass


@dataclass(frozen=True)
class CandleReplayed(BaseEvent):
    pass


@dataclass(frozen=True)
class ReplaySpeedChanged(BaseEvent):
    pass


@dataclass(frozen=True)
class ReplaySeeked(BaseEvent):
    pass
