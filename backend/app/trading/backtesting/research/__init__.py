"""Sprint 8 Phase 2 institutional research framework."""

from backend.app.trading.backtesting.research.engine import InMemoryHistoricalMarketDataSource, ResearchEngine
from backend.app.trading.backtesting.research.metrics import InstitutionalMetrics, InstitutionalMetricsEngine
from backend.app.trading.backtesting.research.models import (
    DatasetFormat,
    MonteCarloConfig,
    MonteCarloMethod,
    MonteCarloResult,
    OptimizationDirection,
    OptimizationResult,
    PortfolioAllocation,
    PortfolioOptimizationMethod,
    PortfolioOptimizationResult,
    ResearchDataset,
    ResearchObjective,
    ResearchReport,
    ResearchTask,
    ResearchTrial,
    WalkForwardResult,
    WalkForwardStepResult,
    WalkForwardWindow,
)
from backend.app.trading.backtesting.research.monte_carlo import TradeMonteCarloSimulator
from backend.app.trading.backtesting.research.optimizer import GridSearchOptimizer, infer_objective
from backend.app.trading.backtesting.research.parameter_space import ParameterAxis, ParameterSet, ParameterSpace
from backend.app.trading.backtesting.research.portfolio_optimizer import PortfolioOptimizer
from backend.app.trading.backtesting.research.reports import ResearchReportRenderer
from backend.app.trading.backtesting.research.walk_forward import WalkForwardResearchAnalyzer

__all__ = [
    "DatasetFormat",
    "GridSearchOptimizer",
    "InMemoryHistoricalMarketDataSource",
    "InstitutionalMetrics",
    "InstitutionalMetricsEngine",
    "MonteCarloConfig",
    "MonteCarloMethod",
    "MonteCarloResult",
    "OptimizationDirection",
    "OptimizationResult",
    "ParameterAxis",
    "ParameterSet",
    "ParameterSpace",
    "PortfolioAllocation",
    "PortfolioOptimizationMethod",
    "PortfolioOptimizationResult",
    "PortfolioOptimizer",
    "ResearchDataset",
    "ResearchEngine",
    "ResearchObjective",
    "ResearchReport",
    "ResearchReportRenderer",
    "ResearchTask",
    "ResearchTrial",
    "TradeMonteCarloSimulator",
    "WalkForwardResearchAnalyzer",
    "WalkForwardResult",
    "WalkForwardStepResult",
    "WalkForwardWindow",
    "infer_objective",
]
