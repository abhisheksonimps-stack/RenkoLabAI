# Trading System T3 — Strategy Validation & Batch Backtesting (new package)

Built on the frozen Renko, Strategy, and Backtesting layers. NOTHING under
backend/app/chart/renko/, backend/app/trading/strategy/, or
backend/app/trading/backtesting/ is modified. Research only: it enumerates,
evaluates, ranks, and reports — no optimization, no ML, no search/feedback.

## New files (backend/app/trading/validation/)
scenario.py  # Scenario (immutable, scenario_id), BrickSpec, RiskSettings, MarketInfo
             #   (MarketInfo carries exchange/market/currency for multi-market)
dataset.py   # BrickDataSource ABC + InMemoryBrickDataSource + CachingBrickDataSource
matrix.py    # ValidationMatrix: axes -> Cartesian product of Scenarios (+filter, dedup)
runner.py    # ValidationRunner: _run_one(scenario) reuses the frozen BacktestEngine;
             #   sequential map with a parallel seam; per-scenario failure capture
results.py   # ScenarioResult + ResultSet; normalizes frozen PerformanceMetrics
ranking.py   # rank_by (single metric, direction-aware) + composite_score (weighted, normalized)
report.py    # JSON / CSV / Markdown over one canonical record schema
tests/test_validation.py
conftest.py

## Metrics per scenario
net_profit, win_rate, profit_factor, expectancy, sharpe, sortino, max_drawdown
(+pct), total_trades, average_trade, largest_win, largest_loss (+ total_return/pnl).

## Example
    m = (ValidationMatrix()
         .add_strategy("ema_crossover", period=[5,8,10,12,20,30])
         .with_bricks(BrickSpec(brick_size=1.0), BrickSpec(brick_size=2.0))
         .with_symbols("AAA","BBB").with_datasets("d1")
         .with_risk(RiskSettings(starting_capital=1_000_000, fixed_quantity=1)))
    results = ValidationRunner(data_source).run(m.scenarios())
    ranking.composite_score(results, {"profit_factor":1.0, "expectancy":1.0, "max_drawdown_pct":1.0})
    report.to_json(results); report.to_csv(results); report.to_markdown(results)

## Run
    pytest -q tests/test_validation.py
    # add --cov=backend/app/trading/validation --cov-report=term  (100%)
