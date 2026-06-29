# Production Readiness Audit

Audit scope: complete repository inspection of the uploaded ZIP, with no source-code changes. The audit verified the requested live trading path and adjacent production controls from the current implementation only.

Audit commands executed:

```bash
python -m compileall backend/app
pytest -q
pytest -q tests/test_market_streaming.py tests/test_trading_strategy.py tests/test_portfolio.py
```

Repository inspection coverage: 600 files read from the extracted repository, including backend source, tests, docs, deployment files, frontend files, and configuration.

## 1. Overall Production Readiness Score

**Overall production readiness score: 38 / 100**

Rationale: the repository has a meaningful domain foundation, streaming primitives, strategy framework, backtesting, paper trading, analytics, and a broker adapter abstraction. However, the requested live runtime pipeline is not fully connected, full pytest collection fails in the current environment, live trading does not update portfolio/analytics/reporting end-to-end, production dependency packaging is not reliable, risk validation is implemented but not enforced by OMS, and several production controls are either missing or not wired.

## 2. Architecture Score

**Architecture score: 61 / 100**

Strengths:

- Clean package boundaries exist across `api`, `application`, `domain`, `infrastructure`, `events`, `marketdata`, `pipeline`, `trading`, and `analytics`.
- Trading abstractions are mostly separated: strategies, signals, OMS, execution, broker, portfolio, costs, paper trading, and backtesting.
- Analytics is implemented as a bounded context with domain entities, DTOs, mappers, services, API routes, and renderers.
- Market-data and broker interfaces exist and preserve adapter boundaries.

Architecture violations and gaps:

- Two separate event dispatch systems exist: `backend/app/events/bus.py` and `backend/app/marketdata/streaming/dispatcher.py`; they are not unified or bridged.
- `backend/app/marketdata/streaming/router.py` exists but is not integrated into `StreamingManager` and is not exported from `backend/app/marketdata/streaming/__init__.py`.
- The runtime live trading pipeline is not represented as a composed application service or pipeline stage graph.
- Dependency injection does not register streaming, strategy engine, OMS, broker adapter, live executor, portfolio, analytics engine, or reporting renderer.
- Infrastructure modules are imported eagerly; missing optional/runtime dependencies break test collection and application import paths.
- Repository and database abstractions exist but are not integrated into trading/order/position/analytics persistence.
- Several base modules contain placeholder/pass-only classes or empty marker files.

## 3. Trading Engine Score

**Trading engine score: 44 / 100**

Strengths:

- Strategy framework supports `on_market_data`, `on_tick`, `on_brick`, order-fill hooks, position-close hooks, risk manager integration, strategy registry, and multiple built-in strategies.
- OMS can convert manual `Signal` inputs into `Order` instances and route them to an executor.
- `LiveExecutor` implements a broker adapter bridge for submit/poll/fill mapping.
- `PositionSynchronizer` can apply fills locally and reconcile with broker-reported positions.
- Portfolio supports fills, marking, equity curves, reservations, trades, brokerage, and slippage.

Critical gaps:

- No implemented live orchestrator connects streaming ticks to strategy engine, strategy results to OMS, OMS orders to portfolio, portfolio state to analytics, and analytics to reporting.
- OMS does not call `PreExecutionRiskValidator.validate()`; risk validation is effectively bypassed at the OMS layer.
- OMS does not apply fills to `PositionSynchronizer` or portfolio.
- `LiveExecutor` does not put platform orders into `PENDING` status before broker submission.
- Platform `Order` has no broker-order ID field, so broker order reconciliation/cancellation is weak.
- Portfolio is long-only and single-position oriented, which does not match institutional multi-symbol live trading readiness.
- Live trading tests cover only mocked `signal -> OMS -> LiveExecutor -> Broker` and do not cover streaming, dispatcher, portfolio, analytics, or reporting.

## 4. Live Trading Readiness

**Live trading readiness: 24 / 100**

The repository is **not production ready for live trading**. It has some live trading primitives, but the actual runtime path is incomplete.

