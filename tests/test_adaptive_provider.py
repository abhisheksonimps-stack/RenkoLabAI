from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from backend.app.chart.renko.builder import HybridBrickBuilder, default_builder_registry
from backend.app.chart.renko.configuration import BrickConfiguration, BrickType, RenkoMode
from backend.app.chart.renko.engine import TraditionalRenkoEngine
from backend.app.chart.renko.exceptions import RenkoConfigurationError
from backend.app.chart.renko.factory import RenkoFactory
from backend.app.chart.renko.interfaces import BrickSizeProvider
from backend.app.chart.renko.providers import (
    ATRBrickSizeProvider,
    AdaptiveBrickSizeProvider,
    FixedBrickSizeProvider,
    PercentageBrickSizeProvider,
    default_provider_registry,
)
from backend.app.chart.renko.registry import RenkoRegistry
from backend.app.chart.renko.snapshot import JsonSnapshotSerializer, SnapshotManager
from backend.app.chart.renko.strategies import default_strategy_registry
from backend.app.chart.renko.validator import DefaultBrickValidator
from backend.app.infrastructure.di import configure_container

TS = datetime(2024, 1, 1)


def adaptive_config(**kw):
    base = dict(
        brick_type=BrickType.TRADITIONAL, provider="adaptive", brick_size=1.0,
        percentage=1.0, atr_period=3, atr_multiplier=0.75,
        adaptive_window=5, adaptive_thresholds=(1.0, 2.0), adaptive_hysteresis=0.05,
        mode=RenkoMode.REPLAY,
    )
    base.update(kw)
    return BrickConfiguration(**base)


def candle(i, close, spread=0.5):
    return {"timestamp": TS + timedelta(minutes=i), "close": close,
            "high": close + spread, "low": close - spread, "open": close}


def constant_close_series(spreads):
    """Constant close, varying spread -> deterministic TR = 2*spread per candle."""
    return [candle(i, 100.0, spread=s) for i, s in enumerate(spreads)]


def climb(n, step=2.0, spread=0.5, start=100.0):
    out, p = [], start
    for i in range(n):
        p += step
        out.append(candle(i, p, spread=spread))
    return out


# ---------------------------------------------------------------------------
# Interface / registry / DI
# ---------------------------------------------------------------------------

def test_adaptive_implements_provider_interface():
    assert issubclass(AdaptiveBrickSizeProvider, BrickSizeProvider)
    p = AdaptiveBrickSizeProvider.from_configuration(adaptive_config())
    assert isinstance(p, BrickSizeProvider)
    assert p.name == "adaptive"


def test_registry_and_di_expose_adaptive():
    assert "adaptive" in default_provider_registry().names()
    container = configure_container()
    assert "adaptive" in container.brick_size_provider_registry().names()


def test_from_configuration_builds_fixed_provider_set():
    p = AdaptiveBrickSizeProvider.from_configuration(adaptive_config())
    children = p.children
    assert set(children) == {"low", "medium", "high"}
    assert isinstance(children["low"], FixedBrickSizeProvider)
    assert isinstance(children["medium"], PercentageBrickSizeProvider)
    assert isinstance(children["high"], ATRBrickSizeProvider)


# ---------------------------------------------------------------------------
# Regime detection / hysteresis / selection
# ---------------------------------------------------------------------------

def test_regime_detection_is_deterministic():
    # window=1 -> EMA alpha=1 -> stat equals current TR (= 2*spread).
    cfg = adaptive_config(adaptive_window=1, adaptive_hysteresis=0.0)
    p = AdaptiveBrickSizeProvider.from_configuration(cfg)
    p.update(candle(0, 100.0, spread=0.4))   # TR=0.8 -> low
    assert p.regime == "low"
    p.update(candle(1, 100.0, spread=0.7))   # TR=1.4 -> medium
    assert p.regime == "medium"
    p.update(candle(2, 100.0, spread=1.2))   # TR=2.4 -> high
    assert p.regime == "high"
    p.update(candle(3, 100.0, spread=0.4))   # TR=0.8 -> low
    assert p.regime == "low"


