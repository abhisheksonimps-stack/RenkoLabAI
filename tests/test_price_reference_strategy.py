from __future__ import annotations

import pathlib
import tempfile
from datetime import datetime

import pytest

from backend.app.chart.renko.configuration import (
    BrickConfiguration,
    BrickType,
    ReferencePrice,
    RenkoMode,
)
from backend.app.chart.renko.engine import TraditionalRenkoEngine
from backend.app.chart.renko.exceptions import RenkoConfigurationError
from backend.app.chart.renko.factory import RenkoFactory
from backend.app.chart.renko.interfaces import PriceReferenceStrategy
from backend.app.chart.renko.providers import PercentageBrickSizeProvider, default_provider_registry
from backend.app.chart.renko.registry import RenkoRegistry
from backend.app.chart.renko.strategies import (
    ClosePriceStrategy,
    HighPriceStrategy,
    LowPriceStrategy,
    MeanPriceStrategy,
    MedianPriceStrategy,
    OpenPriceStrategy,
    PriceReferenceStrategyRegistry,
    TypicalPriceStrategy,
    default_strategy_registry,
)
from backend.app.chart.renko.validator import DefaultBrickValidator
from backend.app.infrastructure.di import configure_container
from backend.app.plugins.manager import PluginManager


TS = datetime(2024, 1, 1, 0, 0, 0)
CANDLE = {"timestamp": TS, "open": 90.0, "high": 120.0, "low": 80.0, "close": 100.0}


# =====================================================================
# Phase 2 — strategy maths
# =====================================================================

@pytest.mark.parametrize(
    "strategy, expected",
    [
        (ClosePriceStrategy(), 100.0),
        (OpenPriceStrategy(), 90.0),
        (HighPriceStrategy(), 120.0),
        (LowPriceStrategy(), 80.0),
        (TypicalPriceStrategy(), (120.0 + 80.0 + 100.0) / 3.0),
        (MeanPriceStrategy(), (90.0 + 120.0 + 80.0 + 100.0) / 4.0),
        (MedianPriceStrategy(), (120.0 + 80.0) / 2.0),
    ],
)
def test_strategy_reference_price(strategy, expected):
    assert strategy.reference_price(CANDLE) == pytest.approx(expected)


def test_mean_price_formula():
    assert MeanPriceStrategy().reference_price(CANDLE) == pytest.approx(97.5)


def test_median_price_formula():
    assert MedianPriceStrategy().reference_price(CANDLE) == pytest.approx(100.0)


def test_typical_price_formula():
    assert TypicalPriceStrategy().reference_price(CANDLE) == pytest.approx(100.0)


def test_strategies_are_stateless():
    """Same instance, repeated calls, different candles -> no carried state."""
    s = MeanPriceStrategy()
    a = s.reference_price({"open": 10, "high": 20, "low": 0, "close": 10})
    b = s.reference_price({"open": 100, "high": 200, "low": 0, "close": 100})
    again = s.reference_price({"open": 10, "high": 20, "low": 0, "close": 10})
    assert a == again  # first candle reproduces exactly
    assert a != b
    assert s.__dict__ == {}  # truly stateless instance


def test_strategy_missing_fields_fall_back_to_close():
    # Only close present -> every strategy resolves to close.
    candle = {"close": 50.0}
    for strategy in (
        OpenPriceStrategy(),
        HighPriceStrategy(),
        LowPriceStrategy(),
        TypicalPriceStrategy(),
        MeanPriceStrategy(),
        MedianPriceStrategy(),
    ):
        assert strategy.reference_price(candle) == pytest.approx(50.0)


# =====================================================================
# Phase 1 — registry
# =====================================================================

def test_default_registry_has_seven_builtins():
    reg = default_strategy_registry()
    assert reg.names() == ["close", "open", "high", "low", "typical", "mean", "median"]
    for name in reg.names():
        assert reg.exists(name)


def test_registry_rejects_duplicate_and_missing():
    reg = PriceReferenceStrategyRegistry()
    reg.register("close", lambda cfg: ClosePriceStrategy())
    with pytest.raises(ValueError):
        reg.register("close", lambda cfg: ClosePriceStrategy())
    with pytest.raises(KeyError):
        reg.get("missing")


def test_registry_create_unknown_raises():
    reg = default_strategy_registry()
    cfg = BrickConfiguration(
        brick_type=BrickType.PERCENTAGE, brick_size=1.0, percentage=1.0,
        reference_price_strategy="does_not_exist",
    )
    with pytest.raises(RenkoConfigurationError):
        reg.create(cfg)


# =====================================================================
# Phase 1 / 2 — configuration selection & factory resolution
# =====================================================================