Main blockers:

- Tick events do not automatically reach strategies.
- Strategy results do not automatically reach OMS.
- OMS does not enforce pre-execution risk validation.
- Orders do not reliably preserve broker IDs.
- Fills do not automatically update position synchronization or portfolio.
- Portfolio updates do not automatically generate analytics or reports.
- Broker adapter imports hard-fail when `ccxt` is absent.
- Redis imports hard-fail when `redis` is absent.
- Full pytest cannot complete collection in the current repository environment.

## 5. End-to-End Runtime Pipeline Audit

| Stage | Implemented | Integrated | Tested | Production Ready | Missing | Dead Code | Duplicate Code | Broken Imports | Runtime Gaps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Market Data | Partial. Historical provider, adapters, models, cache, registry, domain models exist. | Partial. Historical loading is integrated with provider/cache. Live stream models exist separately. | Partial. Market-data unit tests exist. | No. Live market data is not connected to trading runtime. | No production provider lifecycle, no live persistence, no unified historical/live abstraction. | Some unused domain/provider abstractions. | `backend/app/marketdata/provider.py` and `backend/app/domain/market_data/providers.py` define overlapping provider concepts. | None at compile time. | Historical bars and streaming events do not enter the same runtime path. |
| Streaming | Partial. `StreamingManager`, `WebSocketStream`, `ReconnectManager`, `SubscriptionManager`, events, dispatcher, and router exist. | Partial. `StreamingManager` uses `EventDispatcher`, not `MarketRouter`; no strategy/OMS subscriber is wired. | Partial. `tests/test_market_streaming.py` passes. `tests/test_market_router.py` contains only a docstring. | No. No production stream-to-trading integration. | No tick processor, no backpressure policy beyond local queues, no durable recovery, no central subscription orchestration. | `MarketRouter` is present but unused. `EventDispatcher._task` is unused. | `EventDispatcher` duplicates responsibilities with `EventBus`. | None at compile time. | Stream events stop at subscribers; there is no default subscriber that feeds strategy engine. |
| Dispatcher | Yes. `EventDispatcher` and `EventBus` both exist. | Partial. Streaming uses `EventDispatcher`; generic pipeline uses `EventBus`; they are isolated. | Partial. Both dispatcher and event bus have tests. | No. Event buses are not unified and production handlers are not registered through DI. | No global event routing contract between market data, pipeline, trading, analytics, and API. | Event-specific classes with `pass` exist as marker events. | Duplicate event-dispatch abstractions. | None at compile time. | A component subscribed to `EventBus` will not receive `EventDispatcher` market events. |
| Strategy Engine | Yes. `StrategyEngine` supports bars, ticks, bricks, fills, and closes. | Partial. Backtesting uses it. Live streaming does not. Paper has a separate bridge. | Partial. Strategy framework tests pass. | No for live trading. | No runtime subscriber/processor converting `TickEvent` to `StrategyContext` and `process_tick()`. | None blocking. | Strategy live/paper/backtest orchestration paths are separate. | None at compile time. | `process_tick()` is not referenced by live streaming code. |
| Risk Engine | Partial. Strategy `RiskManager` and OMS `PreExecutionRiskValidator` exist. | No at OMS level. `OMS.process_signal()` contains a comment/pass instead of calling `_risk_validator.validate()`. | Partial. Risk validator has direct unit tests. | No. | OMS enforcement, risk rejection order state, account/broker-aware validation, accurate realized P&L basis tracking. | `RiskCheckResult` import in OMS is unused. | Strategy risk and OMS pre-execution risk overlap without a clear sequence. | None at compile time. | A live order can proceed without pre-execution risk checks. |
| OMS | Partial. Signal-to-order and executor routing exist. | Partial. Manually callable only; not wired to strategy/dispatcher/portfolio/analytics. | Partial. Mocked OMS tests exist but full test collection fails before execution. | No. | Broker order sync, position sync application, portfolio update, risk enforcement, multi-symbol active positions. | `get_active_positions()` returns an empty placeholder. | Backtest order mapping duplicates OMS order mapping. | Type-hint introspection fails: `typing.get_type_hints(OMS.__init__)` raises `NameError: PositionSynchronizer is not defined`. | OMS creates orders but does not complete the live lifecycle after execution. |
| Broker Adapter | Partial. `BrokerAdapter` interface and `CCXTAdapter` exist. | Partial. `LiveExecutor` can call adapter methods. | Partial. Tests exist but cannot collect without `ccxt`. | No. | Production credential handling, retries, order-id reconciliation, rate-limit integration, exchange-specific capability validation. | None blocking. | Broker `OrderSide`/`OrderStatus` duplicates platform execution enums. | `import ccxt.async_support as ccxt` hard-fails if `ccxt` is absent. | Adapter errors and exchange quirks are not routed through a circuit breaker/retry policy. |
| Live Executor | Partial. Submits broker order, polls, maps fill/rejection. | Partial. Used by OMS when manually instantiated. | Partial. Mocked tests exist but are blocked by missing `ccxt` during collection. | No. | Pending state transition, immediate terminal broker status handling, broker-order ID propagation, portfolio/fill event emission. | `_slippage` is initialized but not used in live execution. | Uses broker enums separately from platform enums. | Indirectly blocked by broker adapter import failure in tests. | Immediate rejected orders from `submit_order()` are still sent to polling path; unconfigured `get_order` can produce unexpected rejection. |
| Portfolio | Yes for backtest/paper single-portfolio flow. | Partial. Backtest and paper apply orders. Live OMS does not. | Partial. Portfolio tests pass. | No for institutional live trading. | Multi-symbol portfolio, broker cash/equity reconciliation, idempotent fill application, live snapshots. | None blocking. | Position tracking duplicated between `Portfolio.position` and `PositionSynchronizer.positions`. | None at compile time. | Live fills do not automatically mutate portfolio. |
| Analytics | Yes for validation/backtest result analytics and portfolio analytics service. | Partial. Analytics API and validation/report generation exist. Not wired to live portfolio updates. | Partial. Analytics tests exist, but full suite collection fails before completion. | No for live operations. | Live portfolio snapshot ingestion, scheduled/live reports, persistence, API for live analytics. | Facade modules are thin but acceptable. | Research report renderer and analytics report renderer are separate by context. | None at compile time. | Portfolio analytics are not triggered by live portfolio marks/fills. |
| Reporting | Yes. Analytics renderer outputs JSON, CSV, Markdown for analytics reports. | Partial. Integrated with analytics domain reports, not live trading pipeline. | Partial. Renderer tests exist. | No for live operations. | Live trading report generation, publishing/storage, API endpoints for generated reports. | None blocking. | Multiple report renderers exist by bounded context; acceptable if intentionally separated. | None at compile time. | No runtime report production from live portfolio/analytics. |

