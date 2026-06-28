from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from backend.app.chart.renko.models import Brick, BrickDirection
from backend.app.trading.indicators.ema import EMA
from backend.app.trading.indicators.sma import SMA
from backend.app.trading.signals.models import Signal, SignalType
from backend.app.trading.strategy.ema_crossover import EMACrossoverStrategy
from backend.app.trading.strategy.engine import StrategyEngine
from backend.app.trading.strategy.factory import StrategyFactory
from backend.app.trading.strategy.interfaces import Strategy
from backend.app.trading.strategy.registry import StrategyRegistry, default_strategy_registry

TS = datetime(2024, 1, 1)


def make_brick(close: float, i: int = 0, direction: BrickDirection = BrickDirection.UP) -> Brick:
    return Brick(
        brick_id=f"b{i}",
        direction=direction,
        open_price=close,
        close_price=float(close),
        high_price=float(close),
        low_price=float(close),
        volume=0.0,
        created_at=TS + timedelta(minutes=i),
        metadata={},
    )


def bricks_from_closes(closes):
    return [make_brick(c, i) for i, c in enumerate(closes)]


def run_strategy(closes):
    strat = EMACrossoverStrategy(period=10)
    strat.initialize()
    out = []
    for i, c in enumerate(closes):
        strat.on_brick(make_brick(c, i))
        out.append(strat.generate_signal().type)
    return out


# =====================================================================
# Indicators — SMA
# =====================================================================

def test_sma_rejects_non_positive_period():
    with pytest.raises(ValueError):
        SMA(0)
    with pytest.raises(ValueError):
        SMA(-3)


def test_sma_not_ready_before_period():
    sma = SMA(3)
    assert sma.update(1) is None
    assert sma.update(2) is None
    assert sma.ready is False
    assert sma.value is None
    assert sma.count == 2


def test_sma_calculation_and_window_eviction():
    sma = SMA(3)
    sma.update(1); sma.update(2)
    assert sma.update(3) == pytest.approx(2.0)  # (1+2+3)/3
    assert sma.ready is True
    assert sma.update(4) == pytest.approx(3.0)  # (2+3+4)/3, oldest evicted
    assert sma.count == 3


def test_sma_reset():
    sma = SMA(2)
    sma.update(5); sma.update(7)
    assert sma.ready
    sma.reset()
    assert sma.ready is False
    assert sma.value is None
    assert sma.count == 0


# =====================================================================
# Indicators — EMA
# =====================================================================

def test_ema_rejects_non_positive_period():
    with pytest.raises(ValueError):
        EMA(0)


def test_ema_not_ready_before_seed():
    ema = EMA(3)
    assert ema.update(1) is None
    assert ema.update(2) is None
    assert ema.ready is False
    assert ema.value is None
    assert ema.count == 2


def test_ema_seed_is_sma_then_recurrence():
    ema = EMA(3)  # alpha = 2/4 = 0.5
    ema.update(1); ema.update(2)
    assert ema.update(3) == pytest.approx(2.0)   # seed = (1+2+3)/3
    assert ema.ready is True
    assert ema.update(4) == pytest.approx(3.0)   # 0.5*4 + 0.5*2
    assert ema.update(5) == pytest.approx(4.0)   # 0.5*5 + 0.5*3
    assert ema.count == 5


def test_ema_reset():
    ema = EMA(2)
    ema.update(10); ema.update(20)
    assert ema.ready
    ema.reset()
    assert ema.ready is False
    assert ema.value is None
    assert ema.count == 0


# =====================================================================
# Signal model
# =====================================================================

def test_signal_types_and_actionable():
    assert {s.value for s in SignalType} == {"buy", "sell", "exit", "hold"}
    assert Signal(SignalType.BUY).is_actionable is True
    assert Signal(SignalType.HOLD).is_actionable is False


# =====================================================================
# Strategy — signal generation
# =====================================================================

