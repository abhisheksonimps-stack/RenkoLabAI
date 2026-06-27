from __future__ import annotations

from datetime import datetime

import pytest

from backend.app.chart.renko.configuration import BrickConfiguration, BrickType, PriceSource, RenkoMode
from backend.app.chart.renko.engine import TraditionalRenkoEngine
from backend.app.chart.renko.events import BrickOpened, BrickExtended, BrickReversed
from backend.app.chart.renko.models import BrickDirection
from backend.app.events.bus import EventBus


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def engine(event_bus: EventBus) -> TraditionalRenkoEngine:
    engine = TraditionalRenkoEngine(event_bus=event_bus)
    configuration = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0, price_source=PriceSource.CLOSE, mode=RenkoMode.REPLAY)
    engine.configure(configuration)
    return engine


@pytest.mark.asyncio
async def test_first_brick_is_initialized_without_emitting(event_bus: EventBus) -> None:
    events = []

    async def handler(event):
        events.append(event)

    event_bus.subscribe(BrickOpened, handler)
    engine = TraditionalRenkoEngine(event_bus=event_bus)
    configuration = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0)
    engine.configure(configuration)
    await engine.start()

    await engine.process_market_data({"timestamp": datetime.utcnow(), "close": 100.0})

    assert engine.history() == ()
    assert len(events) == 0


@pytest.mark.asyncio
async def test_no_movement_generates_no_bricks(engine: TraditionalRenkoEngine) -> None:
    timestamp = datetime.utcnow()
    await engine.start()
    await engine.process_market_data({"timestamp": timestamp, "close": 100.0})
    await engine.process_market_data({"timestamp": timestamp, "close": 100.5})

    assert engine.history() == ()


@pytest.mark.asyncio
async def test_continuation_creates_single_brick(engine: TraditionalRenkoEngine) -> None:
    timestamp = datetime.utcnow()
    await engine.start()
    await engine.process_market_data({"timestamp": timestamp, "close": 100.0})
    await engine.process_market_data({"timestamp": timestamp, "close": 101.0})

    history = engine.history()
    assert len(history) == 1
    assert history[0].direction == BrickDirection.UP
    assert history[0].open_price == 100.0
    assert history[0].close_price == 101.0


@pytest.mark.asyncio
async def test_reversal_creates_two_bricks(engine: TraditionalRenkoEngine) -> None:
    timestamp = datetime.utcnow()
    await engine.start()
    await engine.process_market_data({"timestamp": timestamp, "close": 100.0})
    await engine.process_market_data({"timestamp": timestamp, "close": 98.0})

    history = engine.history()
    assert len(history) == 2
    assert history[0].direction == BrickDirection.DOWN
    assert history[1].direction == BrickDirection.DOWN
    assert history[0].open_price == 100.0
    assert history[0].close_price == 99.0
    assert history[1].open_price == 99.0
    assert history[1].close_price == 98.0


@pytest.mark.asyncio
async def test_multiple_bricks_generated_from_large_candle(engine: TraditionalRenkoEngine) -> None:
    timestamp = datetime.utcnow()
    await engine.start()
    await engine.process_market_data({"timestamp": timestamp, "close": 100.0})
    await engine.process_market_data({"timestamp": timestamp, "close": 104.0})

    history = engine.history()
    assert len(history) == 4
    assert all(brick.direction == BrickDirection.UP for brick in history)
    assert history[0].open_price == 100.0
    assert history[-1].close_price == 104.0


@pytest.mark.asyncio
async def test_exact_brick_boundary_creates_brick(engine: TraditionalRenkoEngine) -> None:
    timestamp = datetime.utcnow()
    await engine.start()
    await engine.process_market_data({"timestamp": timestamp, "close": 100.0})
    await engine.process_market_data({"timestamp": timestamp, "close": 101.0})

    history = engine.history()
    assert len(history) == 1
    assert history[0].open_price == 100.0
    assert history[0].close_price == 101.0


@pytest.mark.asyncio
async def test_history_ordering_is_preserved(engine: TraditionalRenkoEngine) -> None:
    timestamp = datetime.utcnow()
    await engine.start()
    await engine.process_market_data({"timestamp": timestamp, "close": 100.0})
    await engine.process_market_data({"timestamp": timestamp, "close": 103.0})

    history = engine.history()
    assert [brick.open_price for brick in history] == [100.0, 101.0, 102.0]
    assert [brick.close_price for brick in history] == [101.0, 102.0, 103.0]


