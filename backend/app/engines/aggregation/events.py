from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.app.domain.market_data.models import Candle
from backend.app.events.base import BaseEvent


@dataclass(frozen=True)
class CandleOpened(BaseEvent):
    pass


@dataclass(frozen=True)
class CandleUpdated(BaseEvent):
    pass


@dataclass(frozen=True)
class CandleClosed(BaseEvent):
    pass
