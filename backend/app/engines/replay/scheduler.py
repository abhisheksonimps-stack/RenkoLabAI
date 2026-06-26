from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from backend.app.domain.market_data.models import Candle, Tick
from backend.app.engines.replay.models import ReplaySession, ReplayState, ReplaySpeed
from backend.app.engines.replay.events import CandleReplayed, ReplayCompleted, TickReplayed
from backend.app.events.bus import EventBus


class ReplayScheduler:
    def __init__(
        self,
        session: ReplaySession,
        source: "ReplaySource",
        event_bus: EventBus,
        tick_buffer_size: int = 1024,
    ) -> None:
        self.session = session
        self.source = source
        self.event_bus = event_bus
        self.tick_buffer_size = tick_buffer_size
        self._task: Optional[asyncio.Task[None]] = None
        self._tick_queue: asyncio.Queue[Tick] = asyncio.Queue(maxsize=tick_buffer_size)
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self.session.state == ReplayState.RUNNING:
            return

        self.session.state = ReplayState.RUNNING
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def pause(self) -> None:
        if self.session.state != ReplayState.RUNNING:
            return

        self.session.state = ReplayState.PAUSED

    async def resume(self) -> None:
        if self.session.state != ReplayState.PAUSED:
            return

        self.session.state = ReplayState.RUNNING

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            await self._task
        self.session.state = ReplayState.STOPPED

    async def _run(self) -> None:
        async for tick in self.source.ticks(self.session):
            if self._stop_event.is_set() or self.session.state != ReplayState.RUNNING:
                break

            self.session.current_time = tick.timestamp
            await self._publish_event(TickReplayed, {"tick": tick.model_dump()})
            await self._sleep_until_next_tick(tick)

        if self.session.state == ReplayState.RUNNING and self.session.is_completed:
            self.session.state = ReplayState.COMPLETED
            await self._publish_event(ReplayCompleted, {})

    async def _sleep_until_next_tick(self, tick: Tick) -> None:
        next_timestamp = tick.timestamp
        next_time = next_timestamp - self.session.current_time
        if next_time.total_seconds() > 0:
            await asyncio.sleep(next_time.total_seconds() / self.session.speed.multiplier)

    async def _publish_event(self, event_type, payload: dict) -> None:
        event = event_type(
            name=event_type.__name__,
            occurred_at=datetime.utcnow(),
            payload=payload,
        )
        await self.event_bus.publish(event)
