from dependency_injector import containers, providers
from backend.app.configuration.loader import settings
from backend.app.database.session import DatabaseSession
from backend.app.infrastructure.repositories.base import BaseRepository
from backend.app.infrastructure.redis_client import RedisClient
from backend.app.chart.registry import ChartRegistry
from backend.app.chart.renko.factory import RenkoFactory
from backend.app.chart.renko.registry import RenkoRegistry
from backend.app.chart.renko.providers import default_provider_registry
from backend.app.chart.renko.validator import DefaultBrickValidator


class Container(containers.DeclarativeContainer):
    config = providers.Object(settings)

    database_session = providers.Singleton(DatabaseSession, config=config)
    database_connection = providers.Factory(
        database_session.provided.create_session
    )
    redis_client = providers.Singleton(RedisClient, config=config)

    repository = providers.Factory(BaseRepository, session=database_connection)

    chart_registry = providers.Singleton(ChartRegistry)
    renko_registry = providers.Singleton(RenkoRegistry)
    brick_size_provider_registry = providers.Singleton(default_provider_registry)
    renko_validator = providers.Singleton(
        DefaultBrickValidator, provider_registry=brick_size_provider_registry
    )
    renko_factory = providers.Factory(
        RenkoFactory,
        registry=renko_registry,
        provider_registry=brick_size_provider_registry,
    )

    wiring_config = containers.WiringConfiguration(packages=["backend.app.api"])


def configure_container() -> Container:
    return Container()
