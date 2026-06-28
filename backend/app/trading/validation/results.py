"""ScenarioResult / ResultSet — normalized, serializable outcomes.

Metrics are pulled straight from the frozen ``PerformanceMetrics`` (no
recomputation) into a flat block, so result definitions can never drift from the
backtesting engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional

from backend.app.trading.backtesting.metrics import PerformanceMetrics
from backend.app.trading.validation.scenario import Scenario, ScenarioStatus

# Canonical metric keys exposed by validation.
METRIC_KEYS = (
    "net_profit", "win_rate", "profit_factor", "expectancy", "sharpe", "sortino",
    "max_drawdown", "max_drawdown_pct", "total_trades", "average_trade",
    "largest_win", "largest_loss", "total_return", "total_pnl",
)


def metrics_from_performance(perf: PerformanceMetrics) -> Dict[str, Any]:
    return {
        "net_profit": perf.net_pnl,
        "win_rate": perf.win_rate,
        "profit_factor": perf.profit_factor,
        "expectancy": perf.expectancy,
        "sharpe": perf.sharpe,
        "sortino": perf.sortino,
        "max_drawdown": perf.max_drawdown,
        "max_drawdown_pct": perf.max_drawdown_pct,
        "total_trades": perf.num_trades,
        "average_trade": perf.expectancy,
        "largest_win": perf.largest_win,
        "largest_loss": perf.largest_loss,
        "total_return": perf.total_return,
        "total_pnl": perf.total_pnl,
    }


@dataclass(frozen=True)
class ScenarioResult:
    scenario: Scenario
    status: ScenarioStatus
    metrics: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    duration_seconds: float = 0.0

    @property
    def completed(self) -> bool:
        return self.status is ScenarioStatus.COMPLETED

    def metric(self, name: str) -> Any:
        return self.metrics.get(name)

    def to_record(self) -> Dict[str, Any]:
        s = self.scenario
        record: Dict[str, Any] = {
            "scenario_id": s.scenario_id,
            "strategy": s.strategy_name,
            "strategy_params": dict(s.params),
            "brick_type": s.brick.brick_type,
            "brick_size": s.brick.brick_size,
            "timeframe": s.brick.timeframe,
            "symbol": s.symbol,
            "dataset_id": s.dataset_id,
            "date_start": s.date_range[0],
            "date_end": s.date_range[1],
            "exchange": s.market.exchange,
            "market": s.market.market,
            "currency": s.market.currency,
            "status": self.status.value,
            "error": self.error,
        }
        for key in METRIC_KEYS:
            record[key] = self.metrics.get(key)
        return record


class ResultSet:
    def __init__(self, results: Optional[List[ScenarioResult]] = None) -> None:
        self._results: List[ScenarioResult] = list(results or [])

    def add(self, result: ScenarioResult) -> None:
        self._results.append(result)

    def __iter__(self) -> Iterator[ScenarioResult]:
        return iter(self._results)

    def __len__(self) -> int:
        return len(self._results)

    def __getitem__(self, index: int) -> ScenarioResult:
        return self._results[index]

    @property
    def results(self) -> List[ScenarioResult]:
        return list(self._results)

    def completed(self) -> List[ScenarioResult]:
        return [r for r in self._results if r.completed]

    def failed(self) -> List[ScenarioResult]:
        return [r for r in self._results if r.status is ScenarioStatus.FAILED]

    def to_records(self) -> List[Dict[str, Any]]:
        return [r.to_record() for r in self._results]
