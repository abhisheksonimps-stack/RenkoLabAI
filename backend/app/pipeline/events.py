from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.app.events.base import BaseEvent


@dataclass(frozen=True)
class PipelineStarted(BaseEvent):
    pass


@dataclass(frozen=True)
class PipelineStageStarted(BaseEvent):
    pass


@dataclass(frozen=True)
class PipelineStageCompleted(BaseEvent):
    pass


@dataclass(frozen=True)
class PipelineStageFailed(BaseEvent):
    pass


@dataclass(frozen=True)
class PipelineCompleted(BaseEvent):
    pass


@dataclass(frozen=True)
class PipelineError(BaseEvent):
    pass
