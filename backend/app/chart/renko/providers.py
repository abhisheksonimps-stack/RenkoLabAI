from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from backend.app.chart.renko.configuration import BrickConfiguration
from backend.app.chart.renko.exceptions import RenkoConfigurationError
from backend.app.chart.renko.interfaces import BrickSizeProvider

# A factory turns a configuration into a fresh provider instance. Providers hold
# rolling state, so a registry stores *factories* (not shared instances): every
# engine gets its own provider with its own state.
BrickSizeProviderFactory = Callable[[BrickConfiguration], BrickSizeProvider]


def _candle_prices(candle: Any) -> tuple[float, float, float]:
    """Extract (high, low, close) from a candle dict, with safe fallbacks.

    True Range needs high/low/close. When a feed omits high/low we fall back to
    close so the calculation stays well-defined and deterministic.
    """
    if not hasattr(candle, "get"):
        raise TypeError("Provider candle must be a mapping with price fields")
    close = candle.get("close")
    if close is None:
        # Fall back to any available price field so non-close sources still work.
        for key in ("open", "high", "low"):
            if candle.get(key) is not None:
                close = candle.get(key)
                break
    if close is None:
        raise ValueError("Provider candle must contain at least one price field")
    close = float(close)
    high = float(candle.get("high", close))
    low = float(candle.get("low", close))
    return high, low, close


class FixedBrickSizeProvider(BrickSizeProvider):
    """Constant brick size.

    Replaces the fixed-size logic that previously lived inside the engine.
    Behaviour is identical to Sprint 6B: the size is known immediately, never
    changes, and warm-up is a no-op.
    """

    name = "fixed"

    def __init__(self, brick_size: float) -> None:
        if brick_size <= 0:
            raise RenkoConfigurationError("Fixed brick size must be positive")
        self._brick_size = float(brick_size)

    @classmethod
    def from_configuration(cls, configuration: BrickConfiguration) -> "FixedBrickSizeProvider":
        return cls(configuration.brick_size)

    def update(self, candle: Any) -> None:  # noqa: D401 - fixed size ignores candles
        # A fixed provider carries no rolling state.
        return None

    def current_size(self) -> float:
        return self._brick_size

    def ready(self) -> bool:
        return True

    def reset(self) -> None:
        # No rolling state to clear; the configured size persists.
        return None


class ATRBrickSizeProvider(BrickSizeProvider):
    """Average True Range brick size: ``ATR x atr_multiplier``.

    Uses Wilder's smoothing, which is O(1) per candle with O(1) memory. The ATR
    is *not* recomputed over the full history: during warm-up only a running sum
    of True Ranges is kept; afterwards a single rolling ATR value is updated.
    No randomness and no wall-clock dependence, so replay is deterministic.
    """

    name = "atr"

    def __init__(self, atr_period: int, atr_multiplier: float) -> None:
        if atr_period is None or atr_period <= 0:
            raise RenkoConfigurationError("ATR period must be a positive integer")
        if atr_multiplier is None or atr_multiplier <= 0:
            raise RenkoConfigurationError("ATR multiplier must be positive")
        self._atr_period = int(atr_period)
        self._atr_multiplier = float(atr_multiplier)
        self._prev_close: Optional[float] = None
        self._warmup_sum: float = 0.0
        self._count: int = 0
        self._atr: Optional[float] = None

    @classmethod
    def from_configuration(cls, configuration: BrickConfiguration) -> "ATRBrickSizeProvider":
        multiplier = configuration.atr_multiplier
        if multiplier is None:
            # Backwards-friendly default: a multiplier of 1.0 means "size == ATR".
            multiplier = 1.0
        return cls(configuration.atr_period, multiplier)

    @staticmethod
    def true_range(high: float, low: float, prev_close: Optional[float]) -> float:
        if prev_close is None:
            return high - low
        return max(high - low, abs(high - prev_close), abs(low - prev_close))

    def update(self, candle: Any) -> None:
        high, low, close = _candle_prices(candle)
        tr = self.true_range(high, low, self._prev_close)

        if self._atr is None:
            # Warm-up: accumulate a running sum of True Ranges. O(1) memory.
            self._warmup_sum += tr
            self._count += 1
            if self._count >= self._atr_period:
                self._atr = self._warmup_sum / self._atr_period
        else:
            # Wilder's smoothing: rolling update, no history rescan.
            self._atr = (self._atr * (self._atr_period - 1) + tr) / self._atr_period

        self._prev_close = close

    def current_size(self) -> float:
        if self._atr is None:
            raise RuntimeError("ATR provider is not ready; warm-up incomplete")
        return self._atr * self._atr_multiplier

    def ready(self) -> bool:
        return self._atr is not None

    def reset(self) -> None:
        self._prev_close = None
        self._warmup_sum = 0.0
        self._count = 0
        self._atr = None

    # Introspection helpers (used by tests / diagnostics; not part of the engine path).
    @property
    def atr(self) -> Optional[float]:
        return self._atr

    @property
    def atr_period(self) -> int:
        return self._atr_period

    @property
    def atr_multiplier(self) -> float:
        return self._atr_multiplier


class BrickSizeProviderRegistry:
    """Registry of brick-size provider factories, keyed by name.

    Mirrors the existing ``RenkoRegistry`` style. Stores factories rather than
    instances because providers are stateful. Plugins can register additional
    providers later via ``register``.
    """

    def __init__(self) -> None:
        self._factories: Dict[str, BrickSizeProviderFactory] = {}

    def register(self, name: str, factory: BrickSizeProviderFactory) -> None:
        if name in self._factories:
            raise ValueError(f"Provider already registered: {name}")
        self._factories[name] = factory

    def get(self, name: str) -> BrickSizeProviderFactory:
        if name not in self._factories:
            raise KeyError(f"Provider not registered: {name}")
        return self._factories[name]

    def exists(self, name: str) -> bool:
        return name in self._factories

    def names(self) -> List[str]:
        return list(self._factories.keys())

    def create(self, configuration: BrickConfiguration) -> BrickSizeProvider:
        name = configuration.resolved_provider()
        factory = self.get(name)
        return factory(configuration)


def default_provider_registry() -> BrickSizeProviderRegistry:
    """Build a registry pre-populated with the built-in providers."""
    registry = BrickSizeProviderRegistry()
    registry.register("fixed", FixedBrickSizeProvider.from_configuration)
    registry.register("atr", ATRBrickSizeProvider.from_configuration)
    return registry
