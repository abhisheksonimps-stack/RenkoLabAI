from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class ReplayCursor(Generic[T]):
    timestamp: datetime
    payload: T