## 6. Required Production Control Verification

| Area | Status | Audit Finding |
| --- | --- | --- |
| Exchange abstraction | Partial | `BrokerAdapter` and `CCXTAdapter` exist. Dependency hard-fails when `ccxt` is missing; no capability registry or exchange-specific policy validation. |
| Live broker abstraction | Partial | Broker interface is clean, but broker order IDs are not preserved in platform orders and not synchronized into OMS state. |
| Position synchronization | Partial | `PositionSynchronizer` exists under OMS. It is not wired into OMS execution results or portfolio. Dedicated `backend/app/trading/portfolio/synchronizer.py` is absent. |
| Order lifecycle | Partial | Platform order statuses exist. LiveExecutor does not call `order.submit()` before broker submission, no broker ID, no order reconciliation service. |
| Fill handling | Partial | Fill mapping exists in LiveExecutor. OMS does not record fills into risk validator, position synchronizer, or portfolio. |
| Risk validation | Not integrated | `PreExecutionRiskValidator` exists but `OMS.process_signal()` bypasses it. Broker position check and strategy rule check are placeholders. |
| Portfolio valuation | Partial | Portfolio can mark equity from a supplied price. Live marks are not automatically driven by market data or broker snapshots. |
| Event bus wiring | Partial | `EventBus` and `EventDispatcher` both work in isolation. They are not bridged or registered through DI for live trading. |
| Dependency Injection | Partial | DI config registers database, Redis, repository, Renko services, and snapshot services. It does not register trading/live pipeline components. |
| Configuration | Partial | Settings exist for app/database/Redis/JWT. Broker/exchange, live trading, streaming, risk, and reporting settings are absent. |
| Logging | Partial | Basic root logger setup exists. No structured logs, correlation IDs, trade/order audit log, or alert integration. |
| Error handling | Partial | Local try/except blocks exist in dispatcher, streaming manager, broker, and executor. There is no centralized trading error policy, retry classification, or escalation. |
| Database integration | Weak | SQLAlchemy session and market-data models exist. Alembic `target_metadata` is `None`, async engine use in Alembic is incorrect, and trading/order/portfolio persistence is absent. |
| Redis integration | Weak | `RedisClient` exists but imports `redis.asyncio` eagerly and breaks collection when Redis package is absent. It is not used by streaming/trading runtime. |
| Metrics | Weak | Pipeline stage result metrics exist. No production metrics endpoint, no Prometheus/exporter integration, no trading metrics instrumentation. |
| Health endpoints | Partial | `/api/v1/health` and `/api/v1/analytics/health` exist. They do not check database, Redis, broker, stream, dispatcher, OMS, or portfolio health. |
| API coverage | Weak | APIs are limited to health and analytics capabilities. No live trading, orders, positions, broker, portfolio, streaming, or report retrieval APIs. |
| Thread safety | Weak | Most trading state is mutable and unsynchronized. `SubscriptionManager` uses `asyncio.Lock`; OMS/order manager/portfolio do not. |
| Async safety | Partial | Async primitives are used for streaming and broker operations. Mixed sync/async executor interface exists: `Executor.execute` is abstract sync, `LiveExecutor.execute` is async, and OMS assumes async execution. |
| Graceful shutdown | Partial | FastAPI calls container resource shutdown; streaming manager and websocket streams have stop/disconnect methods. Live OMS/broker/portfolio/reporting shutdown is not wired to app lifecycle. |
| Recovery | Weak | Reconnect manager exists for streams. No order/position recovery, persisted replay, broker reconciliation on restart, or portfolio recovery. |
| Circuit breaker | Missing | No circuit breaker module or broker/stream integration found. |
| Rate limiter | Missing | No rate limiter module or broker/stream integration found. CCXT `enableRateLimit` can be passed by config but no platform limiter exists. |

