"""Walk-forward analysis for strategy research."""

from __future__ import annotations

from typing import Sequence

from backend.app.trading.backtesting.research.models import (
    ResearchTask,
    WalkForwardResult,
    WalkForwardStepResult,
    WalkForwardWindow,
)
from backend.app.trading.backtesting.research.optimizer import GridSearchOptimizer
from backend.app.trading.backtesting.research.parameter_space import ParameterSpace


class WalkForwardResearchAnalyzer:
    """Training -> validation -> forward-test orchestration."""

    def __init__(self, optimizer: GridSearchOptimizer) -> None:
        self._optimizer = optimizer

    def analyze(
        self,
        task: ResearchTask,
        parameter_space: ParameterSpace,
        windows: Sequence[WalkForwardWindow],
    ) -> WalkForwardResult:
        """Run walk-forward analysis over all supplied windows."""
        if not windows:
            raise ValueError("at least one walk-forward window is required")
        steps: list[WalkForwardStepResult] = []
        forward_scores: list[float] = []
        for window in windows:
            training_task = self._with_date_range(task, window.training_range)
            training = self._optimizer.optimize(training_task, parameter_space)
            best = training.best_trial
            validation = None
            forward = None
            if best is not None:
                best_space = ParameterSpace.single(best.parameters)
                validation = self._optimizer.optimize(self._with_date_range(task, window.validation_range), best_space)
                forward = self._optimizer.optimize(self._with_date_range(task, window.forward_range), best_space)
                if forward.best_trial is not None and forward.best_trial.objective_value is not None:
                    forward_scores.append(float(forward.best_trial.objective_value))
            steps.append(WalkForwardStepResult(window=window, training=training, validation=validation, forward=forward))
        aggregate = {
            "windows": float(len(steps)),
            "forward_mean_objective": sum(forward_scores) / len(forward_scores) if forward_scores else None,
            "forward_completed_windows": float(len(forward_scores)),
        }
        return WalkForwardResult(objective=task.objective, steps=tuple(steps), aggregate_metrics=aggregate)

    @staticmethod
    def _with_date_range(task: ResearchTask, date_range: tuple[str | None, str | None]) -> ResearchTask:
        return ResearchTask(
            task_id=task.task_id,
            strategy_names=task.strategy_names,
            symbols=task.symbols,
            dataset_ids=task.dataset_ids,
            brick_specs=task.brick_specs,
            date_ranges=(date_range,),
            risk_settings=task.risk_settings,
            objective=task.objective,
            max_workers=task.max_workers,
            metadata=task.metadata,
        )


__all__ = ["WalkForwardResearchAnalyzer"]
