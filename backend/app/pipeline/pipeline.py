from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from backend.app.events.bus import EventBus
from backend.app.pipeline.context import PipelineContext
from backend.app.pipeline.events import (
    PipelineCompleted,
    PipelineError,
    PipelineStageCompleted,
    PipelineStageFailed,
    PipelineStageStarted,
    PipelineStarted,
)
from backend.app.pipeline.graph import ProcessingGraph
from backend.app.pipeline.interfaces import Pipeline
from backend.app.pipeline.results import StageResult, StageStatus


@dataclass
class PipelineConfig:
    retry_count: int = 0
    retry_delay_seconds: float = 0.0


class DefaultPipeline(Pipeline):
    def __init__(
        self,
        graph: ProcessingGraph,
        event_bus: EventBus,
        config: PipelineConfig | None = None,
    ) -> None:
        self.graph = graph
        self.event_bus = event_bus
        self.config = config or PipelineConfig()

    async def run(self, context: PipelineContext) -> StageResult:
        await self._publish_event(PipelineStarted, {"metadata": context.metadata})
        final_result = StageResult(stage_name="pipeline", status=StageStatus.SUCCESS, context=context)

        for stage in self.graph.get_ordered_stages():
            result = await self._run_stage(stage, context)
            if result.status == StageStatus.FAILED:
                final_result = result
                break
            context.merge(result.context)

        if final_result.status == StageStatus.SUCCESS:
            await self._publish_event(PipelineCompleted, {"metadata": context.metadata})
        else:
            await self._publish_event(PipelineError, {"error": str(final_result.error), "stage": final_result.stage_name})

        return final_result

    async def _run_stage(self, stage, context: PipelineContext) -> StageResult:
        await self._publish_event(PipelineStageStarted, {"stage": stage.name})
        retries = 0
        while True:
            start_time = time.monotonic()
            try:
                result = await stage.execute(context)
            except Exception as exc:
                retries += 1
                if retries > self.config.retry_count:
                    failed_result = StageResult(
                        stage_name=stage.name,
                        status=StageStatus.FAILED,
                        context=context,
                        error=exc,
                        retries=retries - 1,
                        metrics={"duration_seconds": time.monotonic() - start_time},
                    )
                    await self._publish_event(PipelineStageFailed, {"stage": stage.name, "error": str(exc)})
                    return failed_result

                await asyncio.sleep(self.config.retry_delay_seconds)
                continue

            duration = time.monotonic() - start_time
            result.metrics["duration_seconds"] = duration
            result.retries = retries
            await self._publish_event(PipelineStageCompleted, {"stage": stage.name, "status": result.status.value, "metrics": result.metrics})
            return result

    async def _publish_event(self, event_type, payload: dict) -> None:
        event = event_type(
            name=event_type.__name__,
            occurred_at=datetime.utcnow(),
            payload=payload,
        )
        await self.event_bus.publish(event)
