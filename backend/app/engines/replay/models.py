from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Generic, Optional, TypeVar

from backend.app.domain.market_data.enums import Timeframe


class ReplayState(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"


class ReplaySpeed(str, Enum):
    ONE_X = "1x"
    TWO_X = "2x"
    FIVE_X = "5x"
    TEN_X = "10x"
    FIFTY_X = "50x"
    ONE_HUNDRED_X = "100x"

    @property
    def multiplier(self) -> float:
        return {
            ReplaySpeed.ONE_X: 1.0,
            ReplaySpeed.TWO_X: 2.0,
            ReplaySpeed.FIVE_X: 5.0,
            ReplaySpeed.TEN_X: 10.0,
            ReplaySpeed.FIFTY_X: 50.0,
            ReplaySpeed.ONE_HUNDRED_X: 100.0,
        }[self]


T = TypeVar("T")


@dataclass(frozen=True)
class ReplayCursor(Generic[T]):
    timestamp: datetime
    payload: T


@dataclass
class ReplaySession:
    session_id: str
    start_time: datetime
    end_time: datetime
    current_time: datetime
    speed: ReplaySpeed = ReplaySpeed.ONE_X
    state: ReplayState = ReplayState.STOPPED
    seek_target: Optional[datetime] = None

    def advance(self, delta: timedelta) -> None:
        self.current_time += delta

    def reset(self) -> None:
        self.current_time = self.start_time
        self.state = ReplayState.STOPPED
        self.seek_target = None

    @property
    def is_completed(self) -> bool:
        return self.current_time >= self.end_time

    def clamp(self, timestamp: datetime) -> datetime:
        if timestamp < self.start_time:
            return self.start_time
        if timestamp > self.end_time:
            return self.end_time
        return timestamp
