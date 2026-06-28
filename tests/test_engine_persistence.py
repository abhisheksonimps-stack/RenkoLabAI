from __future__ import annotations

from datetime import datetime

import pytest

from backend.app.chart.renko.builder import default_builder_registry
from backend.app.chart.renko.configuration import BrickConfiguration, BrickType, RenkoMode
from backend.app.chart.renko.engine import TraditionalRenkoEngine
from backend.app.chart.renko.exceptions import (
    CorruptedSnapshotError,
    IncompatibleSnapshotError,
    SnapshotVersionError,
)
from backend.app.chart.renko.providers import (
    ATRBrickSizeProvider,
    FixedBrickSizeProvider,
    PercentageBrickSizeProvider,
    default_provider_registry,
)
from backend.app.chart.renko.snapshot import (
    SNAPSHOT_SCHEMA_VERSION,
    EngineState,
    JsonSnapshotSerializer,
    SnapshotManager,
)
from backend.app.chart.renko.strategies import default_strategy_registry
from backend.app.infrastructure.di import configure_container


TS = datetime(2024, 1, 1, 0, 0, 0)


def candle(close, high=None, low=None, open_=None):
    data = {"timestamp": TS, "close": close}
    if high is not None:
        data["high"] = high
    if low is not None:
        data["low"] = low
    if open_ is not None:
        data["open"] = open_
    return data


def manager():
    return SnapshotManager(
        JsonSnapshotSerializer(),
        default_provider_registry(),
        default_strategy_registry(),
        default_builder_registry(),
    )


def fixed_engine(size=1.0):
    cfg = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=size, mode=RenkoMode.REPLAY)
    engine = TraditionalRenkoEngine(provider=FixedBrickSizeProvider(size))
    engine.configure(cfg)
    return engine


def atr_engine(period=2, mult=0.5):
    cfg = BrickConfiguration(
        brick_type=BrickType.ATR, brick_size=1.0, atr_period=period, atr_multiplier=mult, mode=RenkoMode.REPLAY
    )
    engine = TraditionalRenkoEngine(provider=ATRBrickSizeProvider.from_configuration(cfg))
    engine.configure(cfg)
    return engine


def percentage_engine(pct=1.0):
    cfg = BrickConfiguration(
        brick_type=BrickType.PERCENTAGE, brick_size=1.0, percentage=pct, mode=RenkoMode.REPLAY
    )
    engine = TraditionalRenkoEngine(provider=PercentageBrickSizeProvider.from_configuration(cfg))
    engine.configure(cfg)
    return engine


# ---------------------------------------------------------------------------
# Snapshot creation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_snapshot_contains_all_required_fields():
    engine = fixed_engine()
    await engine.start()
    await engine.process_market_data(candle(100.0))
    await engine.process_market_data(candle(102.0))
    snap = engine.snapshot()

    assert isinstance(snap, EngineState)
    assert snap.schema_version == SNAPSHOT_SCHEMA_VERSION
    assert snap.engine_type == "traditional"
    assert snap.configuration["brick_type"] == "traditional"
    assert isinstance(snap.brick_history, list) and len(snap.brick_history) == 2
    assert isinstance(snap.provider_state, dict)
    assert isinstance(snap.strategy_state, dict)
    assert isinstance(snap.builder_state, dict)
    assert snap.metadata["brick_count"] == 2


@pytest.mark.asyncio
async def test_snapshot_requires_configured_engine():
    engine = TraditionalRenkoEngine()
    with pytest.raises(RuntimeError):
        engine.snapshot()


# ---------------------------------------------------------------------------
# Serialization / deserialization
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_serialize_deserialize_round_trip():
    engine = fixed_engine()
    await engine.start()
    for px in (100.0, 101.0, 102.0):
        await engine.process_market_data(candle(px))

    serializer = JsonSnapshotSerializer()
    blob = serializer.serialize(engine.snapshot())
    assert isinstance(blob, str)

    restored = serializer.deserialize(blob)
    assert restored.schema_version == SNAPSHOT_SCHEMA_VERSION
    assert restored.engine_type == "traditional"
    assert len(restored.brick_history) == 2


@pytest.mark.asyncio
async def test_save_state_and_load_state_helpers():
    engine = fixed_engine()
    await engine.start()
    await engine.process_market_data(candle(100.0))
    await engine.process_market_data(candle(103.0))

    blob = engine.save_state()
    state = engine.load_state(blob)
    assert isinstance(state, EngineState)
    assert len(state.brick_history) == 3


