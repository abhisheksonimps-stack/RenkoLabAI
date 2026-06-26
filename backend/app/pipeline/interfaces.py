from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from backend.app.pipeline.context import PipelineContext
from backend.app.pipeline.results import StageResult


class PipelineStage(ABC):
    @abstractmethod
    async def execute(self, context: PipelineContext) -> StageResult:
        raise NotImplementedError

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError


class Pipeline(ABC):
    @abstractmethod
    async def run(self, context: PipelineContext) -> StageResult:
        raise NotImplementedError