## 7. Missing Integrations

1. `TickEvent -> StrategyEngine`
   - `StrategyEngine.process_tick()` exists.
   - No streaming subscriber, tick processor, or live application service calls it.
   - `rg "process_tick(" backend tests` shows only aggregation engine tests and the strategy engine method definition; no live market-data usage.

2. `StrategyEngine -> OMS`
   - `StrategyEngine` stores `StrategyResult` instances.
   - No live component forwards actionable `StrategyResult.signal` to `OMS.process_signal()`.

3. `Risk Engine -> OMS`
   - `PreExecutionRiskValidator.validate()` exists.
   - `OMS.process_signal()` does not call it; the code contains a comment/pass block.

4. `OMS -> Broker/LiveExecutor`
   - Manual path exists when OMS is constructed with a `LiveExecutor`.
   - There is no DI registration, app lifecycle construction, API, or streaming subscriber that instantiates this path for production.

5. `LiveExecutor -> BrokerAdapter`
   - The submit/poll path exists.
   - Platform orders do not retain broker order IDs and immediate terminal broker statuses are not handled safely.

6. `Broker events -> Positions`
   - No broker event stream exists.
   - `PositionSynchronizer.sync()` can poll broker positions, but it is not scheduled or triggered by order fills.

7. `Positions -> Portfolio`
   - Portfolio and `PositionSynchronizer` are separate state stores.
   - No synchronizer applies broker position updates into portfolio.

