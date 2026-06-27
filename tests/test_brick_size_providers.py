from __future__ import annotations

import sys
from datetime import datetime, timedelta

import pytest

from backend.app.chart.renko.configuration import (
    BrickConfiguration,
    BrickType,
    PriceSource,
    RenkoMode,
)
from backend.app.chart.renko.engine import TraditionalRenkoEngine
from backend.app.chart.renko.events import (
    BrickExtended,
    BrickOpened,
    BrickReversed,
    BrickSizeUpdated,
)
from backend.app.chart.renko.exceptions import RenkoConfigurationError
from backend.app.chart.renko.factory import RenkoFactory
from backend.app.chart.renko.interfaces import BrickSizeProvider
from backend.app.chart.renko.models import BrickDirection
from backend.app.chart.renko.pipeline import RenkoPipelineStage
from backend.app.chart.renko.providers import (
    ATRBrickSizeProvider,
    BrickSizeProviderRegistry,
    FixedBrickSizeProvider,
    default_provider_registry,
)
from backend.app.chart.renko.registry import RenkoRegistry
from backend.app.chart.renko.validator import DefaultBrickValidator
from backend.app.events.bus import EventBus
from backend.app.pipeline.context import PipelineContext


TS = datetime(2024, 1, 1, 0, 0, 0)


def candle(close, high=None, low=None, ts=TS, **extra):
    data = {"timestamp": ts, "close": close}
    if high is not None:
        data["high"] = high
    if low is not None:
        data["low"] = low
    data.update(extra)
    return data


# ---------------------------------------------------------------------------
# Fixed provider
# ---------------------------------------------------------------------------

def test_fixed_provider_is_immediately_ready_and_constant():
    provider = FixedBrickSizeProvider(2.5)
    assert provider.ready() is True
    assert provider.current_size() == 2.5
    provider.update(candle(100.0))
    assert provider.current_size() == 2.5  # candle does not change a fixed size


def test_fixed_provider_rejects_non_positive_size():
    with pytest.raises(RenkoConfigurationError):
        FixedBrickSizeProvider(0.0)


def test_fixed_provider_reset_keeps_configured_size():
    provider = FixedBrickSizeProvider(3.0)
    provider.reset()
    assert provider.ready() is True
    assert provider.current_size() == 3.0


@pytest.mark.asyncio
async def test_fixed_provider_regression_matches_default_fixed_engine():
    """Sprint 6B regression: an explicit FixedBrickSizeProvider must produce
    identical brick output AND identical event sequence to the default
    (config-derived) fixed path."""
    closes = [100.0, 104.0, 98.0, 103.0, 100.99]

    async def run(provider):
        bus = EventBus()
        seq: list[str] = []

        async def handler(event):
            seq.append(type(event).__name__)

        bus.subscribe(BrickOpened, handler)
        bus.subscribe(BrickExtended, handler)
        bus.subscribe(BrickReversed, handler)

        engine = TraditionalRenkoEngine(event_bus=bus, provider=provider)
        engine.configure(
            BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0, mode=RenkoMode.REPLAY)
        )
        await engine.start()
        for c in closes:
            await engine.process_market_data(candle(c))
        bricks = [(b.direction, b.open_price, b.close_price) for b in engine.history()]
        return bricks, seq

    explicit_bricks, explicit_events = await run(FixedBrickSizeProvider(1.0))
    default_bricks, default_events = await run(None)  # default = config-derived fixed

    assert explicit_bricks == default_bricks
    assert explicit_events == default_events
    # Lock the known 6B algorithm output: 4 UP, reversal to DOWN, etc.
    assert default_bricks[0] == (BrickDirection.UP, 100.0, 101.0)
    assert sum(1 for b in default_bricks if b[0] == BrickDirection.UP) >= 4


# ---------------------------------------------------------------------------
# ATR provider
# ---------------------------------------------------------------------------

def test_true_range_first_candle_uses_high_low():
    assert ATRBrickSizeProvider.true_range(10.0, 8.0, None) == 2.0


