"""Dependency injection container configuration."""

from __future__ import annotations

from typing import Any, Callable

try:
    from dependency_injector import containers, providers
except ImportError:  # pragma: no cover - used in minimal test/runtime environments
    containers = None  # type: ignore[assignment]
    providers = None  # type: ignore[assignment]

from backend.app.chart.registry import ChartRegistry
from backend.app.chart.renko.builder import default_builder_registry
from backend.app.chart.renko.factory import RenkoFactory
from backend.app.chart.renko.providers import default_provider_registry
from backend.app.chart.renko.registry import RenkoRegistry
from backend.app.chart.renko.snapshot import JsonSnapshotSerializer, SnapshotManager
from backend.app.chart.renko.strategies import default_strategy_registry
from backend.app.chart.renko.validator import DefaultBrickValidator
from backend.app.configuration.loader import settings
from backend.app.database.session import DatabaseSession
from backend.app.infrastructure.redis_client import RedisClient
from backend.app.infrastructure.repositories.base import BaseRepository


class _SimpleProvider:
    """Small provider compatible with dependency_injector's call syntax."""

    def __init__(self, factory: Callable[..., Any], *, singleton: bool = False, **kwargs: Any) -> None:
        self._factory = factory
        self._kwargs = kwargs
        self._singleton = singleton
        self._instance: Any = None
        self._created = False

    def __call__(self) -> Any:
        if self._singleton:
            if not self._created:
                self._instance = self._factory(**self._resolve_kwargs())
                self._created = True
            return self._instance
        return self._factory(**self._resolve_kwargs())

    def _resolve_kwargs(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for key, value in self._kwargs.items():
            values[key] = value() if callable(value) and isinstance(value, _SimpleProvider) else value
        return values


class _SimpleContainer:
    """Fallback application container when dependency-injector is not installed."""

    def __init__(self) -> None:
        self.config = settings
        self.database_session = _SimpleProvider(DatabaseSession, singleton=True, config=settings)
        self.database_connection = _SimpleProvider(lambda: self.database_session().create_session())
        self.redis_client = _SimpleProvider(RedisClient, singleton=True, config=settings)
        self.repository = _SimpleProvider(BaseRepository, session=self.database_connection)
        self.chart_registry = _SimpleProvider(ChartRegistry, singleton=True)
        self.renko_registry = _SimpleProvider(RenkoRegistry, singleton=True)
        self.brick_size_provider_registry = _SimpleProvider(default_provider_registry, singleton=True)
        self.price_reference_strategy_registry = _SimpleProvider(default_strategy_registry, singleton=True)
        self.brick_builder_registry = _SimpleProvider(default_builder_registry, singleton=True)
        self.renko_validator = _SimpleProvider(
            DefaultBrickValidator,
            singleton=True,
            provider_registry=self.brick_size_provider_registry(),
            strategy_registry=self.price_reference_strategy_registry(),
            builder_registry=self.brick_builder_registry(),
        )
        self.renko_factory = _SimpleProvider(
            RenkoFactory,
            registry=self.renko_registry(),
            provider_registry=self.brick_size_provider_registry(),
            strategy_registry=self.price_reference_strategy_registry(),
            builder_registry=self.brick_builder_registry(),
        )
        self.snapshot_serializer = _SimpleProvider(JsonSnapshotSerializer, singleton=True)
        self.snapshot_manager = _SimpleProvider(
            SnapshotManager,
            serializer=self.snapshot_serializer(),
            provider_registry=self.brick_size_provider_registry(),
            strategy_registry=self.price_reference_strategy_registry(),
            builder_registry=self.brick_builder_registry(),
        )

    async def init_resources(self) -> None:
        await self.redis_client().connect()

    async def shutdown_resources(self) -> None:
        await self.redis_client().close()


if containers is not None and providers is not None:

    class Container(containers.DeclarativeContainer):
        """Production dependency-injector container."""

        config = providers.Object(settings)

        database_session = providers.Singleton(DatabaseSession, config=config)
        database_connection = providers.Factory(database_session.provided.create_session)
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

else:
    Container = _SimpleContainer  # type: ignore[assignment]


def configure_container() -> Container:
    """Build the application dependency container."""
    return Container()