def test_hold_until_ema_ready():
    # First 9 bricks: EMA(10) not ready -> HOLD.
    signals = run_strategy([100] * 9)
    assert all(s is SignalType.HOLD for s in signals)


def test_buy_signal_when_close_above_ema_from_flat():
    # 10th brick close (200) above SMA-seed (110) -> BUY.
    signals = run_strategy([100] * 9 + [200])
    assert signals[-1] is SignalType.BUY


def test_sell_signal_when_close_below_ema_from_flat():
    # 10th brick close (50) below SMA-seed (95) -> SELL.
    signals = run_strategy([100] * 9 + [50])
    # seed = (900+50)/10 = 95 ; 50 < 95 -> SELL
    assert signals[-1] is SignalType.SELL


def test_equal_close_is_hold():
    signals = run_strategy([100] * 10)  # seed=100, close=100 -> HOLD
    assert signals[-1] is SignalType.HOLD


def test_exit_when_long_then_bearish():
    seq = run_strategy([100] * 9 + [200, 50])
    # brick10 -> BUY (long); brick11 close 50 < EMA -> EXIT
    assert seq[-2] is SignalType.BUY
    assert seq[-1] is SignalType.EXIT


def test_exit_when_short_then_bullish():
    seq = run_strategy([100] * 9 + [50, 400])
    # brick10 -> SELL (short); brick11 close 400 > EMA -> EXIT
    assert seq[-2] is SignalType.SELL
    assert seq[-1] is SignalType.EXIT


def test_hold_when_already_long_and_bullish():
    seq = run_strategy([100] * 9 + [200, 300])
    assert seq[-2] is SignalType.BUY
    assert seq[-1] is SignalType.HOLD  # still long, still bullish


def test_hold_when_already_short_and_bearish():
    seq = run_strategy([100] * 9 + [50, 40])
    assert seq[-2] is SignalType.SELL
    assert seq[-1] is SignalType.HOLD  # still short, still bearish


def test_full_consecutive_sequence():
    closes = [100] * 9 + [200, 300, 50, 40, 300]
    seq = run_strategy(closes)
    assert seq[:9] == [SignalType.HOLD] * 9
    assert seq[9] is SignalType.BUY    # 200 > 110
    assert seq[10] is SignalType.HOLD  # 300 > ema, still long
    assert seq[11] is SignalType.EXIT  # 50 < ema, long -> flat
    assert seq[12] is SignalType.SELL  # 40 < ema, flat -> short
    assert seq[13] is SignalType.EXIT  # 300 > ema, short -> flat


def test_signal_carries_context():
    strat = EMACrossoverStrategy(period=10)
    strat.initialize()
    for i, c in enumerate([100] * 9 + [200]):
        strat.on_brick(make_brick(c, i))
    sig = strat.generate_signal()
    assert sig.type is SignalType.BUY
    assert sig.brick_id == "b9"
    assert sig.price == 200.0
    assert sig.reference == pytest.approx(110.0)
    assert sig.metadata["position"] == "long"


def test_strategy_reset_clears_state():
    strat = EMACrossoverStrategy(period=10)
    strat.initialize()
    for i, c in enumerate([100] * 9 + [200]):
        strat.on_brick(make_brick(c, i))
        strat.generate_signal()  # advances position to long on the 10th brick
    assert strat.position == "long"
    assert strat.ema.ready
    strat.reset()
    assert strat.position == "flat"
    assert strat.ema.ready is False
    assert strat.generate_signal().type is SignalType.HOLD  # no brick / not ready


def test_initialize_is_reset():
    strat = EMACrossoverStrategy(period=10)
    for i, c in enumerate([100] * 9 + [200]):
        strat.on_brick(make_brick(c, i))
    strat.initialize()
    assert strat.position == "flat"
    assert strat.ema.ready is False


def test_strategy_implements_interface():
    assert issubclass(EMACrossoverStrategy, Strategy)
    assert isinstance(EMACrossoverStrategy(), Strategy)
    assert EMACrossoverStrategy.name == "ema_crossover"


