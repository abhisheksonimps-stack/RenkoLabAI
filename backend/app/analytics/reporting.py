"""Analytics reporting renderers."""

from __future__ import annotations

import csv
import io
import json
from decimal import Decimal
from typing import Iterable

from backend.app.analytics.domain.entities import AnalyticsReport
from backend.app.analytics.dto.analytics import AnalyticsReportDTO, MetricDTO
from backend.app.analytics.mappers.analytics import report_to_dto


def _format_value(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:,.4f}"
    if isinstance(value, Decimal):
        return f"{value:,.4f}"
    return str(value)


def _metric_lookup(metrics: Iterable[MetricDTO], name: str) -> str:
    for metric in metrics:
        if metric.name == name:
            return _format_value(metric.value)
    return "n/a"


class AnalyticsReportRenderer:
    """Render analytics reports into common transport formats."""

    def to_dto(self, report: AnalyticsReport) -> AnalyticsReportDTO:
        """Return the DTO representation of a report."""
        return report_to_dto(report)

    def to_json(self, report: AnalyticsReport, indent: int = 2) -> str:
        """Render a report as JSON."""
        dto = self.to_dto(report)
        return json.dumps(dto.model_dump(mode="json"), indent=indent, sort_keys=True)

    def to_markdown(self, report: AnalyticsReport) -> str:
        """Render a report as Markdown."""
        dto = self.to_dto(report)
        lines = [
            f"# {dto.title}",
            "",
            f"Report ID: `{dto.report_id}`",
            f"Status: `{dto.status}`",
            f"Generated at: `{dto.generated_at.isoformat()}`",
            "",
            "## Strategy Analytics",
            "",
            "| Scenario | Strategy | Symbol | Net Profit | Win Rate | Sharpe | Max Drawdown | Trades |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for item in dto.strategy_analytics:
            lines.append(
                "| "
                + " | ".join(
                    [
                        item.scenario_id,
                        item.strategy_name,
                        item.symbol,
                        _metric_lookup(item.metrics, "net_profit"),
                        _metric_lookup(item.metrics, "win_rate"),
                        _metric_lookup(item.metrics, "sharpe"),
                        _metric_lookup(item.metrics, "max_drawdown_pct"),
                        str(item.trade_count),
                    ]
                )
                + " |"
            )
        lines.extend(["", "## Rankings", ""])
        for ranking in dto.rankings:
            lines.extend(
                [
                    f"### {ranking.metric_name} ({ranking.direction})",
                    "",
                    "| Rank | Analytics ID | Value |",
                    "| --- | --- | --- |",
                ]
            )
            for entry in ranking.entries:
                lines.append(
                    f"| {entry.rank} | {entry.analytics_id} | {_format_value(entry.value)} |"
                )
            lines.append("")
        return "\n".join(lines).rstrip()

    def to_csv(self, report: AnalyticsReport) -> str:
        """Render strategy analytics from a report as CSV."""
        dto = self.to_dto(report)
        fieldnames = [
            "analytics_id",
            "scenario_id",
            "strategy_name",
            "symbol",
            "dataset_id",
            "currency",
            "net_profit",
            "win_rate",
            "sharpe",
            "sortino",
            "max_drawdown_pct",
            "trade_count",
        ]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        for item in dto.strategy_analytics:
            writer.writerow(
                {
                    "analytics_id": item.analytics_id,
                    "scenario_id": item.scenario_id,
                    "strategy_name": item.strategy_name,
                    "symbol": item.symbol,
                    "dataset_id": item.dataset_id,
                    "currency": item.currency,
                    "net_profit": _metric_lookup(item.metrics, "net_profit"),
                    "win_rate": _metric_lookup(item.metrics, "win_rate"),
                    "sharpe": _metric_lookup(item.metrics, "sharpe"),
                    "sortino": _metric_lookup(item.metrics, "sortino"),
                    "max_drawdown_pct": _metric_lookup(item.metrics, "max_drawdown_pct"),
                    "trade_count": item.trade_count,
                }
            )
        return buffer.getvalue()


__all__ = ["AnalyticsReportRenderer"]
