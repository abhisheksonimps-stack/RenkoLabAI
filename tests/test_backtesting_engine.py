from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from backend.app.chart.renko.models import Brick, BrickDirection
from backend.app.trading.backtesting.engine import BacktestEngine
from backend.app.trading.costs.brokerage import FixedBrokerage
from backend.app.trading.costs.slippage import PercentageSlippage
from backend.app.trading.execution.order import OrderStatus
from backend.app.trading.execution.position import TradeAttribution
from backend.app.trading.signals.models import Signal, SignalType
from backend.app.trading.strategy.ema_crossover import EMACrossoverStrategy
from backend.app.trading.strategy.interfaces import Strategy

TS = datetime(2024, 1, 1)


def brick(i, close, direction=BrickDirection.UP):
    return Brick(f"b{i}", direction, close, float(close), float(close), float(close),
                 0.0, TS + timedelta(minutes=i), {})


class Scripted(Strategy):
    """Emits a predetermined signal per brick (controls timing exactly)."""

    name = "scripted"

    def __init__(self, script):
        self._script = script
        self._i = -1

    def initialize(self):
        self._i = -1

    def on_brick(self, b):
        self._i += 1

    def generate_signal(self):
        t = self._script[self._i] if self._i < len(self._script) else SignalType.HOLD
        return Signal(t)

    def reset(self):
        self._i = -1


def attribution():
    return TradeAttribution(symbol="TEST", strategy_name="scripted",
                            brick_type="traditional", brick_size=5.0, timeframe="renko")


# -- Fill timing ---------------------------------------------------------------

def test_signal_fills_on_next_brick_not_same():
    prices = [100, 110, 120, 130, 140, 150]
    script = [SignalType.BUY, SignalType.HOLD, SignalType.HOLD,
              SignalType.EXIT, SignalType.HOLD, SignalType.HOLD]
    bricks = [brick(i, p) for i, p in enumerate(prices)]
    eng = BacktestEngine(Scripted(script), starting_capital=100_000,
                         fixed_quantity=10, attribution=attribution())
    res = eng.run(bricks)
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t.entry_price == 110.0   # BUY on b0(100) fills on b1(110)
    assert t.exit_price == 140.0    # EXIT on b3(130) fills on b4(140)
    assert t.gross_pnl == pytest.approx(300.0)
    assert t.bars_held == 3
    assert len(res.equity_curve) == 6


def test_equity_curve_has_one_point_per_brick():
    bricks = [brick(i, 100 + i) for i in range(5)]
    eng = BacktestEngine(Scripted([SignalType.HOLD] * 5), starting_capital=10_000)
    res = eng.run(bricks)
    assert len(res.equity_curve) == 5
    # No trades, flat equity.
    assert res.metrics.num_trades == 0
    assert res.metrics.ending_equity == 10_000


# -- Position handling ---------------------------------------------------------

def test_force_close_open_position_at_end():
    prices = [100, 110, 120, 130]
    script = [SignalType.BUY, SignalType.HOLD, SignalType.HOLD, SignalType.HOLD]
    bricks = [brick(i, p) for i, p in enumerate(prices)]
    eng = BacktestEngine(Scripted(script), starting_capital=100_000,
                         fixed_quantity=10, attribution=attribution())
    res = eng.run(bricks)
    assert len(res.trades) == 1
    # Entry on b1 (110); force-closed at last brick close (130).
    assert res.trades[0].entry_price == 110.0
    assert res.trades[0].exit_price == 130.0
    assert eng.portfolio.position.is_open is False


def test_no_force_close_leaves_position_open():
    prices = [100, 110, 120, 130]
    script = [SignalType.BUY, SignalType.HOLD, SignalType.HOLD, SignalType.HOLD]
    bricks = [brick(i, p) for i, p in enumerate(prices)]
    eng = BacktestEngine(Scripted(script), starting_capital=100_000,
                         fixed_quantity=10, force_close=False)
    res = eng.run(bricks)
    assert res.trades == []
    assert eng.portfolio.position.is_open is True


def test_pending_order_on_last_brick_is_cancelled():
    # BUY signal arrives on the final brick -> no next brick -> cancelled.
    prices = [100, 110, 120]
    script = [SignalType.HOLD, SignalType.HOLD, SignalType.BUY]
    bricks = [brick(i, p) for i, p in enumerate(prices)]
    eng = BacktestEngine(Scripted(script), starting_capital=100_000, fixed_quantity=10)
    eng.run(bricks)
    last = eng.portfolio.orders[-1]
    assert last.status is OrderStatus.CANCELLED
    assert eng.portfolio.reserved == 0.0
    assert eng.portfolio.position.is_open is False


