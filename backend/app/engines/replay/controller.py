from __future__ import annotations

from datetime import datetime
from typing import AsyncIterator, Optional

from backend.app.domain.market_data.models import Candle, Tick
from backend.app.engines.replay.events import (
    CandleReplayed,
    ReplayCompleted,
    ReplayPaused,
    ReplayResumed,
    ReplaySeeked,
    ReplaySpeedChanged,
    ReplayStarted,
    ReplayStopped,
    TickReplayed,
)
from backend.app.engines.replay.interfaces import ReplayEngine, ReplaySource
from backend.app.engines.replay.models import ReplayCursor, ReplaySession, ReplaySpeed, ReplayState
from backend.app.events.bus import EventBus


class ReplayController(ReplayEngine):
    def __init__(
        self,
        session: ReplaySession,
        source: ReplaySource,
        event_bus: EventBus,
    ) -> None:
        self.session = session
        self.source = source
        self.event_bus = event_bus
        self._tick_iterator: Optional[AsyncIterator[Tick]] = None
        self._candle_iterator: Optional[AsyncIterator[Candle]] = None
        self._next_tick: Optional[Tick] = None
        self._next_candle: Optional[Candle] = None
        self._current_tick: Optional[Tick] = None
        self._current_candle: Optional[Candle] = None
        self._register_events()

    def _register_events(self) -> None:
        self.event_bus.register_event(ReplayStarted)
        self.event_bus.register_event(ReplayPaused)
        self.event_bus.register_event(ReplayResumed)
        self.event_bus.register_event(ReplayStopped)
        self.event_bus.register_event(ReplayCompleted)
        self.event_bus.register_event(TickReplayed)
        self.event_bus.register_event(CandleReplayed)
        self.event_bus.register_event(ReplaySpeedChanged)
        self.event_bus.register_event(ReplaySeeked)

    async def start(self) -> None:
        if self.session.state == ReplayState.RUNNING:
            return

        self.session.state = ReplayState.RUNNING
        self.session.current_time = self.session.start_time
        self._tick_iterator = self.source.ticks(self.session)
        self._candle_iterator = self.source.candles(self.session)
        await self._publish_event(ReplayStarted, {})

    async def pause(self) -> None:
        if self.session.state != ReplayState.RUNNING:
            return

        self.session.state = ReplayState.PAUSED
        await self._publish_event(ReplayPaused, {})

    async def resume(self) -> None:
        if self.session.state != ReplayState.PAUSED:
            return

        self.session.state = ReplayState.RUNNING
        await self._publish_event(ReplayResumed, {})

    async def stop(self) -> None:
        if self.session.state == ReplayState.STOPPED:
            return

        self.session.state = ReplayState.STOPPED
        await self._publish_event(ReplayStopped, {})

    async def restart(self) -> None:
        await self.stop()
        self.session.reset()
        await self.start()

    async def seek(self, timestamp: datetime) -> None:
        timestamp = self.session.clamp(timestamp)
        self.session.current_time = timestamp
        self._tick_iterator = self.source.ticks(self.session)
        self._candle_iterator = self.source.candles(self.session)
        self._next_tick = None
        self._next_candle = None
        await self._publish_event(ReplaySeeked, {"timestamp": timestamp.isoformat()})

    async def step_tick(self) -> None:
        await self._assert_running()
        if self._tick_iterator is None:
            self._tick_iterator = self.source.ticks(self.session)

        tick = await self._get_tick()
        if tick is None:
            await self._complete_if_finished(source_exhausted=True)
            return

        self.session.current_time = tick.timestamp
        self._current_tick = tick
        await self._publish_event(TickReplayed, {"tick": tick.model_dump()})

        if await self._peek_tick_is_exhausted():
            await self._complete_if_finished(source_exhausted=True)
            return

        await self._complete_if_finished()

    async def step_candle(self) -> None:
        await self._assert_running()
        if self._candle_iterator is None:
            self._candle_iterator = self.source.candles(self.session)

        candle = await self._get_candle()
        if candle is None:
            await self._complete_if_finished(source_exhausted=True)
            return

        self.session.current_time = candle.start_time
        self._current_candle = candle
        await self._publish_event(CandleReplayed, {"candle": candle.model_dump()})

        if await self._peek_candle_is_exhausted():
            await self._complete_if_finished(source_exhausted=True)
            return

        await self._complete_if_finished()

    async def change_speed(self, speed: ReplaySpeed) -> None:
        if self.session.speed == speed:
            return

        self.session.speed = speed
        await self._publish_event(ReplaySpeedChanged, {"speed": speed.value})

    async def _complete_if_finished(self, source_exhausted: bool = False) -> None:
        if source_exhausted or self.session.is_completed:
            self.session.state = ReplayState.COMPLETED
            await self._publish_event(ReplayCompleted, {})

    async def _assert_running(self) -> None:
        if self.session.state != ReplayState.RUNNING:
            raise RuntimeError("Replay engine is not running")

    async def _get_tick(self) -> Optional[Tick]:
        if self._next_tick is not None:
            tick = self._next_tick
            self._next_tick = None
            return tick

        try:
            return await self._tick_iterator.__anext__()  # type: ignore[attr-defined]
        except (StopAsyncIteration, TypeError):
            return None

    async def _peek_tick_is_exhausted(self) -> bool:
        if self._next_tick is not None:
            return False

        try:
            self._next_tick = await self._tick_iterator.__anext__()  # type: ignore[attr-defined]
            return False
        except StopAsyncIteration:
            return True

    async def _get_candle(self) -> Optional[Candle]:
        if self._next_candle is not None:
            candle = self._next_candle
            self._next_candle = None
            return candle

        try:
            return await self._candle_iterator.__anext__()  # type: ignore[attr-defined]
        except (StopAsyncIteration, TypeError):
            return None

    async def _peek_candle_is_exhausted(self) -> bool:
        if self._next_candle is not None:
            return False

        try:
            self._next_candle = await self._candle_iterator.__anext__()  # type: ignore[attr-defined]
            return False
        except StopAsyncIteration:
            return True

    async def _publish_event(self, event_type, payload: dict) -> None:
        event = event_type(
            name=event_type.__name__,
            occurred_at=datetime.utcnow(),
            payload=payload,
        )
        await self.event_bus.publish(event)