8. `Portfolio -> Analytics`
   - `AnalyticsPortfolioService.from_portfolio()` exists.
   - It is not triggered by live portfolio state changes.

9. `Analytics -> Reporting`
   - `AnalyticsReportRenderer` exists.
   - It renders only when called directly; no live report generation job or endpoint exists.

10. Dedicated production modules requested in prior implementation expectations:
    - Present but unused: `backend/app/marketdata/streaming/router.py`.
    - Missing: `backend/app/marketdata/streaming/tick_processor.py`.
    - Missing: `backend/app/trading/portfolio/synchronizer.py`.
    - Missing: `backend/app/trading/portfolio/live_snapshot.py`.
    - Missing: `backend/app/trading/oms/order_sync.py`.
    - Missing: any top-level live runtime composition module/service.

## 8. Critical Blockers

1. Full pytest suite does not collect.
   - `pytest -q` fails during collection with `ModuleNotFoundError: No module named 'redis'` and `ModuleNotFoundError: No module named 'ccxt'`.
   - This prevents validating the claimed live trading tests in the current environment.

2. Dependency packaging is not production reliable.
   - `pyproject.toml` uses `[project.dependencies]` as a table. Standard PEP 621 expects `dependencies = [...]` under `[project]`.
   - Docker runs `pip install .`; dependencies may not be installed reliably from the current metadata.

3. Live runtime pipeline is not connected.
   - The path from market-data streaming through reporting does not exist as a composed runtime.

4. OMS bypasses risk validation.
   - Orders can execute without calling `PreExecutionRiskValidator.validate()`.

5. Live fills do not update portfolio or analytics.
   - `OMS.process_signal()` returns an order but does not apply fills to `PositionSynchronizer`, `Portfolio`, or analytics/reporting.

6. Order reconciliation is incomplete.
   - Platform `Order` does not store `broker_order_id`.
   - OMS cancellation uses platform order ID as broker order ID.

7. Database migrations are not production ready.
   - Alembic `target_metadata` is `None`.
   - `env.py` constructs `DatabaseSession` with an Alembic config section instead of application settings.
   - Async engine connection handling is incorrect for Alembic online migration flow.

8. Secrets and auth are not production ready.
   - `.env.example` uses `JWT_SECRET=replace-with-secure-secret`.
   - API routes are not protected by authentication/authorization.

## 9. High Priority Issues

1. `MarketRouter` is dead/incomplete integration.
   - It is not used by `StreamingManager` and is not exported from the streaming package.
   - Symbol-specific routing applies only to `TickEvent`, not candle/order-book/status events.

2. `tests/test_market_router.py` is effectively empty.
   - It contains only a docstring and provides no coverage for the router.

3. Mixed sync/async executor contract.
   - `Executor.execute()` is declared as a regular abstract method.
   - `LiveExecutor.execute()` is async.
   - Backtesting calls executors synchronously; OMS awaits executors. This mismatch is manageable only by convention and is not type-safe.

4. Broker adapter import strategy is fragile.
   - `backend/app/trading/broker/ccxt_adapter.py` imports `ccxt` at module import time, which blocks tests and app imports if the dependency is unavailable.

5. Redis import strategy is fragile.
   - `backend/app/infrastructure/redis_client.py` imports `redis.asyncio` at module import time, which blocks unrelated tests and app imports if the dependency is unavailable.

6. Health checks are superficial.
   - They return static status without verifying database, Redis, broker, streaming, dispatcher, OMS, or analytics health.

7. No persistence for trading state.
   - Orders, fills, positions, portfolio snapshots, risk decisions, and live reports are not persisted.

8. No idempotency controls.
   - Live fill application to portfolio is not implemented, and there is no design to prevent duplicate fill application after reconnect/retry.