# ---------------------------------------------------------------------------
# Restore + resume == continuous (determinism)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_restore_resume_matches_continuous_fixed():
    closes = [100.0, 101.0, 102.0, 98.0, 103.0, 104.0, 100.0]

    async def continuous():
        e = fixed_engine()
        await e.start()
        for px in closes:
            await e.process_market_data(candle(px))
        return [b.brick_id for b in e.history()]

    async def split():
        e = fixed_engine()
        await e.start()
        for px in closes[:3]:
            await e.process_market_data(candle(px))
        restored = manager().restore(e.save_state())
        for px in closes[3:]:
            await restored.process_market_data(candle(px))
        return [b.brick_id for b in restored.history()]

    cont = await continuous()
    assert len(cont) > 0
    assert cont == await split()


@pytest.mark.asyncio
async def test_restore_resume_matches_continuous_percentage():
    closes = [100.0, 103.0, 250.0, 255.0, 240.0, 200.0]

    async def continuous():
        e = percentage_engine()
        await e.start()
        for px in closes:
            await e.process_market_data(candle(px))
        return [b.brick_id for b in e.history()]

    async def split():
        e = percentage_engine()
        await e.start()
        for px in closes[:3]:
            await e.process_market_data(candle(px))
        restored = manager().restore(e.save_state())
        for px in closes[3:]:
            await restored.process_market_data(candle(px))
        return [b.brick_id for b in restored.history()]

    cont = await continuous()
    assert len(cont) > 0
    assert cont == await split()


@pytest.mark.asyncio
async def test_restore_resume_matches_continuous_atr():
    # ATR with small multiplier so bricks are produced; rolling state must persist.
    seq = [
        candle(100, high=104, low=96),
        candle(101, high=105, low=97),
        candle(108, high=110, low=101),
        candle(115, high=116, low=108),
        candle(112, high=118, low=110),
        candle(120, high=121, low=111),
    ]

    async def continuous():
        e = atr_engine(period=2, mult=0.5)
        await e.start()
        for c in seq:
            await e.process_market_data(c)
        return [b.brick_id for b in e.history()]

    async def split():
        e = atr_engine(period=2, mult=0.5)
        await e.start()
        for c in seq[:3]:
            await e.process_market_data(c)
        restored = manager().restore(e.save_state())
        for c in seq[3:]:
            await restored.process_market_data(c)
        return [b.brick_id for b in restored.history()]

    cont = await continuous()
    assert len(cont) > 0
    assert cont == await split()


# ---------------------------------------------------------------------------
# Provider / builder state persistence
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_atr_provider_rolling_state_persisted():
    e = atr_engine(period=3, mult=1.0)
    await e.start()
    for c in (candle(100, high=102, low=98), candle(101, high=103, low=99), candle(102, high=104, low=100)):
        await e.process_market_data(c)

    original_atr = e.provider.atr
    assert original_atr is not None

    restored = manager().restore(e.save_state())
    assert isinstance(restored.provider, ATRBrickSizeProvider)
    assert restored.provider.atr == pytest.approx(original_atr)
    assert restored.provider.ready()
    assert restored.provider.current_size() == pytest.approx(e.provider.current_size())


@pytest.mark.asyncio
async def test_percentage_provider_state_persisted():
    e = percentage_engine(pct=1.0)
    await e.start()
    await e.process_market_data(candle(250.0))
    assert e.provider.current_size() == pytest.approx(2.5)

    restored = manager().restore(e.save_state())
    assert restored.provider.current_size() == pytest.approx(2.5)


@pytest.mark.asyncio
async def test_builder_state_persisted():
    class CountingBuilder(__import__(
        "backend.app.chart.renko.builder", fromlist=["TraditionalBrickBuilder"]
    ).TraditionalBrickBuilder):
        def __init__(self):
            self._calls = 0

        def export_state(self):
            return {"calls": self._calls}

        def import_state(self, state):
            self._calls = int(state.get("calls", 0))

        async def build_brick(self, market_data, configuration):
            self._calls += 1
            return await super().build_brick(market_data, configuration)

    cfg = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0, mode=RenkoMode.REPLAY)
    builder = CountingBuilder()
    engine = TraditionalRenkoEngine(provider=FixedBrickSizeProvider(1.0), builder=builder)
    engine.configure(cfg)
    await engine.start()
    await engine.process_market_data(candle(100.0))
    await engine.process_market_data(candle(103.0))  # 3 bricks -> 3 calls

    snap = engine.snapshot()
    assert snap.builder_state == {"calls": 3}

    target = CountingBuilder()
    target.import_state(snap.builder_state)
    assert target._calls == 3


# ---------------------------------------------------------------------------
# Strategy state persistence (stateless built-ins)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_strategy_state_is_empty_for_stateless_strategy():
    cfg = BrickConfiguration(
        brick_type=BrickType.PERCENTAGE, brick_size=1.0, percentage=1.0,
        reference_price_strategy="mean", mode=RenkoMode.REPLAY,
    )
    engine = TraditionalRenkoEngine(provider=PercentageBrickSizeProvider.from_configuration(cfg))
    engine.configure(cfg)
    await engine.start()
    await engine.process_market_data(candle(100.0, high=110.0, low=90.0, open_=100.0))
    snap = engine.snapshot()
    assert snap.strategy_state == {}
    # Restored engine still uses the mean strategy.
    restored = manager().restore(engine.save_state())
    from backend.app.chart.renko.strategies import MeanPriceStrategy
    assert isinstance(restored.provider.strategy, MeanPriceStrategy)


