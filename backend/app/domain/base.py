from dataclasses import dataclass
from datetime import datetime

@dataclass
class DomainModel:
    """Base domain model."""

    id: str
    created_at: datetime
    updated_at: datetime
