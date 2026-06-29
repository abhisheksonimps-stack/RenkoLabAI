"""Paper-trading domain events.

Subclasses of the platform :class:`BaseEvent`, published on the shared
``EventBus`` so downstream consumers (UI, logging, analytics, strategies) can
observe the order lifecycle without coupling to the simulator. Each carries the
standard ``name`` / ``occurred_at`` / ``payload`` fields; the payload contains a
plain-dict snapshot of the order so events remain serialisable and decoupled
from the in-memory ``Order`` instance.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.events.base import BaseEvent


@dataclass(frozen=True)
class OrderAccepted(BaseEvent):
    """An order passed validation and entered the simulator."""


@dataclass(frozen=True)
class OrderTriggered(BaseEvent):
    """A resting limit/stop order's trigger condition was met."""


@dataclass(frozen=True)
class OrderFilled(BaseEvent):
    """An order was filled and applied to the portfolio."""


@dataclass(frozen=True)
class OrderRejected(BaseEvent):
    """An order was rejected (e.g. no price, insufficient cash)."""


@dataclass(frozen=True)
class OrderCancelled(BaseEvent):
    """A resting order was cancelled before filling."""
