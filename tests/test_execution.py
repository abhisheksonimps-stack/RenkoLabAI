from __future__ import annotations

from datetime import datetime

import pytest

from backend.app.trading.costs.brokerage import FixedBrokerage
from backend.app.trading.costs.slippage import PercentageSlippage
from backend.app.trading.execution.executor import SimulatedExecutor
from backend.app.trading.execution.order import (
    Fill,
    Order,
    OrderIntent,
    OrderSide,
    OrderStatus,
)
from backend.app.trading.execution.position import (
    Position,
    PositionDirection,
    TradeAttribution,
)

TS = datetime(2024, 1, 1)


def make_order(side=OrderSide.BUY, intent=OrderIntent.ENTRY, qty=10.0, ref=100.0):
    return Order(1, side, intent, qty, ref, TS)


# -- Order ---------------------------------------------------------------------

def test_order_lifecycle_transitions():
    o = make_order()
    assert o.status is OrderStatus.CREATED
    o.submit()
    assert o.status is OrderStatus.PENDING
    fill = Fill(101.0, 10.0, 1.0, 100.0, OrderSide.BUY, TS)
    o.complete(fill)
    assert o.status is OrderStatus.FILLED and o.is_filled and o.fill is fill


def test_order_reject_and_cancel():
    o = make_order()
    o.reject("nope")
    assert o.status is OrderStatus.REJECTED and o.reject_reason == "nope"
    o2 = make_order()
    o2.cancel()
    assert o2.status is OrderStatus.CANCELLED


def test_fill_slippage_value():
    fill = Fill(101.0, 10.0, 1.0, 100.0, OrderSide.BUY, TS)
    assert fill.slippage == pytest.approx(10.0)  # |101-100| * 10


# -- Position ------------------------------------------------------------------

def test_position_open_close_long_and_trade():
    pos = Position(TradeAttribution(symbol="X", strategy_name="s", brick_type="traditional",
                                    brick_size=2.0, timeframe="renko"))
    assert pos.is_open is False
    assert pos.market_value(100) == 0.0
    assert pos.unrealized_pnl(100) == 0.0
    pos.open_long(price=100.0, quantity=10.0, cost=1.0, timestamp=TS, bar_index=0)
    assert pos.is_open and pos.direction is PositionDirection.LONG
    assert pos.market_value(110) == pytest.approx(1100.0)
    assert pos.unrealized_pnl(110) == pytest.approx(100.0)
    trade = pos.close(price=120.0, cost=1.0, timestamp=TS, bar_index=5)
    assert trade is not None
    assert trade.gross_pnl == pytest.approx(200.0)        # (120-100)*10
    assert trade.net_pnl == pytest.approx(198.0)          # minus entry 1 + exit 1
    assert trade.bars_held == 5
    assert trade.symbol == "X" and trade.strategy_name == "s"
    assert trade.brick_type == "traditional" and trade.brick_size == 2.0
    assert pos.is_open is False
    assert pos.realized_pnl == pytest.approx(198.0)


def test_position_scale_in_reaverages():
    pos = Position()
    pos.open_long(100.0, 10.0, 0.0, TS, 0)
    pos.open_long(110.0, 10.0, 0.0, TS, 1)
    assert pos.quantity == 20.0
    assert pos.average_entry_price == pytest.approx(105.0)


def test_position_close_when_flat_returns_none():
    assert Position().close(100.0, 0.0, TS, 0) is None


def test_trade_is_win_flag():
    pos = Position()
    pos.open_long(100.0, 1.0, 0.0, TS, 0)
    win = pos.close(110.0, 0.0, TS, 1)
    assert win.is_win is True
    pos.open_long(100.0, 1.0, 0.0, TS, 2)
    loss = pos.close(90.0, 0.0, TS, 3)
    assert loss.is_win is False


def test_position_open_long_rejects_non_positive_qty():
    with pytest.raises(ValueError):
        Position().open_long(100.0, 0.0, 0.0, TS, 0)


# -- Executor ------------------------------------------------------------------

def test_simulated_executor_applies_slippage_and_brokerage():
    ex = SimulatedExecutor(PercentageSlippage(0.01), FixedBrokerage(2.0))
    o = make_order(side=OrderSide.BUY, qty=10.0, ref=100.0)
    ex.execute(o, reference_price=100.0, timestamp=TS)
    assert o.is_filled
    assert o.fill.price == pytest.approx(101.0)   # buy slips up 1%
    assert o.fill.cost == 2.0
    assert o.fill.reference_price == 100.0


def test_simulated_executor_sell_slips_down():
    ex = SimulatedExecutor(PercentageSlippage(0.01))
    o = make_order(side=OrderSide.SELL, intent=OrderIntent.EXIT, qty=10.0, ref=100.0)
    ex.execute(o, reference_price=100.0, timestamp=TS)
    assert o.fill.price == pytest.approx(99.0)
    assert o.fill.cost == 0.0  # default zero brokerage


def test_simulated_executor_rejects_without_price():
    ex = SimulatedExecutor()
    o = make_order()
    ex.execute(o, reference_price=0.0, timestamp=TS)
    assert o.status is OrderStatus.REJECTED and o.fill is None
