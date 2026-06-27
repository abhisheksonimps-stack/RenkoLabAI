# Sprint 6C — ATR Renko via Brick-Size Provider

## 1. Architecture summary

Sprint 6C separates **brick-size calculation** from **brick generation**. The
Traditional brick-generation algorithm (continuation / reversal / multi-brick)
is untouched and fully reused; the only new responsibility is *deciding the
current brick size*, which now lives behind a `BrickSizeProvider` abstraction.

Old flow:

```
Completed Candle -> TraditionalRenkoEngine -> TraditionalBrickBuilder -> Bricks
```

New flow:

```
Completed Candle
  -> BrickSizeProvider.update(candle)
  -> if provider.ready(): size = provider.current_size()
  -> TraditionalBrickBuilder -> Bricks
```

The engine treats the provider as a black box. It calls `update`, checks
`ready`, reads `current_size`, and feeds that size into the *existing*
generation routines. No Renko / continuation / reversal / pipeline logic was
duplicated.

## 2. Modified files

New:
- `backend/app/chart/renko/providers.py` — `BrickSizeProvider` implementations
  (`FixedBrickSizeProvider`, `ATRBrickSizeProvider`) and
  `BrickSizeProviderRegistry` + `default_provider_registry()`.
- `tests/test_brick_size_providers.py` — comprehensive Sprint 6C tests.

Modified:
- `interfaces.py` — added the `BrickSizeProvider` ABC
  (`update`, `current_size`, `ready`, `reset`).
- `configuration.py` — added `atr_multiplier` and `provider` fields plus
  `resolved_provider()`; kept all existing fields (backwards compatible).
- `engine.py` — refactored to source brick size from a provider; defaults to a
  fixed provider so 6B behaviour is identical; warm-up gating; publishes
  `BrickSizeUpdated`; `reset()` clears provider state.
- `events.py` — added the provider-specific `BrickSizeUpdated` event.
- `factory.py` — `RenkoFactory` now optionally takes a provider registry and
  injects the correct provider into the engine based on configuration.
- `validator.py` — validates `atr_multiplier > 0` and (when a registry is
  supplied) that the configured provider exists.
- `plugin.py` — `RenkoPlugin` gained a `register_brick_size_providers` hook.
- `pipeline.py` — registers `BrickSizeUpdated`; pipeline structure unchanged.
- `__init__.py` — exports the new abstractions/events.
- `plugins/manager.py` — optional `provider_registry` + plugin hook invocation.
- `infrastructure/di.py` — registers `brick_size_provider_registry` and wires it
  into the existing factory and validator (no second DI system).

## 3. Design decisions

- **Provider owns all state.** True Range, ATR, warm-up counters and the rolling
  ATR value live inside `ATRBrickSizeProvider`. The engine holds no ATR state.
- **Registry stores factories, not instances.** Providers are stateful, so a
  single shared instance can't be reused across engines. The registry maps a
  provider name to a factory `(configuration) -> BrickSizeProvider`.
- **Wilder's smoothing for ATR.** O(1) time and O(1) memory per candle: during
  warm-up only a running sum of True Ranges is kept; afterwards a single ATR
  float is updated as `ATR = (ATR*(n-1) + TR) / n`. The full history is never
  rescanned.
- **Spec-literal ordering.** `update(candle)` runs before `current_size()`, so a
  candle's own True Range is reflected in the size used for that candle.
- **Backwards compatibility.** `provider` defaults to `None`;
  `resolved_provider()` derives `"fixed"`/`"atr"` from `brick_type`, so existing
  Fixed Renko configurations work unchanged and the engine's default provider is
  the fixed one.
- **Provider-specific events only.** `BrickSizeUpdated` is published when the
  size changes; existing brick lifecycle events are reused, not duplicated.

## 4. Assumptions

- True Range for the first candle (no previous close) is `high - low`.
- When a feed omits `high`/`low`, they fall back to `close` so TR stays defined.
- A default `atr_multiplier` of `1.0` is used when ATR is configured without one
  (`size == ATR`), keeping older partial configs usable.
- During ATR warm-up the engine generates no bricks; the first ready candle sets
  the anchor (consistent with the existing first-brick behaviour).

## 5. Test summary

`export PYTHONPATH=$PWD && pytest -q` → **96 passed** (67 pre-existing + 29 new).

New coverage in `tests/test_brick_size_providers.py`:
- Fixed provider: readiness, constant size, reset, and a regression proving
  identical brick output **and** event sequence vs. the default fixed path.
- ATR provider: true range (first candle + gaps), warm-up + seed, Wilder rolling
  update, multiplier scaling, invalid-config rejection, reset, replay
  determinism, and replay-after-reset.
- Provider registry: built-in resolution, duplicate/missing handling, and
  plugin-registered custom providers; backwards-compatible `resolved_provider()`.
- Validator: rejects bad multiplier / unknown provider, accepts known provider.
- Factory: injects the correct provider per configuration; no-registry path
  stays backwards compatible.
- Engine integration: fixed-provider bricks, ATR warm-up then generation,
  size changing across candles, reset+replay determinism, `BrickSizeUpdated`.
- Pipeline + events: ATR engine runs through the pipeline and emits the event.
- Performance: constant-memory ATR over a 200k-candle replay (no growing
  containers) and a large engine replay that scales sub-10x for 4x candles.
