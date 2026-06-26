from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from backend.app.domain.market_data.enums import Timeframe
from backend.app.domain.market_data.models import Tick, TradingSession
from backend.app.engines.aggregation.interfaces import CandleBuilder, TickAggregator, TimeframeAggregator
from backend.app.engines.aggregation.models import AggregationState


class FixedIntervalTimeframeAggregator(TimeframeAggregator):
    def __init__(self, timeframe: Timeframe) -> None:
        self.timeframe = timeframe

    def align_timestamp(self, timestamp: datetime) -> datetime:
        if self.timeframe == Timeframe.ONE_MINUTE:
            return timestamp.replace(second=0, microsecond=0)
        if self.timeframe == Timeframe.FIVE_MINUTE:
            minute = (timestamp.minute // 5) * 5
            return timestamp.replace(minute=minute, second=0, microsecond=0)
        if self.timeframe == Timeframe.FIFTEEN_MINUTE:
            minute = (timestamp.minute // 15) * 15
            return timestamp.replace(minute=minute, second=0, microsecond=0)
        if self.timeframe == Timeframe.THIRTY_MINUTE:
            minute = (timestamp.minute // 30) * 30
            return timestamp.replace(minute=minute, second=0, microsecond=0)
        if self.timeframe == Timeframe.ONE_HOUR:
            return timestamp.replace(minute=0, second=0, microsecond=0)
        if self.timeframe == Timeframe.FOUR_HOUR:
            hour = (timestamp.hour // 4) * 4
            return timestamp.replace(hour=hour, minute=0, second=0, microsecond=0)
        if self.timeframe == Timeframe.ONE_DAY:
            return timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
        if self.timeframe == Timeframe.ONE_WEEK:
            weekday = timestamp.weekday()
            start_of_week = timestamp - timedelta(days=weekday)
            return start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        if self.timeframe == Timeframe.ONE_MONTH:
            return timestamp.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return timestamp

    def bucket_end(self, start_time: datetime) -> datetime:
        if self.timeframe == Timeframe.ONE_MINUTE:
            return start_time + timedelta(minutes=1)
        if self.timeframe == Timeframe.FIVE_MINUTE:
            return start_time + timedelta(minutes=5)
        if self.timeframe == Timeframe.FIFTEEN_MINUTE:
            return start_time + timedelta(minutes=15)
        if self.timeframe == Timeframe.THIRTY_MINUTE:
            return start_time + timedelta(minutes=30)
        if self.timeframe == Timeframe.ONE_HOUR:
            return start_time + timedelta(hours=1)
        if self.timeframe == Timeframe.FOUR_HOUR:
            return start_time + timedelta(hours=4)
        if self.timeframe == Timeframe.ONE_DAY:
            return start_time + timedelta(days=1)
        if self.timeframe == Timeframe.ONE_WEEK:
            return start_time + timedelta(days=7)
        if self.timeframe == Timeframe.ONE_MONTH:
            return start_time.replace(day=1) + timedelta(days=31)
        return start_time


class DefaultTickAggregator(TickAggregator):
    def __init__(self, timeframe_aggregator: TimeframeAggregator, builder: CandleBuilder) -> None:
        self.timeframe_aggregator = timeframe_aggregator
        self.builder = builder
        self._open_states: Dict[Tuple[str, str, Timeframe, datetime], AggregationState] = {}

    def _state_key(self, tick: Tick, bucket_start: datetime) -> Tuple[str, str, Timeframe, datetime]:
        return (tick.symbol, tick.exchange, self.timeframe_aggregator.timeframe, bucket_start)

    def ingest_tick(self, tick: Tick, session: Optional[TradingSession] = None) -> List[AggregationState]:
        self._validate_tick_timestamp(tick)
        if session and not self._is_within_session(tick, session):
            return []

        closed = self.close_pending(tick.timestamp)
        bucket_start = self.timeframe_aggregator.align_timestamp(tick.timestamp)
        bucket_end = self.timeframe_aggregator.bucket_end(bucket_start)
        state_key = self._state_key(tick, bucket_start)

        state = self._open_states.get(state_key)
        if state is None:
            state = self.builder.create_state(tick, self.timeframe_aggregator.timeframe, bucket_start, bucket_end)
            self._open_states[state_key] = state
            return closed + [state]

        if state.has_seen(tick) or state.is_closed:
            return closed

        self.builder.update_state(state, tick)
        return closed + [state]

    def close_session(self, session: TradingSession, at: datetime) -> List[AggregationState]:
        closed: List[AggregationState] = []
        for key, state in list(self._open_states.items()):
            _, exchange, timeframe, _ = key
            if (
                timeframe == self.timeframe_aggregator.timeframe
                and exchange == session.exchange
                and state.end_time <= at
                and state.start_time.date() == at.date()
            ):
                state.is_closed = True
                closed.append(state)
                del self._open_states[key]
        return closed

    def close_pending(self, at: datetime) -> List[AggregationState]:
        closed: List[AggregationState] = []
        for key, state in list(self._open_states.items()):
            if at >= state.end_time:
                state.is_closed = True
                closed.append(state)
                del self._open_states[key]
        return closed

    def _validate_tick_timestamp(self, tick: Tick) -> None:
        if tick.timestamp.tzinfo is not None:
            raise ValueError("Tick timestamp must be a naive datetime")

    def _is_within_session(self, tick: Tick, session: TradingSession) -> bool:
        timestamp_time = tick.timestamp.time()
        return session.start_time <= timestamp_time < session.end_time
