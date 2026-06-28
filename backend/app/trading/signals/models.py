"""Trading signal types and the immutable Signal value object.

The strategy layer emits exactly four signal types. These models are pure data;
they carry no behaviour and no dependency on the Renko engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class SignalType(str, Enum):
    """The four trading signals produced by strategies."""

    BUY = "buy"
    SELL = "sell"
    EXIT = "exit"
    HOLD = "hold"


@dataclass(frozen=True)
class Signal:
    """A single, immutable trading decision tied to a completed brick.

    ``type`` is the decision. The remaining fields are context for inspection
    and testing (which brick produced it, the brick close, and the indicator
    reference value at that point). They never alter the decision.
    """

    type: SignalType
    brick_id: Optional[str] = None
    price: Optional[float] = None
    reference: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_actionable(self) -> bool:
        """True for everything except HOLD."""
        return self.type is not SignalType.HOLD
