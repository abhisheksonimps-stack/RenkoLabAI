# Sprint 6J — Adaptive Renko (AdaptiveBrickSizeProvider)

Adaptive Renko is a composite BrickSizeProvider (SELECT-only) implemented INSIDE
providers.py. No engine, builder, snapshot, DI, or interface changes. Fixed
regime set per the approved refinements:

    low volatility    -> Fixed provider
    medium volatility -> Percentage provider
    high volatility   -> ATR provider

Key behaviours:
* ready() is True only when ALL three children are ready (deterministic right
  after a regime switch).
* Children are injected via the existing factory/DI pattern (set_sub_providers),
  built from the provider registry's leaf factories — non-recursive.
* Deterministic regime detection: O(1) EMA of True Range + hysteresis, via the
  private methods _detect_regime() / _select_provider(). No helper classes.
* Persistence: only the provider-state shape changes (nested {stat, prev_close,
  regime, count, sub:{child states}}). No new schema/version. The Sprint 6G
  model-agnostic codec serializes it as-is.

## Modified (complete files; drop in at shown paths)
* backend/app/chart/renko/providers.py       — AdaptiveBrickSizeProvider + register "adaptive"
* backend/app/chart/renko/configuration.py   — adaptive_window / adaptive_thresholds / adaptive_hysteresis
* backend/app/chart/renko/factory.py         — non-recursive set_sub_providers injection
* backend/app/chart/renko/validator.py       — adaptive validation branch
* backend/app/chart/renko/__init__.py        — exports AdaptiveBrickSizeProvider
* backend/app/chart/renko/performance.py     — adaptive_engine() + ENGINE_BUILDERS["adaptive"]
* tests/test_percentage_provider.py          — registry assertion now includes "adaptive" (intent preserved)
* tests/test_price_reference_strategy.py     — same intent-preserving update
* conftest.py                                — repo root on sys.path (no PYTHONPATH needed)

## New
* tests/test_adaptive_provider.py            — 21 tests (regime/hysteresis/select, ready=all,
  reset cascade, validation valid+invalid, factory injection, engine integration,
  Adaptive x Hybrid, snapshot/restore/resume determinism, benchmark)

## Config example
    BrickConfiguration(provider="adaptive", brick_size=1.0, percentage=1.0,
        atr_period=14, atr_multiplier=0.75, adaptive_window=14,
        adaptive_thresholds=(1.0, 2.0), adaptive_hysteresis=0.1)
Children reuse existing brick_size / percentage / atr_period / atr_multiplier.

## Run (no PYTHONPATH needed)
    pytest -q                                          # 253 passing
    python -m backend.app.chart.renko.benchmark_runner --full

## Unchanged: engine.py, builder.py, snapshot.py, di.py, models.py, interfaces.py,
## plugin.py, manager.py, strategies.py, registry.py.
## Note: if your BrickConfiguration is a Pydantic model, add the three optional
## adaptive_* fields shown above.
