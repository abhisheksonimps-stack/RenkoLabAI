from __future__ import annotations

from datetime import datetime

import pytest

from backend.app.chart.renko.configuration import (
    BrickConfiguration,
    BrickType,
    ReferencePrice,
    RenkoMode,
    RoundingMode,
)
from backend.app.chart.renko.engine import TraditionalRenkoEngine
from backend.app.chart.renko.exceptions import RenkoConfigurationError
from backend.app.chart.renko.factory import RenkoFactory
from backend.app.chart.renko.models import BrickDirection
from backend.app.chart.renko.providers import (
    ATRBrickSizeProvider,
    FixedBrickSizeProvider,
    PercentageBrickSizeProvider,
    default_provider_registry,
)
from backend.app.chart.renko.registry import RenkoRegistry
from backend.app.chart.renko.validator import DefaultBrickValidator


TS = datetime(2024, 1, 1, 0, 0, 0)


def candle(close, high=None, low=None, open_=None, ts=TS):
    data = {"timestamp": ts, "close": close}
    if high is not None:
        data["high"] = high
    if low is not None:
        data["low"] = low
    if open_ is not None:
        data["open"] = open_
    return data


def pct_config(**kw):
    base = dict(brick_type=BrickType.PERCENTAGE, brick_size=1.0, percentage=1.0, mode=RenkoMode.REPLAY)
    base.update(kw)
    return BrickConfiguration(**base)


# ---------------------------------------------------------------------------
# Provider: percentage maths
# ---------------------------------------------------------------------------

def test_percentage_one_percent():
    p = PercentageBrickSizeProvider(percentage=1.0)
    p.update(candle(100.0))
    assert p.current_size() == pytest.approx(1.0)
    # Future candle changes the size; historical bricks (engine) are unaffected.
    p.update(candle(250.0))
    assert p.current_size() == pytest.approx(2.5)


def test_percentage_half_percent():
    p = PercentageBrickSizeProvider(percentage=0.5)
    p.update(candle(200.0))
    assert p.current_size() == pytest.approx(1.0)


def test_percentage_two_percent():
    p = PercentageBrickSizeProvider(percentage=2.0)
    p.update(candle(250.0))
    assert p.current_size() == pytest.approx(5.0)


def test_percentage_not_ready_before_first_candle():
    p = PercentageBrickSizeProvider(percentage=1.0)
    assert p.ready() is False
    with pytest.raises(RuntimeError):
        p.current_size()
    p.update(candle(100.0))
    assert p.ready() is True


# ---------------------------------------------------------------------------
# Provider: reference price selection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "source, expected",
    [
        (ReferencePrice.CLOSE, 1.0),       # close 100
        (ReferencePrice.OPEN, 0.9),        # open 90
        (ReferencePrice.HIGH, 1.2),        # high 120
        (ReferencePrice.LOW, 0.8),         # low 80
        (ReferencePrice.TYPICAL_PRICE, 1.0),   # (120+80+100)/3 = 100 -> 1.0
        (ReferencePrice.MEDIAN_PRICE, 1.0),    # (120+80)/2 = 100 -> 1.0
    ],
)
def test_reference_price_selection(source, expected):
    p = PercentageBrickSizeProvider(percentage=1.0, reference_price=source)
    p.update(candle(100.0, high=120.0, low=80.0, open_=90.0))
    assert p.current_size() == pytest.approx(expected)


def test_reference_price_falls_back_to_close_when_field_missing():
    p = PercentageBrickSizeProvider(percentage=1.0, reference_price=ReferencePrice.HIGH)
    p.update(candle(100.0))  # no high -> falls back to close
    assert p.current_size() == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Provider: rounding
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "mode, expected",
    [
        (RoundingMode.NONE, 2.5),
        (RoundingMode.ROUND, 3.0),  # round-half-up
        (RoundingMode.FLOOR, 2.0),
        (RoundingMode.CEIL, 3.0),
    ],
)
def test_rounding_modes(mode, expected):
    p = PercentageBrickSizeProvider(percentage=1.0, rounding_mode=mode)
    p.update(candle(250.0))  # raw 2.5
    assert p.current_size() == pytest.approx(expected)


def test_rounding_never_yields_non_positive_size():
    # 1% of 10 = 0.1, floor -> 0; with no minimum, fall back to the exact value.
    p = PercentageBrickSizeProvider(percentage=1.0, rounding_mode=RoundingMode.FLOOR)
    p.update(candle(10.0))
    assert p.current_size() == pytest.approx(0.1)
    assert p.current_size() > 0


# ---------------------------------------------------------------------------
# Provider: minimum brick size
# ---------------------------------------------------------------------------