@pytest.mark.parametrize(
    "name, expected_type",
    [
        ("close", ClosePriceStrategy),
        ("open", OpenPriceStrategy),
        ("high", HighPriceStrategy),
        ("low", LowPriceStrategy),
        ("typical", TypicalPriceStrategy),
        ("mean", MeanPriceStrategy),
        ("median", MedianPriceStrategy),
    ],
)
def test_configuration_selects_strategy(name, expected_type):
    cfg = BrickConfiguration(
        brick_type=BrickType.PERCENTAGE, brick_size=1.0, percentage=1.0,
        reference_price_strategy=name,
    )
    assert cfg.resolved_reference_strategy() == name
    assert isinstance(default_strategy_registry().create(cfg), expected_type)


def test_reference_price_strategy_takes_precedence_over_legacy_enum():
    cfg = BrickConfiguration(
        brick_type=BrickType.PERCENTAGE, brick_size=1.0, percentage=1.0,
        reference_price=ReferencePrice.HIGH,  # legacy 6D field
        reference_price_strategy="mean",       # 6E field wins
    )
    assert cfg.resolved_reference_strategy() == "mean"


def test_legacy_reference_price_maps_to_strategy():
    cfg = BrickConfiguration(
        brick_type=BrickType.PERCENTAGE, brick_size=1.0, percentage=1.0,
        reference_price=ReferencePrice.MEDIAN_PRICE,
    )
    assert cfg.resolved_reference_strategy() == "median"


def test_default_strategy_is_close():
    cfg = BrickConfiguration(brick_type=BrickType.PERCENTAGE, brick_size=1.0, percentage=1.0)
    assert cfg.resolved_reference_strategy() == "close"


def test_factory_injects_strategy_into_percentage_provider():
    registry = RenkoRegistry()
    registry.register("percentage", TraditionalRenkoEngine())
    factory = RenkoFactory(
        registry,
        provider_registry=default_provider_registry(),
        strategy_registry=default_strategy_registry(),
    )
    cfg = BrickConfiguration(
        brick_type=BrickType.PERCENTAGE, brick_size=1.0, percentage=1.0,
        reference_price_strategy="mean",
    )
    engine = factory.create(cfg)
    assert isinstance(engine.provider, PercentageBrickSizeProvider)
    assert isinstance(engine.provider.strategy, MeanPriceStrategy)


# =====================================================================
# Phase 1 — dependency injection
# =====================================================================

def test_di_exposes_strategy_registry():
    container = configure_container()
    reg = container.price_reference_strategy_registry()
    assert reg is not None
    assert reg.names() == ["close", "open", "high", "low", "typical", "mean", "median"]


def test_di_factory_and_validator_receive_strategy_registry():
    container = configure_container()
    # Factory built from the container resolves strategies end-to-end.
    rr = RenkoRegistry()
    rr.register("percentage", TraditionalRenkoEngine())
    factory = RenkoFactory(
        rr,
        provider_registry=container.brick_size_provider_registry(),
        strategy_registry=container.price_reference_strategy_registry(),
    )
    cfg = BrickConfiguration(
        brick_type=BrickType.PERCENTAGE, brick_size=1.0, percentage=1.0,
        reference_price_strategy="median",
    )
    engine = factory.create(cfg)
    assert isinstance(engine.provider.strategy, MedianPriceStrategy)


# =====================================================================
# Phase 1 — validation
# =====================================================================

@pytest.mark.asyncio
async def test_validator_accepts_known_strategy():
    validator = DefaultBrickValidator(
        provider_registry=default_provider_registry(),
        strategy_registry=default_strategy_registry(),
    )
    cfg = BrickConfiguration(
        brick_type=BrickType.PERCENTAGE, brick_size=1.0, percentage=1.0,
        reference_price_strategy="mean",
    )
    assert await validator.validate_configuration(cfg)


@pytest.mark.asyncio
async def test_validator_rejects_unknown_strategy():
    validator = DefaultBrickValidator(
        provider_registry=default_provider_registry(),
        strategy_registry=default_strategy_registry(),
    )
    cfg = BrickConfiguration(
        brick_type=BrickType.PERCENTAGE, brick_size=1.0, percentage=1.0,
        reference_price_strategy="unknown_strategy",
    )
    with pytest.raises(RenkoConfigurationError):
        await validator.validate_configuration(cfg)


# =====================================================================
# Phase 1 — plugin registration
# =====================================================================