def test_true_range_uses_previous_close():
    # gap up: prev_close below the low
    assert ATRBrickSizeProvider.true_range(14.0, 11.0, 11.5) == 3.0
    # prev_close above the high (gap down)
    assert ATRBrickSizeProvider.true_range(11.0, 9.0, 13.0) == pytest.approx(4.0)


def test_atr_warmup_then_seed_is_mean_of_true_ranges():
    provider = ATRBrickSizeProvider(atr_period=3, atr_multiplier=1.0)
    provider.update(candle(9.0, high=10.0, low=8.0))   # TR 2
    assert not provider.ready()
    with pytest.raises(RuntimeError):
        provider.current_size()
    provider.update(candle(10.0, high=11.0, low=9.0))  # TR 2
    assert not provider.ready()
    provider.update(candle(11.5, high=12.0, low=10.0)) # TR 2 -> seed
    assert provider.ready()
    assert provider.atr == pytest.approx(2.0)
    assert provider.current_size() == pytest.approx(2.0)


def test_atr_rolling_update_uses_wilder_smoothing():
    provider = ATRBrickSizeProvider(atr_period=3, atr_multiplier=1.0)
    for c in (
        candle(9.0, high=10.0, low=8.0),
        candle(10.0, high=11.0, low=9.0),
        candle(11.5, high=12.0, low=10.0),
    ):
        provider.update(c)
    assert provider.atr == pytest.approx(2.0)
    provider.update(candle(13.0, high=14.0, low=11.0))  # TR 3
    # Wilder: (2.0*2 + 3)/3 = 7/3
    assert provider.atr == pytest.approx(7.0 / 3.0)


def test_atr_multiplier_scales_size():
    provider = ATRBrickSizeProvider(atr_period=2, atr_multiplier=2.5)
    provider.update(candle(9.0, high=10.0, low=8.0))   # TR 2
    provider.update(candle(10.0, high=11.0, low=9.0))  # TR 2 -> seed 2.0
    assert provider.current_size() == pytest.approx(5.0)


def test_atr_rejects_invalid_configuration():
    with pytest.raises(RenkoConfigurationError):
        ATRBrickSizeProvider(atr_period=0, atr_multiplier=1.0)
    with pytest.raises(RenkoConfigurationError):
        ATRBrickSizeProvider(atr_period=3, atr_multiplier=0.0)


def test_atr_reset_clears_state():
    provider = ATRBrickSizeProvider(atr_period=2, atr_multiplier=1.0)
    provider.update(candle(9.0, high=10.0, low=8.0))
    provider.update(candle(10.0, high=11.0, low=9.0))
    assert provider.ready()
    provider.reset()
    assert not provider.ready()
    assert provider.atr is None
    with pytest.raises(RuntimeError):
        provider.current_size()


def test_atr_replay_determinism_and_reset_replay():
    candles = [
        candle(9.0, high=10.0, low=8.0),
        candle(10.0, high=11.0, low=9.0),
        candle(11.5, high=12.0, low=10.0),
        candle(13.0, high=14.0, low=11.0),
        candle(12.0, high=13.5, low=11.0),
    ]

    def run(provider):
        out = []
        for c in candles:
            provider.update(c)
            out.append(provider.current_size() if provider.ready() else None)
        return out

    first = run(ATRBrickSizeProvider(atr_period=3, atr_multiplier=1.0))
    second = run(ATRBrickSizeProvider(atr_period=3, atr_multiplier=1.0))
    assert first == second

    # Replay after reset on the same instance must reproduce identical output.
    p = ATRBrickSizeProvider(atr_period=3, atr_multiplier=1.0)
    run_a = run(p)
    p.reset()
    run_b = run(p)
    assert run_a == run_b == first


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

