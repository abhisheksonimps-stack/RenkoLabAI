from __future__ import annotations

from typing import Any

from backend.app.chart.renko.configuration import BrickConfiguration, BrickType, PriceSource, RenkoMode
from backend.app.chart.renko.exceptions import (
    InvalidBrickSize,
    RenkoConfigurationError,
    UnsupportedRenkoMode,
    ValidationFailed,
)
from backend.app.chart.renko.interfaces import BrickValidator


class DefaultBrickValidator(BrickValidator):
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

        if configuration.brick_type == BrickType.PERCENTAGE:
            if configuration.percentage is None or configuration.percentage <= 0:
                raise RenkoConfigurationError("Percentage must be positive")

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

        return True

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