## 10. Medium Priority Issues

1. `PositionSynchronizer.sync()` swallows exceptions silently and returns stale local positions.
2. `PreExecutionRiskValidator.record_fill()` does not calculate realized P&L against cost basis and can misstate daily P&L.
3. `PreExecutionRiskValidator._check_broker_positions()` contains a placeholder branch and always passes.
4. `PreExecutionRiskValidator._check_strategy_rules()` always passes.
5. `OMS.get_active_positions()` returns an empty list placeholder.
6. `LiveExecutor._slippage` is unused.
7. `LiveExecutor._wait_for_fill()` always sleeps before checking initial broker status, even if the submitted order is already terminal.
8. `EventDispatcher.publish()` queues events when stopped but has no max queue size and no durable replay strategy.
9. `MarketRouter.route()` drops events on queue-full without metrics or retry escalation.
10. `WebSocketStream._send_heartbeat()` is a pass-only override hook and provides no default heartbeat behavior.
11. Streaming reconnect does not resubscribe symbols after reconnect unless handled externally.
12. No app-level wiring starts/stops streaming manager, broker connections, OMS, or reporting jobs.

## 11. Low Priority Issues

1. Multiple package `__init__.py` files expose little or no public API despite implemented modules.
2. Pydantic deprecation warnings appear for class-based `Config` and classmethod `@model_validator(mode="after")` usage.
3. FastAPI `@app.on_event` is deprecated in newer FastAPI versions in favor of lifespan handlers.
4. Several base marker modules contain pass-only classes; acceptable as placeholders for early architecture but not production-grade.
5. `datetime.utcnow()` is widely used; timezone-aware UTC timestamps would be safer for trading and audit logs.
6. Some tests assert against private attributes, which increases refactor fragility.

## 12. Technical Debt

- Duplicate event systems: `EventBus` and `EventDispatcher`.
- Duplicate provider abstractions between `marketdata` and `domain/market_data`.
- Duplicate position state between `Portfolio.position` and `PositionSynchronizer.positions`.
- Duplicate order status/side enums between broker and platform execution layers.
- Backtest, paper, and live order flows are not mediated through a shared lifecycle service.
- Analytics and research reporting are separate renderers without a common reporting port.
- Dependency management is not aligned with standard Python packaging metadata.
- Alembic integration is incomplete and not connected to application metadata.
- No lint/type-check enforcement output was available from the current audit run.

## 13. Architecture Violations

1. Infrastructure imports can break high-level modules.
   - Importing `backend.app.main` pulls DI, Redis, and database setup; missing Redis package blocks even the health endpoint test.

2. Application orchestration is missing for live trading.
   - Components exist at lower layers, but no application service composes them into the requested runtime pipeline.

3. Risk validation intent is not enforced by the OMS.
   - The domain/service boundary exists but is bypassed.

4. Event-driven boundaries are inconsistent.
   - Generic pipeline uses `EventBus`; streaming uses `EventDispatcher`; paper trading uses `EventBus`; live trading uses neither end-to-end.

5. Persistence boundary is incomplete.
   - Repositories are generic, but no concrete trading repositories exist.

## 14. Performance Bottlenecks

1. `EventDispatcher._dispatch()` awaits all handlers for every event; a slow handler delays the publish call.
2. No bounded queue in `EventDispatcher`; stopped dispatcher can accumulate unbounded events.
3. `LiveExecutor` polls orders sequentially per execution and blocks until fill/timeout; no scalable order-status fanout or broker websocket order updates.
4. `PositionSynchronizer.sync()` fetches all broker positions by default; no incremental reconciliation or schedule/backoff policy.
5. `Portfolio` is single-position/single-lock free mutable state; concurrent live fills could race.
6. Market data streaming has no throughput metrics, latency metrics, or slow-consumer detection.
7. Historical adapters normalize lists eagerly; large datasets may consume memory unnecessarily.

## 15. Security Concerns

