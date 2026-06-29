"""Research engine interfaces.

These ports keep Sprint 8 research execution decoupled from concrete data
sources, optimizers, simulators, report renderers, and portfolio allocators.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Sequence

from backend.app.marketdata.models import MarketBar
from backend.app.trading.backtesting.research.models import (
    MonteCarloConfig,
    MonteCarloResult,
    OptimizationResult,
    PortfolioOptimizationMethod,
    PortfolioOptimizationResult,
    ResearchObjective,
    ResearchReport,
    ResearchTask,
    WalkForwardResult,
    WalkForwardWindow,
)
from backend.app.trading.backtesting.research.parameter_space import ParameterSpace
from backend.app.trading.execution.position import Trade
from backend.app.trading.validation.dataset import BrickDataSource, DateRange
from backend.app.trading.validation.scenario import BrickSpec


class HistoricalMarketDataSource(ABC):
    """Port for historical market data replay."""

    @abstractmethod
    def load_bars(self, *, symbol: str, dataset_id: str, date_range: DateRange = (None, None)) -> tuple[MarketBar, ...]:
        """Return normalized bars for a dataset."""
        raise NotImplementedError

    @abstractmethod
    def stream_bars(self, *, symbol: str, dataset_id: str, date_range: DateRange = (None, None)) -> Iterable[MarketBar]:
        """Yield normalized bars for streaming replay."""
        raise NotImplementedError


class ResearchOptimizer(ABC):
    """Port for research optimizers."""

    @abstractmethod
    def optimize(self, task: ResearchTask, parameter_space: ParameterSpace) -> OptimizationResult:
        """Optimize a research task over a parameter space."""
        raise NotImplementedError


class WalkForwardAnalyzer(ABC):
    """Port for walk-forward analysis."""

    @abstractmethod
    def analyze(
        self,
        task: ResearchTask,
        parameter_space: ParameterSpace,
        windows: Sequence[WalkForwardWindow],
    ) -> WalkForwardResult:
        """Run walk-forward analysis."""
        raise NotImplementedError


class MonteCarloSimulator(ABC):
    """Port for Monte Carlo trade-path simulation."""

    @abstractmethod
    def simulate(self, trades: Sequence[Trade], config: MonteCarloConfig) -> MonteCarloResult:
        """Run Monte Carlo simulation over completed trades."""
        raise NotImplementedError


class PortfolioAllocator(ABC):
    """Port for portfolio optimization."""

    @abstractmethod
    def optimize(
        self,
        returns_by_strategy: dict[str, Sequence[float]],
        *,
        method: PortfolioOptimizationMethod,
        capital: float,
    ) -> PortfolioOptimizationResult:
        """Return capital allocations across strategy sleeves."""
        raise NotImplementedError


class ResearchReportRenderer(ABC):
    """Port for research report rendering."""

    @abstractmethod
    def render_json(self, report: ResearchReport) -> str:
        """Render a report as JSON."""
        raise NotImplementedError

    @abstractmethod
    def render_csv(self, report: ResearchReport) -> str:
        """Render a report as CSV."""
        raise NotImplementedError

    @abstractmethod
    def render_markdown(self, report: ResearchReport) -> str:
        """Render a report as Markdown."""
        raise NotImplementedError

    @abstractmethod
    def render_html(self, report: ResearchReport) -> str:
        """Render a report as HTML."""
        raise NotImplementedError


class ResearchRunner(ABC):
    """Top-level research engine port."""

    @abstractmethod
    def optimize(
        self,
        *,
        strategy_names: Sequence[str] | None,
        symbols: Sequence[str],
        dataset_ids: Sequence[str],
        brick_specs: Sequence[BrickSpec],
        parameter_space: ParameterSpace,
        objective: ResearchObjective,
        max_workers: int = 1,
    ) -> OptimizationResult:
        """Run a complete optimization."""
        raise NotImplementedError


__all__ = [
    "BrickDataSource",
    "HistoricalMarketDataSource",
    "MonteCarloSimulator",
    "PortfolioAllocator",
    "ResearchOptimizer",
    "ResearchReportRenderer",
    "ResearchRunner",
    "WalkForwardAnalyzer",
]
