from __future__ import annotations

from datetime import datetime
from typing import Iterable

from backend.app.chart.interfaces import ChartBuilder, ChartEngine, ChartValidator
from backend.app.chart.models import Chart, ChartBar, ChartConfiguration, ChartContext, ChartMetadata


class DefaultChartBuilder(ChartBuilder):
    async def build(self, candles: Iterable[ChartContext], configuration: ChartConfiguration) -> Chart:
        bars = []
        for candle_context in candles:
            bars.extend(candle_context.candles)

        metadata = ChartMetadata(
            chart_type=configuration.chart_type,
            created_at=datetime.utcnow(),
            description=None,
            tags=[],
        )

        context = ChartContext(candles=bars, configuration=configuration, metadata={})

        return Chart(
            chart_id=f"chart-{configuration.chart_type}-{int(metadata.created_at.timestamp())}",
            metadata=metadata,
            bars=bars,
            configuration=configuration,
            context=context,
        )


class DefaultChartValidator(ChartValidator):
    async def validate(self, configuration: ChartConfiguration) -> bool:
        return bool(configuration.chart_type and isinstance(configuration.settings, dict))


class DefaultChartEngine(ChartEngine):
    async def create_chart(self, context: ChartContext) -> Chart:
        chart_id = f"chart-{context.configuration.chart_type}-{int(datetime.utcnow().timestamp())}"
        metadata = ChartMetadata(
            chart_type=context.configuration.chart_type,
            created_at=datetime.utcnow(),
            description=None,
            tags=[],
        )
        return Chart(
            chart_id=chart_id,
            metadata=metadata,
            bars=context.candles,
            configuration=context.configuration,
            context=context,
        )

    async def update_chart(self, chart: Chart, context: ChartContext) -> Chart:
        updated = Chart(
            chart_id=chart.chart_id,
            metadata=chart.metadata,
            bars=chart.bars + context.candles,
            configuration=chart.configuration,
            context=context,
        )
        return updated

    async def close_chart(self, chart: Chart) -> Chart:
        return chart