def test_default_registry_resolves_builtin_providers():
    reg = default_provider_registry()
    assert reg.exists("fixed")
    assert reg.exists("atr")
    fixed = reg.create(BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0))
    atr = reg.create(
        BrickConfiguration(brick_type=BrickType.ATR, brick_size=1.0, atr_period=5, atr_multiplier=2.0)
    )
    assert isinstance(fixed, FixedBrickSizeProvider)
    assert isinstance(atr, ATRBrickSizeProvider)


def test_registry_rejects_duplicate_and_missing():
    reg = BrickSizeProviderRegistry()
    reg.register("fixed", FixedBrickSizeProvider.from_configuration)
    with pytest.raises(ValueError):
        reg.register("fixed", FixedBrickSizeProvider.from_configuration)
    with pytest.raises(KeyError):
        reg.get("missing")


def test_registry_supports_plugin_registered_provider():
    """Plugins must be able to register additional providers later."""
    reg = default_provider_registry()

    class ConstantTwoProvider(BrickSizeProvider):
        def update(self, candle):
            return None

        def current_size(self):
            return 2.0

        def ready(self):
            return True

        def reset(self):
            return None

    reg.register("constant_two", lambda cfg: ConstantTwoProvider())
    cfg = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0, provider="constant_two")
    provider = reg.create(cfg)
    assert isinstance(provider, ConstantTwoProvider)
    assert provider.current_size() == 2.0


def test_resolved_provider_backwards_compatible():
    # Old fixed config (no provider field) resolves to "fixed".
    legacy = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0)
    assert legacy.resolved_provider() == "fixed"
    # ATR brick type without explicit provider resolves to "atr".
    atr = BrickConfiguration(brick_type=BrickType.ATR, brick_size=1.0, atr_period=3)
    assert atr.resolved_provider() == "atr"
    # Explicit provider wins.
    explicit = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0, provider="atr")
    assert explicit.resolved_provider() == "atr"


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validator_rejects_non_positive_atr_multiplier():
    validator = DefaultBrickValidator()
    cfg = BrickConfiguration(brick_type=BrickType.ATR, brick_size=1.0, atr_period=3, atr_multiplier=0.0)
    with pytest.raises(RenkoConfigurationError):
        await validator.validate_configuration(cfg)


@pytest.mark.asyncio
async def test_validator_rejects_unknown_provider():
    validator = DefaultBrickValidator(provider_registry=default_provider_registry())
    cfg = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0, provider="does_not_exist")
    with pytest.raises(RenkoConfigurationError):
        await validator.validate_configuration(cfg)


@pytest.mark.asyncio
async def test_validator_accepts_known_provider():
    validator = DefaultBrickValidator(provider_registry=default_provider_registry())
    cfg = BrickConfiguration(
        brick_type=BrickType.ATR, brick_size=1.0, atr_period=3, atr_multiplier=2.0, provider="atr"
    )
    assert await validator.validate_configuration(cfg)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def test_factory_injects_correct_provider_per_configuration():
    registry = RenkoRegistry()
    registry.register("traditional", TraditionalRenkoEngine())
    registry.register("atr", TraditionalRenkoEngine())
    factory = RenkoFactory(registry, provider_registry=default_provider_registry())

    fixed_engine = factory.create(BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0))
    assert isinstance(fixed_engine.provider, FixedBrickSizeProvider)

    atr_engine = factory.create(
        BrickConfiguration(brick_type=BrickType.ATR, brick_size=1.0, atr_period=4, atr_multiplier=1.5)
    )
    assert isinstance(atr_engine.provider, ATRBrickSizeProvider)


def test_factory_without_provider_registry_is_backwards_compatible():
    registry = RenkoRegistry()
    engine = TraditionalRenkoEngine()
    registry.register("traditional", engine)
    factory = RenkoFactory(registry)
    assert factory.create(BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=2.0)) is engine


# ---------------------------------------------------------------------------
# Engine integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_engine_with_fixed_provider_generates_bricks():
    engine = TraditionalRenkoEngine(provider=FixedBrickSizeProvider(1.0))
    engine.configure(BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0, mode=RenkoMode.REPLAY))
    await engine.start()
    await engine.process_market_data(candle(100.0))
    await engine.process_market_data(candle(104.0))
    history = engine.history()
    assert len(history) == 4
    assert all(b.direction == BrickDirection.UP for b in history)


