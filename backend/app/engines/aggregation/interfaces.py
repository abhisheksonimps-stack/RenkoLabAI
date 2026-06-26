from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from backend.app.domain.market_data.models import Candle, Tick, TradingSession
from backend.app.domain.market_data.enums import Timeframe
from backend.app.engines.aggregation.models import AggregationState


class CandleBuilder(ABC):
    @abstractmethod
    def create_state(self, tick: Tick, timeframe: Timeframe, start_time: datetime, end_time: datetime) -> AggregationState:
        raise NotImplementedError

    @abstractmethod
    def update_state(self, state: AggregationState, tick: Tick) -> AggregationState:
        raise NotImplementedError

    @abstractmethod
    def finalize_candle(self, state: AggregationState) -> Candle:
        raise NotImplementedError


class TimeframeAggregator(ABC):
    @abstractmethod
    def align_timestamp(self, timestamp: datetime) -> datetime:
        raise NotImplementedError

    @abstractmethod
    def bucket_end(self, start_time: datetime) -> datetime:
        raise NotImplementedError


class TickAggregator(ABC):
    @abstractmethod
    def ingest_tick(self, tick: Tick, session: Optional[TradingSession] = None) -> list[AggregationState]:
        raise NotImplementedError

    @abstractmethod
    def close_session(self, session: TradingSession, at: datetime) -> list[AggregationState]:
        raise NotImplementedError

    @abstractmethod
    def close_pending(self, at: datetime) -> list[AggregationState]:
        raise NotImplementedError
