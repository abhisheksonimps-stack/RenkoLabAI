from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from backend.app.chart.renko.configuration import BrickConfiguration, BrickType, PriceSource, RenkoMode
from backend.app.chart.renko.exceptions import (
    InvalidBrickSize,
    RenkoConfigurationError,
    UnsupportedRenkoMode,
    ValidationFailed,
)
from backend.app.chart.renko.events import (
    BrickValidationFailed,
    RenkoEngineStarted,
    RenkoEngineStopped,
)
from backend.app.chart.renko.factory import RenkoFactory
from backend.app.chart.renko.interfaces import BrickValidator, RenkoEngine
from backend.app.chart.renko.models import BrickState, BrickDirection
from backend.app.chart.renko.pipeline import RenkoPipelineStage
from backend.app.chart.renko.registry import RenkoRegistry
from backend.app.chart.renko.validator import DefaultBrickValidator
from backend.app.events.bus import EventBus
from backend.app.pipeline.context import PipelineContext
from backend.app.plugins.manager import PluginManager
from backend.app.infrastructure.di import configure_container


class DummyRenkoEngine(RenkoEngine):
    def __init__(self) -> None:
        self._state = BrickState(direction=BrickDirection.NEUTRAL, last_price=0.0, brick_size=1.0, is_open=False)
        self.processed = []

    @property
    def state(self) -> BrickState:
        return self._state

    async def start(self) -> None:
        self._state = BrickState(direction=self._state.direction, last_price=self._state.last_price, brick_size=self._state.brick_size, is_open=True)

    async def stop(self) -> None:
        self._state = BrickState(direction=self._state.direction, last_price=self._state.last_price, brick_size=self._state.brick_size, is_open=False)

    async def reset(self) -> None:
        self._state = BrickState(direction=BrickDirection.NEUTRAL, last_price=0.0, brick_size=self._state.brick_size, is_open=False)

    async def process_market_data(self, market_data: dict) -> None:
        self.processed.append(market_data)

    async def get_snapshot(self):
        return self._state


class TestBrickValidator(BrickValidator):
    async def validate_configuration(self, configuration: BrickConfiguration) -> bool:
        return True

    async def validate_data(self, market_data: dict) -> bool:
        return True

    async def validate_transition(self, previous_state, next_state) -> bool:
        return True


@pytest.mark.asyncio
async def test_renko_registry_register_and_lookup() -> None:
    registry = RenkoRegistry()
    engine = DummyRenkoEngine()
    registry.register("traditional", engine)

    assert registry.exists("traditional")
    assert registry.get("traditional") is engine
    assert registry.all() == [engine]

    with pytest.raises(ValueError):
        registry.register("traditional", engine)

    with pytest.raises(KeyError):
        registry.get("missing")


def test_renko_factory_uses_registry() -> None:
    registry = RenkoRegistry()
    engine = DummyRenkoEngine()
    registry.register("traditional", engine)
    factory = RenkoFactory(registry)

    configuration = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=2.0)
    assert factory.create(configuration) is engine

    with pytest.raises(KeyError):
        factory.create(BrickConfiguration(brick_type=BrickType.AI, brick_size=2.0, ai_model="model"))


@pytest.mark.asyncio
async def test_default_brick_validator_configuration() -> None:
    validator = DefaultBrickValidator()
    configuration = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0)
    assert await validator.validate_configuration(configuration)


@pytest.mark.asyncio
async def test_default_brick_validator_rejects_invalid_brick_size() -> None:
    validator = DefaultBrickValidator()
    configuration = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=0.0)

    with pytest.raises(InvalidBrickSize):
        await validator.validate_configuration(configuration)


@pytest.mark.asyncio
async def test_default_brick_validator_rejects_unsupported_mode() -> None:
    validator = DefaultBrickValidator()
    configuration = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0, mode=RenkoMode.LIVE)
    assert await validator.validate_configuration(configuration)


@pytest.mark.asyncio
async def test_default_brick_validator_rejects_bad_data() -> None:
    validator = DefaultBrickValidator()

    with pytest.raises(ValidationFailed):
        await validator.validate_data(None)

    with pytest.raises(ValidationFailed):
        await validator.validate_data({})


@pytest.mark.asyncio
async def test_renko_pipeline_stage_publishes_events() -> None:
    registry = RenkoRegistry()
    engine = DummyRenkoEngine()
    registry.register("traditional", engine)

    factory = RenkoFactory(registry)
    validator = DefaultBrickValidator()
    event_bus = EventBus()

    events: list = []

    async def handler(event):
        events.append(event)

    event_bus.subscribe(RenkoEngineStarted, handler)
    event_bus.subscribe(RenkoEngineStopped, handler)
    event_bus.subscribe(BrickValidationFailed, handler)

    stage = RenkoPipelineStage(factory, validator, event_bus)
    context = PipelineContext()
    context.set("renko_configuration", BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0))
    context.set("aggregated_market_data", {"timestamp": datetime.utcnow(), "close": 100.0})

    result = await stage.execute(context)

    assert result.status.name == "SUCCESS"
    assert context.get("renko_engine") is engine
    assert any(isinstance(event, RenkoEngineStarted) for event in events)
    assert any(isinstance(event, RenkoEngineStopped) for event in events)


@pytest.mark.asyncio
async def test_plugin_manager_loads_renko_registrations(tmp_path) -> None:
    plugin_code = """from __future__ import annotations

from backend.app.chart.renko.registry import RenkoRegistry
from backend.app.chart.renko.interfaces import RenkoEngine
from backend.app.chart.renko.models import BrickState, BrickDirection


class DummyRenkoEngineImpl(RenkoEngine):
    def __init__(self) -> None:
        self._state = BrickState(direction=BrickDirection.NEUTRAL, last_price=0.0, brick_size=1.0, is_open=False)

    @property
    def state(self):
        return self._state

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def reset(self) -> None:
        pass

    async def process_market_data(self, market_data: dict) -> None:
        pass

    async def get_snapshot(self):
        return self._state


class RenkoPlugin:
    name = "renko_plugin"

    async def load(self, event_bus=None):
        pass

    async def start(self):
        pass

    async def stop(self):
        pass

    async def unload(self):
        pass

    async def register_renko_engines(self, registry: RenkoRegistry):
        registry.register("traditional", DummyRenkoEngineImpl())
"""
    plugin_file = tmp_path / "renko_plugin.py"
    plugin_file.write_text(plugin_code, encoding="utf-8")

    renko_registry = RenkoRegistry()
    manager = PluginManager(tmp_path, renko_registry=renko_registry)

    await manager.load()

    assert renko_registry.exists("traditional")
    assert manager.get_plugin("renko_plugin").name == "renko_plugin"

    await manager.unload()


def test_dependency_injection_container_provides_renko_components() -> None:
    container = configure_container()

    assert container.renko_registry() is not None
    assert container.renko_factory() is not None
    assert container.renko_validator() is not None