@pytest.mark.asyncio
async def test_plugin_registers_new_strategy_without_engine_change():
    plugin_code = '''
from backend.app.chart.renko.strategies import PriceReferenceStrategyRegistry
from backend.app.chart.renko.interfaces import PriceReferenceStrategy

class WeightedCloseStrategy(PriceReferenceStrategy):
    name = "weighted_close"
    def reference_price(self, candle):
        return (candle["high"] + candle["low"] + 2 * candle["close"]) / 4.0

class MyPlugin:
    name = "wclose_plugin"
    async def load(self, event_bus=None): pass
    async def start(self): pass
    async def stop(self): pass
    async def unload(self): pass
    async def register_price_reference_strategies(self, registry: PriceReferenceStrategyRegistry):
        registry.register("weighted_close", lambda cfg: WeightedCloseStrategy())
'''
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "wclose_plugin.py").write_text(plugin_code, encoding="utf-8")

    strategy_registry = default_strategy_registry()
    manager = PluginManager(d, strategy_registry=strategy_registry)
    await manager.load()

    assert manager.get_plugin("wclose_plugin").name == "wclose_plugin"
    assert strategy_registry.exists("weighted_close")

    cfg = BrickConfiguration(
        brick_type=BrickType.PERCENTAGE, brick_size=1.0, percentage=1.0,
        reference_price_strategy="weighted_close",
    )
    strategy = strategy_registry.create(cfg)
    # (120 + 80 + 2*100) / 4 = 100
    assert strategy.reference_price(CANDLE) == pytest.approx(100.0)
    await manager.unload()


# =====================================================================
# Phase 2 — provider integration & replay determinism
# =====================================================================

def test_percentage_provider_uses_injected_strategy():
    cfg = BrickConfiguration(
        brick_type=BrickType.PERCENTAGE, brick_size=1.0, percentage=1.0,
        reference_price_strategy="mean",
    )
    provider = PercentageBrickSizeProvider.from_configuration(cfg)
    assert isinstance(provider.strategy, MeanPriceStrategy)
    provider.update(CANDLE)  # 1% of mean(97.5)
    assert provider.current_size() == pytest.approx(0.975)


def test_set_price_reference_strategy_overrides():
    provider = PercentageBrickSizeProvider(percentage=1.0)  # defaults to close
    provider.set_price_reference_strategy(HighPriceStrategy())
    provider.update(CANDLE)
    assert provider.current_size() == pytest.approx(1.2)  # 1% of high(120)


def test_replay_determinism_with_strategy():
    candles = [
        {"open": 90, "high": 120, "low": 80, "close": 100},
        {"open": 100, "high": 130, "low": 95, "close": 120},
        {"open": 120, "high": 121, "low": 60, "close": 70},
    ]

    def run():
        cfg = BrickConfiguration(
            brick_type=BrickType.PERCENTAGE, brick_size=1.0, percentage=1.0,
            reference_price_strategy="mean",
        )
        p = PercentageBrickSizeProvider.from_configuration(cfg)
        out = []
        for c in candles:
            p.update(c)
            out.append(p.current_size())
        return out

    assert run() == run()


@pytest.mark.asyncio
async def test_engine_replay_determinism_with_strategy():
    candles = [
        {"timestamp": TS, "open": 100, "high": 101, "low": 99, "close": 100},
        {"timestamp": TS, "open": 100, "high": 104, "low": 100, "close": 103},
        {"timestamp": TS, "open": 103, "high": 103, "low": 96, "close": 97},
    ]

    async def run():
        cfg = BrickConfiguration(
            brick_type=BrickType.PERCENTAGE, brick_size=1.0, percentage=1.0,
            reference_price_strategy="typical", mode=RenkoMode.REPLAY,
        )
        engine = TraditionalRenkoEngine(
            provider=PercentageBrickSizeProvider.from_configuration(cfg)
        )
        engine.configure(cfg)
        await engine.start()
        for c in candles:
            await engine.process_market_data(c)
        return [b.brick_id for b in engine.history()]

    first = await run()
    assert first == await run()
    assert len(first) > 0  # bricks were actually produced


# =====================================================================
# Regression — sizing providers unaffected by the new abstraction
# =====================================================================

def test_regression_all_providers_still_registered():
    names = default_provider_registry().names()
    for name in ("fixed", "atr", "percentage"):
        assert name in names


def test_regression_legacy_percentage_construction_unchanged():
    # 6D-style direct construction with the ReferencePrice enum still works.
    p = PercentageBrickSizeProvider(percentage=1.0, reference_price=ReferencePrice.TYPICAL_PRICE)
    p.update(CANDLE)
    assert p.current_size() == pytest.approx(1.0)  # 1% of typical(100)
    assert p.reference_price == ReferencePrice.TYPICAL_PRICE
