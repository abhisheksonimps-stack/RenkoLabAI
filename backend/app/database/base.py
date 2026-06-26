from typing import Protocol
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

class DatabaseBootstrap(Protocol):
    """Database bootstrap helper interface."""

    @property
    def engine(self) -> AsyncEngine:
        ...

    def create_session(self) -> AsyncSession:
        ...