@pytest.mark.asyncio
async def test_engine_with_atr_provider_warms_up_then_generates():
    provider = ATRBrickSizeProvider(atr_period=3, atr_multiplier=1.0)
    engine = TraditionalRenkoEngine(provider=provider)
    engine.configure(
        BrickConfiguration(
            brick_type=BrickType.ATR, brick_size=1.0, atr_period=3, atr_multiplier=1.0, mode=RenkoMode.REPLAY
        )
    )
    await engine.start()

    # Warm-up candles (period 3): each TR == 1.0, so seed ATR == 1.0.
    await engine.process_market_data(candle(100.0, high=100.5, low=99.5))
    await engine.process_market_data(candle(100.2, high=100.7, low=99.7))
    assert engine.history() == ()  # still warming up -> no bricks
    await engine.process_market_data(candle(100.1, high=100.6, low=99.6))  # ready; anchor candle
    assert engine.history() == ()  # first ready candle only anchors

    # Now ATR ~1.0. A sustained uptrend produces a stream of UP bricks. (Each
    # trending candle's own True Range nudges the ATR, so size adapts as we go.)
    for px in (102.0, 104.0, 106.0, 108.0):
        await engine.process_market_data(candle(px, high=px + 0.1, low=px - 2.0))
    history = engine.history()
    assert len(history) >= 2
    assert all(b.direction == BrickDirection.UP for b in history)


@pytest.mark.asyncio
async def test_engine_atr_brick_size_can_change_across_candles():
    provider = ATRBrickSizeProvider(atr_period=2, atr_multiplier=1.0)
    engine = TraditionalRenkoEngine(provider=provider)
    engine.configure(
        BrickConfiguration(
            brick_type=BrickType.ATR, brick_size=1.0, atr_period=2, atr_multiplier=1.0, mode=RenkoMode.REPLAY
        )
    )
    await engine.start()
    await engine.process_market_data(candle(100.0, high=101.0, low=99.0))   # TR 2
    await engine.process_market_data(candle(100.0, high=101.0, low=99.0))   # TR 2 -> ATR 2.0 (anchor)
    size_after_seed = provider.current_size()
    await engine.process_market_data(candle(100.0, high=110.0, low=99.0))   # large TR widens ATR
    assert provider.current_size() != size_after_seed


@pytest.mark.asyncio
async def test_engine_reset_resets_provider_and_replays_identically():
    def build():
        p = ATRBrickSizeProvider(atr_period=2, atr_multiplier=1.0)
        e = TraditionalRenkoEngine(provider=p)
        e.configure(
            BrickConfiguration(
                brick_type=BrickType.ATR, brick_size=1.0, atr_period=2, atr_multiplier=1.0, mode=RenkoMode.REPLAY
            )
        )
        return e

    closes = [
        candle(100.0, high=101.0, low=99.0),
        candle(100.0, high=101.0, low=99.0),
        candle(104.0, high=104.0, low=100.0),
    ]

    engine = build()
    await engine.start()
    for c in closes:
        await engine.process_market_data(c)
    first_ids = [b.brick_id for b in engine.history()]

    await engine.reset()
    assert engine.history() == ()
    assert not engine.provider.ready()  # provider state cleared

    engine.configure(
        BrickConfiguration(
            brick_type=BrickType.ATR, brick_size=1.0, atr_period=2, atr_multiplier=1.0, mode=RenkoMode.REPLAY
        )
    )
    await engine.start()
    for c in closes:
        await engine.process_market_data(c)
    second_ids = [b.brick_id for b in engine.history()]

    assert first_ids == second_ids


