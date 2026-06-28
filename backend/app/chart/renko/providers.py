from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional

from backend.app.chart.renko.configuration import (
    BrickConfiguration,
    ReferencePrice,
    RoundingMode,
)
from backend.app.chart.renko.exceptions import RenkoConfigurationError
from backend.app.chart.renko.interfaces import BrickSizeProvider, PriceReferenceStrategy
from backend.app.chart.renko.strategies import (
    ClosePriceStrategy,
    strategy_for_reference_price,
)

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

    def export_state(self) -> dict:
        return {
            "prev_close": self._prev_close,
            "warmup_sum": self._warmup_sum,
            "count": self._count,
            "atr": self._atr,
        }

    def import_state(self, state: dict) -> None:
        self._prev_close = state.get("prev_close")
        self._warmup_sum = float(state.get("warmup_sum", 0.0) or 0.0)
        self._count = int(state.get("count", 0) or 0)
        atr = state.get("atr")
        self._atr = float(atr) if atr is not None else None

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


def _coerce_reference_price(value: Any) -> ReferencePrice:
    if isinstance(value, ReferencePrice):
        return value
    return ReferencePrice(value)


def _coerce_rounding_mode(value: Any) -> RoundingMode:
    if isinstance(value, RoundingMode):
        return value
    return RoundingMode(value)


def _select_reference_price(candle: Any, source: ReferencePrice) -> float:
    """Pick the reference price from a candle for the given source.

    ``typical_price`` = (high + low + close) / 3, ``median_price`` = (high + low) / 2.
    Direct sources fall back to close when a feed omits that field so sizing
    stays well-defined and deterministic.
    """
    if not hasattr(candle, "get"):
        raise TypeError("Provider candle must be a mapping with price fields")
    close = candle.get("close")
    if close is None:
        for key in ("open", "high", "low"):
            if candle.get(key) is not None:
                close = candle.get(key)
                break
    if close is None:
        raise ValueError("Provider candle must contain at least one price field")
    close = float(close)
    high = float(candle.get("high", close))
    low = float(candle.get("low", close))
    open_ = float(candle.get("open", close))

    if source == ReferencePrice.CLOSE:
        return close
    if source == ReferencePrice.OPEN:
        return open_
    if source == ReferencePrice.HIGH:
        return high
    if source == ReferencePrice.LOW:
        return low
    if source == ReferencePrice.TYPICAL_PRICE:
        return (high + low + close) / 3.0
    if source == ReferencePrice.MEDIAN_PRICE:
        return (high + low) / 2.0
    raise ValueError(f"Unsupported reference price: {source}")


class PercentageBrickSizeProvider(BrickSizeProvider):
    """Brick size as a percentage of a reference price.

    ``size = reference_price * (percentage / 100)`` recomputed each candle in
    O(1) time with O(1) memory. There is no historical recalculation: only the
    size used for *future* bricks changes; already-generated bricks are
    immutable. Pure arithmetic with no randomness or wall-clock dependence, so
    replay is deterministic.
    """

    name = "percentage"

    def __init__(
        self,
        percentage: float,
        strategy: Optional[PriceReferenceStrategy] = None,
        reference_price: Optional[ReferencePrice] = None,
        rounding_mode: RoundingMode = RoundingMode.NONE,
        minimum_brick_size: Optional[float] = None,
    ) -> None:
        if percentage is None or percentage <= 0:
            raise RenkoConfigurationError("Percentage must be positive")
        if percentage > 100:
            raise RenkoConfigurationError("Percentage must be <= 100")
        if minimum_brick_size is not None and minimum_brick_size <= 0:
            raise RenkoConfigurationError("Minimum brick size must be positive")
        self._percentage = float(percentage)
        # Price selection is delegated to a PriceReferenceStrategy. An explicit
        # strategy wins; otherwise we derive one from the legacy 6D
        # ``reference_price`` enum; otherwise default to close.
        if strategy is not None:
            self._strategy: PriceReferenceStrategy = strategy
            self._reference_price = (
                _coerce_reference_price(reference_price)
                if reference_price is not None
                else None
            )
        elif reference_price is not None:
            self._reference_price = _coerce_reference_price(reference_price)
            self._strategy = strategy_for_reference_price(self._reference_price)
        else:
            self._reference_price = ReferencePrice.CLOSE
            self._strategy = ClosePriceStrategy()
        self._rounding_mode = _coerce_rounding_mode(rounding_mode)
        self._minimum_brick_size = (
            float(minimum_brick_size) if minimum_brick_size is not None else None
        )
        self._current_size: Optional[float] = None

    @classmethod
    def from_configuration(cls, configuration: BrickConfiguration) -> "PercentageBrickSizeProvider":
        # Resolve the strategy from the built-in registry; the RenkoFactory may
        # later override it with a DI/plugin-extended registry via
        # ``set_price_reference_strategy``.
        from backend.app.chart.renko.strategies import default_strategy_registry

        strategy = default_strategy_registry().create(configuration)
        return cls(
            percentage=configuration.percentage,
            strategy=strategy,
            rounding_mode=configuration.rounding_mode,
            minimum_brick_size=configuration.minimum_brick_size,
        )

    def set_price_reference_strategy(self, strategy: PriceReferenceStrategy) -> None:
        """Inject the price-reference strategy this provider sizes against."""
        self._strategy = strategy

    @property
    def strategy(self) -> PriceReferenceStrategy:
        return self._strategy

    def _apply_rounding(self, size: float) -> float:
        if self._rounding_mode == RoundingMode.NONE:
            return size
        if self._rounding_mode == RoundingMode.FLOOR:
            return float(math.floor(size))
        if self._rounding_mode == RoundingMode.CEIL:
            return float(math.ceil(size))
        if self._rounding_mode == RoundingMode.ROUND:
            # Deterministic round-half-up (avoids banker's rounding surprises).
            return float(math.floor(size + 0.5))
        raise ValueError(f"Unsupported rounding mode: {self._rounding_mode}")

    def update(self, candle: Any) -> None:
        reference = self._strategy.reference_price(candle)
        raw = reference * (self._percentage / 100.0)
        size = self._apply_rounding(raw)
        if self._minimum_brick_size is not None:
            size = max(size, self._minimum_brick_size)
        # Never emit a non-positive size (rounding can floor a tiny size to 0);
        # fall back to the exact unrounded value, which is positive for a
        # positive reference price.
        if size <= 0:
            size = raw
        if size <= 0:
            # Reference price was non-positive (degenerate data); stay un-ready.
            return
        self._current_size = size

    def current_size(self) -> float:
        if self._current_size is None:
            raise RuntimeError("Percentage provider is not ready; no candle seen yet")
        return self._current_size

    def ready(self) -> bool:
        return self._current_size is not None

    def reset(self) -> None:
        self._current_size = None

    def export_state(self) -> dict:
        return {"current_size": self._current_size}

    def import_state(self, state: dict) -> None:
        size = state.get("current_size")
        self._current_size = float(size) if size is not None else None

    # Introspection helpers (tests / diagnostics; not part of the engine path).
    @property
    def percentage(self) -> float:
        return self._percentage

    @property
    def reference_price(self) -> ReferencePrice:
        return self._reference_price

    @property
    def rounding_mode(self) -> RoundingMode:
        return self._rounding_mode

    @property
    def minimum_brick_size(self) -> Optional[float]:
        return self._minimum_brick_size


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
    registry.register("percentage", PercentageBrickSizeProvider.from_configuration)
    return registry
