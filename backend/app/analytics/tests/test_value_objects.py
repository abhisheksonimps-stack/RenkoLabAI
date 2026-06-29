from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from backend.app.analytics.domain.value_objects import (
    DrawdownPoint,
    EquityPoint,
    Money,
    Percentage,
    ReturnPeriod,
    ReturnSeries,
)

TS = datetime(2024, 1, 1, 0, 0, 0)


def test_money_is_immutable_and_currency_safe() -> None:
    usd = Money(amount=Decimal("10"), currency="usd")
    assert str(usd) == "USD 10.00"
    assert usd + Money(amount=Decimal("2.25"), currency="USD") == Money(
        amount=Decimal("12.25"), currency="USD"
    )
    with pytest.raises(ValueError):
        _ = usd + Money(amount=Decimal("1"), currency="EUR")
    with pytest.raises(Exception):
        usd.amount = Decimal("99")


def test_percentage_conversions_and_arithmetic() -> None:
    pct = Percentage.from_percent(25)
    assert pct.to_decimal() == Decimal("0.25")
    assert pct.to_percent() == Decimal("25.00")
    assert str(pct + Percentage(value=Decimal("0.05"))) == "30.00%"


def test_equity_point_requires_matching_currencies() -> None:
    point = EquityPoint(
        timestamp=TS,
        equity=Money(amount=Decimal("100"), currency="USD"),
        realized_pnl=Money(amount=Decimal("5"), currency="USD"),
        unrealized_pnl=Money(amount=Decimal("2"), currency="USD"),
    )
    assert point.total_pnl == Money(amount=Decimal("7"), currency="USD")
    with pytest.raises(ValueError):
        EquityPoint(
            timestamp=TS,
            equity=Money(amount=Decimal("100"), currency="USD"),
            realized_pnl=Money(amount=Decimal("5"), currency="EUR"),
            unrealized_pnl=Money(amount=Decimal("2"), currency="USD"),
        )


def test_drawdown_point_sign_and_duration() -> None:
    point = DrawdownPoint(
        timestamp=TS + timedelta(days=2),
        drawdown=Percentage(value=Decimal("-0.10")),
        peak_equity=Money(amount=Decimal("100"), currency="USD"),
        current_equity=Money(amount=Decimal("90"), currency="USD"),
        peak_timestamp=TS,
    )
    assert point.duration_days == 2
    assert point.drawdown_amount == Money(amount=Decimal("10"), currency="USD")
    assert point.is_in_drawdown is True


def test_return_series_statistics() -> None:
    series = ReturnSeries(
        period=ReturnPeriod.DAILY,
        returns=(
            Percentage(value=Decimal("0.10")),
            Percentage(value=Decimal("-0.05")),
            Percentage(value=Decimal("0.02")),
        ),
        start_timestamp=TS,
        end_timestamp=TS + timedelta(days=3),
    )
    assert series.count == 3
    assert series.periods_per_year() == 252
    assert series.positive_count == 2
    assert series.negative_count == 1
    assert series.cumulative.to_decimal().quantize(Decimal("0.0001")) == Decimal("0.0659")
