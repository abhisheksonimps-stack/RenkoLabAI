"""Trading signal types and immutable Signal value object.

The signal model remains venue-agnostic and backwards compatible with the
Sprint T1/T2 long-only engines while exposing Sprint 8 explicit exit aliases.
``EXIT_LONG`` and ``EXIT_SHORT`` intentionally alias ``EXIT`` so existing tests
and iteration over ``SignalType`` continue to see the original four canonical
values. Direction-specific exit intent is carried by strategy metadata until the
execution layer grows native short support.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class SignalType(str, Enum):
    """Canonical trading signals produced by strategies.

    ``EXIT_LONG`` and ``EXIT_SHORT`` are aliases of ``EXIT`` for backwards
    compatibility with the existing backtesting engine and SignalType tests.
    """

    BUY = "buy"
    SELL = "sell"
    EXIT = "exit"
    EXIT_LONG = "exit"
    EXIT_SHORT = "exit"
    HOLD = "hold"


@dataclass(frozen=True)
class Signal:
    """A single immutable trading decision.

    ``type`` is the execution decision. Remaining fields are context for
    inspection, reporting, testing, and integration; they never alter the
    decision itself.
    """

    type: SignalType
    brick_id: Optional[str] = None
    price: Optional[float] = None
    reference: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_actionable(self) -> bool:
        """True for every signal except HOLD."""
        return self.type is not SignalType.HOLD

    @property
    def is_entry(self) -> bool:
        """True for BUY and SELL entry signals."""
        return self.type in (SignalType.BUY, SignalType.SELL)

    @property
    def is_exit(self) -> bool:
        """True for any exit signal."""
        return self.type is SignalType.EXIT

    @classmethod
    def hold(cls) -> "Signal":
        """Create a HOLD signal."""
        return cls(SignalType.HOLD)
