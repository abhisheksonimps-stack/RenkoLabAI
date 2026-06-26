from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class ChartMetadata:
    chart_type: str
    created_at: datetime
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ChartBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trades: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChartConfiguration:
    chart_type: str
    settings: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChartContext:
    candles: List[ChartBar]
    configuration: ChartConfiguration
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Chart:
    chart_id: str
    metadata: ChartMetadata
    bars: List[ChartBar]
    configuration: ChartConfiguration
    context: ChartContext