def test_sell_signal_is_ignored_long_only():
    prices = [100, 110, 120]
    script = [SignalType.SELL, SignalType.SELL, SignalType.SELL]
    bricks = [brick(i, p) for i, p in enumerate(prices)]
    eng = BacktestEngine(Scripted(script), starting_capital=100_000, fixed_quantity=10)
    res = eng.run(bricks)
    assert res.trades == []
    assert eng.portfolio.orders == []  # nothing ever ordered


# -- Costs reflected -----------------------------------------------------------

def test_zero_cost_gross_equals_net():
    prices = [100, 110, 120, 130, 140]
    script = [SignalType.BUY, SignalType.HOLD, SignalType.EXIT, SignalType.HOLD, SignalType.HOLD]
    bricks = [brick(i, p) for i, p in enumerate(prices)]
    eng = BacktestEngine(Scripted(script), starting_capital=100_000, fixed_quantity=10)
    res = eng.run(bricks)
    t = res.trades[0]
    assert t.gross_pnl == t.net_pnl
    assert eng.portfolio.total_brokerage == 0.0
    assert eng.portfolio.total_slippage == 0.0


def test_costs_reduce_net_pnl():
    prices = [100, 110, 120, 130, 140]
    script = [SignalType.BUY, SignalType.HOLD, SignalType.EXIT, SignalType.HOLD, SignalType.HOLD]
    bricks = [brick(i, p) for i, p in enumerate(prices)]
    eng = BacktestEngine(Scripted(script), starting_capital=100_000, fixed_quantity=10,
                         slippage=PercentageSlippage(0.001), brokerage=FixedBrokerage(1.0))
    res = eng.run(bricks)
    t = res.trades[0]
    assert t.net_pnl < t.gross_pnl
    assert eng.portfolio.total_brokerage == pytest.approx(2.0)   # entry + exit
    assert eng.portfolio.total_slippage > 0.0


# -- Sizing / capital ----------------------------------------------------------

def test_fraction_sizing_uses_buying_power():
    prices = [100, 100, 100, 100]
    script = [SignalType.BUY, SignalType.HOLD, SignalType.HOLD, SignalType.HOLD]
    bricks = [brick(i, p) for i, p in enumerate(prices)]
    eng = BacktestEngine(Scripted(script), starting_capital=10_000,
                         position_fraction=0.5, force_close=False)
    eng.run(bricks)
    # 50% of 10,000 buying power / price 100 = 50 units entered on b1.
    assert eng.portfolio.position.quantity == pytest.approx(50.0)


# -- Real strategy integration / determinism -----------------------------------

def _ema_series():
    closes = [100] * 9 + [200, 300, 50, 40, 300, 60, 500, 50, 600]
    return [brick(i, c) for i, c in enumerate(closes)]


def test_integration_with_ema_strategy_runs_and_trades():
    eng = BacktestEngine(EMACrossoverStrategy(period=10), starting_capital=1_000_000,
                         fixed_quantity=1,
                         attribution=TradeAttribution(symbol="SIM", strategy_name="ema_crossover",
                                                      brick_type="traditional", brick_size=1.0,
                                                      timeframe="renko"))
    res = eng.run(_ema_series())
    assert res.metrics.num_trades >= 1
    assert all(t.strategy_name == "ema_crossover" for t in res.trades)
    assert len(res.equity_curve) == len(_ema_series())


def test_backtest_is_deterministic():
    def run():
        eng = BacktestEngine(EMACrossoverStrategy(period=10), starting_capital=1_000_000,
                             fixed_quantity=1)
        res = eng.run(_ema_series())
        return [(p.equity) for p in res.equity_curve], [t.net_pnl for t in res.trades]
    a = run()
    b = run()
    assert a == b


def test_attribution_defaults_to_strategy_name():
    eng = BacktestEngine(EMACrossoverStrategy(period=10), starting_capital=1_000_000,
                         fixed_quantity=1)
    eng.run(_ema_series())
    assert eng.portfolio.position.attribution.strategy_name == "ema_crossover"


def test_entry_quantity_edge_cases():
    eng = BacktestEngine(Scripted([]), starting_capital=10_000)
    assert eng._entry_quantity(0.0) == 0.0          # non-positive reference price
    eng_fixed_zero = BacktestEngine(Scripted([]), starting_capital=10_000, fixed_quantity=0.0)
    assert eng_fixed_zero._entry_quantity(100.0) == 0.0


def test_zero_quantity_signal_produces_no_order():
    prices = [100, 110, 120]
    script = [SignalType.BUY, SignalType.HOLD, SignalType.HOLD]
    bricks = [brick(i, p) for i, p in enumerate(prices)]
    eng = BacktestEngine(Scripted(script), starting_capital=10_000, fixed_quantity=0.0)
    res = eng.run(bricks)
    assert res.trades == []
    assert eng.portfolio.orders == []  # BUY with qty 0 -> no order created
