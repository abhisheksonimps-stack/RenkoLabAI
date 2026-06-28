from dependency_injector import containers, providers
from backend.app.configuration.loader import settings
from backend.app.database.session import DatabaseSession
from backend.app.infrastructure.repositories.base import BaseRepository
from backend.app.infrastructure.redis_client import RedisClient
from backend.app.chart.registry import ChartRegistry
from backend.app.chart.renko.factory import RenkoFactory
from backend.app.chart.renko.registry import RenkoRegistry
from backend.app.chart.renko.providers import default_provider_registry
from backend.app.chart.renko.strategies import default_strategy_registry
from backend.app.chart.renko.builder import default_builder_registry
from backend.app.chart.renko.snapshot import JsonSnapshotSerializer, SnapshotManager
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
    price_reference_strategy_registry = providers.Singleton(default_strategy_registry)
    brick_builder_registry = providers.Singleton(default_builder_registry)
    renko_validator = providers.Singleton(
        DefaultBrickValidator,
        provider_registry=brick_size_provider_registry,
        strategy_registry=price_reference_strategy_registry,
        builder_registry=brick_builder_registry,
    )
    renko_factory = providers.Factory(
        RenkoFactory,
        registry=renko_registry,
        provider_registry=brick_size_provider_registry,
        strategy_registry=price_reference_strategy_registry,
        builder_registry=brick_builder_registry,
    )

    snapshot_serializer = providers.Singleton(JsonSnapshotSerializer)
    snapshot_manager = providers.Factory(
        SnapshotManager,
        serializer=snapshot_serializer,
        provider_registry=brick_size_provider_registry,
        strategy_registry=price_reference_strategy_registry,
        builder_registry=brick_builder_registry,
    )

    wiring_config = containers.WiringConfiguration(packages=["backend.app.api"])


def configure_container() -> Container:
    return Container()
