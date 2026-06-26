from __future__ import annotations

from typing import Dict, Iterable

from backend.app.pipeline.interfaces import PipelineStage


class StageRegistry:
    def __init__(self) -> None:
        self._stages: Dict[str, PipelineStage] = {}

    def register(self, stage: PipelineStage) -> None:
        if stage.name in self._stages:
            raise ValueError(f"Stage already registered: {stage.name}")
        self._stages[stage.name] = stage

    def get(self, name: str) -> PipelineStage:
        return self._stages[name]

    def all(self) -> Iterable[PipelineStage]:
        return self._stages.values()

    def names(self) -> list[str]:
        return list(self._stages)
