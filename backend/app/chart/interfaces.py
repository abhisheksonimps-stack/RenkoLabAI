from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from backend.app.chart.models import Chart, ChartContext, ChartConfiguration


class ChartBuilder(ABC):
    @abstractmethod
    async def build(self, candles: Iterable[ChartContext], configuration: ChartConfiguration) -> Chart:
        raise NotImplementedError


class ChartValidator(ABC):
    @abstractmethod
    async def validate(self, configuration: ChartConfiguration) -> bool:
        raise NotImplementedError


class ChartEngine(ABC):
    @abstractmethod
    async def create_chart(self, context: ChartContext) -> Chart:
        raise NotImplementedError

    @abstractmethod
    async def update_chart(self, chart: Chart, context: ChartContext) -> Chart:
        raise NotImplementedError

    @abstractmethod
    async def close_chart(self, chart: Chart) -> Chart:
        raise NotImplementedError