@pytest.mark.asyncio
async def test_event_publication_for_each_brick(engine: TraditionalRenkoEngine) -> None:
    events = []

    async def handler(event):
        events.append(event)

    engine._event_bus.subscribe(BrickOpened, handler)
    engine._event_bus.subscribe(BrickExtended, handler)
    engine._event_bus.subscribe(BrickReversed, handler)

    timestamp = datetime.utcnow()
    await engine.start()
    await engine.process_market_data({"timestamp": timestamp, "close": 100.0})
    await engine.process_market_data({"timestamp": timestamp, "close": 104.0})

    assert any(isinstance(event, BrickOpened) for event in events)
    assert any(isinstance(event, BrickExtended) for event in events)


@pytest.mark.asyncio
async def test_replay_determinism(engine: TraditionalRenkoEngine) -> None:
    timestamp = datetime.utcnow()
    await engine.start()
    await engine.process_market_data({"timestamp": timestamp, "close": 100.0})
    await engine.process_market_data({"timestamp": timestamp, "close": 104.0})

    first_run_ids = [brick.brick_id for brick in engine.history()]

    second_engine = TraditionalRenkoEngine(event_bus=engine._event_bus)
    configuration = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0, price_source=PriceSource.CLOSE, mode=RenkoMode.REPLAY)
    second_engine.configure(configuration)
    await second_engine.start()
    await second_engine.process_market_data({"timestamp": timestamp, "close": 100.0})
    await second_engine.process_market_data({"timestamp": timestamp, "close": 104.0})

    second_run_ids = [brick.brick_id for brick in second_engine.history()]
    assert first_run_ids == second_run_ids


@pytest.mark.asyncio
async def test_large_gap_creates_multiple_bricks(event_bus: EventBus) -> None:
    engine = TraditionalRenkoEngine(event_bus=event_bus)
    configuration = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0, price_source=PriceSource.CLOSE, mode=RenkoMode.REPLAY)
    engine.configure(configuration)
    
    timestamp = datetime.utcnow()
    await engine.start()
    await engine.process_market_data({"timestamp": timestamp, "close": 100.0})
    await engine.process_market_data({"timestamp": timestamp, "close": 110.0})

    history = engine.history()
    assert len(history) == 10
    assert all(brick.direction == BrickDirection.UP for brick in history)
    assert history[0].open_price == 100.0
    assert history[-1].close_price == 110.0


@pytest.mark.asyncio
async def test_large_reversal_with_multiple_bricks(event_bus: EventBus) -> None:
    engine = TraditionalRenkoEngine(event_bus=event_bus)
    configuration = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0, price_source=PriceSource.CLOSE, mode=RenkoMode.REPLAY)
    engine.configure(configuration)
    
    timestamp = datetime.utcnow()
    await engine.start()
    await engine.process_market_data({"timestamp": timestamp, "close": 100.0})
    await engine.process_market_data({"timestamp": timestamp, "close": 93.0})

    history = engine.history()
    assert len(history) == 7
    assert all(brick.direction == BrickDirection.DOWN for brick in history)
    assert history[0].open_price == 100.0
    assert history[-1].close_price == 93.0


@pytest.mark.asyncio
async def test_partial_movement_does_not_create_brick(event_bus: EventBus) -> None:
    engine = TraditionalRenkoEngine(event_bus=event_bus)
    configuration = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0, price_source=PriceSource.CLOSE, mode=RenkoMode.REPLAY)
    engine.configure(configuration)
    
    timestamp = datetime.utcnow()
    await engine.start()
    await engine.process_market_data({"timestamp": timestamp, "close": 100.0})
    await engine.process_market_data({"timestamp": timestamp, "close": 100.99})

    assert engine.history() == ()


@pytest.mark.asyncio
async def test_reset_clears_history(engine: TraditionalRenkoEngine) -> None:
    timestamp = datetime.utcnow()
    await engine.start()
    await engine.process_market_data({"timestamp": timestamp, "close": 100.0})
    await engine.process_market_data({"timestamp": timestamp, "close": 101.0})

    assert len(engine.history()) > 0
    await engine.reset()
    assert engine.history() == ()


@pytest.mark.asyncio
async def test_state_transition_preserves_direction(event_bus: EventBus) -> None:
    engine = TraditionalRenkoEngine(event_bus=event_bus)
    configuration = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0, price_source=PriceSource.CLOSE, mode=RenkoMode.REPLAY)
    engine.configure(configuration)
    
    timestamp = datetime.utcnow()
    await engine.start()
    await engine.process_market_data({"timestamp": timestamp, "close": 100.0})
    await engine.process_market_data({"timestamp": timestamp, "close": 102.0})
    
    state_after_up = engine.state
    assert state_after_up.direction == BrickDirection.UP
    
    await engine.process_market_data({"timestamp": timestamp, "close": 103.0})
    state_after_continuation = engine.state
    assert state_after_continuation.direction == BrickDirection.UP