# =====================================================================
# No repaint — past signals never change as new bricks arrive
# =====================================================================

def test_no_repaint():
    closes = [100] * 9 + [200, 300, 50, 40, 300, 60, 500]
    bricks = bricks_from_closes(closes)

    # Reference: full run.
    engine = StrategyEngine(EMACrossoverStrategy(period=10))
    full = [s.type for s in engine.process_bricks(bricks)]

    # For every prefix length, a fresh strategy fed only bricks[0..i] must
    # produce the SAME signal at step i (no dependence on future bricks).
    for i in range(len(bricks)):
        strat = EMACrossoverStrategy(period=10)
        strat.initialize()
        last = None
        for j in range(i + 1):
            strat.on_brick(bricks[j])
            last = strat.generate_signal()
        assert last.type is full[i]


# =====================================================================
# Strategy engine
# =====================================================================

def test_engine_process_brick_returns_and_accumulates():
    engine = StrategyEngine(EMACrossoverStrategy(period=10))
    engine.start()
    sig = engine.process_brick(make_brick(100, 0))
    assert isinstance(sig, Signal)
    assert len(engine.signals()) == 1


def test_engine_process_bricks_batch():
    engine = StrategyEngine(EMACrossoverStrategy(period=10))
    signals = engine.process_bricks(bricks_from_closes([100] * 9 + [200]))
    assert len(signals) == 10
    assert signals[-1].type is SignalType.BUY
    assert engine.strategy.position == "long"


def test_engine_autostarts_without_explicit_start():
    engine = StrategyEngine(EMACrossoverStrategy(period=10))
    sig = engine.process_brick(make_brick(100, 0))  # no start() called
    assert isinstance(sig, Signal)
    assert len(engine.signals()) == 1


def test_engine_reset():
    engine = StrategyEngine(EMACrossoverStrategy(period=10))
    engine.process_bricks(bricks_from_closes([100] * 9 + [200]))
    engine.reset()
    assert engine.signals() == []
    assert engine.strategy.position == "flat"


# =====================================================================
# Registry
# =====================================================================

def test_registry_register_get_exists_names_create():
    reg = StrategyRegistry()
    reg.register("ema_crossover", lambda **kw: EMACrossoverStrategy(**kw))
    assert reg.exists("ema_crossover")
    assert "ema_crossover" in reg.names()
    assert callable(reg.get("ema_crossover"))
    strat = reg.create("ema_crossover", period=5)
    assert isinstance(strat, EMACrossoverStrategy)
    assert strat._period == 5


def test_registry_unknown_raises():
    reg = StrategyRegistry()
    with pytest.raises(KeyError):
        reg.get("nope")


def test_registry_empty_name_raises():
    reg = StrategyRegistry()
    with pytest.raises(ValueError):
        reg.register("", lambda **kw: EMACrossoverStrategy())


def test_default_registry_has_ema_crossover():
    reg = default_strategy_registry()
    assert reg.exists("ema_crossover")
    assert isinstance(reg.create("ema_crossover"), EMACrossoverStrategy)


# =====================================================================
# Factory resolution
# =====================================================================

def test_factory_resolves_default():
    factory = StrategyFactory()
    strat = factory.create("ema_crossover")
    assert isinstance(strat, EMACrossoverStrategy)
    assert "ema_crossover" in factory.available()
    assert factory.registry.exists("ema_crossover")


def test_factory_with_custom_registry_and_kwargs():
    reg = StrategyRegistry()
    reg.register("ema_crossover", lambda **kw: EMACrossoverStrategy(**kw))
    factory = StrategyFactory(reg)
    strat = factory.create("ema_crossover", period=20)
    assert strat._period == 20


def test_factory_unknown_strategy_raises():
    factory = StrategyFactory()
    with pytest.raises(KeyError):
        factory.create("does_not_exist")
