"""RenkoLabAI performance benchmark harness.

Pure measurement utilities — no Renko behaviour lives here. Everything is
deterministic (no randomness, no wall-clock dependence in the data) so runs are
reproducible. Engines are created without an event bus to measure the core
replay path.
"""

from __future__ import annotations

import asyncio
import gc
import time
import tracemalloc
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List

from backend.app.chart.renko.builder import default_builder_registry
from backend.app.chart.renko.configuration import BrickConfiguration, BrickType, RenkoMode
from backend.app.chart.renko.engine import TraditionalRenkoEngine
from backend.app.chart.renko.providers import (
    ATRBrickSizeProvider,
    FixedBrickSizeProvider,
    PercentageBrickSizeProvider,
    default_provider_registry,
)
from backend.app.chart.renko.snapshot import JsonSnapshotSerializer, SnapshotManager
from backend.app.chart.renko.strategies import default_strategy_registry

TS0 = datetime(2024, 1, 1)


# --------------------------------------------------------------------------- #
# Deterministic candle generators (scenarios)
# --------------------------------------------------------------------------- #

def _candle(i: int, price: float, spread: float = 0.5) -> Dict[str, Any]:
    return {
        "timestamp": TS0 + timedelta(minutes=i),
        "open": price,
        "high": price + spread,
        "low": price - spread,
        "close": price,
    }


def trending(n: int, step: float = 1.5, span: float = 60.0) -> List[Dict[str, Any]]:
    """Bounded sawtooth (price oscillates within a band). Generates a steady
    stream of continuation bricks with periodic reversals for all providers,
    while keeping the price bounded so percentage brick sizing stays stable and
    memory does not explode on very large runs."""
    out = []
    price = 100.0
    direction = 1
    low, high = 100.0, 100.0 + span
    for i in range(n):
        price += step * direction
        if price >= high:
            price = high
            direction = -1
        elif price <= low:
            price = low
            direction = 1
        out.append(_candle(i, round(price, 6)))
    return out


def alternating(n: int, step: float = 1.5) -> List[Dict[str, Any]]:
    """Alternating up/down each candle — heavy reversal load."""
    out = []
    price = 100.0
    for i in range(n):
        price += step if i % 2 == 0 else -step
        out.append(_candle(i, round(price, 6)))
    return out


