# Sprint 7 Analytics

Sprint 7 adds an Analytics bounded context without changing the existing trading,
backtesting, validation, or paper-trading contexts.

## Architecture

The implementation follows the repository's Clean Architecture / DDD style:

- `backend/app/analytics/domain` contains immutable value objects, entities,
  domain interfaces, and pure domain services.
- `backend/app/analytics/application` contains the application service and command
  used to build analytics reports from validation result sets.
- `backend/app/analytics/api` exposes read-only analytics capability and health
  routes under `/api/v1/analytics`.
- `backend/app/analytics/dto` defines serializable DTO shapes.
- `backend/app/analytics/mappers` maps domain entities into DTOs.
- `backend/app/analytics/reporting.py` renders analytics reports as JSON, CSV,
  and Markdown.
- `backend/app/analytics/engine.py`, `portfolio.py`, `performance.py`, and
  `drawdown.py` provide narrow facades for engine, portfolio, performance, and
  drawdown analytics.

## Reuse Boundaries

Sprint 7 reuses the existing repository models instead of duplicating them:

- `backend.app.trading.backtesting.metrics.PerformanceMetrics`
- `backend.app.trading.execution.position.Trade`
- `backend.app.trading.portfolio.portfolio.Portfolio`
- `backend.app.trading.validation.results.ResultSet` and `ScenarioResult`
- `backend.app.trading.validation.scenario.Scenario`

## Running Tests

```bash
pytest backend/app/analytics/tests tests/test_health.py
```

The analytics API is registered in `backend/app/main.py` and is available at:

- `GET /api/v1/analytics/health`
- `GET /api/v1/analytics/capabilities`