1. Default JWT secret is insecure and shown in `.env.example`.
2. API routes do not enforce authentication or authorization.
3. No broker credential model, secret store integration, key rotation, or restricted runtime permission model is implemented.
4. No audit trail for submitted orders, risk decisions, cancels, fills, broker errors, or operator actions.
5. No explicit transport security configuration in backend app setup.
6. Docker Compose includes default Postgres credentials suitable only for development.
7. Redis has no authentication/TLS configuration in compose or settings.
8. No request rate limiting, API abuse controls, or trading kill switch endpoints are implemented.

## 16. Test Results

### Compile

`python -m compileall backend/app` — **passed**.

### Full pytest

`pytest -q` — **failed during collection**.

Observed collection errors:

- `ModuleNotFoundError: No module named 'redis'`
- `ModuleNotFoundError: No module named 'ccxt'`

Affected test modules during collection included:

- `tests/test_adaptive_provider.py`
- `tests/test_brick_builder_abstraction.py`
- `tests/test_engine_persistence.py`
- `tests/test_health.py`
- `tests/test_hybrid_builder.py`
- `tests/test_price_reference_strategy.py`
- `tests/test_renko_infrastructure.py`
- `tests/test_sprint10_live_trading.py`

### Partial targeted tests

`pytest -q tests/test_market_streaming.py tests/test_trading_strategy.py tests/test_portfolio.py` — **58 passed**.

### Warning categories observed

- Pydantic v2 deprecation warnings for class-based config and validator style.
- Pytest collection warning for a test dataclass with an `__init__` constructor.

## 17. Recommended Sprint 12 Tasks

1. Fix dependency packaging and import resilience.
   - Correct `pyproject.toml` dependency metadata.
   - Defer optional external imports or provide clear install extras.
   - Ensure `pytest -q` collects and runs fully in a clean environment.

2. Create the live runtime composition layer using existing components.
   - Wire `StreamingManager/EventDispatcher`, strategy engine, risk validator, OMS, live executor, broker adapter, position synchronizer, portfolio, analytics, and reporting.
   - Do not replace existing components; compose them.

3. Enforce OMS pre-execution risk validation.
   - Call `PreExecutionRiskValidator.validate()` before executor submission.
   - Persist/log risk decisions and rejected orders.

4. Implement order synchronization and broker ID propagation.
   - Preserve broker order IDs on platform orders or a dedicated mapping.
   - Reconcile open broker orders on startup and after reconnect.

5. Implement live fill-to-position-to-portfolio synchronization.
   - Make fill application idempotent.
   - Reconcile broker-reported positions and account balances against portfolio state.

6. Integrate live portfolio snapshots with analytics/reporting.
   - Generate portfolio analytics from live marks/fills.
   - Expose or persist generated reports.

7. Unify or bridge event dispatch systems.
   - Decide how `EventBus`, `EventDispatcher`, and `MarketRouter` cooperate.
   - Add production tests covering event flow across boundaries.

8. Productionize health, metrics, circuit breaker, and rate limiter.
   - Add health checks for DB, Redis, broker, streams, dispatcher, OMS, and portfolio.
   - Add metrics endpoint/instrumentation.
   - Add broker/stream circuit breaker and platform rate limiter.

9. Fix persistence and migrations.
   - Set Alembic `target_metadata`.
   - Correct async migration flow.
   - Add trading tables for orders, fills, positions, risk decisions, and portfolio snapshots.

10. Add end-to-end tests for the requested runtime pipeline.
    - Verify: Tick events reach strategies; strategies generate signals; signals reach OMS; OMS creates orders; orders reach LiveExecutor; LiveExecutor reaches BrokerAdapter; broker fills update positions; positions update portfolio; portfolio updates analytics; analytics produces reports.

## 18. Final Audit Position

The repository is a strong prototype/foundation but not yet a production-grade institutional live trading platform. The core issue is not lack of isolated components; it is missing runtime composition, missing enforcement at critical boundaries, incomplete persistence/recovery, and failing full test collection in the current environment.