@pytest.mark.asyncio
async def test_gap_fill_scenario(event_bus: EventBus) -> None:
    """Test scenario: up 2, down 4 (creates 4 DOWN bricks due to full reversal)"""
    engine = TraditionalRenkoEngine(event_bus=event_bus)
    configuration = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0, price_source=PriceSource.CLOSE, mode=RenkoMode.REPLAY)
    engine.configure(configuration)
    
    timestamp = datetime.utcnow()
    await engine.start()
    
    await engine.process_market_data({"timestamp": timestamp, "close": 100.0})  # Anchor
    await engine.process_market_data({"timestamp": timestamp, "close": 102.0})  # Up 2 -> 2 UP bricks
    
    history_after_up = engine.history()
    assert len(history_after_up) == 2
    assert all(b.direction == BrickDirection.UP for b in history_after_up)
    
    await engine.process_market_data({"timestamp": timestamp, "close": 98.0})  # Down 4 -> 4 DOWN bricks (full reversal)
    
    history_after_down = engine.history()
    assert len(history_after_down) == 6  # 2 UP + 4 DOWN
    assert history_after_down[2].direction == BrickDirection.DOWN
    assert history_after_down[3].direction == BrickDirection.DOWN
    assert history_after_down[4].direction == BrickDirection.DOWN
    assert history_after_down[5].direction == BrickDirection.DOWN


@pytest.mark.asyncio
async def test_different_price_sources(event_bus: EventBus) -> None:
    """Test that different price sources work correctly"""
    engine = TraditionalRenkoEngine(event_bus=event_bus)
    configuration = BrickConfiguration(
        brick_type=BrickType.TRADITIONAL,
        brick_size=1.0,
        price_source=PriceSource.HIGH,
        mode=RenkoMode.REPLAY
    )
    engine.configure(configuration)
    
    timestamp = datetime.utcnow()
    await engine.start()
    
    # Using HIGH price source
    await engine.process_market_data({"timestamp": timestamp, "open": 100.0, "high": 100.0, "low": 99.0, "close": 99.5})
    await engine.process_market_data({"timestamp": timestamp, "open": 99.5, "high": 101.0, "low": 99.0, "close": 100.5})
    
    history = engine.history()
    assert len(history) >= 1
    assert history[0].open_price == 100.0


@pytest.mark.asyncio
async def test_immutable_history(event_bus: EventBus) -> None:
    """Test that returned history is immutable"""
    engine = TraditionalRenkoEngine(event_bus=event_bus)
    configuration = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0, price_source=PriceSource.CLOSE, mode=RenkoMode.REPLAY)
    engine.configure(configuration)
    
    timestamp = datetime.utcnow()
    await engine.start()
    await engine.process_market_data({"timestamp": timestamp, "close": 100.0})
    await engine.process_market_data({"timestamp": timestamp, "close": 102.0})
    
    history1 = engine.history()
    history2 = engine.history()
    
    # Should be tuples (immutable)
    assert isinstance(history1, tuple)
    assert isinstance(history2, tuple)
    assert history1 == history2


@pytest.mark.asyncio
async def test_successive_reversals(event_bus: EventBus) -> None:
    """Test multiple reversals in sequence"""
    engine = TraditionalRenkoEngine(event_bus=event_bus)
    configuration = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0, price_source=PriceSource.CLOSE, mode=RenkoMode.REPLAY)
    engine.configure(configuration)
    
    timestamp = datetime.utcnow()
    await engine.start()
    
    await engine.process_market_data({"timestamp": timestamp, "close": 100.0})  # Anchor
    await engine.process_market_data({"timestamp": timestamp, "close": 103.0})  # Up 3
    
    history1 = engine.history()
    assert len(history1) == 3
    assert all(b.direction == BrickDirection.UP for b in history1)
    
    await engine.process_market_data({"timestamp": timestamp, "close": 99.0})  # Down 4 -> reversal + 1
    
    history2 = engine.history()
    # Should have 3 UP + 2 DOWN (reversal) + potentially more
    assert len(history2) >= 5
    down_bricks = [b for b in history2[3:] if b.direction == BrickDirection.DOWN]
    assert len(down_bricks) >= 2
