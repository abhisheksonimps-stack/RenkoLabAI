"""Benchmark runner — executes the grid and writes a Markdown report.

Usage:
    export PYTHONPATH=$PWD
    python -m benchmark.benchmark_runner            # default grid (up to 100k)
    python -m benchmark.benchmark_runner --full     # include 1,000,000 candles
    python -m benchmark.benchmark_runner --out path/to/report.md
"""

from __future__ import annotations

import argparse
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from benchmark.performance import (
    BenchmarkResult,
    run_benchmark,
    run_snapshot_benchmark,
)

DEFAULT_SIZES = [100, 1_000, 10_000, 100_000]
FULL_SIZES = DEFAULT_SIZES + [1_000_000]

# Memory sampling (tracemalloc) is heavy; only sample up to this size.
MEMORY_SAMPLE_LIMIT = 100_000


def _hardware_info() -> List[tuple[str, str]]:
    try:
        import os

        cpus = os.cpu_count() or 0
    except Exception:
        cpus = 0
    return [
        ("Generated", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")),
        ("Platform", platform.platform()),
        ("Processor", platform.processor() or "n/a"),
        ("CPU count", str(cpus)),
        ("Python", sys.version.split()[0]),
        ("Implementation", platform.python_implementation()),
    ]


def _md_table(headers: List[str], rows: List[List[str]]) -> str:
    line = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = "\n".join("| " + " | ".join(r) + " |" for r in rows)
    return "\n".join([line, sep, body])


def run_grid(sizes: List[int], providers: List[str], scenario: str = "trending") -> List[BenchmarkResult]:
    results: List[BenchmarkResult] = []
    for provider in providers:
        for n in sizes:
            results.append(
                run_benchmark(provider, scenario, n, sample_memory=(n <= MEMORY_SAMPLE_LIMIT))
            )
    return results


def build_report(full: bool = False) -> str:
    sizes = FULL_SIZES if full else DEFAULT_SIZES
    providers = ["fixed", "atr", "percentage"]

    parts: List[str] = ["# RenkoLabAI — Sprint 6H Performance Report", ""]

    parts.append("## Environment")
    parts.append("")
    parts.append(_md_table(["Field", "Value"], [[k, v] for k, v in _hardware_info()]))
    parts.append("")

    # Throughput / memory grid (scenario: trending).
    parts.append("## Throughput & memory (scenario: trending)")
    parts.append("")
    grid = run_grid(sizes, providers)
    rows = []
    for r in grid:
        row = r.as_row()
        rows.append([
            row["provider"],
            f"{row['candles']:,}",
            f"{row['bricks']:,}",
            f"{row['seconds']:.4f}",
            f"{row['candles_per_sec']:,}",
            f"{row['bricks_per_sec']:,}",
            ("n/a" if row["candles"] > MEMORY_SAMPLE_LIMIT else f"{row['peak_kib']:.0f}"),
            ("n/a" if row["candles"] > MEMORY_SAMPLE_LIMIT else f"{row['avg_kib']:.0f}"),
        ])
    parts.append(_md_table(
        ["provider", "candles", "bricks", "seconds", "candles/s", "bricks/s", "peak KiB", "avg KiB"],
        rows,
    ))
    parts.append("")
    parts.append("> Memory is tracemalloc-traced Python allocation; sampling is disabled above "
                 f"{MEMORY_SAMPLE_LIMIT:,} candles to avoid skewing timings.")
    parts.append("")

    # Scenario stress sweep at a fixed size.
    parts.append("## Scenario sweep (fixed provider, 50,000 candles)")
    parts.append("")
    srows = []
    for scenario in ["trending", "alternating", "rapid_reversals", "flat", "large_gaps"]:
        r = run_benchmark("fixed", scenario, 50_000, sample_memory=True)
        row = r.as_row()
        srows.append([
            scenario, f"{row['bricks']:,}", f"{row['seconds']:.4f}",
            f"{row['candles_per_sec']:,}", f"{row['peak_kib']:.0f}",
        ])
    parts.append(_md_table(["scenario", "bricks", "seconds", "candles/s", "peak KiB"], srows))
    parts.append("")

    # Snapshot / restore overhead.
    parts.append("## Snapshot / restore overhead")
    parts.append("")
    snap = run_snapshot_benchmark("fixed", 50_000)
    parts.append(_md_table(
        ["bricks", "snapshot (ms)", "serialize (ms)", "restore (ms)", "payload (KiB)"],
        [[
            f"{snap.bricks:,}",
            f"{snap.snapshot_ms:.2f}",
            f"{snap.serialize_ms:.2f}",
            f"{snap.restore_ms:.2f}",
            f"{snap.payload_bytes / 1024.0:.1f}",
        ]],
    ))
    parts.append("")
    parts.append("Restore performs no candle replay; it reconstructs components from the "
                 "registries and imports captured state, so its cost is bounded by history size, "
                 "not by the number of candles originally processed.")
    parts.append("")

    parts.append("## Optimization notes")
    parts.append("")
    parts.append(OPTIMIZATION_NOTES)
    parts.append("")
    return "\n".join(parts)


OPTIMIZATION_NOTES = """All optimizations preserve byte-identical output (the full 205-test suite passes
unchanged, brick IDs and counts identical). They are pure implementation changes;
Renko logic, public APIs, and architecture are untouched.

1. **Builder — skip redundant enum re-validation.** `build_brick` previously called
   `BrickDirection(market_data["direction"])` on every brick even though the engine
   already passes a `BrickDirection`. It now re-validates only for raw inputs,
   eliminating one enum `__call__` per brick.

2. **Builder — avoid discarded default computation.** `high_price`/`low_price` used
   `dict.get(key, max(...)/min(...))`, which evaluates the `max`/`min` default on
   every call even when the key is present (it always is from the engine). The
   default is now computed only when the field is genuinely absent — removing two
   `max`/`min` calls per brick.

3. **Engine — guard event publication.** The per-brick `await _publish_brick_event`
   created and awaited a coroutine even when no event bus is attached (the replay
   path). It is now skipped entirely when there is no bus — same events (none),
   no coroutine churn.

4. **Engine — batch resulting state on the no-bus path.** The brick loop rebuilt
   `BrickState` on every brick, but with no event bus the intermediate states are
   never observed. The resulting state is now built once after the loop (identical
   final state), removing the majority of per-brick `BrickState` allocations during
   replay. With an event bus, per-brick state is preserved exactly because each
   published snapshot reflects the current state.

The remaining per-brick cost (brick-ID string construction and the frozen-dataclass
allocation) is intrinsic to the output contract and was intentionally left unchanged.
Providers are already O(1) per candle with O(1) memory (ATR keeps a rolling value, not
history), and history uses a `deque`; no algorithmic changes were needed there."""


def main() -> None:
    parser = argparse.ArgumentParser(description="RenkoLabAI benchmark runner")
    parser.add_argument("--full", action="store_true", help="include 1,000,000 candles")
    parser.add_argument("--out", default="benchmark/benchmark_report.md", help="report output path")
    args = parser.parse_args()

    report = build_report(full=args.full)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"Wrote {out} ({len(report)} bytes)")


if __name__ == "__main__":
    main()
