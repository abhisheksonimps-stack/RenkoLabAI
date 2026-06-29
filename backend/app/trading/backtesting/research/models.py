"""Research engine models.

Sprint 8 Phase 2 models are immutable Pydantic v2 value objects that describe
research tasks, optimization outputs, walk-forward splits, Monte Carlo results,
and portfolio allocation outputs. Runtime execution still reuses existing
validation ``Scenario`` / ``ScenarioResult`` and backtesting ``BacktestResult``
objects; these models only add the research boundary around them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Mapping, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.trading.validation.results import ResultSet, ScenarioResult
from backend.app.trading.validation.scenario import BrickSpec, RiskSettings, Scenario

ResearchScalar: TypeAlias = str | int | float | bool | None
ParameterMapping: TypeAlias = Mapping[str, ResearchScalar]
MetricMapping: TypeAlias = Mapping[str, float | int | None]
DateRange: TypeAlias = tuple[str | None, str | None]


class ResearchModel(BaseModel):
    """Base immutable model for research DTOs."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True, extra="forbid")


class ResearchStatus(str, Enum):
    """Research execution status."""

    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class OptimizationDirection(str, Enum):
    """Optimization objective direction."""

    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


class PortfolioOptimizationMethod(str, Enum):
    """Supported portfolio allocation methods."""

    EQUAL_WEIGHT = "equal_weight"
    RISK_PARITY = "risk_parity"
    MAXIMUM_SHARPE = "maximum_sharpe"
    MINIMUM_VARIANCE = "minimum_variance"


class MonteCarloMethod(str, Enum):
    """Supported Monte Carlo sampling modes."""

    RANDOM_TRADE_ORDER = "random_trade_order"
    BOOTSTRAP = "bootstrap"


class DatasetFormat(str, Enum):
    """Historical dataset file formats."""

    CSV = "csv"
    PARQUET = "parquet"


class ResearchObjective(ResearchModel):
    """Metric objective used by optimizers and rankings."""

    metric: str = Field(min_length=1)
    direction: OptimizationDirection = OptimizationDirection.MAXIMIZE

    @field_validator("metric")
    @classmethod
    def _normalize_metric(cls, value: str) -> str:
        metric = value.strip()
        if not metric:
            raise ValueError("objective metric cannot be blank")
        return metric

    def score(self, metrics: Mapping[str, object]) -> float | None:
        """Return the sortable score for a metrics mapping."""
        raw = metrics.get(self.metric)
        if raw is None or isinstance(raw, bool):
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None


class ResearchDataset(ResearchModel):
    """Research dataset reference."""

    dataset_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    format: DatasetFormat | None = None
    source: str | None = None
    row_count: int = 0
    metadata: Mapping[str, ResearchScalar] = Field(default_factory=dict)

    @field_validator("dataset_id", "symbol")
    @classmethod
    def _normalize_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("dataset identifiers cannot be blank")
        return text

    @field_validator("row_count")
    @classmethod
    def _validate_row_count(cls, value: int) -> int:
        if value < 0:
            raise ValueError("row_count cannot be negative")
        return value


