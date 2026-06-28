"""Ranking — configurable, composable ordering over a ResultSet.

Presentation only: ranking never selects, re-runs, or tunes anything. Single
metric ranking and a normalized weighted composite score are provided.
Undefined metrics (e.g. profit factor with no losses) are treated as worst and
sorted last, deterministically (tie-break on scenario_id).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional

from backend.app.trading.validation.results import ResultSet, ScenarioResult

# +1 = higher is better, -1 = lower is better, 0 = neutral (excluded from default composite).
METRIC_DIRECTIONS: Dict[str, int] = {
    "net_profit": 1, "win_rate": 1, "profit_factor": 1, "expectancy": 1,
    "sharpe": 1, "sortino": 1, "average_trade": 1, "largest_win": 1,
    "largest_loss": 1, "total_return": 1, "total_pnl": 1,
    "max_drawdown": -1, "max_drawdown_pct": -1, "total_trades": 0,
}


@dataclass(frozen=True)
class RankedEntry:
    rank: int
    result: ScenarioResult
    value: float


def _is_valid(value) -> bool:
    return value is not None and not (isinstance(value, float) and math.isnan(value))


def rank_by(result_set: ResultSet, metric: str,
            higher_is_better: Optional[bool] = None) -> List[RankedEntry]:
    if higher_is_better is None:
        higher_is_better = METRIC_DIRECTIONS.get(metric, 1) >= 0
    completed = result_set.completed()

    def sort_key(r: ScenarioResult):
        v = r.metric(metric)
        valid = _is_valid(v)
        # Invalid -> always worst. Primary sort uses negated value for desc.
        primary = (v if valid else float("-inf")) if higher_is_better else (-v if valid else float("inf"))
        # We sort ascending on a tuple: (invalid_flag, primary_for_asc, scenario_id)
        invalid_flag = 0 if valid else 1
        primary_asc = (-v if higher_is_better else v) if valid else float("inf")
        return (invalid_flag, primary_asc, r.scenario.scenario_id)

    ordered = sorted(completed, key=sort_key)
    return [
        RankedEntry(rank=i + 1, result=r, value=(r.metric(metric) if _is_valid(r.metric(metric)) else float("nan")))
        for i, r in enumerate(ordered)
    ]


def _normalized(values: List[float], direction: int) -> List[float]:
    lo, hi = min(values), max(values)
    span = hi - lo
    if span == 0:
        return [0.0 for _ in values]
    norm = [(v - lo) / span for v in values]
    if direction < 0:  # lower is better -> invert
        norm = [1.0 - n for n in norm]
    return norm


def composite_score(result_set: ResultSet,
                    weights: Mapping[str, float]) -> List[RankedEntry]:
    completed = result_set.completed()
    if not completed or not weights:
        return [RankedEntry(rank=i + 1, result=r, value=0.0) for i, r in enumerate(completed)]

    # Gather and clean each metric column (invalid -> worst observed value).
    columns: Dict[str, List[float]] = {}
    for metric in weights:
        raw = [r.metric(metric) for r in completed]
        valid = [v for v in raw if _is_valid(v)]
        direction = METRIC_DIRECTIONS.get(metric, 1)
        if valid:
            worst = min(valid) if direction >= 0 else max(valid)
        else:
            worst = 0.0
        columns[metric] = [v if _is_valid(v) else worst for v in raw]

    scores = [0.0] * len(completed)
    for metric, weight in weights.items():
        direction = METRIC_DIRECTIONS.get(metric, 1)
        norm = _normalized(columns[metric], direction)
        for i, n in enumerate(norm):
            scores[i] += float(weight) * n

    indexed = sorted(
        range(len(completed)),
        key=lambda i: (-scores[i], completed[i].scenario.scenario_id),
    )
    return [RankedEntry(rank=pos + 1, result=completed[i], value=scores[i])
            for pos, i in enumerate(indexed)]
