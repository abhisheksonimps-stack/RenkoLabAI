from __future__ import annotations

from typing import TYPE_CHECKING

from backend.app.chart.interfaces import ChartEngine
from backend.app.chart.registry import ChartRegistry

if TYPE_CHECKING:
    from backend.app.chart.models import ChartConfiguration


class ChartFactory:
    def __init__(self, registry: ChartRegistry) -> None:
        self.registry = registry

    def create(self, configuration: "ChartConfiguration") -> ChartEngine:
        return self.registry.get(configuration.chart_type)
