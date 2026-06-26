from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class BaseEvent:
    """Base event object."""

    name: str
    occurred_at: datetime
    payload: dict

DomainEvent = BaseEvent
