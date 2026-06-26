from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from backend.app.engines.replay.models import ReplaySpeed


class ReplayClock:
    def __init__(self, speed: ReplaySpeed = ReplaySpeed.ONE_X) -> None:
        self.speed = speed
        self._start_time: Optional[datetime] = None
        self._elapsed: timedelta = timedelta(0)

    def start(self, now: datetime) -> None:
        self._start_time = now
        self._elapsed = timedelta(0)

    def pause(self, now: datetime) -> None:
        self._update_elapsed(now)

    def resume(self, now: datetime) -> None:
        self._start_time = now

    def change_speed(self, speed: ReplaySpeed, now: datetime) -> None:
        self._update_elapsed(now)
        self.speed = speed
        self._start_time = now

    def elapsed(self, now: datetime) -> timedelta:
        self._update_elapsed(now)
        return self._elapsed

    def _update_elapsed(self, now: datetime) -> None:
        if self._start_time is None:
            return
        self._elapsed += (now - self._start_time) * self.speed.multiplier
        self._start_time = now

    def current_time(self, session_start: datetime, now: datetime) -> datetime:
        elapsed = self.elapsed(now)
        return session_start + elapsed
