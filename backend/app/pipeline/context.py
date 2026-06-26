from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class PipelineContext:
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def add_metadata(self, key: str, value: Any) -> None:
        self.metadata[key] = value

    def merge(self, other: "PipelineContext") -> None:
        self.data.update(other.data)
        self.metadata.update(other.metadata)
