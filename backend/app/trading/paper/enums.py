"""Paper-trading order classifications.

These describe *how* and *when* an order should match — concerns specific to a
simulated venue, and intentionally absent from the venue-agnostic ``Order`` type
in :mod:`backend.app.trading.execution.order`. Keeping them here means the core
``Order``/``Fill`` primitives stay reusable across backtest, paper, and live
without acquiring paper-specific fields.
"""

from __future__ import annotations

from enum import Enum


class OrderType(str, Enum):
    """The execution semantics of a paper order."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class TimeInForce(str, Enum):
    """How long a resting order remains live on the simulated book.

    GTC (good-til-cancelled) rests until it triggers or is cancelled. IOC
    (immediate-or-cancel) is matched against the very next market update only;
    if it does not trigger then, it is cancelled.
    """

    GTC = "gtc"
    IOC = "ioc"
