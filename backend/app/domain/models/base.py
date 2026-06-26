from dataclasses import dataclass
from datetime import datetime


@dataclass
class DomainEntity:
    id: str
    created_at: datetime
    updated_at: datetime
