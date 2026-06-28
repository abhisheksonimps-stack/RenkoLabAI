from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List

from backend.app.chart.renko.configuration import BrickConfiguration
from backend.app.chart.renko.interfaces import BrickBuilder
from backend.app.chart.renko.models import Brick, BrickDirection


class TraditionalBrickBuilder(BrickBuilder):
    name = "traditional"

    async def build_brick(self, market_data: Any, configuration: BrickConfiguration) -> Brick:
        if not isinstance(market_data, dict):
            raise TypeError("Brick builder market_data must be a dict")

        # The engine already supplies a BrickDirection; only re-validate when a
        # raw value (e.g. a string from an external caller) is passed. Identical
        # result, but avoids the enum __call__ on the hot path.
        raw_direction = market_data["direction"]
        direction = (
            raw_direction
            if isinstance(raw_direction, BrickDirection)
            else BrickDirection(raw_direction)
        )
        open_price = float(market_data["open_price"])
        close_price = float(market_data["close_price"])
        # Avoid computing the max/min default unless the field is actually absent
        # (the engine always provides them). Same output, fewer calls.
        high = market_data.get("high_price")
        high_price = float(high) if high is not None else max(open_price, close_price)
        low = market_data.get("low_price")
        low_price = float(low) if low is not None else min(open_price, close_price)
        volume = float(market_data.get("volume", 0.0) or 0.0)
        timestamp = market_data["timestamp"]

        if not isinstance(timestamp, datetime):
            raise TypeError("Brick timestamp must be a datetime")

        brick_id = (
            f"brick-{direction.value}-{timestamp.isoformat()}-"
            f"{int(open_price * 100000)}-{int(close_price * 100000)}"
        )

        return Brick(
            brick_id=brick_id,
            direction=direction,
            open_price=open_price,
            close_price=close_price,
            high_price=high_price,
            low_price=low_price,
            volume=volume,
            created_at=timestamp,
            metadata={
                "brick_size": configuration.brick_size,
                "price_source": configuration.price_source.value,
            },
        )


# Same architectural style as BrickSizeProviderFactory / PriceReferenceStrategyFactory:
# a factory turns a configuration into a builder instance. Builders are stateless
# (a pure market_data -> Brick transform), so factories may return fresh
# instances or singletons without affecting determinism.
BrickBuilderFactory = Callable[[BrickConfiguration], BrickBuilder]


class BrickBuilderRegistry:
    """Registry of brick-builder factories, keyed by name.

    Mirrors ``BrickSizeProviderRegistry`` and ``PriceReferenceStrategyRegistry``.
    Plugins can register additional builders later via ``register`` without
    changing engine code.
    """

    def __init__(self) -> None:
        self._factories: Dict[str, BrickBuilderFactory] = {}

    def register(self, name: str, factory: BrickBuilderFactory) -> None:
        if name in self._factories:
            raise ValueError(f"Builder already registered: {name}")
        self._factories[name] = factory

    def get(self, name: str) -> BrickBuilderFactory:
        if name not in self._factories:
            raise KeyError(f"Builder not registered: {name}")
        return self._factories[name]

    def exists(self, name: str) -> bool:
        return name in self._factories

    def names(self) -> List[str]:
        return list(self._factories.keys())

    def create(self, configuration: BrickConfiguration) -> BrickBuilder:
        name = configuration.resolved_builder()
        factory = self.get(name)
        return factory(configuration)


def default_builder_registry() -> BrickBuilderRegistry:
    """Build a registry pre-populated with the built-in Traditional builder."""
    registry = BrickBuilderRegistry()
    registry.register("traditional", lambda configuration: TraditionalBrickBuilder())
    return registry