def test_minimum_brick_size_floor_is_enforced():
    p = PercentageBrickSizeProvider(percentage=1.0, minimum_brick_size=0.5)
    p.update(candle(10.0))  # raw 0.1 -> floored up to 0.5
    assert p.current_size() == pytest.approx(0.5)


def test_minimum_brick_size_not_applied_when_above():
    p = PercentageBrickSizeProvider(percentage=1.0, minimum_brick_size=0.5)
    p.update(candle(100.0))  # raw 1.0 > 0.5
    assert p.current_size() == pytest.approx(1.0)


def test_minimum_brick_size_must_be_positive():
    with pytest.raises(RenkoConfigurationError):
        PercentageBrickSizeProvider(percentage=1.0, minimum_brick_size=0.0)


# ---------------------------------------------------------------------------
# Provider: config validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [0.0, -1.0, 150.0])
def test_percentage_bounds_rejected(bad):
    with pytest.raises(RenkoConfigurationError):
        PercentageBrickSizeProvider(percentage=bad)


# ---------------------------------------------------------------------------
# Provider: reset + replay determinism
# ---------------------------------------------------------------------------

def test_reset_clears_state():
    p = PercentageBrickSizeProvider(percentage=1.0)
    p.update(candle(100.0))
    assert p.ready()
    p.reset()
    assert not p.ready()
    with pytest.raises(RuntimeError):
        p.current_size()


def test_replay_determinism_and_reset_replay():
    closes = [candle(100.0), candle(250.0), candle(123.45), candle(50.0)]

    def run(provider):
        out = []
        for c in closes:
            provider.update(c)
            out.append(provider.current_size())
        return out

    first = run(PercentageBrickSizeProvider(percentage=1.0))
    second = run(PercentageBrickSizeProvider(percentage=1.0))
    assert first == second

    p = PercentageBrickSizeProvider(percentage=1.0)
    a = run(p)
    p.reset()
    b = run(p)
    assert a == b == first


# ---------------------------------------------------------------------------
# Registry / factory / validator integration
# ---------------------------------------------------------------------------

def test_registry_resolves_percentage_provider():
    reg = default_provider_registry()
    assert reg.exists("percentage")
    provider = reg.create(pct_config(percentage=2.0))
    assert isinstance(provider, PercentageBrickSizeProvider)
    assert provider.percentage == 2.0


def test_configuration_resolves_percentage():
    assert pct_config().resolved_provider() == "percentage"
    # provider override on a traditional brick type still resolves.
    override = BrickConfiguration(
        brick_type=BrickType.TRADITIONAL, brick_size=1.0, provider="percentage", percentage=1.0
    )
    assert override.resolved_provider() == "percentage"


def test_factory_injects_percentage_provider():
    registry = RenkoRegistry()
    registry.register("percentage", TraditionalRenkoEngine())
    factory = RenkoFactory(registry, provider_registry=default_provider_registry())
    engine = factory.create(pct_config(percentage=1.0))
    assert isinstance(engine.provider, PercentageBrickSizeProvider)


@pytest.mark.asyncio
async def test_validator_accepts_valid_percentage_config():
    validator = DefaultBrickValidator(provider_registry=default_provider_registry())
    cfg = pct_config(
        percentage=1.0,
        reference_price=ReferencePrice.TYPICAL_PRICE,
        rounding_mode=RoundingMode.FLOOR,
        minimum_brick_size=0.5,
    )
    assert await validator.validate_configuration(cfg)


@pytest.mark.asyncio
async def test_validator_rejects_percentage_over_100():
    validator = DefaultBrickValidator(provider_registry=default_provider_registry())
    with pytest.raises(RenkoConfigurationError):
        await validator.validate_configuration(pct_config(percentage=101.0))


# ---------------------------------------------------------------------------
# Engine integration
# ---------------------------------------------------------------------------

def make_engine(**cfg_kw):
    provider = PercentageBrickSizeProvider.from_configuration(pct_config(**cfg_kw))
    engine = TraditionalRenkoEngine(provider=provider)
    engine.configure(pct_config(**cfg_kw))
    return engine


@pytest.mark.asyncio
async def test_engine_continuation_with_percentage_provider():
    # The size is derived from the move candle's own price (1% of 103 = 1.03),
    # so +3 from the anchor yields 2 UP bricks of size 1.03.
    engine = make_engine(percentage=1.0)
    await engine.start()
    await engine.process_market_data(candle(100.0))  # anchor
    await engine.process_market_data(candle(103.0))
    history = engine.history()
    assert len(history) == 2
    assert all(b.direction == BrickDirection.UP for b in history)
    assert history[0].open_price == 100.0
    assert all(round(b.close_price - b.open_price, 6) == 1.03 for b in history)


