from __future__ import annotations

from typing import Iterable

from backend.app.pipeline.interfaces import PipelineStage
from backend.app.pipeline.registry import StageRegistry


class ProcessingGraph:
    def __init__(self, stage_registry: StageRegistry) -> None:
        self.stage_registry = stage_registry
        self._edges: dict[str, list[str]] = {}

    def add_edge(self, source: str, target: str) -> None:
        if source not in self.stage_registry.names() or target not in self.stage_registry.names():
            raise ValueError("Both source and target stages must be registered")
        self._edges.setdefault(source, []).append(target)

    def get_ordered_stages(self) -> list[PipelineStage]:
        visited: set[str] = set()
        order: list[PipelineStage] = []

        def visit(stage_name: str) -> None:
            if stage_name in visited:
                return
            visited.add(stage_name)
            for target in self._edges.get(stage_name, []):
                visit(target)
            order.append(self.stage_registry.get(stage_name))

        for stage_name in self.stage_registry.names():
            visit(stage_name)

        return list(reversed(order))

    def downstream(self, source: str) -> list[str]:
        return list(self._edges.get(source, []))

    def upstream(self, target: str) -> list[str]:
        return [source for source, targets in self._edges.items() if target in targets]
