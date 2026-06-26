from __future__ import annotations

from typing import Dict, Optional

from backend.app.chart.interfaces import ChartEngine


class ChartRegistry:
    def __init__(self) -> None:
        self._engines: Dict[str, ChartEngine] = {}

    def register(self, chart_type: str, engine: ChartEngine) -> None:
        if chart_type in self._engines:
            raise ValueError(f"Chart type already registered: {chart_type}")
        self._engines[chart_type] = engine

    def get(self, chart_type: str) -> ChartEngine:
        if chart_type not in self._engines:
            raise KeyError(f"Chart type not registered: {chart_type}")
        return self._engines[chart_type]

    def all(self) -> list[ChartEngine]:
        return list(self._engines.values())

    def exists(self, chart_type: str) -> bool:
        return chart_type in self._engines
