# RenkoLabAI — Sprint 6H Performance Report

## Environment

| Field | Value |
| --- | --- |
| Generated | 2026-06-27 16:19:50 UTC |
| Platform | Linux-6.18.5-x86_64-with-glibc2.39 |
| Processor | x86_64 |
| CPU count | 1 |
| Python | 3.12.3 |
| Implementation | CPython |

## Throughput & memory (scenario: trending)

| provider | candles | bricks | seconds | candles/s | bricks/s | peak KiB | avg KiB |
| --- | --- | --- | --- | --- | --- | --- | --- |
| fixed | 100 | 59 | 0.0010 | 97,911 | 57,767 | 36 | 22 |
| fixed | 1,000 | 519 | 0.0052 | 192,219 | 99,761 | 236 | 116 |
| fixed | 10,000 | 4,999 | 0.0497 | 201,167 | 100,563 | 2193 | 1050 |
| fixed | 100,000 | 49,999 | 0.5036 | 198,588 | 99,292 | 21847 | 10386 |
| fixed | 1,000,000 | 499,999 | 5.3884 | 185,585 | 92,792 | n/a | n/a |
| atr | 100 | 46 | 0.0010 | 104,547 | 48,092 | 30 | 17 |
| atr | 1,000 | 506 | 0.0060 | 167,020 | 84,512 | 230 | 110 |
| atr | 10,000 | 4,986 | 0.0576 | 173,496 | 86,505 | 2187 | 1044 |
| atr | 100,000 | 49,986 | 0.6059 | 165,044 | 82,499 | 21841 | 10380 |
| atr | 1,000,000 | 499,986 | 6.2326 | 160,448 | 80,222 | n/a | n/a |
| percentage | 100 | 70 | 0.0011 | 87,582 | 61,308 | 40 | 24 |
| percentage | 1,000 | 597 | 0.0063 | 159,014 | 94,931 | 270 | 132 |
| percentage | 10,000 | 5,749 | 0.0599 | 166,868 | 95,932 | 2520 | 1206 |
| percentage | 100,000 | 57,499 | 0.6179 | 161,838 | 93,055 | 25122 | 11942 |
| percentage | 1,000,000 | 574,999 | 6.4351 | 155,398 | 89,354 | n/a | n/a |

> Memory is tracemalloc-traced Python allocation; sampling is disabled above 100,000 candles to avoid skewing timings.

## Scenario sweep (fixed provider, 50,000 candles)

| scenario | bricks | seconds | candles/s | peak KiB |
| --- | --- | --- | --- | --- |
| trending | 24,999 | 0.2424 | 206,274 | 10928 |
| alternating | 25,000 | 0.2439 | 205,012 | 10977 |
| rapid_reversals | 33,332 | 0.3031 | 164,958 | 14567 |
| flat | 0 | 0.0915 | 546,623 | 8 |
| large_gaps | 16,467 | 0.1681 | 297,427 | 7262 |

## Snapshot / restore overhead

| bricks | snapshot (ms) | serialize (ms) | restore (ms) | payload (KiB) |
| --- | --- | --- | --- | --- |
| 24,999 | 145.49 | 74.31 | 204.91 | 6763.3 |

Restore performs no candle replay; it reconstructs components from the registries and imports captured state, so its cost is bounded by history size, not by the number of candles originally processed.

## Optimization notes

All optimizations preserve byte-identical output (the full 205-test suite passes
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
history), and history uses a `deque`; no algorithmic changes were needed there.
