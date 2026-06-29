"""Deterministic grid-search optimizer for strategy research."""

from __future__ import annotations

import inspect
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Callable, Iterable, Sequence

from backend.app.trading.backtesting.engine import BacktestEngine
from backend.app.trading.backtesting.research.models import (
    OptimizationDirection,
    OptimizationResult,
    ResearchObjective,
    ResearchTask,
    ResearchTrial,
)
from backend.app.trading.backtesting.research.parameter_space import ParameterSet, ParameterSpace, coerce_float
from backend.app.trading.strategy.factory import StrategyFactory
from backend.app.trading.strategy.registry import StrategyRegistry, default_strategy_registry
from backend.app.trading.strategy.risk import RiskManager, RiskRule, StopLossRule, TakeProfitRule, TrailingStopRule, MaxOpenPositionsRule
from backend.app.trading.validation.dataset import BrickDataSource
from backend.app.trading.validation.results import ResultSet, ScenarioResult, metrics_from_performance
from backend.app.trading.validation.scenario import BrickSpec, RiskSettings, Scenario, ScenarioStatus
from backend.app.trading.execution.position import TradeAttribution


def _accepted_kwargs(factory: StrategyFactory, strategy_name: str, parameters: ParameterSet) -> dict[str, object]:
    """Return constructor kwargs accepted by the registered strategy class."""
    registry = factory.registry
    classes = registry.classes()
    strategy_cls = classes.get(strategy_name)
    strategy_values = parameters.strategy_values
    if strategy_cls is None:
        return dict(strategy_values)
    signature = inspect.signature(strategy_cls.__init__)
    if any(param.kind is inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
        return dict(strategy_values)
    accepted = {
        name
        for name, param in signature.parameters.items()
        if name != "self" and param.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    return {key: value for key, value in strategy_values.items() if key in accepted}


def _with_parameter_overrides(brick: BrickSpec, risk: RiskSettings, parameters: ParameterSet) -> tuple[BrickSpec, RiskSettings]:
    infra = parameters.infrastructure_values
    brick_size = coerce_float(infra.get("brick_size"), brick.brick_size)
    brick_type = str(infra.get("brick_type") or brick.brick_type)
    timeframe = str(infra.get("timeframe") or brick.timeframe)
    position_fraction = coerce_float(infra.get("position_fraction"), risk.position_fraction)
    risk_percent = coerce_float(infra.get("risk_percent"), None)
    fixed_quantity = coerce_float(infra.get("fixed_quantity"), risk.fixed_quantity)
    leverage = coerce_float(infra.get("leverage"), risk.leverage)
    return (
        BrickSpec(brick_type=brick_type, brick_size=float(brick_size or brick.brick_size), timeframe=timeframe),
        RiskSettings(
            starting_capital=risk.starting_capital,
            position_fraction=float(risk_percent if risk_percent is not None else position_fraction),
            fixed_quantity=fixed_quantity,
            leverage=float(leverage or risk.leverage),
            brokerage=risk.brokerage,
            brokerage_value=risk.brokerage_value,
            slippage=risk.slippage,
            slippage_value=risk.slippage_value,
        ),
    )


def _risk_manager_from_parameters(parameters: ParameterSet) -> RiskManager:
    infra = parameters.infrastructure_values
    rules: list[RiskRule] = []
    stop_loss = coerce_float(infra.get("stop_loss"), None)
    take_profit = coerce_float(infra.get("take_profit"), None)
    trailing_stop = coerce_float(infra.get("trailing_stop"), None)
    trailing_stop_percent = coerce_float(infra.get("trailing_stop_percent"), None)
    max_open_positions = coerce_float(infra.get("max_open_positions"), None)
    if stop_loss is not None and stop_loss > 0:
        rules.append(StopLossRule(stop_price=stop_loss))
    if take_profit is not None and take_profit > 0:
        rules.append(TakeProfitRule(take_profit_price=take_profit))
    if trailing_stop is not None and trailing_stop > 0:
        rules.append(TrailingStopRule(trail_amount=trailing_stop))
    elif trailing_stop_percent is not None and 0 < trailing_stop_percent < 1:
        rules.append(TrailingStopRule(trail_percent=trailing_stop_percent))
    if max_open_positions is not None and max_open_positions >= 0:
        rules.append(MaxOpenPositionsRule(max_open_positions=int(max_open_positions)))
    return RiskManager(rules)


class GridSearchOptimizer:
    """Parallel deterministic grid-search optimizer."""

    def __init__(
        self,
        data_source: BrickDataSource,
        *,
        strategy_factory: StrategyFactory | None = None,
        registry: StrategyRegistry | None = None,
    ) -> None:
        resolved_registry = registry or default_strategy_registry()
        self._strategy_factory = strategy_factory or StrategyFactory(resolved_registry)
        self._data_source = data_source

    def optimize(self, task: ResearchTask, parameter_space: ParameterSpace) -> OptimizationResult:
        """Optimize all scenario/parameter combinations for a research task."""
        started = datetime.now(UTC)
        trials = self._build_trials(task, parameter_space)
        if task.max_workers <= 1 or len(trials) <= 1:
            results = [self._run_trial(item) for item in trials]
        else:
            with ThreadPoolExecutor(max_workers=task.max_workers) as executor:
                results = list(executor.map(self._run_trial, trials))
        completed = datetime.now(UTC)
        return OptimizationResult(
            objective=task.objective,
            trials=tuple(results),
            result_set=ResultSet([trial.result for trial in results]),
            started_at=started,
            completed_at=completed,
        )

    def _build_trials(self, task: ResearchTask, parameter_space: ParameterSpace) -> list[tuple[Scenario, ParameterSet, ResearchObjective]]:
        combinations = parameter_space.combinations()
        trials: list[tuple[Scenario, ParameterSet, ResearchObjective]] = []
        seen: set[tuple[str, tuple[tuple[str, object], ...]]] = set()
        for strategy_name in task.strategy_names:
            for symbol in task.symbols:
                for dataset_id in task.dataset_ids:
                    for base_brick in task.brick_specs:
                        for date_range in task.date_ranges:
                            for base_risk in task.risk_settings:
                                for parameters in combinations:
                                    brick, risk = _with_parameter_overrides(base_brick, base_risk, parameters)
                                    strategy_kwargs = _accepted_kwargs(self._strategy_factory, strategy_name, parameters)
                                    scenario = Scenario.create(
                                        strategy_name=strategy_name,
                                        strategy_params=strategy_kwargs,
                                        brick=brick,
                                        symbol=symbol,
                                        dataset_id=dataset_id,
                                        date_range=date_range,
                                        risk=risk,
                                    )
                                    key = (scenario.scenario_id, tuple(sorted(parameters.values.items())))
                                    if key in seen:
                                        continue
                                    seen.add(key)
                                    trials.append((scenario, parameters, task.objective))
        return trials

    def _run_trial(self, trial: tuple[Scenario, ParameterSet, ResearchObjective]) -> ResearchTrial:
        scenario, parameters, objective = trial
        started = datetime.now(UTC)
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
            engine = BacktestEngine(
                strategy,
                starting_capital=scenario.risk.starting_capital,
                attribution=attribution,
                position_fraction=scenario.risk.position_fraction,
                fixed_quantity=scenario.risk.fixed_quantity,
                leverage=scenario.risk.leverage,
                force_close=True,
                risk_manager=_risk_manager_from_parameters(parameters),
            )
            result = engine.run(bricks)
            metrics = metrics_from_performance(result.metrics)
            duration = (datetime.now(UTC) - started).total_seconds()
            scenario_result = ScenarioResult(scenario, ScenarioStatus.COMPLETED, metrics, None, duration)
        except Exception as exc:
            duration = (datetime.now(UTC) - started).total_seconds()
            scenario_result = ScenarioResult(scenario, ScenarioStatus.FAILED, {}, str(exc), duration)
        score = objective.score(scenario_result.metrics)
        return ResearchTrial(
            scenario=scenario,
            result=scenario_result,
            parameters=parameters.values,
            objective_value=score,
        )


def infer_objective(metric: str) -> ResearchObjective:
    """Return default objective direction for a metric name."""
    lower_is_better = {"max_drawdown", "max_drawdown_pct", "var", "cvar", "volatility"}
    direction = OptimizationDirection.MINIMIZE if metric in lower_is_better else OptimizationDirection.MAXIMIZE
    return ResearchObjective(metric=metric, direction=direction)


__all__ = ["GridSearchOptimizer", "infer_objective"]
