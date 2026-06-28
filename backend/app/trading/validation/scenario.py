"""Scenario — one immutable, fully-resolved backtest configuration.

A Scenario is a pure description (no strategy instance, no data); the runner
materializes those at run time. It carries a deterministic ``scenario_id`` (a
hash of its defining inputs) for reproducibility and de-duplication.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Tuple


class ScenarioStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class BrickSpec:
    brick_type: str = "traditional"
    brick_size: float = 1.0
    timeframe: str = "renko"


@dataclass(frozen=True)
class RiskSettings:
    starting_capital: float = 100_000.0
    position_fraction: float = 0.95
    fixed_quantity: Optional[float] = None
    leverage: float = 1.0
    # Cost specs are primitives (kept serializable/hashable); the runner maps
    # them onto the frozen cost models.
    brokerage: str = "zero"          # zero | fixed | percentage | per_share
    brokerage_value: float = 0.0
    slippage: str = "zero"           # zero | fixed | percentage
    slippage_value: float = 0.0


@dataclass(frozen=True)
class MarketInfo:
    """Optional market metadata for future multi-market support."""

    exchange: str = "UNKNOWN"
    market: str = "UNKNOWN"
    currency: str = "UNKNOWN"


@dataclass(frozen=True)
class Scenario:
    strategy_name: str
    strategy_params: Tuple[Tuple[str, Any], ...]   # canonical sorted (key, value) pairs
    brick: BrickSpec
    symbol: str
    dataset_id: str
    date_range: Tuple[Optional[str], Optional[str]] = (None, None)
    risk: RiskSettings = RiskSettings()
    market: MarketInfo = MarketInfo()
    scenario_id: str = field(init=False, default="")

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenario_id", self._compute_id())

    @classmethod
    def create(
        cls,
        strategy_name: str,
        strategy_params: Optional[Mapping[str, Any]] = None,
        *,
        brick: Optional[BrickSpec] = None,
        symbol: str = "UNKNOWN",
        dataset_id: str = "default",
        date_range: Tuple[Optional[str], Optional[str]] = (None, None),
        risk: Optional[RiskSettings] = None,
        market: Optional[MarketInfo] = None,
    ) -> "Scenario":
        params = strategy_params or {}
        canonical = tuple(sorted((str(k), v) for k, v in params.items()))
        return cls(
            strategy_name=strategy_name,
            strategy_params=canonical,
            brick=brick or BrickSpec(),
            symbol=symbol,
            dataset_id=dataset_id,
            date_range=tuple(date_range),
            risk=risk or RiskSettings(),
            market=market or MarketInfo(),
        )

    @property
    def params(self) -> dict:
        return dict(self.strategy_params)

    def _compute_id(self) -> str:
        payload = {
            "strategy": self.strategy_name,
            "params": [list(p) for p in self.strategy_params],
            "brick": [self.brick.brick_type, self.brick.brick_size, self.brick.timeframe],
            "symbol": self.symbol,
            "dataset": self.dataset_id,
            "date_range": list(self.date_range),
            "risk": [
                self.risk.starting_capital, self.risk.position_fraction,
                self.risk.fixed_quantity, self.risk.leverage,
                self.risk.brokerage, self.risk.brokerage_value,
                self.risk.slippage, self.risk.slippage_value,
            ],
            "market": [self.market.exchange, self.market.market, self.market.currency],
        }
        blob = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]