def rapid_reversals(n: int, step: float = 2.0) -> List[Dict[str, Any]]:
    """Frequent multi-brick reversals."""
    out = []
    price = 100.0
    for i in range(n):
        price += step * (1 if (i // 3) % 2 == 0 else -1)
        out.append(_candle(i, round(price, 6)))
    return out


def flat(n: int) -> List[Dict[str, Any]]:
    """Flat market — almost no bricks (tests overhead per candle)."""
    return [_candle(i, 100.0) for i in range(n)]


def large_gaps(n: int, gap: float = 50.0) -> List[Dict[str, Any]]:
    """Periodic large gaps — many bricks generated in single candles."""
    out = []
    price = 100.0
    for i in range(n):
        price += gap if i % 100 == 0 else 0.1
        out.append(_candle(i, round(price, 6), spread=gap))
    return out


SCENARIOS: Dict[str, Callable[[int], List[Dict[str, Any]]]] = {
    "trending": trending,
    "alternating": alternating,
    "rapid_reversals": rapid_reversals,
    "flat": flat,
    "large_gaps": large_gaps,
}


# --------------------------------------------------------------------------- #
# Engine builders
# --------------------------------------------------------------------------- #

def fixed_engine(size: float = 1.5) -> tuple[TraditionalRenkoEngine, BrickConfiguration]:
    cfg = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=size, mode=RenkoMode.REPLAY)
    engine = TraditionalRenkoEngine(provider=FixedBrickSizeProvider(size))
    engine.configure(cfg)
    return engine, cfg


def atr_engine(period: int = 14, mult: float = 0.75) -> tuple[TraditionalRenkoEngine, BrickConfiguration]:
    cfg = BrickConfiguration(
        brick_type=BrickType.ATR, brick_size=1.0, atr_period=period, atr_multiplier=mult, mode=RenkoMode.REPLAY
    )
    engine = TraditionalRenkoEngine(provider=ATRBrickSizeProvider.from_configuration(cfg))
    engine.configure(cfg)
    return engine, cfg


def percentage_engine(pct: float = 1.0) -> tuple[TraditionalRenkoEngine, BrickConfiguration]:
    cfg = BrickConfiguration(
        brick_type=BrickType.PERCENTAGE, brick_size=1.0, percentage=pct, mode=RenkoMode.REPLAY
    )
    engine = TraditionalRenkoEngine(provider=PercentageBrickSizeProvider.from_configuration(cfg))
    engine.configure(cfg)
    return engine, cfg


ENGINE_BUILDERS: Dict[str, Callable[[], tuple[TraditionalRenkoEngine, BrickConfiguration]]] = {
    "fixed": fixed_engine,
    "atr": atr_engine,
    "percentage": percentage_engine,
}


# --------------------------------------------------------------------------- #
# Measurement
# --------------------------------------------------------------------------- #

@dataclass
class BenchmarkResult:
    provider: str
    scenario: str
    candles: int
    bricks: int
    seconds: float
    candles_per_sec: float
    bricks_per_sec: float
    peak_kib: float
    avg_kib: float

    def as_row(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "scenario": self.scenario,
            "candles": self.candles,
            "bricks": self.bricks,
            "seconds": round(self.seconds, 4),
            "candles_per_sec": round(self.candles_per_sec),
            "bricks_per_sec": round(self.bricks_per_sec),
            "peak_kib": round(self.peak_kib, 1),
            "avg_kib": round(self.avg_kib, 1),
        }


async def _process(engine: TraditionalRenkoEngine, candles: List[Dict[str, Any]], *, sample_memory: bool) -> tuple[int, float, float]:
    """Process candles, optionally sampling traced memory. Returns (peak_kib, avg_kib, _)."""
    await engine.start()
    samples: List[int] = []
    every = max(1, len(candles) // 20)
    for i, c in enumerate(candles):
        await engine.process_market_data(c)
        if sample_memory and i % every == 0:
            samples.append(tracemalloc.get_traced_memory()[0])
    if sample_memory:
        peak = tracemalloc.get_traced_memory()[1] / 1024.0
        avg = (sum(samples) / len(samples) / 1024.0) if samples else 0.0
        return len(engine.history()), peak, avg
    return len(engine.history()), 0.0, 0.0


def run_benchmark(provider: str, scenario: str, n: int, *, sample_memory: bool = True) -> BenchmarkResult:
    candles = SCENARIOS[scenario](n)

    # Timing pass: no tracemalloc, so throughput is not distorted by tracing.
    engine, _cfg = ENGINE_BUILDERS[provider]()
    gc.collect()
    start = time.perf_counter()
    bricks, _, _ = asyncio.run(_process(engine, candles, sample_memory=False))
    elapsed = time.perf_counter() - start

    # Memory pass (separate): tracemalloc heavily slows execution, so it is only
    # used to capture allocation figures, never to time the run.
    peak_kib = avg_kib = 0.0
    if sample_memory:
        mem_engine, _ = ENGINE_BUILDERS[provider]()
        gc.collect()
        tracemalloc.start()
        _, peak_kib, avg_kib = asyncio.run(_process(mem_engine, candles, sample_memory=True))
        tracemalloc.stop()

    return BenchmarkResult(
        provider=provider,
        scenario=scenario,
        candles=n,
        bricks=bricks,
        seconds=elapsed,
        candles_per_sec=(n / elapsed) if elapsed else 0.0,
        bricks_per_sec=(bricks / elapsed) if elapsed else 0.0,
        peak_kib=peak_kib,
        avg_kib=avg_kib,
    )


@dataclass
class SnapshotResult:
    bricks: int
    snapshot_ms: float
    serialize_ms: float
    restore_ms: float
    payload_bytes: int


def run_snapshot_benchmark(provider: str = "fixed", n: int = 50_000) -> SnapshotResult:
    """Measure snapshot creation, serialization, and restore overhead."""
    candles = SCENARIOS["trending"](n)
    engine, _cfg = ENGINE_BUILDERS[provider]()

    async def fill():
        await engine.start()
        for c in candles:
            await engine.process_market_data(c)

    asyncio.run(fill())

    t = time.perf_counter()
    state = engine.snapshot()
    snapshot_ms = (time.perf_counter() - t) * 1000.0

    serializer = JsonSnapshotSerializer()
    t = time.perf_counter()
    blob = serializer.serialize(state)
    serialize_ms = (time.perf_counter() - t) * 1000.0

    manager = SnapshotManager(
        serializer,
        default_provider_registry(),
        default_strategy_registry(),
        default_builder_registry(),
    )
    t = time.perf_counter()
    manager.restore(blob)
    restore_ms = (time.perf_counter() - t) * 1000.0

    return SnapshotResult(
        bricks=len(engine.history()),
        snapshot_ms=snapshot_ms,
        serialize_ms=serialize_ms,
        restore_ms=restore_ms,
        payload_bytes=len(blob.encode("utf-8")),
    )
