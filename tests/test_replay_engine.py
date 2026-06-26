from __future__ import annotations

from datetime import datetime, timedelta, time
from typing import AsyncIterator

import pytest

from backend.app.domain.market_data.models import Candle, Tick, TradingSession
from backend.app.engines.replay import (
    CandleReplayed,
    ReplayController,
    ReplayCompleted,
    ReplayPaused,
    ReplayResumed,
    ReplaySeeked,
    ReplaySpeed,
    ReplaySpeedChanged,
    ReplaySession,
    ReplayStarted,
    ReplayStopped,
    ReplayState,
    TickReplayed,
)
from backend.app.events.bus import EventBus
from backend.app.engines.replay.interfaces import ReplaySource


class InMemoryReplaySource(ReplaySource):
    def __init__(self, ticks: list[Tick], candles: list[Candle]) -> None:
        self._ticks = ticks
        self._candles = candles

    async def ticks(self, session: ReplaySession) -> AsyncIterator[Tick]:
        for tick in self._ticks:
            if tick.timestamp >= session.current_time:
                yield tick

    async def candles(self, session: ReplaySession) -> AsyncIterator[Candle]:
        for candle in self._candles:
            if candle.start_time >= session.current_time:
                yield candle


@pytest.fixture
def event_bus():
    bus = EventBus()
    events: list = []

    async def handler(event):
        events.append(event)

    bus.subscribe(ReplayStarted, handler)
    bus.subscribe(ReplayPaused, handler)
    bus.subscribe(ReplayResumed, handler)
    bus.subscribe(ReplayStopped, handler)
    bus.subscribe(ReplayCompleted, handler)
    bus.subscribe(TickReplayed, handler)
    bus.subscribe(CandleReplayed, handler)
    bus.subscribe(ReplaySpeedChanged, handler)
    bus.subscribe(ReplaySeeked, handler)
    return bus, events


@pytest.fixture
def session():
    return ReplaySession(
        session_id="session-1",
        start_time=datetime(2026, 1, 1, 10, 0, 0),
        end_time=datetime(2026, 1, 1, 10, 5, 0),
        current_time=datetime(2026, 1, 1, 10, 0, 0),
    )


def make_tick(seconds: int, price: float) -> Tick:
    return Tick(
        symbol="BTCUSDT",
        exchange="BINANCE",
        timestamp=datetime(2026, 1, 1, 10, 0, seconds),
        price=price,
        size=1.0,
    )


def make_candle(seconds: int, price: float) -> Candle:
    return Candle(
        symbol="BTCUSDT",
        exchange="BINANCE",
        timeframe="1m",
        start_time=datetime(2026, 1, 1, 10, 0, seconds),
        open=price,
        high=price,
        low=price,
        close=price,
        volume=1.0,
        trades=1,
    )


@pytest.mark.asyncio
async def test_start_and_complete_replay(event_bus, session):
    bus, events = event_bus
    source = InMemoryReplaySource([make_tick(10, 100.0)], [])
    controller = ReplayController(session, source, bus)

    await controller.start()
    assert session.state == ReplayState.RUNNING
    assert isinstance(events[0], ReplayStarted)

    await controller.step_tick()
    assert isinstance(events[1], TickReplayed)

    assert session.state == ReplayState.COMPLETED
    assert isinstance(events[2], ReplayCompleted)


@pytest.mark.asyncio
async def test_pause_resume(event_bus, session):
    bus, events = event_bus
    source = InMemoryReplaySource([make_tick(10, 100.0)], [])
    controller = ReplayController(session, source, bus)

    await controller.start()
    await controller.pause()
    assert session.state == ReplayState.PAUSED
    assert isinstance(events[1], ReplayPaused)

    await controller.resume()
    assert session.state == ReplayState.RUNNING
    assert isinstance(events[2], ReplayResumed)


@pytest.mark.asyncio
async def test_stop(event_bus, session):
    bus, events = event_bus
    source = InMemoryReplaySource([], [])
    controller = ReplayController(session, source, bus)

    await controller.start()
    await controller.stop()

    assert session.state == ReplayState.STOPPED
    assert isinstance(events[1], ReplayStopped)


@pytest.mark.asyncio
async def test_seek(event_bus, session):
    bus, events = event_bus
    source = InMemoryReplaySource([make_tick(10, 100.0)], [])
    controller = ReplayController(session, source, bus)

    await controller.start()
    await controller.seek(datetime(2026, 1, 1, 10, 2, 0))

    assert session.current_time == datetime(2026, 1, 1, 10, 2, 0)
    assert any(isinstance(event, ReplaySeeked) for event in events)


@pytest.mark.asyncio
async def test_change_speed(event_bus, session):
    bus, events = event_bus
    source = InMemoryReplaySource([make_tick(10, 100.0)], [])
    controller = ReplayController(session, source, bus)

    await controller.start()
    await controller.change_speed(ReplaySpeed.TEN_X)

    assert session.speed == ReplaySpeed.TEN_X
    assert isinstance(events[1], ReplaySpeedChanged)


@pytest.mark.asyncio
async def test_step_candle(event_bus, session):
    bus, events = event_bus
    source = InMemoryReplaySource([], [make_candle(0, 100.0)])
    controller = ReplayController(session, source, bus)

    await controller.start()
    await controller.step_candle()

    assert isinstance(events[1], CandleReplayed)
    assert session.state == ReplayState.COMPLETED


@pytest.mark.asyncio
async def test_empty_dataset(event_bus, session):
    bus, events = event_bus
    source = InMemoryReplaySource([], [])
    controller = ReplayController(session, source, bus)

    await controller.start()
    await controller.step_tick()

    assert isinstance(events[1], ReplayCompleted)
    assert session.state == ReplayState.COMPLETED


@pytest.mark.asyncio
async def test_invalid_step_when_paused(event_bus, session):
    bus, _ = event_bus
    source = InMemoryReplaySource([make_tick(10, 100.0)], [])
    controller = ReplayController(session, source, bus)

    await controller.start()
    await controller.pause()

    with pytest.raises(RuntimeError):
        await controller.step_tick()


@pytest.mark.asyncio
async def test_large_dataset_performance(event_bus, session):
    bus, events = event_bus
    ticks = [make_tick(i, 100.0 + i) for i in range(0, 60, 5)]
    source = InMemoryReplaySource(ticks, [])
    controller = ReplayController(session, source, bus)

    await controller.start()
    for _ in ticks:
        await controller.step_tick()

    assert len([e for e in events if isinstance(e, TickReplayed)]) == len(ticks)
    assert isinstance(events[-1], ReplayCompleted)


@pytest.mark.asyncio
async def test_seek_before_start_time(event_bus, session):
    bus, events = event_bus
    source = InMemoryReplaySource([make_tick(10, 100.0)], [])
    controller = ReplayController(session, source, bus)

    await controller.start()
    await controller.seek(datetime(2025, 12, 31, 23, 59, 0))

    assert session.current_time == session.start_time
    assert any(isinstance(event, ReplaySeeked) for event in events)
