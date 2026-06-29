from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.chart.renko.models import Brick, BrickDirection
from backend.app.domain.market_data.enums import Timeframe
from backend.app.domain.market_data.models import Candle
from backend.app.events.bus import EventBus
from backend.app.marketdata.models import MarketBar
from backend.app.trading.backtesting.engine import BacktestEngine
from backend.app.trading.paper.session import PaperTradingSession
from backend.app.trading.portfolio.portfolio import Portfolio
from backend.app.trading.signals.models import Signal, SignalType
from backend.app.trading.strategy import (
    ATRPositionSizer,
    EMATrendStrategy,
    FixedQuantitySizer,
    FixedRiskPercentSizer,
    MaxOpenPositionsRule,
    PDHPDLBreakoutStrategy,
    PositionSizingContext,
    RenkoTrendStrategy,
    RiskManager,
    StopLossRule,
    StrategyConfiguration,
    StrategyContext,
    StrategyFactory,
    StrategyLoader,
    StrategyEngine,
)
from backend.app.trading.strategy.paper_bridge import PaperStrategyBridge

TS = datetime(2024, 1, 1, tzinfo=timezone.utc)


def brick(i: int, close: float, direction: BrickDirection = BrickDirection.UP) -> Brick:
    return Brick(
        brick_id=f"b{i}",
        direction=direction,
        open_price=close,
        close_price=float(close),
        high_price=float(close),
        low_price=float(close),
        volume=0.0,
        created_at=TS + timedelta(minutes=i),
        metadata={"symbol": "TEST"},
    )


def bar(i: int, open_: float, high: float, low: float, close: float) -> MarketBar:
    return MarketBar.create(
        symbol="TEST",
        timestamp=TS + timedelta(days=i),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100,
        interval="1d",
    )


def candle(i: int, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        symbol="TEST",
        exchange="XNAS",
        timeframe=Timeframe.ONE_DAY,
        start_time=TS + timedelta(days=i),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100,
        trades=1,
    )


def test_signal_type_exit_aliases_preserve_existing_iteration_contract():
    assert {item.value for item in SignalType} == {"buy", "sell", "exit", "hold"}
    assert SignalType.EXIT_LONG is SignalType.EXIT
    assert SignalType.EXIT_SHORT is SignalType.EXIT
    assert Signal(SignalType.EXIT_LONG).is_exit is True


def test_strategy_factory_and_loader_register_builtins():
    factory = StrategyFactory()
    assert {"ema_crossover", "ema_trend", "pdh_pdl_breakout", "renko_trend"}.issubset(set(factory.available()))
    assert isinstance(factory.create_from_configuration(StrategyConfiguration(name="ema_trend", parameters={"period": 3})), EMATrendStrategy)

    registry = StrategyLoader().discover()
    assert isinstance(registry.create("renko_trend", trend_length=2), RenkoTrendStrategy)


def test_position_sizers():
    context = PositionSizingContext(equity=100_000, price=100, stop_price=95, atr=2)
    assert FixedQuantitySizer(10).size(context) == 10
    assert FixedRiskPercentSizer(0.01, round_down=True).size(context) == 200
    assert ATRPositionSizer(0.01, atr_multiple=2, round_down=True).size(context) == 250


def test_risk_manager_applies_stop_and_max_open_positions():
    context = StrategyContext(symbol="TEST", current_price=90, position_quantity=10, open_positions=1)
    signal = RiskManager([StopLossRule(95)]).evaluate(Signal(SignalType.HOLD, price=90), context)
    assert signal.type is SignalType.EXIT
    assert signal.metadata["risk_rule"] == "stop_loss"

    blocked = RiskManager([MaxOpenPositionsRule(1)]).evaluate(
        Signal(SignalType.BUY, price=100),
        StrategyContext(symbol="TEST", current_price=100, open_positions=1),
    )
    assert blocked.type is SignalType.HOLD


def test_pdh_pdl_breakout_market_data_lifecycle():
    strategy = PDHPDLBreakoutStrategy(buffer=0)
    strategy.initialize()
    assert strategy.on_market_data(bar(0, 100, 110, 90, 105)).signal.type is SignalType.HOLD
    result = strategy.on_market_data(bar(1, 105, 120, 104, 111))
    assert result.signal.type is SignalType.BUY
    assert result.signal.reference == 110


def test_ema_trend_and_renko_trend_are_backtest_executable():
    ema_result = BacktestEngine(EMATrendStrategy(period=3), starting_capital=100_000, fixed_quantity=10).run(
        [brick(i, close) for i, close in enumerate([100, 101, 102, 103, 99, 98, 104, 105])]
    )
    assert ema_result.metrics.num_trades >= 0

    renko_result = BacktestEngine(RenkoTrendStrategy(trend_length=2), starting_capital=100_000, fixed_quantity=10).run(
        [
            brick(0, 100, BrickDirection.UP),
            brick(1, 101, BrickDirection.UP),
            brick(2, 102, BrickDirection.UP),
            brick(3, 101, BrickDirection.DOWN),
            brick(4, 100, BrickDirection.DOWN),
        ]
    )
    assert renko_result.metrics.num_trades >= 0


def test_strategy_engine_process_market_data_with_risk_manager():
    engine = StrategyEngine(EMATrendStrategy(period=2), risk_manager=RiskManager([MaxOpenPositionsRule(0)]))
    engine.process_market_data(bar(0, 100, 101, 99, 100))
    result = engine.process_market_data(bar(1, 100, 103, 99, 103), StrategyContext(symbol="TEST", market_data=bar(1, 100, 103, 99, 103), open_positions=0))
    assert result.signal.type in (SignalType.HOLD, SignalType.BUY)
    assert len(engine.results()) == 2


@pytest.mark.asyncio
async def test_paper_strategy_bridge_routes_buy_signal():
    portfolio = Portfolio(100_000)
    session = PaperTradingSession("TEST", portfolio, EventBus())
    session.start()
    bridge = PaperStrategyBridge(PDHPDLBreakoutStrategy(), session, FixedQuantitySizer(5))

    first = await bridge.on_candle(candle(0, 100, 110, 90, 105))
    assert first.order is None
    second = await bridge.on_candle(candle(1, 105, 120, 104, 111))
    assert second.signal.type is SignalType.BUY
    assert second.order is not None
