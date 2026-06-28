# Trading System T2 — Backtesting Engine (new packages under backend/app/trading/)

Built on the frozen Renko engine and frozen Strategy layer. NOTHING under
backend/app/chart/renko/ or backend/app/trading/strategy/ is modified.

## New files
backend/app/trading/execution/{__init__,order,position,executor}.py
backend/app/trading/portfolio/{__init__,portfolio}.py
backend/app/trading/costs/{__init__,brokerage,slippage}.py
backend/app/trading/backtesting/{__init__,engine,metrics,report}.py
tests/{test_costs,test_execution,test_portfolio,test_metrics,test_backtesting_engine}.py
conftest.py

## Refinements applied
1. Next-brick fill: a signal on completed brick N executes on brick N+1 (no
   optimistic same-brick execution).
2. Portfolio tracks available_capital, reserved_capital (reserve/release), and
   buying_power (= available * leverage; leverage defaults to 1.0 -> backward
   compatible).
3. Trade records carry strategy_name, symbol, brick_type, brick_size, timeframe.

## Reusable execution core
Order / Position / Trade / Portfolio / cost models are venue-agnostic; the
Executor ABC is the seam. SimulatedExecutor is the only backtest-specific piece;
PaperExecutor / LiveExecutor can implement the same interface later.

## Run
    pytest -q tests/test_costs.py tests/test_execution.py tests/test_portfolio.py \
             tests/test_metrics.py tests/test_backtesting_engine.py
    # add --cov=backend/app/trading/{execution,portfolio,costs,backtesting} for coverage (100%)
