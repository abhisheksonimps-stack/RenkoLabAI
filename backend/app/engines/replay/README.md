# Replay Engine

## Responsibilities

The Replay Engine replays historical market data exactly as if it were arriving from a live exchange. It supports tick and candle replay, replay timing, replay state management, events, and replay controls without introducing trading decisions, charting, or broker dependencies.

## Public Interfaces

- `ReplaySource` - protocol for sources that provide async iterators for ticks and candles.
- `ReplayEngine` - abstract interface for replay controls: start, pause, resume, stop, restart, seek, step tick, step candle, and speed changes.
- `ReplayController` - concrete implementation of `ReplayEngine` that drives replay control logic and publishes events through `EventBus`.
- `ReplayClock` - utility for replay timing and speed multiplier calculations.
- `ReplaySession` - session state object keeping track of current replay time, speed, state, and limits.
- `ReplayCursor` - cursor metadata wrapper for replayed payloads.
- `ReplayScheduler` - optional scheduling helper for running replay in streaming mode behind an event bus.
- `ReplayState` - enum for stopped, running, paused, and completed states.
- `ReplaySpeed` - enum for replay speed multipliers.

## Event Flow

The replay engine publishes events through the existing `EventBus`:

- `ReplayStarted`
- `ReplayPaused`
- `ReplayResumed`
- `ReplayStopped`
- `ReplayCompleted`
- `TickReplayed`
- `CandleReplayed`
- `ReplaySpeedChanged`
- `ReplaySeeked`

Consumers can subscribe to these events for integration with backtests, paper trading, chart engines, or live simulation.

## Replay Lifecycle

1. Create a `ReplaySession` and a `ReplaySource`.
2. Instantiate `ReplayController` with the `EventBus`.
3. Call `start()` to begin replay.
4. Use `pause()`, `resume()`, `seek(timestamp)`, `step_tick()`, `step_candle()`, or `change_speed()` as needed.
5. Replay completes when current session time reaches the end time.

## Extension Points

- Implement new `ReplaySource` classes for alternate historical data sources.
- Subscribe custom event handlers to the `EventBus` for downstream processing.
- Replace `ReplayController` with a specialized controller for multi-stream replay or advanced schedule handling.
