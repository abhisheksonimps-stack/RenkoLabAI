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
    atr_multiplier: Optional[float] = None
    provider: Optional[str] = None
    percentage: Optional[float] = None
    mean_lookback: Optional[int] = None
    median_lookback: Optional[int] = None
    hybrid_weight: Optional[float] = None
    ai_model: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def resolved_provider(self) -> str:
        """Resolve the brick-size provider name.

        Backwards compatible: configurations that pre-date Sprint 6C do not set
        ``provider``. When it is omitted we derive it from ``brick_type`` so old
        Fixed Renko configurations keep working unchanged.
        """
        if self.provider:
            return self.provider
        if self.brick_type == BrickType.ATR:
            return "atr"
        return "fixed"
