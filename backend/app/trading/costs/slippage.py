"""Slippage models.

Independent of execution/venue: each model maps a reference price + trade
direction to the actual fill price. Convention: buys fill no better than the
reference (price up), sells no better (price down). ``side`` is the string
``"buy"`` or ``"sell"`` so this module stays decoupled from the order types.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


def _is_buy(side: str) -> bool:
    return str(side).lower() == "buy"


class SlippageModel(ABC):
    @abstractmethod
    def adjust(self, *, price: float, side: str) -> float:
        """Return the fill price after slippage."""


class ZeroSlippage(SlippageModel):
    def adjust(self, *, price: float, side: str) -> float:
        return float(price)


class FixedSlippage(SlippageModel):
    """Absolute price offset against the trader."""

    def __init__(self, amount: float) -> None:
        if amount < 0:
            raise ValueError("FixedSlippage amount must be >= 0")
        self.amount = float(amount)

    def adjust(self, *, price: float, side: str) -> float:
        return float(price) + self.amount if _is_buy(side) else float(price) - self.amount


class PercentageSlippage(SlippageModel):
    """Fractional price offset against the trader (e.g. 0.0005 = 5 bps)."""

    def __init__(self, rate: float) -> None:
        if rate < 0:
            raise ValueError("PercentageSlippage rate must be >= 0")
        self.rate = float(rate)

    def adjust(self, *, price: float, side: str) -> float:
        factor = (1.0 + self.rate) if _is_buy(side) else (1.0 - self.rate)
        return float(price) * factor
