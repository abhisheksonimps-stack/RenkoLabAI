from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from backend.app.chart.renko.builder import BrickBuilderRegistry
from backend.app.chart.renko.configuration import BrickConfiguration
from backend.app.chart.renko.exceptions import (
    CorruptedSnapshotError,
    IncompatibleSnapshotError,
    SnapshotVersionError,
)
from backend.app.chart.renko.providers import BrickSizeProviderRegistry
from backend.app.chart.renko.serialization import configuration_from_dict
from backend.app.chart.renko.strategies import PriceReferenceStrategyRegistry

# Current snapshot schema version. Future versions must remain extensible: add
# fields with defaults and bump this, then handle older versions on load.
SNAPSHOT_SCHEMA_VERSION = 1

_REQUIRED_FIELDS = (
    "schema_version",
    "engine_type",
    "configuration",
    "builder_state",
    "brick_history",
    "provider_state",
    "strategy_state",
    "metadata",
)


@dataclass
class EngineState:
    """Serializable snapshot of an engine's complete resumable state.

    Holds only JSON-compatible primitives (dicts/lists/str/float/int/bool/None),
    so any ``SnapshotSerializer`` format (JSON now, binary later) can encode it.
    """

    schema_version: int
    engine_type: str
    configuration: Dict[str, Any]
    builder_state: Dict[str, Any]
    brick_history: List[Dict[str, Any]]
    provider_state: Dict[str, Any]
    strategy_state: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "engine_type": self.engine_type,
            "configuration": self.configuration,
            "builder_state": self.builder_state,
            "brick_history": self.brick_history,
            "provider_state": self.provider_state,
            "strategy_state": self.strategy_state,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "EngineState":
        if not isinstance(data, dict):
            raise CorruptedSnapshotError("Snapshot payload must be a JSON object")
        missing = [key for key in _REQUIRED_FIELDS if key not in data]
        if missing:
            raise CorruptedSnapshotError(
                f"Snapshot is missing required field(s): {', '.join(missing)}"
            )
        return cls(
            schema_version=data["schema_version"],
            engine_type=data["engine_type"],
            configuration=data["configuration"],
            builder_state=data["builder_state"],
            brick_history=data["brick_history"],
            provider_state=data["provider_state"],
            strategy_state=data["strategy_state"],
            metadata=data.get("metadata", {}),
        )


class SnapshotSerializer(ABC):
    """Serializes an EngineState to/from a transport format.

    The abstraction lets future binary serializers drop in without touching the
    engine or the SnapshotManager.
    """

    format: str = "abstract"

    @abstractmethod
    def serialize(self, state: EngineState) -> str:
        raise NotImplementedError

    @abstractmethod
    def deserialize(self, data: str) -> EngineState:
        raise NotImplementedError


class JsonSnapshotSerializer(SnapshotSerializer):
    """JSON implementation of the snapshot serializer."""

    format = "json"

    def __init__(self, *, indent: Optional[int] = None, sort_keys: bool = True) -> None:
        # sort_keys keeps output stable/deterministic across runs.
        self._indent = indent
        self._sort_keys = sort_keys

    def serialize(self, state: EngineState) -> str:
        return json.dumps(state.to_dict(), indent=self._indent, sort_keys=self._sort_keys)

    def deserialize(self, data: str) -> EngineState:
        try:
            payload = json.loads(data)
        except (json.JSONDecodeError, TypeError) as exc:
            raise CorruptedSnapshotError(f"Snapshot is not valid JSON: {exc}") from exc
        return EngineState.from_dict(payload)