@pytest.mark.asyncio
async def test_engine_reversal_with_percentage_provider():
    engine = make_engine(percentage=1.0)
    await engine.start()
    await engine.process_market_data(candle(100.0))  # anchor, size 1.0
    await engine.process_market_data(candle(98.0))   # down 2 -> reversal (2 DOWN)
    history = engine.history()
    assert len(history) == 2
    assert all(b.direction == BrickDirection.DOWN for b in history)


@pytest.mark.asyncio
async def test_engine_gap_creates_multiple_bricks():
    engine = make_engine(percentage=1.0)
    await engine.start()
    await engine.process_market_data(candle(100.0))   # anchor
    await engine.process_market_data(candle(110.0))   # size 1% of 110 = 1.1 -> 9 UP bricks
    history = engine.history()
    assert len(history) == 9
    assert all(b.direction == BrickDirection.UP for b in history)
    assert all(round(b.close_price - b.open_price, 6) == 1.1 for b in history)
    assert history[-1].close_price == pytest.approx(109.9)


@pytest.mark.asyncio
async def test_engine_history_is_immutable_when_size_changes():
    """Historical bricks keep their original size; only future bricks resize."""
    engine = make_engine(percentage=1.0)
    await engine.start()
    await engine.process_market_data(candle(100.0))  # anchor
    await engine.process_market_data(candle(103.0))  # 2 UP bricks at size 1.03
    early = engine.history()
    early_snapshot = [(b.open_price, b.close_price) for b in early]
    assert len(early) == 2
    assert all(round(b.close_price - b.open_price, 6) == 1.03 for b in early)

    # Price jumps to ~203; new size = 1% of 203 = 2.03 for subsequent bricks.
    await engine.process_market_data(candle(203.0))
    full = engine.history()
    # The original bricks are unchanged (immutable history).
    assert [(b.open_price, b.close_price) for b in full[: len(early)]] == early_snapshot
    # New, larger bricks were produced beyond the originals.
    assert len(full) > len(early)
    new_brick = full[len(early)]
    assert round(new_brick.close_price - new_brick.open_price, 6) == 2.03


@pytest.mark.asyncio
async def test_engine_replay_determinism_with_percentage():
    closes = [100.0, 103.0, 98.0, 250.0, 255.0]

    async def run():
        engine = make_engine(percentage=1.0)
        await engine.start()
        for c in closes:
            await engine.process_market_data(candle(c))
        return [b.brick_id for b in engine.history()]

    assert await run() == await run()


# ---------------------------------------------------------------------------
# Regression: fixed + ATR providers remain unchanged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_regression_fixed_provider_unchanged():
    engine = TraditionalRenkoEngine(provider=FixedBrickSizeProvider(1.0))
    engine.configure(
        BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0, mode=RenkoMode.REPLAY)
    )
    await engine.start()
    await engine.process_market_data(candle(100.0))
    await engine.process_market_data(candle(104.0))
    history = engine.history()
    assert len(history) == 4
    assert all(b.direction == BrickDirection.UP for b in history)


def test_regression_atr_provider_unchanged():
    p = ATRBrickSizeProvider(atr_period=3, atr_multiplier=1.0)
    for c in (
        candle(9.0, high=10.0, low=8.0),
        candle(10.0, high=11.0, low=9.0),
        candle(11.5, high=12.0, low=10.0),
    ):
        p.update(c)
    assert p.current_size() == pytest.approx(2.0)


def test_regression_default_registry_has_all_three_providers():
    reg = default_provider_registry()
    assert reg.names() == ["fixed", "atr", "percentage"]


# ---------------------------------------------------------------------------
# Performance: O(1) update, no historical recalculation
# ---------------------------------------------------------------------------

def test_percentage_provider_uses_constant_memory():
    import sys

    provider = PercentageBrickSizeProvider(percentage=1.0)
    provider.update(candle(100.0))
    keys_small = sorted(provider.__dict__.keys())
    size_small = sum(sys.getsizeof(v) for v in provider.__dict__.values())

    for i in range(200_000):
        provider.update(candle(100.0 + (i % 7)))

    keys_large = sorted(provider.__dict__.keys())
    size_large = sum(sys.getsizeof(v) for v in provider.__dict__.values())

    assert keys_small == keys_large
    assert size_large <= size_small + 64  # only scalar fields; no growth
    for value in provider.__dict__.values():
        assert not isinstance(value, (list, tuple, dict, set))
