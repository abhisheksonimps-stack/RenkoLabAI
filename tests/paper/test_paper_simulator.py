from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from backend.app.trading.execution.order import OrderIntent, OrderSide, OrderStatus
from backend.app.trading.paper.enums import OrderType, TimeInForce
from backend.app.trading.paper.executor import PaperExecutor
from backend.app.trading.paper.quote import MarketQuote
from backend.app.trading.paper.simulator import ExchangeSimulator
from backend.app.trading.portfolio.portfolio import Portfolio

T0 = datetime(2024, 1, 1, 9, 30, 0)


def quote(price, t=T0, high=None, low=None):
    return MarketQuote("X", t, price, high if high is not None else price,
                       low if low is not None else price)


def make_sim(capital=100_000.0, executor=None):
    return ExchangeSimulator(Portfolio(capital), executor=executor or PaperExecutor())


def _kinds(events):
    return [e.kind for e in events]


def test_market_buy_fills_on_next_quote_and_updates_portfolio():
    sim = make_sim()
    accepted = sim.submit(side=OrderSide.BUY, intent=OrderIntent.ENTRY,
                          quantity=10.0, order_type=OrderType.MARKET)
    assert accepted.kind == "accepted"
    events = sim.on_market_data(quote(100.0))
    assert "filled" in _kinds(events)
    p = sim.portfolio
    assert p.position.is_open and p.position.quantity == 10.0
    assert p.cash == pytest.approx(100_000 - 1000)        # 10 * 100
    assert len(p.equity_curve) == 1
    assert p.equity_curve[0].equity == pytest.approx(100_000)


def test_market_buy_then_market_sell_round_trip():
    sim = make_sim()
    sim.submit(side=OrderSide.BUY, intent=OrderIntent.ENTRY, quantity=10.0,
               order_type=OrderType.MARKET)
    sim.on_market_data(quote(100.0))
    sim.submit(side=OrderSide.SELL, intent=OrderIntent.EXIT, quantity=10.0,
               order_type=OrderType.MARKET)
    sim.on_market_data(quote(120.0, t=T0 + timedelta(minutes=1)))
    p = sim.portfolio
    assert not p.position.is_open
    assert len(p.trades) == 1
    assert p.trades[0].gross_pnl == pytest.approx(200.0)   # (120-100)*10
    assert p.cash == pytest.approx(100_000 + 200)


def test_limit_buy_rests_then_triggers_at_limit():
    sim = make_sim()
    sim.submit(side=OrderSide.BUY, intent=OrderIntent.ENTRY, quantity=10.0,
               order_type=OrderType.LIMIT, limit_price=95.0)
    assert sim.portfolio.reserved == pytest.approx(950.0)  # 10 * 95 reserved
    no_fill = sim.on_market_data(quote(96.0))               # above limit
    assert "filled" not in _kinds(no_fill)
    assert len(sim.open_orders) == 1
    events = sim.on_market_data(quote(94.0, t=T0 + timedelta(minutes=1)))
    assert _kinds(events).count("triggered") == 1
    assert "filled" in _kinds(events)
    assert sim.portfolio.reserved == pytest.approx(0.0)     # released on settle
    assert sim.portfolio.position.average_entry_price == pytest.approx(95.0)


def test_stop_buy_triggers_when_price_rises_through_stop():
    sim = make_sim()
    sim.submit(side=OrderSide.BUY, intent=OrderIntent.ENTRY, quantity=5.0,
               order_type=OrderType.STOP, stop_price=105.0)
    assert "filled" not in _kinds(sim.on_market_data(quote(104.0)))
    events = sim.on_market_data(quote(104.0, t=T0 + timedelta(minutes=1), high=106.0))
    assert "filled" in _kinds(events)
    assert sim.portfolio.position.quantity == 5.0
    assert sim.portfolio.position.average_entry_price == pytest.approx(105.0)


def test_cancel_resting_order_releases_reservation():
    sim = make_sim()
    accepted = sim.submit(side=OrderSide.BUY, intent=OrderIntent.ENTRY, quantity=10.0,
                          order_type=OrderType.LIMIT, limit_price=95.0)
    assert sim.portfolio.reserved == pytest.approx(950.0)
    cancelled = sim.cancel(accepted.order.order_id)
    assert cancelled is not None and cancelled.kind == "cancelled"
    assert cancelled.order.status is OrderStatus.CANCELLED
    assert sim.portfolio.reserved == pytest.approx(0.0)
    assert sim.open_orders == []
    assert sim.cancel(accepted.order.order_id) is None       # already gone


def test_ioc_order_cancelled_when_not_triggered():
    sim = make_sim()
    sim.submit(side=OrderSide.BUY, intent=OrderIntent.ENTRY, quantity=10.0,
               order_type=OrderType.LIMIT, limit_price=90.0, time_in_force=TimeInForce.IOC)
    events = sim.on_market_data(quote(95.0))                 # no trigger this cycle
    assert "cancelled" in _kinds(events)
    assert sim.open_orders == []
    assert sim.portfolio.reserved == pytest.approx(0.0)


def test_insufficient_cash_is_rejected_on_fill():
    sim = make_sim(capital=500.0)
    sim.submit(side=OrderSide.BUY, intent=OrderIntent.ENTRY, quantity=10.0,
               order_type=OrderType.MARKET)
    events = sim.on_market_data(quote(100.0))                # needs 1000 > 500
    assert "rejected" in _kinds(events)
    assert not sim.portfolio.position.is_open
    assert sim.portfolio.cash == 500.0


def test_zero_or_negative_quantity_is_rejected_at_submit():
    sim = make_sim()
    event = sim.submit(side=OrderSide.BUY, intent=OrderIntent.ENTRY, quantity=0.0,
                       order_type=OrderType.MARKET)
    assert event.kind == "rejected"
    assert sim.open_orders == []
