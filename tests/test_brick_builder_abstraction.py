from __future__ import annotations

import pathlib
import tempfile
from datetime import datetime

import pytest

from backend.app.chart.renko.builder import (
    BrickBuilderRegistry,
    TraditionalBrickBuilder,
    default_builder_registry,
)
from backend.app.chart.renko.configuration import (
    BrickConfiguration,
    BrickType,
    RenkoMode,
)
from backend.app.chart.renko.engine import TraditionalRenkoEngine
from backend.app.chart.renko.factory import RenkoFactory
from backend.app.chart.renko.interfaces import BrickBuilder
from backend.app.chart.renko.models import BrickDirection
from backend.app.chart.renko.providers import FixedBrickSizeProvider, default_provider_registry
from backend.app.chart.renko.registry import RenkoRegistry
from backend.app.chart.renko.strategies import default_strategy_registry
from backend.app.infrastructure.di import configure_container
from backend.app.plugins.manager import PluginManager


TS = datetime(2024, 1, 1, 0, 0, 0)


def candle(close):
    return {"timestamp": TS, "close": close}


def trad_config(**kw):
    base = dict(brick_type=BrickType.TRADITIONAL, brick_size=1.0, mode=RenkoMode.REPLAY)
    base.update(kw)
    return BrickConfiguration(**base)


# ---------------------------------------------------------------------------
# Abstraction
# ---------------------------------------------------------------------------

def test_traditional_builder_implements_interface():
    assert issubclass(TraditionalBrickBuilder, BrickBuilder)
    assert isinstance(TraditionalBrickBuilder(), BrickBuilder)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_default_builder_registry_has_traditional():
    reg = default_builder_registry()
    assert reg.names() == ["traditional"]
    assert reg.exists("traditional")
    builder = reg.create(trad_config())
    assert isinstance(builder, BrickBuilder)
    assert isinstance(builder, TraditionalBrickBuilder)


def test_builder_registry_rejects_duplicate_and_missing():
    reg = BrickBuilderRegistry()
    reg.register("traditional", lambda cfg: TraditionalBrickBuilder())
    with pytest.raises(ValueError):
        reg.register("traditional", lambda cfg: TraditionalBrickBuilder())
    with pytest.raises(KeyError):
        reg.get("missing")


def test_config_resolves_builder_name():
    assert trad_config().resolved_builder() == "traditional"
    assert trad_config(builder="custom").resolved_builder() == "custom"


# ---------------------------------------------------------------------------
# Engine depends on the interface, not the concrete builder
# ---------------------------------------------------------------------------

def test_engine_defaults_to_traditional_builder():
    engine = TraditionalRenkoEngine()
    assert isinstance(engine.builder, TraditionalBrickBuilder)
    assert isinstance(engine.builder, BrickBuilder)


def test_engine_accepts_injected_builder_via_constructor():
    sentinel = TraditionalBrickBuilder()
    engine = TraditionalRenkoEngine(builder=sentinel)
    assert engine.builder is sentinel


def test_engine_set_brick_builder_overrides():
    engine = TraditionalRenkoEngine()
    replacement = TraditionalBrickBuilder()
    engine.set_brick_builder(replacement)
    assert engine.builder is replacement


@pytest.mark.asyncio
async def test_engine_actually_uses_injected_builder():
    """Prove the engine calls the injected interface, not a hardcoded concrete."""

    class TaggingBuilder(TraditionalBrickBuilder):
        async def build_brick(self, market_data, configuration):
            brick = await super().build_brick(market_data, configuration)
            return brick.__class__(**{**brick.__dict__, "metadata": {**brick.metadata, "tagged": True}})

    engine = TraditionalRenkoEngine(provider=FixedBrickSizeProvider(1.0), builder=TaggingBuilder())
    engine.configure(trad_config())
    await engine.start()
    await engine.process_market_data(candle(100.0))
    await engine.process_market_data(candle(101.0))
    history = engine.history()
    assert len(history) == 1
    assert history[0].metadata.get("tagged") is True


# ---------------------------------------------------------------------------
# Factory resolves builders through the abstraction
# ---------------------------------------------------------------------------

def test_factory_injects_resolved_builder():
    registry = RenkoRegistry()
    registry.register("traditional", TraditionalRenkoEngine())
    factory = RenkoFactory(
        registry,
        provider_registry=default_provider_registry(),
        strategy_registry=default_strategy_registry(),
        builder_registry=default_builder_registry(),
    )
    engine = factory.create(trad_config())
    assert isinstance(engine.builder, TraditionalBrickBuilder)


def test_factory_create_builder_helper():
    factory = RenkoFactory(RenkoRegistry(), builder_registry=default_builder_registry())
    assert isinstance(factory.create_builder(trad_config()), TraditionalBrickBuilder)


# ---------------------------------------------------------------------------
# Dependency injection
# ---------------------------------------------------------------------------

def test_di_exposes_builder_registry():
    container = configure_container()
    reg = container.brick_builder_registry()
    assert reg is not None
    assert reg.names() == ["traditional"]


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_plugin_registers_new_builder_without_engine_change():
    plugin_code = '''
from backend.app.chart.renko.builder import BrickBuilderRegistry, TraditionalBrickBuilder

class CustomBuilder(TraditionalBrickBuilder):
    pass

class MyPlugin:
    name = "custom_builder_plugin"
    async def load(self, event_bus=None): pass
    async def start(self): pass
    async def stop(self): pass
    async def unload(self): pass
    async def register_brick_builders(self, registry: BrickBuilderRegistry):
        registry.register("custom", lambda cfg: CustomBuilder())
'''
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "custom_builder_plugin.py").write_text(plugin_code, encoding="utf-8")

    builder_registry = default_builder_registry()
    manager = PluginManager(d, builder_registry=builder_registry)
    await manager.load()

    assert manager.get_plugin("custom_builder_plugin").name == "custom_builder_plugin"
    assert builder_registry.exists("custom")
    built = builder_registry.create(trad_config(builder="custom"))
    assert isinstance(built, BrickBuilder)
    await manager.unload()


# ---------------------------------------------------------------------------
# Behaviour unchanged (regression at the abstraction boundary)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_behaviour_unchanged_with_resolved_builder():
    """A factory-resolved builder yields the same bricks as the default path."""
    registry = RenkoRegistry()
    registry.register("traditional", TraditionalRenkoEngine(provider=FixedBrickSizeProvider(1.0)))
    factory = RenkoFactory(
        registry,
        provider_registry=default_provider_registry(),
        builder_registry=default_builder_registry(),
    )
    engine = factory.create(trad_config())
    engine.configure(trad_config())
    await engine.start()
    await engine.process_market_data(candle(100.0))
    await engine.process_market_data(candle(104.0))
    history = engine.history()
    assert len(history) == 4
    assert all(b.direction == BrickDirection.UP for b in history)
    assert history[0].open_price == 100.0
    assert history[-1].close_price == 104.0
