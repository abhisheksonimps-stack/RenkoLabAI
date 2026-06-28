"""ValidationRunner — runs every scenario through the frozen BacktestEngine.

Strict isolation: each scenario gets a fresh strategy (via the frozen
StrategyFactory), a fresh data slice (from a BrickDataSource), and a fresh engine.
``_run_one`` is a pure function of its scenario, so a future parallel mode can map
it across workers with no redesign. Failures are captured per scenario and never
abort the batch.
"""

from __future__ import annotations

import time
from typing import Callable, Iterable, Optional

from backend.app.trading.backtesting.engine import BacktestEngine
from backend.app.trading.costs.brokerage import (
    BrokerageModel,
    FixedBrokerage,
    PercentageBrokerage,
    PerShareBrokerage,
    ZeroBrokerage,
)
from backend.app.trading.costs.slippage import (
    FixedSlippage,
    PercentageSlippage,
    SlippageModel,
    ZeroSlippage,
)
from backend.app.trading.execution.position import TradeAttribution
from backend.app.trading.strategy.factory import StrategyFactory
from backend.app.trading.validation.dataset import BrickDataSource
from backend.app.trading.validation.results import (
    ResultSet,
    ScenarioResult,
    metrics_from_performance,
)
from backend.app.trading.validation.scenario import RiskSettings, Scenario, ScenarioStatus


def _build_brokerage(risk: RiskSettings) -> BrokerageModel:
    kind = risk.brokerage
    if kind == "fixed":
        return FixedBrokerage(risk.brokerage_value)
    if kind == "percentage":
        return PercentageBrokerage(risk.brokerage_value)
    if kind == "per_share":
        return PerShareBrokerage(risk.brokerage_value)
    return ZeroBrokerage()


def _build_slippage(risk: RiskSettings) -> SlippageModel:
    kind = risk.slippage
    if kind == "fixed":
        return FixedSlippage(risk.slippage_value)
    if kind == "percentage":
        return PercentageSlippage(risk.slippage_value)
    return ZeroSlippage()


class ValidationRunner:
    def __init__(
        self,
        data_source: BrickDataSource,
        strategy_factory: Optional[StrategyFactory] = None,
        mapper: Callable = map,
    ) -> None:
        self._data_source = data_source
        self._strategy_factory = strategy_factory or StrategyFactory()
        # ``mapper`` is the parallelism seam: builtin map (sequential) by default;
        # an executor's map can be supplied later without changing _run_one.
        self._mapper = mapper

    def run(self, scenarios: Iterable[Scenario]) -> ResultSet:
        results = list(self._mapper(self._run_one, list(scenarios)))
        return ResultSet(results)

    def _run_one(self, scenario: Scenario) -> ScenarioResult:
        start = time.perf_counter()
        try:
            strategy = self._strategy_factory.create(scenario.strategy_name, **scenario.params)
            bricks = self._data_source.get_bricks(
                symbol=scenario.symbol,
                dataset_id=scenario.dataset_id,
                brick=scenario.brick,
                date_range=scenario.date_range,
            )
            attribution = TradeAttribution(
                symbol=scenario.symbol,
                strategy_name=scenario.strategy_name,
                brick_type=scenario.brick.brick_type,
                brick_size=scenario.brick.brick_size,
                timeframe=scenario.brick.timeframe,
            )
            risk = scenario.risk
            engine = BacktestEngine(
                strategy,
                starting_capital=risk.starting_capital,
                attribution=attribution,
                slippage=_build_slippage(risk),
                brokerage=_build_brokerage(risk),
                position_fraction=risk.position_fraction,
                fixed_quantity=risk.fixed_quantity,
                leverage=risk.leverage,
                force_close=True,
            )
            result = engine.run(bricks)
            metrics = metrics_from_performance(result.metrics)
            duration = time.perf_counter() - start
            return ScenarioResult(scenario, ScenarioStatus.COMPLETED, metrics, None, duration)
        except Exception as exc:  # capture, never abort the batch
            duration = time.perf_counter() - start
            return ScenarioResult(scenario, ScenarioStatus.FAILED, {}, str(exc), duration)
