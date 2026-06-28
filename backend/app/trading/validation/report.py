"""Report — render a ResultSet (optionally ranked) into JSON / CSV / Markdown.

All renderers read the same canonical records (ScenarioResult.to_record), so the
formats cannot diverge. Pure and dependency-free; a future HTML dashboard would
consume ``to_records`` / ``to_json``.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Dict, List, Sequence

from backend.app.trading.validation.ranking import RankedEntry
from backend.app.trading.validation.results import ResultSet

_SUMMARY_COLUMNS = [
    "scenario_id", "strategy", "symbol", "brick_size", "net_profit", "win_rate",
    "profit_factor", "expectancy", "sharpe", "sortino", "max_drawdown_pct", "total_trades",
]


def to_records(result_set: ResultSet) -> List[Dict[str, Any]]:
    return result_set.to_records()


def to_json(result_set: ResultSet, indent: int = 2) -> str:
    return json.dumps(to_records(result_set), indent=indent, default=str, sort_keys=True)


def to_csv(result_set: ResultSet) -> str:
    records = to_records(result_set)
    if not records:
        return ""
    # Stable, union-of-keys header in first-seen order.
    header: List[str] = []
    for rec in records:
        for k in rec:
            if k not in header:
                header.append(k)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=header)
    writer.writeheader()
    for rec in records:
        row = {k: ("" if rec.get(k) is None else rec.get(k)) for k in header}
        if isinstance(row.get("strategy_params"), dict):
            row["strategy_params"] = json.dumps(row["strategy_params"], sort_keys=True)
        writer.writerow(row)
    return buf.getvalue()


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:,.4f}"
    return str(value)


def to_markdown(result_set: ResultSet, title: str = "Validation Results") -> str:
    records = to_records(result_set)
    lines = [f"# {title}", "", f"Scenarios: {len(records)}", ""]
    lines.append("| " + " | ".join(_SUMMARY_COLUMNS) + " |")
    lines.append("| " + " | ".join("---" for _ in _SUMMARY_COLUMNS) + " |")
    for rec in records:
        lines.append("| " + " | ".join(_fmt(rec.get(c)) for c in _SUMMARY_COLUMNS) + " |")
    return "\n".join(lines)


def ranked_to_markdown(entries: Sequence[RankedEntry], metric_label: str = "score",
                       title: str = "Ranked Validation Results") -> str:
    cols = ["rank", "score", "scenario_id", "strategy", "symbol", "brick_size"]
    lines = [f"# {title}", "", "| " + " | ".join(cols) + " |",
             "| " + " | ".join("---" for _ in cols) + " |"]
    for e in entries:
        rec = e.result.to_record()
        lines.append(
            "| " + " | ".join([
                str(e.rank), _fmt(e.value), str(rec["scenario_id"]),
                str(rec["strategy"]), str(rec["symbol"]), _fmt(rec["brick_size"]),
            ]) + " |"
        )
    return "\n".join(lines)
