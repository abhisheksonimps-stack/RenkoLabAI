from dependency_injector import containers, providers
from backend.app.configuration.loader import settings
from backend.app.database.session import DatabaseSession
from backend.app.infrastructure.repositories.base import BaseRepository
from backend.app.infrastructure.redis_client import RedisClient


class Container(containers.DeclarativeContainer):
    config = providers.Object(settings)

    database_session = providers.Singleton(DatabaseSession, config=config)
    database_connection = providers.Factory(
        database_session.provided.create_session
    )
    redis_client = providers.Singleton(RedisClient, config=config)

    repository = providers.Factory(BaseRepository, session=database_connection)

    wiring_config = containers.WiringConfiguration(packages=["backend.app.api"])


def configure_container() -> Container:
    return Container()