# ---------------------------------------------------------------------------
# Invalid / corrupted / version-mismatch snapshots
# ---------------------------------------------------------------------------

def test_corrupted_json_raises():
    with pytest.raises(CorruptedSnapshotError):
        JsonSnapshotSerializer().deserialize("{ this is not json")


def test_missing_required_field_raises():
    with pytest.raises(CorruptedSnapshotError):
        EngineState.from_dict({"schema_version": 1, "engine_type": "traditional"})


@pytest.mark.asyncio
async def test_version_mismatch_raises():
    e = fixed_engine()
    await e.start()
    await e.process_market_data(candle(100.0))
    snap = e.snapshot()
    payload = snap.to_dict()
    payload["schema_version"] = 999
    blob = JsonSnapshotSerializer().serialize(EngineState.from_dict(payload))
    with pytest.raises(SnapshotVersionError):
        manager().restore(blob)


@pytest.mark.asyncio
async def test_incompatible_engine_type_raises():
    e = fixed_engine()
    await e.start()
    await e.process_market_data(candle(100.0))
    payload = e.snapshot().to_dict()
    payload["engine_type"] = "quantum_renko"
    blob = JsonSnapshotSerializer().serialize(EngineState.from_dict(payload))
    with pytest.raises(IncompatibleSnapshotError):
        manager().restore(blob)


@pytest.mark.asyncio
async def test_incompatible_provider_raises():
    e = fixed_engine()
    await e.start()
    await e.process_market_data(candle(100.0))
    payload = e.snapshot().to_dict()
    payload["configuration"]["provider"] = "nonexistent_provider"
    blob = JsonSnapshotSerializer().serialize(EngineState.from_dict(payload))
    with pytest.raises(IncompatibleSnapshotError):
        manager().restore(blob)


# ---------------------------------------------------------------------------
# DI integration
# ---------------------------------------------------------------------------

def test_di_exposes_serializer_and_manager():
    container = configure_container()
    serializer = container.snapshot_serializer()
    snap_manager = container.snapshot_manager()
    assert serializer.format == "json"
    assert isinstance(snap_manager, SnapshotManager)


@pytest.mark.asyncio
async def test_di_manager_round_trip():
    container = configure_container()
    snap_manager = container.snapshot_manager()
    e = fixed_engine()
    await e.start()
    await e.process_market_data(candle(100.0))
    await e.process_market_data(candle(104.0))
    restored = snap_manager.restore(snap_manager.save(e))
    assert len(restored.history()) == 4


# ---------------------------------------------------------------------------
# Performance: snapshot is linear, restore does not replay
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_snapshot_scales_linearly_and_restore_has_no_replay():
    e = fixed_engine()
    await e.start()
    await e.process_market_data(candle(100.0))
    # Produce a large brick history with one big move (no per-candle loop needed).
    await e.process_market_data(candle(2100.0))  # 2000 UP bricks of size 1.0
    assert len(e.history()) == 2000

    snap = e.snapshot()
    assert len(snap.brick_history) == 2000

    # Restore reconstructs the 2000 bricks without reprocessing any candle.
    restored = manager().restore(e.save_state())
    assert len(restored.history()) == 2000
    # Resume one more candle continues from the restored boundary.
    await restored.process_market_data(candle(2101.0))
    assert len(restored.history()) == 2001


# ---------------------------------------------------------------------------
# Direct engine.restore() component-compatibility guard (Sprint 6G hardening)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_direct_restore_rejects_incompatible_provider():
    """A direct engine.restore() must reject a snapshot whose configured
    provider does not match the engine's live provider."""
    source = atr_engine(period=2, mult=0.5)
    await source.start()
    for c in [candle(100, high=104, low=96), candle(101, high=105, low=97), candle(108, high=110, low=101)]:
        await source.process_market_data(c)
    state = source.snapshot()

    target = fixed_engine()  # live provider is "fixed", snapshot expects "atr"
    with pytest.raises(IncompatibleSnapshotError):
        target.restore(state)


@pytest.mark.asyncio
async def test_direct_restore_into_matching_engine_succeeds():
    source = percentage_engine(pct=1.0)
    await source.start()
    for px in [100.0, 103.0, 250.0]:
        await source.process_market_data(candle(px))
    state = source.snapshot()

    target = percentage_engine(pct=1.0)  # matching live components
    target.restore(state)
    assert [b.brick_id for b in target.history()] == [b.brick_id for b in source.history()]
