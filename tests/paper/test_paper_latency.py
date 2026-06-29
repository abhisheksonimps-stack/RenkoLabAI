from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from backend.app.trading.paper.latency import (
    FixedLatency,
    RandomLatency,
    ZeroLatency,
)

TS = datetime(2024, 1, 1, 12, 0, 0)


def test_zero_latency_does_not_shift():
    model = ZeroLatency()
    assert model.delay() == timedelta()
    assert model.apply(TS) == TS


def test_fixed_latency_shifts_by_amount():
    model = FixedLatency(milliseconds=250)
    assert model.delay() == timedelta(milliseconds=250)
    assert model.apply(TS) == TS + timedelta(milliseconds=250)


def test_fixed_latency_rejects_negative():
    with pytest.raises(ValueError):
        FixedLatency(milliseconds=-1)


def test_random_latency_within_bounds_and_deterministic_with_seed():
    a = RandomLatency(min_ms=10, max_ms=20, seed=42)
    b = RandomLatency(min_ms=10, max_ms=20, seed=42)
    for _ in range(50):
        delay = a.delay()
        assert timedelta(milliseconds=10) <= delay <= timedelta(milliseconds=20)
    # Same seed -> identical sequence.
    a2 = RandomLatency(min_ms=10, max_ms=20, seed=42)
    assert [a2.delay() for _ in range(5)] == [b.delay() for _ in range(5)]


def test_random_latency_validates_bounds():
    with pytest.raises(ValueError):
        RandomLatency(min_ms=20, max_ms=10)
    with pytest.raises(ValueError):
        RandomLatency(min_ms=-1, max_ms=5)
