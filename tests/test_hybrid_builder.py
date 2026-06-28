from __future__ import annotations

import pathlib
import tempfile
from datetime import datetime, timedelta

import pytest

from backend.app.chart.renko.builder import (
    BrickBuilderRegistry,
    HybridBrickBuilder,
    TraditionalBrickBuilder,
    default_builder_registry,
)
from backend.app.chart.renko.configuration import BrickConfiguration, BrickType, RenkoMode
from backend.app.chart.renko.engine import TraditionalRenkoEngine
from backend.app.chart.renko.exceptions import RenkoConfigurationError
from backend.app.chart.renko.factory import RenkoFactory
from backend.app.chart.renko.interfaces import BrickBuilder
from backend.app.chart.renko.models import BrickDirection
from backend.app.chart.renko.providers import FixedBrickSizeProvider, default_provider_registry
from backend.app.chart.renko.snapshot import JsonSnapshotSerializer, SnapshotManager
from backend.app.chart.renko.strategies import default_strategy_registry
from backend.app.chart.renko.validator import DefaultBrickValidator
from backend.app.infrastructure.di import configure_container
from backend.app.plugins.manager import PluginManager

TS = datetime(2024, 1, 1)


def hybrid_config(**kw):
    base = dict(
        brick_type=BrickType.TRADITIONAL, brick_size=1.0, builder_type="hybrid", mode=RenkoMode.REPLAY
    )
    base.update(kw)
    return BrickConfiguration(**base)


def climb(n, start=100.0, step=2.0):
    out = []
    p = start
    for i in range(n):
        p += step
        out.append({"timestamp": TS + timedelta(minutes=i), "close": p, "high": p + 0.5, "low": p - 0.5, "open": p})
    return out


def hybrid_engine():
    cfg = hybrid_config()
    engine = TraditionalRenkoEngine(provider=FixedBrickSizeProvider(1.0), builder=HybridBrickBuilder())
    engine.configure(cfg)
    return engine, cfg


# ---------------------------------------------------------------------------
# Abstraction / construction
# ---------------------------------------------------------------------------

def test_hybrid_builder_implements_interface():
    assert issubclass(HybridBrickBuilder, BrickBuilder)
    assert isinstance(HybridBrickBuilder(), BrickBuilder)
    assert HybridBrickBuilder().name == "hybrid"


@pytest.mark.asyncio
async def test_hybrid_construction_tags_and_sequences_bricks():
    engine, _ = hybrid_engine()
    await engine.start()
    for c in climb(6):
        await engine.process_market_data(c)
    history = engine.history()
    assert len(history) > 0
    assert all(b.direction == BrickDirection.UP for b in history)
    # Hybrid markers and a monotonic sequence.
    for i, b in enumerate(history, start=1):
        assert b.metadata["builder_type"] == "hybrid"
        assert b.metadata["hybrid_sequence"] == i
        assert b.brick_id.startswith(f"hybrid-{i}-")


@pytest.mark.asyncio
async def test_hybrid_reuses_traditional_geometry():
    """Hybrid must not change brick geometry (it composes the Traditional builder)."""
    cfg = hybrid_config()
    md = {
        "direction": BrickDirection.UP, "open_price": 100.0, "close_price": 101.0,
        "high_price": 101.0, "low_price": 100.0, "volume": 0.0, "timestamp": TS,
    }
    hybrid = await HybridBrickBuilder().build_brick(md, cfg)
    base = await TraditionalBrickBuilder().build_brick(md, cfg)
    assert (hybrid.open_price, hybrid.close_price, hybrid.high_price, hybrid.low_price) == (
        base.open_price, base.close_price, base.high_price, base.low_price
    )
    assert hybrid.brick_id != base.brick_id  # distinct identity
    assert base.brick_id in hybrid.brick_id  # but derived from it


# ---------------------------------------------------------------------------
# Builder selection / configuration validation
# ---------------------------------------------------------------------------

def test_builder_type_selection():
    assert hybrid_config().resolved_builder() == "hybrid"
    assert BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0).resolved_builder() == "traditional"
    # builder_type wins over the legacy builder field.
    assert BrickConfiguration(
        brick_type=BrickType.TRADITIONAL, brick_size=1.0, builder="traditional", builder_type="hybrid"
    ).resolved_builder() == "hybrid"


def test_default_registry_has_traditional_and_hybrid():
    reg = default_builder_registry()
    assert set(reg.names()) == {"traditional", "hybrid"}
    assert isinstance(reg.create(hybrid_config()), HybridBrickBuilder)


@pytest.mark.asyncio
async def test_validation_accepts_hybrid():
    validator = DefaultBrickValidator(
        provider_registry=default_provider_registry(),
        strategy_registry=default_strategy_registry(),
        builder_registry=default_builder_registry(),
    )
    assert await validator.validate_configuration(hybrid_config())


@pytest.mark.asyncio
async def test_validation_rejects_unknown_builder():
    validator = DefaultBrickValidator(
        provider_registry=default_provider_registry(),
        strategy_registry=default_strategy_registry(),
        builder_registry=default_builder_registry(),
    )
    with pytest.raises(RenkoConfigurationError):
        await validator.validate_configuration(hybrid_config(builder_type="does_not_exist"))


