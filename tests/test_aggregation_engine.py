from datetime import datetime, timedelta, time

import pytest

from backend.app.domain.market_data import Candle, Tick, Timeframe, TradingSession
from backend.app.engines.aggregation import AggregationEngine, CandleClosed, CandleOpened, CandleUpdated
from backend.app.events.bus import EventBus


@pytest.fixture
def event_bus():
    bus = EventBus()
    events = []

    async def handler(event):
        events.append(event)

    bus.subscribe(CandleOpened, handler)
    bus.subscribe(CandleUpdated, handler)
    bus.subscribe(CandleClosed, handler)
    return bus, events


@pytest.mark.asyncio
async def test_single_candle_creation(event_bus):
    bus, events = event_bus
    engine = AggregationEngine(bus, Timeframe.ONE_MINUTE)

    tick = Tick(
        symbol="BTCUSDT",
        exchange="BINANCE",
        timestamp=datetime(2026, 1, 1, 10, 0, 10),
        price=100.0,
        size=1.0,
    )

    await engine.process_tick(tick)
    await engine.close_pending_candles(datetime(2026, 1, 1, 10, 1, 0))

    assert len(events) == 2
    assert isinstance(events[0], CandleOpened)
    assert isinstance(events[1], CandleClosed)
    assert events[1].payload["candle"]["open"] == 100.0
    assert events[1].payload["candle"]["close"] == 100.0


@pytest.mark.asyncio
async def test_multiple_candle_generation(event_bus):
    bus, events = event_bus
    engine = AggregationEngine(bus, Timeframe.ONE_MINUTE)

    first_tick = Tick(
        symbol="BTCUSDT",
        exchange="BINANCE",
        timestamp=datetime(2026, 1, 1, 10, 0, 10),
        price=100.0,
        size=1.0,
    )
    second_tick = Tick(
        symbol="BTCUSDT",
        exchange="BINANCE",
        timestamp=datetime(2026, 1, 1, 10, 1, 5),
        price=101.0,
        size=2.0,
    )

    await engine.process_tick(first_tick)
    await engine.process_tick(second_tick)

    assert any(isinstance(event, CandleClosed) for event in events)
    assert any(isinstance(event, CandleOpened) for event in events)


@pytest.mark.asyncio
async def test_session_open_close(event_bus):
    bus, events = event_bus
    engine = AggregationEngine(bus, Timeframe.ONE_MINUTE)
    session = TradingSession(
        exchange="BINANCE",
        session_name="REGULAR",
        start_time=time(10, 0),
        end_time=time(10, 2),
        timezone="UTC",
    )

    tick = Tick(
        symbol="BTCUSDT",
        exchange="BINANCE",
        timestamp=datetime(2026, 1, 1, 10, 0, 10),
        price=100.0,
        size=1.0,
    )
    await engine.process_tick(tick, session=session)
    await engine.close_session(session, datetime(2026, 1, 1, 10, 2, 0))

    assert any(isinstance(event, CandleClosed) for event in events)


@pytest.mark.asyncio
async def test_duplicate_ticks_are_ignored(event_bus):
    bus, events = event_bus
    engine = AggregationEngine(bus, Timeframe.ONE_MINUTE)

    tick = Tick(
        symbol="BTCUSDT",
        exchange="BINANCE",
        timestamp=datetime(2026, 1, 1, 10, 0, 10),
        price=100.0,
        size=1.0,
    )

    await engine.process_tick(tick)
    await engine.process_tick(tick)
    await engine.close_pending_candles(datetime(2026, 1, 1, 10, 1, 0))

    assert len([event for event in events if isinstance(event, CandleOpened)]) == 1


@pytest.mark.asyncio
async def test_out_of_order_ticks_update_candle(event_bus):
    bus, events = event_bus
    engine = AggregationEngine(bus, Timeframe.ONE_MINUTE)

    later_tick = Tick(
        symbol="BTCUSDT",
        exchange="BINANCE",
        timestamp=datetime(2026, 1, 1, 10, 0, 50),
        price=105.0,
        size=1.0,
    )
    earlier_tick = Tick(
        symbol="BTCUSDT",
        exchange="BINANCE",
        timestamp=datetime(2026, 1, 1, 10, 0, 10),
        price=100.0,
        size=1.0,
    )

    await engine.process_tick(later_tick)
    await engine.process_tick(earlier_tick)
    await engine.close_pending_candles(datetime(2026, 1, 1, 10, 1, 0))

    closed = [event for event in events if isinstance(event, CandleClosed)][0]
    assert closed.payload["candle"]["open"] == 105.0
    assert closed.payload["candle"]["close"] == 105.0
    assert closed.payload["candle"]["low"] == 100.0


@pytest.mark.asyncio
async def test_missing_ticks_result_in_no_empty_candle(event_bus):
    bus, events = event_bus
    engine = AggregationEngine(bus, Timeframe.ONE_MINUTE)

    first_tick = Tick(
        symbol="BTCUSDT",
        exchange="BINANCE",
        timestamp=datetime(2026, 1, 1, 10, 0, 10),
        price=100.0,
        size=1.0,
    )
    third_tick = Tick(
        symbol="BTCUSDT",
        exchange="BINANCE",
        timestamp=datetime(2026, 1, 1, 10, 2, 10),
        price=102.0,
        size=1.0,
    )

    await engine.process_tick(first_tick)
    await engine.process_tick(third_tick)

    closed = [event for event in events if isinstance(event, CandleClosed)]
    assert len(closed) == 1


@pytest.mark.asyncio
async def test_boundary_timestamps_create_separate_candles(event_bus):
    bus, events = event_bus
    engine = AggregationEngine(bus, Timeframe.ONE_MINUTE)

    tick1 = Tick(
        symbol="BTCUSDT",
        exchange="BINANCE",
        timestamp=datetime(2026, 1, 1, 10, 0, 0),
        price=100.0,
        size=1.0,
    )
    tick2 = Tick(
        symbol="BTCUSDT",
        exchange="BINANCE",
        timestamp=datetime(2026, 1, 1, 10, 1, 0),
        price=101.0,
        size=1.0,
    )

    await engine.process_tick(tick1)
    await engine.process_tick(tick2)
    await engine.close_pending_candles(datetime(2026, 1, 1, 10, 2, 0))

    assert len([event for event in events if isinstance(event, CandleClosed)]) == 2
