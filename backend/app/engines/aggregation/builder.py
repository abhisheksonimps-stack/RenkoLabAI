from __future__ import annotations

from backend.app.domain.market_data.models import Candle, Tick
from backend.app.domain.market_data.enums import Timeframe
from backend.app.engines.aggregation.interfaces import CandleBuilder
from backend.app.engines.aggregation.models import AggregationState


class DefaultCandleBuilder(CandleBuilder):
    def create_state(self, tick: Tick, timeframe: Timeframe, start_time, end_time) -> AggregationState:
        state = AggregationState(
            symbol=tick.symbol,
            exchange=tick.exchange,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
            open=tick.price,
            high=tick.price,
            low=tick.price,
            close=tick.price,
            volume=tick.size or 0.0,
            trades=1,
            last_timestamp=tick.timestamp,
        )
        state.record_tick(tick)
        return state

    def update_state(self, state: AggregationState, tick: Tick) -> AggregationState:
        if state.has_seen(tick):
            return state

        state.high = max(state.high, tick.price)
        state.low = min(state.low, tick.price)

        if tick.timestamp > state.last_timestamp:
            state.close = tick.price
            state.last_timestamp = tick.timestamp

        state.volume += tick.size or 0.0
        state.trades += 1
        state.record_tick(tick)
        return state

    def finalize_candle(self, state: AggregationState) -> Candle:
        return Candle(
            symbol=state.symbol,
            exchange=state.exchange,
            timeframe=state.timeframe,
            start_time=state.start_time,
            open=state.open,
            high=state.high,
            low=state.low,
            close=state.close,
            volume=state.volume,
            trades=state.trades,
        )
