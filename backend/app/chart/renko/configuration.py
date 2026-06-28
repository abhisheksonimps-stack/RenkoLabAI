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


class ReferencePrice(str, Enum):
    """Price a percentage provider sizes bricks against."""

    CLOSE = "close"
    OPEN = "open"
    HIGH = "high"
    LOW = "low"
    TYPICAL_PRICE = "typical_price"
    MEDIAN_PRICE = "median_price"


class RoundingMode(str, Enum):
    """How a computed brick size is rounded."""

    NONE = "none"
    ROUND = "round"
    FLOOR = "floor"
    CEIL = "ceil"


@dataclass(frozen=True)
class BrickConfiguration:
    brick_type: BrickType
    brick_size: float
    price_source: PriceSource = PriceSource.CLOSE
    mode: RenkoMode = RenkoMode.LIVE
    atr_period: Optional[int] = None
    atr_multiplier: Optional[float] = None
    provider: Optional[str] = None
    builder: Optional[str] = None
    builder_type: Optional[str] = None
    percentage: Optional[float] = None
    reference_price: ReferencePrice = ReferencePrice.CLOSE
    reference_price_strategy: Optional[str] = None
    minimum_brick_size: Optional[float] = None
    rounding_mode: RoundingMode = RoundingMode.NONE
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
        if self.brick_type == BrickType.PERCENTAGE:
            return "percentage"
        return "fixed"

    def resolved_builder(self) -> str:
        """Resolve the brick-builder name.

        Precedence: explicit ``builder_type`` (Sprint 6I) wins, then the Sprint
        6F ``builder`` field, then a ``builder_type`` entry in ``metadata`` (a
        no-schema-change escape hatch), else the Traditional default. Pre-6F/6I
        configurations resolve to ``traditional`` unchanged.
        """
        if self.builder_type:
            return self.builder_type
        if self.builder:
            return self.builder
        if self.metadata:
            meta_builder = self.metadata.get("builder_type")
            if meta_builder:
                return meta_builder
        return "traditional"

    def resolved_reference_strategy(self) -> str:
        """Resolve the price-reference strategy name.

        Precedence: the explicit ``reference_price_strategy`` wins; otherwise we
        fall back to the Sprint 6D ``reference_price`` enum (default ``close``),
        keeping older percentage configs working unchanged.
        """
        if self.reference_price_strategy:
            return self.reference_price_strategy
        mapping = {
            ReferencePrice.CLOSE: "close",
            ReferencePrice.OPEN: "open",
            ReferencePrice.HIGH: "high",
            ReferencePrice.LOW: "low",
            ReferencePrice.TYPICAL_PRICE: "typical",
            ReferencePrice.MEDIAN_PRICE: "median",
        }
        if self.reference_price is not None:
            return mapping[ReferencePrice(self.reference_price)]
        return "close"
