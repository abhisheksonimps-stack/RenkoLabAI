from __future__ import annotations

from typing import Any

from backend.app.chart.renko.configuration import (
    BrickConfiguration,
    BrickType,
    PriceSource,
    ReferencePrice,
    RenkoMode,
    RoundingMode,
)
from backend.app.chart.renko.exceptions import (
    InvalidBrickSize,
    RenkoConfigurationError,
    UnsupportedRenkoMode,
    ValidationFailed,
)
from backend.app.chart.renko.builder import BrickBuilderRegistry
from backend.app.chart.renko.interfaces import BrickValidator
from backend.app.chart.renko.providers import BrickSizeProviderRegistry
from backend.app.chart.renko.strategies import PriceReferenceStrategyRegistry


class DefaultBrickValidator(BrickValidator):
    def __init__(
        self,
        provider_registry: BrickSizeProviderRegistry | None = None,
        strategy_registry: PriceReferenceStrategyRegistry | None = None,
        builder_registry: BrickBuilderRegistry | None = None,
    ) -> None:
        # Optional: when supplied, the validator can confirm that the configured
        # provider / reference-price strategy / builder actually exist.
        self._provider_registry = provider_registry
        self._strategy_registry = strategy_registry
        self._builder_registry = builder_registry

    async def validate_configuration(self, configuration: BrickConfiguration) -> bool:
        if configuration.brick_size <= 0:
            raise InvalidBrickSize("Brick size must be positive")

        if configuration.price_source not in PriceSource:
            raise RenkoConfigurationError(f"Unsupported price source: {configuration.price_source}")

        if configuration.mode not in RenkoMode:
            raise UnsupportedRenkoMode(f"Unsupported renko mode: {configuration.mode}")

        if configuration.brick_type == BrickType.ATR:
            if configuration.atr_period is None or configuration.atr_period <= 0:
                raise RenkoConfigurationError("ATR period must be a positive integer")
            if configuration.atr_multiplier is not None and configuration.atr_multiplier <= 0:
                raise RenkoConfigurationError("ATR multiplier must be positive")

        if configuration.brick_type == BrickType.PERCENTAGE:
            if configuration.percentage is None or configuration.percentage <= 0:
                raise RenkoConfigurationError("Percentage must be positive")

        if configuration.resolved_provider() == "percentage":
            if configuration.percentage is None or configuration.percentage <= 0:
                raise RenkoConfigurationError("Percentage must be positive")
            if configuration.percentage > 100:
                raise RenkoConfigurationError("Percentage must be <= 100")
            if (
                configuration.minimum_brick_size is not None
                and configuration.minimum_brick_size <= 0
            ):
                raise RenkoConfigurationError("Minimum brick size must be positive")
            try:
                ReferencePrice(configuration.reference_price)
            except ValueError:
                raise RenkoConfigurationError(
                    f"Unsupported reference price: {configuration.reference_price}"
                )
            try:
                RoundingMode(configuration.rounding_mode)
            except ValueError:
                raise RenkoConfigurationError(
                    f"Unsupported rounding mode: {configuration.rounding_mode}"
                )

        if configuration.brick_type == BrickType.MEAN:
            if configuration.mean_lookback is None or configuration.mean_lookback <= 0:
                raise RenkoConfigurationError("Mean lookback must be positive")

        if configuration.brick_type == BrickType.MEDIAN:
            if configuration.median_lookback is None or configuration.median_lookback <= 0:
                raise RenkoConfigurationError("Median lookback must be positive")

        if configuration.brick_type == BrickType.HYBRID:
            if configuration.hybrid_weight is None or not (0.0 <= configuration.hybrid_weight <= 1.0):
                raise RenkoConfigurationError("Hybrid weight must be between 0 and 1")

        if configuration.brick_type == BrickType.AI:
            if not configuration.ai_model:
                raise RenkoConfigurationError("AI model identifier must be provided for AI Renko")

        if self._provider_registry is not None:
            provider_name = configuration.resolved_provider()
            if not self._provider_registry.exists(provider_name):
                raise RenkoConfigurationError(f"Unknown brick-size provider: {provider_name}")

        if self._strategy_registry is not None:
            strategy_name = configuration.resolved_reference_strategy()
            if not self._strategy_registry.exists(strategy_name):
                raise RenkoConfigurationError(
                    f"Unknown reference price strategy: {strategy_name}"
                )

        if self._builder_registry is not None:
            builder_name = configuration.resolved_builder()
            if not self._builder_registry.exists(builder_name):
                raise RenkoConfigurationError(f"Unknown brick builder: {builder_name}")

        if configuration.resolved_provider() == "adaptive":
            self._validate_adaptive(configuration)

        return True

    def _validate_adaptive(self, configuration) -> None:
        # Adaptive composes Fixed (low) / Percentage (medium) / ATR (high), so the
        # parameters those children need must be present and valid.
        if configuration.brick_size is None or configuration.brick_size <= 0:
            raise RenkoConfigurationError("Adaptive requires a positive brick_size (low regime)")
        if configuration.percentage is None or configuration.percentage <= 0:
            raise RenkoConfigurationError("Adaptive requires a positive percentage (medium regime)")
        if configuration.atr_period is None or configuration.atr_period <= 0:
            raise RenkoConfigurationError("Adaptive requires a positive atr_period (high regime)")

        if configuration.adaptive_window is not None and configuration.adaptive_window <= 0:
            raise RenkoConfigurationError("adaptive_window must be a positive integer")
        if configuration.adaptive_hysteresis is not None and configuration.adaptive_hysteresis < 0:
            raise RenkoConfigurationError("adaptive_hysteresis must be >= 0")
        thresholds = configuration.adaptive_thresholds
        if thresholds is not None:
            t = tuple(thresholds)
            if len(t) != 2 or not (t[0] < t[1]) or t[0] <= 0:
                raise RenkoConfigurationError(
                    "adaptive_thresholds must be two ascending positive values"
                )

    async def validate_data(self, market_data: Any) -> bool:
        if market_data is None:
            raise ValidationFailed("Market data cannot be None")
        if not hasattr(market_data, "get") and not isinstance(market_data, dict):
            raise ValidationFailed("Market data must be a dict-like object")
        if "timestamp" not in market_data:
            raise ValidationFailed("Market data must contain timestamp")
        if not any(key in market_data for key in ("open", "high", "low", "close")):
            raise ValidationFailed("Market data must include at least one price field")
        return True

    async def validate_transition(self, previous_state, next_state) -> bool:
        if previous_state is None or next_state is None:
            raise ValidationFailed("State transition requires both previous and next state")
        if previous_state.brick_size != next_state.brick_size:
            raise ValidationFailed("Brick size cannot change during state transition")
        return True
