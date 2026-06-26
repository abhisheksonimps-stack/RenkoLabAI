# Market Processing Pipeline

## Responsibilities

The processing pipeline provides a reusable asynchronous infrastructure for connecting replay, live data, aggregation, chart engines, indicators, and future strategy modules. It focuses on stage orchestration, context propagation, event publication, retry handling, and metrics, without implementing chart generation, Renko, indicators, or strategies.

## Public Interfaces

- `PipelineStage` - stage abstraction for processing units.
- `Pipeline` - runner abstraction that executes stages in order.
- `PipelineContext` - shared state container for data and metadata.
- `StageRegistry` - registry for available pipeline stages.
- `StageResult` - execution result model including status, retries, and metrics.
- `ProcessingGraph` - dependency graph resolving stage ordering.
- `DefaultPipeline` - concrete async pipeline runner with retry policy and event hooks.

## Event Flow

Pipeline events are published through the shared `EventBus`:

- `PipelineStarted`
- `PipelineStageStarted`
- `PipelineStageCompleted`
- `PipelineStageFailed`
- `PipelineCompleted`
- `PipelineError`

Consumers can subscribe to these events for monitoring, logging, and integration.

## Replay Lifecycle

1. Register pipeline stages in `StageRegistry`.
2. Build a `ProcessingGraph` with stage dependencies.
3. Create a `DefaultPipeline` with graph, `EventBus`, and optional retry config.
4. Execute `pipeline.run(context)`.
5. Stage results are returned in a final `StageResult` and published as events.

## Extension Points

- Add new `PipelineStage` implementations for replay, aggregation, or live ingestion.
- Build alternative `Pipeline` classes that support parallel execution or dynamic stage resolution.
- Subscribe to `EventBus` lifecycle events for metrics, alerting, or visualization.
