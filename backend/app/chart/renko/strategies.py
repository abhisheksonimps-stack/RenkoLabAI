from __future__ import annotations

from typing import Any, Callable, Dict, List

from backend.app.chart.renko.configuration import BrickConfiguration, ReferencePrice
from backend.app.chart.renko.exceptions import RenkoConfigurationError
from backend.app.chart.renko.interfaces import PriceReferenceStrategy

# Same architectural style as ``BrickSizeProviderFactory``: a factory turns a
# configuration into a strategy instance. Strategies are stateless, so factories
# may return shared singletons.
PriceReferenceStrategyFactory = Callable[[BrickConfiguration], PriceReferenceStrategy]


def _ohlc(candle: Any) -> tuple[float, float, float, float]:
    """Extract (open, high, low, close) with safe fallbacks to close.

    Close is required; the other fields fall back to close when a feed omits
    them so every strategy stays well-defined and deterministic.
    """
    if not hasattr(candle, "get"):
        raise TypeError("Strategy candle must be a mapping with price fields")
    close = candle.get("close")
    if close is None:
        for key in ("open", "high", "low"):
            if candle.get(key) is not None:
                close = candle.get(key)
                break
    if close is None:
        raise ValueError("Strategy candle must contain at least one price field")
    close = float(close)
    open_ = float(candle.get("open", close))
    high = float(candle.get("high", close))
    low = float(candle.get("low", close))
    return open_, high, low, close


class ClosePriceStrategy(PriceReferenceStrategy):
    name = "close"

    def reference_price(self, candle: Any) -> float:
        return _ohlc(candle)[3]


class OpenPriceStrategy(PriceReferenceStrategy):
    name = "open"

    def reference_price(self, candle: Any) -> float:
        return _ohlc(candle)[0]


class HighPriceStrategy(PriceReferenceStrategy):
    name = "high"

    def reference_price(self, candle: Any) -> float:
        return _ohlc(candle)[1]


class LowPriceStrategy(PriceReferenceStrategy):
    name = "low"

    def reference_price(self, candle: Any) -> float:
        return _ohlc(candle)[2]


class TypicalPriceStrategy(PriceReferenceStrategy):
    """Typical Price = (High + Low + Close) / 3."""

    name = "typical"

    def reference_price(self, candle: Any) -> float:
        _, high, low, close = _ohlc(candle)
        return (high + low + close) / 3.0


class MeanPriceStrategy(PriceReferenceStrategy):
    """Mean Price = (Open + High + Low + Close) / 4."""

    name = "mean"

    def reference_price(self, candle: Any) -> float:
        open_, high, low, close = _ohlc(candle)
        return (open_ + high + low + close) / 4.0


class MedianPriceStrategy(PriceReferenceStrategy):
    """Median Price = (High + Low) / 2."""

    name = "median"

    def reference_price(self, candle: Any) -> float:
        _, high, low, _close = _ohlc(candle)
        return (high + low) / 2.0


# Map the Sprint 6D ``ReferencePrice`` enum to a strategy name for backwards
# compatibility (configs and providers built before 6E still resolve correctly).
_REFERENCE_PRICE_TO_STRATEGY: Dict[ReferencePrice, str] = {
    ReferencePrice.CLOSE: "close",
    ReferencePrice.OPEN: "open",
    ReferencePrice.HIGH: "high",
    ReferencePrice.LOW: "low",
    ReferencePrice.TYPICAL_PRICE: "typical",
    ReferencePrice.MEDIAN_PRICE: "median",
}

_BUILTIN_STRATEGIES: Dict[str, PriceReferenceStrategy] = {
    "close": ClosePriceStrategy(),
    "open": OpenPriceStrategy(),
    "high": HighPriceStrategy(),
    "low": LowPriceStrategy(),
    "typical": TypicalPriceStrategy(),
    "mean": MeanPriceStrategy(),
    "median": MedianPriceStrategy(),
}


def strategy_for_reference_price(reference_price: ReferencePrice) -> PriceReferenceStrategy:
    """Return the built-in strategy matching a 6D ``ReferencePrice`` value."""
    name = _REFERENCE_PRICE_TO_STRATEGY[ReferencePrice(reference_price)]
    return _BUILTIN_STRATEGIES[name]


class PriceReferenceStrategyRegistry:
    """Registry of price-reference strategy factories, keyed by name.

    Mirrors ``BrickSizeProviderRegistry``. Plugins can register additional
    strategies later via ``register`` without changing engine or provider code.
    """

    def __init__(self) -> None:
        self._factories: Dict[str, PriceReferenceStrategyFactory] = {}

    def register(self, name: str, factory: PriceReferenceStrategyFactory) -> None:
        if name in self._factories:
            raise ValueError(f"Strategy already registered: {name}")
        self._factories[name] = factory

    def get(self, name: str) -> PriceReferenceStrategyFactory:
        if name not in self._factories:
            raise KeyError(f"Strategy not registered: {name}")
        return self._factories[name]

    def exists(self, name: str) -> bool:
        return name in self._factories

    def names(self) -> List[str]:
        return list(self._factories.keys())

    def create(self, configuration: BrickConfiguration) -> PriceReferenceStrategy:
        name = configuration.resolved_reference_strategy()
        if name not in self._factories:
            raise RenkoConfigurationError(f"Unknown reference price strategy: {name}")
        return self._factories[name](configuration)


def default_strategy_registry() -> PriceReferenceStrategyRegistry:
    """Build a registry pre-populated with the seven built-in strategies."""
    registry = PriceReferenceStrategyRegistry()
    for name, instance in _BUILTIN_STRATEGIES.items():
        # Stateless singletons: the factory ignores configuration and returns the
        # shared instance, which keeps replay deterministic.
        registry.register(name, (lambda inst: (lambda cfg: inst))(instance))
    return registry
