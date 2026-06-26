from __future__ import annotations

from __future__ import annotations

from datetime import datetime

from backend.app.chart.renko.configuration import BrickConfiguration
from backend.app.chart.renko.events import BrickValidationFailed, RenkoEngineStarted, RenkoEngineStopped
from backend.app.chart.renko.factory import RenkoFactory
from backend.app.chart.renko.interfaces import BrickValidator
from backend.app.events.bus import EventBus
from backend.app.pipeline.context import PipelineContext
from backend.app.pipeline.interfaces import PipelineStage
from backend.app.pipeline.results import StageResult, StageStatus


class RenkoPipelineStage(PipelineStage):
    def __init__(self, factory: RenkoFactory, validator: BrickValidator, event_bus: EventBus) -> None:
        self.factory = factory
        self.validator = validator
        self.event_bus = event_bus

        self.event_bus.register_event(RenkoEngineStarted)
        self.event_bus.register_event(RenkoEngineStopped)
        self.event_bus.register_event(BrickValidationFailed)

    @property
    def name(self) -> str:
        return "renko_pipeline"

    async def execute(self, context: PipelineContext) -> StageResult:
        configuration = context.get("renko_configuration")
        market_data = context.get("aggregated_market_data")

        if configuration is None or market_data is None:
            return StageResult(stage_name=self.name, status=StageStatus.SKIPPED, context=context)

        try:
            await self.validator.validate_configuration(configuration)
            await self.validator.validate_data(market_data)
        except Exception as exc:
            await self._publish_event(BrickValidationFailed, configuration=configuration, reason=str(exc))
            return StageResult(stage_name=self.name, status=StageStatus.FAILED, context=context)

        engine = self.factory.create(configuration)
        await self._publish_event(RenkoEngineStarted, configuration=configuration)
        await engine.process_market_data(market_data)
        await self._publish_event(RenkoEngineStopped, configuration=configuration)

        context.set("renko_engine", engine)
        return StageResult(stage_name=self.name, status=StageStatus.SUCCESS, context=context)

    async def _publish_event(self, event_type, **payload) -> None:
        event = event_type(
            name=event_type.__name__,
            occurred_at=datetime.utcnow(),
            payload={},
            **payload,
        )
        await self.event_bus.publish(event)
