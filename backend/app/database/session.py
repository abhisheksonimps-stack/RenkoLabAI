from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from backend.app.configuration.loader import settings


class DatabaseSession:
    def __init__(self, config) -> None:
        self._engine: AsyncEngine = create_async_engine(
            f"postgresql+asyncpg://{config.database_user}:{config.database_password}@{config.database_host}:{config.database_port}/{config.database_name}",
            future=True,
            echo=False,
        )
        self._session_factory = sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    def create_session(self) -> AsyncSession:
        return self._session_factory()