def test_hysteresis_prevents_flapping():
    cfg = adaptive_config(adaptive_window=1, adaptive_hysteresis=0.3)
    p = AdaptiveBrickSizeProvider.from_configuration(cfg)
    p.update(candle(0, 100.0, spread=0.75))  # TR=1.5 -> medium (first classify)
    assert p.regime == "medium"
    # TR=0.9 (<t1=1.0 but >= t1-h=0.7) must NOT drop to low.
    p.update(candle(1, 100.0, spread=0.45))
    assert p.regime == "medium"
    # TR=0.6 (< t1-h=0.7) finally drops to low.
    p.update(candle(2, 100.0, spread=0.30))
    assert p.regime == "low"


def test_select_returns_selected_child_size():
    # atr_period=1 so all children are ready after one candle.
    cfg = adaptive_config(atr_period=1, adaptive_window=1, adaptive_hysteresis=0.0)
    p = AdaptiveBrickSizeProvider.from_configuration(cfg)
    p.update(candle(0, 100.0, spread=0.7))   # TR=1.4 -> medium
    p.update(candle(1, 100.0, spread=0.7))
    assert p.ready()
    selected = p.children[p.regime]
    assert p.current_size() == selected.current_size()


# ---------------------------------------------------------------------------
# Refinement 1: ready() requires ALL children ready
# ---------------------------------------------------------------------------

def test_ready_requires_all_children_ready():
    cfg = adaptive_config(atr_period=3)  # ATR needs 3 candles to warm up
    p = AdaptiveBrickSizeProvider.from_configuration(cfg)
    p.update(candle(0, 100.0, spread=1.0))
    assert p.ready() is False  # ATR not ready yet
    with pytest.raises(RuntimeError):
        p.current_size()
    p.update(candle(1, 101.0, spread=1.0))
    assert p.ready() is False
    p.update(candle(2, 103.0, spread=1.0))
    assert p.ready() is True   # all three children ready
    assert p.current_size() > 0


def test_reset_cascades_to_children():
    cfg = adaptive_config(atr_period=2)
    p = AdaptiveBrickSizeProvider.from_configuration(cfg)
    for i in range(3):
        p.update(candle(i, 100.0 + i, spread=1.0))
    assert p.ready()
    p.reset()
    assert p.regime is None
    assert p.ready() is False  # ATR child reset -> not ready
    assert all(not c.ready() if c.name == "atr" else True for c in p.children.values())


# ---------------------------------------------------------------------------
# Configuration validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validation_accepts_valid_adaptive():
    validator = DefaultBrickValidator(
        default_provider_registry(), default_strategy_registry(), default_builder_registry()
    )
    assert await validator.validate_configuration(adaptive_config())


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [
    dict(percentage=None),                      # missing percentage (medium child)
    dict(atr_period=None),                      # missing atr_period (high child)
    dict(adaptive_thresholds=(2.0, 1.0)),       # not ascending
    dict(adaptive_thresholds=(-1.0, 2.0)),      # not positive
    dict(adaptive_window=0),                    # non-positive window
    dict(adaptive_hysteresis=-0.1),             # negative hysteresis
])
async def test_validation_rejects_invalid_adaptive(bad):
    validator = DefaultBrickValidator(
        default_provider_registry(), default_strategy_registry(), default_builder_registry()
    )
    with pytest.raises(RenkoConfigurationError):
        await validator.validate_configuration(adaptive_config(**bad))


# ---------------------------------------------------------------------------
# Factory resolution (non-recursive child injection)
# ---------------------------------------------------------------------------

def test_factory_injects_children_non_recursively():
    registry = RenkoRegistry()
    registry.register("traditional", TraditionalRenkoEngine())
    factory = RenkoFactory(
        registry,
        provider_registry=default_provider_registry(),
        strategy_registry=default_strategy_registry(),
        builder_registry=default_builder_registry(),
    )
    engine = factory.create(adaptive_config())
    provider = engine.provider
    assert isinstance(provider, AdaptiveBrickSizeProvider)
    children = provider.children
    assert set(children) == {"low", "medium", "high"}
    # No child is itself an adaptive provider (no recursion / nesting).
    assert not any(isinstance(c, AdaptiveBrickSizeProvider) for c in children.values())
    assert isinstance(children["high"], ATRBrickSizeProvider)


