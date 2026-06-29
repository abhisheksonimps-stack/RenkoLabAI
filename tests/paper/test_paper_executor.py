from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from backend.app.trading.costs.brokerage import FixedBrokerage
from backend.app.trading.costs.slippage import PercentageSlippage
from backend.app.trading.execution.executor import Executor
from backend.app.trading.execution.order import (
    Order,
    OrderIntent,
    OrderSide,
    OrderStatus,
)
from backend.app.trading.paper.executor import PaperExecutor
from backend.app.trading.paper.latency import FixedLatency

TS = datetime(2024, 1, 1, 9, 30, 0)


def make_order(side=OrderSide.BUY, intent=OrderIntent.ENTRY, qty=10.0, ref=100.0):
    return Order(1, side, intent, qty, ref, TS)


def test_paper_executor_is_an_executor():
    assert isinstance(PaperExecutor(), Executor)


def test_paper_executor_applies_slippage_and_brokerage():
    ex = PaperExecutor(PercentageSlippage(0.01), FixedBrokerage(2.0))
    order = make_order(side=OrderSide.BUY, qty=10.0, ref=100.0)
    ex.execute(order, reference_price=100.0, timestamp=TS)
    assert order.is_filled
    assert order.fill.price == pytest.approx(101.0)  # buy slips up 1%
    assert order.fill.cost == 2.0
    assert order.fill.reference_price == 100.0


def test_paper_executor_sell_slips_down():
    ex = PaperExecutor(PercentageSlippage(0.01))
    order = make_order(side=OrderSide.SELL, intent=OrderIntent.EXIT, qty=10.0, ref=100.0)
    ex.execute(order, reference_price=100.0, timestamp=TS)
    assert order.fill.price == pytest.approx(99.0)
    assert order.fill.cost == 0.0  # default zero brokerage


def test_paper_executor_rejects_without_price():
    ex = PaperExecutor()
    order = make_order()
    ex.execute(order, reference_price=0.0, timestamp=TS)
    assert order.status is OrderStatus.REJECTED and order.fill is None


def test_paper_executor_latency_shifts_fill_timestamp():
    ex = PaperExecutor(latency=FixedLatency(milliseconds=500))
    order = make_order()
    ex.execute(order, reference_price=100.0, timestamp=TS)
    assert order.fill.timestamp == TS + timedelta(milliseconds=500)


def test_paper_executor_zero_models_fill_at_reference():
    ex = PaperExecutor()
    order = make_order(ref=100.0)
    ex.execute(order, reference_price=123.45, timestamp=TS)
    assert order.fill.price == pytest.approx(123.45)
    assert order.fill.timestamp == TS  # zero latency default
