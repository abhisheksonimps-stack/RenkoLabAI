from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from backend.app.domain.market_data.enums import Timeframe
from backend.app.domain.market_data.models import Candle, Tick, TradingSession
from backend.app.engines.aggregation.aggregator import DefaultTickAggregator, FixedIntervalTimeframeAggregator
from backend.app.engines.aggregation.builder import DefaultCandleBuilder
from backend.app.engines.aggregation.events import CandleClosed, CandleOpened, CandleUpdated
from backend.app.engines.aggregation.interfaces import TickAggregator
from backend.app.events.bus import EventBus


class AggregationEngine:
    def __init__(self, event_bus: EventBus, timeframe: Timeframe) -> None:
        self.event_bus = event_bus
        self.timeframe = timeframe
        self.timeframe_aggregator = FixedIntervalTimeframeAggregator(timeframe)
        self.builder = DefaultCandleBuilder()
        self.aggregator: TickAggregator = DefaultTickAggregator(self.timeframe_aggregator, self.builder)

        self.event_bus.register_event(CandleOpened)
        self.event_bus.register_event(CandleUpdated)
        self.event_bus.register_event(CandleClosed)

    async def process_tick(self, tick: Tick, session: Optional[TradingSession] = None) -> None:
        closed_states = self.aggregator.close_pending(tick.timestamp)
        for state in closed_states:
            await self._publish_event(CandleClosed, state)

        states = self.aggregator.ingest_tick(tick, session)

        for state in states:
            if state.is_closed:
                await self._publish_event(CandleClosed, state)
            elif state.trades == 1:
                await self._publish_event(CandleOpened, state)
            else:
                await self._publish_event(CandleUpdated, state)

    async def close_session(self, session: TradingSession, at: datetime) -> None:
        closed_states = self.aggregator.close_session(session, at)
        for state in closed_states:
            await self._publish_event(CandleClosed, state)

    async def close_pending_candles(self, at: datetime) -> None:
        closed_states = self.aggregator.close_pending(at)
        for state in closed_states:
            await self._publish_event(CandleClosed, state)

    async def _publish_event(self, event_type, state) -> None:
        candle = self.builder.finalize_candle(state)
        event = event_type(
            name=event_type.__name__,
            occurred_at=datetime.utcnow(),
            payload={"candle": candle.model_dump()},
        )
        await self.event_bus.publish(event)
