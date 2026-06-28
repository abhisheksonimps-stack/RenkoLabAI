from __future__ import annotations

from datetime import datetime

import pytest

from backend.app.trading.execution.order import Fill, Order, OrderIntent, OrderSide, OrderStatus
from backend.app.trading.execution.position import TradeAttribution
from backend.app.trading.portfolio.portfolio import Portfolio

TS = datetime(2024, 1, 1)


def filled_buy(qty=10.0, price=100.0, cost=0.0, ref=None, reserved=0.0):
    o = Order(1, OrderSide.BUY, OrderIntent.ENTRY, qty, price, TS, reserved=reserved)
    o.complete(Fill(price, qty, cost, ref if ref is not None else price, OrderSide.BUY, TS))
    return o


def filled_sell(qty=10.0, price=120.0, cost=0.0, ref=None):
    o = Order(2, OrderSide.SELL, OrderIntent.EXIT, qty, price, TS)
    o.complete(Fill(price, qty, cost, ref if ref is not None else price, OrderSide.SELL, TS))
    return o


def test_portfolio_validates_inputs():
    with pytest.raises(ValueError):
        Portfolio(0)
    with pytest.raises(ValueError):
        Portfolio(1000, leverage=0)


def test_capital_views_and_reserve_release():
    p = Portfolio(1000.0)
    assert p.available_capital == 1000.0
    assert p.buying_power == 1000.0
    p.reserve(200.0)
    assert p.reserved == 200.0
    assert p.available_capital == 800.0
    assert p.buying_power == 800.0
    p.release(50.0)
    assert p.reserved == 150.0
    p.release(1000.0)  # cannot go negative
    assert p.reserved == 0.0


def test_buying_power_uses_leverage():
    p = Portfolio(1000.0, leverage=2.0)
    assert p.buying_power == 2000.0


def test_apply_buy_then_sell_updates_cash_and_trade():
    p = Portfolio(100_000.0, attribution=TradeAttribution(symbol="X"))
    buy = filled_buy(qty=10, price=100, cost=1.0, reserved=1000.0)
    p.reserve(1000.0)
    p.apply_order(buy, bar_index=0)
    assert p.reserved == 0.0                       # reservation released on settle
    assert p.cash == pytest.approx(100_000 - 1001) # 10*100 + 1 brokerage
    assert p.position.is_open
    assert p.total_brokerage == 1.0

    sell = filled_sell(qty=10, price=120, cost=1.0)
    trade = p.apply_order(sell, bar_index=3)
    assert trade is not None
    assert p.cash == pytest.approx(100_000 - 1001 + (1200 - 1))
    assert len(p.trades) == 1
    assert trade.symbol == "X"
    assert p.total_brokerage == 2.0


def test_apply_buy_rejected_on_insufficient_cash():
    p = Portfolio(500.0)
    buy = filled_buy(qty=10, price=100, cost=0.0)  # needs 1000 > 500
    p.apply_order(buy, bar_index=0)
    assert buy.status is OrderStatus.REJECTED
    assert p.cash == 500.0
    assert p.position.is_open is False


def test_apply_order_with_no_fill_is_noop():
    p = Portfolio(1000.0)
    o = Order(1, OrderSide.BUY, OrderIntent.ENTRY, 1, 100, TS, reserved=100.0)
    p.reserve(100.0)
    # no fill set (executor would have rejected)
    assert p.apply_order(o, 0) is None
    assert p.reserved == 0.0    # reservation still released for buys
    assert p.cash == 1000.0


def test_mark_builds_equity_curve():
    p = Portfolio(100_000.0)
    buy = filled_buy(qty=10, price=100, cost=0.0)
    p.apply_order(buy, 0)
    eq = p.mark(TS, 110.0)
    assert eq == pytest.approx(100_000 - 1000 + 10 * 110)  # cash + MV
    assert len(p.equity_curve) == 1
    assert p.equity_curve[0].equity == pytest.approx(eq)


def test_slippage_accumulates():
    p = Portfolio(100_000.0)
    buy = filled_buy(qty=10, price=101, cost=0.0, ref=100.0)  # slipped 1 * 10 = 10
    p.apply_order(buy, 0)
    assert p.total_slippage == pytest.approx(10.0)
