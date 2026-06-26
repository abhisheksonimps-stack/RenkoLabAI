from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import pytest

from backend.app.events.bus import EventBus
from backend.app.pipeline import (
    PipelineContext,
    PipelineStarted,
    PipelineStageCompleted,
    PipelineStageFailed,
    PipelineStageStarted,
    PipelineCompleted,
    PipelineError,
    ProcessingGraph,
    StageRegistry,
    StageResult,
    StageStatus,
)
from backend.app.pipeline.interfaces import PipelineStage
from backend.app.pipeline.pipeline import DefaultPipeline, PipelineConfig


class DummyStage(PipelineStage):
    def __init__(self, name: str, output_key: str, output_value: Any) -> None:
        self._name = name
        self.output_key = output_key
        self.output_value = output_value

    @property
    def name(self) -> str:
        return self._name

    async def execute(self, context: PipelineContext) -> StageResult:
        context.set(self.output_key, self.output_value)
        return StageResult(stage_name=self.name, status=StageStatus.SUCCESS, context=context)


class FailingStage(PipelineStage):
    def __init__(self, name: str, fail_on_attempt: int = 1) -> None:
        self._name = name
        self.attempts = 0
        self.fail_on_attempt = fail_on_attempt

    @property
    def name(self) -> str:
        return self._name

    async def execute(self, context: PipelineContext) -> StageResult:
        self.attempts += 1
        if self.attempts <= self.fail_on_attempt:
            raise RuntimeError("stage failure")
        return StageResult(stage_name=self.name, status=StageStatus.SUCCESS, context=context)


@pytest.fixture
def event_bus():
    bus = EventBus()
    events: list = []

    async def handler(event):
        events.append(event)

    for event_type in [
        PipelineStarted,
        PipelineStageStarted,
        PipelineStageCompleted,
        PipelineStageFailed,
        PipelineCompleted,
        PipelineError,
    ]:
        bus.subscribe(event_type, handler)

    return bus, events


@pytest.fixture
def registry():
    return StageRegistry()


@pytest.mark.asyncio
async def test_stage_execution_and_context_propagation(event_bus, registry):
    bus, events = event_bus
    registry.register(DummyStage("stage1", "value1", 123))
    graph = ProcessingGraph(registry)
    pipeline = DefaultPipeline(graph, bus)
    context = PipelineContext()

    result = await pipeline.run(context)

    assert result.status == StageStatus.SUCCESS
    assert context.get("value1") == 123
    assert any(isinstance(event, PipelineStarted) for event in events)
    assert any(isinstance(event, PipelineStageStarted) for event in events)
    assert any(isinstance(event, PipelineStageCompleted) for event in events)
    assert any(isinstance(event, PipelineCompleted) for event in events)


@pytest.mark.asyncio
async def test_multiple_stages_respect_order(event_bus, registry):
    bus, events = event_bus
    stage1 = DummyStage("stage1", "a", 1)
    stage2 = DummyStage("stage2", "b", 2)
    registry.register(stage1)
    registry.register(stage2)
    graph = ProcessingGraph(registry)
    graph.add_edge("stage1", "stage2")
    pipeline = DefaultPipeline(graph, bus)
    context = PipelineContext()

    result = await pipeline.run(context)

    assert result.status == StageStatus.SUCCESS
    assert context.get("a") == 1
    assert context.get("b") == 2
    order = [event.payload.get("stage") for event in events if isinstance(event, PipelineStageStarted)]
    assert order == ["stage1", "stage2"]


@pytest.mark.asyncio
async def test_failure_handling_stops_pipeline(event_bus, registry):
    bus, events = event_bus
    registry.register(DummyStage("stage1", "a", 1))
    registry.register(FailingStage("stage2"))
    registry.register(DummyStage("stage3", "c", 3))
    graph = ProcessingGraph(registry)
    graph.add_edge("stage1", "stage2")
    graph.add_edge("stage2", "stage3")
    pipeline = DefaultPipeline(graph, bus)
    context = PipelineContext()

    result = await pipeline.run(context)

    assert result.status == StageStatus.FAILED
    assert context.get("a") == 1
    assert context.get("c") is None
    assert any(isinstance(event, PipelineStageFailed) for event in events)
    assert any(isinstance(event, PipelineError) for event in events)


@pytest.mark.asyncio
async def test_retry_policy(event_bus, registry):
    bus, events = event_bus
    failing = FailingStage("stage1", fail_on_attempt=2)
    registry.register(failing)
    graph = ProcessingGraph(registry)
    pipeline = DefaultPipeline(graph, bus, PipelineConfig(retry_count=2, retry_delay_seconds=0.0))
    context = PipelineContext()

    result = await pipeline.run(context)

    assert result.status == StageStatus.SUCCESS
    assert failing.attempts == 3
    assert any(isinstance(event, PipelineStageCompleted) for event in events)


@pytest.mark.asyncio
async def test_event_publication_for_each_stage(event_bus, registry):
    bus, events = event_bus
    registry.register(DummyStage("stage1", "a", 1))
    registry.register(DummyStage("stage2", "b", 2))
    graph = ProcessingGraph(registry)
    graph.add_edge("stage1", "stage2")
    pipeline = DefaultPipeline(graph, bus)
    context = PipelineContext()

    await pipeline.run(context)

    assert len([event for event in events if isinstance(event, PipelineStageStarted)]) == 2
    assert len([event for event in events if isinstance(event, PipelineStageCompleted)]) == 2


@pytest.mark.asyncio
async def test_context_propagation_between_stages(event_bus, registry):
    bus, events = event_bus
    class ContextStage(PipelineStage):
        def __init__(self, name: str):
            self._name = name

        @property
        def name(self) -> str:
            return self._name

        async def execute(self, context: PipelineContext) -> StageResult:
            if self._name == "stage1":
                context.set("shared", 42)
            return StageResult(stage_name=self.name, status=StageStatus.SUCCESS, context=context)

    stage1 = ContextStage("stage1")
    stage2 = ContextStage("stage2")
    registry.register(stage1)
    registry.register(stage2)
    graph = ProcessingGraph(registry)
    graph.add_edge("stage1", "stage2")

    pipeline = DefaultPipeline(graph, bus)
    context = PipelineContext()

    result = await pipeline.run(context)

    assert result.status == StageStatus.SUCCESS
    assert context.get("shared") == 42
