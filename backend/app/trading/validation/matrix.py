"""ValidationMatrix — expands declared axes into a deterministic, deduplicated
list of Scenarios (the only place combinations are built).

Axes: strategy(+param grid) x brick spec x symbol x dataset x date range x risk
x market. Adding an axis is additive and never touches the runner.
"""

from __future__ import annotations

import itertools
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from backend.app.trading.validation.scenario import (
    BrickSpec,
    MarketInfo,
    RiskSettings,
    Scenario,
)


def _expand_param_grid(grid: Mapping[str, List[Any]]) -> List[Dict[str, Any]]:
    if not grid:
        return [{}]
    keys = sorted(grid)
    value_lists = [list(grid[k]) for k in keys]
    return [dict(zip(keys, combo)) for combo in itertools.product(*value_lists)]


class ValidationMatrix:
    def __init__(self) -> None:
        self._strategies: List[Tuple[str, Dict[str, List[Any]]]] = []
        self._bricks: List[BrickSpec] = []
        self._symbols: List[str] = []
        self._datasets: List[str] = []
        self._date_ranges: List[Tuple[Optional[str], Optional[str]]] = [(None, None)]
        self._risks: List[RiskSettings] = [RiskSettings()]
        self._markets: List[MarketInfo] = [MarketInfo()]
        self._filter: Optional[Callable[[Scenario], bool]] = None

    # -- fluent axis declaration ---------------------------------------------
    def add_strategy(self, name: str, **param_grid: List[Any]) -> "ValidationMatrix":
        self._strategies.append((name, dict(param_grid)))
        return self

    def with_bricks(self, *bricks: BrickSpec) -> "ValidationMatrix":
        self._bricks = list(bricks)
        return self

    def with_symbols(self, *symbols: str) -> "ValidationMatrix":
        self._symbols = list(symbols)
        return self

    def with_datasets(self, *dataset_ids: str) -> "ValidationMatrix":
        self._datasets = list(dataset_ids)
        return self

    def with_date_ranges(self, *ranges: Tuple[Optional[str], Optional[str]]) -> "ValidationMatrix":
        self._date_ranges = list(ranges) if ranges else [(None, None)]
        return self

    def with_risk(self, *risks: RiskSettings) -> "ValidationMatrix":
        self._risks = list(risks) if risks else [RiskSettings()]
        return self

    def with_markets(self, *markets: MarketInfo) -> "ValidationMatrix":
        self._markets = list(markets) if markets else [MarketInfo()]
        return self

    def filter(self, predicate: Callable[[Scenario], bool]) -> "ValidationMatrix":
        self._filter = predicate
        return self

    # -- expansion ------------------------------------------------------------
    def scenarios(self) -> List[Scenario]:
        strategy_combos: List[Tuple[str, Dict[str, Any]]] = [
            (name, params)
            for name, grid in self._strategies
            for params in _expand_param_grid(grid)
        ]
        axes = itertools.product(
            strategy_combos, self._bricks, self._symbols, self._datasets,
            self._date_ranges, self._risks, self._markets,
        )
        out: List[Scenario] = []
        seen: set[str] = set()
        for (name, params), brick, symbol, dataset, date_range, risk, market in axes:
            scenario = Scenario.create(
                name, params, brick=brick, symbol=symbol, dataset_id=dataset,
                date_range=date_range, risk=risk, market=market,
            )
            if self._filter is not None and not self._filter(scenario):
                continue
            if scenario.scenario_id in seen:
                continue
            seen.add(scenario.scenario_id)
            out.append(scenario)
        return out

    def count(self) -> int:
        return len(self.scenarios())