@pytest.mark.asyncio
async def test_engine_publishes_brick_size_updated_event():
    bus = EventBus()
    events = []

    async def handler(event):
        events.append(event)

    bus.subscribe(BrickSizeUpdated, handler)

    provider = ATRBrickSizeProvider(atr_period=1, atr_multiplier=1.0)
    engine = TraditionalRenkoEngine(event_bus=bus, provider=provider)
    engine.configure(
        BrickConfiguration(
            brick_type=BrickType.ATR, brick_size=1.0, atr_period=1, atr_multiplier=1.0, mode=RenkoMode.REPLAY
        )
    )
    await engine.start()
    await engine.process_market_data(candle(100.0, high=101.0, low=99.0))
    assert any(isinstance(e, BrickSizeUpdated) for e in events)
    assert events[0].provider == "atr"


# ---------------------------------------------------------------------------
# Pipeline + events
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_runs_atr_engine_and_publishes_size_event():
    bus = EventBus()
    registry = RenkoRegistry()
    registry.register("atr", TraditionalRenkoEngine(event_bus=bus))
    factory = RenkoFactory(registry, provider_registry=default_provider_registry())
    validator = DefaultBrickValidator(provider_registry=default_provider_registry())

    size_events = []

    async def handler(event):
        size_events.append(event)

    bus.subscribe(BrickSizeUpdated, handler)

    stage = RenkoPipelineStage(factory, validator, bus)
    context = PipelineContext()
    context.set(
        "renko_configuration",
        BrickConfiguration(brick_type=BrickType.ATR, brick_size=1.0, atr_period=1, atr_multiplier=1.0),
    )
    context.set("aggregated_market_data", candle(100.0, high=101.0, low=99.0))

    result = await stage.execute(context)
    assert result.status.name == "SUCCESS"
    assert context.get("renko_engine").provider.__class__ is ATRBrickSizeProvider
    assert any(isinstance(e, BrickSizeUpdated) for e in size_events)


# ---------------------------------------------------------------------------
# Performance / scaling
# ---------------------------------------------------------------------------

def test_atr_provider_uses_constant_memory_over_large_replay():
    """The provider must not accumulate per-candle history (no full recompute)."""
    provider = ATRBrickSizeProvider(atr_period=14, atr_multiplier=1.0)

    def footprint():
        return sorted(provider.__dict__.keys()), sum(
            sys.getsizeof(v) for v in provider.__dict__.values()
        )

    provider.update(candle(100.0, high=101.0, low=99.0))
    keys_small, size_small = footprint()

    for i in range(200_000):
        provider.update(candle(100.0 + (i % 5), high=101.0 + (i % 5), low=99.0 + (i % 5)))

    keys_large, size_large = footprint()

    # Same attributes, and no container grew with candle count.
    assert keys_small == keys_large
    assert size_large <= size_small + 64  # only scalar fields; no growth
    for value in provider.__dict__.values():
        assert not isinstance(value, (list, tuple, dict, set))


@pytest.mark.asyncio
async def test_engine_large_atr_replay_scales_linearly():
    import time

    def make_engine():
        p = ATRBrickSizeProvider(atr_period=14, atr_multiplier=1.0)
        e = TraditionalRenkoEngine(provider=p)
        e.configure(
            BrickConfiguration(
                brick_type=BrickType.ATR, brick_size=1.0, atr_period=14, atr_multiplier=1.0, mode=RenkoMode.REPLAY
            )
        )
        return e

    async def replay(n):
        engine = make_engine()
        await engine.start()
        price = 100.0
        for i in range(n):
            price += 0.25 if (i // 50) % 2 == 0 else -0.25
            await engine.process_market_data(candle(price, high=price + 0.5, low=price - 0.5))
        return engine

    start = time.perf_counter()
    await replay(2_000)
    t_small = time.perf_counter() - start

    start = time.perf_counter()
    await replay(8_000)
    t_large = time.perf_counter() - start

    # 4x the candles should take well under 10x the time if per-candle work is
    # O(1) (no recompute over the full history). Generous bound avoids flakiness.
    assert t_large < t_small * 10
