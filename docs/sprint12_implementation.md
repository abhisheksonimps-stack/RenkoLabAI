# Sprint 12 Production Integrations

## Live Runtime Orchestration

Sprint 12 adds a live runtime layer that connects streaming ticks to strategy execution, risk validation, OMS execution, broker submission, portfolio synchronization, analytics and reporting. The runtime is intentionally a composition layer over existing packages and does not replace the established strategy, OMS, broker, portfolio, analytics or streaming implementations.

Implemented integration modules:

- `backend/app/trading/runtime.py`
- `backend/app/trading/live_pipeline.py`
- `backend/app/marketdata/streaming/tick_processor.py`
- `backend/app/events/bridge.py`

## OMS Risk Enforcement

The OMS now performs `PreExecutionRiskValidator.validate()` for every non-HOLD signal when OMS risk validation is enabled. Risk decisions are retained on the OMS and rejected orders are logged and returned with rejected status.

## Broker Order Synchronization

Broker order IDs are propagated from broker acknowledgements back to platform orders. OMS order synchronization supports active-order reconciliation, recovery, cancellation synchronization and local modify validation.

Implemented module:

- `backend/app/trading/oms/order_sync.py`

## Position and Portfolio Synchronization

Broker fills update the existing `PositionSynchronizer`. Filled OMS orders are applied to the existing `Portfolio` through an idempotent portfolio synchronizer so duplicate fill events cannot double-apply cash, position or trade mutations.

Implemented modules:

- `backend/app/trading/portfolio/synchronizer.py`
- `backend/app/trading/portfolio/live_snapshot.py`

## Event System Unification

`EventBus` and `EventDispatcher` remain backward compatible. Sprint 12 adds a bridge that can subscribe and publish through both systems without changing either public API.

Implemented module:

- `backend/app/events/bridge.py`

## Persistence

Sprint 12 adds a durable append-only persistence port and JSONL adapter for runtime state:

- Orders
- Fills
- Risk decisions
- Portfolio snapshots
- Analytics snapshots
- Broker synchronization state

Implemented module:

- `backend/app/trading/persistence.py`

## Health and Metrics

Sprint 12 adds component-level production health checks and Prometheus-backed trading metrics. Metrics are collected for tick processing, order submission, order rejection, fill processing, event queue depth, active positions, portfolio equity and execution latency.

Implemented modules:

- `backend/app/health/production.py`
- `backend/app/metrics/production.py`

## Security

Sprint 12 adds trading security primitives while preserving the existing JWT service:

- Principal model
- Trading permissions
- Role-based authorization
- Broker credential resolution from environment variables
- Kill switch

Implemented modules:

- `backend/app/security/base.py`
- `backend/app/security/credentials.py`

## Dependency Hardening

Optional deployment dependencies are now imported defensively so local tests and audit tooling can collect and execute without Redis, CCXT or dependency-injector installed. In production, the real packages are used automatically when installed.

Updated modules:

- `backend/app/infrastructure/redis_client.py`
- `backend/app/infrastructure/di.py`
- `backend/app/trading/broker/ccxt_adapter.py`

## Validation

Sprint 12 adds end-to-end live runtime tests covering:

- Tick to strategy
- Strategy signal to OMS
- OMS risk validation
- Broker execution
- Broker order ID propagation
- Fill handling
- Position synchronization
- Portfolio synchronization
- Analytics/reporting output
- Runtime persistence
- Risk rejection persistence
- Cancel synchronization
