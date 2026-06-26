from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class StageStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StageResult:
    stage_name: str
    status: StageStatus
    context: "PipelineContext"
    error: Exception | None = None
    retries: int = 0
    metrics: dict[str, Any] = None

    def __post_init__(self) -> None:
        if self.metrics is None:
            self.metrics = {}