class ResearchTask(ResearchModel):
    """Complete immutable request for a strategy research run."""

    task_id: str = Field(min_length=1)
    strategy_names: tuple[str, ...] = Field(default_factory=tuple)
    symbols: tuple[str, ...] = Field(default_factory=tuple)
    dataset_ids: tuple[str, ...] = Field(default_factory=tuple)
    brick_specs: tuple[BrickSpec, ...] = Field(default_factory=lambda: (BrickSpec(),))
    date_ranges: tuple[DateRange, ...] = Field(default_factory=lambda: ((None, None),))
    risk_settings: tuple[RiskSettings, ...] = Field(default_factory=lambda: (RiskSettings(),))
    objective: ResearchObjective = Field(default_factory=lambda: ResearchObjective(metric="net_profit"))
    max_workers: int = 1
    metadata: Mapping[str, ResearchScalar] = Field(default_factory=dict)

    @field_validator("task_id")
    @classmethod
    def _normalize_task_id(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("task_id cannot be blank")
        return text

    @field_validator("strategy_names", "symbols", "dataset_ids", mode="before")
    @classmethod
    def _normalize_text_tuple(cls, value: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
        if value is None:
            return ()
        return tuple(str(item).strip() for item in value if str(item).strip())

    @field_validator("max_workers")
    @classmethod
    def _validate_workers(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_workers must be at least 1")
        return value

    @model_validator(mode="after")
    def _validate_axes(self) -> "ResearchTask":
        if not self.strategy_names:
            raise ValueError("at least one strategy name is required")
        if not self.symbols:
            raise ValueError("at least one symbol is required")
        if not self.dataset_ids:
            raise ValueError("at least one dataset_id is required")
        if not self.brick_specs:
            raise ValueError("at least one brick spec is required")
        if not self.date_ranges:
            raise ValueError("at least one date range is required")
        if not self.risk_settings:
            raise ValueError("at least one risk setting is required")
        return self


class ResearchTrial(ResearchModel):
    """One completed research scenario with its full parameter set."""

    scenario: Scenario
    result: ScenarioResult
    parameters: Mapping[str, ResearchScalar] = Field(default_factory=dict)
    objective_value: float | None = None

    @property
    def completed(self) -> bool:
        """Return whether the underlying scenario completed successfully."""
        return self.result.completed


class OptimizationResult(ResearchModel):
    """Result of a deterministic grid optimization."""

    objective: ResearchObjective
    trials: tuple[ResearchTrial, ...] = Field(default_factory=tuple)
    result_set: ResultSet
    started_at: datetime
    completed_at: datetime

    @property
    def best_trial(self) -> ResearchTrial | None:
        """Return the best completed trial according to objective direction."""
        scored = [trial for trial in self.trials if trial.completed and trial.objective_value is not None]
        if not scored:
            return None
        reverse = self.objective.direction is OptimizationDirection.MAXIMIZE
        return sorted(scored, key=lambda trial: float(trial.objective_value), reverse=reverse)[0]

    @property
    def best_result(self) -> ScenarioResult | None:
        """Return the best ScenarioResult when available."""
        best = self.best_trial
        return None if best is None else best.result

    @property
    def duration_seconds(self) -> float:
        """Return wall-clock duration for the optimization."""
        return (self.completed_at - self.started_at).total_seconds()


class WalkForwardWindow(ResearchModel):
    """One walk-forward split."""

    index: int = Field(ge=0)
    training_range: DateRange
    validation_range: DateRange
    forward_range: DateRange


class WalkForwardStepResult(ResearchModel):
    """Result for one walk-forward split."""

    window: WalkForwardWindow
    training: OptimizationResult
    validation: OptimizationResult | None = None
    forward: OptimizationResult | None = None


class WalkForwardResult(ResearchModel):
    """Aggregated walk-forward analysis output."""

    objective: ResearchObjective
    steps: tuple[WalkForwardStepResult, ...]
    aggregate_metrics: Mapping[str, float | int | None] = Field(default_factory=dict)

    @property
    def step_count(self) -> int:
        """Return number of evaluated walk-forward windows."""
        return len(self.steps)


class MonteCarloConfig(ResearchModel):
    """Monte Carlo simulation configuration."""

    iterations: int = 1000
    method: MonteCarloMethod = MonteCarloMethod.RANDOM_TRADE_ORDER
    seed: int = 42
    starting_equity: float = 100_000.0
    ruin_threshold: float = 0.7
    confidence_levels: tuple[float, ...] = (0.05, 0.5, 0.95)

    @field_validator("iterations")
    @classmethod
    def _validate_iterations(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("iterations must be positive")
        return value

    @model_validator(mode="after")
    def _validate_thresholds(self) -> "MonteCarloConfig":
        if self.starting_equity <= 0:
            raise ValueError("starting_equity must be positive")
        if not 0 < self.ruin_threshold < 1:
            raise ValueError("ruin_threshold must be between 0 and 1")
        if any(level <= 0 or level >= 1 for level in self.confidence_levels):
            raise ValueError("confidence levels must be between 0 and 1")
        return self


class MonteCarloPath(ResearchModel):
    """One simulated equity path summary."""

    index: int
    ending_equity: float
    max_drawdown: float
    max_drawdown_pct: float
    ruined: bool


class MonteCarloResult(ResearchModel):
    """Monte Carlo simulation summary."""

    config: MonteCarloConfig
    paths: tuple[MonteCarloPath, ...]
    confidence_intervals: Mapping[str, float]
    probability_of_ruin: float
    drawdown_distribution: tuple[float, ...]


class PortfolioAllocation(ResearchModel):
    """Capital allocation for one strategy sleeve."""

    name: str = Field(min_length=1)
    weight: float
    capital: float

    @field_validator("weight")
    @classmethod
    def _validate_weight(cls, value: float) -> float:
        if value < 0:
            raise ValueError("allocation weight cannot be negative")
        return value


class PortfolioOptimizationResult(ResearchModel):
    """Portfolio optimizer output."""

    method: PortfolioOptimizationMethod
    allocations: tuple[PortfolioAllocation, ...]
    expected_return: float
    expected_volatility: float
    expected_sharpe: float
    correlation_matrix: Mapping[str, Mapping[str, float]]

    @property
    def total_weight(self) -> float:
        """Return total allocation weight."""
        return sum(item.weight for item in self.allocations)


class ResearchReport(ResearchModel):
    """Interactive-ready research report DTO."""

    report_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    optimization: OptimizationResult | None = None
    walk_forward: WalkForwardResult | None = None
    monte_carlo: MonteCarloResult | None = None
    portfolio: PortfolioOptimizationResult | None = None
    metadata: Mapping[str, ResearchScalar] = Field(default_factory=dict)


__all__ = [
    "DatasetFormat",
    "DateRange",
    "MetricMapping",
    "MonteCarloConfig",
    "MonteCarloMethod",
    "MonteCarloPath",
    "MonteCarloResult",
    "OptimizationDirection",
    "OptimizationResult",
    "ParameterMapping",
    "PortfolioAllocation",
    "PortfolioOptimizationMethod",
    "PortfolioOptimizationResult",
    "ResearchDataset",
    "ResearchModel",
    "ResearchObjective",
    "ResearchReport",
    "ResearchScalar",
    "ResearchStatus",
    "ResearchTask",
    "ResearchTrial",
    "WalkForwardResult",
    "WalkForwardStepResult",
    "WalkForwardWindow",
]
