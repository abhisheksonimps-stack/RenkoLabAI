from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from backend.app.chart.events import ChartClosed, ChartCreated, ChartUpdated, ChartValidationFailed
from backend.app.chart.factory import ChartFactory
from backend.app.chart.interfaces import ChartValidator
from backend.app.chart.models import Chart, ChartBar, ChartConfiguration, ChartContext
from backend.app.events.bus import EventBus
from backend.app.pipeline.context import PipelineContext
from backend.app.pipeline.interfaces import PipelineStage
from backend.app.pipeline.results import StageResult, StageStatus


class ChartPipelineStage(PipelineStage):
    def __init__(
        self,
        chart_factory: ChartFactory,
        validator: ChartValidator,
        event_bus: EventBus,
    ) -> None:
        self.chart_factory = chart_factory
        self.validator = validator
        self.event_bus = event_bus

        self.event_bus.register_event(ChartCreated)
        self.event_bus.register_event(ChartUpdated)
        self.event_bus.register_event(ChartClosed)
        self.event_bus.register_event(ChartValidationFailed)

    @property
    def name(self) -> str:
        return "chart_pipeline"

    async def execute(self, context: PipelineContext) -> StageResult:
        configuration = context.get("chart_configuration")
        candles = context.get("completed_candles")

        if configuration is None or candles is None:
            return StageResult(stage_name=self.name, status=StageStatus.SKIPPED, context=context)

        if not await self.validator.validate(configuration):
            await self._publish_event(ChartValidationFailed, {"configuration": configuration})
            return StageResult(stage_name=self.name, status=StageStatus.FAILED, context=context)

        engine = self.chart_factory.create(configuration)
        chart_context = ChartContext(candles=cast_candles(candles), configuration=configuration)
        chart = await engine.create_chart(chart_context)

        await self._publish_event(ChartCreated, {"chart_id": chart.chart_id})
        context.set("chart", chart)
        return StageResult(stage_name=self.name, status=StageStatus.SUCCESS, context=context)

    async def _publish_event(self, event_type, payload: dict) -> None:
        event = event_type(
            name=event_type.__name__,
            occurred_at=datetime.utcnow(),
            payload=payload,
        )
        await self.event_bus.publish(event)


def cast_candles(candles: Iterable[dict]) -> list[ChartBar]:
    bars: list[ChartBar] = []
    for candle in candles:
        bars.append(
            ChartBar(
                timestamp=candle["timestamp"],
                open=candle["open"],
                high=candle["high"],
                low=candle["low"],
                close=candle["close"],
                volume=candle.get("volume", 0.0),
                trades=candle.get("trades", 0),
                metadata=candle.get("metadata", {}),
            )
        )
    return bars
