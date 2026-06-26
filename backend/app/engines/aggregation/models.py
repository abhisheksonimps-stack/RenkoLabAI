from __future__ import annotations

from datetime import datetime
from typing import Optional, Set, Tuple

from pydantic import BaseModel, Field, model_validator

from backend.app.domain.market_data.enums import Timeframe
from backend.app.domain.market_data.models import Tick

TickSignature = Tuple[str, str, str, float, Optional[float], Optional[float], Optional[float]]


class AggregationState(BaseModel):
    symbol: str
    exchange: str
    timeframe: Timeframe
    start_time: datetime
    end_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trades: int
    last_timestamp: datetime
    tick_signatures: Set[TickSignature] = Field(default_factory=set)
    is_closed: bool = False

    @model_validator(mode="after")
    def validate_times(cls, values):
        if values.end_time <= values.start_time:
            raise ValueError("AggregationState end_time must be after start_time")
        return values

    def signature_for(self, tick: Tick) -> TickSignature:
        return (
            tick.symbol,
            tick.exchange,
            tick.timestamp.isoformat(),
            tick.price,
            tick.size,
            tick.bid,
            tick.ask,
        )

    def has_seen(self, tick: Tick) -> bool:
        return self.signature_for(tick) in self.tick_signatures

    def record_tick(self, tick: Tick) -> None:
        self.tick_signatures.add(self.signature_for(tick))
