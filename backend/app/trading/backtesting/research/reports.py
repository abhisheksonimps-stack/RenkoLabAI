"""Research report renderers."""

from __future__ import annotations

import csv
import html
import io
import json
from datetime import datetime
from typing import Iterable, Mapping

from backend.app.trading.backtesting.research.models import ResearchReport


def _json_default(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "to_records"):
        return value.to_records()
    if hasattr(value, "to_record"):
        return value.to_record()
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python")
    if hasattr(value, "__dict__"):
        return vars(value)
    return str(value)


def _records(report: ResearchReport) -> list[dict[str, object]]:
    if report.optimization is None:
        return []
    return [trial.result.to_record() | {"objective_value": trial.objective_value, "parameters": dict(trial.parameters)} for trial in report.optimization.trials]


class ResearchReportRenderer:
    """Render research reports in machine and human readable formats."""

    def render_json(self, report: ResearchReport) -> str:
        """Render report as JSON."""
        return json.dumps(report, sort_keys=True, indent=2, default=_json_default)

    def render_csv(self, report: ResearchReport) -> str:
        """Render optimization trials as CSV."""
        rows = _records(report)
        if not rows:
            return ""
        flattened = [self._flatten(row) for row in rows]
        fields = sorted({key for row in flattened for key in row})
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fields)
        writer.writeheader()
        writer.writerows(flattened)
        return buffer.getvalue()

    def render_markdown(self, report: ResearchReport) -> str:
        """Render report as Markdown."""
        lines = [f"# {report.title}", "", f"Generated: {report.generated_at.isoformat()}", ""]
        if report.optimization is not None:
            best = report.optimization.best_trial
            lines.append("## Optimization")
            lines.append("")
            lines.append(f"Objective: `{report.optimization.objective.metric}`")
            lines.append(f"Trials: {len(report.optimization.trials)}")
            if best is not None:
                lines.append(f"Best scenario: `{best.scenario.scenario_id}`")
                lines.append(f"Best value: {best.objective_value}")
            lines.append("")
            rows = _records(report)[:20]
            if rows:
                flattened = [self._flatten(row) for row in rows]
                fields = ["scenario_id", "strategy", "symbol", "status", "objective_value"]
                lines.append("| " + " | ".join(fields) + " |")
                lines.append("| " + " | ".join("---" for _ in fields) + " |")
                for row in flattened:
                    lines.append("| " + " | ".join(str(row.get(field, "")) for field in fields) + " |")
        if report.monte_carlo is not None:
            lines.extend(["", "## Monte Carlo", "", f"Probability of ruin: {report.monte_carlo.probability_of_ruin}"])
        if report.portfolio is not None:
            lines.extend(["", "## Portfolio Allocation", ""])
            for allocation in report.portfolio.allocations:
                lines.append(f"- {allocation.name}: {allocation.weight:.4f} ({allocation.capital:.2f})")
        return "\n".join(lines).rstrip() + "\n"

    def render_html(self, report: ResearchReport) -> str:
        """Render report as minimal HTML suitable for dashboards."""
        markdown = self.render_markdown(report)
        escaped = html.escape(markdown)
        return f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(report.title)}</title></head><body><pre>{escaped}</pre></body></html>"

    @staticmethod
    def _flatten(row: Mapping[str, object]) -> dict[str, object]:
        flattened: dict[str, object] = {}
        for key, value in row.items():
            if isinstance(value, Mapping):
                for nested_key, nested_value in value.items():
                    flattened[f"{key}.{nested_key}"] = nested_value
            else:
                flattened[key] = value
        return flattened


__all__ = ["ResearchReportRenderer"]
