from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from backend.app.chart.renko.models import BrickType


class PriceSource(str, Enum):
    OPEN = "open"
    HIGH = "high"
    LOW = "low"
    CLOSE = "close"
    TYPICAL = "typical"


class RenkoMode(str, Enum):
    LIVE = "live"
    REPLAY = "replay"
    BACKTEST = "backtest"


@dataclass(frozen=True)
class BrickConfiguration:
    brick_type: BrickType
    brick_size: float
    price_source: PriceSource = PriceSource.CLOSE
    mode: RenkoMode = RenkoMode.LIVE
    atr_period: Optional[int] = None
    percentage: Optional[float] = None
    mean_lookback: Optional[int] = None
    median_lookback: Optional[int] = None
    hybrid_weight: Optional[float] = None
    ai_model: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
