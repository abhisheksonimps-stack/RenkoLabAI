"""Brokerage (commission) models.

Independent of execution/venue: each model maps a fill (quantity, price) to a
commission. Reusable across backtest, paper, and live.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BrokerageModel(ABC):
    @abstractmethod
    def cost(self, *, quantity: float, price: float) -> float:
        """Commission for a fill of ``quantity`` at ``price`` (>= 0)."""


class ZeroBrokerage(BrokerageModel):
    def cost(self, *, quantity: float, price: float) -> float:
        return 0.0


class FixedBrokerage(BrokerageModel):
    """Flat commission per fill."""

    def __init__(self, amount: float) -> None:
        if amount < 0:
            raise ValueError("FixedBrokerage amount must be >= 0")
        self.amount = float(amount)

    def cost(self, *, quantity: float, price: float) -> float:
        return self.amount


class PercentageBrokerage(BrokerageModel):
    """Commission as a fraction of notional (e.g. 0.001 = 0.1%)."""

    def __init__(self, rate: float) -> None:
        if rate < 0:
            raise ValueError("PercentageBrokerage rate must be >= 0")
        self.rate = float(rate)

    def cost(self, *, quantity: float, price: float) -> float:
        return abs(quantity) * abs(price) * self.rate


class PerShareBrokerage(BrokerageModel):
    """Commission per unit traded."""

    def __init__(self, per_share: float) -> None:
        if per_share < 0:
            raise ValueError("PerShareBrokerage per_share must be >= 0")
        self.per_share = float(per_share)

    def cost(self, *, quantity: float, price: float) -> float:
        return abs(quantity) * self.per_share
