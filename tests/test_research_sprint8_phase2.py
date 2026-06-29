from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.app.chart.renko.models import Brick, BrickDirection
from backend.app.marketdata.models import MarketBar
from backend.app.trading.backtesting.research import (
    GridSearchOptimizer,
    InMemoryHistoricalMarketDataSource,
    InstitutionalMetricsEngine,
    MonteCarloConfig,
    ParameterSpace,
    PortfolioOptimizationMethod,
    PortfolioOptimizer,
    ResearchEngine,
    ResearchObjective,
    ResearchReportRenderer,
    ResearchTask,
    WalkForwardResearchAnalyzer,
    WalkForwardWindow,
)
from backend.app.trading.backtesting.research.models import OptimizationDirection
from backend.app.trading.validation.dataset import InMemoryBrickDataSource
from backend.app.trading.validation.scenario import BrickSpec

TS = datetime(2024, 1, 1, tzinfo=timezone.utc)


def brick(index: int, close: float, direction: BrickDirection = BrickDirection.UP) -> Brick:
    return Brick(
        brick_id=f"b{index}",
        direction=direction,
        open_price=float(close),
        close_price=float(close),
        high_price=float(close),
        low_price=float(close),
        volume=0.0,
        created_at=TS + timedelta(minutes=index),
        metadata={"symbol": "TEST"},
    )


def data_source() -> InMemoryBrickDataSource:
    source = InMemoryBrickDataSource()
    spec = BrickSpec(brick_size=1.0)
    source.register(
        symbol="TEST",
        dataset_id="ds",
        brick=spec,
        bricks=[brick(i, price) for i, price in enumerate([100, 101, 102, 103, 99, 98, 104, 105])],
    )
    source.register(
        symbol="TEST",
        dataset_id="ds",
        brick=BrickSpec(brick_size=2.0),
        bricks=[brick(i, price) for i, price in enumerate([100, 102, 104, 106, 101, 99, 107, 109])],
    )
    return source


def test_parameter_space_expands_deterministically():
    space = ParameterSpace.standard_grid(ema_periods=[3, 5], renko_brick_sizes=[1.0, 2.0], risk_percents=[0.5])
    combos = space.combinations()
    assert len(combos) == 4
    assert combos[0].values["brick_size"] == 1.0
    assert combos[0].values["period"] == 3


def test_grid_optimizer_runs_registered_strategy():
    source = data_source()
    optimizer = GridSearchOptimizer(source)
    task = ResearchTask(
        task_id="t1",
        strategy_names=("ema_trend",),
        symbols=("TEST",),
        dataset_ids=("ds",),
        brick_specs=(BrickSpec(brick_size=1.0),),
        objective=ResearchObjective(metric="net_profit", direction=OptimizationDirection.MAXIMIZE),
    )
    result = optimizer.optimize(task, ParameterSpace.standard_grid(ema_periods=[2, 3]))
    assert len(result.trials) == 2
    assert result.best_result is not None
    assert result.result_set.completed()


def test_research_engine_auto_discovers_strategies_and_builds_report():
    engine = ResearchEngine(data_source())
    result = engine.optimize(
        strategy_names=("ema_trend",),
        symbols=("TEST",),
        dataset_ids=("ds",),
        brick_specs=(BrickSpec(brick_size=1.0),),
        parameter_space=ParameterSpace.standard_grid(ema_periods=[2]),
        objective=ResearchObjective(metric="net_profit"),
    )
    report = engine.build_report(report_id="r1", title="Research", optimization=result)
    renderer = ResearchReportRenderer()
    assert '"report_id": "r1"' in renderer.render_json(report)
    assert "Optimization" in renderer.render_markdown(report)
    assert "scenario_id" in renderer.render_csv(report)
    assert "<html" in renderer.render_html(report)


def test_walk_forward_uses_best_training_parameters():
    source = data_source()
    optimizer = GridSearchOptimizer(source)
    analyzer = WalkForwardResearchAnalyzer(optimizer)
    task = ResearchTask(
        task_id="wf",
        strategy_names=("ema_trend",),
        symbols=("TEST",),
        dataset_ids=("ds",),
        brick_specs=(BrickSpec(brick_size=1.0),),
        objective=ResearchObjective(metric="net_profit"),
    )
    result = analyzer.analyze(
        task,
        ParameterSpace.standard_grid(ema_periods=[2]),
        [WalkForwardWindow(index=0, training_range=(None, None), validation_range=(None, None), forward_range=(None, None))],
    )
    assert result.step_count == 1
    assert result.steps[0].training.best_result is not None


def test_monte_carlo_metrics_and_portfolio_optimizer():
    source = data_source()
    engine = ResearchEngine(source)
    optimized = engine.optimize(
        strategy_names=("ema_trend",),
        symbols=("TEST",),
        dataset_ids=("ds",),
        brick_specs=(BrickSpec(brick_size=1.0),),
        parameter_space=ParameterSpace.standard_grid(ema_periods=[2]),
        objective=ResearchObjective(metric="net_profit"),
    )
    trial = optimized.best_trial
    assert trial is not None
    strategy = engine.registry.create("ema_trend", period=2)
    from backend.app.trading.backtesting.engine import BacktestEngine
    backtest = BacktestEngine(strategy, fixed_quantity=10).run(source.get_bricks(symbol="TEST", dataset_id="ds", brick=BrickSpec(brick_size=1.0)))
    metrics = InstitutionalMetricsEngine().compute(backtest.equity_curve, backtest.trades, starting_capital=100_000)
    assert metrics.max_drawdown_pct >= 0
    mc = engine.simulate_trades(backtest.trades, MonteCarloConfig(iterations=10, seed=7))
    assert len(mc.paths) == 10
    portfolio = PortfolioOptimizer().optimize(
        {"a": [0.01, 0.02, -0.01], "b": [0.005, 0.004, 0.006]},
        method=PortfolioOptimizationMethod.RISK_PARITY,
        capital=100_000,
    )
    assert round(portfolio.total_weight, 10) == 1.0


def test_historical_csv_dataset_support(tmp_path):
    path = tmp_path / "bars.csv"
    path.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2024-01-01T00:00:00+00:00,100,110,90,105,10\n"
        "2024-01-02T00:00:00+00:00,105,111,100,110,20\n",
        encoding="utf-8",
    )
    source = InMemoryHistoricalMarketDataSource()
    dataset = source.load_csv(path, symbol="TEST", dataset_id="bars")
    assert dataset.row_count == 2
    bars = source.load_bars(symbol="TEST", dataset_id="bars")
    assert isinstance(bars[0], MarketBar)
    assert [bar.close for bar in source.stream_bars(symbol="TEST", dataset_id="bars")] == [105.0, 110.0]
