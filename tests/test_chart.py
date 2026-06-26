from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from backend.app.chart.events import ChartCreated, ChartValidationFailed
from backend.app.chart.factory import ChartFactory
from backend.app.chart.interfaces import ChartEngine, ChartValidator
from backend.app.chart.models import Chart, ChartBar, ChartConfiguration, ChartContext, ChartMetadata
from backend.app.chart.pipeline import ChartPipelineStage
from backend.app.chart.registry import ChartRegistry
from backend.app.events.bus import EventBus
from backend.app.pipeline.context import PipelineContext
from backend.app.plugins.manager import PluginManager


class DummyChartEngine(ChartEngine):
    async def create_chart(self, context: ChartContext):
        return Chart(
            chart_id="dummy-chart",
            metadata=ChartMetadata(
                chart_type=context.configuration.chart_type,
                created_at=datetime.utcnow(),
            ),
            bars=context.candles,
            configuration=context.configuration,
            context=context,
        )

    async def update_chart(self, chart, context: ChartContext):
        return chart

    async def close_chart(self, chart):
        return chart


class AlwaysValidChartValidator(ChartValidator):
    async def validate(self, configuration: ChartConfiguration) -> bool:
        return True


class NeverValidChartValidator(ChartValidator):
    async def validate(self, configuration: ChartConfiguration) -> bool:
        return False


@pytest.mark.asyncio
async def test_chart_registry_register_and_retrieve_engine() -> None:
    registry = ChartRegistry()
    engine = DummyChartEngine()
    registry.register("dummy", engine)

    assert registry.get("dummy") is engine
    assert registry.exists("dummy")
    assert registry.all() == [engine]

    with pytest.raises(ValueError):
        registry.register("dummy", engine)

    with pytest.raises(KeyError):
        registry.get("missing")


@pytest.mark.asyncio
async def test_chart_factory_creates_engine_from_registry() -> None:
    registry = ChartRegistry()
    engine = DummyChartEngine()
    registry.register("dummy", engine)
    factory = ChartFactory(registry)

    assert factory.create(ChartConfiguration(chart_type="dummy")) is engine

    with pytest.raises(KeyError):
        factory.create(ChartConfiguration(chart_type="missing"))


@pytest.mark.asyncio
async def test_chart_pipeline_stage_publishes_chart_created_event() -> None:
    registry = ChartRegistry()
    engine = DummyChartEngine()
    registry.register("dummy", engine)
    factory = ChartFactory(registry)
    validator = AlwaysValidChartValidator()
    event_bus = EventBus()

    events: list = []

    async def handler(event):
        events.append(event)

    event_bus.subscribe(ChartCreated, handler)
    stage = ChartPipelineStage(factory, validator, event_bus)
    context = PipelineContext()
    context.set("chart_configuration", ChartConfiguration(chart_type="dummy", settings={}))
    context.set(
        "completed_candles",
        [
            {
                "timestamp": datetime.utcnow(),
                "open": 100.0,
                "high": 105.0,
                "low": 95.0,
                "close": 102.5,
                "volume": 1000.0,
                "trades": 10,
            }
        ],
    )

    result = await stage.execute(context)

    assert result.status.name == "SUCCESS"
    assert context.get("chart") is not None
    assert any(isinstance(event, ChartCreated) for event in events)


@pytest.mark.asyncio
async def test_chart_pipeline_stage_skips_when_no_configuration() -> None:
    registry = ChartRegistry()
    factory = ChartFactory(registry)
    validator = AlwaysValidChartValidator()
    event_bus = EventBus()
    stage = ChartPipelineStage(factory, validator, event_bus)
    context = PipelineContext()

    result = await stage.execute(context)

    assert result.status.name == "SKIPPED"
    assert context.get("chart") is None


@pytest.mark.asyncio
async def test_chart_pipeline_stage_fails_validation() -> None:
    registry = ChartRegistry()
    engine = DummyChartEngine()
    registry.register("dummy", engine)
    factory = ChartFactory(registry)
    validator = NeverValidChartValidator()
    event_bus = EventBus()

    events: list = []

    async def handler(event):
        events.append(event)

    event_bus.subscribe(ChartValidationFailed, handler)
    stage = ChartPipelineStage(factory, validator, event_bus)
    context = PipelineContext()
    context.set("chart_configuration", ChartConfiguration(chart_type="dummy", settings={}))
    context.set("completed_candles", [])

    result = await stage.execute(context)

    assert result.status.name == "FAILED"
    assert any(isinstance(event, ChartValidationFailed) for event in events)


@pytest.mark.asyncio
async def test_plugin_manager_loads_plugins_with_chart_registration(tmp_path) -> None:
    plugin_code = """from __future__ import annotations

from backend.app.chart.registry import ChartRegistry
from backend.app.chart.interfaces import ChartEngine
from backend.app.chart.models import ChartContext


class DummyChartEngineImpl(ChartEngine):
    async def create_chart(self, context: ChartContext):
        return None

    async def update_chart(self, chart, context: ChartContext):
        return chart

    async def close_chart(self, chart):
        return chart


class ChartPlugin:
    name = "chart_plugin"

    async def load(self, event_bus=None):
        self.loaded = True

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True

    async def unload(self):
        self.unloaded = True

    async def register_charts(self, registry: ChartRegistry):
        registry.register("plugin_chart", DummyChartEngineImpl())
"""
    plugin_file = tmp_path / "chart_plugin.py"
    plugin_file.write_text(plugin_code, encoding="utf-8")

    chart_registry = ChartRegistry()
    manager = PluginManager(tmp_path, chart_registry=chart_registry)

    await manager.load()

    assert chart_registry.exists("plugin_chart")
    assert manager.get_plugin("chart_plugin").name == "chart_plugin"

    await manager.unload()
