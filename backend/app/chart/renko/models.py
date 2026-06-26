from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class BrickDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    NEUTRAL = "neutral"


class BrickType(str, Enum):
    TRADITIONAL = "traditional"
    ATR = "atr"
    PERCENTAGE = "percentage"
    MEAN = "mean"
    MEDIAN = "median"
    HYBRID = "hybrid"
    AI = "ai"


@dataclass(frozen=True)
class BrickState:
    direction: BrickDirection
    last_price: float
    brick_size: float
    is_open: bool
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BrickSnapshot:
    configuration: "BrickConfiguration"
    state: BrickState
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Brick:
    brick_id: str
    direction: BrickDirection
    open_price: float
    close_price: float
    high_price: float
    low_price: float
    volume: float
    created_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