def validate_snapshot(
    state: EngineState,
    *,
    supported_engine_types: Optional[set[str]] = None,
    provider_registry: Optional[BrickSizeProviderRegistry] = None,
    strategy_registry: Optional[PriceReferenceStrategyRegistry] = None,
    builder_registry: Optional[BrickBuilderRegistry] = None,
) -> BrickConfiguration:
    """Validate a snapshot and return its reconstructed configuration.

    Checks schema version, required fields (already enforced by
    ``EngineState.from_dict``), engine-type compatibility, and that the
    configured provider / strategy / builder are resolvable in their registries.
    """
    if state.schema_version != SNAPSHOT_SCHEMA_VERSION:
        raise SnapshotVersionError(
            f"Unsupported snapshot schema_version {state.schema_version}; "
            f"expected {SNAPSHOT_SCHEMA_VERSION}"
        )

    if supported_engine_types is not None and state.engine_type not in supported_engine_types:
        raise IncompatibleSnapshotError(
            f"Snapshot engine_type '{state.engine_type}' is not supported "
            f"(supported: {sorted(supported_engine_types)})"
        )

    try:
        configuration = configuration_from_dict(state.configuration)
    except Exception as exc:  # malformed configuration block
        raise CorruptedSnapshotError(f"Snapshot configuration is invalid: {exc}") from exc

    if provider_registry is not None:
        name = configuration.resolved_provider()
        if not provider_registry.exists(name):
            raise IncompatibleSnapshotError(f"Snapshot requires unknown provider: {name}")
    if strategy_registry is not None:
        name = configuration.resolved_reference_strategy()
        if not strategy_registry.exists(name):
            raise IncompatibleSnapshotError(f"Snapshot requires unknown strategy: {name}")
    if builder_registry is not None:
        name = configuration.resolved_builder()
        if not builder_registry.exists(name):
            raise IncompatibleSnapshotError(f"Snapshot requires unknown builder: {name}")

    return configuration


class SnapshotManager:
    """Saves and restores engines through the persistence pipeline.

    Reconstructs provider / strategy / builder from their registries (so
    plugin-registered components are restorable by name, with no hardcoding),
    then hands the EngineState to ``engine.restore`` to import component state,
    rebuild brick history, and resume — without replaying any candles.
    """

    SUPPORTED_ENGINE_TYPES = {"traditional"}

    def __init__(
        self,
        serializer: SnapshotSerializer,
        provider_registry: BrickSizeProviderRegistry,
        strategy_registry: PriceReferenceStrategyRegistry,
        builder_registry: BrickBuilderRegistry,
        engine_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        self._serializer = serializer
        self._provider_registry = provider_registry
        self._strategy_registry = strategy_registry
        self._builder_registry = builder_registry
        self._engine_factory = engine_factory

    @property
    def serializer(self) -> SnapshotSerializer:
        return self._serializer

    def create_snapshot(self, engine: Any) -> EngineState:
        return engine.snapshot()

    def save(self, engine: Any) -> str:
        return self._serializer.serialize(engine.snapshot())

    def serialize(self, state: EngineState) -> str:
        return self._serializer.serialize(state)

    def deserialize(self, data: str) -> EngineState:
        return self._serializer.deserialize(data)

    def _make_engine(self, *, provider, builder, event_bus):
        factory = self._engine_factory
        if factory is None:
            # Deferred import avoids a module-level cycle (engine imports snapshot).
            from backend.app.chart.renko.engine import TraditionalRenkoEngine

            factory = TraditionalRenkoEngine
        return factory(event_bus=event_bus, provider=provider, builder=builder)

    def restore(self, data: Any, *, event_bus: Any = None) -> Any:
        """Restore a fully-wired engine from a serialized snapshot or EngineState."""
        state = data if isinstance(data, EngineState) else self.deserialize(data)
        configuration = validate_snapshot(
            state,
            supported_engine_types=self.SUPPORTED_ENGINE_TYPES,
            provider_registry=self._provider_registry,
            strategy_registry=self._strategy_registry,
            builder_registry=self._builder_registry,
        )

        provider = self._provider_registry.create(configuration)
        inject_strategy = getattr(provider, "set_price_reference_strategy", None)
        if callable(inject_strategy):
            inject_strategy(self._strategy_registry.create(configuration))
        builder = self._builder_registry.create(configuration)

        engine = self._make_engine(provider=provider, builder=builder, event_bus=event_bus)
        engine.restore(state)
        return engine