# ---------------------------------------------------------------------------
# Factory resolution / DI registration
# ---------------------------------------------------------------------------

def test_factory_resolves_hybrid_builder_dynamically():
    from backend.app.chart.renko.registry import RenkoRegistry

    registry = RenkoRegistry()
    registry.register("traditional", TraditionalRenkoEngine())
    factory = RenkoFactory(
        registry,
        provider_registry=default_provider_registry(),
        strategy_registry=default_strategy_registry(),
        builder_registry=default_builder_registry(),
    )
    engine = factory.create(hybrid_config())
    assert isinstance(engine.builder, HybridBrickBuilder)
    # Traditional remains the default when nothing is specified.
    engine2 = factory.create(BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0))
    assert isinstance(engine2.builder, TraditionalBrickBuilder)


def test_di_registers_hybrid_builder():
    container = configure_container()
    assert set(container.brick_builder_registry().names()) == {"traditional", "hybrid"}


# ---------------------------------------------------------------------------
# Plugin registration (additional builders, same mechanism)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_plugin_registers_additional_builder():
    plugin_code = '''
from backend.app.chart.renko.builder import BrickBuilderRegistry, HybridBrickBuilder

class ExperimentalBuilder(HybridBrickBuilder):
    name = "experimental"

class MyPlugin:
    name = "experimental_builder_plugin"
    async def load(self, event_bus=None): pass
    async def start(self): pass
    async def stop(self): pass
    async def unload(self): pass
    async def register_brick_builders(self, registry: BrickBuilderRegistry):
        registry.register("experimental", lambda cfg: ExperimentalBuilder())
'''
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "experimental_builder_plugin.py").write_text(plugin_code, encoding="utf-8")
    builder_registry = default_builder_registry()
    manager = PluginManager(d, builder_registry=builder_registry)
    await manager.load()
    assert manager.get_plugin("experimental_builder_plugin").name == "experimental_builder_plugin"
    assert builder_registry.exists("experimental")
    await manager.unload()


# ---------------------------------------------------------------------------
# Snapshot compatibility (state snapshot / restore / resume)
# ---------------------------------------------------------------------------

def _manager():
    return SnapshotManager(
        JsonSnapshotSerializer(),
        default_provider_registry(),
        default_strategy_registry(),
        default_builder_registry(),
    )


def test_hybrid_builder_exports_and_imports_state():
    b = HybridBrickBuilder()
    assert b.export_state() == {"sequence": 0}
    b._sequence = 7
    state = b.export_state()
    restored = HybridBrickBuilder()
    restored.import_state(state)
    assert restored.export_state() == {"sequence": 7}


@pytest.mark.asyncio
async def test_hybrid_snapshot_restore_resume_is_deterministic():
    candles = climb(20)

    async def continuous():
        engine, _ = hybrid_engine()
        await engine.start()
        for c in candles:
            await engine.process_market_data(c)
        return [b.brick_id for b in engine.history()], engine.builder.export_state()

    async def split():
        engine, _ = hybrid_engine()
        await engine.start()
        for c in candles[:10]:
            await engine.process_market_data(c)
        restored = _manager().restore(engine.save_state())
        for c in candles[10:]:
            await restored.process_market_data(c)
        return [b.brick_id for b in restored.history()], restored.builder.export_state()

    cont_ids, cont_state = await continuous()
    split_ids, split_state = await split()
    assert len(cont_ids) > 0
    assert cont_ids == split_ids                 # identical hybrid brick IDs
    assert cont_state == split_state             # builder sequence resumed exactly
    assert isinstance(_manager(), SnapshotManager)


# ---------------------------------------------------------------------------
# Performance / benchmark compatibility + no Traditional regression
# ---------------------------------------------------------------------------

def test_hybrid_benchmark_runs_and_traditional_unaffected():
    from backend.app.chart.renko.performance import run_benchmark

    hybrid = run_benchmark("hybrid", "trending", 5_000, sample_memory=False)
    traditional = run_benchmark("fixed", "trending", 5_000, sample_memory=False)
    assert hybrid.bricks > 0
    assert traditional.bricks > 0
    # Traditional output is unchanged regardless of Hybrid being present.
    again = run_benchmark("fixed", "trending", 5_000, sample_memory=False)
    assert traditional.bricks == again.bricks


@pytest.mark.asyncio
async def test_traditional_builder_output_unchanged_by_hybrid_addition():
    cfg = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0)
    md = {
        "direction": BrickDirection.UP, "open_price": 100.0, "close_price": 101.0,
        "high_price": 101.0, "low_price": 100.0, "volume": 0.0, "timestamp": TS,
    }
    brick = await TraditionalBrickBuilder().build_brick(md, cfg)
    assert brick.brick_id == f"brick-up-{TS.isoformat()}-{int(100.0*100000)}-{int(101.0*100000)}"
    assert "builder_type" not in brick.metadata  # Traditional carries no hybrid marker