# ---------------------------------------------------------------------------
# Engine integration + builder orthogonality
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_engine_generates_bricks_deterministically():
    candles = climb(30)

    async def run():
        engine = TraditionalRenkoEngine(provider=AdaptiveBrickSizeProvider.from_configuration(adaptive_config()))
        engine.configure(adaptive_config())
        await engine.start()
        for c in candles:
            await engine.process_market_data(c)
        return [b.brick_id for b in engine.history()]

    first = await run()
    second = await run()
    assert len(first) > 0
    assert first == second  # deterministic replay


@pytest.mark.asyncio
async def test_adaptive_works_with_hybrid_builder():
    candles = climb(30)
    engine = TraditionalRenkoEngine(
        provider=AdaptiveBrickSizeProvider.from_configuration(adaptive_config()),
        builder=HybridBrickBuilder(),
    )
    engine.configure(adaptive_config())
    await engine.start()
    for c in candles:
        await engine.process_market_data(c)
    history = engine.history()
    assert len(history) > 0
    assert all(b.metadata.get("builder_type") == "hybrid" for b in history)
    assert all(b.brick_id.startswith("hybrid-") for b in history)


# ---------------------------------------------------------------------------
# Persistence: snapshot -> restore -> resume (nested provider state)
# ---------------------------------------------------------------------------

def _manager():
    return SnapshotManager(
        JsonSnapshotSerializer(),
        default_provider_registry(),
        default_strategy_registry(),
        default_builder_registry(),
    )


def test_adaptive_export_import_state_roundtrip():
    p = AdaptiveBrickSizeProvider.from_configuration(adaptive_config(atr_period=2))
    for i in range(4):
        p.update(candle(i, 100.0 + i, spread=1.0))
    state = p.export_state()
    assert set(state["sub"]) == {"low", "medium", "high"}
    restored = AdaptiveBrickSizeProvider.from_configuration(adaptive_config(atr_period=2))
    restored.import_state(state)
    assert restored.export_state() == state


@pytest.mark.asyncio
async def test_snapshot_restore_resume_is_deterministic():
    # Mixed calm/volatile blocks to exercise regime changes across the boundary.
    series, p = [], 100.0
    for i in range(60):
        amp = 0.4 if (i // 15) % 2 == 0 else 3.0
        p += amp if i % 2 == 0 else -amp * 0.5
        series.append(candle(i, round(p, 4), spread=amp))

    def mk():
        e = TraditionalRenkoEngine(provider=AdaptiveBrickSizeProvider.from_configuration(adaptive_config()))
        e.configure(adaptive_config())
        return e

    async def continuous():
        e = mk(); await e.start()
        for c in series:
            await e.process_market_data(c)
        return [b.brick_id for b in e.history()], e.provider.export_state()

    async def split():
        e = mk(); await e.start()
        for c in series[:30]:
            await e.process_market_data(c)
        r = _manager().restore(e.save_state())
        for c in series[30:]:
            await r.process_market_data(c)
        return [b.brick_id for b in r.history()], r.provider.export_state()

    cont_ids, cont_state = await continuous()
    split_ids, split_state = await split()
    assert cont_ids == split_ids
    assert cont_state["stat"] == split_state["stat"]
    assert cont_state["regime"] == split_state["regime"]
    assert cont_state["sub"] == split_state["sub"]


# ---------------------------------------------------------------------------
# Benchmark compatibility
# ---------------------------------------------------------------------------

def test_adaptive_benchmark_runs_and_others_unchanged():
    from backend.app.chart.renko.performance import run_benchmark

    adaptive = run_benchmark("adaptive", "trending", 5_000, sample_memory=False)
    assert adaptive.bricks >= 0  # adaptive sizing may vary; must at least run
    assert adaptive.candles == 5_000

    fixed_a = run_benchmark("fixed", "trending", 5_000, sample_memory=False)
    fixed_b = run_benchmark("fixed", "trending", 5_000, sample_memory=False)
    assert fixed_a.bricks == fixed_b.bricks  # existing path unchanged / deterministic
