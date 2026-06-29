from __future__ import annotations

from datetime import datetime

import pytest

from backend.app.trading.execution.order import Order, OrderIntent, OrderSide
from backend.app.trading.paper.enums import OrderType, TimeInForce
from backend.app.trading.paper.pending import PendingOrderManager
from backend.app.trading.paper.quote import MarketQuote
from backend.app.trading.paper.ticket import OrderTicket

TS = datetime(2024, 1, 1)


def quote(price, high=None, low=None):
    return MarketQuote("X", TS, price, high if high is not None else price,
                       low if low is not None else price)


def ticket(order_id, side, order_type, *, limit=None, stop=None, tif=TimeInForce.GTC):
    order = Order(order_id, side, OrderIntent.ENTRY, 5.0, 100.0, TS)
    return OrderTicket(order, order_type, time_in_force=tif, limit_price=limit, stop_price=stop)


def test_ticket_validates_required_prices():
    with pytest.raises(ValueError):
        ticket(1, OrderSide.BUY, OrderType.LIMIT)  # missing limit
    with pytest.raises(ValueError):
        ticket(1, OrderSide.BUY, OrderType.STOP)   # missing stop


def test_limit_buy_triggers_when_price_falls_to_limit():
    mgr = PendingOrderManager()
    mgr.add(ticket(1, OrderSide.BUY, OrderType.LIMIT, limit=95.0))
    assert mgr.match(quote(96.0)) == []          # above limit -> no fill
    assert len(mgr) == 1
    matched = mgr.match(quote(96.0, high=97, low=94.0))  # intrabar touch
    assert len(matched) == 1
    _, reference = matched[0]
    assert reference == 95.0                      # fills at limit price
    assert len(mgr) == 0                          # removed once triggered


def test_limit_sell_triggers_when_price_rises_to_limit():
    mgr = PendingOrderManager()
    mgr.add(ticket(1, OrderSide.SELL, OrderType.LIMIT, limit=110.0))
    assert mgr.match(quote(105.0)) == []
    matched = mgr.match(quote(108.0, high=111.0, low=107.0))
    assert matched[0][1] == 110.0


def test_stop_buy_triggers_when_price_rises_to_stop():
    mgr = PendingOrderManager()
    mgr.add(ticket(1, OrderSide.BUY, OrderType.STOP, stop=105.0))
    assert mgr.match(quote(104.0)) == []
    matched = mgr.match(quote(104.0, high=106.0, low=103.0))
    assert matched[0][1] == 105.0                 # stop level as reference


def test_stop_sell_triggers_when_price_falls_to_stop():
    mgr = PendingOrderManager()
    mgr.add(ticket(1, OrderSide.SELL, OrderType.STOP, stop=90.0))
    assert mgr.match(quote(95.0)) == []
    matched = mgr.match(quote(92.0, high=96.0, low=89.0))
    assert matched[0][1] == 90.0


def test_match_is_ordered_and_remove_works():
    mgr = PendingOrderManager()
    mgr.add(ticket(2, OrderSide.BUY, OrderType.LIMIT, limit=100.0))
    mgr.add(ticket(1, OrderSide.BUY, OrderType.LIMIT, limit=100.0))
    matched = mgr.match(quote(99.0))
    assert [t.order_id for t, _ in matched] == [1, 2]  # ascending id


def test_remove_returns_ticket_and_membership():
    mgr = PendingOrderManager()
    mgr.add(ticket(7, OrderSide.BUY, OrderType.STOP, stop=120.0))
    assert 7 in mgr
    removed = mgr.remove(7)
    assert removed is not None and removed.order_id == 7
    assert 7 not in mgr
    assert mgr.remove(7) is None
