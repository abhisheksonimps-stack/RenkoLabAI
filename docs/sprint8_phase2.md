# Sprint 8 Phase 2 — Institutional Research Platform

Sprint 8 Phase 2 adds a repository-native quantitative research layer under
`backend/app/trading/backtesting/research`.

## Architecture

The research engine follows the existing RenkoLabAI boundaries:

- Strategies are discovered through the existing Strategy Registry.
- Backtests are executed by the existing BacktestEngine.
- Scenarios and results reuse the existing validation models.
- Strategy interfaces remain shared by backtesting and paper trading.
- Sprint 7 Analytics remains the reporting analytics integration point.

## Components

- `models.py`: immutable Pydantic v2 research DTOs.
- `parameter_space.py`: deterministic parameter-grid expansion.
- `optimizer.py`: deterministic sequential or parallel grid search.
- `walk_forward.py`: train, validate, forward-test orchestration.
- `monte_carlo.py`: random trade order and bootstrap simulation.
- `portfolio_optimizer.py`: equal-weight, risk-parity, max-Sharpe, and min-variance allocation.
- `metrics.py`: institutional metrics for research-grade comparisons.
- `reports.py`: JSON, CSV, Markdown, and HTML rendering.
- `engine.py`: top-level facade and historical dataset support.

## Usage

```python
from backend.app.trading.backtesting.research import (
    ParameterSpace,
    ResearchEngine,
    ResearchObjective,
)
from backend.app.trading.validation.scenario import BrickSpec

engine = ResearchEngine(brick_data_source)
result = engine.optimize(
    strategy_names=None,
    symbols=["TEST"],
    dataset_ids=["default"],
    brick_specs=[BrickSpec(brick_size=1.0)],
    parameter_space=ParameterSpace.standard_grid(
        ema_periods=[10, 20],
        renko_brick_sizes=[1.0, 2.0],
        risk_percents=[0.25, 0.50],
    ),
    objective=ResearchObjective(metric="net_profit"),
    max_workers=4,
)
```

## Determinism

Parallel grid search uses `ThreadPoolExecutor.map`, which preserves input order.
Monte Carlo simulations use a local seeded RNG and never mutate global random
state.

## Reporting

`ResearchReportRenderer` provides machine-readable JSON and CSV plus Markdown
and HTML outputs for dashboards or notebooks.
