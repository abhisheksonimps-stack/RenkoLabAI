"""Institutional quantitative research engine.

The engine composes existing strategy registry, validation scenarios, brick data
sources, backtesting engine, Sprint 7 analytics facade, and Sprint 8 research
components into one repository-native research platform.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable, Sequence

from backend.app.analytics.engine import AnalyticsEngine
from backend.app.marketdata.models import MarketBar
from backend.app.trading.backtesting.research.models import (
    DatasetFormat,
    MonteCarloConfig,
    MonteCarloResult,
    OptimizationResult,
    PortfolioOptimizationMethod,
    PortfolioOptimizationResult,
    ResearchDataset,
    ResearchObjective,
    ResearchReport,
    ResearchTask,
    WalkForwardResult,
    WalkForwardWindow,
)
from backend.app.trading.backtesting.research.monte_carlo import TradeMonteCarloSimulator
from backend.app.trading.backtesting.research.optimizer import GridSearchOptimizer
from backend.app.trading.backtesting.research.parameter_space import ParameterSpace
from backend.app.trading.backtesting.research.portfolio_optimizer import PortfolioOptimizer
from backend.app.trading.backtesting.research.reports import ResearchReportRenderer
from backend.app.trading.backtesting.research.walk_forward import WalkForwardResearchAnalyzer
from backend.app.trading.execution.position import Trade
from backend.app.trading.strategy.registry import StrategyRegistry, default_strategy_registry
from backend.app.trading.validation.dataset import BrickDataSource, DateRange
from backend.app.trading.validation.scenario import BrickSpec, RiskSettings


class InMemoryHistoricalMarketDataSource:
    """Repository-native in-memory historical market-data source."""

    def __init__(self) -> None:
        self._bars: dict[tuple[str, str], tuple[MarketBar, ...]] = {}

    def register(self, *, symbol: str, dataset_id: str, bars: Sequence[MarketBar]) -> ResearchDataset:
        """Register normalized bars under a symbol/dataset key."""
        key = (symbol.strip().upper(), dataset_id.strip())
        normalized = tuple(sorted(bars, key=lambda bar: bar.timestamp))
        self._bars[key] = normalized
        return ResearchDataset(dataset_id=dataset_id, symbol=symbol, row_count=len(normalized))

    def load_bars(self, *, symbol: str, dataset_id: str, date_range: DateRange = (None, None)) -> tuple[MarketBar, ...]:
        """Return registered bars filtered by optional ISO date range."""
        key = (symbol.strip().upper(), dataset_id.strip())
        if key not in self._bars:
            raise KeyError(f"No bars registered for {key}")
        start, end = date_range
        bars = self._bars[key]
        if start is None and end is None:
            return bars
        return tuple(
            bar
            for bar in bars
            if (start is None or bar.timestamp.isoformat() >= start)
            and (end is None or bar.timestamp.isoformat() <= end)
        )

    def stream_bars(self, *, symbol: str, dataset_id: str, date_range: DateRange = (None, None)) -> Iterable[MarketBar]:
        """Yield registered bars in timestamp order."""
        yield from self.load_bars(symbol=symbol, dataset_id=dataset_id, date_range=date_range)

    def load_csv(self, path: str | Path, *, symbol: str, dataset_id: str, interval: str = "1d") -> ResearchDataset:
        """Load OHLCV bars from CSV with timestamp/open/high/low/close/volume columns."""
        file_path = Path(path)
        bars: list[MarketBar] = []
        with file_path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                bars.append(
                    MarketBar.create(
                        symbol=symbol,
                        timestamp=row["timestamp"],
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row.get("volume") or 0.0),
                        interval=interval,
                        source="csv",
                    )
                )
        dataset = self.register(symbol=symbol, dataset_id=dataset_id, bars=bars)
        return ResearchDataset(
            dataset_id=dataset.dataset_id,
            symbol=dataset.symbol,
            format=DatasetFormat.CSV,
            source=str(file_path),
            row_count=dataset.row_count,
        )

    def load_parquet(self, path: str | Path, *, symbol: str, dataset_id: str, interval: str = "1d") -> ResearchDataset:
        """Load OHLCV bars from Parquet using pandas when available."""
        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError("Parquet dataset support requires pandas") from exc
        file_path = Path(path)
        frame = pd.read_parquet(file_path)
        bars = [
            MarketBar.create(
                symbol=symbol,
                timestamp=row["timestamp"],
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"] if "volume" in row else 0.0),
                interval=interval,
                source="parquet",
            )
            for _, row in frame.iterrows()
        ]
        dataset = self.register(symbol=symbol, dataset_id=dataset_id, bars=bars)
        return ResearchDataset(
            dataset_id=dataset.dataset_id,
            symbol=dataset.symbol,
            format=DatasetFormat.PARQUET,
            source=str(file_path),
            row_count=dataset.row_count,
        )


class ResearchEngine:
    """Facade for Sprint 8 Phase 2 institutional research workflows."""

    def __init__(
        self,
        brick_data_source: BrickDataSource,
        *,
        registry: StrategyRegistry | None = None,
        analytics_engine: AnalyticsEngine | None = None,
    ) -> None:
        self.registry = registry or default_strategy_registry()
        self.optimizer = GridSearchOptimizer(brick_data_source, registry=self.registry)
        self.walk_forward_analyzer = WalkForwardResearchAnalyzer(self.optimizer)
        self.monte_carlo = TradeMonteCarloSimulator()
        self.portfolio_optimizer = PortfolioOptimizer()
        self.report_renderer = ResearchReportRenderer()
        self.historical_data = InMemoryHistoricalMarketDataSource()
        self.analytics_engine = analytics_engine or AnalyticsEngine()

    def optimize(
        self,
        *,
        strategy_names: Sequence[str] | None,
        symbols: Sequence[str],
        dataset_ids: Sequence[str],
        brick_specs: Sequence[BrickSpec],
        parameter_space: ParameterSpace,
        objective: ResearchObjective,
        risk_settings: Sequence[RiskSettings] = (RiskSettings(),),
        date_ranges: Sequence[DateRange] = ((None, None),),
        max_workers: int = 1,
        task_id: str = "research",
    ) -> OptimizationResult:
        """Run grid-search optimization across strategies, symbols, and parameters."""
        names = tuple(strategy_names) if strategy_names is not None else tuple(self.registry.names())
        task = ResearchTask(
            task_id=task_id,
            strategy_names=names,
            symbols=tuple(symbols),
            dataset_ids=tuple(dataset_ids),
            brick_specs=tuple(brick_specs),
            date_ranges=tuple(date_ranges),
            risk_settings=tuple(risk_settings),
            objective=objective,
            max_workers=max_workers,
        )
        return self.optimizer.optimize(task, parameter_space)

    def walk_forward(
        self,
        task: ResearchTask,
        parameter_space: ParameterSpace,
        windows: Sequence[WalkForwardWindow],
    ) -> WalkForwardResult:
        """Run walk-forward analysis."""
        return self.walk_forward_analyzer.analyze(task, parameter_space, windows)

    def simulate_trades(self, trades: Sequence[Trade], config: MonteCarloConfig) -> MonteCarloResult:
        """Run Monte Carlo simulation over completed trades."""
        return self.monte_carlo.simulate(trades, config)

    def optimize_portfolio(
        self,
        returns_by_strategy: dict[str, Sequence[float]],
        *,
        method: PortfolioOptimizationMethod = PortfolioOptimizationMethod.RISK_PARITY,
        capital: float = 100_000.0,
    ) -> PortfolioOptimizationResult:
        """Run multi-strategy portfolio optimization."""
        return self.portfolio_optimizer.optimize(returns_by_strategy, method=method, capital=capital)

    def build_report(
        self,
        *,
        report_id: str,
        title: str,
        optimization: OptimizationResult | None = None,
        walk_forward: WalkForwardResult | None = None,
        monte_carlo: MonteCarloResult | None = None,
        portfolio: PortfolioOptimizationResult | None = None,
    ) -> ResearchReport:
        """Build an interactive-ready research report DTO."""
        return ResearchReport(
            report_id=report_id,
            title=title,
            generated_at=datetime.now(UTC),
            optimization=optimization,
            walk_forward=walk_forward,
            monte_carlo=monte_carlo,
            portfolio=portfolio,
        )


__all__ = ["InMemoryHistoricalMarketDataSource", "ResearchEngine"]
