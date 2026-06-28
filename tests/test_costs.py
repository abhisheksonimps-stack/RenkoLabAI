from __future__ import annotations

import pytest

from backend.app.trading.costs.brokerage import (
    FixedBrokerage,
    PercentageBrokerage,
    PerShareBrokerage,
    ZeroBrokerage,
)
from backend.app.trading.costs.slippage import (
    FixedSlippage,
    PercentageSlippage,
    ZeroSlippage,
)


def test_zero_brokerage():
    assert ZeroBrokerage().cost(quantity=10, price=100) == 0.0


def test_fixed_brokerage():
    assert FixedBrokerage(5.0).cost(quantity=10, price=100) == 5.0
    with pytest.raises(ValueError):
        FixedBrokerage(-1)


def test_percentage_brokerage():
    assert PercentageBrokerage(0.001).cost(quantity=10, price=100) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        PercentageBrokerage(-0.1)


def test_per_share_brokerage():
    assert PerShareBrokerage(0.02).cost(quantity=10, price=100) == pytest.approx(0.2)
    with pytest.raises(ValueError):
        PerShareBrokerage(-1)


def test_zero_slippage():
    assert ZeroSlippage().adjust(price=100, side="buy") == 100.0
    assert ZeroSlippage().adjust(price=100, side="sell") == 100.0


def test_fixed_slippage_direction():
    s = FixedSlippage(0.5)
    assert s.adjust(price=100, side="buy") == 100.5
    assert s.adjust(price=100, side="sell") == 99.5
    with pytest.raises(ValueError):
        FixedSlippage(-1)


def test_percentage_slippage_direction():
    s = PercentageSlippage(0.01)
    assert s.adjust(price=100, side="buy") == pytest.approx(101.0)
    assert s.adjust(price=100, side="sell") == pytest.approx(99.0)
    with pytest.raises(ValueError):
        PercentageSlippage(-0.01)
