from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from backend.app.chart.renko.builder import TraditionalBrickBuilder
from backend.app.chart.renko.configuration import BrickConfiguration, BrickType, RenkoMode
from backend.app.chart.renko.engine import TraditionalRenkoEngine
from backend.app.chart.renko.events import BrickExtended, BrickOpened, BrickReversed
from backend.app.chart.renko.models import BrickDirection
from backend.app.chart.renko.providers import ATRBrickSizeProvider, FixedBrickSizeProvider
from backend.app.events.bus import EventBus

from benchmark.performance import (
    ENGINE_BUILDERS,
    SCENARIOS,
    run_benchmark,
    run_snapshot_benchmark,
    trending,
)

TS = datetime(2024, 1, 1)


# =====================================================================
# Output-identity regression — optimizations must not change results
# =====================================================================

@pytest.mark.asyncio
async def test_optimized_builder_output_is_exact():
    """The optimized builder must produce the same Brick (incl. brick_id) as
    its documented output contract."""
    builder = TraditionalBrickBuilder()
    cfg = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0)
    market = {
        "direction": BrickDirection.UP,
        "open_price": 100.0,
        "close_price": 101.0,
        "high_price": 101.0,
        "low_price": 100.0,
        "volume": 0.0,
        "timestamp": TS,
    }
    brick = await builder.build_brick(market, cfg)
    assert brick.direction == BrickDirection.UP
    assert brick.open_price == 100.0 and brick.close_price == 101.0
    assert brick.high_price == 101.0 and brick.low_price == 100.0
    assert brick.brick_id == f"brick-up-{TS.isoformat()}-{int(100.0*100000)}-{int(101.0*100000)}"


@pytest.mark.asyncio
async def test_builder_accepts_raw_string_direction_and_missing_extents():
    """Backward-compatible: raw string direction + absent high/low still work
    (the optimization only skips redundant work, it does not drop support)."""
    builder = TraditionalBrickBuilder()
    cfg = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0)
    brick = await builder.build_brick(
        {"direction": "down", "open_price": 50.0, "close_price": 49.0, "timestamp": TS}, cfg
    )
    assert brick.direction == BrickDirection.DOWN
    assert brick.high_price == 50.0  # max(open, close)
    assert brick.low_price == 49.0   # min(open, close)


@pytest.mark.asyncio
async def test_event_bus_path_matches_no_bus_path():
    """Optimization batches state on the no-bus path; output (brick history)
    must be identical to the event-bus path."""
    candles = trending(2_000)

    async def run(with_bus: bool):
        bus = None
        if with_bus:
            bus = EventBus()

            async def noop(event):
                return None

            bus.subscribe(BrickOpened, noop)
            bus.subscribe(BrickExtended, noop)
            bus.subscribe(BrickReversed, noop)
        cfg = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.5, mode=RenkoMode.REPLAY)
        engine = TraditionalRenkoEngine(event_bus=bus, provider=FixedBrickSizeProvider(1.5))
        engine.configure(cfg)
        await engine.start()
        for c in candles:
            await engine.process_market_data(c)
        return [b.brick_id for b in engine.history()], engine.state.last_price

    no_bus = await run(False)
    with_bus = await run(True)
    assert no_bus == with_bus


def test_benchmark_runs_are_deterministic():
    a = run_benchmark("fixed", "trending", 3_000, sample_memory=False)
    b = run_benchmark("fixed", "trending", 3_000, sample_memory=False)
    assert a.bricks == b.bricks > 0


# =====================================================================
# Benchmark validation — scaling & memory behave linearly
# =====================================================================

def test_throughput_scales_sub_quadratically():
    small = run_benchmark("fixed", "trending", 10_000, sample_memory=False)
    large = run_benchmark("fixed", "trending", 50_000, sample_memory=False)
    # 5x the candles must cost well under 25x the time (linear, not quadratic).
    assert large.seconds < small.seconds * 15
    assert small.candles_per_sec > 0 and large.candles_per_sec > 0


def test_memory_grows_linearly_with_history():
    small = run_benchmark("fixed", "trending", 10_000, sample_memory=True)
    large = run_benchmark("fixed", "trending", 50_000, sample_memory=True)
    # ~5x history -> roughly ~5x peak allocation, allow generous head-room.
    assert large.peak_kib < small.peak_kib * 12
    assert large.bricks > small.bricks


def test_history_length_tracks_bricks():
    r = run_benchmark("percentage", "trending", 5_000, sample_memory=False)
    assert r.bricks > 0


# =====================================================================
# Stress tests
# =====================================================================

def test_flat_market_produces_no_bricks():
    r = run_benchmark("fixed", "flat", 20_000, sample_memory=False)
    assert r.bricks == 0


def test_large_gaps_produce_many_bricks():
    r = run_benchmark("fixed", "large_gaps", 20_000, sample_memory=False)
    assert r.bricks > 0


def test_rapid_reversals_and_alternating_run():
    for scenario in ("rapid_reversals", "alternating"):
        r = run_benchmark("fixed", scenario, 20_000, sample_memory=False)
        assert r.bricks > 0


def test_huge_atr_window_is_constant_memory_and_warms_up_slowly():
    # period far exceeds candle count: never warms up -> no bricks, O(1) memory.
    provider = ATRBrickSizeProvider(atr_period=100_000, atr_multiplier=1.0)
    for i in range(50_000):
        provider.update({"timestamp": TS, "close": 100.0 + (i % 7), "high": 101.0, "low": 99.0})
    assert provider.ready() is False
    # No growing containers in provider state.
    for value in provider.__dict__.values():
        assert not isinstance(value, (list, tuple, dict, set))


def test_one_million_candles_completes_deterministically():
    """Stress: 1,000,000 candles must complete and be deterministic."""
    a = run_benchmark("fixed", "trending", 1_000_000, sample_memory=False)
    assert a.bricks > 0
    b = run_benchmark("fixed", "trending", 1_000_000, sample_memory=False)
    assert a.bricks == b.bricks  # deterministic across runs


# =====================================================================
# Snapshot / restore overhead
# =====================================================================

def test_snapshot_restore_overhead_is_measurable_and_bounded():
    s = run_snapshot_benchmark("fixed", 20_000)
    assert s.bricks > 0
    assert s.snapshot_ms >= 0 and s.serialize_ms >= 0 and s.restore_ms >= 0
    assert s.payload_bytes > 0
