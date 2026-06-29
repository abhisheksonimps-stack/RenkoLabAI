from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import List, Tuple

import pytest

from backend.app.domain.market_data.enums import Timeframe
from backend.app.domain.market_data.models import Candle, Tick
from backend.app.engines.replay.events import CandleReplayed, TickReplayed
from backend.app.events.base import BaseEvent
from backend.app.events.bus import EventBus
from backend.app.trading.execution.order import OrderSide
from backend.app.trading.paper.events import (
    OrderAccepted,
    OrderCancelled,
    OrderFilled,
    OrderTriggered,
)
from backend.app.trading.paper.replay_feed import ReplayMarketFeed
from backend.app.trading.paper.session import (
    PaperSessionManager,
    PaperTradingSession,
    SessionState,
)
from backend.app.trading.portfolio.portfolio import Portfolio

T0 = datetime(2024, 1, 1, 9, 30, 0)


def make_session(capital=100_000.0, symbol="X") -> Tuple[PaperTradingSession, EventBus, list]:
    bus = EventBus()
    session = PaperTradingSession(symbol, Portfolio(capital), bus)
    received: List[Tuple[str, dict]] = []

    async def record(event: BaseEvent) -> None:
        received.append((type(event).__name__, event.payload))

    for event_type in (OrderAccepted, OrderTriggered, OrderFilled, OrderCancelled):
        bus.subscribe(event_type, record)
    return session, bus, received


def candle(close, *, t=T0, high=None, low=None, symbol="X"):
    high = high if high is not None else max(close, close)
    low = low if low is not None else min(close, close)
    return Candle(symbol=symbol, exchange="SIM", timeframe=Timeframe.ONE_MINUTE,
                  start_time=t, open=close, high=max(high, close), low=min(low, close),
                  close=close, volume=1.0, trades=1)


def tick(price, *, t=T0, symbol="X"):
    return Tick(symbol=symbol, exchange="SIM", timestamp=t, price=price)


def test_session_market_buy_publishes_accepted_then_filled():
    session, _, received = make_session()

    async def run():
        session.start()
        await session.submit_market(OrderSide.BUY, 10.0)
        await session.on_tick(tick(100.0))

    asyncio.run(run())

    names = [name for name, _ in received]
    assert names == ["OrderAccepted", "OrderFilled"]
    assert session.portfolio.position.is_open
    assert session.portfolio.position.quantity == 10.0


def test_session_limit_lifecycle_emits_triggered_and_filled():
    session, _, received = make_session()

    async def run():
        await session.submit_limit(OrderSide.BUY, 10.0, limit_price=95.0)
        await session.on_candle(candle(96.0, low=96.0, high=96.0))            # no trigger
        await session.on_candle(candle(96.0, t=T0 + timedelta(minutes=1), low=94.0, high=97.0))

    asyncio.run(run())

    names = [name for name, _ in received]
    assert names[0] == "OrderAccepted"
    assert "OrderTriggered" in names
    assert names[-1] == "OrderFilled"
    assert session.portfolio.position.average_entry_price == pytest.approx(95.0)


def test_session_cancel_emits_cancelled_event():
    session, _, received = make_session()

    async def run():
        order = await session.submit_limit(OrderSide.BUY, 10.0, limit_price=95.0)
        ok = await session.cancel(order.order_id)
        assert ok is True

    asyncio.run(run())
    assert ("OrderCancelled", received[-1][1]) == received[-1]
    assert received[-1][0] == "OrderCancelled"
    assert session.portfolio.reserved == pytest.approx(0.0)


def test_replay_feed_drives_session_from_candle_events():
    bus = EventBus()
    session = PaperTradingSession("X", Portfolio(100_000.0), bus)
    feed = ReplayMarketFeed(session, bus)
    feed.attach()

    async def run():
        await session.submit_market(OrderSide.BUY, 10.0)
        # Emulate the replay engine publishing a replayed candle on the bus.
        bus.register_event(CandleReplayed)
        c = candle(100.0)
        await bus.publish(CandleReplayed(name="CandleReplayed",
                                         occurred_at=datetime.utcnow(),
                                         payload={"candle": c.model_dump()}))

    asyncio.run(run())
    assert session.portfolio.position.is_open
    assert session.portfolio.position.quantity == 10.0


def test_replay_feed_ignores_other_symbols():
    bus = EventBus()
    session = PaperTradingSession("X", Portfolio(100_000.0), bus)
    ReplayMarketFeed(session, bus).attach()

    async def run():
        await session.submit_market(OrderSide.BUY, 10.0)
        bus.register_event(TickReplayed)
        other = tick(100.0, symbol="Y")
        await bus.publish(TickReplayed(name="TickReplayed",
                                       occurred_at=datetime.utcnow(),
                                       payload={"tick": other.model_dump()}))

    asyncio.run(run())
    # Order for symbol X must not fill on a Y tick; it is still queued.
    assert not session.portfolio.position.is_open
    assert len(session.simulator.open_orders) == 1


def test_session_manager_create_get_close():
    bus = EventBus()
    manager = PaperSessionManager(bus)
    session = manager.create_session("alpha", "X", Portfolio(50_000.0))
    assert isinstance(session, PaperTradingSession)
    assert manager.get("alpha") is session
    assert manager.sessions == ["alpha"]
    with pytest.raises(ValueError):
        manager.create_session("alpha", "X", Portfolio(50_000.0))
    assert manager.close("alpha") is True
    assert session.state is SessionState.STOPPED
    assert manager.close("alpha") is False
