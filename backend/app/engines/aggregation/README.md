# Aggregation Engine

The Aggregation Engine converts validated market ticks into completed OHLC candles.

## Responsibilities

- Accept validated ticks and aggregate them into time-based candles.
- Publish event notifications when candles open, update, and close.
- Support configurable timeframes including sub-minute and multi-minute intervals.
- Handle out-of-order tick arrival and ignore duplicate ticks.
- Respect optional trading session boundaries.

## Public interfaces

- `TimeframeAggregator` - aligns timestamps to candle boundaries.
- `TickAggregator` - ingests ticks and maintains aggregation state.
- `CandleBuilder` - builds and updates candle state from ticks.
- `AggregationEngine` - orchestrates aggregation and publishes candle events.

## Event flow

1. A new tick arrives.
2. The engine validates the tick timestamp and session boundary.
3. The engine opens a candle if necessary.
4. The engine updates the candle with price, volume, and timestamp information.
5. When the timeframe boundary passes or a session closes, the engine closes the candle.
6. `CandleOpened`, `CandleUpdated`, and `CandleClosed` events are published using the existing `EventBus`.

## Extension points

- Provide a custom `CandleBuilder` implementation for alternate aggregation rules.
- Provide a custom `TimeframeAggregator` implementation for non-fixed calendars or trading sessions.
- Replace the `TickAggregator` implementation to support additional persistence or event semantics.
